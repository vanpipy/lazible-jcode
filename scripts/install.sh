#!/usr/bin/env bash
# scripts/install.sh — lazible-jcode installer.
#
# Linear, unconditional, overwrite-by-default. Runs 6 steps every time:
#   1. Install jcode binary to ~/.local/bin/jcode
#        - If jcode-patches/*.patch exists, build a canary from those patches
#          and replace ~/.local/bin/jcode (backup the old one as jcode.bak.<ts>)
#        - Otherwise call skills/install-jcode/jcode-install.sh to install
#          upstream jcode (default v0.65.0)
#   2. Symlink overlay + swarm config into ~/.jcode/
#   3. Symlink every skills/<name>/SKILL.md into ~/.jcode/skills/<name>
#   4. Symlink AGENTS.md to ~/.jcode/AGENTS.md
#   5. Symlink scripts/ into ~/.jcode/scripts/ and add ~/.jcode/scripts/ to PATH
#      so swarm-state-monitor.py + check-*.py + conflict-detect.py are reachable
#      from any cwd (not just the lazible-jcode checkout).
#   6. Build the tick/ Go daemon and copy it to ~/.local/bin/jcode-swarm-tick.
#      The daemon is the worker's self-reminder substrate; jcode spawns it as
#      an MCP subprocess on first use.
#
# No flags control which step runs or whether to overwrite. Overwriting is the
# point. Existing files at the destination are always backed up to <dst>.bak.<ts>
# before being replaced, so rerunning this script is safe.
#
# Opt-in: set IDEMPOTENT=1 to skip the symlink steps (2/3/4/5) when their target
# is already a symlink pointing at the right source. Step 1 (the jcode binary)
# and step 6 (the tick binary) always run. See --help for details.
#
# Usage:
#   ./scripts/install.sh                          # run all 5 steps with defaults
#   ./scripts/install.sh --canary-version v0.65.0 # pin jcode tag for the canary build
#   ./scripts/install.sh --clean                  # wipe source-dir before canary build
#   ./scripts/install.sh --help                   # show usage
#   IDEMPOTENT=1 ./scripts/install.sh             # skip already-correct symlinks
#
# Flags:
#   --canary-version <v>   Pin the jcode tag the canary is built from. Default: latest.
#                          Only used when jcode-patches/*.patch exists.
#   --clean                Pass through to build-jcode-canary.sh: wipe the source-dir
#                          (~/Project/jcode by default) before cloning + applying
#                          patches. Use this when a previous build left a polluted
#                          working tree and the patch fails to apply. Slower on
#                          rerun (~30s extra clone) — only use when needed.
#   -h, --help             Show this help.
#
# Every run does all 4 steps and overwrites every destination (backed up as
# <dst>.bak.<ts> first). The flags above are *values* (which tag, whether to
# clean the canary source), not step toggles. IDEMPOTENT is an env var, not a
# flag, on purpose: the CLI shape stays "linear and unconditional", and the
# safety guarantee is opt-in via environment.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
installer="$repo_root/skills/install-jcode/jcode-install.sh"
build_canary="$repo_root/scripts/build-jcode-canary.sh"

CANARY_VERSION=""
CANARY_CLEAN=0

