#!/usr/bin/env python3
"""
swarm-state-monitor.py

One-shot Smart Postman tick helper. Root calls this from the main session
to:

  1. List active worker branches (by convention `feat/<name>_<short-sha>`,
     `fix/<name>_<short-sha>`, etc.) via `git for-each-ref`.
  2. For each branch, read the latest artifact block from `git log
     <branch> --format=%B` and classify it.
  3. Emit a structured table root can read in one prompt turn.

The script is **pure stdlib** and **read-only** — it never modifies the
working tree. The classification engine is intentionally simple: it reads
the latest commit's artifact `type` field and the commit's age, and
classifies into `healthy / progressing / quiet / silent / dead`. Root
turns that into chat messages, dm reminders, or recoverer spawns.

Usage:

    python3 scripts/swarm-state-monitor.py tick          # full active-branch table
    python3 scripts/swarm-state-monitor.py classify <branch>   # one branch
    python3 scripts/swarm-state-monitor.py list         # only branch names

Exit codes:

    0 = all branches healthy or progressing
    1 = at least one quiet (caution)
    2 = at least one silent or dead (root action required)

Time deltas use the local timezone. The script reads `git log` via
subprocess; if git is missing, it exits 3.

This is the MVP. Future versions may add:

  - Heartbeat-SLA per worker (loaded from .jcode/conflict-config.yaml).
  - Cross-worker dependency detection (parse artifact `open_questions[]`).
  - Auto-emit dm reminder artifacts (opt-in only).
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


#: Branch name patterns that indicate a worker branch (vs. main / develop).
#: By convention: feat/<name>_<short-sha>, fix/<name>_<short-sha>,
#: chore/<name>_<short-sha>, refactor/<name>_<short-sha>,
#: docs/<name>_<short-sha>, test/<name>_<short-sha>, hotfix/<name>_<short-sha>.
WORKER_BRANCH_PATTERNS = (
    "feat/", "fix/", "chore/", "refactor/", "docs/", "test/", "hotfix/",
)

#: Classification thresholds (minutes since latest commit).
#: These are tips-of-the-trade defaults; operators can override via env
#: variables POSTMAN_QUIET_MIN / POSTMAN_SILENT_MIN / POSTMAN_DEAD_MIN.
THRESHOLDS = {
    "quiet_min": int(__import__("os").environ.get("POSTMAN_QUIET_MIN", "5")),
    "silent_min": int(__import__("os").environ.get("POSTMAN_SILENT_MIN", "15")),
    "dead_min": int(__import__("os").environ.get("POSTMAN_DEAD_MIN", "30")),
}

#: Regex to extract the artifact JSON block from a commit body.
ARTIFACT_RE = re.compile(
    r"```json artifact\s*\n(\{.*?\})\n```",
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class BranchState:
    """One worker branch's classification result."""

    branch: str
    has_commits: bool = False
    latest_commit: Optional[str] = None
    latest_age_min: Optional[int] = None
    artifact_type: Optional[str] = None  # "progress" / "final" / None
    artifact_step: Optional[str] = None
    artifact_next: Optional[str] = None
    artifact_confidence: Optional[str] = None
    classification: Optional[str] = None  # healthy/progressing/quiet/silent/dead
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "branch": self.branch,
            "has_commits": self.has_commits,
            "latest_commit": self.latest_commit,
            "latest_age_min": self.latest_age_min,
            "artifact_type": self.artifact_type,
            "artifact_step": self.artifact_step,
            "artifact_next": self.artifact_next,
            "artifact_confidence": self.artifact_confidence,
            "classification": self.classification,
            "rationale": self.rationale,
        }


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    """Run git, return (returncode, stdout, stderr)."""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _ensure_git(cwd: Path) -> None:
    rc, _, err = _git(["rev-parse", "--git-dir"], cwd)
    if rc != 0:
        print(f"swarm-state-monitor: not a git repo: {err.strip()}", file=sys.stderr)
        sys.exit(3)


def _list_worker_branches(cwd: Path) -> list[str]:
    """List local branches matching worker conventions."""
    rc, out, err = _git([
        "for-each-ref",
        "--format=%(refname:short)",
        "refs/heads/",
    ], cwd)
    if rc != 0:
        print(f"swarm-state-monitor: git for-each-ref failed: {err.strip()}",
              file=sys.stderr)
        return []
    branches = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(line.startswith(p) for p in WORKER_BRANCH_PATTERNS):
            branches.append(line)
    return branches


