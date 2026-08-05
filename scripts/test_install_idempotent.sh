#!/usr/bin/env bash
# scripts/test_install_idempotent.sh — TDD harness for the IDEMPOTENT flag
# in scripts/install.sh.
#
# Builds a tiny fake lazible-jcode checkout in $TMPDIR with stub binary
# installers (no network, no real jcode download), copies install.sh into it,
# and runs the install twice in each of two modes:
#
#   Mode A: IDEMPOTENT unset  → original "overwrite unconditionally" behavior.
#                            The second run backs up every existing symlink
#                            and re-creates it. New .bak.<ts> files appear.
#   Mode B: IDEMPOTENT=1      → second run leaves already-correct symlinks
#                            alone and prints "skipping: <reason>". No new
#                            .bak.<ts> files for unchanged targets.
#
# Exit 0 = both modes match expectations. Exit 1 = mismatch (with diff).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_SH_SRC="$REPO_ROOT/scripts/install.sh"

# ── helpers ───────────────────────────────────────────────────────────────────
fail() {
  printf '\033[1;31mFAIL: %s\033[0m\n' "$*" >&2
  exit 1
}
info() { printf '\033[1;34m[test] %s\033[0m\n' "$*"; }

# ── set up fake lazible-jcode checkout ───────────────────────────────────────
TMP="$(mktemp -d -t install-idempotent-XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

FAKE_HOME="$TMP/home"
FAKE_REPO="$TMP/fake-repo"
mkdir -p "$FAKE_HOME" "$FAKE_REPO"/{swarm/roles,skills/install-jcode,scripts,jcode-patches}
mkdir -p "$FAKE_REPO/skills/test-skill"

# Touch every required path the sanity check at the top of install.sh looks
# for: AGENTS.md, README.md, config, skills, swarm, jcode-patches.
touch "$FAKE_REPO/AGENTS.md"
touch "$FAKE_REPO/README.md"
mkdir -p "$FAKE_REPO/config"
touch "$FAKE_REPO/config/.gitkeep"
touch "$FAKE_REPO/swarm/prompt-overlay.md"
touch "$FAKE_REPO/swarm/swarm-prompt.md"
touch "$FAKE_REPO/swarm/ARCHITECTURE.md"
touch "$FAKE_REPO/swarm/roles/.gitkeep"
touch "$FAKE_REPO/skills/install-jcode/.gitkeep"
touch "$FAKE_REPO/skills/test-skill/SKILL.md"
# Stub the remaining scripts the install.sh step-0 pre-flight iterates.
# Pre-flight was added in commit e96aec8 ("root pre-action inspection gate
# for silent-stuck branches") — the test grew in lockstep with most of
# those scripts, but the four below were missed. They each only need to
# exist + be executable for the pre-flight; the install body never invokes
# them in this test (it always picks jcode-install.sh / build-jcode-canary.sh).
for stub_script in \
    "$FAKE_REPO/scripts/uninstall.sh" \
    "$FAKE_REPO/scripts/root-tick.sh" \
    "$FAKE_REPO/scripts/sync-jcode-source.sh" \
    "$FAKE_REPO/skills/copy-from-jcode/copy-from-jcode.sh"; do
  mkdir -p "$(dirname "$stub_script")"
  printf '#!/usr/bin/env bash\necho "[stub] %s invoked"\n' "$(basename "$stub_script")" > "$stub_script"
  chmod +x "$stub_script"
done

# Mirror scripts/lib/configure_path.sh so step 5 exercises the real
# jcode_configure_path call (not the "missing → skip" warn path). The fake
# install writes the export line to $FAKE_HOME's bashrc, which is fine — the
# fake HOME is wiped on EXIT.
mkdir -p "$FAKE_REPO/scripts/lib"
cp "$REPO_ROOT/scripts/lib/configure_path.sh" "$FAKE_REPO/scripts/lib/configure_path.sh"

# Stub the tick/ Go source so step 6's `go build` actually produces a binary
# in FAKE_REPO/tick/tick. install.sh only calls `go build` when both `tick/`
# exists AND `go` is on PATH; we satisfy both via a stub-go on PATH that
# creates the binary file from the `-o` flag and exits 0.
mkdir -p "$FAKE_REPO/tick"
cat > "$FAKE_REPO/tick/main.go" <<'GO'
package main