print_help() {
  cat <<EOF
Usage: $0 [options]

Linear install of jcode + lazible-jcode overlay. Runs 6 steps every time and
overwrites the destination unconditionally:

  1. Install jcode binary to ~/.local/bin/jcode
       (or build a canary from jcode-patches/*.patch if any exist)
  2. Symlink swarm/prompt-overlay.md, swarm/swarm-prompt.md,
     swarm/ARCHITECTURE.md, swarm/roles/, and docs/HEARTBEAT.md
     into ~/.jcode/
  3. Symlink each skills/<name> into ~/.jcode/skills/<name>
  4. Symlink AGENTS.md to ~/.jcode/AGENTS.md
  5. Symlink scripts/ into ~/.jcode/scripts/ and add ~/.jcode/scripts/ to PATH
     so swarm-state-monitor.py, conflict-detect.py, check-*.py are reachable
     from any cwd
  6. Build the tick/ Go daemon (cd tick && go build) and copy the binary to
     ~/.local/bin/jcode-swarm-tick. After the copy, merge a tick entry into
     ~/.jcode/mcp.json (idempotent: skips silently when the entry is already
     present, warns + skips on malformed JSON). jcode then spawns tick as
     an MCP subprocess on first use. Skipped silently if Go is not installed
     or tick/ is missing.

Existing files at any destination are backed up to <dst>.bak.<timestamp> before
being replaced, so rerunning is safe.

Environment variables:
  IDEMPOTENT=1           Opt into skip-if-unchanged mode for the symlink steps
                         (2/3/4/5). When set, already-correct symlinks are left
                         in place and 'skipping: <reason>' is printed instead
                         of backing them up + re-linking. Steps 1 (jcode binary)
                         and 6 (tick daemon build) always run — their own
                         version-pin / build logic lives in the upstream
                         installer and `go build`, respectively. Default: unset
                         (always overwrite, original behavior).

Options:
  --canary-version <v>   Pin the jcode tag the canary is built from. Default: latest.
                         Only used when jcode-patches/*.patch exists.
  --clean                Pass through to the canary builder: wipe the source-dir
                         (~/Project/jcode) before re-cloning. Use when a previous
                         build left a polluted working tree and the patch fails
                         to apply. Slower on rerun; only use when needed.
  -h, --help             Show this help.

Examples:
  # Default install (installs upstream jcode when no patch exists, or builds
  # canary when jcode-patches/ has any *.patch file).
  $0

  # Pin a specific jcode tag for the canary build.
  $0 --canary-version v0.65.0

  # Wipe the canary source-dir first (when a previous build polluted it).
  $0 --clean

  # Re-run safely: skip symlinks that already point at the right target.
  IDEMPOTENT=1 $0
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --canary-version) CANARY_VERSION="${2:-}"; shift 2 ;;
    --clean)          CANARY_CLEAN=1; shift ;;
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

# IDEMPOTENT opt-in env var. When set to a non-zero, non-empty value, the
# symlink steps (2/3/4/5) skip already-correct links instead of backing them up
# and overwriting. Default 0 preserves the original "overwrite unconditionally"
# behavior. The jcode binary install (step 1) is not affected: that step still
# always runs and is handled by the upstream installer / canary builder, which
# already has its own mtime + version-pin logic.
IDEMPOTENT="${IDEMPOTENT:-0}"

info()  { printf '\033[1;34m%s\033[0m\n' "$*"; }
warn()  { printf '\033[1;33m%s\033[0m\n' "$*" >&2; }
err()   { printf '\033[1;31merror: %s\033[0m\n' "$*" >&2; exit 1; }

# Returns 0 (true) if $dst is a symlink that already resolves to the same
# canonical target as $src (compared via `readlink -f`). Returns 1 otherwise.
# Only consulted when IDEMPOTENT=1; the unconditional path ignores this.
is_same_link() {
  local src="$1" dst="$2"
  [[ -L "$dst" ]] || return 1
  local src_real dst_real
  src_real="$(readlink -f "$src" 2>/dev/null)" || return 1
  dst_real="$(readlink -f "$dst" 2>/dev/null)" || return 1
  [[ "$src_real" == "$dst_real" ]]
}

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

# Like overwrite_link(), but consults IDEMPOTENT: when IDEMPOTENT=1 and dst
# already resolves to the same canonical target as src, skip without backing
# up or re-linking. When IDEMPOTENT=0 (default), behavior matches overwrite_link
# exactly. Returns 0 in both branches.
maybe_overwrite_link() {
  local src="$1" dst="$2" label="$3"
  if [[ "$IDEMPOTENT" == "1" ]] && is_same_link "$src" "$dst"; then
    info "skipping: $label (already linked to same target)"
    return 0
  fi
  overwrite_link "$src" "$dst" "$label"
}

# ── step 0: pre-flight checks ──────────────────────────────────────────────────
# Verify all framework scripts that the swarm root agent invokes from any cwd
# are present + executable. The root agent's mandatory pre-action gate
# (`scripts/root-tick.sh`, AGENTS.md §"Mandatory root pre-action inspection")
# is the silent-stuck guard; if it's not +x after install, the gate fails
# silently and the failure mode the wrapper was designed to catch returns.
# This check makes that failure mode loud.
for required_script in \
    "$repo_root/scripts/install.sh" \
    "$repo_root/scripts/uninstall.sh" \
    "$repo_root/scripts/build-jcode-canary.sh" \
    "$repo_root/scripts/sync-jcode-source.sh" \
    "$repo_root/scripts/root-tick.sh" \
    "$repo_root/skills/install-jcode/jcode-install.sh" \
    "$repo_root/skills/copy-from-jcode/copy-from-jcode.sh"; do
  if [[ ! -x "$required_script" ]]; then
    err "required script missing or not executable: $required_script (run 'chmod +x' on it)"
  fi
done

# ── step 1: install jcode binary ──────────────────────────────────────────────
info "── step 1/6: install jcode binary ──"
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
  [[ $CANARY_CLEAN -eq 1 ]] && canary_args+=(--clean)
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
info "── step 2/6: overlay + swarm config ──"
mkdir -p "$JCODE_HOME" "$JCODE_HOME/roles"
maybe_overwrite_link "$repo_root/swarm/prompt-overlay.md" "$JCODE_HOME/prompt-overlay.md" "prompt-overlay.md"
maybe_overwrite_link "$repo_root/swarm/swarm-prompt.md"   "$JCODE_HOME/swarm-prompt.md"   "swarm-prompt.md"
maybe_overwrite_link "$repo_root/swarm/ARCHITECTURE.md"   "$JCODE_HOME/ARCHITECTURE.md"   "ARCHITECTURE.md"
maybe_overwrite_link "$repo_root/swarm/roles"             "$JCODE_HOME/roles"             "roles/"
# docs/HEARTBEAT.md is referenced by the overlay + swarm-prompt + every role
# file's liveness contract. It must be discoverable from $JCODE_HOME so jcode
# can resolve the reference regardless of cwd.
if [[ -f "$repo_root/docs/HEARTBEAT.md" ]]; then
  maybe_overwrite_link "$repo_root/docs/HEARTBEAT.md" "$JCODE_HOME/HEARTBEAT.md" "HEARTBEAT.md"
fi

# ── step 3: skills ────────────────────────────────────────────────────────────
info "── step 3/6: skills ──"
mkdir -p "$JCODE_HOME/skills"
skill_count=0
for skill_dir in "$repo_root/skills"/*; do
  [[ -d "$skill_dir" ]] || continue
  [[ -f "$skill_dir/SKILL.md" ]] || continue
  name="$(basename "$skill_dir")"
  maybe_overwrite_link "$skill_dir" "$JCODE_HOME/skills/$name" "skill:$name"
  skill_count=$((skill_count + 1))
done
info "linked $skill_count skill(s)"

# ── step 4: AGENTS.md ─────────────────────────────────────────────────────────
info "── step 4/6: AGENTS.md ──"
maybe_overwrite_link "$repo_root/AGENTS.md" "$JCODE_HOME/AGENTS.md" "AGENTS.md"

# ── step 5: scripts/ ──────────────────────────────────────────────────────────
# Wire the framework's helper scripts (swarm-state-monitor.py, conflict-detect.py,
# check-*.py, install-dryrun.sh, the test-*.sh harness, etc.) into ~/.jcode/scripts/
# so they are reachable on the production path — not just from this checkout's cwd.
# This is what lets the swarm root session call `swarm-state-monitor.py tick` (or
# `python3 ~/.jcode/scripts/swarm-state-monitor.py tick`) from any directory.
info "── step 5/6: scripts/ ──"
maybe_overwrite_link "$repo_root/scripts" "$JCODE_HOME/scripts" "scripts/"

# After linking, add ~/.jcode/scripts/ to PATH so users can call the scripts by
# name from any cwd. configure_path.sh is idempotent: it grep-checks each rc
# file for the install_dir and only appends when missing, so re-running this
# step never duplicates the export line.
configure_path_lib="$repo_root/scripts/lib/configure_path.sh"
if [[ -f "$configure_path_lib" ]]; then
  # shellcheck disable=SC1091
  . "$configure_path_lib"
  if command -v jcode_configure_path >/dev/null 2>&1; then
    jcode_configure_path "$JCODE_HOME/scripts"
  else
    warn "jcode_configure_path not defined in $configure_path_lib — skipping PATH edit"
  fi
else
  warn "configure_path.sh missing at $configure_path_lib — skipping PATH edit"
fi

# ── step 6: build + install tick daemon ───────────────────────────────────────
# Build the tick/ Go daemon and copy the binary to ~/.local/bin/jcode-swarm-tick,
# then merge a tick entry into ~/.jcode/mcp.json so jcode spawns the daemon as
# an MCP subprocess on first use. The agent then has submit_job / cancel_job /
# list_jobs tools available (see swarm/roles/tick-user.md).
#
# Skipped silently if Go is not installed or tick/ is missing — the rest of
# the install still succeeds; jcode will just lack the tick MCP server.
info "── step 6/6: tick daemon ──"
tick_dir="$repo_root/tick"
if [[ ! -d "$tick_dir" ]]; then
  warn "tick/ directory missing at $tick_dir — skipping step 6 (jcode-swarm-tick unavailable)"
elif ! command -v go >/dev/null 2>&1; then
  warn "go not on PATH — skipping step 6 (jcode-swarm-tick unavailable)"
else
  tick_bin="$tick_dir/tick"
  # Build into tick/ first so a build failure doesn't leave a stale binary on
  # $INSTALL_DIR. -trimpath strips local paths from the binary (reproducible builds).
  if ! (cd "$tick_dir" && go build -trimpath -o tick .); then
    err "go build failed in $tick_dir — fix and re-run; jcode-swarm-tick NOT installed"
  fi

  tick_dst="$INSTALL_DIR/jcode-swarm-tick"
  if [[ -e "$tick_dst" || -L "$tick_dst" ]]; then
    mv "$tick_dst" "$tick_dst.bak.$TIMESTAMP"
    warn "backed up $tick_dst → $tick_dst.bak.$TIMESTAMP"
  fi
  # Copy (not symlink) — $INSTALL_DIR survives a `git clean` in the repo,
  # and the binary is rebuilt on every install anyway.
  cp "$tick_bin" "$tick_dst"
  chmod 0755 "$tick_dst"
  info "installed $tick_dst (built from $repo_root/tick/)"

  # Register the daemon with jcode by merging an entry into ~/.jcode/mcp.json.
  # Idempotent: skips silently when the entry already exists under either
  # mcpServers (canonical) or servers (legacy) — no rewrite, no .bak. If the
  # file is missing, creates one with only mcpServers.tick. If the file exists
  # but is malformed JSON, warns and skips (the install otherwise succeeds).
  # Matches the `maybe_overwrite_*` discipline: backup ONLY when content
  # actually changes; honor IDEMPOTENT implicitly (a skip when entry present
  # is the same outcome in both modes).
  merge_tick_mcp_entry() {
    local mcp_json="$JCODE_HOME/mcp.json"
    local tick_bin_path="$tick_dst"
    local existing=""
    local has_existing_tick=0

    if [[ -f "$mcp_json" ]]; then
      # JSON safety: bail before rewriting if the file is unparseable.
      if ! python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$mcp_json" 2>/dev/null; then
        warn "mcp.json is malformed JSON — skipping tick merge (leave $mcp_json untouched)"
        return 0
      fi
      # Probe both canonical + legacy keys for an existing tick entry.
      has_existing_tick=$(MCP_JSON_PATH="$mcp_json" python3 - <<'PY'
import json, os
try:
    with open(os.environ["MCP_JSON_PATH"]) as f: d = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    print(0); raise SystemExit
for key in ("mcpServers", "servers"):
    if isinstance(d.get(key), dict) and "tick" in d[key]:
        print(1); raise SystemExit
print(0)
PY
)
      if [[ "$has_existing_tick" == "1" ]]; then
        info "skipping: mcp.json already has tick entry (canonical or legacy key)"
        return 0
      fi
      existing=1
    fi

    # Back up only when the file actually exists and is about to be rewritten.
    if [[ -n "$existing" ]]; then
      mv "$mcp_json" "$mcp_json.bak.$TIMESTAMP"
      warn "backed up $mcp_json → $mcp_json.bak.$TIMESTAMP"
    fi

    # Atomic write: stage to <mcp_json>.new, then mv into place. Preserves
    # the file if Python raises mid-write.
    MCP_JSON_PATH="$mcp_json" TICK_BIN_PATH="$tick_bin_path" \
    HAS_EXISTING="$existing" python3 - <<'PY'
import json, os, sys
mcp_json = os.environ["MCP_JSON_PATH"]
tick_bin = os.environ["TICK_BIN_PATH"]
has_existing = os.environ["HAS_EXISTING"] == "1"

tick_entry = {
    "command": tick_bin,
    "args": ["mcp"],
    "env": {},
    "shared": True,
}

if has_existing:
    with open(mcp_json) as f:
        d = json.load(f)
else:
    d = {}

# Always add under the canonical mcpServers key.
d.setdefault("mcpServers", {})
d["mcpServers"]["tick"] = tick_entry
# If the legacy 'servers' key exists, mirror the entry there too — jcode
# reads whichever key it finds first, so a legacy file picks up tick without
# the user having to migrate.
if isinstance(d.get("servers"), dict):
    d["servers"]["tick"] = tick_entry

stage = mcp_json + ".new"
with open(stage, "w") as f:
    json.dump(d, f, indent=2)
os.replace(stage, mcp_json)
PY
    info "merged tick entry into $mcp_json"
  }
  merge_tick_mcp_entry
fi

# ── summary ────────────────────────────────────────────────────────────────────
info "✅ lazible-jcode install complete."
info "   mode:           $([[ "$IDEMPOTENT" == "1" ]] && echo "idempotent (IDEMPOTENT=1)" || echo "overwrite (IDEMPOTENT unset)")"
info "   jcode binary:   $INSTALL_DIR/jcode"
info "   jcode home:     $JCODE_HOME"
info "   overlay:        $JCODE_HOME/prompt-overlay.md → $repo_root/swarm/prompt-overlay.md"
info "   architecture:   $JCODE_HOME/ARCHITECTURE.md → $repo_root/swarm/ARCHITECTURE.md"
info "   AGENTS.md:      $JCODE_HOME/AGENTS.md → $repo_root/AGENTS.md"
info "   scripts:        $JCODE_HOME/scripts → $repo_root/scripts (added to PATH)"
info "   tick binary:    $INSTALL_DIR/jcode-swarm-tick (built from $repo_root/tick/)"
info "   tick MCP entry: $JCODE_HOME/mcp.json (merged mcpServers.tick; idempotent)"
info ""
info "Tip: re-running with IDEMPOTENT=1 skips symlinks that already point at"
info "     the right target — no backups, no rewrites. See --help for details."