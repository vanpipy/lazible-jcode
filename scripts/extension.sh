#!/usr/bin/env bash
# scripts/extension.sh — bundle's per-project extension mechanisms.
#
# The bundle defines a small set of conventions for projects that want
# to customize behavior without forking the bundle. Each convention is
# a per-project file at `<repo>/.jcode/<name>.{sh,md}`. This script
# is the single entry point that root calls to invoke those
# conventions. Five subcommands, one per convention.
#
# Usage:
#   scripts/extension.sh role <name>
#     Print the role template body for <name>. Per-project file at
#     <cwd-or-ancestor>/.jcode/roles/<name>.md wins; otherwise
#     ~/.jcode/roles/<name>.md. Empty per-project file falls back to
#     global with a warning to stderr. <name> must be one of the 6
#     roles (reviewer, implementer, investigator, migrator,
#     test-writer, doc-writer) — exit 2 otherwise.
#
#   scripts/extension.sh pre-merge <branch> <base_commit> <role>
#     Run the per-project pre-merge hook at <cwd>/.jcode/pre-merge.sh
#     if present and executable. Exit 0 if absent / not executable
#     (with a warning if not executable). Exit hook's exit code if
#     it ran. 5-minute timeout (300s).
#
#   scripts/extension.sh verify
#     Run the per-project verify hook at <cwd>/.jcode/verify.sh if
#     present and executable. Exit 0 if absent. Exit hook's exit
#     code otherwise. Used by the bundle's verification suite
#     step 6.
#
#   scripts/extension.sh notify <status> <label> <artifact_path>
#     Run the per-project notify hook at <cwd>/.jcode/notify.sh if
#     present. Bypass: notify failure does NOT block the workflow
#     (exit 0 always, with a warning to stderr on hook failure).
#
#   scripts/extension.sh pre-spawn <label> <role> <files_count>
#     Run the per-project pre-spawn hook at <cwd>/.jcode/pre-spawn.sh
#     if present. Exit 0 if absent. Hook's stdout is parsed for
#     KEY=VALUE lines (regex ^[A-Z_][A-Z0-9_]*=); each line is
#     exported as an env var in the calling shell via a small
#     response protocol (see output protocol below). Hook's exit
#     code is propagated.
#
# Output protocol for pre-spawn:
#   stdout KEY=VALUE lines become env vars in the calling shell.
#   Anything else on stdout is silently dropped.
#   stderr is passed through unchanged.
#
# Conventions (which is the bundle, which is the project):
#   - The script itself is bundle-owned (lives in scripts/).
#   - The per-project files it looks for are project-owned
#     (<repo>/.jcode/<name>.*) and committed with the project.
#   - The bundle never creates or modifies per-project files.
#   - Absence of a per-project file is never a failure — root just
#     proceeds with the default behavior.

set -euo pipefail

# Walk up from a directory until we find a `.jcode/` dir. Echoes the
# path to that `.jcode/` dir, or empty string if none found.
project_jcode_dir() {
  local dir="${1:-$PWD}"
  while [[ "$dir" != "/" ]]; do
    if [[ -d "$dir/.jcode" ]]; then
      echo "$dir/.jcode"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  return 1
}

# Globals used by subcommands.
PROJ_DIR=""
if PROJ_DIR="$(project_jcode_dir 2>/dev/null)"; then :; fi

cmd="${1:-help}"
shift || true

# ---------- subcommand: role ----------
cmd_role() {
  local name="${1:?usage: extension.sh role <name>}"
  if [[ ! "$name" =~ ^(reviewer|implementer|investigator|migrator|test-writer|doc-writer)$ ]]; then
    echo "extension.sh: role '$name' is not one of the 6 (red line)" >&2
    exit 2
  fi
  if [[ -n "$PROJ_DIR" && -s "$PROJ_DIR/roles/$name.md" ]]; then
    cat "$PROJ_DIR/roles/$name.md"
    return
  fi
  if [[ -n "$PROJ_DIR" && -e "$PROJ_DIR/roles/$name.md" ]]; then
    echo "extension.sh: $PROJ_DIR/roles/$name.md is empty, falling back to global" >&2
  fi
  if [[ ! -f "$HOME/.jcode/roles/$name.md" ]]; then
    echo "extension.sh: no role file at $HOME/.jcode/roles/$name.md" >&2
    exit 3
  fi
  cat "$HOME/.jcode/roles/$name.md"
}