func main() {}
GO
FAKE_BIN_DIR="$FAKE_REPO/fake-bin"
mkdir -p "$FAKE_BIN_DIR"
cat > "$FAKE_BIN_DIR/go" <<'STUB'
#!/usr/bin/env bash
# Stub `go build`: scan args for `-o <path>`, ensure that file exists + is
# executable, then exit 0. Lets install.sh step 6 run end-to-end without a
# real Go toolchain while still exercising the merge-tick-into-mcp.json
# logic that follows the `cp` of the binary.
out=""
prev=""
for arg in "$@"; do
  if [[ "$prev" == "-o" && -n "$arg" ]]; then
    out="$arg"
    break
  fi
  prev="$arg"
done
if [[ -n "$out" ]]; then
  mkdir -p "$(dirname "$out")"
  printf '#!/usr/bin/env bash\necho "fake tick"\n' > "$out"
  chmod +x "$out"
fi
exit 0
STUB
chmod +x "$FAKE_BIN_DIR/go"

# Stub installers — neither needs network. Step 1 of install.sh picks the
# canary builder when jcode-patches/*.patch exists; since we keep that
# directory empty, install.sh falls through to jcode-install.sh.
cat > "$FAKE_REPO/scripts/build-jcode-canary.sh" <<'STUB'
#!/usr/bin/env bash
echo "[stub] build-jcode-canary invoked"
STUB
chmod +x "$FAKE_REPO/scripts/build-jcode-canary.sh"

cat > "$FAKE_REPO/skills/install-jcode/jcode-install.sh" <<'STUB'
#!/usr/bin/env bash
echo "[stub] jcode-install invoked"
STUB
chmod +x "$FAKE_REPO/skills/install-jcode/jcode-install.sh"

# Copy install.sh into the fake repo so its `repo_root` resolves there.
cp "$INSTALL_SH_SRC" "$FAKE_REPO/scripts/install.sh"
chmod +x "$FAKE_REPO/scripts/install.sh"

bash -n "$FAKE_REPO/scripts/install.sh" || fail "fake install.sh fails bash -n"

JCODE_HOME="$FAKE_HOME/.jcode"

# Path used to invoke install.sh: must include our stub-go so install.sh's
# `command -v go` check passes and step 6 actually runs (which is what
# triggers the mcp.json merge under test).
FAKE_PATH="$FAKE_BIN_DIR:$PATH"

count_baks() {
  find "$JCODE_HOME" -name '*.bak.*' 2>/dev/null | wc -l | tr -d ' '
}

# ── Mode A: IDEMPOTENT unset (original behavior) ─────────────────────────────
# Step 2 of install.sh does `mkdir -p "$JCODE_HOME/roles"` BEFORE the
# roles/ symlink call. That mkdir creates a real directory, and the very
# next overwrite_link backs it up to make room for the symlink. So every
# initial run produces exactly one .bak.<ts> (the roles directory).
# On rerun in non-idempotent mode, every existing symlink is backed up too.
info "Mode A run 1: IDEMPOTENT unset (initial install)"
HOME="$FAKE_HOME" PATH="$FAKE_PATH" bash "$FAKE_REPO/scripts/install.sh" >/dev/null
BAKS_A1="$(count_baks)"
info "Mode A run 1 produced $BAKS_A1 .bak.<ts> file(s) (expected: 1 — the roles dir created by mkdir then backed up)"
[[ "$BAKS_A1" == "1" ]] || fail "first run should produce exactly 1 backup (the roles dir); got $BAKS_A1"

info "Mode A run 2: IDEMPOTENT unset (rerun — must back up every existing symlink)"
sleep 1  # ensure timestamp differs so mv targets don't collide
HOME="$FAKE_HOME" PATH="$FAKE_PATH" bash "$FAKE_REPO/scripts/install.sh" >/dev/null
BAKS_A2="$(count_baks)"
info "Mode A run 2 produced $BAKS_A2 .bak.<ts> file(s) (expected: >1)"
[[ "$BAKS_A2" -gt "$BAKS_A1" ]] || fail "second non-idempotent run should back up existing symlinks (A1=$BAKS_A1, A2=$BAKS_A2)"

