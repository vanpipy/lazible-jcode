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


# ---------------------------------------------------------------------------
# R19 gap 3: severity_threshold_n escalation in suggest_serialization
# ---------------------------------------------------------------------------


class TestSerializationThresholds(unittest.TestCase):
    """R19 gap 3: non-lockfile overlap escalates by worker count.

    N = number of unique workers sharing the file.
        N <  major_threshold   -> minor  (parallel ok with rebase)
        major_threshold <= N   -> major  (serialize recommended)
        N >= blocker_threshold -> blocker (force serialize, refuse merge)
    """

    def _make_tasks(self, n_tasks: int, path: str):
        return [
            cd.Task(task_id=f"t{i}", scope_files=[path, f"src/unique_{i}.py"])
            for i in range(n_tasks)
        ]

    def test_two_workers_below_major_threshold(self):
        # 2 workers sharing a doc -> minor (default major threshold is 4).
        tasks = self._make_tasks(2, "docs/x.md")
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run", return_value=mock.Mock(stdout="", returncode=0)
        ):
            conflicts = cd.suggest_serialization(
                tasks, repo_path="/tmp/repo", config={}
            )
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "minor")

    def test_four_workers_hit_major_threshold(self):
        # 4 workers sharing a doc -> major (default major threshold is 4).
        tasks = self._make_tasks(4, "AGENTS.md")
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run", return_value=mock.Mock(stdout="", returncode=0)
        ):
            conflicts = cd.suggest_serialization(
                tasks, repo_path="/tmp/repo", config={}
            )
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "major")
        self.assertEqual(conflicts[0].category, "serialization_overlap")

    def test_six_workers_hit_blocker_threshold(self):
        # 6 workers sharing a doc -> blocker (default blocker threshold is 6).
        tasks = self._make_tasks(6, "AGENTS.md")
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run", return_value=mock.Mock(stdout="", returncode=0)
        ):
            conflicts = cd.suggest_serialization(
                tasks, repo_path="/tmp/repo", config={}
            )
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "blocker")
        self.assertEqual(conflicts[0].category, "serialization_overlap")

    def test_custom_thresholds_override_default(self):
        # Custom {major: 3, blocker: 5}: 3 workers -> major, 5 -> blocker.
        custom = {"severity_threshold_n": {"major": 3, "blocker": 5}}
        # 3 workers, expect major.
        tasks = self._make_tasks(3, "AGENTS.md")
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run", return_value=mock.Mock(stdout="", returncode=0)
        ):
            conflicts = cd.suggest_serialization(
                tasks, repo_path="/tmp/repo", config=custom
            )
        self.assertEqual(conflicts[0].severity, "major")
        # 5 workers, expect blocker.
        tasks5 = self._make_tasks(5, "AGENTS.md")
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run", return_value=mock.Mock(stdout="", returncode=0)
        ):
            conflicts5 = cd.suggest_serialization(
                tasks5, repo_path="/tmp/repo", config=custom
            )
        self.assertEqual(conflicts5[0].severity, "blocker")

    def test_lockfile_path_always_blocker(self):
        # A lockfile always escalates to blocker regardless of N. Here 2
        # workers share package.json; below default threshold but lockfile
        # rule still wins.
        custom = {"lockfile_files": ["package.json"]}
        tasks = self._make_tasks(2, "package.json")
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ):
            conflicts = cd.suggest_serialization(
                tasks, repo_path="/tmp/repo", config=custom
            )
        self.assertEqual(conflicts[0].severity, "blocker")
        self.assertEqual(conflicts[0].category, "serialization_lockfile")

    def test_evidence_carries_owner_count(self):
        # The escalation decision depends on N. The emitted conflict must
        # surface N in evidence so operators can debug threshold choices.
        tasks = self._make_tasks(4, "AGENTS.md")
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run", return_value=mock.Mock(stdout="", returncode=0)
        ):
            conflicts = cd.suggest_serialization(
                tasks, repo_path="/tmp/repo", config={}
            )
        joined = " ".join(conflicts[0].evidence)
        # Some evidence mentions N>=4 or "N=4".
        self.assertTrue(
            any(token in joined for token in ("N=4", "n=4", "workers=4")),
            msg=f"owner count not in evidence: {conflicts[0].evidence}",
        )


