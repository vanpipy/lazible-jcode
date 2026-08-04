#!/usr/bin/env python3
"""Simulator tests for the recoverer role's liveness edge cases.

Each test creates a throwaway git repo in a tempdir, stages commit
timestamps with GIT_COMMITTER_DATE / GIT_AUTHOR_DATE, then invokes the
classifier as a subprocess and parses the JSON block from its stdout.

These tests pin the 5 liveness edge cases the recoverer role depends on:

  1. Dead progress branch (`progress` artifact, 30 min old) -> recoverer.
  2. Final commit without handoff (`final` artifact, 5 min old) ->
     integrate-now (silent-stuck gate catches this).
  3. Empty branch (ref exists, no commits) -> recoverer.
  4. Abandoned worker with partial progress -> recover / investigate.
  5. Mixed-batch tick returns the worst-action aggregate.
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional


_HERE = Path(__file__).resolve().parent
_MONITOR = _HERE / "swarm-state-monitor.py"


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git(args, cwd, env=None):
    """Run git, raise on failure."""
    full_env = {**os.environ, **env} if env else None
    subprocess.run(
        ["git", *args],
        cwd=str(cwd), capture_output=True, text=True,
        env=full_env, check=True,
    )


def _git_stdout(args, cwd):
    """Run git, return stripped stdout. Raises on failure."""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd), capture_output=True, text=True, check=True,
    )
    return proc.stdout.strip()


def _init_repo(tmp, base_age_min=0):
    """Init fresh repo on `main` with one base commit.

    `base_age_min` lets tests backdate the base commit so an empty
    branch pointing at HEAD reads as past the dead SLA. Default 0
    (fresh base commit, suitable for tests that add their own commits).
    """
    _git(["init", "-q", "-b", "main"], tmp)
    _git(["config", "user.email", "test@local"], tmp)
    _git(["config", "user.name", "Test"], tmp)
    (tmp / "README.md").write_text("base\n")
    _git(["add", "README.md"], tmp)
    if base_age_min > 0:
        # Backdate the base commit so a branch pointing at HEAD with no
        # extra commits reads as past the dead SLA on the classifier.
        past = datetime.datetime.now() - datetime.timedelta(minutes=base_age_min)
        iso = past.strftime("%Y-%m-%dT%H:%M:%S")
        _git(["commit", "-q", "-m", "base"], tmp, env={
            "GIT_COMMITTER_DATE": iso,
            "GIT_AUTHOR_DATE": iso,
        })
    else:
        _git(["commit", "-q", "-m", "base"], tmp)
    # On older git that ignores -b, the default branch may be `master`. Make
    # sure the integration target the classifier queries is named `main`.
    current = _git_stdout(["rev-parse", "--abbrev-ref", "HEAD"], tmp)
    if current != "main":
        _git(["branch", "-m", "main"], tmp)


def _commit_at(tmp, message, age_min, allow_empty=True):
    """Add a commit on the current branch, dated `age_min` ago.

    `allow_empty=True` keeps the helper usable for branches whose first
    commit does not need a tree change (e.g. typed-artifact simulators).
    """
    past = datetime.datetime.now() - datetime.timedelta(minutes=age_min)
    iso = past.strftime("%Y-%m-%dT%H:%M:%S")
    args = ["commit", "-q", "-m", message]
    if allow_empty:
        args.insert(1, "--allow-empty")
    _git(args, tmp, env={
        "GIT_COMMITTER_DATE": iso,
        "GIT_AUTHOR_DATE": iso,
    })


def _branch_with_artifact(tmp, branch_name, artifact_type, age_min):
    """Create `branch_name` with one commit (dated `age_min` ago) carrying
    a typed artifact block."""
    _git(["checkout", "-q", "-b", branch_name], tmp)
    artifact = {
        "type": artifact_type,
        "session_id": "test-session",
        "task_id": "test-task",
        "branch": branch_name,
        "commit": "placeholder",
        "elapsed_min": age_min,
        "step": f"test {artifact_type}",
        "next": "next",
        "confidence": "high",
        "blockers": [],
    }
    body = json.dumps(artifact)
    msg = (
        f"commit on {branch_name}\n\n"
        f"```json artifact\n{body}\n```\n"
    )
    _commit_at(tmp, msg, age_min)


def _empty_branch(tmp, branch_name):
    """Create `branch_name` ref pointing at HEAD with no extra commits."""
    _git(["branch", branch_name], tmp)


def _append_plain_commit(tmp, branch_name, age_min):
    """Add a plain (no-artifact) commit on `branch_name`, dated `age_min`
    ago. Assumes the branch already exists; checks it out if needed."""
    current = _git_stdout(["rev-parse", "--abbrev-ref", "HEAD"], tmp)
    if current != branch_name:
        _git(["checkout", "-q", branch_name], tmp)
    _commit_at(tmp, f"plain follow-up on {branch_name}", age_min)


# ---------------------------------------------------------------------------
# Classifier driver
# ---------------------------------------------------------------------------


def _run_tick(tmp):
    """Invoke `swarm-state-monitor.py tick --include-stale` against `tmp`.

    Returns the parsed JSON dict from the trailing JSON block. The script
    prints a table then a JSON object; the JSON is the last block on
    stdout. We extract the first line that is exactly `{` and parse from
    there to EOF.

    Exit code is intentionally ignored: 1 means "root must act" (e.g.
    `integrate-now`), 2 means "recoverer spawn required". Both are valid
    classifier outputs that the tests assert on.
    """
    proc = subprocess.run(
        [
            sys.executable, str(_MONITOR),
            "--cwd", str(tmp),
            "tick", "--include-stale",
        ],
        capture_output=True, text=True,
    )
    out = proc.stdout
    lines = out.splitlines()
    json_start = None
    for i, line in enumerate(lines):
        if line.strip() == "{":
            json_start = i
            break
    if json_start is None:
        raise RuntimeError(
            f"No JSON block in tick output (rc={proc.returncode}):\n"
            f"--- stdout ---\n{out}\n--- stderr ---\n{proc.stderr}"
        )
    return json.loads("\n".join(lines[json_start:]))


def _state_for(branch, payload):
    for s in payload.get("states", []):
        if s["branch"] == branch:
            return s
    raise AssertionError(
        f"branch {branch!r} not in tick payload; "
        f"got {[s['branch'] for s in payload.get('states', [])]}"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRecovererLogic(unittest.TestCase):
    """End-to-end simulator tests for the recoverer role's liveness cases."""

    def test_dead_progress_branch_triggers_recoverer(self):
        """Progress artifact past dead SLA -> recoverer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _init_repo(tmp)
            _branch_with_artifact(
                tmp, "feat/dead-progress_59305d5",
                artifact_type="progress", age_min=30,
            )
            payload = _run_tick(tmp)
            state = _state_for("feat/dead-progress_59305d5", payload)
            self.assertEqual(state["classification"], "dead")
            self.assertEqual(state["recommended_action"], "recover")

    def test_final_without_handoff_triggers_integrate_now(self):
        """Final commit past handoff-pending window -> integrate-now.

        This is the silent-stuck repro: the durable commit landed but
        `complete_node` never arrived. The classifier must surface
        `integrate-now` so root merges from the commit anyway.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _init_repo(tmp)
            _branch_with_artifact(
                tmp, "feat/final-no-handoff_59305d5",
                artifact_type="final", age_min=5,
            )
            payload = _run_tick(tmp)
            state = _state_for("feat/final-no-handoff_59305d5", payload)
            # 5m is past handoff-pending window (default 1m) and within
            # the quiet window (default 5m). Classification is `quiet`
            # but action is `integrate-now`.
            self.assertEqual(state["recommended_action"], "integrate-now")

    def test_no_commits_branch_triggers_recoverer(self):
        """Empty branch (ref only) -> recoverer.

        Backdates the base commit to 60 min ago so the branch tip (which
        points at the base commit with no extra work) reads as past the
        dead SLA. The classifier then classifies this as `dead` with
        `recover` action — the recoverer spawn trigger.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _init_repo(tmp, base_age_min=60)
            _empty_branch(tmp, "feat/empty_59305d5")
            payload = _run_tick(tmp)
            state = _state_for("feat/empty_59305d5", payload)
            self.assertEqual(state["classification"], "dead")
            self.assertEqual(state["recommended_action"], "recover")

    def test_abandoned_worker_with_partial_progress(self):
        """Two commits: progress 20m ago, plain (no artifact) 15m ago.

        The classifier sees the *latest* commit (15m, no artifact). The
        action must NOT be `observe` because the worker is clearly not
        fresh-allocated. It should be `recover` (silent SLA) or
        `investigate` (quiet window) depending on threshold edge cases.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _init_repo(tmp)
            branch = "feat/abandoned_59305d5"
            _branch_with_artifact(tmp, branch, "progress", 20)
            _append_plain_commit(tmp, branch, 15)
            payload = _run_tick(tmp)
            state = _state_for(branch, payload)
            self.assertNotEqual(state["recommended_action"], "observe")
            self.assertIn(
                state["recommended_action"], ("recover", "investigate"),
            )

    def test_recoverer_spawn_threshold_consistent(self):
        """Mixed-batch tick returns the worst-action aggregate.

        Three branches:
          - healthy:  progress  1m   -> observe
          - mid:      progress 10m   -> dm-heartbeat-reminder
          - dead:     progress 45m   -> recover

        The aggregate `worst` action across all branches is `recover`
        (rank 2 in the action_rank scale). This is the threshold root
        uses to decide whether to spawn a recoverer worker.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _init_repo(tmp)
            _branch_with_artifact(
                tmp, "feat/healthy_59305d5", "progress", 1,
            )
            _branch_with_artifact(
                tmp, "feat/mid_59305d5", "progress", 10,
            )
            _branch_with_artifact(
                tmp, "feat/dead_59305d5", "progress", 45,
            )
            payload = _run_tick(tmp)
            states = payload["states"]
            self.assertEqual(len(states), 3)
            actions = [s["recommended_action"] for s in states]
            # The dead branch alone triggers recover.
            self.assertIn("recover", actions)
            # Worst-action aggregate ordering (highest = worst):
            #   observe=0, dm-heartbeat-reminder=1, integrate-now=1,
            #   investigate=1, recover=2
            rank = {
                "observe": 0,
                "dm-heartbeat-reminder": 1,
                "integrate-now": 1,
                "investigate": 1,
                "recover": 2,
            }
            worst = max(rank[a] for a in actions)
            self.assertEqual(worst, rank["recover"])


if __name__ == "__main__":
    unittest.main(verbosity=2)