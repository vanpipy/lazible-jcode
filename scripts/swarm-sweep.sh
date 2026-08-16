#!/usr/bin/env bash
#
# scripts/swarm-sweep.sh — clean up stale swarm worktrees
#
# Find and (optionally) remove git worktrees whose path matches either
# of the two swarm worktree conventions:
#
#   bundle:   $LAZIBLE_TMPDIR/jcode/<repo>-<short-sha>/wt-<label>/
#   jcode:    $TMPDIR/swarm-<user>/<repo>-<short-sha>/wt-<label>/
#
# and whose last commit is older than `--max-age` days. Cleans up the
# residue of M3 (silent worker disappearance) and M2 (worker forgot
# to emit artifact) without touching the main worktree or any manual
# feature worktree.
#
# Worktree detection: scans `git worktree list --porcelain` for paths
# matching either convention. Other worktrees (main, manual feature
# work) are NEVER touched.
#
# Why two patterns: bundle rewrites the path layout (drop the
# `swarm-<user>` segment, add a `jcode/` prefix) so that worktrees
# live under the same scratch root the user can see in
# `extension.sh scratch-dir`. Older jcode versions and any workers
# that bypass bundle's scratch-dir helper still emit the jcode
# native form, so we match both. Sweep is silent on which one it
# matched (a single worktree is either in scope or it isn't).
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

# Color-aware output. Disable color in three cases:
#   1. NO_COLOR env set (https://no-color.org standard)
#   2. stdout not a tty (output is being piped/captured)
#   3. TERM=dumb (terminal can't render ANSI; CI / minimal emulators)
if [[ -n "${NO_COLOR:-}" || ! -t 1 || "${TERM:-}" == "dumb" ]]; then
  C_INFO=''; C_WARN=''; C_ERR=''; C_RESET=''
else
  C_INFO='\033[1;34m'; C_WARN='\033[1;33m'; C_ERR='\033[1;31m'; C_RESET='\033[0m'
fi
info() { printf '%b%s%b\n' "$C_INFO" "$*" "$C_RESET"; }
warn() { printf '%b%s%b\n' "$C_WARN" "$*" "$C_RESET" >&2; }
err()  { printf '%b%s%b\n' "$C_ERR" "error: $*" "$C_RESET" >&2; exit 1; }

YES=0
MAX_AGE_DAYS=7
REPO_ROOT=""

for arg in "$@"; do
  case "$arg" in
    --yes) YES=1 ;;
    --max-age=*) MAX_AGE_DAYS="${arg#*=}" ;;
    --repo=*) REPO_ROOT="${arg#*=}" ;;
    --help|-h)
      sed -n '28,40p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      err "unknown option: $arg — run with --help for usage."
      ;;
  esac
done

if ! [[ "$MAX_AGE_DAYS" =~ ^[0-9]+$ ]] || [[ "$MAX_AGE_DAYS" -lt 1 ]]; then
  err "--max-age must be a positive integer"
fi

if [[ -z "$REPO_ROOT" ]]; then
  if ! REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    err "not inside a git repository (use --repo=<path>)"
  fi
fi

# Convention (two forms):
#   bundle:   $LAZIBLE_TMPDIR/jcode/<repo>-<short-sha>/wt-<label>/
#   jcode:    $TMPDIR/swarm-<user>/<repo>-<short-sha>/wt-<label>/
#
# Bundle uses `LAZIBLE_TMPDIR` (default /tmp). Older jcode and any
# worker that bypasses bundle's `scratch-dir` helper still emit the
# native form (uses `$TMPDIR`). Sweep matches BOTH so it works on
# bundle-created AND jcode-native worktrees; the path itself is the
# only signal — sweep does not care which convention produced it.
WT_PATTERN='.*(/jcode/[^/]+-[0-9a-f]+/|/swarm-[^/]+/[^/]+/)wt-[^/]+/?$'

NOW=$(date +%s)
THRESHOLD=$((MAX_AGE_DAYS * 86400))

echo "swarm-sweep: searching for stale swarm worktrees in $REPO_ROOT"
echo "  max age: $MAX_AGE_DAYS days"
echo "  match: bundle form (\$LAZIBLE_TMPDIR/jcode/<repo>-<short-sha>/wt-*)"
echo "         jcode  form (\$TMPDIR/swarm-<user>/<repo>/wt-*)"

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
  echo "  hint: bundle worktrees live under \$LAZIBLE_TMPDIR/jcode/, jcode-native under \$TMPDIR/swarm-*/."
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