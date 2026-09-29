#!/usr/bin/env python3
# Tests for jcode-orchestrate state machine (T7-T12).
#
# Run from any cwd; uses a temp git repo + temp goal home so nothing leaks.
# Exits non-zero on any assertion failure.
#
# Coverage (per design doc):
#   T7 : happy review (verified via CLI; same logic)
#   T8 : reviewer findings -> precise step reset
#   T9 : review_retry exhausted -> escalated
#   T10: reviewer crashed -> handled as no-confidence (retry path)
#   T11: coder_session_id != reviewer_session_id (always true)
#   T12: --no-review bypass

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
GOAL = REPO / "config" / "bin" / "jcode-goal"
ORCH = REPO / "config" / "bin" / "jcode-orchestrate"

# Use a stable goal_id substring so we can find goals after creation
PASS = 0
FAIL = 0


def run(cmd: list[str], env: dict | None = None, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, env=env, check=False, **kw)


def setup_repo() -> tuple[Path, str]:
    """Create temp git repo, init goal, return (goal_home, goal_id)."""
    home = Path(tempfile.mkdtemp(prefix="orch-test-"))
    # Init git repo so project_hash matches
    run(["git", "init", "-q", str(home)])
    run(["git", "-C", str(home), "config", "user.email", "test@test"])
    run(["git", "-C", str(home), "config", "user.name", "test"])
    (home / "README.md").write_text("init")
    run(["git", "-C", str(home), "add", "README.md"])
    run(["git", "-C", str(home), "commit", "-q", "-m", "init"])
    env = os.environ.copy()
    env["JCODE_GOAL_HOME"] = str(home)
    # Pass --cwd home so jcode-goal hashes the test repo, not parent bash cwd.
    out = run([str(GOAL), "add", "Test", "--priority", "high",
               "--content", "test", "--scope", "project", "--cwd", str(home)], env=env)
    assert out.returncode == 0, out.stderr
    # list/show do not accept --cwd; change cwd so subsequent commands hash home.
    cwd_backup = os.getcwd()
    os.chdir(home)
    return home, json.loads(run([str(GOAL), "list", "--json"], env=env).stdout)[0]["id"], cwd_backup


def orchestrate(home: Path, fake_report: str = '{"verdict":"clean","findings":[],"confidence":1.0}') -> str:
    env = os.environ.copy()
    env["JCODE_GOAL_HOME"] = str(home)
    out = run([str(ORCH), "--dry-run", "--cwd", str(home),
               "--fake-report", fake_report], env=env)
    return out.stdout


def get_goal(home: Path, gid: str) -> dict:
    env = os.environ.copy()
    env["JCODE_GOAL_HOME"] = str(home)
    out = run([str(GOAL), "show", gid, "--cwd", str(home)], env=env)
    # show returns human-readable; use list --json instead and find
    data = json.loads(run([str(GOAL), "list", "--json"], env=env).stdout)
    return next(g for g in data if g["id"] == gid)


def cycle_until(home: Path, gid: str, n: int, fake_report: str = '{"verdict":"clean","findings":[],"confidence":1.0}') -> int:
    """Run up to n cycles, stop early when goal status != 'active'."""
    for i in range(n):
        out = orchestrate(home, fake_report)
        if "no active goals" in out:
            return i
        g = get_goal(home, gid)
        if g["status"] != "active":
            return i + 1
    return n


def step_status(g: dict, mid: str, sid: str) -> str:
    m = next(m for m in g["milestones"] if m["id"] == mid)
    s = next(s for s in m["steps"] if s["id"] == sid)
    return s["status"]


def milestone_status(g: dict, mid: str) -> str:
    return next(m for m in g["milestones"] if m["id"] == mid)["status"]


def assert_eq(actual, expected, label):
    global PASS, FAIL
    if actual == expected:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}: got {actual!r}, expected {expected!r}")


def assert_in(needle, haystack, label):
    global PASS, FAIL
    if needle in haystack:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}: {needle!r} not in {haystack!r}")


