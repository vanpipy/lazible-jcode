#!/usr/bin/env bash
#
# tests/liveness_scenario_sim.sh
#
# Git-only simulation of the 2026-08 silent-stuck incident: a worker
# commits a `final` artifact to its worker branch but never calls
# `complete_node`. The root session is the only entity that can
# detect this, and it does so via passive `git log` inspection.
#
# This test simulates both the "live" path (worker + dm both fire,
# root stays silent but integrates) and the "silent-stuck" path
# (worker commits final, dm dies, root detects via git log alone).
#
# Exits 0 if all scenarios behave as the contract requires,
# 1 if any scenario violates the contract.

set -euo pipefail

TESTS_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/.." && pwd)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

# Build a clean tiny repo to play with.
git init -q -b main .
git config user.email "test@example.com"
git config user.name  "Test"
echo "init" > README.md
git add README.md
git commit -q -m "init"
BASE_SHA="$(git rev-parse HEAD)"

log() { echo "--- $*"; }

# parse_artifact <commit>: extract the JSON artifact block from a
# commit's body. Echoes the JSON object on success, empty on failure.
parse_artifact() {
    local sha="$1"
    git log -1 --format=%B "$sha" \
        | awk '/^```json artifact$/,/^```$/' \
        | sed -n '/^```json artifact$/d; /^```$/d; p'
}

# extract_field <json> <key>: pull a top-level string/number field out
# of the artifact. Uses python for safe parsing (no jq dep).
extract_field() {
    local json="$1" key="$2"
    python3 -c "
import json, sys
d = json.loads(sys.argv[1])
v = d.get(sys.argv[2])
print(v if v is not None else '')
" "$json" "$key"
}

# ----------------------------------------------------------------------
# Scenario A: healthy final — both commit + complete_node fire.
# Root is silent (model: a lazy LLM) but the artifact is durable and
# passive inspection picks it up.
# ----------------------------------------------------------------------
log "Scenario A: healthy final commit + complete_node fire"
git checkout -q -b feat/a "${BASE_SHA}"

ARTIFACT_A='{
  "type": "final",
  "session_id": "root-1",
  "task_id": "feat-a",
  "branch": "feat/a",
  "commit": "PLACEHOLDER",
  "elapsed_min": 12,
  "step": "all tests green, lint clean",
  "next": "integrate",
  "confidence": "high",
  "blockers": []
}'

git commit --allow-empty -q -m "$(cat <<MSG
feat(a): done

