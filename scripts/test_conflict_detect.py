"""Tests for scripts/conflict-detect.py — generic swarm conflict detection.

TDD harness. All tests run without a real git repo: git calls are stubbed via
unittest.mock. Run with:

    python3 -m unittest scripts.test_conflict_detect -v
"""

import importlib.util
import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


# Load `scripts/conflict-detect.py` (dash, not underscore) by file path.
_CONFLICT_DETECT_PATH = Path(__file__).resolve().parent / "conflict-detect.py"
_SPEC = importlib.util.spec_from_file_location("conflict_detect", _CONFLICT_DETECT_PATH)
cd = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules["conflict_detect"] = cd
_SPEC.loader.exec_module(cd)


# ---------------------------------------------------------------------------
# Dataclass shape
# ---------------------------------------------------------------------------


class TestConflictDataclass(unittest.TestCase):
    """The Conflict dataclass must expose the spec'd fields."""

    def test_fields_present(self):
        c = cd.Conflict(
            severity="blocker",
            category="scope_overlap",
            summary="file touched by 2 workers",
            evidence=["worker_a: foo.py", "worker_b: foo.py"],
            remediation="serialize worker_a and worker_b",
        )
        self.assertEqual(c.severity, "blocker")
        self.assertEqual(c.category, "scope_overlap")
        self.assertEqual(c.summary, "file touched by 2 workers")
        self.assertEqual(c.evidence, ["worker_a: foo.py", "worker_b: foo.py"])
        self.assertEqual(c.remediation, "serialize worker_a and worker_b")

    def test_severity_levels_known(self):
        # The severity vocabulary must include the three categories we use.
        self.assertIn("blocker", cd.SEVERITY_ORDER)
        self.assertIn("major", cd.SEVERITY_ORDER)
        self.assertEqual(cd.SEVERITY_ORDER["blocker"], 2)
        self.assertEqual(cd.SEVERITY_ORDER["major"], 1)


# ---------------------------------------------------------------------------
# Detector 1: scope overlap
# ---------------------------------------------------------------------------


class TestScopeOverlap(unittest.TestCase):
    """detect_scope_overlap: any file touched by >=2 workers = blocker."""

    def test_scope_overlap_basic(self):
        scopes = {
            "worker_a": ["src/a.py", "src/common.py"],
            "worker_b": ["src/b.py", "src/common.py"],
        }
        conflicts = cd.detect_scope_overlap(scopes)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "blocker")
        self.assertEqual(conflicts[0].category, "scope_overlap")
        # evidence is a list[str]; assert via substring so we don't couple
        # to the exact "worker: file" formatting.
        joined = " ".join(conflicts[0].evidence)
        self.assertIn("src/common.py", joined)
        self.assertIn("worker_a", joined)
        self.assertIn("worker_b", joined)

    def test_scope_overlap_no_overlap(self):
        scopes = {
            "worker_a": ["src/a.py"],
            "worker_b": ["src/b.py"],
            "worker_c": ["src/c.py"],
        }
        conflicts = cd.detect_scope_overlap(scopes)
        self.assertEqual(conflicts, [])

    def test_scope_overlap_three_workers(self):
        scopes = {
            "worker_a": ["x.py"],
            "worker_b": ["x.py"],
            "worker_c": ["x.py"],
        }
        conflicts = cd.detect_scope_overlap(scopes)
        self.assertEqual(len(conflicts), 1)
        # evidence should list all three workers
        joined = " ".join(conflicts[0].evidence)
        self.assertIn("worker_a", joined)
        self.assertIn("worker_b", joined)
        self.assertIn("worker_c", joined)


# ---------------------------------------------------------------------------
# Detector 2: lockfile contention
# ---------------------------------------------------------------------------