# ---------------------------------------------------------------------------
# T7: happy review (covered by main test runner; re-verified here)
# ---------------------------------------------------------------------------
def test_t7_happy_review():
    print("T7: happy review (verdict=clean)")
    home, gid, cwd_backup = setup_repo()
    try:
        env = os.environ.copy()
        env["JCODE_GOAL_HOME"] = str(home)
        # milestone/step 'add' subcommands don't accept --cwd;
        # setup_repo already chdir'd into home.
        run([str(GOAL), "milestone", gid, "add", "M0",
             "--review-criteria", "tests"], env=env)
        run([str(GOAL), "step", gid, "m-0", "add", "implement X",
             "--verify", "true"], env=env)

        cycles = cycle_until(home, gid, 10)
        g = get_goal(home, gid)
        assert_eq(g["status"], "complete", "T7 goal status")
        assert_eq(milestone_status(g, "m-0"), "completed", "T7 milestone status")
        assert_eq(g["milestones"][0]["review_verdict"], "clean", "T7 review_verdict")
        assert_eq(g["milestones"][0]["reviewer_label"], "reviewer:m-0", "T7 reviewer_label")
        assert_eq(cycles, 4, "T7 cycle count")
    finally:
        os.chdir(cwd_backup)
        shutil.rmtree(home, ignore_errors=True)


# ---------------------------------------------------------------------------
# T8: reviewer findings -> precise step reset
# ---------------------------------------------------------------------------
def test_t8_findings_precise_reset():
    print("T8: reviewer findings -> precise step reset")
    home, gid, cwd_backup = setup_repo()
    try:
        env = os.environ.copy()
        env["JCODE_GOAL_HOME"] = str(home)
        run([str(GOAL), "milestone", gid, "add", "M0"], env=env)
        run([str(GOAL), "step", gid, "m-0", "add", "step-A",
             "--verify", "true"], env=env)
        run([str(GOAL), "step", gid, "m-0", "add", "step-B",
             "--verify", "true"], env=env)

        # Cycle 1: spawn coder for step-A (cycle1)
        out = orchestrate(home)
        # Cycle 2: step-A done, spawn coder for step-B (cycle2)
        out = orchestrate(home)
        # Cycle 3: step-B done, milestone_in_progress (cycle3)
        out = orchestrate(home)
        # Cycle 4: spawn reviewer (cycle4)
        out = orchestrate(home)
        # Cycle 5: reviewer returns findings targeting step-B only
        findings = ('{"verdict":"findings","findings":'
                    '[{"step_id":"m-0-step-1","severity":"major",'
                    '"location":"src/x.rs:42","issue":"missing edge case"}],'
                    '"confidence":0.8,"reasoning":"needs work"}')
        out = orchestrate(home, findings)
        g = get_goal(home, gid)

        assert_in("review_failed", out, "T8 review_failed action")
        # step-A should remain done; step-B should be reset to pending
        assert_eq(step_status(g, "m-0", "m-0-step-0"), "done", "T8 step-A unchanged")
        assert_eq(step_status(g, "m-0", "m-0-step-1"), "pending", "T8 step-B reset to pending")
        # last_findings should be attached to step-B
        s_b = next(s for s in g["milestones"][0]["steps"] if s["id"] == "m-0-step-1")
        assert_in("missing edge case", s_b.get("last_findings") or "", "T8 findings attached")
        # milestone re-opened as in_progress
        assert_eq(milestone_status(g, "m-0"), "in_progress", "T8 milestone reopened")
        # review_retry_count incremented
        assert_eq(g["milestones"][0]["review_retry_count"], 1, "T8 retry_count=1")
    finally:
        os.chdir(cwd_backup)
        shutil.rmtree(home, ignore_errors=True)


# ---------------------------------------------------------------------------
# T9: review_retry exhausted -> escalated
# ---------------------------------------------------------------------------
def test_t9_review_retry_exhausted():
    print("T9: review_retry exhausted -> escalated")
    home, gid, cwd_backup = setup_repo()
    try:
        env = os.environ.copy()
        env["JCODE_GOAL_HOME"] = str(home)
        # max_retries=2 -> escalate after 2 findings
        run([str(GOAL), "milestone", gid, "add", "M0",
             "--review-max-retries", "2"], env=env)
        run([str(GOAL), "step", gid, "m-0", "add", "step-A",
             "--verify", "true"], env=env)

        findings = ('{"verdict":"findings","findings":'
                    '[{"step_id":"m-0-step-0","severity":"major","issue":"first"}],'
                    '"confidence":0.8}')

        # Cycle 1: spawn_coder (default clean = fine)
        orchestrate(home)
        # Cycle 2: step_done, milestone pending -> in_progress
        orchestrate(home)
        # Cycle 3: spawn_reviewer
        orchestrate(home)
        # Cycle 4: reviewer returns findings -> retry_count=1, step reset
        orchestrate(home, findings)
        # Cycle 5: spawn_coder (step was reset to pending)
        orchestrate(home)
        # Cycle 6: step_done, spawn_reviewer again
        orchestrate(home)
        # Cycle 7: reviewer findings -> retry_count=2 (= max) -> escalate
        orchestrate(home, findings)

        g = get_goal(home, gid)
        assert_eq(milestone_status(g, "m-0"), "escalated", "T9 milestone escalated")
        assert_eq(g["milestones"][0]["review_retry_count"], 2, "T9 retry_count=2 (==max)")
    finally:
        os.chdir(cwd_backup)
        shutil.rmtree(home, ignore_errors=True)