def _commit_age_minutes(cwd: Path, branch: str) -> Optional[int]:
    """Return age of the latest commit on `branch` in minutes, or None
    if the branch has no commits."""
    rc, out, _ = _git([
        "log", "-1", "--format=%ct", branch,
    ], cwd)
    if rc != 0 or not out.strip():
        return None
    try:
        ts = int(out.strip())
    except ValueError:
        return None
    commit_dt = datetime.datetime.fromtimestamp(ts)
    now = datetime.datetime.now()
    delta = now - commit_dt
    return int(delta.total_seconds() // 60)


def _commit_sha(cwd: Path, branch: str) -> Optional[str]:
    rc, out, _ = _git([
        "log", "-1", "--format=%H", branch,
    ], cwd)
    if rc != 0 or not out.strip():
        return None
    return out.strip()


def _commit_body(cwd: Path, branch: str) -> str:
    rc, out, _ = _git([
        "log", "-1", "--format=%B", branch,
    ], cwd)
    if rc != 0:
        return ""
    return out


def _parse_artifact(body: str) -> dict:
    """Extract the JSON artifact block from a commit body."""
    if not body:
        return {}
    m = ARTIFACT_RE.search(body)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify(state: BranchState, age_min: Optional[int]) -> None:
    """Populate state.classification and state.rationale."""
    if not state.has_commits or age_min is None:
        state.classification = "dead"
        state.rationale = "no commits on branch"
        return

    artifact_type = state.artifact_type
    silent_threshold = THRESHOLDS["silent_min"]
    dead_threshold = THRESHOLDS["dead_min"]
    quiet_threshold = THRESHOLDS["quiet_min"]

    if artifact_type == "final":
        if age_min <= quiet_threshold:
            state.classification = "healthy"
            state.rationale = (
                f"final commit {age_min}m ago, within quiet window"
            )
        elif age_min <= silent_threshold:
            state.classification = "quiet"
            state.rationale = (
                f"final commit {age_min}m ago, no handoff observed"
            )
        else:
            state.classification = "silent"
            state.rationale = (
                f"final commit {age_min}m ago, no handoff, past silent SLA"
            )
        return

    if artifact_type == "progress":
        if age_min >= dead_threshold:
            state.classification = "dead"
            state.rationale = (
                f"progress commit {age_min}m ago, past dead SLA"
            )
        elif age_min >= silent_threshold:
            state.classification = "silent"
            state.rationale = (
                f"progress commit {age_min}m ago, past silent SLA"
            )
        elif age_min >= quiet_threshold:
            state.classification = "quiet"
            state.rationale = (
                f"progress commit {age_min}m ago, within quiet window"
            )
        else:
            state.classification = "progressing"
            state.rationale = (
                f"progress commit {age_min}m ago, within heartbeat SLA"
            )
        return

    # No artifact in the commit body.
    if age_min >= dead_threshold:
        state.classification = "dead"
        state.rationale = (
            f"commit {age_min}m ago without artifact, past dead SLA"
        )
    elif age_min >= silent_threshold:
        state.classification = "silent"
        state.rationale = (
            f"commit {age_min}m ago without artifact, past silent SLA"
        )
    else:
        state.classification = "quiet"
        state.rationale = (
            f"commit {age_min}m ago without artifact, within quiet window"
        )


def collect_state(branch: str, cwd: Path) -> BranchState:
    state = BranchState(branch=branch)
    state.latest_commit = _commit_sha(cwd, branch)
    if state.latest_commit is None:
        state.has_commits = False
        classify(state, None)
        return state
    state.has_commits = True
    age = _commit_age_minutes(cwd, branch)
    state.latest_age_min = age
    body = _commit_body(cwd, branch)
    artifact = _parse_artifact(body)
    state.artifact_type = artifact.get("type")
    state.artifact_step = artifact.get("step")
    state.artifact_next = artifact.get("next")
    state.artifact_confidence = artifact.get("confidence")
    classify(state, age)
    return state


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


CLASSIFICATION_RANK = {
    "healthy": 0,
    "progressing": 0,
    "quiet": 1,
    "silent": 2,
    "dead": 2,
}


def _format_table(states: list[BranchState]) -> str:
    if not states:
        return "(no worker branches found)"
    header = (
        f"{'branch':<48}  {'class':<13}  {'age':>5}  "
        f"{'artifact':<10}  {'conf':<8}  rationale"
    )
    lines = [header, "-" * len(header) * 2]
    for s in sorted(
        states,
        key=lambda x: (CLASSIFICATION_RANK.get(x.classification or "", 0),
                       -(x.latest_age_min or 0)),
        reverse=True,
    ):
        branch = s.branch[:48]
        cls = s.classification or "?"
        age = f"{s.latest_age_min}m" if s.latest_age_min is not None else "—"
        artifact = s.artifact_type or "—"
        conf = s.artifact_confidence or "—"
        rationale = s.rationale
        lines.append(
            f"{branch:<48}  {cls:<13}  {age:>5}  "
            f"{artifact:<10}  {conf:<8}  {rationale}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_tick(cwd: Path) -> int:
    branches = _list_worker_branches(cwd)
    if not branches:
        print("(no worker branches found)")
        return 0
    states = [collect_state(b, cwd) for b in branches]
    print(_format_table(states))
    print()
    print(json.dumps(
        {"states": [s.to_dict() for s in states]},
        indent=2,
        ensure_ascii=False,
    ))
    worst = max(
        (CLASSIFICATION_RANK.get(s.classification or "", 0) for s in states),
        default=0,
    )
    return worst


def cmd_classify(branch: str, cwd: Path) -> int:
    state = collect_state(branch, cwd)
    print(json.dumps(state.to_dict(), indent=2, ensure_ascii=False))
    return CLASSIFICATION_RANK.get(state.classification or "", 0)


def cmd_list(cwd: Path) -> int:
    branches = _list_worker_branches(cwd)
    for b in branches:
        print(b)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("tick", help="classify all worker branches and emit a table")
    p_classify = sub.add_parser("classify", help="classify a single branch")
    p_classify.add_argument("branch")
    sub.add_parser("list", help="list worker branch names only")

    parser.add_argument(
        "--cwd", default=".",
        help="git working directory (default: current dir)",
    )

    args = parser.parse_args()
    cwd = Path(args.cwd).resolve()
    _ensure_git(cwd)

    if args.cmd == "tick":
        return cmd_tick(cwd)
    if args.cmd == "classify":
        return cmd_classify(args.branch, cwd)
    if args.cmd == "list":
        return cmd_list(cwd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
