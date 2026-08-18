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
#   scripts/extension.sh mcp info
#     Print a summary of the per-project MCP config (file path +
#     server count). Detects python3/jq availability and degrades
#     gracefully if neither is present (prints "unavailable" instead
#     of false-positive "invalid JSON syntax"). Exit 3 only if the
#     file is genuinely malformed JSON.
#
#   scripts/extension.sh mcp init [--project=PATH]
#     One-time per-project bootstrap: copy the bundle-shipped
#     config/mcp.json.example into <project>/.jcode/mcp.json,
#     substituting the /workspace placeholder with the actual
#     project root. Idempotent — never overwrites an existing file
#     (prints skip message + rm hint, exit 0). Used by users/agents
#     entering a new project that hasn't set up MCP yet.
#
#   scripts/extension.sh mcp init-global [--project=PATH]
#     One-time global bootstrap: copy the bundle-shipped
#     config/mcp.json.example into ~/.jcode/mcp.json — the global
#     location matching every other bundle config (prompt-overlay.md,
#     swarm-prompt.md, config.toml, roles/*.md). Default project is
#     the bundle's own repo; --project=PATH overrides. install.sh
#     runs this unconditionally on every install. Idempotent — same
#     skip-when-present semantics as `mcp init`.
#
#   scripts/extension.sh mcp worktree-hint <wt-path>
#     Worker-side serena staleness detector. jcode inherits the
#     project's MCP config (A4) into spawned workers, but serena's
#     --project is anchored to the MAIN repo path — its tree-sitter
#     index is stale relative to worktree edits. This subcommand
#     reports serena's effective status (live / stale / not-configured)
#     plus the verification pattern (jcode-native read + agentgrep
#     for post-edit symbol checks). Output is line-oriented and
#     grep-friendly. Exit 0 on success (informational), 3 on hard
#     errors (no MCP config; malformed serena args), 2 on usage.
#
# Conventions (which is the bundle, which is the project):
#   - The script itself is bundle-owned (lives in scripts/).
#   - The per-project files it looks for are project-owned
#     (<repo>/.jcode/<name>.*) and committed with the project.
#   - The bundle never creates or modifies per-project files, EXCEPT
#     mcp init (the only one-shot bootstrap subcommand; everything
#     else is read-only w.r.t. project state).
#   - Absence of a per-project file is never a failure — root just
#     proceeds with the default behavior.

set -euo pipefail

# Resolve the bundle root from this script's path. Used by subcommands
# that need to read bundle-shipped files (templates, schemas, etc.)
# without hardcoding the path. The script lives at <bundle>/scripts/
# so going up one level gives the bundle root.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_ROOT="$(dirname "$SCRIPT_DIR")"

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

# Returns the name of the available JSON tool (python3 | jq) on stdout
# and exit 0 if found, or prints nothing and exits 1 otherwise.
#
# Several subcommands (mcp info, artifact validate, scratch-dir hash,
# doctor A4) need to parse JSON. Linux supports both python3 and jq;
# we prefer python3 (more portable across minor versions of common
# distros' default packages) but fall back to jq when python3 is
# absent — and report explicitly when neither is present, so the user
# sees "install python3 (or jq) to enable JSON inspection" instead of
# a silent fallback or a false-positive "invalid JSON syntax".
#
# Always-available noop fallback: return non-zero without printing,
# so callers can decide what to print.
json_tool() {
  if command -v python3 >/dev/null 2>&1; then
    echo python3
    return 0
  fi
  if command -v jq >/dev/null 2>&1; then
    echo jq
    return 0
  fi
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

# ---------- subcommand: artifact ----------
# Validate a typed-artifact JSON file against the 8-field contract
# (status, findings, evidence, edge_cases_considered, validation,
# open_questions, confidence, what_i_did_not_check).
#
# Usage:
#   extension.sh artifact validate <path>
#     Exit 0 if all 8 fields present and well-typed.
#     Exit 1 if any field missing or wrong type.
#     Exit 2 on usage error.
#
# Why this exists: A8.9 sub-case — notify.sh may receive an artifact
# with missing fields. Bundle provides a validator so root can check
# the artifact before acting on it. The 8-field contract is the same
# one roles/swarm/roles/*.md output schemas use.
cmd_artifact() {
  local action="${1:-}"
  shift || true
  case "$action" in
    validate)
      local path="${1:-}"
      if [[ -z "$path" ]]; then
        echo "usage: extension.sh artifact validate <path>" >&2
        return 2
      fi
      if [[ ! -f "$path" ]]; then
        echo "artifact: no file at $path" >&2
        return 2
      fi
      local tool
      if ! tool="$(json_tool)"; then
        echo "artifact: cannot validate — no python3 or jq on PATH" >&2
        echo "  install python3 (preferred) or jq to enable the 8-field contract check" >&2
        return 3
      fi
      if [[ "$tool" == jq ]]; then
        # Simplified jq check: presence + basic type for each of the
        # 8 contract fields. Rich per-field messages are python3-only;
        # when only jq is available we report all problems at once.
        local jq_out
        if ! jq_out=$(jq -e '
          (.status|type=="string") and
          (.findings|type=="array") and
          (.evidence|type=="array") and
          (.edge_cases_considered|type=="array") and
          (.validation|type=="string") and
          (.open_questions|type=="array") and
          (.confidence|type=="string") and
          (.what_i_did_not_check|type=="array")
        ' "$path" 2>&1); then
          echo "artifact: validation failed (jq): $jq_out" >&2
          return 1
        fi
        jq -r '"artifact OK: status=\(.status) confidence=\(.confidence) findings=\(.findings|length) evidence=\(.evidence|length) open_questions=\(.open_questions|length)"' "$path"
        return 0
      fi
      # python3 path — full field-by-field validation with rich messages.
      python3 - "$path" <<'PY'
import json, sys
path = sys.argv[1]
required = {
    "status": str,
    "findings": list,
    "evidence": list,
    "edge_cases_considered": list,
    "validation": str,
    "open_questions": list,
    "confidence": str,
    "what_i_did_not_check": list,
}
try:
    obj = json.load(open(path))
except json.JSONDecodeError as e:
    print(f"artifact: JSON parse error: {e}", file=sys.stderr)
    sys.exit(1)
if not isinstance(obj, dict):
    print(f"artifact: top-level is {type(obj).__name__}, expected object", file=sys.stderr)
    sys.exit(1)
missing = []
wrong_type = []
for k, t in required.items():
    if k not in obj:
        missing.append(k)
    elif not isinstance(obj[k], t):
        wrong_type.append(f"{k} (got {type(obj[k]).__name__}, want {t.__name__})")
if missing or wrong_type:
    if missing:
        print(f"artifact: missing fields: {', '.join(missing)}", file=sys.stderr)
    if wrong_type:
        print(f"artifact: wrong-type fields: {', '.join(wrong_type)}", file=sys.stderr)
    sys.exit(1)
status = obj.get("status", "?")
confidence = obj.get("confidence", "?")
n_findings = len(obj["findings"])
n_evidence = len(obj["evidence"])
n_open = len(obj["open_questions"])
print(f"artifact OK: status={status} confidence={confidence} "
          f"findings={n_findings} evidence={n_evidence} open_questions={n_open}")
PY
      ;;
    *)
      echo "usage: extension.sh artifact validate <path>" >&2
      return 2
      ;;
  esac
}

