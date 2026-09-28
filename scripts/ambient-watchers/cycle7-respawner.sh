#!/bin/bash
# Respawning wrapper for cycle-7-watcher.sh. Runs forever (until killed by
# user), respawning the watcher when it exits cleanly every ~9 min.
# Started via nohup so it survives shell exit.
#
# Usage: nohup bash /tmp/lazible-watch/cycle7-respawner.sh [EXPECTED] [START_CYCLES] &
#   EXPECTED      : human-readable expected fire time (cosmetic, for log only)
#   START_CYCLES  : current cycle count; watcher exits when state.total > this
# Defaults: EXPECTED="~25:36:44 CST" (cycle #7 fire time), START_CYCLES=6
set -u

WATCHER=/tmp/lazible-watch/cycle7-watcher.sh
EXPECTED="${1:-~25:36:44 CST}"
START_CYCLES="${2:-6}"
LOG_DIR=/tmp/lazible-watch
RESPAWN_COUNT=0

echo "[$(date '+%H:%M:%S')] respawner started, watching for cycle #$((START_CYCLES + 1))+ (total=$START_CYCLES → $((START_CYCLES + 1)), expected $EXPECTED)"

while true; do
    RESPAWN_COUNT=$((RESPAWN_COUNT + 1))
    LOG="$LOG_DIR/cycle7-watcher-$RESPAWN_COUNT.log"
    echo "[$(date '+%H:%M:%S')] spawning watcher #$RESPAWN_COUNT (log: $LOG)"
    bash "$WATCHER" "$EXPECTED" "$START_CYCLES" > "$LOG" 2>&1
    EXIT=$?
    echo "[$(date '+%H:%M:%S')] watcher #$RESPAWN_COUNT exited with code $EXIT"
    if [ $EXIT -eq 0 ] && grep -q "FIRED detected" "$LOG" 2>/dev/null; then
        echo "[$(date '+%H:%M:%S')] cycle #7+ FIRED : stopping respawner"
        exit 0
    fi
    # brief pause before respawn
    sleep 2
done