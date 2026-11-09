# common.sh : shared by scripts/install and scripts/uninstall
#
# This file is sourced, never executed. It holds only what both scripts
# need: the path set, the --help printer, and the log prefix. Anything
# used by one script alone stays in that script.
#
# Sourcing is safe here because $0 is always the entry script, not this
# file. usage() reads the header comment of $0, so each script still
# prints its own help text, and log() derives its prefix from $0 too.

# shellcheck shell=bash
# The variables below are consumed by whichever script sources this file,
# which shellcheck cannot see. They are deliberately not exported.
# shellcheck disable=SC2034

set -euo pipefail

# Basename of the entry script: "install" or "uninstall". Used only as a
# log prefix, so it matches the [install] / [uninstall] tags both scripts
# have always printed.
SCRIPT_NAME="$(basename "$0")"

REPO="$(cd "$(dirname "$0")/.." && pwd)"

JCODE_CONFIG="$HOME/.jcode/config.toml"
SKILLS_HOME="$HOME/.jcode/skills"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/lazible-jcode"
STATE_FILE="$STATE_DIR/state.json"

usage() {
    # Print the leading comment block of the entry script, whatever length
    # it happens to be. $0 is install or uninstall, never common.sh.
    awk 'NR==1 {next} /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"
    exit 0
}

log() { echo "[$SCRIPT_NAME] $*"; }

err() { echo "[$SCRIPT_NAME] ERR: $*" >&2; }

# Is "$1" inside this repo, once symlinks are resolved?
#
# The repo holds the source of truth. Neither script may write into it or
# delete from it, because a symlink in the way would turn a normal install
# into a repo corruption. The check resolves the path first, so a symlinked
# ~/.jcode pointing back at the repo is caught too.
#
# readlink -m is used rather than -f: -f fails outright when a parent
# component does not exist, and the paths checked here routinely do not exist
# yet. -m resolves what it can and normalises the rest, which is exactly
# what a "where would this land" question needs.
inside_repo() {
    local target resolved
    target="$(readlink -m -- "$1" 2>/dev/null)" || return 1
    resolved="$(readlink -m -- "$REPO" 2>/dev/null)" || return 1
    [[ -n "$target" && -n "$resolved" ]] || return 1
    [[ "$target" == "$resolved" || "$target" == "$resolved"/* ]]
}

# Refuse to touch any of the given paths, if any of them resolves inside
# this repo.
#
# The check belongs here rather than in either script, because the two
# scripts must agree on exactly what the rule is. One script protecting the
# repo while the other does not is the failure mode this prevents.
guard_outside_repo() {
    local p
    for p in "$@"; do
        if inside_repo "$p"; then
            err "$p resolves inside this repo"
            err "$SCRIPT_NAME refuses to touch it. Fix the symlink first:"
            err "  rm $p && mkdir -p $p"
            exit 1
        fi
    done
}

# Refuse to REMOVE any of the given paths, if removing them would touch
# something inside this repo.
#
# There are two ways a removal can land inside the repo, and they need
# two different checks.
#
# CHECK 1: the path itself resolves inside the repo.
#
#   ~/.jcode/skills/swarm-engineering -> <repo>/config/skills/swarm-engineering
#
# The target resolves into the repo. rm -rf on that path removes the
# SYMLINK and not the repo's directory, so no harm happens, but the
# shape is still a redirect into the repo and is worth refusing.
#
# CHECK 2: the ENTRY lives inside the repo, even though the path points
# out of it.
#
#   ~/.jcode/skills              -> <repo>/config/skills
#   <repo>/config/skills/<skill> -> a directory OUTSIDE the repo
#
# The skill target $SKILLS_HOME/<skill> resolves to a directory outside
# the repo, so check 1 sees nothing wrong with it. But rm does not
# follow a final symlink: it removes the ENTRY, and that entry is the
# repo's own <repo>/config/skills/<skill>. Without check 2 the
# uninstaller deletes a file out of the repo and reports success.
#
# Check 1 asks "where does this path point". Check 2 asks "where does
# this entry live", which is the resolved parent plus the literal
# basename. The two disagree exactly in the dangerous case, so both run.
#
# Refusing on check 1 even though rm would be harmless there is
# deliberate. A redirect into the repo is a broken setup either way, and
# a refusal is cheap while a repo deletion is not.
#
# The parent is resolved with readlink -m, the same way inside_repo does
# it, so the two agree on how a path is normalised.
inside_repo_for_removal() {
    local parent resolved
    parent="$(dirname -- "$1")"
    # Resolve the PARENT only. Resolving the target itself would follow
    # the final symlink and then answer the wrong question: the entry rm
    # removes is the one named by the parent plus the literal basename,
    # not the thing that basename happens to point at.
    parent="$(readlink -m -- "$parent" 2>/dev/null)" || return 1
    resolved="$(readlink -m -- "$REPO" 2>/dev/null)" || return 1
    [[ -n "$parent" && -n "$resolved" ]] || return 1
    [[ "$parent" == "$resolved" || "$parent" == "$resolved"/* ]]
}

guard_outside_repo_for_removal() {
    local p
    for p in "$@"; do
        if inside_repo "$p"; then
            err "$p resolves inside this repo"
            err "$SCRIPT_NAME refuses to remove it. Fix the symlink first:"
            err "  rm $p && mkdir -p $p"
            exit 1
        fi
        if inside_repo_for_removal "$p"; then
            err "$p lives inside this repo"
            err "$SCRIPT_NAME refuses to remove it. Fix the symlink first:"
            err "  rm $p && mkdir -p $p"
            exit 1
        fi
    done
}