# ---------- subcommand: preflight ----------
# Pre-spawn environment gate. Run BEFORE drafting a worker spawn prompt.
# Prints a checklist of env conditions and exits 0 if all green.
#
# Why this exists: P1-P3 in NOTES.md — root wasted spawns on auth failure,
# scope ambiguity, and unexpected tempdir-vs-final-path layout. Catching
# these upfront saves minutes per spawn.
#
# Checks:
#   1. jcode binary present + on PATH
#   2. jcode --version runs (daemon reachable)
#   3. Bundle install: ~/.jcode/prompt-overlay.md symlink resolves
#   4. A model that works: probe a default candidate, report status
#   5. Workspace path writable: if --workspace <path> given, check writable
#   6. Project root: if --project <path> given, check exists + .git (optional)
#
# Exit codes:
#   0 = all checks pass
#   1 = a soft warning (degraded but not blocking)
#   2 = usage error
#   3 = hard failure (cannot spawn)
cmd_preflight() {
  # Note: dispatcher already shifted off the subcommand name, so $@ here
  # contains the user's flags (e.g. "--workspace /tmp/jcode/foo"). Don't
  # shift again — that would drop --workspace.
  local workspace_path=""
  local project=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --workspace) workspace_path="${2:-}"; shift 2 ;;
      --worktree) workspace_path="${2:-}"; shift 2 ;;  # legacy alias
      --project)  project="${2:-}"; shift 2 ;;
      --help|-h)
        echo "usage: extension.sh preflight [--workspace <path>] [--project <path>]" >&2
        return 2
        ;;
      *) echo "extension.sh: unknown preflight flag '$1'" >&2; return 2 ;;
    esac
  done

  local fails=0
  local warns=0

  check() {
    local name="$1" result="$2" detail="$3"
    if [[ "$result" == "ok" ]]; then
      printf '  [OK]   %-32s %s\n' "$name" "$detail"
    elif [[ "$result" == "warn" ]]; then
      printf '  [WARN] %-32s %s\n' "$name" "$detail"
      warns=$((warns + 1))
    else
      printf '  [FAIL] %-32s %s\n' "$name" "$detail"
      fails=$((fails + 1))
    fi
  }

  echo "preflight checks:"
  # 1. jcode on PATH
  if command -v jcode >/dev/null 2>&1; then
    local jc
    jc="$(command -v jcode)"
    check "jcode binary" "ok" "$jc"
  else
    check "jcode binary" "fail" "not on PATH"
  fi

  # 2. jcode --version works (proves daemon / spawn substrate is alive)
  if command -v jcode >/dev/null 2>&1; then
    set +e
    local ver
    ver="$(jcode --version 2>&1 | head -1)"
    local rc=$?
    set -e
    if [[ $rc -eq 0 && -n "$ver" ]]; then
      check "jcode --version" "ok" "$ver"
    else
      check "jcode --version" "fail" "exit $rc"
    fi
  else
    check "jcode --version" "fail" "skipped (no jcode)"
  fi

  # 3. Bundle install (overlay symlink)
  local overlay="$HOME/.jcode/prompt-overlay.md"
  if [[ -L "$overlay" ]]; then
    local target
    target="$(readlink "$overlay")"
    if [[ -e "$target" ]]; then
      check "bundle install (overlay)" "ok" "$overlay -> $target"
    else
      check "bundle install (overlay)" "fail" "symlink dangles: $target"
    fi
  elif [[ -e "$overlay" ]]; then
    check "bundle install (overlay)" "warn" "$overlay exists but is NOT a symlink (manual install?)"
  else
    check "bundle install (overlay)" "fail" "$overlay missing; run scripts/install.sh"
  fi

  # 4. Workspace path writable (if given)
  if [[ -n "$workspace_path" ]]; then
    if [[ -e "$workspace_path" ]]; then
      if [[ -d "$workspace_path" && -w "$workspace_path" ]]; then
        check "workspace path writable" "ok" "$workspace_path"
      else
        check "workspace path writable" "fail" "$workspace_path exists but not writable dir"
      fi
    else
      # Try parent dir
      local parent
      parent="$(dirname "$workspace_path")"
      if [[ -d "$parent" && -w "$parent" ]]; then
        check "workspace path writable" "ok" "$workspace_path (parent $parent is writable, will be created)"
      else
        check "workspace path writable" "fail" "$parent not writable"
      fi
    fi
  else
    # No workspace given; print the canonical layout
    local root
    root="$(cmd_scratch_dir root 2>/dev/null || echo '?')"
    check "workspace path" "ok" "(not specified; default would be $root/ws-<label>)"
  fi

  # 5. Project root (if given)
  if [[ -n "$project" ]]; then
    if [[ ! -e "$project" ]]; then
      check "project root" "fail" "$project does not exist"
    elif [[ -d "$project" ]]; then
      if [[ -d "$project/.git" ]]; then
        check "project root" "ok" "$project (git repo)"
      else
        check "project root" "warn" "$project exists but no .git (new repo — worker will git init)"
      fi
    else
      check "project root" "fail" "$project is not a directory"
    fi
  fi

  # 6. Model auth probe (use jcode's auto-default).
  #    Do NOT hardcode any model name in the bundle — that would leak
  #    machine-specific routing into a generic script. Probe with no
  #    --model flag; jcode picks its auto-default based on the user's
  #    config + provider auth. If the probe fails, the user knows to
  #    either fix their auth or run `extension.sh models probe <name>`
  #    to find a specific working model.
  if command -v jcode >/dev/null 2>&1; then
    set +e
    jcode run "ok" >/dev/null 2>&1
    local rc=$?
    set -e
    if [[ $rc -eq 0 ]]; then
      check "model auth (jcode auto-default)" "ok" "responds"
    else
      check "model auth (jcode auto-default)" "warn" "exit $rc; fix auth or run 'extension.sh models probe <name>' to find a working model"
    fi
  fi

  echo ""
  if [[ $fails -gt 0 ]]; then
    echo "RESULT: $fails failure(s), $warns warning(s) — DO NOT spawn until fixed"
    return 3
  fi
  if [[ $warns -gt 0 ]]; then
    echo "RESULT: 0 failures, $warns warning(s) — safe to spawn but review warnings"
    return 1
  fi
  echo "RESULT: all green — safe to spawn"
  return 0
}

