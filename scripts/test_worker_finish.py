"""Tests for scripts/worker-finish.sh — the canonical worker.json writer.

The script is not git-aware. Tests use a throwaway tmp dir, not a worktree.
Five tests as specified by item E' of the swarm spawn prompt:

1. test_missing_required_env_returns_nonzero
2. test_invalid_confidence_returns_nonzero
3. test_atomic_write_creates_final_file
4. test_custom_output_path_respected
5. test_files_changed_parsed_from_space_separated_string

Run via:
    python3 -m unittest scripts.test_worker_finish
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

# Resolve repo root from this test file's location so the script path is
# stable regardless of where the test is invoked from.
TEST_FILE = Path(__file__).resolve()
REPO_ROOT = TEST_FILE.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "worker-finish.sh"


def _run(env: dict, cwd: Path, output_path: str | None = None) -> tuple[int, str, str]:
    """Invoke worker-finish.sh in `cwd` with `env`, optionally overriding output.

    Returns (exit_code, stdout, stderr). Output_path override lets tests
    point at a non-default location; passed via env.
    """
    full_env = os.environ.copy()
    full_env.update(env)
    if output_path is not None:
        full_env["WORKER_OUTPUT"] = output_path
    proc = subprocess.run(
        [str(SCRIPT_PATH)],
        cwd=str(cwd),
        env=full_env,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


class WorkerFinishScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        # Throwaway tmp dir; script is not git-aware so no worktree setup needed.
        self.tmpdir = Path(tempfile.mkdtemp(prefix="worker-finish-test-"))
        # Sanity: script exists at the expected path.
        self.assertTrue(
            SCRIPT_PATH.exists(),
            f"worker-finish.sh not found at {SCRIPT_PATH}; cannot run tests",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # --- Test 1 ---
    def test_missing_required_env_returns_nonzero(self) -> None:
        # No env vars set; expect non-zero exit AND stderr names the missing variable.
        rc, _stdout, stderr = _run(env={}, cwd=self.tmpdir)
        self.assertNotEqual(
            rc,
            0,
            f"expected non-zero exit, got {rc}. stderr={stderr!r}",
        )
        self.assertIn(
            "WORKER_BRANCH",
            stderr,
            f"stderr should name the missing var WORKER_BRANCH; got: {stderr!r}",
        )

    # --- Test 2 ---
    def test_invalid_confidence_returns_nonzero(self) -> None:
        rc, _stdout, stderr = _run(
            env={
                "WORKER_BRANCH": "feat/x_abc1234",
                "WORKER_COMMIT": "deadbeef" * 4,  # 28 hex chars
                "WORKER_SUMMARY": "summary line",
                "WORKER_FILES_CHANGED": "a.sh b.py",
                "WORKER_TEST_MODULE": "scripts.test_worker_finish",
                "WORKER_CONFIDENCE": "bogus",
            },
            cwd=self.tmpdir,
        )
        self.assertNotEqual(
            rc,
            0,
            f"expected non-zero exit for bogus confidence, got {rc}",
        )
        self.assertIn(
            "WORKER_CONFIDENCE",
            stderr,
            f"stderr should name the bad var WORKER_CONFIDENCE; got: {stderr!r}",
        )

    # --- Test 3 ---
    def test_atomic_write_creates_final_file(self) -> None:
        rc, stdout, stderr = _run(
            env={
                "WORKER_BRANCH": "feat/worker-json_50e17e6",
                "WORKER_COMMIT": "abcdef" + "0" * 34,
                "WORKER_SUMMARY": "worker-finish.sh + tests + implementer.md step 9",
                "WORKER_FILES_CHANGED": "scripts/worker-finish.sh scripts/test_worker_finish.py swarm/roles/implementer.md",
                "WORKER_TEST_MODULE": "scripts.test_worker_finish",
                "WORKER_CONFIDENCE": "high",
            },
            cwd=self.tmpdir,
        )
        self.assertEqual(
            rc, 0, f"expected exit 0, got {rc}. stderr={stderr!r}"
        )
        out_file = self.tmpdir / "worker.json"
        self.assertTrue(
            out_file.exists(),
            f"expected {out_file} to exist after success",
        )
        # Validate JSON shape
        data = json.loads(out_file.read_text())
        expected_keys = {
            "branch",
            "commit",
            "summary",
            "files_changed",
            "gates_run",
            "confidence",
            "blockers",
        }
        self.assertTrue(
            expected_keys.issubset(data.keys()),
            f"missing keys: {expected_keys - set(data.keys())}",
        )
        # Validate the values for the most stable fields
        self.assertEqual(data["branch"], "feat/worker-json_50e17e6")
        self.assertEqual(data["commit"], "abcdef" + "0" * 34)
        self.assertEqual(data["confidence"], "high")
        self.assertEqual(data["blockers"], [])
        # gates_run should mention the test module
        self.assertIn(
            "scripts.test_worker_finish", str(data["gates_run"])
        )
        # Tmp file should NOT linger (atomic move happened)
        self.assertFalse(
            (self.tmpdir / "worker.json.tmp").exists(),
            "worker.json.tmp should be cleaned up after atomic move",
        )
        # stdout should mention the final path
        self.assertIn("worker.json", stdout)

    # --- Test 4 ---
    def test_custom_output_path_respected(self) -> None:
        custom = str(self.tmpdir / "subdir" / "custom-output.json")
        # Make sure parent dir exists since the script uses .tmp + mv.
        os.makedirs(os.path.dirname(custom), exist_ok=True)
        rc, _stdout, stderr = _run(
            env={
                "WORKER_BRANCH": "feat/x_abc1234",
                "WORKER_COMMIT": "1234567" + "0" * 33,
                "WORKER_SUMMARY": "custom path test",
                "WORKER_FILES_CHANGED": "x.sh",
                "WORKER_TEST_MODULE": "scripts.test_worker_finish",
                "WORKER_CONFIDENCE": "medium",
            },
            cwd=self.tmpdir,
            output_path=custom,
        )
        self.assertEqual(rc, 0, f"stderr={stderr!r}")
        self.assertTrue(
            os.path.exists(custom),
            f"expected custom output at {custom}",
        )
        # Default path should NOT be created in cwd.
        default_path = self.tmpdir / "worker.json"
        self.assertFalse(
            default_path.exists(),
            f"default {default_path} should not exist when WORKER_OUTPUT overrides",
        )

    # --- Test 5 ---
    def test_files_changed_parsed_from_space_separated_string(self) -> None:
        out_file = self.tmpdir / "worker.json"
        rc, _stdout, stderr = _run(
            env={
                "WORKER_BRANCH": "feat/x_abc1234",
                "WORKER_COMMIT": "feedface" * 4,
                "WORKER_SUMMARY": "files-changed parse test",
                "WORKER_FILES_CHANGED": "a.sh b.py c.md",
                "WORKER_TEST_MODULE": "scripts.test_worker_finish",
                "WORKER_CONFIDENCE": "low",
            },
            cwd=self.tmpdir,
        )
        self.assertEqual(rc, 0, f"stderr={stderr!r}")
        data = json.loads(out_file.read_text())
        self.assertEqual(
            data["files_changed"],
            ["a.sh", "b.py", "c.md"],
            f"expected files_changed parsed as list, got {data['files_changed']!r}",
        )


if __name__ == "__main__":
    unittest.main()
