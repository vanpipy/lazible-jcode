#!/usr/bin/env bash
# scripts/uninstall.sh — remove jcode binaries and the launcher.
#
# Default: keep ~/.jcode/ (config, auth, sessions, logs, memory) so a clean
#           reinstall picks up where you left off.
#   --purge  Also wipe ~/.jcode/ entirely. Use when recovering from a broken
#            install or before handing the machine off to someone else.
#   --dry-run Print the plan without touching anything.
#   --yes    Skip the confirmation prompt.
#   --help   Show usage.
#
# This script never touches shell rc files. Use `git restore` or your editor
# if you want to undo the PATH line the installer added.
set -euo pipefail

PURGE=0
DRY_RUN=0
YES=0
INSTALL_DIR="${JCODE_INSTALL_DIR:-$HOME/.local/bin}"
JCODE_HOME="${JCODE_HOME:-$HOME/.jcode}"

print_help() {
  cat <<EOF
Usage: $0 [options]

Remove the jcode launcher and (by default) the versioned builds in ~/.jcode/builds.
Keeps config, auth, sessions, logs, and memory under ~/.jcode/.

Options:
  --purge       Also wipe ~/.jcode/ entirely (config, auth, sessions, logs).
  --dry-run     Print the plan only.
  --yes         Skip the confirmation prompt.
  --install-dir <dir>  Launcher dir to unlink. Default: \$HOME/.local/bin
  --jcode-home  <dir>  jcode home dir. Default: \$HOME/.jcode
  -h, --help    Show this help and exit.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --purge)        PURGE=1; shift ;;
    --dry-run)      DRY_RUN=1; shift ;;
    --yes|-y)       YES=1; shift ;;
    --install-dir)  INSTALL_DIR="${2:-}"; shift 2 ;;
    --jcode-home)   JCODE_HOME="${2:-}"; shift 2 ;;
    -h|--help)      print_help; exit 0 ;;
    *) echo "error: unknown flag: $1" >&2; print_help >&2; exit 1 ;;
  esac
done

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[dry-run] %s\n' "$*"
  else
    "$@"
  fi
}

targets=(
  "$INSTALL_DIR/jcode"
  "$JCODE_HOME/builds/stable/jcode"
  "$JCODE_HOME/builds/current/jcode"
)

info() { printf '\033[1;34m%s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*" >&2; }

info "Plan:"
info "  launcher:        $INSTALL_DIR/jcode"
info "  builds dir:      $JCODE_HOME/builds/"
if [[ "$PURGE" == "1" ]]; then
  info "  full purge of:   $JCODE_HOME/"
else
  info "  preserve:        $JCODE_HOME/{config.toml,mcp.json,auth*,logs,sessions,memory}"
fi

if [[ "$DRY_RUN" == "1" ]]; then
  info "(dry-run) no changes made"
  exit 0
fi

if [[ "$YES" != "1" ]]; then
  printf 'Proceed? [y/N] '
  read -r ans
  [[ "$ans" == "y" || "$ans" == "Y" ]] || { echo "aborted"; exit 1; }
fi

for t in "${targets[@]}"; do
  if [[ -e "$t" || -L "$t" ]]; then
    info "removing $t"
    run rm -f "$t"
  fi
done

# Stable/current are symlinks; remove the version markers too.
for marker in stable-version current-version; do
  f="$JCODE_HOME/builds/$marker"
  if [[ -e "$f" ]]; then
    info "removing $f"
    run rm -f "$f"
  fi
done

# Optionally wipe everything
if [[ "$PURGE" == "1" ]]; then
  if [[ -d "$JCODE_HOME" ]]; then
    info "purging $JCODE_HOME"
    run rm -rf "$JCODE_HOME"
  fi
else
  # Leave ~/.jcode but offer to clear versioned binaries if the user wants.
  # We don't auto-remove ~/.jcode/builds/versions/ because rerunning the
  # installer uses it as a cache for downgrade/upgrade.
  info "Kept $JCODE_HOME/config* and $JCODE_HOME/builds/versions/."
  info "Re-run with --purge to wipe everything."
fi

info "✅ Uninstall complete."
if [[ "$PURGE" != "1" ]]; then
  info "Tip: rerun ./scripts/install.sh to install again."
fi