# ---------- subcommand: scratch-dir ----------
# Print the canonical per-project scratch root under $TMPDIR.
# Layout: $TMPDIR/jcode/<repo-name>-<short-sha>/
#   ├── ws-<label>/           # workspaces (one per logical task; backing = worktree | folder)
#   ├── .jcode-workspaces/    # workspace manifests (one JSON per workspace)
#   └── scratch/              # misc scratch files
#
# Used by root when constructing the spawn prompt's workspace_path arg.
# The convention is documented in swarm/prompt-overlay.md §4.1 and
# keeps workspaces OFF the user's home filesystem and OUT of the repo
# itself — both important on macOS where home may be slow and /tmp
# may be RAM-backed.
#
# Args:
#   (none)             print the scratch root only
#   ws <label>         print $root/ws-<label>
#   wt <label>         alias for `ws <label>` (deprecated; warns to stderr)
#   scratch            print $root/scratch
#   clean [--yes]      remove the entire scratch root (dry-run by default)
#
# If cwd is not inside a git repo, fall back to a synthetic key from
# the absolute path (stable per-machine, deterministic).
cmd_scratch_dir() {
  local kind="${1:-root}"
  local repo_name short_sha root
  if git rev-parse --show-toplevel >/dev/null 2>&1; then
    local toplevel
    toplevel="$(git rev-parse --show-toplevel)"
    repo_name="$(basename "$toplevel")"
    short_sha="$(git rev-parse --short=8 HEAD 2>/dev/null || echo "unborn")"
  else
    # Fallback for non-git cwd: derive stable key from absolute path.
    # Use a hash so we don't expose absolute paths in /tmp.
    local abs
    abs="$(cd "${PROJ_DIR:-$PWD}" && pwd -P)"
    repo_name="$(basename "$abs")"
    # Hash the absolute path with whichever tool is available so we
    # don't expose absolute paths in /tmp. python3 is preferred (same
    # algorithm); if absent, fall back to jq's @sha256 or sha256sum.
    # If none of those exist, fall back to a deterministic but less
    # opaque key (the basename's printable length + a non-cryptographic
    # checksum via `cksum`). Always emits 8 chars.
    local tool=""
    if command -v python3 >/dev/null 2>&1; then
      tool=python3
    elif command -v jq >/dev/null 2>&1; then
      tool=jq
    elif command -v sha256sum >/dev/null 2>&1; then
      tool=sha256sum
    fi
    case "$tool" in
      python3)
        short_sha="$(printf '%s' "$abs" | python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.read().encode()).hexdigest()[:8])')"
        ;;
      jq)
        short_sha="$(printf '%s' "$abs" | jq -sRr '.[0] | @sha256 | .[0:8]')"
        ;;
      sha256sum)
        short_sha="$(printf '%s' "$abs" | sha256sum | cut -c1-8)"
        ;;
      *)
        # Last-resort fallback: cksum-derived, not cryptographic.
        # Warns because collisions are easier to construct and the
        # path is no longer hidden behind the hash.
        echo "extension.sh: no python3/jq/sha256sum — using cksum-derived short_sha" >&2
        short_sha="$(printf '%s' "$abs" | cksum | awk '{printf "%08x", $1}' | cut -c1-8)"
        ;;
    esac
  fi
  local tmpdir="${LAZIBLE_TMPDIR:-/tmp}"
  root="$tmpdir/jcode/${repo_name}-${short_sha}"
  case "$kind" in
    root)    echo "$root" ;;
    ws)      echo "$root/ws-${2:?usage: extension.sh scratch-dir ws <label>}" ;;
    wt)
      # Deprecated alias for `ws <label>`. The old worktree-only layout
      # used wt-<label>; the new workspace layer uses ws-<label>. For
      # backward compatibility we keep emitting the ws- path but warn
      # so callers update.
      echo "extension.sh: scratch-dir wt is deprecated; use 'ws'" >&2
      echo "$root/ws-${2:?usage: extension.sh scratch-dir ws <label>}"
      ;;
    scratch) echo "$root/scratch" ;;
    clean)
      # Remove the entire scratch root for the current project.
      # Dry-run by default; pass --yes to actually delete.
      shift
      local confirm=""
      while [[ $# -gt 0 ]]; do
        case "$1" in
          --yes|-y) confirm="yes"; shift ;;
          *) echo "extension.sh: unknown clean flag '$1'" >&2; return 2 ;;
        esac
      done
      if [[ ! -d "$root" ]]; then
        echo "(no $root — nothing to clean)"
        return 0
      fi
      # Enumerate contents so the user sees what would go.
      local size
      size=$(du -sh "$root" 2>/dev/null | awk '{print $1}')
      echo "scratch root: $root"
      echo "size: $size"
      echo "contents:"
      ls -la "$root" | tail -n +2 | awk '{print "  " $NF}' | grep -v '^\.$\|^\.\.$' || true
      if [[ "$confirm" != "yes" ]]; then
        echo ""
        echo "DRY-RUN. Pass --yes to actually delete:"
        echo "  extension.sh scratch-dir clean --yes"
        return 0
      fi
      rm -rf "$root"
      echo "removed: $root"
      ;;
    *)
      echo "usage: extension.sh scratch-dir [root|ws <label>|wt <label>|scratch|clean [--yes]]" >&2
      return 2
      ;;
  esac
}

# ---------- subcommand: workspace ----------
# Workspace lifecycle for spawn coordination. A workspace is the unit
# of file allocation; multiple slots may share one workspace when
# their `files_touched[]` is disjoint (root enforces disjointness on
# `add-slot`). Replaces the old "1 worker : 1 worktree" rule.
#
# Workspace identity = (repo, short-sha, label). Path:
#   $TMPDIR/jcode/<repo-name>-<short-sha>/ws-<label>/
# Manifest at:
#   $TMPDIR/jcode/<repo-name>-<short-sha>/.jcode-workspaces/<label>.json
#
# Backing auto-detected:
#   - worktree (project has .git/) — `git worktree add -b ws-<label>`,
#     all slots commit to the shared ws-<label> branch.
#   - folder (no .git/) — plain directory; `git init` + empty initial
#     commit if git available, otherwise raw fs. Slots write files but
#     do not commit; root copies contents at integration time.
#
# Usage:
#   extension.sh workspace init <label> [--backing=worktree|folder]
#     Create a workspace + manifest. Prints path + branch + manifest.
#     Exit 0 on success, 1 if already exists, 3 on hard fail (git
#     missing for worktree backing, .git missing for folder backing
#     + git init requested, etc.).
#
#   extension.sh workspace add-slot <label> --role=<r> --files=<f1,f2,...>
#                                    [--slot-id=<id>]
#     Register a slot in the manifest. Validates role + disjointness.
#     Auto-assigns slot id if not given: `<role>-<n>` where n is
#     (existing slots with same role) + 1.
#     Exit 0 on success, 1 on overlap, 3 on missing workspace, 2 on usage.
#
#   extension.sh workspace ls
#     List workspaces in current project's scratch dir. Prints label,
#     backing, slot count, status.
#
#   extension.sh workspace show <label>
#     Pretty-print the manifest for <label>.
#
#   extension.sh workspace destroy <label> [--keep-branch]
#     Remove the workspace directory. Default: also delete ws-<label>
#     branch (worktree backing) via `git branch -D`.
#     --keep-branch: leave the branch; root will handle merge.
#     Marks manifest status="destroyed".
#
#   extension.sh workspace clean [--yes]
#     Remove all "completed" or "destroyed" workspaces. Dry-run by default.
cmd_workspace() {
  local action="${1:-}"
  shift || true
  case "$action" in
    init)        cmd_workspace_init "$@" ;;
    add-slot)    cmd_workspace_add_slot "$@" ;;
    ls)          cmd_workspace_ls "$@" ;;
    show)        cmd_workspace_show "$@" ;;
    destroy)     cmd_workspace_destroy "$@" ;;
    clean)       cmd_workspace_clean "$@" ;;
    *)
      echo "usage: extension.sh workspace {init|add-slot|ls|show|destroy|clean} ..." >&2
      return 2
      ;;
  esac
}

# Helper: get the per-project scratch root + manifests dir.
# Defined here so all workspace subcommands share one source of truth.
_workspace_dirs() {
  WS_ROOT="$(cmd_scratch_dir root 2>/dev/null || true)"
  if [[ -z "$WS_ROOT" ]]; then
    echo "extension.sh workspace: cannot derive scratch root (no repo + no fallback)" >&2
    return 3
  fi
  WS_MANIFESTS_DIR="$WS_ROOT/.jcode-workspaces"
}

# Helper: read manifest path for <label>, fail with exit code if missing.
_workspace_manifest_path() {
  local label="$1"
  _workspace_dirs || return $?
  echo "$WS_MANIFESTS_DIR/$label.json"
}

