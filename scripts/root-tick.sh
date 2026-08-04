#!/usr/bin/env bash
# scripts/root-tick.sh
#
# Root session pre-action gate. Wrapper around swarm-state-monitor.py tick
# that:
#   1. Detects the current repo root (REPO_ROOT).
#   2. Runs `tick --include-stale` so root sees every worker branch regardless
#      of age — silent-stuck branches that are days old must NOT be hidden
#      when root is about to integrate or spawn.
#   3. Adds a clear ACTION NEEDED header that tells root exactly what to do,
#      so the wrapper's output is unambiguous even when root is skimming.
#   4. Exits with the same code as tick (0 / 1 / 2 / 3). Scripts that want to
#      block on root action can use this as a pre-condition.
#
# Why this wrapper exists
# ------------------------
# The overlay (prompt-overlay §12 root obligation 3, §13 smart postman)
# mandates that root inspect every active worker branch before any
# integration / spawn action. The discipline gap that exposed the
# silent-stuck failure mode in the postman-framework-hardening session was:
# root polled `swarm status` instead of doing `git log <branch>` passive
# inspection. This wrapper makes the discipline mechanical: root runs
# `scripts/root-tick.sh` before integrating, sees the action column, and
# either proceeds (exit 0) or pauses to investigate (exit 1/2).
#
# Usage
# -----
#   scripts/root-tick.sh                  # default: tick --include-stale
#   scripts/root-tick.sh --since=1        # tick with custom since window
#   scripts/root-tick.sh --no-include-stale   # honor tick's age filter
#
# Exit codes (inherited from tick):
#   0 = no worker action needed; safe to integrate / spawn
#   1 = at least one branch needs root action
#       (integrate-now / investigate / dm-heartbeat-reminder)
#       — root should pause, read the action column, and act directly
#   2 = at least one branch needs recoverer (silent / dead / no commits)
#       — spawn a recoverer worker per docs/POSTMAN_PROTOCOL.md
#   3 = git missing or not a repo
#
# See also:
#   docs/POSTMAN_PROTOCOL.md  — root-side protocol that consumes this output
#   docs/HEARTBEAT.md         — worker-side obligation this complements

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITOR_PY="$SCRIPT_DIR/swarm-state-monitor.py"

if [[ ! -f "$MONITOR_PY" ]]; then
    echo "root-tick.sh: cannot find $MONITOR_PY" >&2
    exit 3
fi

# Repo root detection: prefer `git rev-parse --show-toplevel` from CWD; if
# CWD is not in a git repo, fall back to the script's parent dir.
if git rev-parse --show-toplevel >/dev/null 2>&1; then
    REPO_ROOT="$(git rev-parse --show-toplevel)"
elif git rev-parse --git-dir >/dev/null 2>&1; then
    # Worktree case: --show-toplevel should have worked above, but for
    # robustness fall back to --git-dir's parent.
    REPO_ROOT="$(git rev-parse --git-dir | xargs dirname)"
else
    echo "root-tick.sh: not in a git repo (CWD=$(pwd))" >&2
    exit 3
fi

# Default args: --include-stale so silent-stuck branches always surface.
# Anything passed on the CLI overrides the default.
TICK_ARGS=(--include-stale)
for arg in "$@"; do
    case "$arg" in
        --no-include-stale)
            TICK_ARGS=()
            ;;
        --since=*)
            TICK_ARGS=(--include-stale "$arg")
            ;;
        *)
            # Forward unknown flags as-is.
            TICK_ARGS+=("$arg")
            ;;
    esac
done

echo "=== root-tick.sh ==="
echo "REPO_ROOT:    $REPO_ROOT"
echo "TICK_ARGS:    ${TICK_ARGS[*]}"
echo "EXIT POLICY:  0 = safe to integrate; 1 = pause (integrate-now/investigate); 2 = recoverer"
echo

# Run tick from REPO_ROOT so worker-branch discovery is consistent.
cd "$REPO_ROOT"
set +e
python3 "$MONITOR_PY" tick "${TICK_ARGS[@]}"
TICK_EXIT=$?
set -e

echo
case "$TICK_EXIT" in
    0)
        echo "=== ACTION: none. Safe to integrate / spawn. ==="
        ;;
    1)
        echo "=== ACTION: PAUSE. At least one branch has recommended_action" \
             "in {integrate-now, investigate, dm-heartbeat-reminder}. ==="
        echo "===         Re-read the action column; integrate from the" \
             "commit even if complete_node never arrived. ==="
        ;;
    2)
        echo "=== ACTION: SPAWN RECOVERER. At least one branch is silent /" \
             "dead / no commits. ==="
        echo "===         After recovery, re-run root-tick.sh to confirm" \
             "all-clear before integrating. ==="
        ;;
    *)
        echo "=== ACTION: error (exit $TICK_EXIT). Re-run manually for" \
             "details. ==="
        ;;
esac

exit "$TICK_EXIT"