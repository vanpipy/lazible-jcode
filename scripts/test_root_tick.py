#!/usr/bin/env python3
"""Tests for scripts/root-tick.sh.

These tests exercise the wrapper against real (throwaway) git repos to
verify:

  * repo-root detection works in both main and worktree layouts
  * exit codes match the worst recommended_action in the table
  * the wrapper surfaces silent-stuck branches (final commit past the
    handoff-pending window → recommended_action = integrate-now → exit 1)

The wrapper is the root agent's pre-action gate, so regressions here are
exactly the silent-stuck failure mode the test suite is designed to
prevent.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
WRAPPER = REPO_ROOT / "scripts" / "root-tick.sh"
MONITOR = REPO_ROOT / "scripts" / "swarm-state-monitor.py"


def _git(*args: str, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run a git command and return CompletedProcess. Asserts rc=0."""
    full_env = os.environ.copy()
    full_env["GIT_AUTHOR_NAME"] = "Test"
    full_env["GIT_AUTHOR_EMAIL"] = "test@example.com"
    full_env["GIT_COMMITTER_NAME"] = "Test"
    full_env["GIT_COMMITTER_EMAIL"] = "test@example.com"
    if env:
        full_env.update(env)
    r = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=full_env,
    )
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r


def _init_repo(tmp: Path) -> Path:
    """Create a minimal git repo at tmp with one initial commit."""
    tmp.mkdir(parents=True, exist_ok=True)
    _git("init", "-b", "main", cwd=tmp)
    _git("config", "user.email", "test@example.com", cwd=tmp)
    _git("config", "user.name", "Test", cwd=tmp)
    (tmp / "README.md").write_text("# test\n")
    _git("add", "README.md", cwd=tmp)
    _git("commit", "-m", "initial", cwd=tmp)
    return tmp


def _make_worker_branch(
    repo: Path,
    *,
    branch_name: str,
    final_age_min: int | None = None,
    progress_age_min: int | None = None,
) -> str:
    """Create a worker branch with a typed-artifact commit.

    final_age_min:     create a `final` artifact commit, optionally
                       dated N minutes in the past via GIT_AUTHOR_DATE /
                       GIT_COMMITTER_DATE.
    progress_age_min:  create a `progress` artifact commit, optional.
    """
    _git("checkout", "-b", branch_name, cwd=repo)
    # Use a flat filename derived from the branch's basename (after the
    # last `/`). Writing to "feat/healthy_abcdef0.txt" would create a
    # directory tree, which we don't want.
    flat_name = branch_name.rsplit("/", 1)[-1] + ".txt"
    (repo / flat_name).write_text("worker output\n")

    if final_age_min is not None:
        body = textwrap.dedent("""\
            worker output

            ```json artifact
            {
              "type": "final",
              "step": "done",
              "next": "root merges",
              "confidence": "high"
            }
            ```
            """)
        env = {
            "GIT_AUTHOR_DATE": _fake_date(final_age_min),
            "GIT_COMMITTER_DATE": _fake_date(final_age_min),
        }
        _git("add", flat_name, cwd=repo, env=env)
        _git("commit", "-m", body, cwd=repo, env=env)
    elif progress_age_min is not None:
        body = textwrap.dedent("""\
            worker output

            ```json artifact
            {
              "type": "progress",
              "step": "mid-task",
              "next": "continue",
              "confidence": "medium"
            }
            ```
            """)
        env = {
            "GIT_AUTHOR_DATE": _fake_date(progress_age_min),
            "GIT_COMMITTER_DATE": _fake_date(progress_age_min),
        }
        _git("add", flat_name, cwd=repo, env=env)
        _git("commit", "-m", body, cwd=repo, env=env)
    else:
        _git("add", flat_name, cwd=repo)
        _git("commit", "-m", "no artifact", cwd=repo)

    _git("checkout", "main", cwd=repo)
    return branch_name


def _fake_date(minutes_ago: int) -> str:
    """Return a GIT_AUTHOR_DATE-compatible ISO date string N minutes ago."""
    import datetime
    dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z")


