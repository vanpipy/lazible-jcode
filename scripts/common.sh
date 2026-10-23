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
