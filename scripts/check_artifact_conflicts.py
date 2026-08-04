#!/usr/bin/env python3
"""Pre-commit hook: detect Git conflict markers in a commit's diff.

Invoked by worker-side `scripts/check_artifact_conflicts.py <commit-ish>`
before `complete_node`. If the diff between <commit-ish> and main (or
its parent, if no main branch) contains any of the three Git conflict
markers (`<<<<<<<`, `=======`, `>>>>>>>`), exits 1 with the offending
lines on stderr. Exits 0 on a clean diff.

Stdlib-only. Pure subprocess wrapper around `git diff`.

Exit codes:
    0 - clean diff (no markers)
    1 - conflict markers detected
    2 - invalid input (no commit-ish, no such commit, etc.)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


# Three markers. Anchored at start-of-line. The middle marker is the
# divider; we ignore it if it's a Markdown heading (lines starting with
# `#` or `##` etc.). The decide-and-divider line could be `=======` with
# or without trailing whitespace. The end marker is `>>>>>>> ` with
# trailing space (the standard conflict-marker block).
_START_MARKER_RE = re.compile(
    r"^[+\- ]?(?P<m><{7,}|>{7,})\s",
    re.MULTILINE,
)
_DIVIDER_RE = re.compile(
    r"^[+\- ]?(?P<m>={7,})\s*$",
    re.MULTILINE,
)


def _resolve_commit(cwd: str, ref: str) -> str:
    """Resolve a commit-ish to a full SHA. Errors on invalid input."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"error: no such commit: {ref!r}", file=sys.stderr)
        print(exc.stderr.strip(), file=sys.stderr)
        sys.exit(2)
    return out.stdout.strip()


def _diff(cwd: str, commit: str) -> str:
    """Compute the diff for the commit. Prefers main..commit, falls back
    to commit's own diff against parent if main is absent.
    """
    # Try main..commit first.
    try:
        subprocess.run(
            ["git", "rev-parse", "--verify", "main"],
            cwd=cwd,
            capture_output=True,
            check=True,
        )
        diff_range = f"main..{commit}"
    except subprocess.CalledProcessError:
        # No main branch; use parent diff.
        diff_range = f"{commit}~1..{commit}"

    out = subprocess.run(
        ["git", "diff", diff_range],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    diff_text = out.stdout

    # If main..commit is empty (commit is on main itself, or main has
    # advanced past commit), fall back to the commit's own diff against
    # its parent.
    if not diff_text.strip():
        try:
            parent_range = f"{commit}~1..{commit}"
            out2 = subprocess.run(
                ["git", "diff", parent_range],
                cwd=cwd,
                capture_output=True,
                text=True,
            )
            diff_text = out2.stdout
        except subprocess.CalledProcessError:
            pass

    return diff_text


def _scan(diff_text: str) -> list[str]:
    """Return offending lines (with surrounding context)."""
    bad: list[str] = []
    for m in _START_MARKER_RE.finditer(diff_text):
        bad.append(m.group(0).rstrip("\n"))
    for m in _DIVIDER_RE.finditer(diff_text):
        bad.append(m.group(0).rstrip("\n"))
    return bad


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="check_artifact_conflicts.py",
        description="Detect Git conflict markers in a commit's diff.",
    )
    parser.add_argument(
        "commit",
        help="commit SHA, branch name, or HEAD",
    )
    args = parser.parse_args(argv)

    cwd = str(Path.cwd())
    commit = _resolve_commit(cwd, args.commit)
    diff_text = _diff(cwd, commit)

    if not diff_text.strip():
        print(f"{commit[:12]}: clean (no diff)")
        return 0

    bad = _scan(diff_text)
    if bad:
        print(
            f"{commit[:12]}: CONFLICT MARKERS DETECTED "
            f"({len(bad)} line(s))",
            file=sys.stderr,
        )
        for line in bad[:20]:
            print(f"  {line}", file=sys.stderr)
        if len(bad) > 20:
            print(f"  ... ({len(bad) - 20} more)", file=sys.stderr)
        return 1

    print(f"{commit[:12]}: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
