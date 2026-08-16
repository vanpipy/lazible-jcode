#!/usr/bin/env bash
# scripts/install.sh — lazible-jcode installer.
#
# Linear, unconditional, overwrite-by-default. Runs 3 steps every time:
#   1. Install jcode binary to ~/.local/bin/jcode via the upstream installer.
#   2. Symlink swarm/prompt-overlay.md, swarm/swarm-prompt.md,
#      swarm/ARCHITECTURE.md, and swarm/roles/*.md into ~/.jcode/.
#   3. Symlink AGENTS.md to ~/.jcode/AGENTS.md.
#
# No flags control which step runs or whether to overwrite. Overwriting is
# the point. Existing files at the destination are always backed up to
# <dst>.bak.<ts> before being replaced, so rerunning this script is safe.
#
# Usage:
#   ./scripts/install.sh             # run all 3 steps with defaults
#   ./scripts/install.sh --help      # show usage
#
# Every run does all 3 steps and overwrites every destination (backed up as
# <dst>.bak.<ts> first).

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

print_help() {
  cat <<EOF
Usage: $0 [options]

Linear install of jcode + lazible-jcode overlay. Runs 3 steps every time and
overwrites the destination unconditionally:

  1. Install jcode binary to ~/.local/bin/jcode via the upstream installer.
  2. Symlink swarm/prompt-overlay.md, swarm/swarm-prompt.md,
     swarm/ARCHITECTURE.md, and swarm/roles/*.md into ~/.jcode/.
  3. Symlink AGENTS.md to ~/.jcode/AGENTS.md.

Existing files at any destination are backed up to <dst>.bak.<timestamp>
before being replaced.

Options:
  -h, --help   Show this help.

Examples:
  # Default install.
  $0
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) print_help; exit 0 ;;
    *) echo "error: unknown flag: $1" >&2; print_help >&2; exit 1 ;;
  esac
done

# ── sanity ────────────────────────────────────────────────────────────────────
# Verify the lazible-jcode checkout has the minimum the installer needs.
for required in AGENTS.md swarm; do
  if [[ ! -e "$repo_root/$required" ]]; then
    echo "error: lazible-jcode checkout looks incomplete: missing $repo_root/$required" >&2
    exit 1
  fi
done

JCODE_HOME="${JCODE_HOME:-$HOME/.jcode}"
TIMESTAMP="$(date +%s)"

info() { printf '\033[1;34m%s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*" >&2; }
err()  { printf '\033[1;31merror: %s\033[0m\n' "$*" >&2; exit 1; }

# Overwrite a file or symlink unconditionally. If dst exists (regular file,
# symlink, or directory), back it up to <dst>.bak.<ts> first. If dst does not
# exist, just create it. Always links src as the final dst.
#
# Fast path: if dst is already a symlink pointing at src, do nothing. This
# keeps idempotent reruns from accumulating a symlink-of-a-symlink per run
# when the user just wants to refresh links that are already correct.
overwrite_link() {
  local src="$1" dst="$2" label="$3"
  [[ -e "$src" ]] || { warn "skip $label — source missing: $src"; return 0; }

  # Fast path: dst already links to src — nothing to do.
  if [[ -L "$dst" ]] && [[ "$(readlink "$dst")" == "$src" ]]; then
    info "unchanged $label → $src"
    return 0
  fi

  if [[ -e "$dst" || -L "$dst" ]]; then
    mv "$dst" "$dst.bak.$TIMESTAMP"
    warn "backed up $dst → $dst.bak.$TIMESTAMP"
  fi
  mkdir -p "$(dirname "$dst")"
  ln -s "$src" "$dst"
  info "linked $label → $src"
}

# ── step 1: install jcode binary via upstream installer ──────────────────────
info "step 1/3: installing jcode binary"
if command -v jcode >/dev/null 2>&1; then
  info "jcode already on PATH: $(command -v jcode)"
else
  warn "jcode not found on PATH — installing via upstream installer"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL https://jcode.sh/install | bash
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://jcode.sh/install | bash
  else
    err "jcode not installed and neither curl nor wget is available"
  fi
fi

# ── step 2: symlink swarm/* into ~/.jcode/ ───────────────────────────────────
info "step 2/3: linking swarm/ into $JCODE_HOME"
overwrite_link "$repo_root/swarm/prompt-overlay.md" "$JCODE_HOME/prompt-overlay.md"           "prompt-overlay.md"
overwrite_link "$repo_root/swarm/swarm-prompt.md"   "$JCODE_HOME/swarm-prompt.md"             "swarm-prompt.md"
overwrite_link "$repo_root/swarm/ARCHITECTURE.md"   "$JCODE_HOME/ARCHITECTURE.md"             "ARCHITECTURE.md"

mkdir -p "$JCODE_HOME/roles"
for role_file in "$repo_root/swarm/roles/"*.md; do
  [[ -e "$role_file" ]] || continue
  role_name="$(basename "$role_file")"
  overwrite_link "$role_file" "$JCODE_HOME/roles/$role_name" "roles/$role_name"
done

# ── step 3: symlink AGENTS.md ────────────────────────────────────────────────
info "step 3/3: linking AGENTS.md"
overwrite_link "$repo_root/AGENTS.md" "$JCODE_HOME/AGENTS.md" "AGENTS.md"

info "done — jcode + lazible-jcode overlay installed"