def _run_root_tick(cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(WRAPPER)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


class TestRootTickWrapper(unittest.TestCase):
    """Behavioral tests for scripts/root-tick.sh.

    These exist because the silent-stuck failure mode in
    postman-framework-hardening (a worker committed `final` but root never
    noticed — exit-code-0 == "nothing to do") was a regression of root
    discipline. The wrapper enforces discipline via exit code; tests here
    pin that contract.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="root-tick-test-"))
        self.repo = _init_repo(self.tmp / "repo")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_wrapper_script_exists_and_is_executable(self) -> None:
        self.assertTrue(WRAPPER.exists(), f"missing {WRAPPER}")
        self.assertTrue(os.access(WRAPPER, os.X_OK), f"{WRAPPER} not +x")

    def test_silent_stuck_final_commit_surfaces_integrate_now(self) -> None:
        """The repro: final commit 10 min ago, no handoff.

        Before fix: classification=quiet, no action field, root
        mis-classified as 'nothing to do' and missed integration.

        After fix: recommended_action=integrate-now, exit code 1,
        wrapper prints 'PAUSE'.
        """
        _make_worker_branch(
            self.repo,
            branch_name="feat/silent_abcdef0",
            final_age_min=10,
        )
        r = _run_root_tick(self.repo)
        self.assertEqual(
            r.returncode, 1,
            f"expected exit 1 (integrate-now), got {r.returncode}\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}",
        )
        self.assertIn("integrate-now", r.stdout)
        self.assertIn("PAUSE", r.stdout)
        self.assertIn("feat/silent_abcdef0", r.stdout)

    def test_healthy_progress_action_is_observe(self) -> None:
        """Fresh progress commit (< 5 min) → recommended_action=observe → exit 0."""
        _make_worker_branch(
            self.repo,
            branch_name="feat/healthy_abcdef0",
            progress_age_min=1,
        )
        r = _run_root_tick(self.repo)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("Safe to integrate", r.stdout)

    def test_silent_dead_branch_triggers_recoverer_exit(self) -> None:
        """progress commit past silent SLA (15min) + past dead SLA (30min)
        → recommended_action=recover → exit code 2 → wrapper prints
        'SPAWN RECOVERER'.
        """
        _make_worker_branch(
            self.repo,
            branch_name="feat/dead_abcdef0",
            progress_age_min=120,
        )
        r = _run_root_tick(self.repo)
        self.assertEqual(
            r.returncode, 2,
            f"expected exit 2 (recover), got {r.returncode}\n{r.stdout}",
        )
        self.assertIn("SPAWN RECOVERER", r.stdout)

    def test_wrapper_exits_3_outside_git_repo(self) -> None:
        """Cwd is a non-git directory → wrapper exits 3."""
        non_git = self.tmp / "not-a-repo"
        non_git.mkdir()
        r = _run_root_tick(non_git)
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("not in a git repo", r.stderr)

    def test_wrapper_handles_multiple_branches_takes_worst(self) -> None:
        """Two branches: one healthy (observe), one silent-stuck
        (integrate-now). Wrapper exit code = worst = 1.
        """
        _make_worker_branch(
            self.repo,
            branch_name="feat/healthy_abcdef0",
            progress_age_min=1,
        )
        _make_worker_branch(
            self.repo,
            branch_name="feat/silent_abcdef0",
            final_age_min=10,
        )
        r = _run_root_tick(self.repo)
        self.assertEqual(
            r.returncode, 1,
            f"expected exit 1 (worst is integrate-now), got {r.returncode}",
        )

    def test_wrapper_includes_action_column_in_table(self) -> None:
        """The wrapper's underlying tick output must include the
        'action' column header so root can read it directly.
        """
        _make_worker_branch(
            self.repo,
            branch_name="feat/x_abcdef0",
            final_age_min=10,
        )
        r = _run_root_tick(self.repo)
        self.assertIn("action", r.stdout)


class TestRootTickHelpfulMessages(unittest.TestCase):
    """Verify the wrapper's per-exit-code ACTION message is unambiguous."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="root-tick-msg-"))
        self.repo = _init_repo(self.tmp / "repo")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_exit_0_message_is_safe_to_integrate(self) -> None:
        _make_worker_branch(
            self.repo, branch_name="feat/h_abcdef0", progress_age_min=1,
        )
        r = _run_root_tick(self.repo)
        self.assertEqual(r.returncode, 0)
        self.assertIn("Safe to integrate / spawn", r.stdout)

    def test_exit_1_message_mentions_complete_node_gap(self) -> None:
        """The exit-1 message must remind root about the complete_node
        gap (the silent-stuck failure mode).
        """
        _make_worker_branch(
            self.repo, branch_name="feat/s_abcdef0", final_age_min=10,
        )
        r = _run_root_tick(self.repo)
        self.assertEqual(r.returncode, 1)
        # The wrapper must call out that root should integrate even if
        # complete_node never arrived — this is the discipline the
        # wrapper enforces.
        self.assertIn("complete_node", r.stdout)


if __name__ == "__main__":
    unittest.main()