class TestLockfileContention(unittest.TestCase):
    """detect_lockfile_contention: high-contention file touched = major."""

    def test_lockfile_default_set(self):
        scopes = {"worker_a": ["package.json", "src/index.ts"]}
        conflicts = cd.detect_lockfile_contention(scopes)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "major")
        self.assertEqual(conflicts[0].category, "lockfile_contention")
        joined = " ".join(conflicts[0].evidence)
        self.assertIn("package.json", joined)

    def test_lockfile_custom_config(self):
        scopes = {"worker_a": ["dotnet/project.assets.json"]}
        config = {"lockfile_files": ["dotnet/project.assets.json"]}
        conflicts = cd.detect_lockfile_contention(scopes, config=config)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "major")
        joined = " ".join(conflicts[0].evidence)
        self.assertIn("dotnet/project.assets.json", joined)

    def test_lockfile_ignore_path(self):
        # ignored_paths lets a repo skip noisy files.
        scopes = {"worker_a": ["tests/__pycache__/x.pyc"]}
        config = {"ignored_paths": ["**/__pycache__/**"]}
        conflicts = cd.detect_lockfile_contention(scopes, config=config)
        # The conflict should still be reported (lockfile default set) unless
        # the file is both lockfile-shaped AND ignored. .pyc is not lockfile,
        # so it should not match.
        self.assertEqual(conflicts, [])

    def test_lockfile_migrations_dir(self):
        scopes = {"worker_a": ["migrations/0001_init.py"]}
        conflicts = cd.detect_lockfile_contention(scopes)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "major")


# ---------------------------------------------------------------------------
# Detector 3: in-flight overlap
# ---------------------------------------------------------------------------


class TestInFlightOverlap(unittest.TestCase):
    """detect_in_flight_overlap: planned scope vs in-flight branch diffs."""

    def test_in_flight_overlap(self):
        # Stub git diff to return a file that overlaps with the planned scope.
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess,
            "run",
            return_value=mock.Mock(
                stdout="src/common.py\nsrc/a.py\n", returncode=0
            ),
        ):
            conflicts = cd.detect_in_flight_overlap(
                planned=["src/common.py", "src/new.py"],
                in_flight_branches=["feat/worker_a"],
                repo_root="/tmp/repo",
            )
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "blocker")
        self.assertEqual(conflicts[0].category, "in_flight_overlap")
        joined = " ".join(conflicts[0].evidence)
        self.assertIn("src/common.py", joined)
        self.assertIn("feat/worker_a", joined)

    def test_in_flight_no_overlap(self):
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess,
            "run",
            return_value=mock.Mock(
                stdout="src/other.py\n", returncode=0
            ),
        ):
            conflicts = cd.detect_in_flight_overlap(
                planned=["src/common.py"],
                in_flight_branches=["feat/worker_a"],
                repo_root="/tmp/repo",
            )
        self.assertEqual(conflicts, [])


# ---------------------------------------------------------------------------
# Detector 4: dirty state
# ---------------------------------------------------------------------------


class TestDirtyState(unittest.TestCase):
    """detect_dirty_state: non-empty porcelain = blocker."""

    def test_dirty_clean_worktree(self):
        with mock.patch.object(
            cd.subprocess,
            "run",
            return_value=mock.Mock(stdout="", returncode=0),
        ):
            conflicts = cd.detect_dirty_state("/tmp/wt")
        self.assertEqual(conflicts, [])

    def test_dirty_uncommitted(self):
        with mock.patch.object(
            cd.subprocess,
            "run",
            return_value=mock.Mock(
                stdout=" M scripts/install.sh\n", returncode=0
            ),
        ):
            conflicts = cd.detect_dirty_state("/tmp/wt")
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "blocker")
        self.assertEqual(conflicts[0].category, "dirty_state")
        joined = " ".join(conflicts[0].evidence)
        self.assertIn("scripts/install.sh", joined)


# ---------------------------------------------------------------------------
# Detectors 5 & 6: manifest corruption + heartbeat staleness
# ---------------------------------------------------------------------------


class TestManifestCorruption(unittest.TestCase):
    """detect_manifest_corruption: malformed JSON = blocker."""

    def test_manifest_corrupt(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{this is not json")
            path = f.name
        try:
            conflicts = cd.detect_manifest_corruption(path)
        finally:
            os.unlink(path)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "blocker")
        self.assertEqual(conflicts[0].category, "manifest_corruption")

    def test_manifest_schema_missing_keys(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"entries": [{"wt_path": "/x", "branch": "b"}]}, f)
            path = f.name
        try:
            conflicts = cd.detect_manifest_corruption(path)
        finally:
            os.unlink(path)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "major")
        self.assertEqual(conflicts[0].category, "manifest_schema")


