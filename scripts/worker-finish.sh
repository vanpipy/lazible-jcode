#!/usr/bin/env bash
# scripts/worker-finish.sh — canonical worker.json writer.
#
# Workers call this at the moment of `complete_node` / final handoff. The
# script takes worker metadata as environment variables, validates them,
# and writes a structured JSON payload to disk atomically (write to .tmp,
# then mv). The JSON is the typed handoff artifact root reads to confirm
# what landed on the worker branch.
#
# Contract:
#   Required env vars (script errors if missing or empty):
#     WORKER_BRANCH        e.g. feat/worker-json_50e17e6
#     WORKER_COMMIT        final commit SHA on WORKER_BRANCH
#     WORKER_SUMMARY       one-line summary of the change
#     WORKER_FILES_CHANGED space-separated list of relative paths
#     WORKER_TEST_MODULE   e.g. scripts.test_worker_finish
#     WORKER_CONFIDENCE    low|medium|high
#   Optional env vars:
#     WORKER_OUTPUT        output path (default: ./worker.json at cwd)
#     WORKER_BLOCKERS      JSON array string (default: [])
#
# Exit codes:
#   0   success, JSON written; final path printed to stdout
#   1   validation failure (missing required env, bad confidence, etc.)
#   2   JSON build failure
#   3   atomic write failure
#
# Atomicity: the script writes to <output>.tmp and `mv`s to <output>. This
# avoids half-written files if the script is killed mid-write. The .tmp
# sidecar is removed on success; failure leaves it for inspection.
#
# Failure mode to avoid: committing worker.json in the implementation
# commit diff. Add it via `git commit --amend --no-edit` ONLY if you
# forgot; in any case, never let it appear in `git diff main..<branch>`.

set -euo pipefail

err() {
    # err <message> — print to stderr; exit 1.
    echo "worker-finish.sh: $*" >&2
    exit 1
}

# --- Validate required env vars ------------------------------------------

require_var() {
    # require_var <name> — error if unset or empty.
    local name="$1"
    local value="${!name:-}"
    if [[ -z "$value" ]]; then
        err "missing required env var: $name"
    fi
}

for v in WORKER_BRANCH WORKER_COMMIT WORKER_SUMMARY WORKER_FILES_CHANGED \
         WORKER_TEST_MODULE WORKER_CONFIDENCE; do
    require_var "$v"
done

# WORKER_BLOCKERS may be empty (no blockers); default to "[]" for jq/python.
: "${WORKER_BLOCKERS:=[]}"

case "$WORKER_CONFIDENCE" in
    low|medium|high) ;;
    *) err "WORKER_CONFIDENCE must be one of low|medium|high (got: '$WORKER_CONFIDENCE')" ;;
esac

# --- Resolve output path --------------------------------------------------

WORKER_OUTPUT="${WORKER_OUTPUT:-./worker.json}"

# Ensure the parent directory exists. atomic mv needs it.
parent_dir="$(dirname "$WORKER_OUTPUT")"
if [[ ! -d "$parent_dir" ]]; then
    mkdir -p "$parent_dir" || err "failed to create output directory: $parent_dir"
fi

tmp_path="${WORKER_OUTPUT}.tmp"

# --- Build JSON payload ---------------------------------------------------
#
# Detect jq first; fall back to python3. Both produce byte-identical output
# for the simple flat + 1-deep-nested shape we need.

build_json() {
    # All values pass through as bash vars; python3 json.dumps does the
    # escaping. space-separated files_changed becomes a JSON array.
    WORKER_BRANCH="$WORKER_BRANCH" \
    WORKER_COMMIT="$WORKER_COMMIT" \
    WORKER_SUMMARY="$WORKER_SUMMARY" \
    WORKER_FILES_CHANGED="$WORKER_FILES_CHANGED" \
    WORKER_TEST_MODULE="$WORKER_TEST_MODULE" \
    WORKER_CONFIDENCE="$WORKER_CONFIDENCE" \
    WORKER_BLOCKERS="$WORKER_BLOCKERS" \
    python3 - <<'PYEOF'
import json
import os
import sys

branch = os.environ["WORKER_BRANCH"]
commit = os.environ["WORKER_COMMIT"]
summary = os.environ["WORKER_SUMMARY"]
files_changed = os.environ["WORKER_FILES_CHANGED"].split()
test_module = os.environ["WORKER_TEST_MODULE"]
confidence = os.environ["WORKER_CONFIDENCE"]
blockers_raw = os.environ.get("WORKER_BLOCKERS", "[]")

try:
    blockers = json.loads(blockers_raw)
    if not isinstance(blockers, list):
        raise ValueError("WORKER_BLOCKERS must be a JSON array")
except (json.JSONDecodeError, ValueError) as exc:
    print(f"worker-finish.sh: invalid WORKER_BLOCKERS ({exc})", file=sys.stderr)
    sys.exit(2)

payload = {
    "branch": branch,
    "commit": commit,
    "summary": summary,
    "files_changed": files_changed,
    "gates_run": {
        "test_module": test_module,
        "bash_n_files": [os.environ.get("WORKER_BASH_N_FILES", "")] if os.environ.get("WORKER_BASH_N_FILES") else [],
    },
    "confidence": confidence,
    "blockers": blockers,
}
sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
sys.stdout.write("\n")
PYEOF
}

if ! json_payload="$(build_json)"; then
    err "JSON build failed"
fi

# --- Atomic write ---------------------------------------------------------

# Write tmp, fsync, then mv. mv is atomic on a single filesystem.
printf '%s' "$json_payload" > "$tmp_path" || {
    rm -f "$tmp_path"
    err "failed to write tmp file: $tmp_path"
}

mv "$tmp_path" "$WORKER_OUTPUT" || {
    rm -f "$tmp_path"
    err "failed to rename $tmp_path -> $WORKER_OUTPUT"
}

# --- Success --------------------------------------------------------------

echo "worker.json written: $WORKER_OUTPUT"
