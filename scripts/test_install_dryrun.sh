#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd -P)"
dryrun_script="$repo_root/scripts/install-dryrun.sh"

fail() {
  printf 'test_install_dryrun: FAIL: %s\n' "$*" >&2
  exit 1
}

[[ -x "$dryrun_script" ]] || fail "missing executable: $dryrun_script"

temp_root="$(mktemp -d "${TMPDIR:-/tmp}/test-install-dryrun.XXXXXX")"
sim_home="$temp_root/home"
output_file="$temp_root/stdout"
stderr_file="$temp_root/stderr"
observation_file="$temp_root/observed-links"
mkdir -p "$sim_home"

cleanup() {
  command rm -rf -- "$temp_root"
}
trap cleanup EXIT

# install-dryrun.sh must remove sim_home on EXIT, so inspect the links from an
# exported rm wrapper immediately before that cleanup removes them.
EXPECTED_DRYRUN_HOME="$sim_home"
EXPECTED_DRYRUN_REPO="$repo_root"
DRYRUN_OBSERVATION_FILE="$observation_file"
export EXPECTED_DRYRUN_HOME EXPECTED_DRYRUN_REPO DRYRUN_OBSERVATION_FILE

rm() {
  if [[ $# -ge 3 && "$1" == "-rf" && "$2" == "--" && "$3" == "$EXPECTED_DRYRUN_HOME" ]]; then
    local jcode_home="$EXPECTED_DRYRUN_HOME/.jcode"
    local failed=0
    local link expected

    # Append to the observation file so later reads see a single PASS line even
    # if previous runs of the wrapper appended a FAIL note.
    while IFS='|' read -r link expected; do
      if [[ ! -L "$link" || "$(readlink "$link")" != "$expected" ]]; then
        printf 'missing or incorrect symlink: %s -> %s\n' "$link" "$expected" >>"$DRYRUN_OBSERVATION_FILE"
        failed=1
      fi
    done <<EOF
$jcode_home/prompt-overlay.md|$EXPECTED_DRYRUN_REPO/swarm/prompt-overlay.md
$jcode_home/swarm-prompt.md|$EXPECTED_DRYRUN_REPO/swarm/swarm-prompt.md
$jcode_home/ARCHITECTURE.md|$EXPECTED_DRYRUN_REPO/swarm/ARCHITECTURE.md
$jcode_home/roles|$EXPECTED_DRYRUN_REPO/swarm/roles
$jcode_home/AGENTS.md|$EXPECTED_DRYRUN_REPO/AGENTS.md
$jcode_home/scripts|$EXPECTED_DRYRUN_REPO/scripts
EOF

    local skill_linked=0
    local candidate
    shopt -s nullglob
    for candidate in "$jcode_home/skills/"*; do
      if [[ -L "$candidate" ]]; then
        skill_linked=1
        break
      fi
    done
    shopt -u nullglob
    if [[ $skill_linked -ne 1 ]]; then
      printf 'no skill symlink found under %s\n' "$jcode_home/skills" >>"$DRYRUN_OBSERVATION_FILE"
      failed=1
    fi

    if [[ $failed -eq 0 ]]; then
      printf 'PASS\n' >"$DRYRUN_OBSERVATION_FILE"
    fi
  fi

  command rm "$@"
}
export -f rm

status=0
"$dryrun_script" --home "$sim_home" --repo "$repo_root" >"$output_file" 2>"$stderr_file" || status=$?

[[ $status -eq 0 ]] || {
  cat "$output_file" >&2
  cat "$stderr_file" >&2
  fail "install-dryrun.sh exited $status"
}
grep -Fqx 'DRYRUN: PASS' "$output_file" || {
  cat "$output_file" >&2
  cat "$stderr_file" >&2
  fail "stdout did not contain DRYRUN: PASS"
}
[[ -f "$observation_file" && "$(cat "$observation_file")" == "PASS" ]] || {
  [[ -f "$observation_file" ]] && cat "$observation_file" >&2
  fail "expected symlinks were not present immediately before cleanup"
}
[[ ! -e "$sim_home" && ! -L "$sim_home" ]] || fail "simulated home was not removed after exit"

printf 'test_install_dryrun: PASS\n'