# ---------------------------------------------------------------------------
# T10: reviewer crashed -> handled as findings (no-confidence)
# ---------------------------------------------------------------------------
def test_t10_reviewer_crashed():
    print("T10: reviewer crashed -> fallback to findings")
    home, gid, cwd_backup = setup_repo()
    try:
        env = os.environ.copy()
        env["JCODE_GOAL_HOME"] = str(home)
        run([str(GOAL), "milestone", gid, "add", "M0"], env=env)
        run([str(GOAL), "step", gid, "m-0", "add", "step-A",
             "--verify", "true"], env=env)

        # Cycle 1: spawn_coder
        orchestrate(home)
        # Cycle 2: step_done, milestone_in_progress
        orchestrate(home)
        # Cycle 3: spawn_reviewer
        orchestrate(home)
        # Cycle 4: reviewer parse-fail (empty report) -> findings, retry_count=1
        out = orchestrate(home, "")

        g = get_goal(home, gid)
        assert_in("review_failed", out, "T10 review_failed action")
        # review_retry_count incremented; not yet escalated (default max=3)
        assert_eq(g["milestones"][0]["review_retry_count"], 1, "T10 retry_count=1 on parse fail")
    finally:
        os.chdir(cwd_backup)
        shutil.rmtree(home, ignore_errors=True)


# ---------------------------------------------------------------------------
# T11: coder_session_id != reviewer_session_id
# ---------------------------------------------------------------------------
def test_t11_coder_reviewer_different_ids():
    print("T11: coder_session_id != reviewer_session_id")
    home, gid, cwd_backup = setup_repo()
    try:
        env = os.environ.copy()
        env["JCODE_GOAL_HOME"] = str(home)
        run([str(GOAL), "milestone", gid, "add", "M0"], env=env)
        run([str(GOAL), "step", gid, "m-0", "add", "step-A",
             "--verify", "true"], env=env)

        # Cycle 1: spawn_coder
        orchestrate(home)
        # Cycle 2: step_done, milestone_in_progress
        orchestrate(home)
        # Cycle 3: spawn_reviewer
        orchestrate(home)

        g = get_goal(home, gid)
        m = g["milestones"][0]
        # step coder_session_id starts with DRYRUN-
        # milestone reviewer_session_id starts with DRYRUN-
        coder_ids = {s.get("coder_session_id") for s in m["steps"] if s.get("coder_session_id")}
        reviewer_id = m.get("reviewer_session_id")
        assert_eq(len(coder_ids), 1, "T11 one coder session")
        assert reviewer_id is not None, "T11 reviewer_id set"
        assert coder_ids != {reviewer_id}, "T11 coder_id != reviewer_id"
        # labels also distinct
        coder_labels = {s.get("coder_label") for s in m["steps"] if s.get("coder_label")}
        reviewer_label = m.get("reviewer_label")
        assert "coder" in list(coder_labels)[0], "T11 coder label"
        assert "reviewer" in reviewer_label, "T11 reviewer label"
        assert_eq(coder_labels & {reviewer_label}, set(), "T11 labels disjoint")
    finally:
        os.chdir(cwd_backup)
        shutil.rmtree(home, ignore_errors=True)


