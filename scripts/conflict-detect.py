#!/usr/bin/env python3
"""Generic swarm conflict-detection framework.

Six detectors, each returning `list[Conflict]`:

    detect_scope_overlap(scopes)
    detect_lockfile_contention(scopes, config=None)
    detect_in_flight_overlap(planned, in_flight_branches, repo_root=".")
    detect_dirty_state(worktree_path)
    detect_manifest_corruption(manifest_path)
    detect_heartbeat_stale(entries, now=None)

The CLI wraps them:

    scripts/conflict-detect.py <command> [args]

Subcommands: scope-overlap, lockfile, in-flight, dirty, manifest, all.

Exit codes:
    0 = no conflicts
    1 = major (warning)
    2 = blocker (refuse to proceed)

Pure stdlib. Tested with `python3 -m unittest scripts.test_conflict_detect`.
"""

from __future__ import annotations

import argparse
import datetime
import fnmatch
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


#: Stable, documented severity vocabulary. Integer rank drives exit code.
SEVERITY_ORDER: dict[str, int] = {"info": 0, "major": 1, "blocker": 2}

#: Default high-contention lockfile set. Repos can extend via
#: `.jcode/conflict-config.yaml` -> `lockfile_files:`. Comments group by
#: ecosystem so operators can scan the list quickly.
DEFAULT_LOCKFILE_PATTERNS: list[str] = [
    # Node
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    # Rust
    "Cargo.toml", "Cargo.lock",
    # Python
    "pyproject.toml", "poetry.lock", "Pipfile.lock",
    "requirements.txt", "requirements-*.txt",
    # Go
    "go.mod", "go.sum",
    # Secrets — anyone touching these risks stomping another worker.
    ".env", ".env.*",
    # DB migrations are sequential by nature. Workers racing on migrations
    # produce schema drift.
    "migrations/*", "db/migrate/*", "prisma/migrations/*", "alembic/versions/*",
]

#: Default heartbeat TTL. Override via
#: `.jcode/conflict-config.yaml` -> `heartbeat_ttl_seconds:`.
DEFAULT_HEARTBEAT_TTL_SECONDS: int = 8 * 60 * 60  # 8 hours

#: Default severity escalation thresholds for `suggest_serialization`. When a
#: non-lockfile file is shared by `N` tasks, the emitted conflict's severity
#: escalates:
#:     N <  major          -> minor (parallel ok with rebase)
#:     major <= N < blocker -> major
#:     N >= blocker        -> blocker
#: Override via `.jcode/conflict-config.yaml` -> `severity_threshold_n:`.
DEFAULT_SEVERITY_THRESHOLD_N: dict[str, int] = {"major": 4, "blocker": 6}

#: Default cleanup patterns for `cleanup_worktree_artifacts`. A worktree's
#: uncommitted changes whose path matches one of these globs are deleted
#: rather than staged; everything else is staged with `git add`.
#: Override via `.jcode/conflict-config.yaml` -> `cleanup_patterns:`.
DEFAULT_CLEANUP_PATTERNS: list[str] = [
    "__pycache__/",
    "*.bak.*",
    "*.pyc",
    "*.tmp",
]

#: Closed set of `prefer_side` values accepted by `resolve_conflict_hunks`.
#: `intersection` = `git merge --union` style; keep both sides' hunks.
VALID_PREFER_SIDES: tuple[str, ...] = ("worker", "main", "newer", "intersection")

#: Manifest schema — every entry must have these keys.
_MANIFEST_REQUIRED_KEYS: tuple[str, ...] = (
    "wt_path", "branch", "pid", "started_at", "last_heartbeat",
)


@dataclass
class Conflict:
    """A single detected conflict.

    Fields:
        severity   — "info" | "major" | "blocker". Drives exit code.
        category   — stable machine-readable tag (e.g. "scope_overlap").
        summary    — one-line human description.
        evidence   — list[str] of file:line / branch / commit references.
        remediation — one-line actionable suggestion for the operator.
    """

    severity: str
    category: str
    summary: str
    evidence: list[str] = field(default_factory=list)
    remediation: str = ""


@dataclass
class CleanupAction:
    """One row of `cleanup_worktree_artifacts` output.

    Fields:
        path    — the repo-relative file or directory path.
        action  — "rm" (delete), "git_add" (stage), or "noop" (no
                  automated action; operator must inspect).
        command — runnable shell command, or "" when action == "noop".
        reason  — short string explaining why this action was chosen
                  (matched pattern name, "untracked", etc.).
    """

    path: str
    action: str
    command: str
    reason: str = ""


@dataclass
class MergeStrategy:
    """Output of `pick_merge_strategy`.

    Fields:
        strategy — one of:
            "fast-forward"     (base is ancestor of branch; FF is safe)
            "merge --no-ff"    (single branch diverged from base)
            "rebase-then-merge" (multiple parallel branches)
            "drop"             (empty input)
            "manual"           (git missing / cannot determine)
        reason   — human-readable explanation of why this strategy fits.
        commands — list of git commands the operator should run, in order.
    """

    strategy: str
    reason: str
    commands: list[str] = field(default_factory=list)