# ── Mode B: IDEMPOTENT=1 ──────────────────────────────────────────────────────
# Each scenario starts with a clean fake HOME so the .bak count reflects
# only what that scenario produced.
info "Resetting fake HOME before Mode B"
rm -rf "$FAKE_HOME"
mkdir -p "$FAKE_HOME"

info "Mode B run 1: IDEMPOTENT=1 (initial install, links created)"
HOME="$FAKE_HOME" IDEMPOTENT=1 PATH="$FAKE_PATH" bash "$FAKE_REPO/scripts/install.sh" >/dev/null
BAKS_B1="$(count_baks)"
info "Mode B run 1 produced $BAKS_B1 .bak.<ts> file(s) (expected: 1, same as Mode A)"
[[ "$BAKS_B1" == "1" ]] || fail "first idempotent run should produce exactly 1 backup (the roles dir); got $BAKS_B1"

info "Mode B run 2: IDEMPOTENT=1 (rerun — must skip everything, no new .bak files)"
HOME="$FAKE_HOME" IDEMPOTENT=1 PATH="$FAKE_PATH" bash "$FAKE_REPO/scripts/install.sh" >"$TMP/mode_b_run2.log"
BAKS_B2="$(count_baks)"
info "Mode B run 2 produced $BAKS_B2 .bak.<ts> file(s) (expected: same as B1=$BAKS_B1)"
[[ "$BAKS_B2" == "$BAKS_B1" ]] || fail "idempotent rerun should not create new .bak files (B1=$BAKS_B1, B2=$BAKS_B2)"

# Step-5 idempotency: the new scripts/ symlink (step 5 of install.sh) must not
# be backed up on an idempotent rerun. The skip count check above only proves
# "no new .bak files anywhere" generically; this pinpoints the new step.
[[ -L "$JCODE_HOME/scripts" ]] || fail "scripts/ should be a symlink after first install (step 5)"
[[ ! -e "$JCODE_HOME/scripts.bak."* ]] \
  || fail "idempotent rerun must not back up the scripts/ symlink (found $JCODE_HOME/scripts.bak.*)"
info "Mode B scripts/ idempotency: linked=$JCODE_HOME/scripts → $(readlink "$JCODE_HOME/scripts"), no .bak file"

# Every linked target should be in the skipping log.
SKIP_COUNT=$(grep -c '^.*skipping:' "$TMP/mode_b_run2.log" || true)
info "Mode B run 2 printed 'skipping:' $SKIP_COUNT time(s)"
[[ "$SKIP_COUNT" -gt 0 ]] || fail "idempotent rerun should print 'skipping:' lines"

# The summary line should mention IDEMPOTENT mode.
grep -q 'idempotent (IDEMPOTENT=1)' "$TMP/mode_b_run2.log" \
  || fail "summary line should mention 'idempotent (IDEMPOTENT=1)'"

# And the non-idempotent summary should mention the other mode.
HOME="$FAKE_HOME" PATH="$FAKE_PATH" bash "$FAKE_REPO/scripts/install.sh" >"$TMP/mode_a_summary.log"
grep -q 'overwrite (IDEMPOTENT unset)' "$TMP/mode_a_summary.log" \
  || fail "summary line should mention 'overwrite (IDEMPOTENT unset)' in non-idempotent mode"

