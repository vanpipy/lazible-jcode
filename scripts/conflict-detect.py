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
    `#` comments, quoted strings, ints, bools, null. Anything fancier
    (anchors, multi-line strings, flow style) is unsupported.
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
            result[key] = _coerce(value)
        else:
            # Look ahead: if next line starts with `- ` at deeper indent, list.
            if pos[0] < len(raw_lines):
                next_indent, next_text = raw_lines[pos[0]]
                if next_indent > indent and next_text.startswith("- "):
                    result[key] = parse_list(next_indent)
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

    return _emit(conflicts, fmt)


if __name__ == "__main__":
    sys.exit(main())