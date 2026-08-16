#!/usr/bin/env bash
#
# scripts/swarm-sweep.sh — clean up stale swarm worktrees
#
# Find and (optionally) remove git worktrees whose path matches the
# swarm convention `$TMPDIR/swarm-<user>/<repo>-<short-sha>/wt-<label>/`
# and whose last commit is older than `--max-age` days. Cleans up
# the residue of M3 (silent worker disappearance) and M2 (worker
# forgot to emit artifact) without touching the main worktree or
# any manual feature worktree.
#
# Worktree detection: scans `git worktree list --porcelain` for paths
# matching the swarm convention. Other worktrees (main, manual
# feature work) are NEVER touched.
#
# Usage:
#   swarm-sweep [--yes] [--max-age=N] [--repo=PATH]
#
# Options:
#   --yes           actually remove (default: dry-run only).
#   --max-age=N     threshold in days (default: 7).
#   --repo=PATH     operate on this repo (default: current dir's
#                   toplevel).
#   --help          show this help.
#
# Exit codes:
#   0  no stale worktrees (or all successfully removed)
#   1  some removals failed (others succeeded)
#   2  invalid arguments or not in a git repo
#
# This script is part of lazible-jcode. install.sh symlinks it into
# ~/.local/bin/swarm-sweep during the binary install step.

set -euo pipefail

YES=0
MAX_AGE_DAYS=7
REPO_ROOT=""

for arg in "$@"; do
  case "$arg" in
    --yes) YES=1 ;;
    --max-age=*) MAX_AGE_DAYS="${arg#*=}" ;;
    --repo=*) REPO_ROOT="${arg#*=}" ;;
    --help|-h)
      sed -n '16,32p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "swarm-sweep: unknown option: $arg" >&2
      echo "Run with --help for usage." >&2
      exit 2
      ;;
  esac
done

if ! [[ "$MAX_AGE_DAYS" =~ ^[0-9]+$ ]] || [[ "$MAX_AGE_DAYS" -lt 1 ]]; then
  echo "swarm-sweep: --max-age must be a positive integer" >&2
  exit 2
fi

if [[ -z "$REPO_ROOT" ]]; then
  if ! REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    echo "swarm-sweep: not inside a git repository (use --repo=<path>)" >&2
    exit 2
  fi
fi

# Convention: $TMPDIR/swarm-<user>/<repo>-<short-sha>/wt-<label>/
# Match the tail: anything ending in /swarm-<user>/<repo>/wt-<label>(/)?
WT_PATTERN='.*/swarm-[^/]+/[^/]+/wt-[^/]+/?$'

NOW=$(date +%s)
THRESHOLD=$((MAX_AGE_DAYS * 86400))

STALE=()

CURRENT_WT=""
CURRENT_SHA=""
CURRENT_BRANCH=""

while IFS= read -r line; do
  case "$line" in
    "worktree "*)
      CURRENT_WT="${line#worktree }"
      ;;
    "HEAD "*)
      CURRENT_SHA="${line#HEAD }"
      ;;
    "branch "*)
      CURRENT_BRANCH="${line#branch refs/heads/}"
      # All three fields now available for this worktree.
      if [[ -n "$CURRENT_WT" && -n "$CURRENT_BRANCH" ]]; then
        if [[ "$CURRENT_WT" =~ $WT_PATTERN ]]; then
          ts=$(git -C "$CURRENT_WT" log -1 --format=%ct "${CURRENT_SHA:-HEAD}" 2>/dev/null || echo 0)
          age_seconds=$((NOW - ts))
          if [[ $age_seconds -gt $THRESHOLD ]]; then
            age_days=$((age_seconds / 86400))
            STALE+=("$CURRENT_WT"$'\t'"$CURRENT_BRANCH"$'\t'"$age_days")
          fi
        fi
      fi
      CURRENT_WT=""
      CURRENT_SHA=""
      CURRENT_BRANCH=""
      ;;
    "")
      # Blank line separates worktrees. Reset state defensively.
      CURRENT_WT=""
      CURRENT_SHA=""
      CURRENT_BRANCH=""
      ;;
  esac
done < <(git -C "$REPO_ROOT" worktree list --porcelain)

if [[ ${#STALE[@]} -eq 0 ]]; then
  echo "swarm-sweep: no stale swarm worktrees (max age: $MAX_AGE_DAYS days, repo: $REPO_ROOT)"
  exit 0
fi

FAIL=0
for entry in "${STALE[@]}"; do
  IFS=$'\t' read -r wt branch age <<<"$entry"
  echo "stale: $wt ($age days old, branch: $branch)"
  if [[ $YES -eq 1 ]]; then
    if git -C "$REPO_ROOT" worktree remove --force "$wt" 2>&1; then
      echo "  removed worktree"
      # Remove the branch too. -D because it may not be merged.
      if git -C "$REPO_ROOT" branch -D "$branch" 2>&1; then
        echo "  removed branch $branch"
      else
        echo "  (branch $branch kept — may be checked out elsewhere or merged)" >&2
      fi
    else
      echo "  FAILED to remove worktree" >&2
      FAIL=1
    fi
  fi
done

if [[ $YES -eq 0 ]]; then
  echo
  echo "dry-run mode. Re-run with --yes to actually remove."
fi

exit $FAIL