cmd_workspace_init() {
  local label="${1:?usage: workspace init <label> [--backing=worktree|folder]}"
  shift
  local backing=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --backing=*) backing="${1#*=}" ;;
      *) echo "extension.sh workspace init: unknown flag '$1'" >&2; return 2 ;;
    esac
    shift
  done

  # Auto-detect backing if not specified.
  if [[ -z "$backing" ]]; then
    if git rev-parse --git-dir >/dev/null 2>&1; then
      backing="worktree"
    else
      backing="folder"
    fi
  fi
  if [[ "$backing" != "worktree" && "$backing" != "folder" ]]; then
    echo "extension.sh workspace init: --backing must be 'worktree' or 'folder' (got '$backing')" >&2
    return 2
  fi

  _workspace_dirs || return $?
  local ws_path="$WS_ROOT/ws-$label"
  local manifest="$WS_MANIFESTS_DIR/$label.json"

  if [[ -e "$ws_path" || -e "$manifest" ]]; then
    echo "extension.sh workspace init: '$label' already exists at $ws_path or $manifest" >&2
    return 1
  fi

  local branch="ws-$label"
  local base_commit=""
  local repo_root
  repo_root="$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")"
  local short_sha
  short_sha="$(git rev-parse --short=8 HEAD 2>/dev/null || echo "unborn")"

  if [[ "$backing" == "worktree" ]]; then
    if ! command -v git >/dev/null 2>&1; then
      echo "extension.sh workspace init: git required for worktree backing" >&2
      return 3
    fi
    if ! git rev-parse --git-dir >/dev/null 2>&1; then
      echo "extension.sh workspace init: cwd is not a git repo; cannot use worktree backing" >&2
      echo "  pass --backing=folder for non-git projects" >&2
      return 3
    fi
    base_commit="$(git rev-parse HEAD 2>/dev/null || echo "")"
    git worktree add -b "$branch" "$ws_path" || {
      echo "extension.sh workspace init: git worktree add failed" >&2
      return 3
    }
  else
    mkdir -p "$ws_path" || return 3
    if command -v git >/dev/null 2>&1; then
      # Optional: git init inside the folder so workers can `git add` etc.
      # Workers still do NOT commit to a shared workspace branch — root
      # integrates by copying files. branch stays empty for folder backing.
      (cd "$ws_path" && git init -q && git -c user.name=j -c user.email=j@localhost commit --allow-empty -q -m "workspace init" 2>/dev/null) || true
      base_commit=""
    else
      base_commit=""
    fi
    branch=""
  fi

  mkdir -p "$WS_MANIFESTS_DIR"
  # Write manifest via python3 for safe JSON (paths may contain special chars).
  LABEL="$label" REPO="$repo_root" SHORT_SHA="$short_sha" BACKING="$backing" \
  BASE_COMMIT="$base_commit" BRANCH="$branch" WS_PATH="$ws_path" \
  MANIFEST_PATH="$manifest" \
  python3 - <<'PY' || {
import json, os
m = {
  "label": os.environ["LABEL"],
  "repo": os.environ["REPO"],
  "short_sha": os.environ["SHORT_SHA"],
  "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
  "backing": os.environ["BACKING"],
  "base_commit": os.environ["BASE_COMMIT"],
  "branch": os.environ["BRANCH"],
  "path": os.environ["WS_PATH"],
  "status": "active",
  "slots": [],
}
os.makedirs(os.path.dirname(os.environ["MANIFEST_PATH"]), exist_ok=True)
json.dump(m, open(os.environ["MANIFEST_PATH"], "w"), indent=2)
PY
      echo "extension.sh workspace init: failed to write manifest" >&2
      return 3
    }

  echo "workspace initialized: $label"
  echo "  backing:     $backing"
  echo "  path:        $ws_path"
  if [[ -n "$branch" ]]; then
    echo "  branch:      $branch"
    echo "  base_commit: ${base_commit:-(unknown)}"
  fi
  echo "  manifest:    $manifest"
}

cmd_workspace_add_slot() {
  local label="${1:?usage: workspace add-slot <label> --role=<r> --files=<f1,f2,...> [--slot-id=<id>]}"
  shift
  local role="" files_csv="" slot_id=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --role=*) role="${1#*=}" ;;
      --files=*) files_csv="${1#*=}" ;;
      --slot-id=*) slot_id="${1#*=}" ;;
      *) echo "extension.sh workspace add-slot: unknown flag '$1'" >&2; return 2 ;;
    esac
    shift
  done
  if [[ -z "$role" ]]; then
    echo "usage: workspace add-slot <label> --role=<r> --files=<f1,f2,...> [--slot-id=<id>]" >&2
    return 2
  fi
  if [[ ! "$role" =~ ^(reviewer|implementer|investigator|migrator|test-writer|doc-writer)$ ]]; then
    echo "extension.sh workspace add-slot: role '$role' is not one of the 6" >&2
    return 2
  fi
  if [[ -z "$files_csv" ]]; then
    echo "extension.sh workspace add-slot: --files=<f1,f2,...> is required" >&2
    return 2
  fi

  local manifest
  manifest="$(_workspace_manifest_path "$label")" || return $?
  if [[ ! -f "$manifest" ]]; then
    echo "extension.sh workspace add-slot: workspace '$label' not found (no manifest at $manifest)" >&2
    return 3
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    echo "extension.sh workspace add-slot: python3 required for manifest updates" >&2
    return 3
  fi

  LABEL="$label" ROLE="$role" FILES_CSV="$files_csv" SLOT_ID="$slot_id" \
  MANIFEST_PATH="$manifest" \
  python3 - <<'PY' || exit $?
import json, os, sys
m = json.load(open(os.environ["MANIFEST_PATH"]))
files = [f.strip() for f in os.environ["FILES_CSV"].split(",") if f.strip()]
if not files:
    print("extension.sh workspace add-slot: --files is empty", file=sys.stderr)
    sys.exit(2)

# Disjoint check across existing slots.
existing = set()
for s in m.get("slots", []):
    for f in s.get("files_touched", []):
        existing.add(f)
overlap = [f for f in files if f in existing]
if overlap:
    print(f"extension.sh workspace add-slot: files overlap with existing slots: {overlap}", file=sys.stderr)
    sys.exit(1)

# Auto-assign slot id if not given: <role>-<n> where n is the count of
# existing slots with the same role + 1.
slot_id = os.environ.get("SLOT_ID", "")
if not slot_id:
    n = sum(1 for s in m.get("slots", []) if s.get("role") == os.environ["ROLE"]) + 1
    slot_id = f"{os.environ['ROLE']}-{n}"

# Reject duplicate slot id (idempotency hint).
for s in m.get("slots", []):
    if s.get("slot_id") == slot_id:
        print(f"extension.sh workspace add-slot: slot id '{slot_id}' already exists", file=sys.stderr)
        sys.exit(1)

m.setdefault("slots", []).append({
    "slot_id": slot_id,
    "role": os.environ["ROLE"],
    "files_touched": files,
    "status": "active",
    "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
})
json.dump(m, open(os.environ["MANIFEST_PATH"], "w"), indent=2)
print(slot_id)
PY
}

