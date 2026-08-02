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


if __name__ == "__main__":
    unittest.main()
