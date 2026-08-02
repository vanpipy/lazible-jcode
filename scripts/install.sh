#!/usr/bin/env bash
# scripts/install.sh — lazible-jcode installer.
#
# Linear, unconditional, overwrite-by-default. Runs 4 steps every time:
#   1. Install jcode binary to ~/.local/bin/jcode
#        - If jcode-patches/*.patch exists, build a canary from those patches
#          and replace ~/.local/bin/jcode (backup the old one as jcode.bak.<ts>)
#        - Otherwise call skills/install-jcode/jcode-install.sh to install
#          upstream jcode (default v0.65.0)
#   2. Symlink overlay + swarm config into ~/.jcode/
#   3. Symlink every skills/<name>/SKILL.md into ~/.jcode/skills/<name>
#   4. Symlink AGENTS.md to ~/.jcode/AGENTS.md
#
# No flags control which step runs or whether to overwrite. Overwriting is the
# point. Existing files at the destination are always backed up to <dst>.bak.<ts>
# before being replaced, so rerunning this script is safe.
#
# Usage:
#   ./scripts/install.sh                   # run all 4 steps with defaults
#   ./scripts/install.sh --canary-version v0.65.0   # pin jcode tag for the canary build
#   ./scripts/install.sh --help            # show usage
#
# The only configuration flag is --canary-version, because it is a value
# (which upstream tag to build against), not a step toggle.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
installer="$repo_root/skills/install-jcode/jcode-install.sh"
build_canary="$repo_root/scripts/build-jcode-canary.sh"

CANARY_VERSION=""

print_help() {
  cat <<EOF
Usage: $0 [options]

Linear install of jcode + lazible-jcode overlay. Runs 4 steps every time and
overwrites the destination unconditionally:

  1. Install jcode binary to ~/.local/bin/jcode
       (or build a canary from jcode-patches/*.patch if any exist)
  2. Symlink swarm/prompt-overlay.md, swarm/swarm-prompt.md, swarm/roles/
  3. Symlink each skills/<name> into ~/.jcode/skills/<name>
  4. Symlink AGENTS.md to ~/.jcode/AGENTS.md

Existing files at any destination are backed up to <dst>.bak.<timestamp> before
being replaced, so rerunning is safe.

Options:
  --canary-version <v>   Pin the jcode tag the canary is built from. Default: latest.
                         Only used when jcode-patches/*.patch exists.
  -h, --help             Show this help.

Examples:
  # Default install (installs upstream jcode when no patch exists, or builds
  # canary when jcode-patches/ has any *.patch file).
  $0

  # Pin a specific jcode tag for the canary build.
  $0 --canary-version v0.65.0
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --canary-version) CANARY_VERSION="${2:-}"; shift 2 ;;
    -h|--help)        print_help; exit 0 ;;
    *) echo "error: unknown flag: $1" >&2; print_help >&2; exit 1 ;;
  esac
done

# ── sanity ─────────────────────────────────────────────────────────────────────
for required in AGENTS.md README.md config skills swarm jcode-patches; do
  if [[ ! -e "$repo_root/$required" ]]; then
    echo "error: lazible-jcode checkout looks incomplete: missing $repo_root/$required" >&2
    exit 1
  fi
done

JCODE_HOME="${JCODE_HOME:-$HOME/.jcode}"
INSTALL_DIR="${JCODE_INSTALL_DIR:-$HOME/.local/bin}"
TIMESTAMP="$(date +%s)"

info()  { printf '\033[1;34m%s\033[0m\n' "$*"; }
warn()  { printf '\033[1;33m%s\033[0m\n' "$*" >&2; }
err()   { printf '\033[1;31merror: %s\033[0m\n' "$*" >&2; exit 1; }

# Overwrite a file or symlink unconditionally. If dst exists (regular file,
# symlink, or directory), back it up to <dst>.bak.<ts> first. If dst does not
# exist, just create it. Always links src as the final dst.
overwrite_link() {
  local src="$1" dst="$2" label="$3"
  [[ -e "$src" ]] || { warn "skip $label — source missing: $src"; return 0; }

  if [[ -e "$dst" || -L "$dst" ]]; then
    mv "$dst" "$dst.bak.$TIMESTAMP"
    warn "backed up $dst → $dst.bak.$TIMESTAMP"
  fi
  ln -s "$src" "$dst"
  info "linked $label → $src"
}

# ── step 1: install jcode binary ──────────────────────────────────────────────
info "── step 1/4: install jcode binary ──"
mkdir -p "$INSTALL_DIR"

# Detect canary mode by the presence of jcode-patches/*.patch. If any exist,
# build a canary from them and use it as the final binary.
shopt -s nullglob
patches=("$repo_root/jcode-patches"/*.patch)
shopt -u nullglob

if [[ ${#patches[@]} -gt 0 ]]; then
  if [[ ! -x "$build_canary" ]]; then
    err "jcode-patches/ has patches but $build_canary is missing or not executable"
  fi
  info "found ${#patches[@]} patch(es) in jcode-patches/ — building canary"
  canary_args=(--replace-main)
  [[ -n "$CANARY_VERSION" ]] && canary_args+=(--jcode-version "$CANARY_VERSION")
  "$build_canary" "${canary_args[@]}"
  info "canary installed to $INSTALL_DIR/jcode (original backed up as .bak.$TIMESTAMP)"
else
  if [[ ! -x "$installer" ]]; then
    err "no patches and upstream installer missing: $installer (chmod +x it)"
  fi
  "$installer"
  info "upstream jcode installed to $INSTALL_DIR/jcode"
fi

# ── step 2: overlay + swarm config ─────────────────────────────────────────────
info "── step 2/4: overlay + swarm config ──"
mkdir -p "$JCODE_HOME" "$JCODE_HOME/roles"
overwrite_link "$repo_root/swarm/prompt-overlay.md" "$JCODE_HOME/prompt-overlay.md" "prompt-overlay.md"
overwrite_link "$repo_root/swarm/swarm-prompt.md"   "$JCODE_HOME/swarm-prompt.md"   "swarm-prompt.md"
overwrite_link "$repo_root/swarm/roles"             "$JCODE_HOME/roles"             "roles/"

# ── step 3: skills ────────────────────────────────────────────────────────────
info "── step 3/4: skills ──"
mkdir -p "$JCODE_HOME/skills"
skill_count=0
for skill_dir in "$repo_root/skills"/*; do
  [[ -d "$skill_dir" ]] || continue
  [[ -f "$skill_dir/SKILL.md" ]] || continue
  name="$(basename "$skill_dir")"
  overwrite_link "$skill_dir" "$JCODE_HOME/skills/$name" "skill:$name"
  skill_count=$((skill_count + 1))
done
info "linked $skill_count skill(s)"

# ── step 4: AGENTS.md ─────────────────────────────────────────────────────────
info "── step 4/4: AGENTS.md ──"
overwrite_link "$repo_root/AGENTS.md" "$JCODE_HOME/AGENTS.md" "AGENTS.md"

# ── summary ────────────────────────────────────────────────────────────────────
info "✅ lazible-jcode install complete."
info "   jcode binary:   $INSTALL_DIR/jcode"
info "   jcode home:     $JCODE_HOME"
info "   overlay:        $JCODE_HOME/prompt-overlay.md → $repo_root/swarm/prompt-overlay.md"
info "   AGENTS.md:      $JCODE_HOME/AGENTS.md → $repo_root/AGENTS.md"