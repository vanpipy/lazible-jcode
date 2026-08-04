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
    python3 scripts/swarm-state-monitor.py tick --since=1
    python3 scripts/swarm-state-monitor.py tick --include-stale
    python3 scripts/swarm-state-monitor.py classify <branch>   # one branch
    python3 scripts/swarm-state-monitor.py list         # only branch names

Exit codes (tick only):

    0 = all branches have recommended_action == "observe" (nothing for root to do)
    1 = at least one branch needs root action: integrate-now / recover / investigate
    2 = at least one branch is silent/dead (recoverer spawn required)
    3 = git missing or not a repo

The `recommended_action` column on the table tells root exactly what to do:

    observe                 → wait briefly, handoff may still be in flight
    integrate-now           → final commit landed; root MUST integrate from commit
                              even if `complete_node` never arrived. This catches
                              the silent-stuck failure mode.
    dm-heartbeat-reminder   → cheap ping; worker probably fine
    recover                 → silent/dead; spawn a recoverer worker
    investigate             → commit without artifact; check what worker is doing

Time deltas use the local timezone. The script reads `git log` via
subprocess; if git is missing, it exits 3.

Thresholds (env-overridable):
    POSTMAN_QUIET_MIN      (default 5)  — progress heartbeat SLA
    POSTMAN_SILENT_MIN      (default 15) — progress silent SLA
    POSTMAN_DEAD_MIN        (default 30) — progress dead SLA
    HANDOFF_PENDING_MIN     (default 1)  — `final` commit handoff-pending window;
                                           past this window, action = integrate-now

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