# ---------- subcommand: pre-merge ----------
cmd_pre_merge() {
  local branch="${1:?usage: extension.sh pre-merge <branch> <base> <role>}"
  local base="${2:?usage: extension.sh pre-merge <branch> <base> <role>}"
  local role="${3:?usage: extension.sh pre-merge <branch> <base> <role>}"
  if [[ -z "$PROJ_DIR" ]]; then
    echo "extension.sh: no .jcode/ in cwd ancestors; skipping pre-merge hook"
    return 0
  fi
  local hook="$PROJ_DIR/pre-merge.sh"
  if [[ ! -e "$hook" ]]; then
    echo "extension.sh: no $hook; skipping"
    return 0
  fi
  if [[ ! -x "$hook" ]]; then
    echo "extension.sh: $hook exists but is not executable. Run: chmod +x $hook" >&2
    return 0
  fi
  local hook_rc=0
  timeout 300 "$hook" "$branch" "$base" "$role" || hook_rc=$?
  if [[ $hook_rc -ne 0 ]]; then
    if [[ $hook_rc -eq 124 ]]; then
      echo "extension.sh: pre-merge hook timed out after 5 min. Merge blocked." >&2
    else
      echo "extension.sh: pre-merge hook failed (exit $hook_rc). Merge blocked." >&2
    fi
    return $hook_rc
  fi
}

# ---------- subcommand: verify ----------
cmd_verify() {
  if [[ -z "$PROJ_DIR" ]]; then
    return 0
  fi
  local hook="$PROJ_DIR/verify.sh"
  if [[ ! -x "$hook" ]]; then
    return 0
  fi
  "$hook"
}

# ---------- subcommand: notify ----------
# Bypass mode: always exit 0, log hook failure to stderr.
cmd_notify() {
  local status="${1:?usage: extension.sh notify <status> <label> <artifact>}"
  local label="${2:?usage: extension.sh notify <status> <label> <artifact>}"
  local artifact="${3:?usage: extension.sh notify <status> <label> <artifact>}"
  if [[ -z "$PROJ_DIR" ]]; then
    return 0
  fi
  local hook="$PROJ_DIR/notify.sh"
  if [[ ! -x "$hook" ]]; then
    return 0
  fi
  if ! "$hook" "$status" "$label" "$artifact"; then
    echo "extension.sh: notify hook failed (exit $?); bypass (does not block workflow)" >&2
  fi
  return 0
}

# ---------- subcommand: pre-spawn ----------
# Emits KEY=VALUE exports to a response file so the caller can source
# them. Usage:
#   exports=$(mktemp); extension.sh pre-spawn ... --exports "$exports"
#   source "$exports"
cmd_pre_spawn() {
  local label="" role="" count="" exports=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --exports) exports="${2:?--exports requires arg}"; shift 2 ;;
      *) : "${label:=$1}"; shift; : "${role:=$1}"; shift; : "${count:=$1}"; shift ;;
    esac
  done
  if [[ -z "$label" || -z "$role" || -z "$count" ]]; then
    echo "usage: extension.sh pre-spawn <label> <role> <count> [--exports FILE]" >&2
    return 2
  fi
  if [[ -z "$PROJ_DIR" ]]; then
    return 0
  fi
  local hook="$PROJ_DIR/pre-spawn.sh"
  if [[ ! -x "$hook" ]]; then
    return 0
  fi
  local out
  if ! out="$("$hook" "$label" "$role" "$count" 2>/dev/null)"; then
    local rc=$?
    echo "extension.sh: pre-spawn hook failed (exit $rc). Spawn aborted." >&2
    return $rc
  fi
  if [[ -n "$exports" ]]; then
    : > "$exports"  # truncate
    while IFS= read -r line; do
      if [[ "$line" =~ ^[A-Z_][A-Z0-9_]*= ]]; then
        echo "export $line" >> "$exports"
      fi
    done <<< "$out"
  fi
}

# ---------- dispatch ----------
case "$cmd" in
  role)        cmd_role "$@" ;;
  pre-merge)   cmd_pre_merge "$@" ;;
  verify)      cmd_verify "$@" ;;
  notify)      cmd_notify "$@" ;;
  pre-spawn)   cmd_pre_spawn "$@" ;;
  help|--help|-h|"")
    cat <<EOF
scripts/extension.sh — bundle's per-project extension mechanisms.

Subcommands:
  role <name>                          Print role template (per-project → global fallback)
  pre-merge <branch> <base> <role>     Run pre-merge hook if present (5 min timeout)
  verify                               Run verify hook if present
  notify <status> <label> <artifact>   Run notify hook if present (bypass mode)
  pre-spawn <label> <role> <count>     Run pre-spawn hook if present
     [--exports FILE]                  Emit KEY=VALUE exports to FILE for caller to source

Per-project hooks live at <repo>/.jcode/{pre-merge,verify,notify,pre-spawn}.sh
Per-project role overrides live at <repo>/.jcode/roles/<name>.md
See docs/EXTENSIONS.md for the full 8×7 boundary-behavior walkthrough.
EOF
    ;;
  *)
    echo "extension.sh: unknown subcommand '$cmd' (try 'help')" >&2
    exit 2
    ;;
esac