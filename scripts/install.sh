#!/usr/bin/env bash
# scripts/install.sh — lazible-jcode installer.
#
# Linear, unconditional, overwrite-by-default. Runs 3 steps every time:
#   1. Install jcode binary to ~/.local/bin/jcode via the upstream installer.
#      This is the ONLY thing the bundle writes outside ~/.jcode/.
#   2. Symlink all bundle artifacts into ~/.jcode/ — markdown overlays,
#      config.toml, the extension.sh + swarm-sweep CLI entry points, and
#      the roles/*.md templates. Single source of truth: `ls ~/.jcode/`
#      shows everything the bundle deploys.
#   3. Auto-init ~/.jcode/mcp.json from the bundle's template,
#      substituting the actual project root for /workspace. Idempotent:
#      skips with a message if the file already exists.
#
# NOTE: This bundle ships NO AGENTS.md. The repo's AGENTS.md is the
# maintenance manual for this repository itself, not a shipped overlay.
# To activate lazible-jcode in another project, copy this repo there and
# run install.sh from within that project. Per-project AGENTS.md
# (if desired) is the user's own concern.
#
# No flags control which step runs or whether to overwrite (except for
# --project; see below). Overwriting is the point for steps 1-3 — existing
# files at the destination are backed up to <dst>.bak.<ts> before being
# replaced, so rerunning this script is safe. Fast path: a destination that
# is already a symlink to the source target is left unchanged (no backup,
# no recreate) — repeated runs do not accumulate .bak.<ts> files.
#
# Usage:
#   ./scripts/install.sh                       # install bundle + init
#                                              # .jcode/mcp.json in bundle's
#                                              # own checkout (default project)
#   ./scripts/install.sh --project=PATH        # also init .jcode/mcp.json in
#                                              # PATH (for using the bundle
#                                              # in another project)
#   ./scripts/install.sh --help                # show usage
#
# Every run does all 3 steps and overwrites steps 1-2 destinations (backed up
# as <dst>.bak.<ts> first, except for the fast-path case above). Step 3 is
# idempotent (skip if .jcode/mcp.json already exists).

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

print_help() {
  cat <<EOF
Usage: $0 [options]

Linear install of jcode + lazible-jcode overlay. Runs 3 steps every time and
overwrites the destination unconditionally (step 3 is idempotent, never
overwrites an existing file):

  1. Install jcode binary to ~/.local/bin/jcode via the upstream installer.
  2. Symlink all bundle artifacts into ~/.jcode/: markdown overlays,
     config.toml, the extension.sh + swarm-sweep CLI helpers, and
     the roles/*.md templates.
  3. Auto-init ~/.jcode/mcp.json from the bundle's template
     (config/mcp.json.example), substituting the actual project root for
     the /workspace placeholder. Mirrors the "all config in ~/.jcode/"
     pattern of steps 1-2. With --project=PATH where PATH is not the
     bundle's own repo, also writes a per-project override at
     <PATH>/.jcode/mcp.json. Skips with a message if either file already
     exists — never overwrites.

Existing files at any destination (steps 1-2) are backed up to <dst>.bak.<ts>
before being replaced. A destination that is already a symlink to the source
target is left unchanged (no backup, no recreate).

Options:
  -h, --help          Show this help.
  --project=PATH       Substitute PATH for /workspace when generating
     ~/.jcode/mcp.json (default: the bundle's own checkout at
     $repo_root). When PATH is not the bundle's own repo, also writes
     a per-project override at <PATH>/.jcode/mcp.json so multi-project
     hosts can scope filesystem/git/serena to the right repo.

Examples:
  # Default: install bundle + init ~/.jcode/mcp.json (scope = bundle's own repo).
  $0

  # Install bundle AND init a per-project override for another project (e.g. your app).
  $0 --project=/path/to/your/project
EOF
}

# Default project for step 3 = the bundle's own checkout. --project=PATH
# overrides this for users setting up the bundle in a different repo.
TARGET_PROJECT="$repo_root"
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) print_help; exit 0 ;;
    --project=*) TARGET_PROJECT="${1#*=}" ;;
    *) echo "error: unknown flag: $1" >&2; print_help >&2; exit 1 ;;
  esac
  shift
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

# ── step 1: install jcode binary ─────────────────────────────────────────────
# Only the jcode engine binary lives under ~/.local/bin/. All other
# bundle artifacts (including CLI helper scripts like extension.sh +
# swarm-sweep) live under ~/.jcode/ — the single source of truth.
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

# ── step 2: symlink bundle artifacts into ~/.jcode/ ──────────────────────────
# All bundle artifacts that jcode (or root/worker) reads at runtime
# live under ~/.jcode/: the markdown overlays + config files + the
# extension.sh CLI entry point. Top-level names below; roles/ stays
# a subdirectory so the role loader can glob it.
info "step 2/3: linking bundle artifacts into $JCODE_HOME"
overwrite_link "$repo_root/swarm/prompt-overlay.md" "$JCODE_HOME/prompt-overlay.md"           "prompt-overlay.md"
overwrite_link "$repo_root/swarm/swarm-prompt.md"   "$JCODE_HOME/swarm-prompt.md"             "swarm-prompt.md"
overwrite_link "$repo_root/config/config.toml"      "$JCODE_HOME/config.toml"                "config.toml"
overwrite_link "$repo_root/scripts/extension.sh"    "$JCODE_HOME/extension.sh"               "extension.sh"
overwrite_link "$repo_root/scripts/swarm-sweep.sh" "$JCODE_HOME/swarm-sweep"               "swarm-sweep"

mkdir -p "$JCODE_HOME/roles"
for role_file in "$repo_root/swarm/roles/"*.md; do
  [[ -e "$role_file" ]] || continue
  role_name="$(basename "$role_file")"
  overwrite_link "$role_file" "$JCODE_HOME/roles/$role_name" "roles/$role_name"
done

# ── step 3: auto-init ~/.jcode/mcp.json (global, like every other bundle config) ──
# The bundle installs ALL its config to ~/.jcode/ — prompt-overlay.md,
# swarm-prompt.md, config.toml, roles/*.md — so mcp.json belongs there too.
# This is the single source of truth for MCP server registration after install.
#
# Per-project override at <project>/.jcode/mcp.json remains available for users
# with multiple projects that need different MCP server scopes, but is opt-in
# (only when --project=PATH was given AND PATH != bundle repo). jcode merges
# per-project over global at session start, so the override still takes effect
# when present.
#
# Both initializations delegate to `extension.sh mcp {init,init-global}`,
# which handle template copy, /workspace → $PROJECT substitution, and the
# idempotent skip-when-present semantics.
info "step 3a/3: initializing ~/.jcode/mcp.json (global, matches every other bundle config)"
bash "$repo_root/scripts/extension.sh" mcp init-global "--project=$TARGET_PROJECT"

# Opt-in per-project: only when the user explicitly targeted a different repo.
# Skipping this on default install keeps the install pattern uniform ("all
# config in ~/.jcode/") and avoids a redundant copy in the bundle's own repo.
if [[ "$TARGET_PROJECT" != "$repo_root" ]]; then
  info "step 3b/3: also initializing per-project override at $TARGET_PROJECT/.jcode/mcp.json"
  bash "$repo_root/scripts/extension.sh" mcp init "--project=$TARGET_PROJECT"
fi

info "done — jcode + lazible-jcode overlay installed, ~/.jcode/mcp.json initialized"