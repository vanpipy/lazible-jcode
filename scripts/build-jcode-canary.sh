#!/usr/bin/env bash
# build-jcode-canary.sh — clone jcode source, apply lazible-jcode patches,
# build a local canary binary that carries the enhanced base system prompt.
#
# This is the "selfdev" leg of the lazible-jcode install flow. After this
# script finishes, the canary at $INSTALL_DIR/jcode-canary embeds:
#   - jcode-patches/swarm-coordinator-first.patch applied to
#     crates/jcode-base/src/prompt/system_prompt.md
# so the base system prompt is genuinely swarm-coordinator-first, not just an
# overlay appended after it.
#
# Usage:
#   scripts/build-jcode-canary.sh [options]
#
# Options:
#   --source-dir <dir>     Where to clone / find jcode source.
#                          Default: $HOME/Project/jcode
#   --output-dir <dir>     Where to install the canary binary.
#                          Default: $HOME/.local/bin
#   --canary-name <name>   Name of the canary binary. Default: jcode-canary
#   --jcode-version <v>    Pin a release tag (e.g. v0.65.0). Default: latest
#                          stable release tag of 1jehuang/jcode.
#   --from-source          Use the already-checked-out source-dir (no clone).
#   --replace-main         Replace ~/.local/bin/jcode with the canary (the
#                          normal install) instead of installing side-by-side.
#   --clean                Wipe source-dir before cloning (use when upgrading
#                          to a new jcode version).
#   --dry-run              Print the plan without writing or compiling.
#   -h, --help             Show this help.
#
# Exit codes:
#   0  success
#   1  user-facing error (missing tool, git failure, patch conflict)
#   2  build error (cargo exit non-zero)
#   3  install error (cannot write to output-dir)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PATCH_FILE="$REPO_ROOT/jcode-patches/swarm-coordinator-first.patch"
NEW_PROMPT_FILE="$REPO_ROOT/jcode-patches/swarm-coordinator-first.system_prompt.md"
TARGET_FILE="crates/jcode-base/src/prompt/system_prompt.md"

# Defaults
SOURCE_DIR="${JCODE_SOURCE_DIR:-$HOME/Project/jcode}"
OUTPUT_DIR="${JCODE_INSTALL_DIR:-$HOME/.local/bin}"
CANARY_NAME="jcode-canary"
JCODE_VERSION=""
FROM_SOURCE=0
REPLACE_MAIN=0
CLEAN=0
DRY_RUN=0

# Color helpers (auto-disable when not a TTY)
if [[ -t 1 ]]; then
    C_BLUE=$'\033[1;34m'; C_YELLOW=$'\033[1;33m'; C_RED=$'\033[1;31m'; C_RST=$'\033[0m'
else
    C_BLUE=""; C_YELLOW=""; C_RED=""; C_RST=""
fi
log_step()  { printf "${C_BLUE}── %s ──${C_RST}\n" "$*"; }
log_warn()  { printf "${C_YELLOW}warning: %s${C_RST}\n" "$*" >&2; }
log_err()   { printf "${C_RED}error: %s${C_RST}\n" "$*" >&2; }
log_dry()   { printf "${C_YELLOW}[dry-run] %s${C_RST}\n" "$*"; }

usage() {
    sed -n '2,/^set -euo/s/^# \{0,1\}//p' "$0" | head -n -1
    exit "${1:-0}"
}

# --- arg parsing ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --source-dir)    SOURCE_DIR="$2"; shift 2 ;;
        --output-dir)    OUTPUT_DIR="$2"; shift 2 ;;
        --canary-name)   CANARY_NAME="$2"; shift 2 ;;
        --jcode-version) JCODE_VERSION="$2"; shift 2 ;;
        --from-source)   FROM_SOURCE=1; shift ;;
        --replace-main)  REPLACE_MAIN=1; shift ;;
        --clean)         CLEAN=1; shift ;;
        --dry-run)       DRY_RUN=1; shift ;;
        -h|--help)       usage 0 ;;
        *) log_err "unknown flag: $1"; usage 1 ;;
    esac
done

# --- preflight ---
for tool in git cargo; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        log_err "required tool '$tool' not found in PATH"
        exit 1
    fi
done

if [[ ! -f "$PATCH_FILE" ]]; then
    log_err "patch file not found: $PATCH_FILE"
    log_err "this script must run from inside the lazible-jcode checkout."
    exit 1
fi
if [[ ! -f "$NEW_PROMPT_FILE" ]]; then
    log_err "new prompt file not found: $NEW_PROMPT_FILE"
    exit 1
fi

run_or_dry() {
    # run_or_dry <description> <command...>
    local desc="$1"; shift
    if [[ "$DRY_RUN" -eq 1 ]]; then
        log_dry "$desc — would run: $*"
    else
        log_step "$desc"
        "$@"
    fi
}

# --- step 1: ensure source ---
log_step "step 1/4: prepare jcode source at $SOURCE_DIR"

if [[ "$FROM_SOURCE" -eq 1 ]]; then
    if [[ ! -d "$SOURCE_DIR/.git" ]]; then
        log_err "--from-source but $SOURCE_DIR is not a git repo"
        exit 1
    fi
    log_step "using existing source-dir (no clone, no fetch)"