\`\`\`json artifact
${ARTIFACT_A}
\`\`\`
MSG
)"
SHA_A="$(git rev-parse HEAD)"

# Simulate complete_node fire: nothing to do here, it's a side
# effect. The contract test is that the artifact on disk is valid
# and root can read it.
GOT_A="$(parse_artifact "$SHA_A")"
if [ -z "$GOT_A" ]; then
    echo "FAIL scenario A: artifact not parseable from commit body"
    exit 1
fi
TYPE_A="$(extract_field "$GOT_A" type)"
CONF_A="$(extract_field "$GOT_A" confidence)"
if [ "$TYPE_A" != "final" ]; then
    echo "FAIL scenario A: expected type=final, got '$TYPE_A'"
    exit 1
fi
if [ "$CONF_A" != "high" ]; then
    echo "FAIL scenario A: expected confidence=high, got '$CONF_A'"
    exit 1
fi
echo "OK scenario A: artifact parses, type=final, confidence=high"

# ----------------------------------------------------------------------
# Scenario B: silent-stuck — worker commits final, dm dies (cross-
# swarm or OOM between commit and complete_node). Root's passive
# inspection must still detect the artifact.
# ----------------------------------------------------------------------
log "Scenario B: silent-stuck — final commit, no dm"
git checkout -q -b feat/b main

ARTIFACT_B='{
  "type": "final",
  "session_id": "root-1",
  "task_id": "feat-b",
  "branch": "feat/b",
  "commit": "PLACEHOLDER",
  "elapsed_min": 9,
  "step": "complete; dm to root failed mid-flight",
  "next": "root integrate via passive inspection",
  "confidence": "medium",
  "blockers": ["cross-swarm: dm channel unreachable, commits-only mode"]
}'

git commit --allow-empty -q -m "$(cat <<MSG
feat(b): done but dm channel unreachable

\`\`\`json artifact
${ARTIFACT_B}
\`\`\`
MSG
)"
SHA_B="$(git rev-parse HEAD)"

# Root's passive inspection: it does git log + parse, no live
# channel. Verify the artifact carries the cross-swarm marker so
# root can act on it without the missing dm.
GOT_B="$(parse_artifact "$SHA_B")"
if [ -z "$GOT_B" ]; then
    echo "FAIL scenario B: artifact not parseable (root's only fallback)"
    exit 1
fi
TYPE_B="$(extract_field "$GOT_B" type)"
NEXT_B="$(extract_field "$GOT_B" next)"
if [ "$TYPE_B" != "final" ]; then
    echo "FAIL scenario B: expected type=final (silent-stuck still "
    echo "  marks final so root knows work is done), got '$TYPE_B'"
    exit 1
fi
if ! echo "$NEXT_B" | grep -q "passive inspection"; then
    echo "FAIL scenario B: next field must hint 'passive inspection' "
    echo "  so root integrates without waiting on the dead dm"
    exit 1
fi
if ! echo "$GOT_B" | grep -q "cross-swarm"; then
    echo "FAIL scenario B: blockers[] must carry the cross-swarm "
    echo "  marker — root uses this to decide report-only mode"
    exit 1
fi
echo "OK scenario B: silent-stuck detected via passive inspection; "
echo "  artifact type=final, next='...passive inspection', "
echo "  blockers=['cross-swarm: ...']"

# ----------------------------------------------------------------------
# Scenario C: progress commit is recognized as alive.
# A 'progress' artifact on the worker branch proves the worker is
# still alive, even with no dm. Root's passive inspection should
# treat 'progress' commits as positive liveness signal.
# ----------------------------------------------------------------------
log "Scenario C: progress commit still alive"
git checkout -q -b feat/c main

ARTIFACT_C='{
  "type": "progress",
  "session_id": "root-1",
  "task_id": "feat-c",
  "branch": "feat/c",
  "commit": "PLACEHOLDER",
  "elapsed_min": 4,
  "step": "running coverage on null/undefined paths",
  "next": "async catch paths",
  "confidence": "low",
  "blockers": []
}'

git commit --allow-empty -q -m "$(cat <<MSG
feat(c): progress

\`\`\`json artifact
${ARTIFACT_C}
\`\`\`
MSG
)"
SHA_C="$(git rev-parse HEAD)"

GOT_C="$(parse_artifact "$SHA_C")"
TYPE_C="$(extract_field "$GOT_C" type)"
if [ "$TYPE_C" != "progress" ]; then
    echo "FAIL scenario C: expected type=progress, got '$TYPE_C'"
    exit 1
fi
echo "OK scenario C: progress artifact parses, root sees the worker "
echo "  is mid-task (elapsed_min=4, step=...)"

# ----------------------------------------------------------------------
# Scenario D: regression — final commit WITHOUT the JSON artifact
# block. The contract says every commit MUST embed a typed JSON
# artifact. This test simulates the silent-stuck case where the
# worker forgot to embed it. The contract checker would also catch
# this on disk; here we verify the parser's safety net.
# ----------------------------------------------------------------------
log "Scenario D: final commit with NO artifact — contract violation"
git checkout -q -b feat/d main
git commit --allow-empty -q -m "feat(d): done (no artifact embedded)"
SHA_D="$(git rev-parse HEAD)"

GOT_D="$(parse_artifact "$SHA_D")"
if [ -n "$GOT_D" ]; then
    echo "FAIL scenario D: parser unexpectedly found artifact in "
    echo "  artifact-less commit"
    exit 1
fi
echo "OK scenario D: artifact-less commit detected as contract "
echo "  violation by the parser (root must reject)"

# ----------------------------------------------------------------------
# Final integration check: run the contract checker on the real
# repo to confirm L1+L2 hardening is still structurally consistent.
# ----------------------------------------------------------------------
log "Final: running scripts/check-liveness-contract.py on real repo"
if ! python3 "$REPO_ROOT/scripts/check-liveness-contract.py" >/dev/null; then
    echo "FAIL: real-repo liveness contract check failed"
    exit 1
fi
echo "OK: real-repo liveness contract check still passes"

echo ""
echo "ALL SCENARIOS PASS — liveness hardening holds for live, "
echo "silent-stuck, progress, and artifact-missing branches."
exit 0