#!/usr/bin/env bash
# scripts/uninstall.sh — remove jcode + lazible-jcode overlay.
#
# Inverse of install.sh. Removes the symlinks it created and the jcode
# binary it installed. Does NOT remove ~/.jcode/ entirely — config and
# auth files are kept so a clean reinstall picks up where you left off.
#
# Usage:
#   ./scripts/uninstall.sh [--purge] [--yes]
#
# Flags:
#   --purge   Also remove ~/.jcode/ entirely (config + auth + sessions +
#             memory). Use this for a full reset.
#   --yes     Skip the confirmation prompt.
#   -h, --help  Show this help.

set -euo pipefail

JCODE_HOME="${JCODE_HOME:-$HOME/.jcode}"
INSTALL_DIR="${JCODE_INSTALL_DIR:-$HOME/.local/bin}"
PURGE=0
ASSUME_YES=0

print_help() {
  cat <<EOF
Usage: $0 [options]

Remove jcode + lazible-jcode overlay symlinks and binary.

By default, ~/.jcode/ is kept (config / auth / sessions preserved).
Pass --purge to wipe it entirely.

Options:
  --purge   Wipe ~/.jcode/ entirely after removing symlinks.
  --yes     Skip the confirmation prompt.
  -h, --help   Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --purge)   PURGE=1; shift ;;
    --yes)     ASSUME_YES=1; shift ;;
    -h|--help) print_help; exit 0 ;;
    *) echo "error: unknown flag: $1" >&2; print_help >&2; exit 1 ;;
  esac
done

info() { printf '\033[1;34m%s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*" >&2; }

# ── confirmation ─────────────────────────────────────────────────────────────
if [[ "$ASSUME_YES" -ne 1 ]]; then
  printf "This will remove:\n"
  printf "  - jcode binary at $INSTALL_DIR/jcode (if installed by lazible-jcode)\n"
  printf "  - symlinks: $JCODE_HOME/{prompt-overlay,swarm-prompt,ARCHITECTURE,AGENTS}.md\n"
  printf "  - symlinks: $JCODE_HOME/roles/*.md\n"
  if [[ "$PURGE" -eq 1 ]]; then
    printf "  - the entire $JCODE_HOME/ directory (--purge)\n"
  else
    printf "  - nothing else from $JCODE_HOME/ (config / auth preserved)\n"
  fi
  printf "\nProceed? [y/N] "
  read -r ans
  [[ "$ans" =~ ^[Yy]$ ]] || { info "aborted"; exit 0; }
fi

# ── remove symlinks created by install.sh ────────────────────────────────────
info "removing symlinks under $JCODE_HOME"
for link in \
  "$JCODE_HOME/prompt-overlay.md" \
  "$JCODE_HOME/swarm-prompt.md" \
  "$JCODE_HOME/ARCHITECTURE.md" \
  "$JCODE_HOME/AGENTS.md"
do
  if [[ -L "$link" ]]; then
    rm -f "$link"
    info "removed $link"
  fi
done

if [[ -d "$JCODE_HOME/roles" ]]; then
  for link in "$JCODE_HOME/roles/"*.md; do
    [[ -L "$link" ]] || continue
    rm -f "$link"
    info "removed $link"
  done
fi

# ── optional purge ───────────────────────────────────────────────────────────
if [[ "$PURGE" -eq 1 ]]; then
  warn "purging $JCODE_HOME/"
  rm -rf "$JCODE_HOME"
fi

# ── remove jcode binary if it looks like ours ────────────────────────────────
jcode_path="$INSTALL_DIR/jcode"
if [[ -x "$jcode_path" ]]; then
  warn "removing $jcode_path"
  rm -f "$jcode_path"
  # Also remove the most recent backup if present.
  latest_bak="$(ls -t "$INSTALL_DIR"/jcode.bak.* 2>/dev/null | head -1 || true)"
  if [[ -n "$latest_bak" ]]; then
    info "left in place: $latest_bak (most recent backup; remove manually if unwanted)"
  fi
fi

info "done"