# ---------------------------------------------------------------------------
# R19 gap 7: cleanup_worktree_artifacts — promote dirty_state to actions
# ---------------------------------------------------------------------------


class TestCleanupWorktreeArtifacts(unittest.TestCase):
    """R19 gap 7: turn `git status --porcelain` rows into runnable commands.

    Default patterns (from .jcode/conflict-config.yaml or module defaults):
        __pycache__/  -> rm -rf <path>     (directory)
        *.bak.*       -> rm -f <path>      (file)
        *.pyc         -> rm -f <path>
        *.tmp         -> rm -f <path>
    Anything else -> git add <path>.

    The function takes raw porcelain strings (e.g. " M file.py", "?? x.py")
    and returns CleanupAction objects with action in {"rm", "git_add"} and
    a runnable command string.
    """

    def test_function_returns_cleanup_actions(self):
        self.assertTrue(hasattr(cd, "cleanup_worktree_artifacts"))
        actions = cd.cleanup_worktree_artifacts([" M scripts/install.sh"])
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].path, "scripts/install.sh")
        self.assertEqual(actions[0].action, "git_add")
        self.assertEqual(actions[0].command, "git add scripts/install.sh")

    def test_pycache_dir_removed(self):
        actions = cd.cleanup_worktree_artifacts(
            ["?? tests/__pycache__/test_x.cpython-313.pyc"]
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action, "rm")
        # Either the file itself (rm -f) or its directory (rm -rf) depending
        # on whether the path is a directory or a file. Default behavior
        # treats the path as a file and uses rm -f.
        self.assertIn("rm", actions[0].command)
        self.assertTrue(
            actions[0].command.startswith("rm ")
            or actions[0].command.startswith("rm -")
        )

    def test_bak_file_removed(self):
        actions = cd.cleanup_worktree_artifacts(
            ["?? scripts/install.sh.bak.1234567890"]
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action, "rm")
        self.assertIn("rm ", actions[0].command)
        self.assertIn("scripts/install.sh.bak.1234567890", actions[0].command)

    def test_pyc_file_removed(self):
        actions = cd.cleanup_worktree_artifacts(["?? module.pyc"])
        self.assertEqual(actions[0].action, "rm")
        self.assertIn("module.pyc", actions[0].command)

    def test_tmp_file_removed(self):
        actions = cd.cleanup_worktree_artifacts(["?? scratch.tmp"])
        self.assertEqual(actions[0].action, "rm")
        self.assertIn("scratch.tmp", actions[0].command)

    def test_untracked_non_pattern_staged(self):
        actions = cd.cleanup_worktree_artifacts(["?? docs/new.md"])
        self.assertEqual(actions[0].action, "git_add")
        self.assertEqual(actions[0].command, "git add docs/new.md")

    def test_modified_file_staged(self):
        actions = cd.cleanup_worktree_artifacts([" M scripts/install.sh"])
        self.assertEqual(actions[0].action, "git_add")
        self.assertEqual(actions[0].command, "git add scripts/install.sh")

    def test_added_file_no_op(self):
        # "A " porcelain prefix = already staged. Treat as no-op (commit
        # is the operator's job, not cleanup's).
        actions = cd.cleanup_worktree_artifacts(["A  scripts/install.sh"])
        self.assertEqual(actions[0].action, "noop")
        # No command emitted; the operator already ran `git add`.
        self.assertEqual(actions[0].command, "")

    def test_custom_patterns_override_default(self):
        actions = cd.cleanup_worktree_artifacts(
            ["?? x.log", "?? y.pyc"],
            patterns=["*.log"],
        )
        # *.log matches custom pattern -> rm
        self.assertEqual(actions[0].action, "rm")
        self.assertIn("x.log", actions[0].command)
        # *.pyc is no longer in the pattern set -> git_add
        self.assertEqual(actions[1].action, "git_add")
        self.assertEqual(actions[1].command, "git add y.pyc")

    def test_directory_pattern_uses_rm_rf(self):
        # A pattern ending with `/` is a directory; the emitted command
        # must use `rm -rf`, not `rm -f`.
        actions = cd.cleanup_worktree_artifacts(
            ["?? build/cache/"], patterns=["build/"]
        )
        self.assertEqual(actions[0].action, "rm")
        self.assertIn("rm -rf", actions[0].command)

    def test_action_reason_is_surfaced(self):
        # CleanupAction.remediation/reason explains why the action was picked.
        actions = cd.cleanup_worktree_artifacts(["?? x.pyc"])
        # `reason` must mention either the matched pattern or a fallback.
        self.assertTrue(
            actions[0].reason,
            msg="CleanupAction.reason must not be empty",
        )

    def test_empty_dirty_list_returns_empty(self):
        actions = cd.cleanup_worktree_artifacts([])
        self.assertEqual(actions, [])

    def test_unparseable_porcelain_row_kept_neutral(self):
        # A row that doesn't look like a porcelain entry must not crash;
        # surface as a no-op so the operator can inspect manually.
        actions = cd.cleanup_worktree_artifacts(["???"])
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action, "noop")


