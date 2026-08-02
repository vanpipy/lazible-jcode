#!/usr/bin/env bash
# scripts/uninstall.sh — remove jcode binaries and the lazible-jcode overlay.
#
# Default: keep ~/.jcode/ (config, auth, sessions, logs, memory) so a clean
#           reinstall picks up where you left off.
#   --purge         Also wipe ~/.jcode/ entirely. Use when recovering from a broken
#                   install or before handing the machine off to someone else.
#   --keep-overlay  Do not remove the lazible-jcode overlay/swarm/roles symlinks
#                   under ~/.jcode/. (Useful when ~/.jcode/ survives but you want
#                   to wipe jcode binaries.)
#   --dry-run       Print the plan without touching anything.
#   --yes           Skip the confirmation prompt.
#   --install-dir <dir>  Launcher dir to unlink. Default: \$HOME/.local/bin
#   --jcode-home <dir>   jcode home dir. Default: \$HOME/.jcode
#   -h, --help      Show usage.
#
# This script never touches shell rc files. Use `git restore` or your editor
# if you want to undo the PATH line the installer added.
#
# Symlink cleanup is safe-by-design: only removes symlinks that point INSIDE
# the lazible-jcode checkout (i.e. were installed by install.sh). User-owned
# files or symlinks to other locations are preserved.
set -euo pipefail

PURGE=0
KEEP_OVERLAY=0
DRY_RUN=0
YES=0
INSTALL_DIR="${JCODE_INSTALL_DIR:-$HOME/.local/bin}"
JCODE_HOME="${JCODE_HOME:-$HOME/.jcode}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

print_help() {
  cat <<EOF
Usage: $0 [options]

Remove the jcode launcher and (by default) the lazible-jcode overlay
symlinks at ~/.jcode/. Keeps config, auth, sessions, logs, and memory
under ~/.jcode/.

Options:
  --purge           Also wipe ~/.jcode/ entirely (config, auth, sessions, logs).
  --keep-overlay    Do NOT remove overlay/swarm/roles symlinks (only jcode binary).
  --dry-run         Print the plan only.
  --yes             Skip the confirmation prompt.
  --install-dir <dir>  Launcher dir to unlink. Default: \$HOME/.local/bin
  --jcode-home <dir>   jcode home dir. Default: \$HOME/.jcode
  -h, --help        Show usage.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --purge)        PURGE=1; shift ;;
    --keep-overlay) KEEP_OVERLAY=1; shift ;;
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

info() { printf '\033[1;34m%s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*" >&2; }

# Remove a symlink only if it points inside the lazible-jcode checkout.
# This protects users who may have manually pointed these slots elsewhere.
remove_owned_symlink() {
  local dst="$1" label="$2"
  if [[ ! -L "$dst" ]]; then
    return 0
  fi
  local target
  target="$(readlink "$dst")"
  # Resolve to absolute path for comparison
  local abs_target
  abs_target="$(cd "$(dirname "$dst")" && cd "$target" 2>/dev/null && pwd || echo "$target")"
  case "$abs_target" in
    "$REPO_ROOT"/*)
      info "removing $label symlink: $dst → $target"
      run rm -f "$dst"
      ;;
    *)
      warn "skipping $label — symlink points outside lazible-jcode checkout: $dst → $target"
      ;;
  esac
}

# ── announce plan ──────────────────────────────────────────────────────────────
info "Plan:"
info "  launcher:        $INSTALL_DIR/jcode"
info "  builds dir:      $JCODE_HOME/builds/"
if [[ "$PURGE" == "1" ]]; then
  info "  full purge of:   $JCODE_HOME/"
elif [[ "$KEEP_OVERLAY" == "1" ]]; then
  info "  preserve:        overlay/swarm/roles symlinks under $JCODE_HOME/"
  info "  preserve:        $JCODE_HOME/{config.toml,mcp.json,auth*,logs,sessions,memory}"
else
  info "  overlay cleanup: $JCODE_HOME/{prompt-overlay.md,swarm-prompt.md,roles/}"
  info "  preserve:        $JCODE_HOME/{config.toml,mcp.json,auth*,logs,sessions,memory}"
fi
info "  dry run:         $DRY_RUN"

if [[ "$DRY_RUN" == "1" ]]; then
  info "(dry-run) no changes made"
  exit 0
fi

if [[ "$YES" != "1" ]]; then
  printf 'Proceed? [y/N] '
  read -r ans
  [[ "$ans" == "y" || "$ans" == "Y" ]] || { echo "aborted"; exit 1; }
fi

# ── remove jcode binaries ──────────────────────────────────────────────────────
targets=(
  "$INSTALL_DIR/jcode"
  "$JCODE_HOME/builds/stable/jcode"
  "$JCODE_HOME/builds/current/jcode"
)

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

# ── remove lazible-jcode overlay symlinks ──────────────────────────────────────
if [[ "$KEEP_OVERLAY" != "1" ]]; then
  remove_owned_symlink "$JCODE_HOME/prompt-overlay.md" "prompt-overlay"
  remove_owned_symlink "$JCODE_HOME/swarm-prompt.md"   "swarm-prompt"
  remove_owned_symlink "$JCODE_HOME/roles"             "roles"
fi

# ── purge or preserve ──────────────────────────────────────────────────────────
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
  info "Tip: rerun $REPO_ROOT/scripts/install.sh to install again."
fi