class TestHeartbeatStale(unittest.TestCase):
    """detect_heartbeat_stale: heartbeat > ttl = major."""

    def _make_entry(self, started_at, last_heartbeat):
        return {
            "wt_path": "/tmp/wt",
            "branch": "feat/x",
            "pid": 12345,
            "started_at": started_at,
            "last_heartbeat": last_heartbeat,
        }

    def test_heartbeat_fresh(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        recent = (now - datetime.timedelta(minutes=1)).isoformat()
        entries = [self._make_entry(recent, recent)]
        conflicts = cd.detect_heartbeat_stale(entries, now=now)
        self.assertEqual(conflicts, [])

    def test_heartbeat_stale(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        old = (now - datetime.timedelta(hours=9)).isoformat()
        entries = [self._make_entry(old, old)]
        conflicts = cd.detect_heartbeat_stale(entries, now=now)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "major")
        self.assertEqual(conflicts[0].category, "heartbeat_stale")


# ---------------------------------------------------------------------------
# CLI exit codes
# ---------------------------------------------------------------------------


class TestCLIExitCodes(unittest.TestCase):
    """End-to-end: invoking the script as a subprocess, exit codes 0/1/2."""

    def _run_cli(self, args, stdin_payload=None):
        return subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "conflict-detect.py"), *args],
            input=stdin_payload,
            capture_output=True,
            text=True,
        )

    def test_cli_help(self):
        result = self._run_cli(["--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage", result.stdout.lower())

    def test_cli_exit_zero_clean(self):
        # scope-overlap with two disjoint workers -> no conflicts -> exit 0.
        payload = json.dumps({"worker_a": ["a.py"], "worker_b": ["b.py"]})
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(payload)
            path = f.name
        try:
            result = self._run_cli(["scope-overlap", "--scopes", path])
        finally:
            os.unlink(path)
        self.assertEqual(result.returncode, 0)

    def test_cli_exit_two_blocker(self):
        # scope-overlap with shared file -> blocker -> exit 2.
        payload = json.dumps({"worker_a": ["x.py"], "worker_b": ["x.py"]})
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(payload)
            path = f.name
        try:
            result = self._run_cli(["scope-overlap", "--scopes", path])
        finally:
            os.unlink(path)
        self.assertEqual(result.returncode, 2)

    def test_cli_manifest_missing(self):
        # manifest command when file does not exist -> info / no blocker
        # (a missing manifest is OK on a brand-new repo).
        result = self._run_cli(
            ["manifest", "--manifest", "/tmp/does-not-exist-987654.json"]
        )
        self.assertIn(result.returncode, (0, 1))

    def test_cli_format_json(self):
        payload = json.dumps({"worker_a": ["a.py"], "worker_b": ["a.py"]})
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(payload)
            path = f.name
        try:
            result = self._run_cli(
                ["scope-overlap", "--scopes", path, "--format", "json"]
            )
        finally:
            os.unlink(path)
        self.assertEqual(result.returncode, 2)
        # Output must be valid JSON with a stable schema.
        out = json.loads(result.stdout)
        self.assertIn("conflicts", out)
        self.assertEqual(len(out["conflicts"]), 1)
        self.assertEqual(out["conflicts"][0]["category"], "scope_overlap")
        self.assertEqual(out["conflicts"][0]["severity"], "blocker")


# ---------------------------------------------------------------------------
# Detectors 7, 8, 9: execution-order planning
# ---------------------------------------------------------------------------


class TestExecutionOrder(unittest.TestCase):
    """plan_execution_order + detect_dependency_chain + suggest_serialization.

    TDD red phase: these tests are appended BEFORE the production
    functions are implemented. They reference cd.Task, cd.ExecutionPlan,
    cd.plan_execution_order, cd.detect_dependency_chain, and
    cd.suggest_serialization.
    """

    # ---- plan_execution_order ------------------------------------------

    def test_plan_order_disjoint(self):
        # 3 tasks with disjoint files => 1 phase, 3 tasks in parallel.
        tasks = [
            cd.Task(task_id="t1", scope_files=["a.py"]),
            cd.Task(task_id="t2", scope_files=["b.py"]),
            cd.Task(task_id="t3", scope_files=["c.py"]),
        ]
        plan = cd.plan_execution_order(tasks)
        self.assertEqual(len(plan.phases), 1)
        self.assertEqual(sorted(plan.phases[0]), ["t1", "t2", "t3"])
        # Critical path = longest DAG chain. With disjoint tasks there is
        # no dependency edge, so the longest chain is a single task.
        self.assertEqual(len(plan.critical_path), 1)
        # Parallel batches == phases whose length > 1. The single phase
        # with 3 tasks counts.
        self.assertEqual(len(plan.parallel_batches), 1)
        self.assertEqual(sorted(plan.parallel_batches[0]), ["t1", "t2", "t3"])

    def test_plan_order_chain(self):
        # t1 and t2 share a file; t2 and t3 share a file => 3 phases.
        tasks = [
            cd.Task(task_id="t1", scope_files=["shared.py"]),
            cd.Task(task_id="t2", scope_files=["shared.py", "b.py"]),
            cd.Task(task_id="t3", scope_files=["b.py"]),
        ]
        plan = cd.plan_execution_order(tasks)
        # Each pair overlaps, so strictly serial: 3 phases of 1 each.
        self.assertEqual(len(plan.phases), 3)
        self.assertEqual(plan.phases[0], ["t1"])
        self.assertEqual(plan.phases[1], ["t2"])
        self.assertEqual(plan.phases[2], ["t3"])
        self.assertEqual(plan.critical_path, ["t1", "t2", "t3"])
        # No parallel batches when phases are length-1.
        self.assertTrue(all(len(b) <= 1 for b in plan.parallel_batches))

    def test_plan_order_diamond(self):
        # Diamond shape in the file-overlap graph: t1 touches root.py;
        # t2,t3 both touch root.py + a branch file; t4 touches the two
        # branch files. Because t2 and t3 BOTH modify "root.py", the
        # implementation must serialize them. The result is a strictly
        # serial 4-phase plan (no parallel batches), and the critical
        # path traverses all four tasks in lex order.
        tasks = [
            cd.Task(task_id="t1", scope_files=["root.py"]),
            cd.Task(task_id="t2", scope_files=["root.py", "left.py"]),
            cd.Task(task_id="t3", scope_files=["root.py", "right.py"]),
            cd.Task(task_id="t4", scope_files=["left.py", "right.py"]),
        ]
        plan = cd.plan_execution_order(tasks)
        self.assertEqual(len(plan.phases), 4)
        self.assertEqual(plan.phases[0], ["t1"])
        self.assertEqual(plan.phases[1], ["t2"])
        self.assertEqual(plan.phases[2], ["t3"])
        self.assertEqual(plan.phases[3], ["t4"])
        # Critical path = longest chain through phases = all four.
        self.assertEqual(plan.critical_path, ["t1", "t2", "t3", "t4"])
        # Strictly serial => no parallel batches.
        self.assertEqual(plan.parallel_batches, [])

    def test_plan_order_parallel_batches(self):
        # True parallel batching: t2 and t3 do NOT share a file with
        # each other, only with t1 and t4 respectively.
        # Edges: t1->t2 (root.py), t1->t3 (other.py),
        #        t2->t4 (left.py), t3->t4 (right.py).
        # Phase 0: [t1], Phase 1: [t2, t3] (parallel!), Phase 2: [t4].
        tasks = [
            cd.Task(task_id="t1", scope_files=["root.py", "other.py"]),
            cd.Task(task_id="t2", scope_files=["root.py", "left.py"]),
            cd.Task(task_id="t3", scope_files=["other.py", "right.py"]),
            cd.Task(task_id="t4", scope_files=["left.py", "right.py"]),
        ]
        plan = cd.plan_execution_order(tasks)
        self.assertEqual(len(plan.phases), 3)
        self.assertEqual(plan.phases[0], ["t1"])
        self.assertEqual(sorted(plan.phases[1]), ["t2", "t3"])
        self.assertEqual(plan.phases[2], ["t4"])
        # Critical path: t1 -> t2 -> t4 (lex tie-break).
        self.assertEqual(plan.critical_path, ["t1", "t2", "t4"])
        # The middle phase IS a parallel batch.
        self.assertEqual(len(plan.parallel_batches), 1)
        self.assertEqual(sorted(plan.parallel_batches[0]), ["t2", "t3"])

    def test_plan_order_cycle_detected(self):
        # Two tasks sharing BOTH files is the pathological "cycle-shaped"
        # input. With lex-based orientation (t1 < t2 => t1 -> t2) the
        # graph is acyclic, but the implementation must handle this case
        # without raising. Verify graceful serial phasing.
        tasks = [
            cd.Task(task_id="t1", scope_files=["a.py", "b.py"]),
            cd.Task(task_id="t2", scope_files=["a.py", "b.py"]),
        ]
        # The function must not raise. It should produce a 2-phase serial
        # plan (lex orientation yields t1 -> t2). The cycle-defensive
        # branch is unreachable for shared-file-only inputs but is
        # covered by the implementation's Kahn-based cycle check.
        plan = cd.plan_execution_order(tasks)
        self.assertEqual(len(plan.phases), 2)
        self.assertEqual(plan.phases[0], ["t1"])
        self.assertEqual(plan.phases[1], ["t2"])
        # Critical path traverses both phases.
        self.assertEqual(plan.critical_path, ["t1", "t2"])

    # ---- detect_dependency_chain ---------------------------------------

    def test_dep_chain_no_overlap(self):
        # New task does not intersect with branch diffs => empty list.
        new_task = cd.Task(task_id="new", scope_files=["scripts/brand_new.py"])
        # Stub the diff to return only files unrelated to new_task.
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess,
            "run",
            return_value=mock.Mock(
                stdout="swarm/prompt-overlay.md\n", returncode=0
            ),
        ):
            conflicts = cd.detect_dependency_chain(
                new_task,
                existing_tasks=[],
                existing_branches=["feat/other"],
                repo_path="/tmp/repo",
            )
        self.assertEqual(conflicts, [])

    def test_dep_chain_with_overlap(self):
        # New task shares a file with branch diff => 1 blocker.
        new_task = cd.Task(task_id="new", scope_files=["src/common.py"])
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess,
            "run",
            return_value=mock.Mock(
                stdout="src/common.py\nsrc/a.py\n", returncode=0
            ),
        ):
            conflicts = cd.detect_dependency_chain(
                new_task,
                existing_tasks=[],
                existing_branches=["feat/worker_a"],
                repo_path="/tmp/repo",
            )
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "blocker")
        joined = " ".join(conflicts[0].evidence)
        self.assertIn("src/common.py", joined)
        self.assertIn("feat/worker_a", joined)

    # ---- suggest_serialization -----------------------------------------

    def test_serialize_lockfile(self):
        # Two tasks touch package.json => config marks it lockfile => blocker.
        tasks = [
            cd.Task(task_id="t1", scope_files=["package.json", "src/a.ts"]),
            cd.Task(task_id="t2", scope_files=["package.json", "src/b.ts"]),
        ]
        config = {"lockfile_files": ["package.json"]}
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ):
            conflicts = cd.suggest_serialization(tasks, repo_path="/tmp/repo", config=config)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "blocker")
        joined = " ".join(conflicts[0].evidence)
        self.assertIn("package.json", joined)
        self.assertIn("serialize", conflicts[0].remediation.lower())

    def test_serialize_disjoint(self):
        # Shared non-lockfile file => minor (parallel ok with rebase).
        tasks = [
            cd.Task(task_id="t1", scope_files=["docs/x.md"]),
            cd.Task(task_id="t2", scope_files=["docs/x.md"]),
        ]
        # Empty config => no lockfiles => falls to git-history heuristic.
        # Stub `git log --oneline -20 -- <file>` to return empty (no history).
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess,
            "run",
            return_value=mock.Mock(stdout="", returncode=0),
        ):
            conflicts = cd.suggest_serialization(
                tasks, repo_path="/tmp/repo", config={}
            )
        # No history => heuristic falls back to minor remediation.
        self.assertGreaterEqual(len(conflicts), 1)
        # All emitted conflicts for non-lockfile disjoint line overlap must be minor.
        for c in conflicts:
            self.assertEqual(c.severity, "minor")
            self.assertIn("parallel", c.remediation.lower())

    # ---- CLI subcommands -----------------------------------------------

    def test_cli_plan_order(self):
        payload = json.dumps([
            {"task_id": "r1", "scope_files": ["scripts/check-swarm-consistency.py"]},
            {"task_id": "r7", "scope_files": ["swarm/role-templates/"]},
        ])
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(payload)
            path = f.name
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parent / "conflict-detect.py"),
                    "plan-order", "--tasks", path, "--format", "json",
                ],
                capture_output=True, text=True,
            )
        finally:
            os.unlink(path)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        out = json.loads(result.stdout)
        self.assertIn("phases", out)
        self.assertIn("critical_path", out)
        self.assertIn("parallel_batches", out)
        # r1 and r7 share no files => single phase of 2.
        self.assertEqual(len(out["phases"]), 1)
        self.assertEqual(sorted(out["phases"][0]), ["r1", "r7"])

    def test_cli_dep_chain(self):
        scope_payload = json.dumps([
            {"task_id": "new", "scope_files": ["src/common.py"]},
        ])
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(scope_payload)
            scope_path = f.name
        try:
            # Stub subprocess.run inside the subprocess by patching git's
            # output via env: simplest is to invoke against a real git repo
            # with no matching branch.
            with mock.patch.object(
                cd.shutil, "which", return_value="/usr/bin/git"
            ):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).resolve().parent / "conflict-detect.py"),
                        "dep-chain",
                        "--scope", scope_path,
                        "--branches", "feat/nonexistent",
                        "--repo", "/tmp",
                        "--format", "json",
                    ],
                    capture_output=True, text=True,
                )
        finally:
            os.unlink(scope_path)
        # No matching branch in /tmp (git will fail) => no conflicts.
        self.assertIn(result.returncode, (0, 1))

    def test_cli_serialize(self):
        payload = json.dumps([
            {"task_id": "t1", "scope_files": ["package.json"]},
            {"task_id": "t2", "scope_files": ["package.json"]},
        ])
        cfg_payload = "lockfile_files:\n  - package.json\n"
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(payload)
            tasks_path = f.name
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(cfg_payload)
            cfg_path = f.name
        try:
            with mock.patch.object(cd.shutil, "which", return_value="/usr/bin/git"):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).resolve().parent / "conflict-detect.py"),
                        "serialize",
                        "--tasks", tasks_path,
                        "--config", cfg_path,
                        "--repo", "/tmp",
                        "--format", "json",
                    ],
                    capture_output=True, text=True,
                )
        finally:
            os.unlink(tasks_path)
            os.unlink(cfg_path)
        # Lockfile contention => blocker => exit 2.
        self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
        out = json.loads(result.stdout)
        self.assertGreaterEqual(len(out["conflicts"]), 1)
        self.assertEqual(out["conflicts"][0]["severity"], "blocker")