# ---------------------------------------------------------------------------
# R19 gap 6: pick_merge_strategy — choose FF vs --no-ff vs rebase
# ---------------------------------------------------------------------------


class TestPickMergeStrategy(unittest.TestCase):
    """R19 gap 6: pick the cheapest safe merge strategy for a set of branches.

    Strategy decision tree:
      - single branch, base is ancestor of branch     -> fast-forward
      - single branch, base NOT ancestor (diverged)   -> merge --no-ff
      - multiple branches, B is descendant of A       -> fast-forward (chain)
      - multiple branches, neither is ancestor        -> rebase-then-merge
      - git missing / unknown                        -> manual

    The function returns MergeStrategy objects carrying the strategy
    name, the reason, and the exact git commands the operator should run.
    """

    def test_single_branch_fast_forward(self):
        # Stub: `git merge-base --is-ancestor main feat/x` -> exit 0
        # (true). With one branch and base as ancestor, FF is viable.
        proc_ok = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run", return_value=proc_ok
        ):
            result = cd.pick_merge_strategy(
                branches=["feat/x"], base="main", repo_root="/tmp/repo"
            )
        self.assertEqual(result.strategy, "fast-forward")
        self.assertIn("main", result.reason.lower() + " " + " ".join(result.commands))
        self.assertTrue(any("feat/x" in c for c in result.commands))

    def test_single_branch_diverged(self):
        # `git merge-base --is-ancestor main feat/x` -> exit 1 (false).
        # Branch diverged from base; FF not possible.
        proc_fail = mock.Mock(returncode=1, stdout="", stderr="")
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run", return_value=proc_fail
        ):
            result = cd.pick_merge_strategy(
                branches=["feat/x"], base="main", repo_root="/tmp/repo"
            )
        self.assertEqual(result.strategy, "merge --no-ff")

    def test_chain_fast_forward(self):
        # A and B share base; B is descendant of A. The chain is FF-able.
        # Stub responses: `merge-base --is-ancestor main A` -> true,
        # `merge-base --is-ancestor main B` -> true,
        # `merge-base --is-ancestor A B` -> true.
        responses = iter([
            mock.Mock(returncode=0, stdout="", stderr=""),  # main is ancestor of A
            mock.Mock(returncode=0, stdout="", stderr=""),  # main is ancestor of B
            mock.Mock(returncode=0, stdout="", stderr=""),  # A is ancestor of B
        ])
        def fake_run(*args, **kwargs):
            return next(responses)
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run", side_effect=fake_run
        ):
            result = cd.pick_merge_strategy(
                branches=["feat/A", "feat/B"], base="main", repo_root="/tmp/repo"
            )
        self.assertEqual(result.strategy, "fast-forward")

    def test_parallel_branches_rebase(self):
        # A and B both diverge from base but neither contains the other.
        # All merge-base --is-ancestor checks fail.
        responses = iter([
            mock.Mock(returncode=1, stdout="", stderr=""),  # main is NOT ancestor of A
            mock.Mock(returncode=1, stdout="", stderr=""),  # main is NOT ancestor of B
            mock.Mock(returncode=1, stdout="", stderr=""),  # A is NOT ancestor of B
            mock.Mock(returncode=1, stdout="", stderr=""),  # B is NOT ancestor of A
        ])
        def fake_run(*args, **kwargs):
            return next(responses)
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run", side_effect=fake_run
        ):
            result = cd.pick_merge_strategy(
                branches=["feat/A", "feat/B"], base="main", repo_root="/tmp/repo"
            )
        self.assertEqual(result.strategy, "rebase-then-merge")
        # Commands should mention rebase and merge.
        joined = " ".join(result.commands)
        self.assertIn("rebase", joined)

    def test_no_branches_returns_drop(self):
        result = cd.pick_merge_strategy(
            branches=[], base="main", repo_root="/tmp/repo"
        )
        self.assertEqual(result.strategy, "drop")
        self.assertEqual(result.commands, [])

    def test_no_git_binary_returns_manual(self):
        with mock.patch.object(cd.shutil, "which", return_value=None):
            result = cd.pick_merge_strategy(
                branches=["feat/x"], base="main", repo_root="/tmp/repo"
            )
        self.assertEqual(result.strategy, "manual")
        self.assertEqual(result.commands, [])

    def test_strategy_reason_is_human_readable(self):
        proc_ok = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run", return_value=proc_ok
        ):
            result = cd.pick_merge_strategy(
                branches=["feat/x"], base="main", repo_root="/tmp/repo"
            )
        # reason explains WHY this strategy was picked
        self.assertTrue(result.reason)
        self.assertGreater(len(result.reason), 10)