# ---------------------------------------------------------------------------
# T12: --no-review bypass
# ---------------------------------------------------------------------------
def test_t12_no_review_bypass():
    print("T12: --no-review bypasses reviewer spawn")
    home, gid, cwd_backup = setup_repo()
    try:
        env = os.environ.copy()
        env["JCODE_GOAL_HOME"] = str(home)
        run([str(GOAL), "milestone", gid, "add", "M0", "--no-review"], env=env)
        run([str(GOAL), "step", gid, "m-0", "add", "step-A",
             "--verify", "true"], env=env)

        cycles = cycle_until(home, gid, 10)
        g = get_goal(home, gid)
        m = g["milestones"][0]
        assert_eq(m["status"], "completed", "T12 milestone completed (no reviewer)")
        assert_eq(m.get("reviewer_session_id"), None, "T12 reviewer never spawned")
        assert_eq(m.get("review_verdict"), None, "T12 no verdict")
        assert_eq(g["status"], "complete", "T12 goal complete")
        # Cycles should be fewer (no reviewer step)
        assert cycles <= 4, f"T12 cycle count ({cycles}) should be <= 4"
    finally:
        os.chdir(cwd_backup)
        shutil.rmtree(home, ignore_errors=True)


# ---------------------------------------------------------------------------
# T13: queue auto-promote — completing the active goal shifts pending -> active
# ---------------------------------------------------------------------------
def test_t13_queue_auto_promote():
    print("T13: queue auto-promote on goal_completed")
    home, active_gid, pending_gid, cwd_backup = setup_repo_with_pending()
    try:
        env = os.environ.copy()
        env["JCODE_GOAL_HOME"] = str(home)
        # Minimal scaffold: 1 milestone with 1 step on the active goal so it
        # can complete quickly. (Pending goal stays empty; we just verify it
        # becomes active when active goal completes.)
        run([str(GOAL), "milestone", active_gid, "add", "M0", "--no-review"], env=env)
        run([str(GOAL), "step", active_gid, "m-0", "add", "only-step",
             "--verify", "true"], env=env)

        # Drive the active goal to completion.
        cycles = cycle_until(home, active_gid, 8)
        assert cycles <= 4, f"T13 active goal cycles ({cycles})"

        # After the active goal completed, the pending goal should have been
        # auto-promoted to active.
        pending_now = get_goal(home, pending_gid)
        active_now = get_goal(home, active_gid)
        assert_eq(active_now["status"], "complete", "T13 active goal marked complete")
        assert_eq(pending_now["status"], "active", "T13 pending goal auto-promoted to active")

        # Run one more cycle to confirm the orchestrator now drives the
        # promoted goal. The promoted goal has no milestones, so the cycle
        # prints "(no actions this cycle)" — but it must NOT print
        # "no active goals", which would mean the auto-promote failed.
        out = orchestrate(home)
        assert "no active goals" not in out, \
            f"T13 orchestrator should see promoted goal; got: {out[:200]}"
    finally:
        os.chdir(cwd_backup)
        shutil.rmtree(home, ignore_errors=True)


def setup_repo_with_pending() -> tuple[Path, str, str, str]:
    """Like setup_repo but also seeds a second pending goal.

    Returns (home, active_gid, pending_gid, cwd_backup).
    """
    home, active_gid, cwd_backup = setup_repo()
    env = os.environ.copy()
    env["JCODE_GOAL_HOME"] = str(home)
    # Add a second goal: since queue already has an active goal, this one
    # enters as pending (per new queue-aware add semantics).
    out = run([str(GOAL), "add", "Pending", "--priority", "high",
               "--content", "queued behind active",
               "--scope", "project", "--cwd", str(home)], env=env)
    assert out.returncode == 0, out.stderr
    # list --json is sorted by filename (goal-<ts>-<4hex>) which is not
    # chronological when both goals share the same unix second. Sort by
    # created_at and find the one that is NOT active (the pending one).
    data = json.loads(run([str(GOAL), "list", "--json"], env=env).stdout)
    data.sort(key=lambda g: g.get("created_at", ""))
    pending_gid = next(g["id"] for g in data if g.get("status") == "pending")
    assert pending_gid, "T13 setup: no pending goal found"
    assert_eq(next(g for g in data if g["id"] == pending_gid)["status"],
              "pending", "T13 setup: new goal starts as pending")
    return home, active_gid, pending_gid, cwd_backup


def main() -> int:
    for t in [test_t7_happy_review, test_t8_findings_precise_reset,
              test_t9_review_retry_exhausted, test_t10_reviewer_crashed,
              test_t11_coder_reviewer_different_ids, test_t12_no_review_bypass,
              test_t13_queue_auto_promote]:
        try:
            t()
        except AssertionError as e:
            global FAIL
            FAIL += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            FAIL += 1
            print(f"  ERROR {t.__name__}: {e}")
    print()
    print(f"{'PASS' if FAIL == 0 else 'FAIL'}: {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())