cmd_workspace_ls() {
  _workspace_dirs || return $?
  if [[ ! -d "$WS_MANIFESTS_DIR" ]]; then
    echo "(no workspaces yet)"
    return 0
  fi
  local any=0
  for mf in "$WS_MANIFESTS_DIR"/*.json; do
    [[ -e "$mf" ]] || continue
    any=1
    python3 - "$mf" <<'PY' 2>/dev/null || echo "(parse error: $mf)"
import json, sys
m = json.load(open(sys.argv[1]))
slots = m.get("slots", [])
print(f"{m.get('label','?'):<32} backing={m.get('backing','?'):<8} "
      f"status={m.get('status','?'):<10} slots={len(slots)} "
      f"path={m.get('path','?')}")
PY
  done
  [[ $any -eq 0 ]] && echo "(no workspaces yet)"
}

cmd_workspace_show() {
  local label="${1:?usage: workspace show <label>}"
  local manifest
  manifest="$(_workspace_manifest_path "$label")" || return $?
  if [[ ! -f "$manifest" ]]; then
    echo "extension.sh workspace show: '$label' not found" >&2
    return 3
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    cat "$manifest"
    return 0
  fi
  python3 - "$manifest" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
print(f"label:       {m.get('label')}")
print(f"backing:     {m.get('backing')}")
print(f"status:      {m.get('status')}")
print(f"path:        {m.get('path')}")
print(f"branch:      {m.get('branch') or '(none — folder backing)'}")
print(f"base_commit: {m.get('base_commit') or '(none)'}")
print(f"created_at:  {m.get('created_at')}")
print(f"slots:       {len(m.get('slots', []))}")
for s in m.get("slots", []):
    files = ", ".join(s.get("files_touched", []))
    print(f"  - {s.get('slot_id'):<24} role={s.get('role'):<12} "
          f"status={s.get('status','?'):<10} files=[{files}]")
PY
}

cmd_workspace_destroy() {
  local label="${1:?usage: workspace destroy <label> [--keep-branch]}"
  shift
  local keep_branch=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --keep-branch) keep_branch=1; shift ;;
      *) echo "extension.sh workspace destroy: unknown flag '$1'" >&2; return 2 ;;
    esac
  done

  local manifest
  manifest="$(_workspace_manifest_path "$label")" || return $?
  if [[ ! -f "$manifest" ]]; then
    echo "extension.sh workspace destroy: '$label' not found" >&2
    return 3
  fi

  local ws_path branch backing
  ws_path="$(python3 -c "import json; print(json.load(open('$manifest'))['path'])" 2>/dev/null)"
  branch="$(python3 -c "import json; print(json.load(open('$manifest')).get('branch',''))" 2>/dev/null)"
  backing="$(python3 -c "import json; print(json.load(open('$manifest')).get('backing',''))" 2>/dev/null)"

  if [[ -z "$ws_path" ]]; then
    echo "extension.sh workspace destroy: manifest has no path" >&2
    return 3
  fi

  if [[ -d "$ws_path" ]]; then
    if [[ "$backing" == "worktree" ]]; then
      # Use `git worktree remove` (cleaner than rm -rf) when possible.
      if command -v git >/dev/null 2>&1 && git -C "$ws_path" rev-parse --git-dir >/dev/null 2>&1; then
        git worktree remove --force "$ws_path" 2>/dev/null || rm -rf "$ws_path"
      else
        rm -rf "$ws_path"
      fi
    else
      rm -rf "$ws_path"
    fi
  fi

  # Delete branch unless --keep-branch or branch empty (folder backing).
  if [[ -n "$branch" && "$keep_branch" -eq 0 ]]; then
    if command -v git >/dev/null 2>&1 && git rev-parse --git-dir >/dev/null 2>&1; then
      git branch -D "$branch" 2>/dev/null || true
    fi
  fi

  # Mark manifest destroyed (keep for audit).
  if command -v python3 >/dev/null 2>&1; then
    MANIFEST_PATH="$manifest" python3 - <<'PY' 2>/dev/null || true
import json, os
m = json.load(open(os.environ["MANIFEST_PATH"]))
m["status"] = "destroyed"
m["destroyed_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
json.dump(m, open(os.environ["MANIFEST_PATH"], "w"), indent=2)
PY
  fi

  echo "workspace destroyed: $label"
  if [[ -n "$branch" && "$keep_branch" -eq 0 ]]; then
    echo "  branch removed: $branch"
  elif [[ -n "$branch" ]]; then
    echo "  branch kept: $branch (--keep-branch)"
  fi
}

cmd_workspace_clean() {
  local confirm=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --yes|-y) confirm="yes"; shift ;;
      *) echo "extension.sh workspace clean: unknown flag '$1'" >&2; return 2 ;;
    esac
  done
  _workspace_dirs || return $?
  if [[ ! -d "$WS_MANIFESTS_DIR" ]]; then
    echo "(no workspaces to clean)"
    return 0
  fi
  local to_clean=()
  for mf in "$WS_MANIFESTS_DIR"/*.json; do
    [[ -e "$mf" ]] || continue
    local status
    status="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('status',''))" "$mf" 2>/dev/null)"
    if [[ "$status" == "completed" || "$status" == "destroyed" ]]; then
      to_clean+=("$mf")
    fi
  done
  if [[ ${#to_clean[@]} -eq 0 ]]; then
    echo "(no completed/destroyed workspaces to clean)"
    return 0
  fi
  echo "workspaces to clean:"
  for mf in "${to_clean[@]}"; do
    local label
    label="$(basename "$mf" .json)"
    echo "  - $label"
  done
  if [[ "$confirm" != "yes" ]]; then
    echo ""
    echo "DRY-RUN. Pass --yes to actually delete:"
    echo "  extension.sh workspace clean --yes"
    return 0
  fi
  for mf in "${to_clean[@]}"; do
    rm -f "$mf"
  done
  echo "removed ${#to_clean[@]} manifest(s)"
}

# ---------- subcommand: mcp ----------
# Discovery + validation helper for jcode-native per-project MCP
# config at `./.jcode/mcp.json`. jcode loads this with precedence
# over `~/.jcode/mcp.json` and merges later sources over earlier
# ones (see `crates/jcode-base/src/mcp/protocol.rs::load_project_locals`).
cmd_mcp() {
  local action="${1:-info}"
  shift 2>/dev/null || true
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
      local tool
      if ! tool="$(json_tool)"; then
        echo "  servers: unavailable (no python3/jq on PATH; install one to enable JSON inspection)"
        return 0
      fi
      # Validate JSON syntax.
      if [[ "$tool" == python3 ]]; then
        if ! python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$proj_mcp" 2>/dev/null; then
          echo "  WARNING: invalid JSON syntax"
          return 3
        fi
        local count
        count=$(python3 -c "import json,sys; print(len(json.load(open(sys.argv[1])).get('mcpServers', {})))" "$proj_mcp" 2>/dev/null || echo "?")
      else
        if ! jq -e . "$proj_mcp" >/dev/null 2>&1; then
          echo "  WARNING: invalid JSON syntax"
          return 3
        fi
        local count
        count=$(jq -r '.mcpServers | length' "$proj_mcp" 2>/dev/null || echo "?")
      fi
      echo "  servers: $count"
      ;;
    init)
      # One-time per-project bootstrap: copy the bundle's mcp.json
      # template into <project>/.jcode/mcp.json, substituting the
      # placeholder path with the actual project root. Idempotent —
      # never overwrites an existing file.
      #
      # Usage: extension.sh mcp init [--project=PATH]
      local project="${PWD}"
      while [[ $# -gt 0 ]]; do
        case "$1" in
          --project=*) project="${1#*=}" ;;
          *) echo "extension.sh mcp init: unknown option: $1" >&2; return 2 ;;
        esac
        shift
      done

      if [[ ! -d "$project" ]]; then
        echo "extension.sh mcp init: $project does not exist" >&2
        return 2
      fi
      if [[ ! -d "$project/.git" ]]; then
        echo "extension.sh mcp init: $project is not a git repository" >&2
        return 2
      fi

      local proj_jcode="$project/.jcode"
      local proj_mcp="$proj_jcode/mcp.json"
      local template="$BUNDLE_ROOT/config/mcp.json.example"

      if [[ -e "$proj_mcp" ]]; then
        echo "extension.sh mcp init: $proj_mcp already exists — not overwriting"
        echo "  to re-bootstrap: rm $proj_mcp && extension.sh mcp init"
        return 0
      fi
      if [[ ! -e "$template" ]]; then
        echo "extension.sh mcp init: template not found at $template" >&2
        echo "  bundle may be incomplete; expected: <bundle>/config/mcp.json.example" >&2
        return 3
      fi

      mkdir -p "$proj_jcode"
      # Substitute the /workspace placeholder with the actual project
      # path. The template ships with /workspace so the bundle stays
      # generic; each project substitutes its own root.
      sed "s|/workspace|$project|g" "$template" > "$proj_mcp"

      echo "extension.sh mcp init: installed"
      echo "  template: $template"
      echo "  target:   $proj_mcp"
      echo "  project:  $project (substituted for /workspace)"
      echo ""
      echo "next: review $proj_mcp, then start a jcode session — servers register automatically"
      ;;
    init-global)
      # One-time global bootstrap: copy the bundle's mcp.json template
      # into ~/.jcode/mcp.json — the global location matching every other
      # bundle config (prompt-overlay.md, swarm-prompt.md, config.toml,
      # roles/*.md). Substitutes the /workspace placeholder with the
      # target project root so the filesystem server scope is sane out
      # of the box.
      #
      # Per-project overrides at <project>/.jcode/mcp.json still take
      # precedence when present (jcode merges them over the global at
      # session start), but they are no longer required for the default
      # install — install.sh now creates ~/.jcode/mcp.json for every run.
      #
      # Usage: extension.sh mcp init-global [--project=PATH]
      local project="$BUNDLE_ROOT"
      while [[ $# -gt 0 ]]; do
        case "$1" in
          --project=*) project="${1#*=}" ;;
          *) echo "extension.sh mcp init-global: unknown option: $1" >&2; return 2 ;;
        esac
        shift
      done

      if [[ ! -d "$project" ]]; then
        echo "extension.sh mcp init-global: $project does not exist" >&2
        return 2
      fi

      local jcode_home="${JCODE_HOME:-$HOME/.jcode}"
      local target_mcp="$jcode_home/mcp.json"
      local template="$BUNDLE_ROOT/config/mcp.json.example"

      if [[ -e "$target_mcp" ]]; then
        echo "extension.sh mcp init-global: $target_mcp already exists — not overwriting"
        echo "  to re-bootstrap: rm $target_mcp && extension.sh mcp init-global"
        return 0
      fi
      if [[ ! -e "$template" ]]; then
        echo "extension.sh mcp init-global: template not found at $template" >&2
        echo "  bundle may be incomplete; expected: <bundle>/config/mcp.json.example" >&2
        return 3
      fi

      mkdir -p "$jcode_home"
      sed "s|/workspace|$project|g" "$template" > "$target_mcp"

      echo "extension.sh mcp init-global: installed"
      echo "  template: $template"
      echo "  target:   $target_mcp"
      echo "  project:  $project (substituted for /workspace)"
      echo ""
      echo "next: review $target_mcp, then start a jcode session — servers register automatically"
      ;;
    worktree-hint)
      # Worker-side serena staleness detector. jcode spawns workers into
      # per-project worktrees but inherits the project's MCP config
      # (A4 axis) verbatim — serena's tree-sitter index stays anchored
      # to the MAIN repo's --project path, so post-edit symbol lookups
      # in the worktree return stale results from main. This subcommand
      # gives the worker a deterministic way to detect that staleness
      # and pick a safe verification path (jcode-native read/agentgrep).
      #
      # Usage: extension.sh mcp worktree-hint <wt-path>
      #   <wt-path> must be absolute. The script does NOT require the
      #   path to exist (workers may call this pre-`git worktree add`).
      #
      # Output is line-oriented and machine-greppable; a worker can
      # `grep '^serena:'` to extract the status. Exits 0 on success
      # (informational, not a gate). Exits 3 on hard errors
      # (no MCP config; malformed serena args). Exits 2 on usage errors.
      local wt_path="${1:-}"
      if [[ -z "$wt_path" ]]; then
        echo "usage: extension.sh mcp worktree-hint <wt-path>" >&2
        return 2
      fi
      if [[ "$wt_path" != /* ]]; then
        echo "extension.sh mcp worktree-hint: <wt-path> must be absolute (got '$wt_path')" >&2
        return 2
      fi

      # Find the per-project MCP config. Two paths to try:
      #   1. $PROJ_DIR/mcp.json — works when invoked from main repo
      #      (PROJ_DIR is resolved by walking up from cwd).
      #   2. <wt-path>'s main repo /.jcode/mcp.json — works when invoked
      #      from a worker worktree where PROJ_DIR is empty (the walker
      #      stops at .git and doesn't reach the main repo's .jcode/).
      #      Derived via `git rev-parse --git-common-dir` so this works
      #      whether <wt-path> IS the main repo or a worktree of it.
      # Falls back to global $HOME/.jcode/mcp.json. If neither path
      # resolves, exit 3 — the hint is meaningless without an MCP
      # config to inspect.
      local mcp_json=""
      local serena_main_repo=""
      if [[ -n "$PROJ_DIR" && -e "$PROJ_DIR/mcp.json" ]]; then
        mcp_json="$PROJ_DIR/mcp.json"
        serena_main_repo="$(dirname "$PROJ_DIR")"
      elif command -v git >/dev/null 2>&1; then
        local wt_common
        wt_common="$(git -C "$wt_path" rev-parse --git-common-dir 2>/dev/null || true)"
        if [[ -n "$wt_common" ]]; then
          # git may return a relative path; resolve against wt_path.
          case "$wt_common" in
            /*) ;;
            *) wt_common="$(cd "$wt_path" && cd "$wt_common" 2>/dev/null && pwd)" ;;
          esac
          serena_main_repo="$(dirname "$wt_common")"
          if [[ -e "$serena_main_repo/.jcode/mcp.json" ]]; then
            mcp_json="$serena_main_repo/.jcode/mcp.json"
          fi
        fi
      fi
      if [[ -z "$mcp_json" && -e "$HOME/.jcode/mcp.json" ]]; then
        mcp_json="$HOME/.jcode/mcp.json"
      fi

      if [[ -z "$mcp_json" ]]; then
        echo "extension.sh mcp worktree-hint: no MCP config found (per-project or global)" >&2
        echo "  serena won't be available in this spawn anyway" >&2
        return 3
      fi

      # Parse the MCP config via the existing json_tool helper (python3
      # preferred, jq fallback). Never shell out to python3 -c directly
      # — the helper makes the missing-tool case uniform across scripts.
      local tool
      if ! tool="$(json_tool)"; then
        echo "extension.sh mcp worktree-hint: no python3 or jq on PATH; cannot parse $mcp_json" >&2
        return 3
      fi

      # Extract (a) serena's --project path, (b) filesystem's scoped root,
      # (c) whether serena is in the config at all. Single python3
      # invocation returns all three separated by NULs — cheaper than 3
      # separate JSON parses and keeps the jq branch parallel.
      local serena_project="" fs_root="" has_serena=""
      if [[ "$tool" == python3 ]]; then
        local triple
        triple="$(python3 - "$mcp_json" <<'PY'
import json, sys
try:
    obj = json.load(open(sys.argv[1]))
except Exception:
    print("\n\n0")
    sys.exit(0)
servers = obj.get("mcpServers", {}) if isinstance(obj, dict) else {}

# (a) serena --project
serena_project = ""
serena_args = servers.get("serena", {}).get("args", []) if isinstance(servers.get("serena"), dict) else []
for i, a in enumerate(serena_args):
    if a == "--project" and i + 1 < len(serena_args):
        serena_project = serena_args[i + 1]
        break

# (b) filesystem scoped root (--root if present, else last arg)
fs_root = ""
fs_args = servers.get("filesystem", {}).get("args", []) if isinstance(servers.get("filesystem"), dict) else []
for i, a in enumerate(fs_args):
    if a == "--root" and i + 1 < len(fs_args):
        fs_root = fs_args[i + 1]
        break
if not fs_root and fs_args:
    # Canonical shape: ["-y", "<pkg>", "<root>"]
    fs_root = fs_args[-1]

# (c) serena presence
has_serena = "1" if isinstance(servers.get("serena"), dict) else "0"

print(serena_project)
print(fs_root)
print(has_serena)
PY
)"
        serena_project="$(printf '%s' "$triple" | sed -n '1p')"
        fs_root="$(printf '%s' "$triple" | sed -n '2p')"
        has_serena="$(printf '%s' "$triple" | sed -n '3p')"
      else
        serena_project="$(jq -r '.mcpServers.serena.args // [] | . as $a | (range(0; length) as $i | if $a[$i] == "--project" and ($i+1) < length then $a[$i+1] else empty end) // ""' "$mcp_json" 2>/dev/null || echo "")"
        fs_root="$(jq -r '.mcpServers.filesystem.args // [] | . as $a | (range(0; length) as $i | if $a[$i] == "--root" and ($i+1) < length then $a[$i+1] else empty end) // (if length > 0 then $a[-1] else empty end)' "$mcp_json" 2>/dev/null || echo "")"
        has_serena="$(jq -r '.mcpServers | (has("serena") | tostring)' "$mcp_json" 2>/dev/null || echo "false")"
      fi

      # Determine serena status.
      local serena_status=""
      if [[ "$has_serena" != "1" && "$has_serena" != "true" ]]; then
        # serena missing entirely — still a useful signal (worker may
        # be using filesystem + git only).
        serena_status="not-configured"
      elif [[ -z "$serena_project" ]]; then
        # serena exists but --project not parseable — config shape
        # unexpected. Surface args on stderr so the user can debug.
        echo "extension.sh mcp worktree-hint: serena config shape unexpected; cannot determine --project" >&2
        echo "  mcp.json: $mcp_json" >&2
        if [[ "$tool" == python3 ]]; then
          python3 -c "import json,sys; print('  args:', json.load(open(sys.argv[1]))['mcpServers']['serena'].get('args', []), file=sys.stderr)" "$mcp_json" 2>&1 || true
        else
          echo "  args: $(jq -c '.mcpServers.serena.args' "$mcp_json" 2>/dev/null)" >&2
        fi
        return 3
      elif [[ "$wt_path" == "$serena_project" ]]; then
        # Worker is editing in main repo itself — no staleness.
        serena_status="live (project=$serena_project)"
      else
        # Compare worktree's common git dir to serena project's .git.
        local wt_common=""
        if command -v git >/dev/null 2>&1; then
          wt_common="$(git -C "$wt_path" rev-parse --git-common-dir 2>/dev/null || true)"
          case "$wt_common" in
            /*) ;;
            *) [[ -n "$wt_common" ]] && wt_common="$(cd "$wt_path" && cd "$wt_common" 2>/dev/null && pwd)" ;;
          esac
        fi
        local serena_git="$serena_project/.git"
        if [[ -n "$wt_common" && "$wt_common" == "$serena_git" ]]; then
          serena_status="stale (sees $serena_project only; worktree edits invisible)"
        elif [[ -z "$wt_common" ]]; then
          # Could not resolve worktree's git-common-dir (path doesn't
          # exist yet, or git is unavailable). Don't claim "different
          # repo entirely" — that misleads workers calling this pre-`git
          # worktree add`. Treat as unknown but conservatively stale.
          serena_status="unknown (could not resolve worktree git dir; treat serena as stale until verified)"
        else
          serena_status="stale (configured for $serena_project; this worktree $wt_path is a different repo entirely)"
        fi
      fi

      echo "mcp worktree-hint $wt_path"
      echo ""
      echo "  main_repo:    ${serena_project:-(no serena config)}"
      echo "  worktree:     $wt_path"
      echo "  serena:       $serena_status"
      echo "  filesystem:   scoped to ${fs_root:-(unknown)}"
      echo "  git:          ok (auto-discovers from cwd)"
      echo ""
      echo "  Verification pattern:"
      echo "    - BEFORE editing:  serena OK for code-intelligence exploration"
      echo "    - AFTER editing:   use jcode-native read + agentgrep"
      echo "    - NEVER trust serena for files you have just modified"
      return 0
      ;;
    *)
      echo "usage: extension.sh mcp {info|init [--project=PATH]|worktree-hint <wt-path>}" >&2
      return 2
      ;;
  esac
}

# ---------- subcommand: models ----------
# List models that jcode currently knows about, plus a probe helper for
# auth status. Root uses this BEFORE spawning workers to avoid
# wasting a spawn on an unauth'd model.
#
# Why this exists: P1 in NOTES — multiple recommended models had no
# credentials in this environment. Root should probe auth state before
# drafting a worker spawn prompt.
#
# Usage:
#   extension.sh models list         # list model names from jcode
#   extension.sh models probe <name>  # try a no-op tool call; report auth
cmd_models() {
  local action="${1:-list}"
  shift || true
  case "$action" in
    list)
      if ! command -v jcode >/dev/null 2>&1; then
        echo "extension.sh: jcode not on PATH" >&2
        return 2
      fi
      echo "jcode-known models (auth status NOT shown here — use 'probe'):"
      jcode model list 2>/dev/null | sed 's/^/  /'
      echo ""
      echo "To check auth for a specific model, run:"
      echo "  extension.sh models probe <model-name>"
      echo ""
      echo "To inspect availability status from the swarm layer:"
      echo "  spawn a temp session and call 'swarm list_models'"
      ;;
    probe)
      local model="${1:-}"
      if [[ -z "$model" ]]; then
        echo "usage: extension.sh models probe <model-name>" >&2
        return 2
      fi
      if ! command -v jcode >/dev/null 2>&1; then
        echo "extension.sh: jcode not on PATH" >&2
        return 2
      fi
      local out
      out="$(jcode model list 2>&1 | grep -F "$model" || true)"
      if [[ -z "$out" ]]; then
        echo "extension.sh: model '$model' not in jcode-known list" >&2
        echo "  run 'extension.sh models list' to see available names" >&2
        return 3
      fi
      # Run the probe and capture exit code BEFORE the if (otherwise
      # the if-expression resets $? to 0 on the success branch).
      # `jcode run` returns 0 on success, non-zero on auth failure or
      # any other error. We send a 1-token prompt to keep cost ~0.
      # Temporarily disable `set -e` (set in line 1 of this script)
      # so the jcode failure doesn't kill the script before we can
      # report exit 4.
      set +e
      jcode run --model "$model" "ok" >/dev/null 2>&1
      local rc=$?
      set -e
      if [[ $rc -eq 0 ]]; then
        echo "auth: OK ($model)"
        return 0
      fi
      echo "auth: FAILED ($model, exit $rc)" >&2
      echo "  recommended: try a different model, or re-authenticate" >&2
      return 4
      ;;
    *)
      echo "usage: extension.sh models [list|probe <name>]" >&2
      return 2
      ;;
  esac
}

# ---------- subcommand: doctor ----------
# Single-shot enumeration of all 10 per-project extension axes.
# Tells root what's wired up vs. what's relying on defaults. Designed
# to be run once at session start so root can plan its strategy.
#
# Usage:
#   extension.sh doctor          # default: list per-axis status (A1-A10)
#   extension.sh doctor --env    # environment probe (Linux-only deps)
#
# Output format (fixed column widths for easy grep):
#   AXIS   FILE                                   STATUS
#   ─────────────────────────────────────────────────────────
#   A1 overlay         <repo>/.jcode/prompt-overlay.md   per-project (active)
#   A2 worker policy   <repo>/.jcode/swarm-prompt.md     (not configured)
#   ...
cmd_doctor() {
  local mode="${1:-axes}"
  case "$mode" in
    --env|env)
      doctor_env
      return 0
      ;;
    axes|"")
      : # fall through to default axes table below
      ;;
    *)
      echo "usage: extension.sh doctor [--env]" >&2
      return 2
      ;;
  esac
  printf '%-30s %-50s %s\n' "AXIS" "FILE" "STATUS"
  printf '%-30s %-50s %s\n' "----" "----" "------"
  # A11 scratch dir (derived from cwd; works even without .jcode/)
  printf '%-30s %-50s %s\n' "A11 scratch dir" "$(cmd_scratch_dir root 2>/dev/null || echo '?')" "(derived from cwd)"
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
    if json_tool >/dev/null 2>&1; then
      count=$(python3 -c "import json,sys; print(len(json.load(open(sys.argv[1])).get('mcpServers', {})))" "$PROJ_DIR/mcp.json" 2>/dev/null || echo "?")
    else
      count="? (no python3/jq)"
    fi
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
  # A10 workspace (manifest in scratch dir)
  local wsdir ws_count="0"
  wsdir="$(cmd_scratch_dir root 2>/dev/null)/.jcode-workspaces"
  if [[ -d "$wsdir" ]]; then
    for _f in "$wsdir"/*.json; do
      [[ -e "$_f" ]] || continue
      ws_count=$((ws_count+1))
    done
  fi
  if [[ "$ws_count" -gt 0 ]]; then
    printf '%-30s %-50s %s\n' "A10 workspace" "$wsdir/" "per-project ($ws_count workspaces)"
  else
    printf '%-30s %-50s %s\n' "A10 workspace" "$wsdir/" "(none active)"
  fi
  echo ""
  echo "Run 'extension.sh help' for invocation details on each axis."
}

# doctor_env — environment probe (Linux-only). Reports which tools
# the bundle relies on, separately from the per-axis status table.
# Use this when something fails and you want to know whether the
# environment is the cause (vs. a missing per-project file).
#
# Always exits 0. Problems are reported as "missing" lines, not
# non-zero exit codes, because "json_tool missing" is information
# the caller wants to see, not a failure of `doctor` itself.
doctor_env() {
  printf '%-30s %s\n' "CHECK" "STATUS"
  printf '%-30s %s\n' "-----" "------"
  printf '%-30s %s\n' "bash >= 4" \
    "$(bash --version 2>/dev/null | head -1 | awk '{print $4}')"
  printf '%-30s %s\n' "git" \
    "$(command -v git 2>/dev/null || echo missing)"
  printf '%-30s %s\n' "HOME" "${HOME:-(unset)}"
  printf '%-30s %s\n' "HOME writable" \
    "$([[ -n "${HOME:-}" && -d "$HOME" && -w "$HOME" ]] && echo yes || echo no)"
  printf '%-30s %s\n' "/tmp writable" \
    "$([[ -w /tmp ]] && echo yes || echo no)"
  printf '%-30s %s\n' "LAZIBLE_TMPDIR" \
    "${LAZIBLE_TMPDIR:-(unset, defaults to /tmp)}"
  if command -v curl >/dev/null 2>&1; then
    printf '%-30s %s\n' "curl or wget" "curl: $(command -v curl)"
  elif command -v wget >/dev/null 2>&1; then
    printf '%-30s %s\n' "curl or wget" "wget: $(command -v wget)"
  else
    printf '%-30s %s\n' "curl or wget" "missing"
  fi
  if command -v python3 >/dev/null 2>&1; then
    printf '%-30s %s\n' "JSON tool" "python3: $(command -v python3)"
  elif command -v jq >/dev/null 2>&1; then
    printf '%-30s %s\n' "JSON tool" "jq: $(command -v jq)"
  else
    printf '%-30s %s\n' "JSON tool" "missing"
  fi
  printf '%-30s %s\n' "sha256sum" \
    "$(command -v sha256sum >/dev/null 2>&1 && echo "$(command -v sha256sum)" || echo missing)"
  printf '%-30s %s\n' "jcode" \
    "$(command -v jcode >/dev/null 2>&1 && echo "$(command -v jcode)" || echo missing)"
  printf '%-30s %s\n' "~/.local/bin on PATH" \
    "$([[ ":$PATH:" == *":$HOME/.local/bin:"* ]] && echo yes || echo "no (jcode won't be reachable)")"
  printf '%-30s %s\n' "NO_COLOR env" \
    "${NO_COLOR:-(unset; color OK)}"
  printf '%-30s %s\n' "TERM" \
    "${TERM:-(unset)}"
}

# ---------- dispatch ----------
case "$cmd" in
  artifact)     cmd_artifact "$@" ;;
  role)        cmd_role "$@" ;;
  pre-merge)   cmd_pre_merge "$@" ;;
  verify)      cmd_verify "$@" ;;
  notify)      cmd_notify "$@" ;;
  pre-spawn)   cmd_pre_spawn "$@" ;;
  skills)      cmd_skills "$@" ;;
  workspace)   cmd_workspace "$@" ;;
  mcp)         cmd_mcp "$@" ;;
  models)      cmd_models "$@" ;;
  preflight)   cmd_preflight "$@" ;;
  scratch-dir) cmd_scratch_dir "$@" ;;
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
  workspace init <label> [--backing=worktree|folder]
                                       Allocate a workspace (path + manifest)
  workspace add-slot <label> --role=<r> --files=<f1,f2,...>
                                       Register a slot in the workspace (disjoint enforced)
  workspace ls|show|destroy|clean      Manage workspace lifecycle
  mcp info                             Show per-project MCP config status (jcode-native)
  mcp worktree-hint <wt-path>          Worker-side serena staleness detector (use at spawn start)
  models [list|probe <name>]           List jcode-known models; probe auth for one
  preflight [--workspace P] [--project P]  Pre-spawn env gate (auth, install, paths)
  scratch-dir [root|ws <label>|wt <label>|scratch|clean [--yes]] Print canonical per-project scratch path under \$TMPDIR
  artifact validate <path>                Validate a typed-artifact JSON file (8-field contract)
  doctor [--env]                       Per-axis status table (default) or environment probe (--env)

Per-project hooks live at <repo>/.jcode/{pre-merge,verify,notify,pre-spawn}.sh
Per-project role overrides live at <repo>/.jcode/roles/<name>.md
Per-project skills live at <repo>/.jcode/skills/<name>/SKILL.md (jcode-native)
Per-project MCP servers live at <repo>/.jcode/mcp.json (jcode-native)
Workspace manifests live at \$TMPDIR/jcode/<repo>-<sha>/.jcode-workspaces/<label>.json
See docs/EXTENSIONS.md for the full 10×10 boundary-behavior walkthrough.
EOF
    ;;
  *)
    echo "extension.sh: unknown subcommand '$cmd' (try 'help')" >&2
    exit 2
    ;;
esac