# ---------------------------------------------------------------------------
# R19 gap 6 supporting type: MergeStrategy dataclass
# ---------------------------------------------------------------------------


class TestMergeStrategyDataclass(unittest.TestCase):
    """The MergeStrategy dataclass must expose the spec'd fields."""

    def test_merge_strategy_fields(self):
        self.assertTrue(hasattr(cd, "MergeStrategy"))
        m = cd.MergeStrategy(
            strategy="fast-forward",
            reason="base is ancestor of branch",
            commands=["git merge --ff-only feat/x"],
        )
        self.assertEqual(m.strategy, "fast-forward")
        self.assertEqual(m.reason, "base is ancestor of branch")
        self.assertEqual(m.commands, ["git merge --ff-only feat/x"])


# ---------------------------------------------------------------------------
# R19 gap 2: detect_branch_ancestry — classify branches by ancestry
# ---------------------------------------------------------------------------


class TestDetectBranchAncestry(unittest.TestCase):
    """R19 gap 2: classify a set of branches by their git ancestry.

    Output (BranchAncestry dataclass):
        parents         — dict[branch -> parent_branch or None].
        chains          — list of linear chains in topological order.
                          `chains[i][-1]` is the leaf of each chain.
        already_merged  — list of branches whose tip is reachable from base.
        parallel_groups — list of branch sets that share a merge-base but
                          have no ancestor relation to each other.
    """

    def _stub_ancestry(self, ancestry_pairs):
        """Stub `git merge-base --is-ancestor a b` for a list of (a, b) pairs."""
        ancestors = set(tuple(p) for p in ancestry_pairs)
        def fake_run(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            # cmd layout: ["git", "-C", repo, "merge-base", "--is-ancestor", a, b]
            if "merge-base" in cmd and "--is-ancestor" in cmd:
                ai = cmd.index("--is-ancestor")
                a, b = cmd[ai + 1], cmd[ai + 2]
                ok = (a, b) in ancestors
                return mock.Mock(returncode=0 if ok else 1, stdout="", stderr="")
            return mock.Mock(returncode=0, stdout="", stderr="")
        return fake_run

    def test_empty_branches_returns_empty(self):
        result = cd.detect_branch_ancestry(branches=[], base="main", repo_root="/tmp/repo")
        self.assertEqual(result.chains, [])
        self.assertEqual(result.already_merged, [])
        self.assertEqual(result.parents, {})

    def test_single_branch_one_chain(self):
        # No ancestry info -> single branch forms its own chain of length 1.
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run", side_effect=self._stub_ancestry([])
        ):
            result = cd.detect_branch_ancestry(
                branches=["feat/A"], base="main", repo_root="/tmp/repo"
            )
        self.assertEqual(len(result.chains), 1)
        self.assertEqual(result.chains[0], ["feat/A"])
        self.assertEqual(result.parents["feat/A"], None)

    def test_chain_a_ancestor_of_b(self):
        # A is ancestor of B => one chain [A, B].
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run",
            side_effect=self._stub_ancestry([("feat/A", "feat/B")]),
        ):
            result = cd.detect_branch_ancestry(
                branches=["feat/A", "feat/B"], base="main", repo_root="/tmp/repo"
            )
        # Both end up in one chain.
        all_branches = [b for chain in result.chains for b in chain]
        self.assertEqual(sorted(all_branches), ["feat/A", "feat/B"])
        # Parent map: A has no parent (None), B's parent is A.
        self.assertIsNone(result.parents["feat/A"])
        self.assertEqual(result.parents["feat/B"], "feat/A")

    def test_three_branch_chain(self):
        # A -> B -> C (A ancestor of B, B ancestor of C).
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run",
            side_effect=self._stub_ancestry([
                ("feat/A", "feat/B"),
                ("feat/A", "feat/C"),
                ("feat/B", "feat/C"),
            ]),
        ):
            result = cd.detect_branch_ancestry(
                branches=["feat/A", "feat/B", "feat/C"],
                base="main", repo_root="/tmp/repo",
            )
        all_branches = [b for chain in result.chains for b in chain]
        self.assertEqual(sorted(all_branches), ["feat/A", "feat/B", "feat/C"])
        # All three should be in the same chain.
        self.assertEqual(len(result.chains), 1)
        # Order: A, B, C
        self.assertEqual(result.chains[0], ["feat/A", "feat/B", "feat/C"])

    def test_parallel_branches_separate_chains(self):
        # A and B parallel (no ancestor relation) -> two chains.
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run",
            side_effect=self._stub_ancestry([]),
        ):
            result = cd.detect_branch_ancestry(
                branches=["feat/A", "feat/B"], base="main", repo_root="/tmp/repo"
            )
        self.assertEqual(len(result.chains), 2)
        all_branches = sorted(b for chain in result.chains for b in chain)
        self.assertEqual(all_branches, ["feat/A", "feat/B"])

    def test_already_merged_branch_dropped(self):
        # feat/A is already an ancestor of main -> already_merged.
        # Use base="main" and test "feat/A" ancestor of "main".
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run",
            side_effect=self._stub_ancestry([("feat/A", "main")]),
        ):
            result = cd.detect_branch_ancestry(
                branches=["feat/A", "feat/B"], base="main", repo_root="/tmp/repo"
            )
        self.assertIn("feat/A", result.already_merged)
        # feat/B still in chains.
        all_branches = [b for chain in result.chains for b in chain]
        self.assertIn("feat/B", all_branches)
        self.assertNotIn("feat/A", all_branches)

    def test_no_git_binary_returns_drop(self):
        with mock.patch.object(cd.shutil, "which", return_value=None):
            result = cd.detect_branch_ancestry(
                branches=["feat/A"], base="main", repo_root="/tmp/repo"
            )
        # Without git, treat all branches as a single parallel group:
        # one chain, no already_merged, no parents.
        self.assertEqual(len(result.chains), 1)
        self.assertEqual(result.chains[0], ["feat/A"])