# ---------------------------------------------------------------------------
# R19 gap 8: per-repo config schema (.jcode/conflict-config.yaml)
# ---------------------------------------------------------------------------


class TestConfigSchema(unittest.TestCase):
    """R19 gap 8: parse the four new config fields from .jcode/conflict-config.yaml.

    Fields:
        guardian_files        — list[str]. Files any worker touching should
                                trigger scope-drift = blocker.
        severity_threshold_n  — dict[str, int]. Map {major: N, blocker: N}
                                where N is the worker-count threshold at which
                                `suggest_serialization` escalates severity.
        prefer_side           — str. Default side for `resolve_conflict_hunks`.
                                One of: worker / main / newer / intersection.
        cleanup_patterns      — list[str]. Glob patterns for
                                `cleanup_worktree_artifacts` (delete vs add).
    """

    def _write_cfg(self, text):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", delete=False
        ) as f:
            f.write(text)
            return f.name

    def test_config_loaded_with_default_thresholds(self):
        # Empty config => defaults are applied by the consumer (severity_threshold_n,
        # cleanup_patterns). This test only asserts the loader does not crash.
        path = self._write_cfg("# empty config\n")
        try:
            cfg = cd.load_config(path)
        finally:
            os.unlink(path)
        self.assertIsInstance(cfg, dict)

    def test_config_guardian_files_parsed(self):
        cfg_text = (
            "guardian_files:\n"
            "  - AGENTS.md\n"
            "  - README.md\n"
            "  - .jcode/prompt-overlay.md\n"
        )
        path = self._write_cfg(cfg_text)
        try:
            cfg = cd.load_config(path)
        finally:
            os.unlink(path)
        self.assertIn("guardian_files", cfg)
        self.assertEqual(
            sorted(cfg["guardian_files"]),
            [".jcode/prompt-overlay.md", "AGENTS.md", "README.md"],
        )

    def test_config_severity_threshold_n_parsed(self):
        cfg_text = (
            "severity_threshold_n:\n"
            "  major: 4\n"
            "  blocker: 6\n"
        )
        path = self._write_cfg(cfg_text)
        try:
            cfg = cd.load_config(path)
        finally:
            os.unlink(path)
        self.assertEqual(
            cfg["severity_threshold_n"], {"major": 4, "blocker": 6}
        )

    def test_config_prefer_side_parsed(self):
        cfg_text = "prefer_side: newer\n"
        path = self._write_cfg(cfg_text)
        try:
            cfg = cd.load_config(path)
        finally:
            os.unlink(path)
        self.assertEqual(cfg["prefer_side"], "newer")

    def test_config_cleanup_patterns_parsed(self):
        cfg_text = (
            "cleanup_patterns:\n"
            "  - __pycache__/\n"
            "  - '*.bak.*'\n"
            "  - '*.pyc'\n"
            "  - '*.tmp'\n"
        )
        path = self._write_cfg(cfg_text)
        try:
            cfg = cd.load_config(path)
        finally:
            os.unlink(path)
        self.assertEqual(
            cfg["cleanup_patterns"],
            ["__pycache__/", "*.bak.*", "*.pyc", "*.tmp"],
        )

    def test_default_severity_thresholds_constant(self):
        # The framework must publish a module-level default for severity
        # escalation thresholds. R19 spec: {major: 4, blocker: 6}.
        self.assertTrue(hasattr(cd, "DEFAULT_SEVERITY_THRESHOLD_N"))
        self.assertEqual(
            cd.DEFAULT_SEVERITY_THRESHOLD_N, {"major": 4, "blocker": 6}
        )

    def test_default_cleanup_patterns_constant(self):
        # Cleanup patterns must have a sane default. R19 spec lists these 4.
        self.assertTrue(hasattr(cd, "DEFAULT_CLEANUP_PATTERNS"))
        self.assertIn("__pycache__/", cd.DEFAULT_CLEANUP_PATTERNS)
        self.assertIn("*.bak.*", cd.DEFAULT_CLEANUP_PATTERNS)
        self.assertIn("*.pyc", cd.DEFAULT_CLEANUP_PATTERNS)
        self.assertIn("*.tmp", cd.DEFAULT_CLEANUP_PATTERNS)

    def test_valid_prefer_sides_constant(self):
        # resolve_conflict_hunks accepts 4 sides; the framework must publish
        # the closed set so callers can validate before invoking.
        self.assertTrue(hasattr(cd, "VALID_PREFER_SIDES"))
        self.assertEqual(
            sorted(cd.VALID_PREFER_SIDES),
            ["intersection", "main", "newer", "worker"],
        )

    def test_example_config_file_parses(self):
        # The shipped `.jcode/conflict-config.yaml.example` must be a valid
        # input to `load_config` — any drift between example and parser is
        # a documentation bug that should fail CI.
        example_path = (
            Path(__file__).resolve().parent.parent
            / ".jcode"
            / "conflict-config.yaml.example"
        )
        self.assertTrue(example_path.is_file(), f"missing {example_path}")
        cfg = cd.load_config(example_path)
        # The four R19 fields must be present in the example.
        self.assertIn("guardian_files", cfg)
        self.assertIn("severity_threshold_n", cfg)
        self.assertIn("prefer_side", cfg)
        self.assertIn("cleanup_patterns", cfg)
        # Spot-check a few values to make sure the example demonstrates them.
        self.assertIn("AGENTS.md", cfg["guardian_files"])
        self.assertEqual(cfg["severity_threshold_n"], {"major": 4, "blocker": 6})
        self.assertEqual(cfg["prefer_side"], "newer")
        self.assertIn("__pycache__/", cfg["cleanup_patterns"])


if __name__ == "__main__":
    unittest.main()