# ── Mode C: cross-mode check — modifying the source should NOT bypass the
# skip in idempotent mode if readlink -f compares canonical paths.
# We won't rewrite source files (that's out of scope for this test), but we
# will confirm that pointing a symlink somewhere else and rerunning in
# idempotent mode does cause a re-link (the helper returns false).
info "Mode C: symlink dst pointing somewhere else must be re-linked even in IDEMPOTENT=1"
info "Resetting fake HOME before Mode C"
rm -rf "$FAKE_HOME"
mkdir -p "$FAKE_HOME"
HOME="$FAKE_HOME" IDEMPOTENT=1 PATH="$FAKE_PATH" bash "$FAKE_REPO/scripts/install.sh" >/dev/null
mkdir -p /tmp/elsewhere
rm -f "$JCODE_HOME/prompt-overlay.md" "$JCODE_HOME/prompt-overlay.md.bak."*
ln -s /tmp/elsewhere "$JCODE_HOME/prompt-overlay.md"
HOME="$FAKE_HOME" IDEMPOTENT=1 PATH="$FAKE_PATH" bash "$FAKE_REPO/scripts/install.sh" >"$TMP/mode_c.log"
# Should NOT say "skipping: prompt-overlay.md"
if grep -q 'skipping: prompt-overlay.md' "$TMP/mode_c.log"; then
  fail "is_same_link should return false when dst points elsewhere"
fi
# Should say it linked prompt-overlay.md (overwrite_link path)
grep -q 'linked prompt-overlay.md' "$TMP/mode_c.log" \
  || fail "expected 'linked prompt-overlay.md' in Mode C output"
rm -rf /tmp/elsewhere

# ── Mode D: --help text must mention IDEMPOTENT ──────────────────────────────
HELP_OUT="$(HOME="$FAKE_HOME" PATH="$FAKE_PATH" bash "$FAKE_REPO/scripts/install.sh" --help)"
echo "$HELP_OUT" | grep -q 'IDEMPOTENT=1' \
  || fail "--help output must mention IDEMPOTENT=1"
echo "$HELP_OUT" | grep -q 'Environment variables' \
  || fail "--help output must include an 'Environment variables' section"

# ── Mode E: tick MCP server merge into ~/.jcode/mcp.json ───────────────────
# Step 6 of install.sh builds + copies the tick daemon, then merges a tick
# entry into ~/.jcode/mcp.json so jcode spawns it on first use. The merge
# must be idempotent: reruns (in either IDEMPOTENT mode) MUST NOT rewrite
# mcp.json when it already has mcpServers.tick. Missing mcp.json must be
# created from scratch; malformed JSON must warn + skip without crashing.

info "Resetting fake HOME before Mode E"
rm -rf "$FAKE_HOME"
mkdir -p "$FAKE_HOME"
MCP_JSON="$JCODE_HOME/mcp.json"

# Sub-scenario E1: missing mcp.json — install creates it with mcpServers.tick.
info "Mode E1: missing mcp.json → install creates one with mcpServers.tick"
HOME="$FAKE_HOME" PATH="$FAKE_PATH" bash "$FAKE_REPO/scripts/install.sh" >"$TMP/mode_e1.log"
[[ -f "$MCP_JSON" ]] || fail "Mode E1: mcp.json should be created on first install"
python3 -c '
import json, sys
with open(sys.argv[1]) as f: d = json.load(f)
assert "mcpServers" in d, "missing mcpServers key"
assert "tick" in d["mcpServers"], "missing tick entry under mcpServers"
t = d["mcpServers"]["tick"]
assert t.get("shared") is True, "tick entry must have shared=true"
assert t.get("command"), "tick entry must have a command"
assert "mcp" in t.get("args", []), "tick entry args must include mcp subcommand"
print("OK")
' "$MCP_JSON" >/dev/null || fail "Mode E1: mcp.json content malformed (expected mcpServers.tick with shared=true and mcp arg)"

BAKS_E1="$(count_baks)"
# mcp.json was created from scratch — no backup. The roles-dir backup from
# step 2 still happens, so total baks count == 1 (same as Mode A).
[[ "$BAKS_E1" == "1" ]] || fail "Mode E1: mcp.json creation should not add a .bak; got $BAKS_E1 baks total (expected 1)"