#: Default age window for tick output, in hours. Branches whose latest
#: commit is older than this are hidden unless --include-stale is passed.
DEFAULT_SINCE_HOURS = 24

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
    artifact_branch: Optional[str] = None  # `branch` field in artifact (for stale cross-check)
    artifact_step: Optional[str] = None
    artifact_next: Optional[str] = None
    artifact_confidence: Optional[str] = None
    classification: Optional[str] = None  # healthy/progressing/quiet/silent/dead
    rationale: str = ""
    # Recommended root action — what root should *do* about this branch.
    # Distinct from `classification` (which describes state). Possible values:
    #   observe                 — fresh commit, handoff may still be in flight
    #   integrate-now           — final commit landed; root should integrate
    #                            from the commit even if no handoff arrived
    #                            (this catches the silent-stuck failure mode
    #                            where worker died between commit and
    #                            complete_node, OR used `report` instead of
    #                            `complete_node`)
    #   dm-heartbeat-reminder   — progress commit in quiet window; cheap ping
    #   recover                 — silent/dead or no commits; spawn recoverer
    #   investigate             — commit without artifact; check what worker
    #                            was doing
    recommended_action: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "branch": self.branch,
            "has_commits": self.has_commits,
            "latest_commit": self.latest_commit,
            "latest_age_min": self.latest_age_min,
            "artifact_type": self.artifact_type,
            "artifact_branch": self.artifact_branch,
            "artifact_step": self.artifact_step,
            "artifact_next": self.artifact_next,
            "artifact_confidence": self.artifact_confidence,
            "classification": self.classification,
            "rationale": self.rationale,
            "recommended_action": self.recommended_action,
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
    """Populate state.classification, state.rationale, and state.recommended_action.

    The recommended_action field encodes what root should *do* about this
    branch, separately from the state-classification. Specifically: a `final`
    artifact past the handoff-pending window (default ~1 min) ALWAYS triggers
    `integrate-now`, even when the classification is `healthy`. This catches
    the silent-stuck failure mode where a worker commits `final` but never
    invokes `complete_node` (or uses `report status: ready`, which doesn't
    wake root). Without the action field, root was treating `healthy` as
    "nothing to do" and missing the integrate window entirely.
    """
    if not state.has_commits or age_min is None:
        state.classification = "dead"
        state.rationale = "no commits on branch"
        state.recommended_action = "recover"
        return

    artifact_type = state.artifact_type
    silent_threshold = THRESHOLDS["silent_min"]
    dead_threshold = THRESHOLDS["dead_min"]
    quiet_threshold = THRESHOLDS["quiet_min"]
    # `handoff_pending_window` is the window in which we tolerate a missing
    # `complete_node` handoff for a `final` commit. Past this window, the
    # commit is durable and root should integrate even without handoff.
    handoff_pending_window = int(
        __import__("os").environ.get("HANDOFF_PENDING_MIN", "1")
    )

    if artifact_type == "final":
        # Inside the handoff-pending window: handoff may still be in flight.
        if age_min <= handoff_pending_window:
            state.classification = "healthy"
            state.rationale = (
                f"final commit {age_min}m ago, within handoff-pending window"
            )
            state.recommended_action = "observe"
        elif age_min <= quiet_threshold:
            state.classification = "quiet"
            state.rationale = (
                f"final commit {age_min}m ago, no handoff observed; "
                f"root must integrate from commit (worker may have died "
                f"between commit and complete_node, or used `report` "
                f"instead of `complete_node`)"
            )
            state.recommended_action = "integrate-now"
        elif age_min <= silent_threshold:
            state.classification = "quiet"
            state.rationale = (
                f"final commit {age_min}m ago, no handoff observed"
            )
            state.recommended_action = "integrate-now"
        else:
            state.classification = "silent"
            state.rationale = (
                f"final commit {age_min}m ago, no handoff, past silent SLA"
            )
            state.recommended_action = "integrate-now"
        return

    if artifact_type == "progress":
        if age_min >= dead_threshold:
            state.classification = "dead"
            state.rationale = (
                f"progress commit {age_min}m ago, past dead SLA"
            )
            state.recommended_action = "recover"
        elif age_min >= silent_threshold:
            state.classification = "silent"
            state.rationale = (
                f"progress commit {age_min}m ago, past silent SLA"
            )
            state.recommended_action = "recover"
        elif age_min >= quiet_threshold:
            state.classification = "quiet"
            state.rationale = (
                f"progress commit {age_min}m ago, within quiet window"
            )
            state.recommended_action = "dm-heartbeat-reminder"
        else:
            state.classification = "progressing"
            state.rationale = (
                f"progress commit {age_min}m ago, within heartbeat SLA"
            )
            state.recommended_action = "observe"
        return

    # No artifact in the commit body. The tip either has no artifact
    # block (worker forgot to add one), or carries an artifact from a
    # *different* branch's worker (stale — see collect_state's branch
    # cross-check). Stale artifacts are expected right after `alloc`:
    # the branch tip is the base commit, which carries a previous
    # worker's artifact until this branch's worker commits. That's
    # `observe`, not `investigate`. A truly missing artifact (worker
    # forgot the block) is `investigate`.
    if state.artifact_branch:
        # Stale artifact from a different branch's worker. Expected
        # state right after alloc.
        if age_min >= dead_threshold:
            state.classification = "dead"
            state.rationale = (
                f"commit {age_min}m ago without artifact, past dead SLA "
                f"(stale artifact from another branch: "
                f"{state.artifact_branch!r})"
            )
            state.recommended_action = "recover"
        else:
            state.classification = "quiet"
            state.rationale = (
                f"branch tip is base commit (stale artifact from "
                f"{state.artifact_branch!r}); waiting for worker to commit"
            )
            state.recommended_action = "observe"
        return

    # Truly missing artifact — worker forgot the block, or this branch
    # has a non-worker-style commit. Treat as investigate.
    if age_min >= dead_threshold:
        state.classification = "dead"
        state.rationale = (
            f"commit {age_min}m ago without artifact, past dead SLA"
        )
        state.recommended_action = "recover"
    elif age_min >= silent_threshold:
        state.classification = "silent"
        state.rationale = (
            f"commit {age_min}m ago without artifact, past silent SLA"
        )
        state.recommended_action = "recover"
    elif age_min >= quiet_threshold:
        state.classification = "quiet"
        state.rationale = (
            f"commit {age_min}m ago without artifact, within quiet window"
        )
        state.recommended_action = "investigate"
    else:
        state.classification = "quiet"
        state.rationale = (
            f"commit {age_min}m ago without artifact, within heartbeat SLA"
        )
        state.recommended_action = "investigate"


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
    state.artifact_step = artifact.get("step")
    state.artifact_next = artifact.get("next")
    state.artifact_confidence = artifact.get("confidence")
    artifact_branch = artifact.get("branch")
    state.artifact_branch = artifact_branch

    # Cross-check: only trust the artifact if its `branch` field matches
    # the current branch. A fresh branch's tip is the base commit, which
    # may carry an artifact from a *different* branch's worker — that's
    # stale and must not trigger integrate-now / silent-stuck handling.
    # Without this guard, every newly-allocated worker branch looked like
    # it had a stale `final` artifact (with handoff overdue) until the
    # worker actually committed.
    if artifact_branch and artifact_branch != branch:
        state.artifact_type = None
    else:
        state.artifact_type = artifact.get("type")
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


