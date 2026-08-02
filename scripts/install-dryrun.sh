#!/usr/bin/env bash
# Simulate scripts/install.sh end-to-end inside a disposable HOME.
set -euo pipefail

DEFAULT_HOME="${TMPDIR:-/tmp}/lazible-jcode-dryrun-$$/home"
DEFAULT_REPO="/home/leroy/Project/lazible-jcode"
SIM_HOME="$DEFAULT_HOME"
REPO_ROOT="$DEFAULT_REPO"
CURRENT_STEP="arguments"
DRYRUN_PASSED=0

print_help() {
  cat <<EOF
Usage: $0 [options]

Simulate all four scripts/install.sh steps without touching the real ~/.jcode/.

Options:
  --home <path>  Disposable simulated HOME. Default: $DEFAULT_HOME
  --repo <path>  Source repository. Default: $DEFAULT_REPO
  -h, --help     Show this help.
EOF
}

fail() {
  printf 'DRYRUN: FAIL %s: %s\n' "$1" "$2" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --home)
      [[ $# -ge 2 && -n "$2" ]] || fail arguments "--home requires a path"
      SIM_HOME="$2"
      shift 2
      ;;
    --repo)
      [[ $# -ge 2 && -n "$2" ]] || fail arguments "--repo requires a path"
      REPO_ROOT="$2"
      shift 2
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      fail arguments "unknown flag: $1"
      ;;
  esac
done

# Resolve paths before installing. Since EXIT removes SIM_HOME recursively,
# reject paths that could contain the checkout or point at the caller's HOME.
[[ -d "$REPO_ROOT" ]] || fail setup "repo does not exist: $REPO_ROOT"
REPO_ROOT="$(cd "$REPO_ROOT" && pwd -P)"
mkdir -p "$SIM_HOME"
SIM_HOME="$(cd "$SIM_HOME" && pwd -P)"
REAL_HOME="$(cd "${HOME:-/}" && pwd -P)"
REAL_JCODE_HOME="$REAL_HOME/.jcode"

[[ "$SIM_HOME" != "/" ]] || fail arguments "refusing to use / as --home"
[[ "$SIM_HOME" != "$REAL_HOME" ]] || fail arguments "refusing to use the real HOME as --home"
[[ "$SIM_HOME" != "$REAL_JCODE_HOME" ]] || fail arguments "refusing to use the real ~/.jcode as --home"
case "$REAL_HOME/" in
  "$SIM_HOME/"*) fail arguments "--home must not contain the real HOME" ;;
esac
case "$REPO_ROOT/" in
  "$SIM_HOME/"*) fail arguments "--home must not contain the source repo" ;;
esac

cleanup() {
  local status=$?
  trap - EXIT ERR
  if ! rm -rf -- "$SIM_HOME"; then
    printf 'DRYRUN: FAIL cleanup: could not remove %s\n' "$SIM_HOME" >&2
    exit 1
  fi
  if [[ $status -eq 0 && $DRYRUN_PASSED -eq 1 ]]; then
    printf 'DRYRUN: PASS\n'
  fi
  exit "$status"
}

unexpected_error() {
  local status=$?
  trap - ERR
  fail "$CURRENT_STEP" "unexpected command failure (exit $status)"
}

trap cleanup EXIT
trap unexpected_error ERR

JCODE_HOME="$SIM_HOME/.jcode"
INSTALL_DIR="$SIM_HOME/.local/bin"
TIMESTAMP="$(date +%s)"
INSTALL_SCRIPT="$REPO_ROOT/scripts/install.sh"

info() { printf '%s\n' "$*"; }
warn() { printf '%s\n' "$*" >&2; }

verify_link() {
  local step="$1" link="$2" expected="$3" target
  [[ -L "$link" ]] || fail "$step" "missing symlink: $link"
  target="$(readlink "$link")"
  [[ "$target" == "$expected" ]] || fail "$step" "$link resolves to $target, expected $expected"
}

for required in \
  "$INSTALL_SCRIPT" \
  "$REPO_ROOT/AGENTS.md" \
  "$REPO_ROOT/swarm/prompt-overlay.md" \
  "$REPO_ROOT/swarm/swarm-prompt.md" \
  "$REPO_ROOT/swarm/ARCHITECTURE.md" \
  "$REPO_ROOT/swarm/roles" \
  "$REPO_ROOT/skills"; do
  [[ -e "$required" ]] || fail setup "missing source: $required"
done

# Source only overwrite_link() from the real installer. Keeping the function
# body in one place prevents the dry-run from drifting from install.sh.
source <(awk '
  /^overwrite_link\(\) \{/ { copying=1 }
  copying { print }
  copying && /^}/ { exit }
' "$INSTALL_SCRIPT")
declare -F overwrite_link >/dev/null || fail setup "could not source overwrite_link from $INSTALL_SCRIPT"

CURRENT_STEP="step 1"
info "── step 1/4: install jcode binary (simulated) ──"
mkdir -p "$INSTALL_DIR"
cat >"$INSTALL_DIR/jcode" <<'STUB'
#!/usr/bin/env bash
printf 'jcode dry-run stub\n'
STUB
chmod +x "$INSTALL_DIR/jcode"
[[ -x "$INSTALL_DIR/jcode" ]] || fail "$CURRENT_STEP" "simulated jcode binary is not executable"

CURRENT_STEP="step 2"
info "── step 2/4: overlay + swarm config ──"
mkdir -p "$JCODE_HOME" "$JCODE_HOME/roles"
overwrite_link "$REPO_ROOT/swarm/prompt-overlay.md" "$JCODE_HOME/prompt-overlay.md" "prompt-overlay.md"
overwrite_link "$REPO_ROOT/swarm/swarm-prompt.md" "$JCODE_HOME/swarm-prompt.md" "swarm-prompt.md"
overwrite_link "$REPO_ROOT/swarm/ARCHITECTURE.md" "$JCODE_HOME/ARCHITECTURE.md" "ARCHITECTURE.md"
overwrite_link "$REPO_ROOT/swarm/roles" "$JCODE_HOME/roles" "roles/"
verify_link "$CURRENT_STEP" "$JCODE_HOME/prompt-overlay.md" "$REPO_ROOT/swarm/prompt-overlay.md"
verify_link "$CURRENT_STEP" "$JCODE_HOME/swarm-prompt.md" "$REPO_ROOT/swarm/swarm-prompt.md"
verify_link "$CURRENT_STEP" "$JCODE_HOME/ARCHITECTURE.md" "$REPO_ROOT/swarm/ARCHITECTURE.md"
verify_link "$CURRENT_STEP" "$JCODE_HOME/roles" "$REPO_ROOT/swarm/roles"

CURRENT_STEP="step 3"
info "── step 3/4: skills ──"
mkdir -p "$JCODE_HOME/skills"
skill_count=0
for skill_dir in "$REPO_ROOT/skills"/*; do
  [[ -d "$skill_dir" && -f "$skill_dir/SKILL.md" ]] || continue
  name="$(basename "$skill_dir")"
  overwrite_link "$skill_dir" "$JCODE_HOME/skills/$name" "skill:$name"
  skill_count=$((skill_count + 1))
done
info "linked $skill_count skill(s)"
[[ $skill_count -gt 0 ]] || fail "$CURRENT_STEP" "no skills were linked"
linked_skill=0
for skill_link in "$JCODE_HOME/skills"/*; do
  if [[ -L "$skill_link" ]]; then
    linked_skill=1
    break
  fi
done
[[ $linked_skill -eq 1 ]] || fail "$CURRENT_STEP" "no skill symlink found"

CURRENT_STEP="step 4"
info "── step 4/4: AGENTS.md ──"
overwrite_link "$REPO_ROOT/AGENTS.md" "$JCODE_HOME/AGENTS.md" "AGENTS.md"
verify_link "$CURRENT_STEP" "$JCODE_HOME/AGENTS.md" "$REPO_ROOT/AGENTS.md"

info "lazible-jcode dry-run complete; cleaning $SIM_HOME"
DRYRUN_PASSED=1
exit 0
