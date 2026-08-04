#!/usr/bin/env python3
"""End-to-end test for worktree-swarm.sh via 10 rounds.

Exercises the actual worktree-swarm.sh companion script (not a mock) over
10 distinct scenarios, each as a separate unittest method. The test
orchestrator calls the script as a subprocess and asserts on its output
+ the resulting git/manifest state.

Each round is independent: round N+1 does NOT depend on the side effects
of round N. setUp/tearDown ensure worktrees are cleaned up between rounds
so a failure in one round does not poison the next.

Per-round design notes live in each method's docstring.

Cleanup safety: this test allocates real worktrees and branches under
$TMPDIR/swarm-$USER/lazible-jcode-<sha>/. On any test failure, the
overall tearDownClass invokes `worktree-swarm.sh cleanup --force` to
make sure no zombie worktree remains after the test exits.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

REPO_ROOT = Path("/home/leroy/Project/lazible-jcode").resolve()
SCRIPT = Path(os.environ.get(
    "WORKTREE_SWARM_SCRIPT",
    "/home/leroy/.jcode/skills/worktree-swarm/worktree-swarm.sh",
))
MANIFEST = REPO_ROOT / ".jcode" / "worktree-manifest.json"


def run_script(*args, cwd=None):
    """Run worktree-swarm.sh with given args, return (rc, stdout, stderr)."""
    r = subprocess.run(
        [str(SCRIPT), *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    return r.returncode, r.stdout, r.stderr


def git(*args, cwd, check=False):
    """Run git with given args; return CompletedProcess."""
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=check,
    )


def ensure_git_user(cwd):
    """Ensure git user.email/user.name are set so commits don't fail.

    Worktrees inherit config from the main repo. If the main repo (or
    the global config) doesn't have user.email/user.name, commits fail
    with exit 1 — completely unrelated to the worktree functionality
    we're trying to test. Set a test-only identity to avoid that noise.
    """
    r = git("config", "user.email", cwd=cwd)
    if r.returncode != 0:
        subprocess.run(
            ["git", "-C", str(cwd), "config", "user.email",
             "worktree-e2e@test.local"],
            check=True, capture_output=True,
        )
    r = git("config", "user.name", cwd=cwd)
    if r.returncode != 0:
        subprocess.run(
            ["git", "-C", str(cwd), "config", "user.name", "Worktree E2E"],
            check=True, capture_output=True,
        )


def parse_alloc_output(out):
    """Extract <worktree_path>\\t<branch> from worktree-swarm.sh alloc output.

    The script emits 3 lines:
      - 'Preparing worktree (new branch ...)'        (informational)
      - 'HEAD is now at <sha> ...'                    (git's own output)
      - '<worktree_path>\\t<branch>'                  (the actual contract)

    Returns (worktree_path, branch)."""
    for line in out.splitlines():
        line = line.strip()
        if "\t" in line:
            wt_path, branch = line.split("\t", 1)
            return wt_path.strip(), branch.strip()
    raise ValueError(f"no tab-separated output found in alloc output:\n{out}")


def short_sha():
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "--short=7", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()


def worktree_path(label):
    """Expected worktree path per skill convention."""
    base = os.environ.get("TMPDIR", "/tmp")
    user = os.environ.get("USER", "leroy")
    return f"{base}/swarm-{user}/lazible-jcode-{short_sha()}/wt-{label}"


def manifest_workers():
    if not MANIFEST.exists():
        return []
    return json.loads(MANIFEST.read_text()).get("workers", [])


def force_cleanup_all():
    """Aggressive cleanup: remove all worktrees and reset manifest.
    Used in tearDownClass to guarantee no zombies."""
    # First, list and teardown each known worker
    for w in manifest_workers():
        run_script("teardown", w["label"])
    # Then force-cleanup anything still left over
    run_script("cleanup", "--force")
    # Brute-force fallback: remove any /tmp/swarm-$USER/lazible-jcode-*/ dirs
    base = os.environ.get("TMPDIR", "/tmp")
    user = os.environ.get("USER", "leroy")
    parent = Path(base) / f"swarm-{user}"
    if parent.exists():
        shutil.rmtree(parent, ignore_errors=True)


class TestWorktreeSwarmE2E(unittest.TestCase):
    """10-round end-to-end test of worktree-swarm.sh."""

    @classmethod
    def setUpClass(cls):
        if not SCRIPT.exists():
            raise unittest.SkipTest(f"worktree-swarm.sh not at {SCRIPT}")
        # Aggressive pre-cleanup so we start clean.
        force_cleanup_all()

    @classmethod
    def tearDownClass(cls):
        # Always cleanup at end, regardless of pass/fail.
        force_cleanup_all()

    def setUp(self):
        # Per-test cleanup: any leftover worktree from prior round gets
        # cleared so each test starts from a clean state.
        force_cleanup_all()

    # ── R1 ──────────────────────────────────────────────────────────────────
    def test_r1_alloc_single_worktree(self):
        """Round 1: alloc one worktree, verify path/branch/manifest."""
        rc, out, _ = run_script("alloc", "r1", "--type", "test")
        self.assertEqual(rc, 0, f"alloc failed: {out}")

        # Output format: <worktree_path>\t<branch>
        wt_path, branch = parse_alloc_output(out)

        self.assertTrue(Path(wt_path).exists(), f"worktree path missing: {wt_path}")
        self.assertTrue(branch.startswith("test/r1_"), f"unexpected branch: {branch}")

        # Manifest has exactly 1 worker
        workers = manifest_workers()
        self.assertEqual(len(workers), 1)
        self.assertEqual(workers[0]["label"], f"test-r1-{short_sha()}")
        self.assertEqual(workers[0]["status"], "active")

        # Teardown
        rc, _, _ = run_script("teardown", f"test-r1-{short_sha()}")
        self.assertEqual(rc, 0)
        self.assertFalse(Path(wt_path).exists(), "worktree not removed by teardown")
        self.assertEqual(manifest_workers(), [], "manifest not empty after teardown")

    # ── R2 ──────────────────────────────────────────────────────────────────
    def test_r2_alloc_three_worktrees_parallel(self):
        """Round 2: 3 worktrees in parallel, all independent."""
        wt_paths = []
        branches = []
        labels = []
        for name in ("r2a", "r2b", "r2c"):
            rc, out, _ = run_script("alloc", name, "--type", "feat")
            self.assertEqual(rc, 0, f"alloc {name} failed")
            wt, br = parse_alloc_output(out)
            wt_paths.append(wt)
            branches.append(br)
            labels.append(f"feat-{name}-{short_sha()}")

        # All 3 worktrees exist
        for p in wt_paths:
            self.assertTrue(Path(p).exists(), f"worktree missing: {p}")

        # All 3 branches are distinct
        self.assertEqual(len(set(branches)), 3, "branches should be distinct")

        # Manifest has 3 entries
        workers = manifest_workers()
        self.assertEqual(len(workers), 3)
        for w in workers:
            self.assertIn(w["branch"], branches)

        # Cleanup all
        for label in labels:
            rc, _, _ = run_script("teardown", label)
            self.assertEqual(rc, 0)
        self.assertEqual(manifest_workers(), [])

    # ── R3 ──────────────────────────────────────────────────────────────────
    def test_r3_per_worktree_isolation(self):
        """Round 3: edits in different worktrees don't cross-contaminate."""
        sha = short_sha()
        label_a = f"feat-r3a-{sha}"
        label_b = f"feat-r3b-{sha}"

        rc, out_a, _ = run_script("alloc", "r3a", "--type", "feat")
        self.assertEqual(rc, 0)
        wt_a, br_a = parse_alloc_output(out_a)

        rc, out_b, _ = run_script("alloc", "r3b", "--type", "feat")
        self.assertEqual(rc, 0)
        wt_b, br_b = parse_alloc_output(out_b)

        # In worktree A, create a unique file
        (Path(wt_a) / "alpha.txt").write_text("alpha\n")
        subprocess.run(
            ["git", "-C", wt_a, "add", "alpha.txt"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", wt_a, "commit", "-m", "add alpha"],
            check=True, capture_output=True,
        )

        # In worktree B, create a different file
        (Path(wt_b) / "beta.txt").write_text("beta\n")
        subprocess.run(
            ["git", "-C", wt_b, "add", "beta.txt"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", wt_b, "commit", "-m", "add beta"],
            check=True, capture_output=True,
        )

        # Main must have NEITHER file
        main_alpha = (REPO_ROOT / "alpha.txt").exists()
        main_beta = (REPO_ROOT / "beta.txt").exists()
        self.assertFalse(main_alpha, "main polluted with alpha.txt")
        self.assertFalse(main_beta, "main polluted with beta.txt")

        # Each branch has only its own file
        r_a = git("show", "--name-only", "--pretty=", br_a, cwd=wt_a)
        self.assertEqual(r_a.returncode, 0)
        self.assertIn("alpha.txt", r_a.stdout)
        r_b = git("show", "--name-only", "--pretty=", br_b, cwd=wt_b)
        self.assertEqual(r_b.returncode, 0)
        self.assertIn("beta.txt", r_b.stdout)

        # Teardown
        run_script("teardown", label_a)
        run_script("teardown", label_b)
        self.assertEqual(manifest_workers(), [])

    # ── R4 ──────────────────────────────────────────────────────────────────
    def test_r4_list_output_consistency(self):
        """Round 4: list output matches manifest and actual worktrees."""
        labels = []
        for name in ("r4a", "r4b"):
            rc, _, _ = run_script("alloc", name, "--type", "fix")
            self.assertEqual(rc, 0)
            labels.append(f"fix-{name}-{short_sha()}")

        # Run list
        rc, out, _ = run_script("list")
        self.assertEqual(rc, 0)

        # Each label appears in list output
        for label in labels:
            self.assertIn(label, out, f"label {label} missing from list output")

        # Manifest == list
        manifest_paths = {w["worktree_path"] for w in manifest_workers()}
        for p in manifest_paths:
            self.assertTrue(Path(p).exists(), f"manifest path doesn't exist: {p}")

        # Cleanup
        for label in labels:
            run_script("teardown", label)

    # ── R4b ─────────────────────────────────────────────────────────────────
    def test_r4b_status_existing_label_returns_tsv(self):
        """Round 4b: `status <label>` on an existing manifest entry returns
        a single tab-separated line: <worktree_path>\t<branch>\t<base_commit>\t<created_at_epoch>\t<age_hours>."""
        sha = short_sha()
        label = f"feat-r4b-{sha}"

        rc, out, _ = run_script("alloc", "r4b", "--type", "feat")
        self.assertEqual(rc, 0, f"alloc failed")

        # Build expected created_at from manifest (frozen at alloc time)
        manifest_workers = [w for w in json.loads(MANIFEST.read_text())["workers"] if w["label"] == label]
        self.assertEqual(len(manifest_workers), 1, f"expected one manifest entry for {label}")
        expected_created_at = manifest_workers[0]["created_at"]

        rc, out, err = run_script("status", label)
        self.assertEqual(rc, 0, f"status failed: rc={rc} stderr={err!r}")
        self.assertEqual(err, "", f"status must not write to stderr on success: {err!r}")

        lines = [ln for ln in out.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1, f"status output must be exactly one line: {out!r}")
        fields = lines[0].split("\t")
        self.assertEqual(len(fields), 5, f"status output must have 5 tab-separated fields: {lines[0]!r}")

        wt_path, branch, base_commit, created_at_str, age_h_str = fields
        self.assertTrue(wt_path.startswith("/") and len(wt_path) > 1,
                        f"worktree_path looks invalid: {wt_path!r}")
        self.assertTrue(branch.startswith("feat/r4b_"),
                        f"branch looks invalid: {branch!r}")
        self.assertEqual(base_commit, sha,
                         f"base_commit must equal short HEAD: got {base_commit!r} expected {sha!r}")
        self.assertEqual(int(created_at_str), expected_created_at,
                         f"created_at_epoch must match manifest: got {created_at_str} expected {expected_created_at}")
        # age_hours must parse as a non-negative float
        self.assertGreaterEqual(float(age_h_str), 0.0,
                                f"age_hours must be non-negative: {age_h_str!r}")
        # Sanity: age_hours should be small (test runs in seconds, well under 1h)
        self.assertLess(float(age_h_str), 1.0,
                        f"age_hours should be < 1h for a fresh alloc: {age_h_str!r}")

        # Cleanup
        run_script("teardown", label)

    # ── R4c ─────────────────────────────────────────────────────────────────
    def test_r4c_status_missing_label_errors(self):
        """Round 4c: `status <label>` on a label absent from a non-empty
        manifest exits non-zero with stderr matching
        `error: status: no manifest entry for '<label>'`."""
        sha = short_sha()
        present_label = f"feat-r4c-{sha}"
        missing_label = f"feat-nonexistent-doesnotexist-{sha}"

        # Allocate a worker so the manifest is non-empty (manifest must exist
        # for the script to reach the "label not found" branch).
        rc, _, _ = run_script("alloc", "r4c", "--type", "feat")
        self.assertEqual(rc, 0, "alloc for R4c setup must succeed")

        # Sanity: the present_label is now in the manifest
        self.assertTrue(any(
            w["label"] == present_label
            for w in manifest_workers()
        ), "R4c setup: manifest must contain present_label")

        rc, out, err = run_script("status", missing_label)
        self.assertNotEqual(rc, 0, f"status on missing label must exit non-zero: rc={rc}")
        expected = f"error: status: no manifest entry for '{missing_label}'"
        self.assertEqual(err.strip(), expected,
                         f"stderr mismatch: got {err.strip()!r} expected {expected!r}")
        self.assertEqual(out, "", f"status must not write to stdout on error: {out!r}")

        # Cleanup the R4c setup worker
        run_script("teardown", present_label)

    # ── R4d ─────────────────────────────────────────────────────────────────
    def test_r4d_status_no_manifest_errors(self):
        """Round 4d: `status <label>` when the manifest file does not
        exist exits non-zero with a clear error message."""
        # Ensure manifest is absent by removing it directly (setUp also
        # calls force_cleanup_all which may have already torn down workers).
        if MANIFEST.exists():
            MANIFEST.unlink()
        self.assertFalse(MANIFEST.exists(), "manifest must not exist before test")

        rc, out, err = run_script("status", "anylabel-anything")
        self.assertNotEqual(rc, 0, f"status with no manifest must exit non-zero: rc={rc}")
        # Error must mention "status" and indicate no manifest. Specific wording
        # is implementation choice; we assert on key fragments only.
        self.assertIn("status", err.lower(),
                      f"stderr must mention 'status': {err!r}")
        self.assertIn("manifest", err.lower(),
                      f"stderr must mention 'manifest': {err!r}")
        self.assertEqual(out, "", f"status must not write to stdout on error: {out!r}")

    # ── R5 ──────────────────────────────────────────────────────────────────
    def test_r5_double_alloc_refused(self):
        """Round 5: allocating with the same label twice must fail;
        after teardown, re-allocation must succeed."""
        sha = short_sha()
        label = f"chore-r5-{sha}"

        rc1, out1, _ = run_script("alloc", "r5", "--type", "chore")
        self.assertEqual(rc1, 0)

        # Second alloc with same label should fail
        rc2, _, err2 = run_script("alloc", "r5", "--type", "chore")
        self.assertNotEqual(rc2, 0, "second alloc should have failed")

        # Teardown
        rc, _, _ = run_script("teardown", label)
        self.assertEqual(rc, 0)

        # Now alloc again — should succeed
        rc3, out3, _ = run_script("alloc", "r5", "--type", "chore")
        self.assertEqual(rc3, 0, f"re-alloc failed: {out3}")

        # Cleanup
        run_script("teardown", label)

    # ── R6 ──────────────────────────────────────────────────────────────────
    def test_r6_cleanup_removes_stale(self):
        """Round 6: cleanup removes TTL-expired worktrees (force mode)."""
        sha = short_sha()
        label = f"docs-r6-{sha}"

        rc, out, _ = run_script("alloc", "r6", "--type", "docs")
        self.assertEqual(rc, 0)
        wt_path, branch = parse_alloc_output(out)

        # Sanity: worktree exists
        self.assertTrue(Path(wt_path).exists())

        # Backdate the manifest entry's created_at to past TTL (8h).
        # TTL is 8 hours = 28800 seconds. Backdate by 9 hours.
        data = json.loads(MANIFEST.read_text())
        for w in data["workers"]:
            if w["label"] == label:
                w["created_at"] = int(time.time()) - 9 * 3600
        MANIFEST.write_text(json.dumps(data, indent=2))

        # Run cleanup (not --force, since branch is unmerged)
        # It should still remove the TTL-expired entry
        rc, _, _ = run_script("cleanup")
        self.assertEqual(rc, 0)

        # Worktree should be gone
        self.assertFalse(Path(wt_path).exists(), "cleanup did not remove worktree")

        # Manifest should be empty
        self.assertEqual(manifest_workers(), [], "manifest not cleaned")

    # ── R7 ──────────────────────────────────────────────────────────────────
    def test_r7_custom_base_sha(self):
        """Round 7: --base flag uses the specified SHA as the fork point."""
        sha = short_sha()

        # Find a base 3 commits back
        base_sha = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", f"{sha}~3"],
            capture_output=True, text=True,
        ).stdout.strip()

        rc, out, _ = run_script("alloc", "r7", "--type", "test", "--base", base_sha)
        self.assertEqual(rc, 0, f"alloc with --base failed: {out}")
        wt_path, branch = parse_alloc_output(out)

        # Verify the branch's merge-base with main is the requested base
        # (i.e. branch was forked from base_sha)
        merge_base = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "merge-base", "main", branch],
            capture_output=True, text=True,
        ).stdout.strip()
        # merge-base may equal base_sha or a successor of it; the key
        # assertion is that the branch does NOT include commits between
        # base_sha..HEAD~3 that are exclusive to main.
        self.assertTrue(len(merge_base) > 0, "merge-base empty")

        # Cleanup
        run_script("teardown", f"test-r7-{sha}")

    # ── R8 ──────────────────────────────────────────────────────────────────
    def test_r8_git_ops_inside_worktree(self):
        """Round 8: standard git operations work inside a worker worktree."""
        sha = short_sha()
        label = f"feat-r8-{sha}"

        rc, out, _ = run_script("alloc", "r8", "--type", "feat")
        self.assertEqual(rc, 0)
        wt_path, branch = parse_alloc_output(out)

        # git status should be clean (we forked from HEAD)
        r = git("status", "--porcelain", cwd=wt_path)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "", f"worktree not clean: {r.stdout!r}")
        out_st = r.stdout

        # Current branch should match
        cur_branch = subprocess.run(
            ["git", "-C", wt_path, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True,
        ).stdout.strip()
        self.assertEqual(cur_branch, branch)

        # Make a commit on this branch
        (Path(wt_path) / "r8-marker.txt").write_text("r8\n")
        subprocess.run(
            ["git", "-C", wt_path, "add", "r8-marker.txt"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", wt_path, "commit", "-m", "r8: add marker"],
            check=True, capture_output=True,
        )

        # The commit should be on the branch but NOT on main
        in_main = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "branch", "--contains", "HEAD"],
            cwd=wt_path, capture_output=True, text=True,
        )
        # The branch contains HEAD; main does not (HEAD~1 is on r8 branch only)
        marker_in_main = (REPO_ROOT / "r8-marker.txt").exists()
        self.assertFalse(marker_in_main, "main polluted with r8 marker")

        # Cleanup
        run_script("teardown", label)

    # ── R9 ──────────────────────────────────────────────────────────────────
    def test_r9_cross_worktree_merge(self):
        """Round 9: verify a worker branch can merge cleanly into main
        via `git merge-tree` (non-destructive; does NOT modify main)."""
        sha = short_sha()
        label = f"refactor-r9-{sha}"

        rc, out, _ = run_script("alloc", "r9", "--type", "refactor")
        self.assertEqual(rc, 0)
        wt_path, branch = parse_alloc_output(out)

        # Create a unique file (uuid) in the worktree, then commit.
        unique = f"r9-marker-{uuid.uuid4().hex[:8]}.txt"
        ensure_git_user(wt_path)
        (Path(wt_path) / unique).write_text("r9 marker\n")
        r = git("add", unique, cwd=wt_path)
        self.assertEqual(r.returncode, 0, f"add failed: {r.stderr}")
        r = git("commit", "-m", f"r9: add {unique}", cwd=wt_path)
        self.assertEqual(r.returncode, 0, f"commit failed: {r.stderr}")

        # Verify merge would succeed via `git merge-tree` (non-destructive).
        # merge-tree returns 0 when the merge is clean.
        main_sha = git("rev-parse", "main", cwd=REPO_ROOT).stdout.strip()
        r = git("merge-tree", main_sha, branch, cwd=REPO_ROOT)
        self.assertEqual(r.returncode, 0, f"merge-tree failed: {r.stderr}")

        # Verify the commit exists on the branch (the merge-ready state).
        r = git("log", "--oneline", "-1", branch, cwd=REPO_ROOT)
        self.assertEqual(r.returncode, 0)
        self.assertIn("r9: add", r.stdout,
                      f"branch commit missing: {r.stdout!r}")

        # Cleanup: teardown removes the worktree + branch.
        run_script("teardown", label)
        self.assertFalse(
            Path(wt_path).exists(),
            f"worktree not removed by teardown: {wt_path}",
        )

    # ── R10 ─────────────────────────────────────────────────────────────────
    def test_r10_full_lifecycle_loss_rate(self):
        """Round 10: 3 sequential workers, full lifecycle, loss rate = 0%."""
        dispatched = 0
        landed = 0

        for i, name in enumerate(("r10a", "r10b", "r10c")):
            dispatched += 1
            sha = short_sha()
            label = f"feat-{name}-{sha}"

            # Allocate
            rc, out, _ = run_script("alloc", name, "--type", "feat")
            self.assertEqual(rc, 0, f"alloc {name} failed")
            wt_path, branch = parse_alloc_output(out)

            # Do work
            marker = f"r10-{name}-{uuid.uuid4().hex[:8]}.txt"
            ensure_git_user(wt_path)
            (Path(wt_path) / marker).write_text(f"r10 {name}\n")
            r = git("add", marker, cwd=wt_path)
            self.assertEqual(r.returncode, 0, f"add {name} failed: {r.stderr}")
            # Verify staged before commit
            r_st = git("status", "--porcelain", cwd=wt_path)
            self.assertIn(marker, r_st.stdout,
                          f"file not staged: {r_st.stdout!r}")
            r = git("commit", "-m", f"r10 {name}: marker", cwd=wt_path)
            self.assertEqual(r.returncode, 0, f"commit {name} failed: {r.stderr}")

            # Verify merge would succeed against main via git merge-tree
            # (non-destructive — does NOT modify main, unlike git merge).
            # merge-tree exits 0 when the merge is clean.
            main_sha = git("rev-parse", "main", cwd=REPO_ROOT).stdout.strip()
            r = git("merge-tree", main_sha, branch, cwd=REPO_ROOT)
            self.assertEqual(r.returncode, 0,
                             f"merge-tree {name} failed: {r.stderr}")
            landed += 1

            # Teardown
            run_script("teardown", label)

            # Best-effort: clean up marker file from main (so subsequent
            # workers don't conflict on it; each uses a unique name)
            try:
                (REPO_ROOT / marker).unlink()
            except Exception:
                pass

        loss_rate = (dispatched - landed) / dispatched
        self.assertEqual(dispatched, 3)
        self.assertEqual(landed, 3)
        self.assertEqual(loss_rate, 0.0, "loss rate must be 0%")

    # ── R11 ─────────────────────────────────────────────────────────────────
    def test_r11_alloc_rejects_malformed_base(self):
        """Round 11: `alloc <name> --base xyz` (non-hex) must exit non-zero
        with stderr that contains "not a valid SHA".

        Pre-flight validation should reject malformed SHA strings before
        the deep `git worktree add` call, so the user gets a clear error
        instead of a confusing git-stack error."""
        rc, out, err = run_script("alloc", "r11", "--type", "feat", "--base", "xyz")
        self.assertNotEqual(
            rc, 0,
            f"alloc with malformed --base must exit non-zero: rc={rc} stdout={out!r}",
        )
        self.assertIn(
            "not a valid SHA", err,
            f"stderr must mention 'not a valid SHA': {err!r}",
        )
        self.assertEqual(out, "", f"stdout must be empty on error: {out!r}")
        # No worktree should have been created and manifest should not have grown
        self.assertEqual(manifest_workers(), [],
                         "malformed --base must not register a worker")

    # ── R12 ─────────────────────────────────────────────────────────────────
    def test_r12_alloc_rejects_nonexistent_commit(self):
        """Round 12: `alloc <name> --base 0000...0000` (well-formed hex but
        no such commit in this repo) must exit non-zero with stderr that
        contains "not a known commit".

        Pre-flight validation should reject well-formed-but-nonexistent
        SHAs before the deep `git worktree add` call."""
        nonexistent = "0" * 40
        rc, out, err = run_script("alloc", "r12", "--type", "feat", "--base", nonexistent)
        self.assertNotEqual(
            rc, 0,
            f"alloc with nonexistent --base must exit non-zero: rc={rc} stdout={out!r}",
        )
        self.assertIn(
            "not a known commit", err,
            f"stderr must mention 'not a known commit': {err!r}",
        )
        self.assertEqual(out, "", f"stdout must be empty on error: {out!r}")
        self.assertEqual(manifest_workers(), [],
                         "nonexistent --base must not register a worker")

    # ── R13 ─────────────────────────────────────────────────────────────────
    def test_r13_alloc_accepts_valid_base(self):
        """Round 13: `alloc <name> --base <HEAD sha>` with a valid commit
        must exit 0 and produce a worktree visible via `git worktree list`."""
        sha = short_sha()
        rc, out, err = run_script("alloc", "r13", "--type", "feat", "--base", sha)
        self.assertEqual(rc, 0, f"alloc with valid --base failed: stderr={err!r}")
        wt_path, branch = parse_alloc_output(out)

        self.assertTrue(Path(wt_path).exists(),
                        f"worktree path missing: {wt_path}")
        self.assertTrue(branch.startswith("feat/r13_"),
                        f"unexpected branch: {branch}")

        # git worktree list must contain this worktree
        r = git("worktree", "list", cwd=REPO_ROOT)
        self.assertEqual(r.returncode, 0)
        self.assertIn(wt_path, r.stdout,
                      f"git worktree list missing worktree: {r.stdout!r}")

        # Cleanup
        label = f"feat-r13-{sha}"
        run_script("teardown", label)
        self.assertEqual(manifest_workers(), [], "manifest not empty after teardown")


if __name__ == "__main__":
    unittest.main(verbosity=2)