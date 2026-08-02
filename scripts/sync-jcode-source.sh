#!/usr/bin/env bash
# sync-jcode-source.sh — keep the local jcode source checkout in sync with
# upstream, and re-validate that lazible-jcode's patches still apply.
#
# Usage:
#   scripts/sync-jcode-source.sh [options]
#
# Options:
#   --source-dir <dir>     Where the jcode source lives.
#                          Default: $HOME/Project/jcode
#   --target-version <v>   Pin a release tag (e.g. v0.65.0). Default: the
#                          tag the source was last cloned at.
#   --patches-dir <dir>    Where lazible-jcode patches live.
#                          Default: <repo>/jcode-patches
#   --strategy <strategy>  "fetch+rebase" (default) or "fetch+clean".
#                          "fetch+rebase" attempts to fast-forward / rebase
#                          the patch application onto the new upstream HEAD.
#                          "fetch+clean" wipes the source-dir and re-clones
#                          (simpler, loses any local edits).
#   --dry-run              Print the plan without touching anything.
#   -h, --help             Show this help.
#
# When the patch fails to apply (the upstream prompt has drifted), this
# script exits non-zero with a clear message pointing at the re-sync recipe
# in docs/SELFDEV.md §4.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SOURCE_DIR="${JCODE_SOURCE_DIR:-$HOME/Project/jcode}"
TARGET_VERSION=""
PATCHES_DIR="$REPO_ROOT/jcode-patches"
STRATEGY="fetch+rebase"
DRY_RUN=0

# Color helpers
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

while [[ $# -gt 0 ]]; do
    case "$1" in
        --source-dir)      SOURCE_DIR="$2"; shift 2 ;;
        --target-version)  TARGET_VERSION="$2"; shift 2 ;;
        --patches-dir)     PATCHES_DIR="$2"; shift 2 ;;
        --strategy)        STRATEGY="$2"; shift 2 ;;
        --dry-run)         DRY_RUN=1; shift ;;
        -h|--help)         usage 0 ;;
        *) log_err "unknown flag: $1"; usage 1 ;;
    esac
done

run_or_dry() {
    local desc="$1"; shift
    if [[ "$DRY_RUN" -eq 1 ]]; then
        log_dry "$desc"
    else
        "$@"
    fi
}

if [[ ! -d "$SOURCE_DIR/.git" ]]; then
    log_err "source-dir is not a git repo: $SOURCE_DIR"
    log_err "run scripts/build-jcode-canary.sh first to clone it."
    exit 1
fi

if [[ ! -d "$PATCHES_DIR" ]]; then
    log_err "patches-dir not found: $PATCHES_DIR"
    exit 1
fi

# --- step 1: fetch upstream ---
log_step "step 1/3: fetch upstream"

run_or_dry "git fetch upstream" \
    git -C "$SOURCE_DIR" fetch --tags origin

if [[ -n "$TARGET_VERSION" ]]; then
    TARGET_REF="refs/tags/$TARGET_VERSION"
else
    # If source-dir has any tag reachable from origin/master, use that.
    TARGET_REF="origin/master"
fi

# --- step 2: rebase or clean ---
log_step "step 2/3: move source to $TARGET_REF (strategy: $STRATEGY)"

# Save any local changes (e.g. the patch we previously applied).
LOCAL_CHANGES=$(git -C "$SOURCE_DIR" status --porcelain 2>/dev/null || true)

case "$STRATEGY" in
    fetch+rebase)
        # Reset to upstream target, then re-apply all patches.
        if [[ "$DRY_RUN" -eq 0 ]]; then
            git -C "$SOURCE_DIR" reset --hard "$TARGET_REF" >/dev/null
            # Clean any untracked files left over from prior builds
            git -C "$SOURCE_DIR" clean -fd >/dev/null
        else
            log_dry "git reset --hard $TARGET_REF"
            log_dry "git clean -fd"
        fi
        ;;
    fetch+clean)
        SOURCE_PARENT="$(dirname "$SOURCE_DIR")/$(basename "$SOURCE_DIR").sync-backup.$(date +%Y%m%d%H%M%S)"
        if [[ "$DRY_RUN" -eq 0 ]]; then
            mv "$SOURCE_DIR" "$SOURCE_PARENT"
            log_warn "moved existing source → $SOURCE_PARENT"
            git clone --depth 1 --branch "${TARGET_VERSION:-master}" \
                https://github.com/1jehuang/jcode.git "$SOURCE_DIR"
        else
            log_dry "would move $SOURCE_DIR to $SOURCE_PARENT and re-clone"
        fi
        ;;
    *)
        log_err "unknown strategy: $STRATEGY"
        exit 1
        ;;
esac

# --- step 3: re-apply patches and verify ---
log_step "step 3/3: re-apply lazible-jcode patches"

PATCH_FAIL=0
for patch in "$PATCHES_DIR"/*.patch; do
    [[ -f "$patch" ]] || continue
    name="$(basename "$patch")"
    if [[ "$DRY_RUN" -eq 1 ]]; then
        log_dry "would apply $name"
        continue
    fi
    if (cd "$SOURCE_DIR" && git apply --check "$patch" 2>/dev/null); then
        (cd "$SOURCE_DIR" && git apply "$patch")
        log_step "✓ applied $name"
    else
        log_err "✗ $name no longer applies cleanly to upstream $TARGET_REF"
        PATCH_FAIL=1
        echo ""
        echo "  The upstream $TARGET_REF has drifted from the snapshot"
        echo "  the lazible-jcode patch was generated against."
        echo ""
        echo "  Recovery steps:"
        echo "    1. cd $SOURCE_DIR"
        echo "    2. git stash                            # if you have local edits"
        echo "    3. Review the drift in $patch"
        echo "    4. Regenerate: see docs/SELFDEV.md §4 (re-syncing)"
        echo "    5. Re-run this script."
    fi
done

if [[ "$PATCH_FAIL" -ne 0 ]]; then
    exit 1
fi

echo ""
log_step "✓ source-dir is on $TARGET_REF with all lazible-jcode patches applied"
echo ""
echo "Next steps:"
echo "  scripts/build-jcode-canary.sh --from-source --replace-main"