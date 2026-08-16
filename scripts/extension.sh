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
#
# Boundary: stops at the first directory containing `.git` (project
# root marker) — does NOT walk past project boundaries to ~/.jcode/.
# Walking all the way to $HOME would mistake the global ~/.jcode/
# (where bundle symlinks live) for the project's own .jcode/. This
# is the bug that bit the first doctor run inside lazible-jcode
# itself: PROJ_DIR resolved to ~/.jcode/ instead of being empty.
project_jcode_dir() {
  local dir="${1:-$PWD}"
  while [[ "$dir" != "/" ]]; do
    # If we hit a project boundary before finding .jcode/, stop.
    if [[ -d "$dir/.git" ]]; then
      if [[ -d "$dir/.jcode" ]]; then
        echo "$dir/.jcode"
        return 0
      fi
      return 1
    fi
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

# ---------- subcommand: skills ----------
# Discovery helper for jcode-native per-project skills at
# `./.jcode/skills/`. jcode auto-loads these with precedence over
# `~/.jcode/skills/`; this subcommand lets root enumerate what's
# available so the spawn prompt's required_skills[] field can be
# populated correctly.
cmd_skills() {
  local action="${1:-list}"
  case "$action" in
    list)
      if [[ -z "$PROJ_DIR" ]]; then
        echo "(no .jcode/ in cwd ancestors)"
        return 0
      fi
      local proj_skills="$PROJ_DIR/skills"
      local glob_skills="$HOME/.jcode/skills"
      if [[ ! -d "$proj_skills" ]]; then
        echo "(no $proj_skills)"
        return 0
      fi
      local found=0
      while IFS= read -r skill_md; do
        local name
        name="$(basename "$(dirname "$skill_md")")"
        if [[ -f "$glob_skills/$name/SKILL.md" ]]; then
          echo "per-project: $name  (overrides global)"
        else
          echo "per-project: $name"
        fi
        found=1
      done < <(find "$proj_skills" -mindepth 2 -maxdepth 2 -name SKILL.md -print 2>/dev/null)
      if [[ $found -eq 0 ]]; then
        echo "(no SKILL.md files under $proj_skills)"
      fi
      ;;
    *)
      echo "usage: extension.sh skills list" >&2
      return 2
      ;;
  esac
}

# ---------- subcommand: mcp ----------
# Discovery + validation helper for jcode-native per-project MCP
# config at `./.jcode/mcp.json`. jcode loads this with precedence
# over `~/.jcode/mcp.json` and merges later sources over earlier
# ones (see `crates/jcode-base/src/mcp/protocol.rs::load_project_locals`).
cmd_mcp() {
  local action="${1:-info}"
  case "$action" in
    info)
      if [[ -z "$PROJ_DIR" ]]; then
        echo "(no .jcode/ in cwd ancestors)"
        return 0
      fi
      local proj_mcp="$PROJ_DIR/mcp.json"
      if [[ ! -e "$proj_mcp" ]]; then
        echo "(no $proj_mcp — using global ~/.jcode/mcp.json)"
        return 0
      fi
      echo "per-project MCP config: $proj_mcp"
      if ! python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$proj_mcp" 2>/dev/null; then
        echo "  WARNING: invalid JSON syntax"
        return 3
      fi
      local count
      count=$(python3 -c "import json,sys; print(len(json.load(open(sys.argv[1])).get('mcpServers', {})))" "$proj_mcp" 2>/dev/null || echo "?")
      echo "  servers: $count"
      ;;
    *)
      echo "usage: extension.sh mcp info" >&2
      return 2
      ;;
  esac
}