def _format_table(states: list[BranchState], filter_rationale: str = "") -> str:
    if not states:
        return "(no worker branches found)"
    header = (
        f"{'branch':<48}  {'class':<13}  {'age':>5}  "
        f"{'artifact':<10}  {'conf':<8}  {'action':<22}  rationale"
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
        action = s.recommended_action or "?"
        rationale = s.rationale
        if filter_rationale:
            rationale = f"{rationale}; {filter_rationale}"
        lines.append(
            f"{branch:<48}  {cls:<13}  {age:>5}  "
            f"{artifact:<10}  {conf:<8}  {action:<22}  {rationale}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Age filter
# ---------------------------------------------------------------------------


def _apply_age_filter(
    states: list[BranchState],
    *,
    since_hours: float,
    include_stale: bool,
) -> tuple[list[BranchState], str, int]:
    """Apply the ``--since`` / ``--include-stale`` policy to ``states``.

    Returns ``(visible, rationale, hidden_count)``. Branches without a known
    commit age (``latest_age_min is None``) are always kept so that operators
    see them rather than silently dropping them.
    """
    if include_stale:
        return list(states), "--include-stale enabled", 0
    cutoff_min = since_hours * 60
    visible = [
        state for state in states
        if state.latest_age_min is None or state.latest_age_min <= cutoff_min
    ]
    hidden = len(states) - len(visible)
    return visible, f"within --since={since_hours:g}h filter", hidden


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_tick(
    cwd: Path,
    since_hours: float = DEFAULT_SINCE_HOURS,
    include_stale: bool = False,
) -> int:
    branches = _list_worker_branches(cwd)
    if not branches:
        print("(no worker branches found)")
        return 0
    all_states = [collect_state(b, cwd) for b in branches]
    states, filter_rationale, hidden_count = _apply_age_filter(
        all_states,
        since_hours=since_hours,
        include_stale=include_stale,
    )

    # Three-way output:
    #   (a) nothing at all           -> "no worker branches found"
    #   (b) all filtered by --since  -> "(N worker branch(es) hidden by
    #                                    --since=H filter; pass --include-stale)"
    #   (c) some visible, some hidden-> table + "(N worker branch(es) hidden;
    #                                    pass --include-stale)" note
    # Avoid (b) printing "(no worker branches found)" — that's misleading
    # when branches actually exist but were filtered out.
    if not states and hidden_count:
        print(
            f"({hidden_count} worker branch(es) hidden by "
            f"--since={since_hours:g}h filter; pass --include-stale to show all)"
        )
        return 0

    print(_format_table(states, filter_rationale))
    if hidden_count:
        # Same wording as case (b) minus the "--since=H filter" clause,
        # which is already implied by the table's filter_rationale column
        # on every visible row above.
        print(
            f"({hidden_count} worker branch(es) hidden; "
            "pass --include-stale to show all)"
        )
    print()
    print(json.dumps(
        {"states": [s.to_dict() for s in states]},
        indent=2,
        ensure_ascii=False,
    ))
    # Exit code: based on worst recommended_action, not worst classification.
    # This makes the exit code itself a gate that scripts/root-tick.sh can
    # use to decide whether root should pause and act.
    #
    #   0 = observe only — safe to integrate / spawn without further action
    #   1 = root must DO something (integrate-now / investigate /
    #       dm-heartbeat-reminder) but no recoverer spawn required
    #   2 = at least one branch is silent/dead/no-commits — spawn recoverer
    #   3 = git missing / not a repo (early-exit before this line)
    action_rank = {
        "observe": 0,
        "dm-heartbeat-reminder": 1,
        "integrate-now": 1,
        "investigate": 1,
        "recover": 2,
    }
    worst = max(
        (action_rank.get(s.recommended_action or "observe", 0) for s in states),
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

    p_tick = sub.add_parser(
        "tick",
        help="classify recent worker branches and emit a table",
    )
    p_tick.add_argument(
        "--since",
        type=float,
        default=DEFAULT_SINCE_HOURS,
        metavar="HOURS",
        help="hide branches older than HOURS (default: 24)",
    )
    p_tick.add_argument(
        "--include-stale",
        action="store_true",
        help="show all branches regardless of age",
    )
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
        return cmd_tick(
            cwd,
            since_hours=args.since,
            include_stale=args.include_stale,
        )
    if args.cmd == "classify":
        return cmd_classify(args.branch, cwd)
    if args.cmd == "list":
        return cmd_list(cwd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