# ---------------------------------------------------------------------------
# R19 gap 2 supporting type: BranchAncestry dataclass
# ---------------------------------------------------------------------------


class TestBranchAncestryDataclass(unittest.TestCase):
    def test_branch_ancestry_fields(self):
        self.assertTrue(hasattr(cd, "BranchAncestry"))
        b = cd.BranchAncestry(
            parents={"feat/A": None, "feat/B": "feat/A"},
            chains=[["feat/A", "feat/B"]],
            already_merged=[],
            parallel_groups=[],
        )
        self.assertEqual(b.parents["feat/B"], "feat/A")
        self.assertEqual(b.chains, [["feat/A", "feat/B"]])


# ---------------------------------------------------------------------------
# R19 gap 1: auto_extract_scope + plan-order --branches
# ---------------------------------------------------------------------------


class TestAutoExtractScope(unittest.TestCase):
    """R19 gap 1: derive {branch: [files]} from `git diff base..branch`."""

    def _stub_diff(self, diff_map):
        """Stub `git -C <root> diff base..branch --name-only`.

        `diff_map` is {branch: "<newline-separated files>"}.
        """
        def fake_run(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            # cmd: ["git", "-C", root, "diff", "base..branch", "--name-only"]
            if "diff" in cmd and "--name-only" in cmd:
                # find ".."
                for piece in cmd:
                    if ".." in piece:
                        branch = piece.split("..", 1)[1]
                        files = diff_map.get(branch, "")
                        return mock.Mock(
                            returncode=0, stdout=files, stderr=""
                        )
            return mock.Mock(returncode=0, stdout="", stderr="")
        return fake_run

    def test_auto_extract_returns_branch_to_files(self):
        diff_map = {
            "feat/A": "src/a.py\nsrc/shared.py\n",
            "feat/B": "src/b.py\n",
        }
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run", side_effect=self._stub_diff(diff_map)
        ):
            scope = cd.auto_extract_scope(
                ["feat/A", "feat/B"], repo_root="/tmp/repo"
            )
        self.assertEqual(set(scope.keys()), {"feat/A", "feat/B"})
        self.assertIn("src/a.py", scope["feat/A"])
        self.assertIn("src/shared.py", scope["feat/A"])
        self.assertEqual(scope["feat/B"], ["src/b.py"])

    def test_auto_extract_handles_empty_diff(self):
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run",
            side_effect=self._stub_diff({"feat/A": ""}),
        ):
            scope = cd.auto_extract_scope(["feat/A"], repo_root="/tmp/repo")
        self.assertEqual(scope["feat/A"], [])

    def test_auto_extract_empty_branches_returns_empty_dict(self):
        scope = cd.auto_extract_scope([], repo_root="/tmp/repo")
        self.assertEqual(scope, {})

    def test_auto_extract_no_git_binary(self):
        with mock.patch.object(cd.shutil, "which", return_value=None):
            scope = cd.auto_extract_scope(
                ["feat/A", "feat/B"], repo_root="/tmp/repo"
            )
        # Each branch gets an empty scope; the operator must populate manually.
        self.assertEqual(scope, {"feat/A": [], "feat/B": []})


