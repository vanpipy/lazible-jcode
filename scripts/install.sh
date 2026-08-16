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
# the point. Existing files at the destination are backed up to
# <dst>.bak.<ts> before being replaced, so rerunning this script is safe.
# Fast path: a destination that is already a symlink to the source target
# is left unchanged (no backup, no recreate) — repeated runs do not
# accumulate .bak.<ts> files.
#
# Usage:
#   ./scripts/install.sh             # run all 3 steps with defaults
#   ./scripts/install.sh --help      # show usage
#
# Every run does all 3 steps and overwrites every destination (backed up as
# <dst>.bak.<ts> first, except for the fast-path case above).

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

print_help() {
  cat <<EOF
Usage: $0 [options]

Linear install of jcode + lazible-jcode overlay. Runs 3 steps every time and
overwrites the destination unconditionally:

  1. Install jcode binary to ~/.local/bin/jcode via the upstream installer.
     Also symlinks the swarm-sweep helper to ~/.local/bin/swarm-sweep
     for cleaning up stale swarm worktrees.
  2. Symlink swarm/prompt-overlay.md, swarm/swarm-prompt.md,
     swarm/ARCHITECTURE.md, and swarm/roles/*.md into ~/.jcode/.
  3. Symlink AGENTS.md to ~/.jcode/AGENTS.md.

Existing files at any destination are backed up to <dst>.bak.<timestamp>
before being replaced. A destination that is already a symlink to the
source target is left unchanged (no backup, no recreate).

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

# Color-aware output. Disable color in three cases:
#   1. NO_COLOR env set (https://no-color.org standard)
#   2. stdout not a tty (output is being piped/captured)
#   3. TERM=dumb (terminal can't render ANSI; CI / minimal emulators)
# All other cases: cyan/blue info, yellow warn, red err.
if [[ -n "${NO_COLOR:-}" || ! -t 1 || "${TERM:-}" == "dumb" ]]; then
  C_INFO=''; C_WARN=''; C_ERR=''; C_RESET=''
else
  C_INFO='\033[1;34m'; C_WARN='\033[1;33m'; C_ERR='\033[1;31m'; C_RESET='\033[0m'
fi
info() { printf '%b%s%b\n' "$C_INFO" "$*" "$C_RESET"; }
warn() { printf '%b%s%b\n' "$C_WARN" "$*" "$C_RESET" >&2; }
err()  { printf '%b%s%b\n' "$C_ERR" "error: $*" "$C_RESET" >&2; exit 1; }

# ── env probe (step 0) ────────────────────────────────────────────────────────
# Linux-only sanity check of the host environment. Required deps block the
# install (exit 3); optional deps warn and continue. Run BEFORE the 3 install
# steps so the user sees "your environment is missing X" instead of a cryptic
# failure halfway through step 1.
#
# Linux scope: bash >= 4 (typical on every maintained distro; bash 3.2 is
# the legacy macOS default and out of scope), `git`, `$HOME` writable,
# `/tmp` writable, curl-or-wget. Optional: python3 / jq / ~/.local/bin on
# PATH.
env_probe() {
  info "env check:"
  local failed=0

  # bash version
  local bash_ver
  bash_ver="$(bash --version 2>/dev/null | head -1 | awk '{print $4}' | cut -d. -f1)"
  bash_ver="${bash_ver:-0}"
  if [[ "$bash_ver" -ge 4 ]]; then
    printf '  %-30s %s\n' "bash >= 4" "ok (${bash_ver})"
  else
    warn "  bash < 4 detected (${bash_ver:-unknown}); install.sh requires bash 4+ on Linux"
    failed=1
  fi

  # git
  if command -v git >/dev/null 2>&1; then
    printf '  %-30s %s\n' "git" "ok ($(command -v git))"
  else
    warn "  git not on PATH; required by jcode and extension.sh"
    failed=1
  fi

  # HOME writable
  if [[ -z "${HOME:-}" ]]; then
    warn "  HOME is unset; cannot determine ~/.jcode or ~/.local/bin"
    failed=1
  elif [[ ! -d "$HOME" ]] || [[ ! -w "$HOME" ]]; then
    warn "  HOME ($HOME) does not exist or is not writable"
    failed=1
  else
    printf '  %-30s %s\n' "HOME writable" "ok ($HOME)"
  fi

  # /tmp writable (jcode scratch dir default)
  if [[ -w /tmp ]]; then
    printf '  %-30s %s\n' "/tmp writable" "ok"
  else
    warn "  /tmp not writable; set LAZIBLE_TMPDIR to a writable path before running"
    failed=1
  fi

  # curl or wget (needed for upstream jcode install)
  if command -v curl >/dev/null 2>&1; then
    printf '  %-30s %s\n' "curl or wget" "ok (curl: $(command -v curl))"
  elif command -v wget >/dev/null 2>&1; then
    printf '  %-30s %s\n' "curl or wget" "ok (wget: $(command -v wget))"
  else
    warn "  neither curl nor wget on PATH; required to fetch jcode binary"
    failed=1
  fi

  # Optional: python3 / jq (extension.sh uses one of these for JSON inspection)
  if command -v python3 >/dev/null 2>&1; then
    printf '  %-30s %s\n' "python3 (optional)" "ok"
  elif command -v jq >/dev/null 2>&1; then
    printf '  %-30s %s\n' "python3 / jq (optional)" "jq only (some extension.sh checks simplified)"
  else
    warn "  python3/jq missing; extension.sh mcp info + artifact validate will report 'unavailable'"
  fi

  # Optional: ~/.local/bin on PATH
  if [[ ":$PATH:" == *":$HOME/.local/bin:"* ]]; then
    printf '  %-30s %s\n' "~/.local/bin on PATH" "ok"
  else
    warn "  ~/.local/bin is NOT on PATH; new shells won't find jcode. Add: export PATH=\"\$HOME/.local/bin:\$PATH\""
  fi

  echo ""
  if [[ $failed -ne 0 ]]; then
    err "env check failed (see warnings above). Aborting install."
  fi
}
env_probe

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

# ── step 1: install jcode binary + swarm-sweep helper ──────────────────────
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

# Install swarm-sweep helper into ~/.local/bin/. Symlinks the script
# directly (not a copy) so updating the repo updates the installed
# version. Idempotent: re-runs do not accumulate .bak.<ts> files
# because the fast path in overwrite_link recognizes existing
# correct symlinks.
LCL_BIN="${LCL_BIN:-$HOME/.local/bin}"
mkdir -p "$LCL_BIN"
overwrite_link "$repo_root/scripts/swarm-sweep.sh" "$LCL_BIN/swarm-sweep" "swarm-sweep"

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