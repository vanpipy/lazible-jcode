#!/usr/bin/env python3
"""Tests for scripts/check_artifact_conflicts.py.

Each test creates a throwaway git repo, makes a commit with or without
Git conflict markers, then runs the script and asserts the exit code /
stderr content.

The script path is resolved relative to this test file's directory.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent / "check_artifact_conflicts.py"


def _run(cmd, cwd, **kwargs):
    """Run cmd in cwd, returning CompletedProcess with capture."""
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        **kwargs,
    )


def _make_temp_repo() -> str:
    """Create a temp dir + init git repo + initial commit. Return path."""
    tmp = tempfile.mkdtemp(prefix="check-conflicts-")
    _run(["git", "init", "-q", "-b", "main", tmp], cwd=tmp)
    _run(["git", "config", "user.email", "test@local"], cwd=tmp)
    _run(["git", "config", "user.name", "test"], cwd=tmp)
    # initial commit on main
    (Path(tmp) / "README.md").write_text("init\n")
    _run(["git", "add", "README.md"], cwd=tmp)
    _run(["git", "commit", "-q", "-m", "init"], cwd=tmp)
    return tmp


class TestCheckArtifactConflicts(unittest.TestCase):
    def _cleanup(self, repo):
        """Best-effort cleanup of temp repo."""
        _run(["git", "worktree", "remove", "--force", repo], cwd=repo)
        import shutil
        shutil.rmtree(repo, ignore_errors=True)

    def test_clean_diff_passes(self):
        """A clean commit produces exit 0 and 'clean' message."""
        repo = _make_temp_repo()
        try:
            (Path(repo) / "hello.txt").write_text("hello\n")
            _run(["git", "add", "hello.txt"], cwd=repo)
            _run(["git", "commit", "-q", "-m", "add hello"], cwd=repo)
            head = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
            result = _run(
                [sys.executable, str(SCRIPT), head],
                cwd=repo,
            )
            self.assertEqual(
                result.returncode, 0,
                f"expected exit 0, got {result.returncode}\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("clean", result.stdout)
        finally:
            self._cleanup(repo)

    def test_conflict_marker_in_added_line_fails(self):
        """A commit adding a file with conflict markers exits 1."""
        repo = _make_temp_repo()
        try:
            marker_lines = (
                "<<<<<<< ours\n"
                "foo\n"
                "=======\n"
                "bar\n"
                ">>>>>>> theirs\n"
            )
            (Path(repo) / "merged.txt").write_text(marker_lines)
            _run(["git", "add", "merged.txt"], cwd=repo)
            _run(["git", "commit", "-q", "-m", "conflict"], cwd=repo)
            head = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
            result = _run(
                [sys.executable, str(SCRIPT), head],
                cwd=repo,
            )
            self.assertEqual(
                result.returncode, 1,
                f"expected exit 1, got {result.returncode}\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("CONFLICT", result.stderr)
        finally:
            self._cleanup(repo)

    def test_conflict_marker_in_modified_line_fails(self):
        """A commit modifying an existing file to contain conflict markers exits 1."""
        repo = _make_temp_repo()
        try:
            # base file
            (Path(repo) / "file.txt").write_text("original\n")
            _run(["git", "add", "file.txt"], cwd=repo)
            _run(["git", "commit", "-q", "-m", "add file"], cwd=repo)
            # modify it to contain markers
            (Path(repo) / "file.txt").write_text(
                "original\n"
                "<<<<<<< ours\n"
                "modified\n"
                "=======\n"
                "alt\n"
                ">>>>>>> theirs\n"
            )
            _run(["git", "add", "file.txt"], cwd=repo)
            _run(["git", "commit", "-q", "-m", "modify with conflict"], cwd=repo)
            head = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
            result = _run(
                [sys.executable, str(SCRIPT), head],
                cwd=repo,
            )
            self.assertEqual(
                result.returncode, 1,
                f"expected exit 1, got {result.returncode}\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}",
            )
            self.assertIn("CONFLICT", result.stderr)
        finally:
            self._cleanup(repo)

    def test_missing_input_argument_fails(self):
        """Running with no positional arg exits non-zero with usage message."""
        result = _run(
            [sys.executable, str(SCRIPT)],
            cwd=tempfile.gettempdir(),
        )
        self.assertNotEqual(
            result.returncode, 0,
            f"expected non-zero exit, got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )
        # usage on stderr
        self.assertTrue(
            "usage" in result.stderr.lower() or "missing" in result.stderr.lower(),
            f"expected usage message, got stderr: {result.stderr!r}",
        )

    def test_markdown_heading_with_equals_is_not_a_marker(self):
        """`## =======` (markdown heading) is NOT a conflict marker."""
        repo = _make_temp_repo()
        try:
            (Path(repo) / "doc.md").write_text(
                "## =======\n"
                "this is a heading with equals\n"
            )
            _run(["git", "add", "doc.md"], cwd=repo)
            _run(["git", "commit", "-q", "-m", "add doc"], cwd=repo)
            head = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
            result = _run(
                [sys.executable, str(SCRIPT), head],
                cwd=repo,
            )
            self.assertEqual(
                result.returncode, 0,
                f"expected exit 0 (markdown heading should not flag), "
                f"got {result.returncode}\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}",
            )
        finally:
            self._cleanup(repo)

    def test_nonexistent_commit_exits_2(self):
        """A bogus commit-ish exits 2 with error message."""
        repo = _make_temp_repo()
        try:
            result = _run(
                [sys.executable, str(SCRIPT), "0000000000000000000000000000000000000000"],
                cwd=repo,
            )
            self.assertEqual(
                result.returncode, 2,
                f"expected exit 2, got {result.returncode}\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}",
            )
        finally:
            self._cleanup(repo)


if __name__ == "__main__":
    unittest.main()