class TestPlanOrderFromBranches(unittest.TestCase):
    """R19 gap 1: `plan-order --branches` derives scope + ancestry from git."""

    def _stub_full(self, diff_map, ancestry_pairs):
        """Stub both diff and merge-base --is-ancestor."""
        def fake_run(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "merge-base" in cmd and "--is-ancestor" in cmd:
                ai = cmd.index("--is-ancestor")
                a, b = cmd[ai + 1], cmd[ai + 2]
                ok = (a, b) in ancestry_pairs
                return mock.Mock(returncode=0 if ok else 1, stdout="", stderr="")
            if "diff" in cmd and "--name-only" in cmd:
                for piece in cmd:
                    if ".." in piece:
                        branch = piece.split("..", 1)[1]
                        files = diff_map.get(branch, "")
                        return mock.Mock(
                            returncode=0, stdout=files, stderr=""
                        )
            return mock.Mock(returncode=0, stdout="", stderr="")
        return fake_run

    def test_plan_order_branches_chain_same_phase_when_disjoint(self):
        # Chain A -> B but their files are disjoint: should appear in the
        # same phase (chain relationship is metadata; file overlap drives
        # actual phase assignment).
        diff_map = {
            "feat/A": "src/a.py\n",
            "feat/B": "src/b.py\n",
        }
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run",
            side_effect=self._stub_full(diff_map, [("feat/A", "feat/B")]),
        ):
            plan = cd.plan_execution_order_from_branches(
                branches=["feat/A", "feat/B"],
                base="main",
                repo_root="/tmp/repo",
            )
        # Both should be in the same phase because files don't conflict.
        all_in_one_phase = any(
            len(phase) >= 2 and sorted(phase) == ["feat/A", "feat/B"]
            for phase in plan.phases
        )
        self.assertTrue(
            all_in_one_phase,
            msg=f"expected A,B in one phase, got phases={plan.phases}",
        )

    def test_plan_order_branches_chain_different_phases_when_shared_file(self):
        # Chain A -> B with overlapping file -> must be in different phases.
        diff_map = {
            "feat/A": "src/shared.py\n",
            "feat/B": "src/shared.py\n",
        }
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run",
            side_effect=self._stub_full(diff_map, [("feat/A", "feat/B")]),
        ):
            plan = cd.plan_execution_order_from_branches(
                branches=["feat/A", "feat/B"],
                base="main",
                repo_root="/tmp/repo",
            )
        # A and B cannot be in the same phase.
        same_phase = any(
            "feat/A" in phase and "feat/B" in phase for phase in plan.phases
        )
        self.assertFalse(same_phase, msg=f"phases={plan.phases}")
        # A must come before B.
        a_phase = next(i for i, p in enumerate(plan.phases) if "feat/A" in p)
        b_phase = next(i for i, p in enumerate(plan.phases) if "feat/B" in p)
        self.assertLess(a_phase, b_phase)

    def test_plan_order_branches_parallel_in_same_phase(self):
        # Parallel branches with disjoint files -> same phase.
        diff_map = {
            "feat/A": "src/a.py\n",
            "feat/B": "src/b.py\n",
        }
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ), mock.patch.object(
            cd.subprocess, "run",
            side_effect=self._stub_full(diff_map, []),  # no ancestry
        ):
            plan = cd.plan_execution_order_from_branches(
                branches=["feat/A", "feat/B"],
                base="main",
                repo_root="/tmp/repo",
            )
        all_in_one_phase = any(
            len(phase) >= 2 and sorted(phase) == ["feat/A", "feat/B"]
            for phase in plan.phases
        )
        self.assertTrue(all_in_one_phase)

    def test_plan_order_branches_empty_returns_empty(self):
        plan = cd.plan_execution_order_from_branches(
            branches=[], base="main", repo_root="/tmp/repo"
        )
        self.assertEqual(plan.phases, [])


class TestPlanOrderCLIWithBranches(unittest.TestCase):
    """The `plan-order` subcommand must accept `--branches` instead of `--tasks`."""

    def test_cli_plan_order_branches_runs(self):
        # Patch only `cd.shutil.which` (cheap); leave real subprocess.run
        # to be called. /tmp is not a git repo so git returns errors and
        # `_run_git` falls back to empty stdout — exactly the case we want.
        with mock.patch.object(
            cd.shutil, "which", return_value="/usr/bin/git"
        ):
            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parent / "conflict-detect.py"),
                    "plan-order",
                    "--branches", "feat/nonexistent",
                    "--base", "main",
                    "--repo", "/tmp",
                    "--format", "json",
                ],
                capture_output=True, text=True,
            )
        # Should exit 0 with a valid JSON plan (branches phase).
        self.assertEqual(
            result.returncode, 0,
            msg=f"stdout={result.stdout!r} stderr={result.stderr!r}",
        )
        out = json.loads(result.stdout)
        self.assertIn("phases", out)
        self.assertIn("critical_path", out)
        # Single branch forms its own chain of 1.
        self.assertEqual(len(out["phases"]), 1)


if __name__ == "__main__":
    unittest.main()