@dataclass
class BranchAncestry:
    """Output of `detect_branch_ancestry`.

    Fields:
        parents         — dict[branch -> parent_branch or None].
                          `parents[B] = A` means A is the immediate
                          ancestor of B in this branch set (when known).
        chains          — list of linear chains in topological order.
                          `chains[i]` is `[b0, b1, ...]` where
                          `b_i` is ancestor of `b_{i+1}`.
        already_merged  — list of branches whose tip is reachable from
                          `base` (no merge work needed).
        parallel_groups — list of branch sets sharing a merge-base but
                          with no ancestor relation to each other.
    """

    parents: dict[str, str | None]
    chains: list[list[str]]
    already_merged: list[str] = field(default_factory=list)
    parallel_groups: list[list[str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _severity_rank(c: Conflict) -> int:
    return SEVERITY_ORDER.get(c.severity, 0)


def _worst_severity(conflicts: list[Conflict]) -> str:
    """Return the highest-severity label in `conflicts`, or 'info' if empty."""
    if not conflicts:
        return "info"
    ranks = [_severity_rank(c) for c in conflicts]
    top = max(ranks)
    for label, rank in SEVERITY_ORDER.items():
        if rank == top:
            return label
    return "info"


def _exit_code_for(conflicts: list[Conflict]) -> int:
    """Translate a conflict list into a CLI exit code."""
    if not conflicts:
        return 0
    top = _worst_severity(conflicts)
    if top == "blocker":
        return 2
    if top == "major":
        return 1
    return 0


# ---------------------------------------------------------------------------
# Tiny YAML subset parser (stdlib has no yaml)
# ---------------------------------------------------------------------------


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse a tiny YAML subset sufficient for `.jcode/conflict-config.yaml`.

    Supports: `key: scalar`, `key:` followed by indented `- item` list,
    `key:` followed by indented nested mapping (`key: value` lines at deeper
    indent), `#` comments, quoted strings, ints, bools, null. Also accepts
    flow-style `{k: v, k: v}` for scalar-value dicts. Anything fancier
    (anchors, multi-line strings, mixed flow + block) is unsupported.
    """
    # Pass 1: collect (indent, text) for non-blank, non-comment lines.
    raw_lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        hash_idx = raw.find("#")
        if hash_idx >= 0:
            raw = raw[:hash_idx]
        stripped = raw.rstrip()
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        raw_lines.append((indent, stripped.lstrip(" ")))
    pos = [0]

    def parse_list(indent: int) -> list[Any]:
        items: list[Any] = []
        while pos[0] < len(raw_lines):
            cur_indent, cur_text = raw_lines[pos[0]]
            if cur_indent < indent:
                break
            if cur_indent > indent or not cur_text.startswith("- "):
                break
            items.append(_coerce(cur_text[2:].strip()))
            pos[0] += 1
        return items

    def parse_mapping(indent: int) -> dict[str, Any]:
        """Parse a block-style mapping at `indent` depth.

        Each key at the same indent may be:
          - `key: scalar`
          - `key:` followed by an indented list (`- item`)
          - `key:` followed by an indented nested mapping (`k: v` lines)
        The recursive call resumes from the deeper indent and consumes
        only that subtree.
        """
        out: dict[str, Any] = {}
        while pos[0] < len(raw_lines):
            cur_indent, cur_text = raw_lines[pos[0]]
            if cur_indent < indent:
                break
            if cur_indent > indent:
                # Should not happen at top-of-loop; defensive break.
                break
            if ":" not in cur_text:
                pos[0] += 1
                continue
            key, _, value = cur_text.partition(":")
            key = key.strip()
            value = value.strip()
            pos[0] += 1
            if value:
                out[key] = _coerce(value)
                continue
            # Value spans multiple lines: look ahead to decide list vs mapping.
            if pos[0] < len(raw_lines):
                next_indent, next_text = raw_lines[pos[0]]
                if next_indent > indent:
                    if next_text.startswith("- "):
                        out[key] = parse_list(next_indent)
                    else:
                        out[key] = parse_mapping(next_indent)
                else:
                    out[key] = None
            else:
                out[key] = None
        return out

    def parse_flow_dict(s: str) -> dict[str, Any]:
        """Parse a single-line `{k: v, k: v}` flow-style mapping.

        Supports only scalar values (int / bool / string). Used so that
        `severity_threshold_n: {major: 4, blocker: 6}` from the spec works.
        """
        s = s.strip()
        if s.startswith("{") and s.endswith("}"):
            s = s[1:-1]
        out: dict[str, Any] = {}
        for part in s.split(","):
            part = part.strip()
            if not part:
                continue
            if ":" not in part:
                continue
            k, _, v = part.partition(":")
            out[k.strip()] = _coerce(v.strip())
        return out

    result: dict[str, Any] = {}
    while pos[0] < len(raw_lines):
        indent, text = raw_lines[pos[0]]
        if indent != 0:
            break  # Caller passed non-root pos; bail.
        if ":" not in text:
            pos[0] += 1
            continue
        key, _, value = text.partition(":")
        key = key.strip()
        value = value.strip()
        pos[0] += 1
        if value:
            # Flow-style nested dict? e.g. `severity_threshold_n: {major: 4}`.
            if value.startswith("{"):
                result[key] = parse_flow_dict(value)
            else:
                result[key] = _coerce(value)
        else:
            # Look ahead: if next line starts with `- ` at deeper indent, list.
            if pos[0] < len(raw_lines):
                next_indent, next_text = raw_lines[pos[0]]
                if next_indent > indent and next_text.startswith("- "):
                    result[key] = parse_list(next_indent)
                elif next_indent > indent:
                    result[key] = parse_mapping(next_indent)
                else:
                    result[key] = None
            else:
                result[key] = None
    return result


def _coerce(value: str) -> Any:
    """Coerce a YAML scalar string to bool/int/null when obvious."""
    if value.lower() in ("true", "yes", "on"):
        return True
    if value.lower() in ("false", "no", "off"):
        return False
    if value.lower() in ("null", "~", ""):
        return None
    # Strip optional surrounding quotes.
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def load_config(path: str | os.PathLike[str] | None) -> dict[str, Any]:
    """Load a config YAML; return {} if path is None or the file is missing."""
    if not path:
        return {}
    p = os.fspath(path)
    if not os.path.isfile(p):
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return _parse_simple_yaml(f.read()) or {}


def _is_ignored(path: str, ignored_patterns: list[str]) -> bool:
    if not ignored_patterns:
        return False
    for pat in ignored_patterns:
        # fnmatch treats `*` as any-char. `**` collapses to `*` for the
        # typical glob semantics we need.
        normalised = pat.replace("**", "*")
        if fnmatch.fnmatch(path, normalised):
            return True
    return False


# ---------------------------------------------------------------------------
# Detector 1: scope overlap
# ---------------------------------------------------------------------------


def detect_scope_overlap(scopes: dict[str, list[str]]) -> list[Conflict]:
    """Flag any file touched by two or more workers.

    A `scope` is `{worker_label: [files...]}` where files are repo-relative
    paths. The detector returns one Conflict per *file* that overlaps, with
    the contributing workers in `evidence`.
    """
    by_file: dict[str, list[str]] = {}
    for worker, files in scopes.items():
        for f in files:
            by_file.setdefault(f, []).append(worker)

    conflicts: list[Conflict] = []
    for path, workers in sorted(by_file.items()):
        if len(workers) >= 2:
            unique = sorted(set(workers))
            evidence = [f"{w}: {path}" for w in unique]
            conflicts.append(
                Conflict(
                    severity="blocker",
                    category="scope_overlap",
                    summary=(
                        f"file '{path}' is in the scope of "
                        f"{len(unique)} workers: {', '.join(unique)}"
                    ),
                    evidence=evidence,
                    remediation=(
                        "serialize the workers (have one finish before the "
                        "other starts) or split the file's ownership"
                    ),
                )
            )
    return conflicts


# ---------------------------------------------------------------------------
# Detector 2: lockfile contention
# ---------------------------------------------------------------------------


def _matches_lockfile(path: str, patterns: Iterable[str]) -> bool:
    """True if `path` matches any pattern in the lockfile set.

    Patterns are glob-shaped (e.g. `requirements-*.txt`, `migrations/*`,
    `.env.*`). The match is fnmatch-based; bare names also do exact match
    so `package.json` doesn't accidentally match `not-package.json`.
    """
    for pat in patterns:
        normalised = pat.replace("**", "*")
        if fnmatch.fnmatch(path, normalised):
            return True
        # Exact basename match for the common case (no wildcards).
        if "/" not in pat and pat == path:
            return True
    return False


def detect_lockfile_contention(
    scopes: dict[str, list[str]],
    config: dict[str, Any] | None = None,
) -> list[Conflict]:
    """Flag any scope entry touching a high-contention lockfile/migration."""
    cfg = config or {}
    patterns = list(DEFAULT_LOCKFILE_PATTERNS)
    extras = cfg.get("lockfile_files") or []
    if isinstance(extras, list):
        patterns.extend(str(x) for x in extras)
    ignored = cfg.get("ignored_paths") or []
    if not isinstance(ignored, list):
        ignored = []

    conflicts: list[Conflict] = []
    for worker, files in scopes.items():
        for f in files:
            if _is_ignored(f, ignored):
                continue
            if _matches_lockfile(f, patterns):
                conflicts.append(
                    Conflict(
                        severity="major",
                        category="lockfile_contention",
                        summary=(
                            f"worker '{worker}' touches high-contention "
                            f"file '{f}'"
                        ),
                        evidence=[f"{worker}: {f}"],
                        remediation=(
                            "rotate the lockfile owner per-merge (e.g. "
                            "dependabot) or serialize this worker"
                        ),
                    )
                )
    return conflicts


# ---------------------------------------------------------------------------
# Detector 3: in-flight overlap
# ---------------------------------------------------------------------------


def _run_git(repo_root: str, *args: str) -> str:
    """Run `git -C <root> <args>...` and return stdout ('' if git missing)."""
    if shutil.which("git") is None:
        return ""
    proc = subprocess.run(
        ["git", "-C", repo_root, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout or ""


def detect_in_flight_overlap(
    planned: list[str],
    in_flight_branches: list[str],
    repo_root: str = ".",
) -> list[Conflict]:
    """Flag files that overlap between `planned` and any in-flight branch.

    For each branch, runs `git diff main..<branch> --name-only` (with a few
    fallback base refs) and intersects with `planned`. Any intersection is
    a `blocker`: the planned worker would collide with in-flight changes.
    """
    planned_set = {p for p in planned if p}
    if not planned_set or not in_flight_branches:
        return []

    conflicts: list[Conflict] = []
    # Try `main` first, then `master`, then `HEAD`'s parent.
    base_candidates = ("main", "master", "HEAD")

    for branch in in_flight_branches:
        changed: set[str] = set()
        for base in base_candidates:
            diff_out = _run_git(
                repo_root, "diff", f"{base}..{branch}", "--name-only"
            )
            if diff_out.strip():
                changed = {line.strip() for line in diff_out.splitlines() if line.strip()}
                break
        # If no diff produced any output, fall back to the branch's own tree.
        if not changed:
            ls_out = _run_git(repo_root, "ls-tree", "-r", "--name-only", branch)
            changed = {line.strip() for line in ls_out.splitlines() if line.strip()}

        overlap = sorted(planned_set & changed)
        if overlap:
            evidence = [f"{branch}: {p}" for p in overlap]
            conflicts.append(
                Conflict(
                    severity="blocker",
                    category="in_flight_overlap",
                    summary=(
                        f"branch '{branch}' already touches {len(overlap)} "
                        f"planned file(s)"
                    ),
                    evidence=evidence,
                    remediation=(
                        "merge the in-flight branch and rebase the planned "
                        "worker, or split the planned scope"
                    ),
                )
            )
    return conflicts


# ---------------------------------------------------------------------------
# Detector 4: dirty state
# ---------------------------------------------------------------------------


def detect_dirty_state(worktree_path: str) -> list[Conflict]:
    """Flag a worktree whose `git status --porcelain` is non-empty."""
    if shutil.which("git") is None:
        return []
    proc = subprocess.run(
        ["git", "-C", worktree_path, "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    out = (proc.stdout or "").strip()
    if not out:
        return []
    evidence = [line for line in out.splitlines() if line.strip()]
    return [
        Conflict(
            severity="blocker",
            category="dirty_state",
            summary=(
                f"worktree '{worktree_path}' has {len(evidence)} "
                f"uncommitted change(s)"
            ),
            evidence=evidence,
            remediation=(
                "commit or stash the changes before the worker resumes; "
                "the swarm manifest's git ops assume a clean tree"
            ),
        )
    ]


# ---------------------------------------------------------------------------
# R19 gap 7: cleanup_worktree_artifacts — promote dirty_state to actions.
# Takes the porcelain rows from `git status --porcelain` and maps each one
# to a runnable command. Used by the swarm operator to fix dirty worktrees
# before a worker resumes.
# ---------------------------------------------------------------------------


def _parse_porcelain_row(row: str) -> tuple[str, str] | None:
    """Extract (status_code, path) from one porcelain row.

    `git status --porcelain` emits rows like:
        " M file.py"
        "?? new.py"
        "R  old.py -> new.py"
        "A  staged.py"

    Returns None when the row doesn't have at least a 2-char status code
    plus a space plus a path (or the row is blank).
    """
    if not row or len(row) < 4:
        return None
    code = row[:2]
    rest = row[3:].strip()
    if not rest:
        return None
    # Renames are reported as `old -> new`; we only need the new path.
    if " -> " in rest:
        rest = rest.split(" -> ", 1)[1].strip()
    return (code, rest)


def _classify_porcelain_code(code: str) -> str:
    """Map a porcelain status code to a coarse action category.

    Returns one of: "already_staged", "deleted", "conflict",
    "untracked", "ignored", "modified".
    """
    x = code[0]  # staged status
    y = code[1]  # unstaged status
    if code == "??":
        return "untracked"
    if code == "!!":
        return "ignored"
    if y == "D" or x == "D":
        return "deleted"
    if y == "U" or x == "U" or (x == "A" and y == "A") or (x == "D" and y == "D"):
        return "conflict"
    if x != " " and x != "?":
        # Staged change (M, A, R, C, T). The path is already in the
        # index; commit is the operator's job, not cleanup's.
        return "already_staged"
    return "modified"


def cleanup_worktree_artifacts(
    dirty_paths: list[str],
    patterns: list[str] | None = None,
) -> list[CleanupAction]:
    """Map porcelain rows to runnable cleanup commands.

    For each row:
      - Match path against `patterns` (defaults to `DEFAULT_CLEANUP_PATTERNS`).
        Matched paths emit `rm -f <path>` (file) or `rm -rf <path>` (pattern
        ends with `/`).
      - Otherwise classify the porcelain status code:
          untracked  -> "git add <path>" (operator can then commit or revert)
          modified   -> "git add <path>"
          deleted    -> "git add <path>" (stages the deletion)
          conflict   -> noop (operator must resolve)
          ignored    -> dropped (returns empty for that row)
          already_staged -> noop (operator already ran `git add`)

    Args:
        dirty_paths — raw porcelain rows from `git status --porcelain`.
        patterns    — glob patterns to delete. Defaults to
                      `DEFAULT_CLEANUP_PATTERNS`.

    Returns:
        list[CleanupAction] in input order. Rows that fail to parse or are
        marked `!!` (ignored) are not returned.
    """
    pats = list(DEFAULT_CLEANUP_PATTERNS if patterns is None else patterns)

    actions: list[CleanupAction] = []
    for row in dirty_paths:
        parsed = _parse_porcelain_row(row)
        if not parsed:
            actions.append(
                CleanupAction(
                    path="",
                    action="noop",
                    command="",
                    reason=f"unparseable porcelain row: {row!r}",
                )
            )
            continue
        code, path = parsed

        # Ignored files: drop them entirely.
        if code == "!!":
            continue

        # Pattern match: delete regardless of porcelain code.
        matched_pattern: str | None = None
        for pat in pats:
            # Patterns ending with `/` are directory prefixes. Match by
            # prefix so `build/` cleans anything under `build/`.
            if pat.endswith("/"):
                if path.startswith(pat) or path.rstrip("/") == pat.rstrip("/"):
                    matched_pattern = pat
                    break
                continue
            normalised = pat.replace("**", "*")
            if fnmatch.fnmatch(path, normalised):
                matched_pattern = pat
                break
        if matched_pattern is not None:
            is_dir = matched_pattern.endswith("/") or path.endswith("/")
            cmd = (
                f"rm -rf {path}"
                if is_dir
                else f"rm -f {path}"
            )
            actions.append(
                CleanupAction(
                    path=path,
                    action="rm",
                    command=cmd,
                    reason=f"matches cleanup_pattern: {matched_pattern}",
                )
            )
            continue

        category = _classify_porcelain_code(code)
        if category == "ignored":
            continue  # defensive; should not happen after the !! guard above
        if category in ("already_staged", "conflict"):
            actions.append(
                CleanupAction(
                    path=path,
                    action="noop",
                    command="",
                    reason=(
                        "already staged; commit instead"
                        if category == "already_staged"
                        else "merge conflict; resolve manually"
                    ),
                )
            )
            continue

        # Everything else (modified / untracked / deleted): git add the path.
        actions.append(
            CleanupAction(
                path=path,
                action="git_add",
                command=f"git add {path}",
                reason=f"{category}: stage before commit",
            )
        )
    return actions


# ---------------------------------------------------------------------------
# R19 gap 6: pick_merge_strategy — choose FF / --no-ff / rebase-then-merge
# ---------------------------------------------------------------------------


def _is_ancestor(repo_root: str, ancestor: str, descendant: str) -> bool:
    """True iff `ancestor` is a git ancestor of `descendant`.

    Uses `git merge-base --is-ancestor`. Returns False when git is missing
    or the call fails (which is the safe default: an unverifiable claim of
    ancestry must not produce a fast-forward recommendation).
    """
    if shutil.which("git") is None:
        return False
    proc = subprocess.run(
        [
            "git",
            "-C",
            repo_root,
            "merge-base",
            "--is-ancestor",
            ancestor,
            descendant,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def pick_merge_strategy(
    branches: list[str],
    base: str,
    repo_root: str,
) -> MergeStrategy:
    """Pick the cheapest safe merge strategy for `branches` against `base`.

    Decision tree:
      - no branches                        -> drop
      - git missing                        -> manual
      - single branch:
          - base is ancestor of branch     -> fast-forward
          - else                           -> merge --no-ff
      - multiple branches:
          - all form a chain (each pair
            ancestor-descendant OR same)   -> fast-forward (chain order)
          - any two branches are parallel  -> rebase-then-merge
            (rebase each onto base first;
            merge with --no-ff)

    Args:
        branches  — list of branch names to bring into `base`.
        base      — the target branch (usually "main").
        repo_root — filesystem path for git commands.

    Returns:
        MergeStrategy with the chosen strategy name, reason, and the
        exact git commands the operator should run.
    """
    if not branches:
        return MergeStrategy(
            strategy="drop",
            reason="no branches to merge",
            commands=[],
        )

    if shutil.which("git") is None:
        return MergeStrategy(
            strategy="manual",
            reason="git binary not available on PATH",
            commands=[],
        )

    # Single-branch path is straightforward.
    if len(branches) == 1:
        branch = branches[0]
        if _is_ancestor(repo_root, base, branch):
            return MergeStrategy(
                strategy="fast-forward",
                reason=(
                    f"{base!r} is an ancestor of {branch!r}; "
                    f"fast-forward is safe"
                ),
                commands=[f"git merge --ff-only {branch}"],
            )
        return MergeStrategy(
            strategy="merge --no-ff",
            reason=(
                f"{branch!r} diverged from {base!r}; "
                f"fast-forward is not possible, use --no-ff"
            ),
            commands=[f"git merge --no-ff {branch}"],
        )

    # Multi-branch path: check pairwise ancestry.
    all_ff = all(_is_ancestor(repo_root, base, b) for b in branches)
    chain_ok = True
    # Sort by lex to get a deterministic chain order; verify each is
    # ancestor of the next.
    chain = sorted(branches)
    for i in range(len(chain) - 1):
        if not _is_ancestor(repo_root, chain[i], chain[i + 1]):
            chain_ok = False
            break
    if all_ff and chain_ok:
        return MergeStrategy(
            strategy="fast-forward",
            reason=(
                f"branches form a chain above {base!r}: "
                f"{' -> '.join([base, *chain])}; fast-forward is safe"
            ),
            commands=[f"git merge --ff-only {chain[-1]}"],
        )

    # Parallel branches: rebase each onto base, then merge with --no-ff.
    cmds: list[str] = []
    for b in chain:
        cmds.append(f"git rebase {base} {b}")
    cmds.append(f"git merge --no-ff {' '.join(chain)}")
    return MergeStrategy(
        strategy="rebase-then-merge",
        reason=(
            f"branches {branches} are parallel above {base!r}; "
            f"rebase each onto {base!r} before merging"
        ),
        commands=cmds,
    )


# ---------------------------------------------------------------------------
# R19 gap 2: detect_branch_ancestry — classify branches by ancestry graph
# ---------------------------------------------------------------------------


def detect_branch_ancestry(
    branches: list[str],
    base: str,
    repo_root: str,
) -> BranchAncestry:
    """Classify `branches` by their git ancestry relations.

    Builds a partial-order graph using `git merge-base --is-ancestor`:
        - If branch A is an ancestor of branch B (and B is in the set),
          `parents[B] = A`. The chain ends at the leaf.
        - If multiple branches share `base` as a common ancestor but no
          pair has an ancestor relation, they form a parallel group.
        - Branches whose tip is reachable from `base` go into
          `already_merged`.

    Falls back gracefully when git is missing or returns errors: every
    branch becomes its own chain.

    Args:
        branches  — list of branch names to classify.
        base      — the target branch (e.g. "main").
        repo_root — filesystem path for git commands.

    Returns:
        BranchAncestry with parents map, chains, already_merged, and
        parallel_groups.
    """
    if not branches:
        return BranchAncestry(parents={}, chains=[], already_merged=[], parallel_groups=[])

    if shutil.which("git") is None:
        return BranchAncestry(
            parents={b: None for b in branches},
            chains=[[b] for b in sorted(branches)],
            already_merged=[],
            parallel_groups=[],
        )

    # Step 1: compute already_merged (branch is ancestor of base).
    already_merged: list[str] = []
    live: list[str] = []
    for b in branches:
        if _is_ancestor(repo_root, b, base):
            already_merged.append(b)
        else:
            live.append(b)

    # Step 2: build ancestry edges among live branches.
    # `direct_ancestor[B]` = the live branch A such that A is ancestor of B
    # and no other live branch sits between them (the most-specific / leafward
    # ancestor). This yields linear chains: B -> A -> A's parent.
    direct_ancestor: dict[str, str | None] = {b: None for b in live}
    for b in live:
        candidates: list[str] = []
        for a in live:
            if a == b:
                continue
            if _is_ancestor(repo_root, a, b):
                candidates.append(a)
        if candidates:
            # Most-specific = no other candidate is a descendant of it.
            def is_leafward(c: str) -> bool:
                return all(
                    c == other or not _is_ancestor(repo_root, c, other)
                    for other in candidates
                )
            leafward = [c for c in candidates if is_leafward(c)]
            direct_ancestor[b] = sorted(leafward)[0]

    # Step 3: build chains by walking parent links.
    chains: list[list[str]] = []
    visited: set[str] = set()
    roots = [b for b in live if direct_ancestor[b] is None]
    roots.sort()
    for root in roots:
        chain = [root]
        visited.add(root)
        cur: str | None = direct_ancestor.get(root)
        # Walk UPSTREAM rather than downstream — direct_ancestor points
        # from descendant to its immediate ancestor, so we need to invert
        # the walk.
        # Build the inverse map first.
        # children[parent] = list of children
        children: dict[str, list[str]] = {b: [] for b in live}
        for child, parent in direct_ancestor.items():
            if parent is not None and parent in children:
                children[parent].append(child)
        # Walk down from root.
        cur = root
        while True:
            kids = sorted(children.get(cur, []))
            unvisited = [k for k in kids if k not in visited]
            if not unvisited:
                break
            nxt = unvisited[0]
            chain.append(nxt)
            visited.add(nxt)
            cur = nxt
        chains.append(chain)

    # Any live branch not visited yet (cycle or disconnected) -> its own chain.
    for b in live:
        if b not in visited:
            chains.append([b])
            visited.add(b)

    # Step 4: build parents map and parallel_groups.
    parents: dict[str, str | None] = {}
    parallel_groups: list[list[str]] = []
    children_map: dict[str | None, list[str]] = {}
    for b, p in direct_ancestor.items():
        parents[b] = p
        children_map.setdefault(p, []).append(b)
    for parent, kids in children_map.items():
        if parent is None and len(kids) >= 2:
            # Multiple live branches with no shared ancestor among the set —
            # they're parallel siblings.
            parallel_groups.append(sorted(kids))

    return BranchAncestry(
        parents=parents,
        chains=chains,
        already_merged=sorted(already_merged),
        parallel_groups=parallel_groups,
    )


# ---------------------------------------------------------------------------
# R19 gap 1: auto_extract_scope + plan_execution_order_from_branches
# ---------------------------------------------------------------------------


def auto_extract_scope(
    branches: list[str],
    repo_root: str,
    base: str = "main",
) -> dict[str, list[str]]:
    """Derive `{branch: [files...]}` from `git diff <base>..<branch>`.

    Used by `plan_execution_order_from_branches` to feed scope-file
    overlap into the existing planning algorithm without requiring the
    operator to hand-write a `tasks.json` file.

    Args:
        branches  — list of branch names to introspect.
        repo_root — filesystem path for git commands.
        base      — the comparison base (default: "main").

    Returns:
        dict mapping each branch to its sorted list of changed files.
        Returns `{b: []}` for each branch when git is missing or no diff
        exists, so downstream callers still see the branch.
    """
    if not branches:
        return {}
    if shutil.which("git") is None:
        return {b: [] for b in branches}

    scope: dict[str, list[str]] = {}
    for branch in branches:
        diff_out = _run_git(
            repo_root, "diff", f"{base}..{branch}", "--name-only"
        )
        files = [line.strip() for line in diff_out.splitlines() if line.strip()]
        scope[branch] = sorted(files)
    return scope


def plan_execution_order_from_branches(
    branches: list[str],
    base: str,
    repo_root: str,
) -> ExecutionPlan:
    """Build an ExecutionPlan directly from git branches.

    Combines `detect_branch_ancestry` (Gap 2) with `auto_extract_scope`
    (Gap 1) to feed scope-file overlap into the existing planner.

    Already-merged branches are dropped. The remaining branches form
    chains; within each chain, scope overlap drives phase assignment.

    Args:
        branches  — list of branch names.
        base      — target branch (default "main" upstream).
        repo_root — filesystem path for git commands.

    Returns:
        ExecutionPlan. Empty branches -> empty plan.
    """
    if not branches:
        return ExecutionPlan(phases=[], critical_path=[], parallel_batches=[])

    ancestry = detect_branch_ancestry(branches, base, repo_root)
    live_branches: list[str] = []
    for chain in ancestry.chains:
        live_branches.extend(chain)
    if not live_branches:
        return ExecutionPlan(phases=[], critical_path=[], parallel_batches=[])

    scope = auto_extract_scope(live_branches, repo_root, base=base)
    tasks = [
        Task(task_id=branch, scope_files=scope.get(branch, []))
        for branch in live_branches
    ]
    return plan_execution_order(tasks)


# ---------------------------------------------------------------------------
# Detector 5: manifest corruption / schema
# ---------------------------------------------------------------------------


def _read_manifest(path: str) -> tuple[Any, str | None]:
    """Read and JSON-parse `path`. Returns (data, error_msg)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError as exc:
        return None, f"json_decode:{exc.msg}:line {exc.lineno}"
    except OSError as exc:
        return None, f"io:{exc.strerror or exc}"


def detect_manifest_corruption(manifest_path: str) -> list[Conflict]:
    """Flag malformed JSON or missing required keys in the manifest.

    Required entry keys: wt_path, branch, pid, started_at, last_heartbeat.
    """
    data, err = _read_manifest(manifest_path)
    if err == "missing":
        # A missing manifest on a brand-new repo is OK (no swarm has run
        # yet). Surface as `major` so operators notice but it does not
        # block the spawn.
        return [
            Conflict(
                severity="major",
                category="manifest_missing",
                summary=f"manifest '{manifest_path}' does not exist",
                evidence=[manifest_path],
                remediation=(
                    "create an empty manifest at .jcode/worktree-manifest.json "
                    "before the first swarm spawn, or ignore on repos with "
                    "no active workers"
                ),
            )
        ]
    if err:
        return [
            Conflict(
                severity="blocker",
                category="manifest_corruption",
                summary=f"manifest '{manifest_path}' is malformed",
                evidence=[manifest_path, err],
                remediation=(
                    "restore the manifest from the last good copy, or "
                    "truncate it to {} if no workers are active"
                ),
            )
        ]

    entries = data.get("entries", []) if isinstance(data, dict) else []
    if not isinstance(entries, list):
        return [
            Conflict(
                severity="blocker",
                category="manifest_corruption",
                summary="manifest root is not an object with an 'entries' list",
                evidence=[manifest_path],
                remediation="restore the manifest from the last good copy",
            )
        ]

    # Schema check: each entry must carry all required keys.
    conflicts: list[Conflict] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            conflicts.append(
                Conflict(
                    severity="major",
                    category="manifest_schema",
                    summary=f"entry #{idx} is not an object",
                    evidence=[f"entry {idx}: {type(entry).__name__}"],
                    remediation="rewrite the entry as a JSON object",
                )
            )
            continue
        missing = [k for k in _MANIFEST_REQUIRED_KEYS if k not in entry]
        if missing:
            conflicts.append(
                Conflict(
                    severity="major",
                    category="manifest_schema",
                    summary=(
                        f"entry #{idx} is missing keys: {', '.join(missing)}"
                    ),
                    evidence=[
                        f"entry {idx}: missing {', '.join(missing)}"
                    ],
                    remediation=(
                        "add the missing keys (or rewrite the manifest "
                        "from scratch)"
                    ),
                )
            )
    return conflicts


# ---------------------------------------------------------------------------
# Detector 6: heartbeat staleness
# ---------------------------------------------------------------------------


def _parse_iso(ts: str) -> datetime.datetime:
    """Parse an ISO-8601 timestamp; tolerate trailing 'Z'."""
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def detect_heartbeat_stale(
    entries: list[dict[str, Any]],
    now: datetime.datetime | None = None,
    ttl_seconds: int = DEFAULT_HEARTBEAT_TTL_SECONDS,
) -> list[Conflict]:
    """Flag manifest entries whose heartbeat is older than `ttl_seconds`."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    conflicts: list[Conflict] = []
    for idx, entry in enumerate(entries):
        hb_raw = entry.get("last_heartbeat")
        if not hb_raw:
            continue
        try:
            hb = _parse_iso(str(hb_raw))
        except ValueError:
            conflicts.append(
                Conflict(
                    severity="major",
                    category="heartbeat_stale",
                    summary=f"entry #{idx} has unparseable heartbeat '{hb_raw}'",
                    evidence=[f"entry {idx}: {hb_raw}"],
                    remediation="rewrite the entry with a valid ISO-8601 timestamp",
                )
            )
            continue
        age = (now - hb).total_seconds()
        if age > ttl_seconds:
            age_hours = round(age / 3600, 1)
            conflicts.append(
                Conflict(
                    severity="major",
                    category="heartbeat_stale",
                    summary=(
                        f"entry #{idx} heartbeat is {age_hours}h old "
                        f"(>{ttl_seconds // 3600}h TTL)"
                    ),
                    evidence=[
                        f"entry {idx}: branch={entry.get('branch', '?')}",
                        f"last_heartbeat={hb_raw}",
                    ],
                    remediation=(
                        "remove the stale entry before the next spawn; the "
                        "worker likely crashed and its worktree is leaked"
                    ),
                )
            )
    return conflicts


# ---------------------------------------------------------------------------
# Manifest convenience: load + run both manifest detectors
# ---------------------------------------------------------------------------


def run_manifest_detectors(
    manifest_path: str,
    heartbeat_ttl: int = DEFAULT_HEARTBEAT_TTL_SECONDS,
    now: datetime.datetime | None = None,
) -> list[Conflict]:
    """Run manifest corruption + heartbeat detectors against one file."""
    data, err = _read_manifest(manifest_path)
    corruption = detect_manifest_corruption(manifest_path)
    if err == "missing":
        return corruption
    if err:
        return corruption
    entries = (data or {}).get("entries", []) if isinstance(data, dict) else []
    heartbeat = detect_heartbeat_stale(
        entries, now=now, ttl_seconds=heartbeat_ttl
    )
    return corruption + heartbeat


# ---------------------------------------------------------------------------
# Detector 7: plan_execution_order — turns scope overlap into a DAG plan.
# Detector 8: detect_dependency_chain — flags new tasks that collide with
#             in-flight workers' actual branch diffs.
# Detector 9: suggest_serialization — orders parallel-runnable tasks to
#             minimise merge risk (lockfile first, then git-history recent).
# ---------------------------------------------------------------------------


@dataclass
class Task:
    """A unit of work with a stable id and a list of files it will touch.

    `scope_files` are repo-relative paths. Used by the planning +
    dependency-chain + serialization detectors.
    """

    task_id: str
    scope_files: list[str] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    """Output of `plan_execution_order`.

    Fields:
        phases           — list of parallel-runnable batches, in dependency
                           order. `phases[i]` only depends on phases[0..i-1].
                           An empty inner list (`phases=[[]]`) is the cycle
                           sentinel: caller should treat it as a blocker.
        critical_path    — longest chain of tasks through the phases. The
                           minimum number of serial steps the swarm must
                           execute even with infinite parallelism.
        parallel_batches — subset of phases whose length > 1. Convenience
                           for operators who only care about fan-out.
    """

    phases: list[list[str]]
    critical_path: list[str]
    parallel_batches: list[list[str]]


def _plan_build_graph(
    tasks: list[Task],
) -> tuple[list[str], dict[str, set[str]], dict[str, set[str]]]:
    """Build a task dependency graph from scope-file overlap.

    Returns (task_ids_sorted, predecessors, successors).

    Orientation: when task A and task B share a file, the lex-smaller id
    is the predecessor. Lex-based orientation is always acyclic, so the
    cycle-detector in `plan_execution_order` is defensive only.
    """
    seen: dict[str, Task] = {}
    for t in tasks:
        if not t.task_id:
            continue
        seen[t.task_id] = t
    task_ids = sorted(seen.keys())

    file_to_tasks: dict[str, set[str]] = {}
    for tid in task_ids:
        for f in seen[tid].scope_files:
            if not f:
                continue
            file_to_tasks.setdefault(f, set()).add(tid)

    preds: dict[str, set[str]] = {tid: set() for tid in task_ids}
    succs: dict[str, set[str]] = {tid: set() for tid in task_ids}
    for owners in file_to_tasks.values():
        owners_sorted = sorted(owners)
        for i, a in enumerate(owners_sorted):
            for b in owners_sorted[i + 1 :]:
                # Lex orientation: a -> b.
                preds[b].add(a)
                succs[a].add(b)
    return task_ids, preds, succs


def plan_execution_order(tasks: list[Task]) -> ExecutionPlan:
    """Build a phase-ordered execution plan from scope-file overlap.

    Algorithm:
        1. Build file -> task_ids reverse index from `tasks`.
        2. For each file touched by >=2 tasks: add undirected edge.
        3. Orient edges by lex task_id (smaller -> larger). Cycles
           cannot arise from lex orientation alone, but we still
           run Kahn's algorithm to detect them defensively.
        4. Phase assignment: phase[t] = max(phase[p] for p in preds) + 1.
        5. Critical path = longest DAG chain (lex tie-break).
        6. Parallel batches = phases whose length > 1.

    Cycle sentinel: if Kahn's leaves any node unreached, return
    `ExecutionPlan(phases=[[]], critical_path=[], parallel_batches=[])`.
    The caller is expected to surface this as a blocker Conflict.
    """
    if not tasks:
        return ExecutionPlan(phases=[], critical_path=[], parallel_batches=[])

    task_ids, preds, succs = _plan_build_graph(tasks)
    if not task_ids:
        return ExecutionPlan(phases=[], critical_path=[], parallel_batches=[])

    # Kahn's topological sort.
    in_degree = {tid: len(preds[tid]) for tid in task_ids}
    queue = sorted(tid for tid, d in in_degree.items() if d == 0)
    topo_order: list[str] = []
    while queue:
        node = queue.pop(0)
        topo_order.append(node)
        # Decrement in-degree for successors; append those that hit zero.
        for nxt in sorted(succs[node]):
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)
                queue.sort()

    if len(topo_order) != len(task_ids):
        # Cycle sentinel: caller surfaces a blocker Conflict.
        return ExecutionPlan(phases=[[]], critical_path=[], parallel_batches=[])

    # Phase assignment by DP over topo order.
    phase_of: dict[str, int] = {tid: 0 for tid in task_ids}
    for tid in topo_order:
        if preds[tid]:
            phase_of[tid] = max(phase_of[p] for p in preds[tid]) + 1

    max_phase = max(phase_of.values()) if phase_of else -1
    phases: list[list[str]] = []
    for p in range(max_phase + 1):
        bucket = sorted(tid for tid in task_ids if phase_of[tid] == p)
        phases.append(bucket)

    # Critical path: longest chain, lex tie-break.
    longest: dict[str, int] = {tid: 1 for tid in task_ids}
    predecessor: dict[str, str | None] = {tid: None for tid in task_ids}
    for tid in topo_order:
        for p in sorted(preds[tid]):  # lex tie-break
            cand = longest[p] + 1
            if cand > longest[tid]:
                longest[tid] = cand
                predecessor[tid] = p

    end_task = max(task_ids, key=lambda t: (longest[t], -ord(t[0]) if t else 0))
    # Tie-break on equal longest length: prefer the lex-later end so that
    # backtracking through lex-sorted predecessors favours smaller ids.
    # Specifically, if multiple tasks share the max length, pick the one
    # whose predecessor is lex-smaller (smaller first preference).
    max_len = max(longest.values())
    candidates = [t for t in task_ids if longest[t] == max_len]
    # Choose the candidate with the lex-smaller predecessor chain.
    def chain_key(t: str) -> tuple[int, str]:
        return (longest[t], t)

    candidates.sort(key=chain_key)
    end_task = candidates[0]

    critical_path: list[str] = []
    cur: str | None = end_task
    while cur is not None:
        critical_path.append(cur)
        cur = predecessor[cur]
    critical_path.reverse()

    parallel_batches = [list(b) for b in phases if len(b) > 1]

    return ExecutionPlan(
        phases=phases,
        critical_path=critical_path,
        parallel_batches=parallel_batches,
    )


def _run_git_diff_files(repo_root: str, base: str, branch: str) -> set[str]:
    """Return `set[str]` of files changed between base and branch.

    Tries `<base>..<branch>` first; falls back to `git ls-tree -r <branch>`
    when the diff produces no output. Returns empty set if git is missing.
    """
    diff_out = _run_git(repo_root, "diff", f"{base}..{branch}", "--name-only")
    if diff_out.strip():
        return {line.strip() for line in diff_out.splitlines() if line.strip()}
    ls_out = _run_git(repo_root, "ls-tree", "-r", "--name-only", branch)
    if ls_out.strip():
        return {line.strip() for line in ls_out.splitlines() if line.strip()}
    return set()


def detect_dependency_chain(
    new_task: Task,
    existing_tasks: list[Task],
    existing_branches: list[str],
    repo_path: str,
) -> list[Conflict]:
    """Flag a new task whose scope collides with any in-flight worker branch.

    For each in-flight branch, runs `git diff main..<branch> --name-only`
    (with `master` and `HEAD` fallbacks) and intersects with the new task's
    `scope_files`. Any intersection is a `blocker`: the new task must wait
    for that worker to finish, or the operator must rebase the new task
    against the in-flight branch first.

    Args:
        new_task          — Task being planned.
        existing_tasks    — Reserved for future cross-task dependency data.
        existing_branches — In-flight worker branch names.
        repo_path         — Filesystem path to the repo root for git commands.

    Returns:
        list[Conflict]; one blocker per branch that shares files with the
        new task. Empty list when no overlap exists.
    """
    planned_set = {p for p in new_task.scope_files if p}
    if not planned_set or not existing_branches:
        return []

    # Try `main`, then `master`, then `HEAD`.
    base_candidates = ("main", "master", "HEAD")

    conflicts: list[Conflict] = []
    for branch in existing_branches:
        changed: set[str] = set()
        for base in base_candidates:
            changed = _run_git_diff_files(repo_path, base, branch)
            if changed:
                break
        if not changed:
            continue
        overlap = sorted(planned_set & changed)
        if overlap:
            evidence = [f"{branch}: {p}" for p in overlap]
            conflicts.append(
                Conflict(
                    severity="blocker",
                    category="dependency_chain",
                    summary=(
                        f"new task '{new_task.task_id}' depends on "
                        f"in-flight worker '{branch}': shared file(s) "
                        f"{overlap}"
                    ),
                    evidence=evidence,
                    remediation=(
                        "merge the in-flight branch and rebase the new "
                        "task against it, or split the new task's scope"
                    ),
                )
            )
    return conflicts


def suggest_serialization(
    conflicting_tasks: list[Task],
    repo_path: str,
    config: dict[str, Any] | None = None,
) -> list[Conflict]:
    """Suggest a serialization order for tasks that share files.

    Algorithm:
        1. For each shared file, check whether it's lockfile-shaped
           (config-driven set + default patterns). If yes: blocker with
           remediation to serialize.
        2. For non-lockfile shared files, check recent git history
           (`git log --oneline -20 -- <file>`). The task that aligns
           with the most recent commit history goes first (least likely
           to conflict on existing lines).
        3. If history is empty: minor remediation ("parallel OK; root
           should rebase after merge") — disjoint line overlap is
           safe to parallelise as long as the operator rebases.
        4. R19 gap 3: severity escalates by worker count using
           `severity_threshold_n` (default {major: 4, blocker: 6}):
               N < major    -> minor
               N >= major   -> major
               N >= blocker -> blocker

    Args:
        conflicting_tasks — Tasks whose scope_files overlap.
        repo_path         — Filesystem path to the repo root for git log.
        config            — Optional config dict (lockfile_files,
                            ignored_paths, severity_threshold_n).

    Returns:
        list[Conflict]; one entry per shared file. Blockers for lockfiles,
        minors otherwise (escalated per threshold config).
    """
    cfg = config or {}
    patterns = list(DEFAULT_LOCKFILE_PATTERNS)
    extras = cfg.get("lockfile_files") or []
    if isinstance(extras, list):
        patterns.extend(str(x) for x in extras)
    ignored = cfg.get("ignored_paths") or []
    if not isinstance(ignored, list):
        ignored = []
    thresholds = dict(DEFAULT_SEVERITY_THRESHOLD_N)
    cfg_thresh = cfg.get("severity_threshold_n")
    if isinstance(cfg_thresh, dict):
        for k, v in cfg_thresh.items():
            try:
                thresholds[str(k)] = int(v)
            except (TypeError, ValueError):
                continue
    major_n = int(thresholds.get("major", 4))
    blocker_n = int(thresholds.get("blocker", 6))

    file_to_tasks: dict[str, list[str]] = {}
    for t in conflicting_tasks:
        if not t.task_id:
            continue
        for f in t.scope_files:
            if not f or _is_ignored(f, ignored):
                continue
            file_to_tasks.setdefault(f, []).append(t.task_id)

    conflicts: list[Conflict] = []
    for path, owners in file_to_tasks.items():
        unique_owners = sorted(set(owners))
        n_owners = len(unique_owners)
        if n_owners < 2:
            continue
        evidence = [f"{o}: {path}" for o in unique_owners]
        if _matches_lockfile(path, patterns):
            conflicts.append(
                Conflict(
                    severity="blocker",
                    category="serialization_lockfile",
                    summary=(
                        f"lockfile contention: '{path}' touched by "
                        f"{n_owners} tasks ({', '.join(unique_owners)})"
                    ),
                    evidence=evidence,
                    remediation=(
                        "serialize; lowest-risk task first (the task "
                        "touching fewest other files should run first)"
                    ),
                )
            )
            continue

        # Non-lockfile: pick severity by worker count, then check git history.
        if n_owners >= blocker_n:
            severity = "blocker"
        elif n_owners >= major_n:
            severity = "major"
        else:
            severity = "minor"
        evidence.append(f"N={n_owners}")
        log_out = _run_git(
            repo_path, "log", "--oneline", "-20", "--", path
        )
        recent_commits = [line for line in log_out.splitlines() if line.strip()]
        if not recent_commits:
            conflicts.append(
                Conflict(
                    severity=severity,
                    category="serialization_overlap",
                    summary=(
                        f"shared file '{path}' across {n_owners} "
                        f"tasks with no recent commit history"
                    ),
                    evidence=evidence,
                    remediation=(
                        "parallel OK; root should rebase after merge "
                        "to surface any line-range conflicts"
                    ),
                )
            )
        else:
            evidence.append(f"recent_commits={len(recent_commits)}")
            conflicts.append(
                Conflict(
                    severity=severity,
                    category="serialization_overlap",
                    summary=(
                        f"shared file '{path}' across {n_owners} tasks; "
                        f"order by git history recency"
                    ),
                    evidence=evidence,
                    remediation=(
                        "run the task aligned with the most recent commit "
                        "history first; parallel OK only if disjoint line "
                        "ranges — root should rebase after merge"
                    ),
                )
            )
    return conflicts


def _read_tasks_file(path: str) -> list[Task]:
    """Load a JSON file of `[{"task_id": ..., "scope_files": [...]}, ...]`."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(
            f"tasks file must be a JSON list, got {type(data).__name__}"
        )
    out: list[Task] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        tid = str(entry.get("task_id", "")).strip()
        files = entry.get("scope_files") or []
        if isinstance(files, list):
            out.append(Task(task_id=tid, scope_files=[str(x) for x in files]))
        else:
            out.append(Task(task_id=tid, scope_files=[]))
    return out


def _format_text_plan(plan: ExecutionPlan) -> str:
    """Plain-text rendering for an ExecutionPlan."""
    if plan.phases == [[]]:
        return (
            "execution plan: CYCLE DETECTED — caller must surface as blocker\n"
        )
    if not plan.phases:
        return "execution plan: (no tasks)\n"
    lines: list[str] = ["execution plan:"]
    for i, phase in enumerate(plan.phases):
        tag = "parallel" if len(phase) > 1 else "serial"
        lines.append(f"  phase {i} ({tag}): {', '.join(phase)}")
    lines.append(f"  critical_path: {' -> '.join(plan.critical_path)}")
    lines.append(
        f"  parallel_batches: "
        f"{', '.join('[' + ','.join(b) + ']' for b in plan.parallel_batches) or '(none)'}"
    )
    return "\n".join(lines) + "\n"


def _emit_plan(plan: ExecutionPlan, fmt: str, out: Any = None) -> int:
    """Print an ExecutionPlan in the chosen format.

    Cycle sentinel (`phases == [[]]`) returns exit code 2 (blocker).
    Otherwise the planning command is informational and returns 0.
    """
    out = out or sys.stdout
    payload = {
        "phases": plan.phases,
        "critical_path": plan.critical_path,
        "parallel_batches": plan.parallel_batches,
        "is_cycle": plan.phases == [[]],
    }
    if fmt == "json":
        out.write(json.dumps(payload, indent=2) + "\n")
    else:
        out.write(_format_text_plan(plan))
    return 2 if plan.phases == [[]] else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_text(conflicts: list[Conflict]) -> str:
    if not conflicts:
        return "no conflicts\n"
    lines = []
    for c in conflicts:
        lines.append(f"[{c.severity}] {c.category}: {c.summary}")
        for ev in c.evidence:
            lines.append(f"    - {ev}")
        if c.remediation:
            lines.append(f"    -> {c.remediation}")
    return "\n".join(lines) + "\n"


def _format_json(conflicts: list[Conflict]) -> str:
    payload = {
        "highest_severity": _worst_severity(conflicts),
        "count": len(conflicts),
        "conflicts": [asdict(c) for c in conflicts],
    }
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def _emit(
    conflicts: list[Conflict],
    fmt: str,
    out: Any = None,
) -> int:
    """Print in chosen format. Returns the exit code."""
    out = out or sys.stdout
    if fmt == "json":
        out.write(_format_json(conflicts))
    else:
        out.write(_format_text(conflicts))
    return _exit_code_for(conflicts)


def _read_scopes_file(path: str) -> dict[str, list[str]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_parser() -> argparse.ArgumentParser:
    # `--format` lives on each subparser via `parents=[fmt_parent]` so the
    # flag works both before and after the subcommand. (argparse parent
    # args are only recognized before the subcommand by default.)
    fmt_parent = argparse.ArgumentParser(add_help=False)
    fmt_parent.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    p = argparse.ArgumentParser(
        prog="conflict-detect",
        description=(
            "Generic swarm conflict-detection framework. Pure stdlib. "
            "Returns exit 0 (clean), 1 (major/warning), or 2 (blocker)."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    sp1 = sub.add_parser("scope-overlap", parents=[fmt_parent],
                          help="detect files touched by 2+ workers in a scope map")
    sp1.add_argument("--scopes", required=True, help="JSON file of {worker: [files]}")

    sp2 = sub.add_parser("lockfile", parents=[fmt_parent],
                          help="detect scope entries that touch high-contention lockfiles")
    sp2.add_argument("--scopes", required=True, help="JSON file of {worker: [files]}")
    sp2.add_argument("--config", default=None,
                     help="optional YAML config file (default set if omitted)")

    sp3 = sub.add_parser("in-flight", parents=[fmt_parent],
                          help="detect overlap between a planned scope and in-flight branches")
    sp3.add_argument("--scope", nargs="+", required=True, help="planned scope files")
    sp3.add_argument("--branches", nargs="+", default=[], help="in-flight branch names")
    sp3.add_argument("--repo", default=".", help="repo root for git commands")

    sp4 = sub.add_parser("dirty", parents=[fmt_parent],
                          help="detect uncommitted changes in a worker worktree")
    sp4.add_argument("--worktree", required=True, help="path to the worktree")

    sp5 = sub.add_parser("manifest", parents=[fmt_parent],
                          help="detect manifest corruption and stale heartbeats")
    sp5.add_argument("--manifest", default=".jcode/worktree-manifest.json",
                     help="path to worktree-manifest.json")
    sp5.add_argument("--heartbeat-ttl", type=int,
                     default=DEFAULT_HEARTBEAT_TTL_SECONDS,
                     help="stale heartbeat threshold in seconds")

    sp6 = sub.add_parser("all", parents=[fmt_parent],
                          help="run scope-overlap + lockfile + in-flight in one pass")
    sp6.add_argument("--scopes", required=True, help="JSON file of {worker: [files]}")
    sp6.add_argument("--branches", nargs="+", default=[], help="in-flight branch names")
    sp6.add_argument("--repo", default=".", help="repo root for git commands")
    sp6.add_argument("--config", default=None, help="optional YAML config file")

    sp7 = sub.add_parser("plan-order", parents=[fmt_parent],
                          help="plan task execution order based on file overlap")
    # R19 gap 1: accept either --tasks (legacy) or --branches (auto-extract).
    # Both are optional; the caller must pass at least one.
    sp7.add_argument("--tasks", required=False, default=None,
                     help="JSON file of [{task_id, scope_files}]")
    sp7.add_argument("--branches", nargs="+", default=None,
                     help="branch names to auto-extract scope from "
                          "(mutually exclusive with --tasks)")
    sp7.add_argument("--base", default="main",
                     help="base ref for --branches mode (default: main)")
    sp7.add_argument("--repo", default=".",
                     help="repo root for --branches mode (default: cwd)")

    sp8 = sub.add_parser("dep-chain", parents=[fmt_parent],
                          help="detect if a planned task depends on in-flight workers' branches")
    sp8.add_argument("--scope", required=True,
                     help="JSON file of [Task] (first entry is the new task)")
    sp8.add_argument("--branches", nargs="+", default=[],
                     help="in-flight branch names")
    sp8.add_argument("--repo", default=".", help="repo root for git commands")

    sp9 = sub.add_parser("serialize", parents=[fmt_parent],
                          help="suggest serialization order for tasks sharing files")
    sp9.add_argument("--tasks", required=True,
                     help="JSON file of [{task_id, scope_files}]")
    sp9.add_argument("--config", default=None,
                     help="optional YAML config file (default set if omitted)")
    sp9.add_argument("--repo", default=".", help="repo root for git commands")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    fmt = getattr(args, "format", "text")
    conflicts: list[Conflict] = []

    if args.command == "scope-overlap":
        scopes = _read_scopes_file(args.scopes)
        conflicts = detect_scope_overlap(scopes)

    elif args.command == "lockfile":
        scopes = _read_scopes_file(args.scopes)
        config = load_config(args.config)
        conflicts = detect_lockfile_contention(scopes, config=config)

    elif args.command == "in-flight":
        conflicts = detect_in_flight_overlap(
            planned=list(args.scope),
            in_flight_branches=list(args.branches),
            repo_root=args.repo,
        )

    elif args.command == "dirty":
        conflicts = detect_dirty_state(args.worktree)

    elif args.command == "manifest":
        conflicts = run_manifest_detectors(
            args.manifest, heartbeat_ttl=args.heartbeat_ttl
        )

    elif args.command == "all":
        scopes = _read_scopes_file(args.scopes)
        config = load_config(args.config)
        # Build the planned scope = union of all workers' files.
        planned: list[str] = []
        for files in scopes.values():
            planned.extend(files)
        conflicts = []
        conflicts.extend(detect_scope_overlap(scopes))
        conflicts.extend(detect_lockfile_contention(scopes, config=config))
        conflicts.extend(
            detect_in_flight_overlap(
                planned=planned,
                in_flight_branches=list(args.branches),
                repo_root=args.repo,
            )
        )

    elif args.command == "plan-order":
        # R19 gap 1: --branches auto-extracts scope + ancestry from git.
        # --tasks keeps the legacy JSON-file path.
        if args.branches:
            if args.tasks:
                raise SystemExit(
                    "plan-order: --tasks and --branches are mutually exclusive"
                )
            plan = plan_execution_order_from_branches(
                branches=list(args.branches),
                base=args.base,
                repo_root=args.repo,
            )
        elif args.tasks:
            tasks = _read_tasks_file(args.tasks)
            plan = plan_execution_order(tasks)
        else:
            raise SystemExit(
                "plan-order: must pass either --tasks <file> or --branches <name>..."
            )
        return _emit_plan(plan, fmt)

    elif args.command == "dep-chain":
        tasks = _read_tasks_file(args.scope)
        new_task = tasks[0] if tasks else Task(task_id="?", scope_files=[])
        conflicts = detect_dependency_chain(
            new_task=new_task,
            existing_tasks=tasks[1:],
            existing_branches=list(args.branches),
            repo_path=args.repo,
        )

    elif args.command == "serialize":
        tasks = _read_tasks_file(args.tasks)
        config = load_config(args.config)
        conflicts = suggest_serialization(
            tasks, repo_path=args.repo, config=config
        )

    return _emit(conflicts, fmt)


if __name__ == "__main__":
    sys.exit(main())