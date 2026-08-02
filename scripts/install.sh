#!/usr/bin/env bash
# scripts/install.sh — repo-level entry point.
#
# What this does (in order):
#   1. Validate the lazible-jcode checkout (looks for skills/, config/, swarm/, etc.)
#   2. Parse flags (binary-install + overlay-specific)
#   3. Invoke the standalone jcode binary installer (jcode-install.sh)
#   4. If overlay install is enabled (default), symlink:
#        swarm/prompt-overlay.md → ~/.jcode/prompt-overlay.md
#        swarm/swarm-prompt.md   → ~/.jcode/swarm-prompt.md
#        swarm/roles/            → ~/.jcode/roles/
#   5. If --install-skills is given, also symlink each skills/<name> into ~/.jcode/skills/
#
# Usage:
#   ./scripts/install.sh                       # install jcode binary + overlay (default)
#   ./scripts/install.sh --no-overlay          # install jcode binary only (no overlay)
#   ./scripts/install.sh --overlay <path>      # use a custom overlay file (replaces swarm/prompt-overlay.md)
#   ./scripts/install.sh --refresh             # force overwrite existing symlinks at ~/.jcode/
#   ./scripts/install.sh --install-skills      # also symlink skills/<name> into ~/.jcode/skills/
#   ./scripts/install.sh --dry-run             # plan only (binary install + overlay)
#
# For the full binary-install flag set, see ./skills/install-jcode/jcode-install.sh --help.
#
# Idempotent: rerunning is safe. Without --refresh, existing non-symlink files at the
# destination are warned and preserved. With --refresh, mismatched symlinks are
# replaced and non-symlink files are backed up to <dst>.bak.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
installer="$repo_root/skills/install-jcode/jcode-install.sh"

if [[ ! -x "$installer" ]]; then
  echo "error: installer not found or not executable: $installer" >&2
  echo "       run: chmod +x '$installer'" >&2
  exit 1
fi

# ── flag parsing ───────────────────────────────────────────────────────────────
INSTALL_OVERLAY=1                       # default: install the prompt-overlay + swarm links
OVERLAY_PATH="$repo_root/swarm/prompt-overlay.md"   # default source for the overlay
REFRESH=0
INSTALL_SKILLS=0
SKIP_BINARY=0
DRY_RUN=0
binary_args=()