# ---------- subcommand: doctor ----------
# Single-shot enumeration of all 9 per-project extension axes.
# Tells root what's wired up vs. what's relying on defaults. Designed
# to be run once at session start so root can plan its strategy.
#
# Output format (fixed column widths for easy grep):
#   AXIS   FILE                                   STATUS
#   ─────────────────────────────────────────────────────────
#   A1 overlay         <repo>/.jcode/prompt-overlay.md   per-project (active)
#   A2 worker policy   <repo>/.jcode/swarm-prompt.md     (not configured)
#   ...
cmd_doctor() {
  printf '%-30s %-50s %s\n' "AXIS" "FILE" "STATUS"
  printf '%-30s %-50s %s\n' "----" "----" "------"
  if [[ -z "$PROJ_DIR" ]]; then
    printf '%-30s %-50s %s\n' "(no .jcode/ in cwd ancestors)" "" "(none)"
    return 0
  fi
  # A1 overlay
  local s=""
  [[ -e "$PROJ_DIR/prompt-overlay.md" ]] && s="per-project (active)"
  [[ -z "$s" && -e "$HOME/.jcode/prompt-overlay.md" ]] && s="global only"
  [[ -z "$s" ]] && s="(not configured)"
  printf '%-30s %-50s %s\n' "A1 overlay" "$PROJ_DIR/prompt-overlay.md" "$s"
  # A2 worker policy
  s=""
  [[ -e "$PROJ_DIR/swarm-prompt.md" ]] && s="per-project (active)"
  [[ -z "$s" && -e "$HOME/.jcode/swarm-prompt.md" ]] && s="global only"
  [[ -z "$s" ]] && s="(not configured)"
  printf '%-30s %-50s %s\n' "A2 worker policy" "$PROJ_DIR/swarm-prompt.md" "$s"
  # A3 skills
  s=""
  if [[ -d "$PROJ_DIR/skills" ]]; then
    local n=0
    while IFS= read -r _; do n=$((n+1)); done < <(find "$PROJ_DIR/skills" -mindepth 2 -maxdepth 2 -name SKILL.md -print 2>/dev/null)
    s="per-project ($n skills)"
  fi
  [[ -z "$s" ]] && s="(not configured)"
  printf '%-30s %-50s %s\n' "A3 skills" "$PROJ_DIR/skills/" "$s"
  # A4 mcp
  s=""
  if [[ -e "$PROJ_DIR/mcp.json" ]]; then
    local count="?"
    count=$(python3 -c "import json,sys; print(len(json.load(open(sys.argv[1])).get('mcpServers', {})))" "$PROJ_DIR/mcp.json" 2>/dev/null || echo "?")
    s="per-project ($count servers)"
  fi
  [[ -z "$s" ]] && s="(not configured)"
  printf '%-30s %-50s %s\n' "A4 mcp" "$PROJ_DIR/mcp.json" "$s"
  # A5-A9 hooks
  for axis_def in \
    "A5 role override:$PROJ_DIR/roles/" \
    "A6 verify hook:$PROJ_DIR/verify.sh" \
    "A7 pre-merge hook:$PROJ_DIR/pre-merge.sh" \
    "A8 notify hook:$PROJ_DIR/notify.sh" \
    "A9 pre-spawn hook:$PROJ_DIR/pre-spawn.sh"; do
    local axis="${axis_def%%:*}"
    local file="${axis_def#*:}"
    s=""
    if [[ "$file" == */ ]] && [[ -d "$file" ]]; then
      local n=0
      while IFS= read -r _; do n=$((n+1)); done < <(find "$file" -mindepth 2 -maxdepth 2 -name SKILL.md -print 2>/dev/null) || true
      # roles/ uses .md files, not SKILL.md
      while IFS= read -r _; do n=$((n+1)); done < <(find "$file" -mindepth 1 -maxdepth 1 -name "*.md" -print 2>/dev/null) || true
      if [[ $n -gt 0 ]]; then s="per-project ($n roles)"; else s="(empty dir)"; fi
    elif [[ -x "$file" ]]; then
      s="per-project (executable)"
    elif [[ -e "$file" ]]; then
      s="per-project (NOT executable)"
    else
      s="(not configured)"
    fi
    printf '%-30s %-50s %s\n' "$axis" "$file" "$s"
  done
  echo ""
  echo "Run 'extension.sh help' for invocation details on each axis."
}

# ---------- dispatch ----------
case "$cmd" in
  role)        cmd_role "$@" ;;
  pre-merge)   cmd_pre_merge "$@" ;;
  verify)      cmd_verify "$@" ;;
  notify)      cmd_notify "$@" ;;
  pre-spawn)   cmd_pre_spawn "$@" ;;
  skills)      cmd_skills "$@" ;;
  mcp)         cmd_mcp "$@" ;;
  doctor)      cmd_doctor "$@" ;;
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
  skills list                          Enumerate per-project skills (jcode-native)
  mcp info                             Show per-project MCP config status (jcode-native)
  doctor                               Single-shot enumeration of all 9 extension axes

Per-project hooks live at <repo>/.jcode/{pre-merge,verify,notify,pre-spawn}.sh
Per-project role overrides live at <repo>/.jcode/roles/<name>.md
Per-project skills live at <repo>/.jcode/skills/<name>/SKILL.md (jcode-native)
Per-project MCP servers live at <repo>/.jcode/mcp.json (jcode-native)
See docs/EXTENSIONS.md for the full 9×7 boundary-behavior walkthrough.
EOF
    ;;
  *)
    echo "extension.sh: unknown subcommand '$cmd' (try 'help')" >&2
    exit 2
    ;;
esac