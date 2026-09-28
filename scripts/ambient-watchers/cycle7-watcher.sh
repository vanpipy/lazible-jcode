#!/bin/bash
# Long-running cycle #7 watcher. Polls state.json + queue.json every 30s,
# emits progress every iteration, exits cleanly after 9 minutes
# (540s) so the parent can respawn without hitting bash tool's 10-min
# timeout cap (Bug G).
#
# Args:
#   $1 = expected fire time (human-readable, for log only)
#   $2 = start cycle count (for sanity: if state shows fewer cycles than this
#        something went very wrong)
#
# Uses python3 instead of jq (jq not installed on this system).
set -u

EXPECTED="${1:-unknown}"
START_CYCLES="${2:-7}"
MAX_RUNTIME=540   # 9 min : leaves 60s buffer under bash tool's 10-min hard cap
SLEEP_INTERVAL=30

# python helper that returns space-separated values: total q next_wake
read_state() {
    python3 -c "
import json, sys
try:
    s = json.load(open('/home/leroy/.jcode/ambient/state.json'))
    q = json.load(open('/home/leroy/.jcode/ambient/queue.json'))
    print(s.get('total_cycles', 0), len(q), s.get('status', {}).get('Scheduled', {}).get('next_wake', '-'))
except Exception as e:
    print('? ? ?', file=sys.stderr)
    sys.exit(0)
" 2>/dev/null
}

START_TS=$(date +%s)

echo "[$(date '+%H:%M:%S')] watcher started; expecting cycle #7 $EXPECTED (from total=$START_CYCLES)"
echo "[$(date '+%H:%M:%S')] will poll every ${SLEEP_INTERVAL}s, exit cleanly after ${MAX_RUNTIME}s"

ITER=0
while true; do
    ITER=$((ITER + 1))
    NOW=$(date +%s)
    ELAPSED=$((NOW - START_TS))

    READ=$(read_state)
    CYCLES=$(echo "$READ" | awk '{print $1}')
    QUEUE_LEN=$(echo "$READ" | awk '{print $2}')
    NEXT_WAKE=$(echo "$READ" | awk '{print $3}')

    if [ -n "$CYCLES" ] && [ "$CYCLES" -gt "$START_CYCLES" ] 2>/dev/null; then
        echo "[$(date '+%H:%M:%S')] iter=$ITER CYCLES=$CYCLES (>$START_CYCLES) : cycle #7+ FIRED detected! q=$QUEUE_LEN next_wake=$NEXT_WAKE"
        NEWEST=$(ls -t /home/leroy/.jcode/ambient/transcripts/*.json 2>/dev/null | head -1)
        echo "[$(date '+%H:%M:%S')] newest transcript: $NEWEST"
        exit 0
    fi

    REMAINING=$((MAX_RUNTIME - ELAPSED))
    echo "[$(date '+%H:%M:%S')] iter=$ITER elapsed=${ELAPSED}s remain=${REMAINING}s total=$CYCLES q=$QUEUE_LEN next_wake=$NEXT_WAKE"

    if [ $ELAPSED -ge $MAX_RUNTIME ]; then
        echo "[$(date '+%H:%M:%S')] max runtime ${MAX_RUNTIME}s reached, exiting cleanly (parent should respawn)"
        exit 0
    fi

    sleep $SLEEP_INTERVAL
done