print_help() {
  cat <<EOF
Usage: $0 [options]

Install jcode plus the lazible-jcode overlay (default).

Overlay-specific options (consumed by this wrapper, not passed to the binary installer):
  --no-overlay         Skip installing prompt-overlay + swarm + roles symlinks.
                       Installs only the jcode binary + PATH.
  --overlay <path>     Use <path> as the overlay source instead of swarm/prompt-overlay.md.
  --refresh            Force overwrite mismatched symlinks. Existing non-symlink
                       files at the destination are backed up to <dst>.bak first.
  --install-skills     Also symlink each skills/<name> into ~/.jcode/skills/<name>.
                       Default: leave ~/.jcode/skills/ untouched (users may have
                       personal skills there).
  --skip-binary        Skip the jcode binary installer (use when you only want
                       to refresh the overlay on a machine that already has jcode).
  --dry-run            Print the plan without writing anything.

All other flags are forwarded to the jcode binary installer. Run
\`$repo_root/skills/install-jcode/jcode-install.sh --help\` for the full list.

Examples:
  # Fresh install on a new machine:
  $0

  # Refresh overlay symlinks only (jcode binary already installed):
  $0 --no-binary --refresh

  # Use a personal overlay file:
  $0 --overlay ~/my-overrides/prompt-overlay.md

  # Full reset on a machine that already has jcode (forces re-link of all
  # overlay/swarm/skills symlinks):
  $0 --skip-binary --refresh --install-skills
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-overlay)        INSTALL_OVERLAY=0; shift ;;
    --overlay)           OVERLAY_PATH="${2:-}"; shift 2 ;;
    --refresh)           REFRESH=1; shift ;;
    --install-skills)    INSTALL_SKILLS=1; shift ;;
    --skip-binary)       SKIP_BINARY=1; shift ;;
    --dry-run)           DRY_RUN=1; binary_args+=("$1"); shift ;;
    -h|--help)           print_help; exit 0 ;;
    *)                   binary_args+=("$1"); shift ;;
  esac
done

# ── layout sanity ──────────────────────────────────────────────────────────────
for required in AGENTS.md README.md config skills swarm; do
  if [[ ! -e "$repo_root/$required" ]]; then
    echo "error: lazible-jcode checkout looks incomplete: missing $repo_root/$required" >&2
    exit 1
  fi
done

JCODE_HOME="${JCODE_HOME:-$HOME/.jcode}"

# ── helpers ────────────────────────────────────────────────────────────────────
info() { printf '\033[1;34m%s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*" >&2; }
err()  { printf '\033[1;31merror: %s\033[0m\n' "$*" >&2; exit "${EXIT_CODE:-1}"; }

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[dry-run] %s\n' "$*"
  else
    "$@"
  fi
}

# Install one symlink. Behavior matrix:
#   dst does not exist              → create link (always)
#   dst is symlink to src           → skip silently (already correct)
#   dst is symlink elsewhere        → replace if REFRESH=1, else warn+skip
#   dst is non-symlink file/dir     → backup to <dst>.bak then link if REFRESH=1, else warn+skip
install_link() {
  local src="$1" dst="$2" label="$3"
  [[ -e "$src" ]] || { warn "skip $label — source missing: $src"; return 0; }

  if [[ -L "$dst" ]]; then
    local target
    target="$(readlink "$dst")"
    if [[ "$target" == "$src" ]]; then
      info "already linked $label → $src"
      return 0
    fi
    if [[ "$REFRESH" == "1" ]]; then
      run rm -f "$dst"
    else
      warn "skip $label — $dst is a symlink to $target (use --refresh to overwrite)"
      return 0
    fi
  elif [[ -e "$dst" ]]; then
    if [[ "$REFRESH" == "1" ]]; then
      run mv "$dst" "$dst.bak"
      warn "backed up $dst → $dst.bak"
    else
      warn "skip $label — $dst exists and is not a symlink (use --refresh to backup + replace)"
      return 0
    fi
  fi

  run ln -s "$src" "$dst"
  info "linked $label → $src"
}

# ── step 1: binary installer ───────────────────────────────────────────────────
if [[ "$SKIP_BINARY" != "1" ]]; then
  info "── step 1/3: jcode binary installer ──"
  run "$installer" "${binary_args[@]}"
else
  info "── step 1/3: skipped (--skip-binary) ──"
fi

# ── step 2: prompt overlay + swarm symlinks ────────────────────────────────────
if [[ "$INSTALL_OVERLAY" == "1" ]]; then
  info "── step 2/3: prompt overlay + swarm config symlinks ──"

  if [[ -n "$OVERLAY_PATH" ]] && [[ ! -e "$OVERLAY_PATH" ]]; then
    err "--overlay source does not exist: $OVERLAY_PATH"
  fi

  run mkdir -p "$JCODE_HOME" "$JCODE_HOME/roles"

  install_link "$OVERLAY_PATH"            "$JCODE_HOME/prompt-overlay.md" "prompt-overlay.md"
  install_link "$repo_root/swarm/swarm-prompt.md" "$JCODE_HOME/swarm-prompt.md"   "swarm-prompt.md"
  install_link "$repo_root/swarm/roles"           "$JCODE_HOME/roles"             "roles/"
else
  info "── step 2/3: skipped (--no-overlay) ──"
fi

# ── step 3: skills symlinks (opt-in) ───────────────────────────────────────────
if [[ "$INSTALL_SKILLS" == "1" ]]; then
  info "── step 3/3: skills symlinks ──"
  run mkdir -p "$JCODE_HOME/skills"
  local_count=0
  for skill_dir in "$repo_root/skills"/*; do
    [[ -d "$skill_dir" ]] || continue
    [[ -f "$skill_dir/SKILL.md" ]] || continue
    name="$(basename "$skill_dir")"
    install_link "$skill_dir" "$JCODE_HOME/skills/$name" "skill:$name"
  done
else
  info "── step 3/3: skipped (use --install-skills to symlink skills/<name>) ──"
fi

info "✅ lazible-jcode install complete."
if [[ "$INSTALL_OVERLAY" == "1" ]]; then
  info "   prompt overlay: $JCODE_HOME/prompt-overlay.md → $OVERLAY_PATH"
  info "   swarm config:   $JCODE_HOME/swarm-prompt.md   → $repo_root/swarm/swarm-prompt.md"
  info "   roles:          $JCODE_HOME/roles             → $repo_root/swarm/roles"
fi
if [[ "$DRY_RUN" == "1" ]]; then
  warn "(dry-run) no changes were written"
fi