# Sub-scenario E2: rerun with mcp.json present + tick entry — must skip
# silently, no .bak.<ts> for mcp.json, no rewrite of the file content.
info "Mode E2: rerun with tick present → no .bak, no rewrite (IDEMPOTENT unset)"
sleep 1  # different timestamp so a stray backup would be detectable
BEFORE_HASH="$(sha256sum "$MCP_JSON" | awk '{print $1}')"
HOME="$FAKE_HOME" PATH="$FAKE_PATH" bash "$FAKE_REPO/scripts/install.sh" >"$TMP/mode_e2.log"
AFTER_HASH="$(sha256sum "$MCP_JSON" | awk '{print $1}')"
[[ "$BEFORE_HASH" == "$AFTER_HASH" ]] || fail "Mode E2: mcp.json content changed on rerun (before=$BEFORE_HASH after=$AFTER_HASH)"
ls "$MCP_JSON".bak.* 2>/dev/null | grep -q . \
  && fail "Mode E2: mcp.json should NOT have a .bak.<ts> file on rerun when tick already present"
grep -q 'skipping.*mcp.json' "$TMP/mode_e2.log" \
  || fail "Mode E2: should log 'skipping: mcp.json' on rerun (got: $(grep -i 'mcp' "$TMP/mode_e2.log" || echo none))"

# Sub-scenario E3: same as E2 but with IDEMPOTENT=1 — also must not rewrite.
info "Mode E3: rerun with IDEMPOTENT=1 and tick present → no .bak, no rewrite"
sleep 1
BEFORE_HASH="$(sha256sum "$MCP_JSON" | awk '{print $1}')"
HOME="$FAKE_HOME" IDEMPOTENT=1 PATH="$FAKE_PATH" bash "$FAKE_REPO/scripts/install.sh" >"$TMP/mode_e3.log"
AFTER_HASH="$(sha256sum "$MCP_JSON" | awk '{print $1}')"
[[ "$BEFORE_HASH" == "$AFTER_HASH" ]] || fail "Mode E3: mcp.json changed on IDEMPOTENT=1 rerun"
ls "$MCP_JSON".bak.* 2>/dev/null | grep -q . \
  && fail "Mode E3: mcp.json should NOT have a .bak.<ts> on IDEMPOTENT=1 rerun"

# Sub-scenario E4: malformed mcp.json — install must warn + skip without
# crashing. This proves the JSON-safety fallback works.
info "Mode E4: malformed mcp.json → warn + skip, no crash"
rm -rf "$FAKE_HOME"
mkdir -p "$FAKE_HOME" "$JCODE_HOME"
MCP_JSON="$JCODE_HOME/mcp.json"
echo '{this is not valid json' > "$MCP_JSON"
set +e
HOME="$FAKE_HOME" PATH="$FAKE_PATH" bash "$FAKE_REPO/scripts/install.sh" >"$TMP/mode_e4.log" 2>"$TMP/mode_e4.err"
mode_e4_status=$?
set -e
[[ $mode_e4_status -eq 0 ]] || fail "Mode E4: install must exit 0 on malformed mcp.json (got $mode_e4_status)"
grep -qi 'malformed\|skip.*tick\|warn.*mcp' "$TMP/mode_e4.err" \
  || fail "Mode E4: should warn about malformed mcp.json (stderr: $(cat "$TMP/mode_e4.err"))"
# The malformed file must be left untouched — install must not have rewritten it.
ORIG_BYTES="$(wc -c < "$MCP_JSON")"
[[ "$ORIG_BYTES" -gt 0 ]] || fail "Mode E4: malformed mcp.json should be left intact, not deleted"
grep -q 'mcpServers' "$MCP_JSON" \
  && fail "Mode E4: install must not inject mcpServers into a malformed file"

# ── final report ─────────────────────────────────────────────────────────────
info "ALL CHECKS PASSED"
info "  Mode A (overwrite):  $BAKS_A1 → $BAKS_A2 .bak files (rerun backed up + re-linked)"
info "  Mode B (idempotent): $BAKS_B1 → $BAKS_B2 .bak files (rerun skipped, no growth)"
info "  Mode C: changing a symlink target triggers re-link in idempotent mode"
info "  Mode D: --help mentions IDEMPOTENT=1 and 'Environment variables'"
info "  Mode E1: missing mcp.json created with mcpServers.tick (shared=true)"
info "  Mode E2: rerun with tick present → no .bak, content unchanged (IDEMPOTENT unset)"
info "  Mode E3: IDEMPOTENT=1 rerun → no .bak, content unchanged"
info "  Mode E4: malformed mcp.json → warn + skip, install exits 0"