else
    if [[ -d "$SOURCE_DIR/.git" ]]; then
        if [[ "$CLEAN" -eq 1 ]]; then
            run_or_dry "clean existing source" rm -rf "$SOURCE_DIR"
        else
            log_step "source-dir already exists; reusing (pass --clean to wipe)"
        fi
    fi

    if [[ ! -d "$SOURCE_DIR/.git" ]]; then
        mkdir -p "$(dirname "$SOURCE_DIR")"
        if [[ -n "$JCODE_VERSION" ]]; then
            run_or_dry "clone jcode at tag $JCODE_VERSION" \
                git clone --depth 1 --branch "$JCODE_VERSION" \
                    https://github.com/1jehuang/jcode.git "$SOURCE_DIR"
        else
            run_or_dry "clone jcode (default branch)" \
                git clone --depth 1 https://github.com/1jehuang/jcode.git "$SOURCE_DIR"
        fi
    fi
fi

# --- step 2: apply patch ---
log_step "step 2/4: apply lazible-jcode patch"

# Reset the target file to upstream clean state before applying. Without this,
# reusing a source-dir from a previous build (where the patch was already
# applied) makes `git apply --check` fail: the patch expects the original
# upstream content, not the patched content. `git checkout HEAD -- <file>`
# restores the file to whatever the current branch's HEAD has, which for
# default-branch clones is upstream master.
if [[ "$DRY_RUN" -eq 0 ]]; then
    (cd "$SOURCE_DIR" && git checkout HEAD -- "$TARGET_FILE" 2>/dev/null) || true

    # Verify the patch is applicable. If not, the upstream prompt file drifted.
    if ! (cd "$SOURCE_DIR" && git apply --check "$PATCH_FILE" 2>&1); then
        log_err "patch no longer applies cleanly to upstream jcode."
        log_err "the upstream system_prompt.md has drifted."
        log_err "fix: regenerate the patch — see docs/SELFDEV.md §4 (re-syncing)."
        exit 1
    fi
    (cd "$SOURCE_DIR" && git apply "$PATCH_FILE")
    log_step "patch applied (1 file changed, identity + autonomy + spawn hygiene + verification)"
else
    log_dry "git checkout HEAD -- $TARGET_FILE"
    log_dry "git apply --check $PATCH_FILE"
    log_dry "git apply $PATCH_FILE"
fi

# --- step 3: cargo build ---
log_step "step 3/4: cargo build --release (this takes a while)"

if [[ "$DRY_RUN" -eq 0 ]]; then
    (cd "$SOURCE_DIR" && cargo build --release --bin jcode) || {
        log_err "cargo build failed (exit $?)"
        exit 2
    }
else
    log_dry "cargo build --release --bin jcode"
fi

BUILT_BIN="$SOURCE_DIR/target/release/jcode"
if [[ "$DRY_RUN" -eq 0 && ! -x "$BUILT_BIN" ]]; then
    log_err "expected built binary at $BUILT_BIN but it is missing"
    exit 2
fi

# --- step 4: install ---
log_step "step 4/4: install canary"

mkdir -p "$OUTPUT_DIR"

CANARY_PATH="$OUTPUT_DIR/$CANARY_NAME"
if [[ "$DRY_RUN" -eq 0 ]]; then
    cp "$BUILT_BIN" "$CANARY_PATH"
    chmod +x "$CANARY_PATH"
else
    log_dry "cp $BUILT_BIN $CANARY_PATH"
fi
log_step "installed canary → $CANARY_PATH"

if [[ "$REPLACE_MAIN" -eq 1 ]]; then
    MAIN_PATH="$OUTPUT_DIR/jcode"
    # Don't overwrite a non-lazible-jcode-owned jcode binary without backup.
    if [[ -e "$MAIN_PATH" && "$MAIN_PATH" != "$CANARY_PATH" ]]; then
        BACKUP="$MAIN_PATH.bak.$(date +%Y%m%d%H%M%S)"
        if [[ "$DRY_RUN" -eq 0 ]]; then
            cp "$MAIN_PATH" "$BACKUP"
            log_warn "backed up existing jcode → $BACKUP"
        else
            log_dry "would back up existing jcode → $BACKUP"
        fi
    fi
    if [[ "$DRY_RUN" -eq 0 ]]; then
        cp "$BUILT_BIN" "$MAIN_PATH"
        chmod +x "$MAIN_PATH"
    else
        log_dry "cp $BUILT_BIN $MAIN_PATH"
    fi
    log_step "replaced main jcode binary"
fi

# --- summary ---
echo ""
echo "Build summary:"
echo "  source-dir:    $SOURCE_DIR"
echo "  patch:         $PATCH_FILE"
echo "  applied to:    $TARGET_FILE"
echo "  canary binary: $CANARY_PATH"
echo "  replace main:  $([[ $REPLACE_MAIN -eq 1 ]] && echo yes || echo "no (side-by-side)")"
echo ""
echo "Smoke test:"
echo "  $CANARY_PATH --version"
echo "  $CANARY_PATH run 'say hello'"

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo ""
    echo "(dry-run) no changes were written, no compile was performed."
fi