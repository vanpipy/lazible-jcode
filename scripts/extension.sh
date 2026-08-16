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
#   5. Worktree path writable: if --worktree <path> given, check writable
#   6. Project root: if --project <path> given, check exists + .git (optional)
#
# Exit codes:
#   0 = all checks pass
#   1 = a soft warning (degraded but not blocking)
#   2 = usage error
#   3 = hard failure (cannot spawn)
cmd_preflight() {
  # Note: dispatcher already shifted off the subcommand name, so $@ here
  # contains the user's flags (e.g. "--worktree /tmp/jcode/foo"). Don't
  # shift again — that would drop --worktree.
  local worktree=""
  local project=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --worktree) worktree="${2:-}"; shift 2 ;;
      --project)  project="${2:-}"; shift 2 ;;
      --help|-h)
        echo "usage: extension.sh preflight [--worktree <path>] [--project <path>]" >&2
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

  # 4. Worktree path writable (if given)
  if [[ -n "$worktree" ]]; then
    if [[ -e "$worktree" ]]; then
      if [[ -d "$worktree" && -w "$worktree" ]]; then
        check "worktree path writable" "ok" "$worktree"
      else
        check "worktree path writable" "fail" "$worktree exists but not writable dir"
      fi
    else
      # Try parent dir
      local parent
      parent="$(dirname "$worktree")"
      if [[ -d "$parent" && -w "$parent" ]]; then
        check "worktree path writable" "ok" "$worktree (parent $parent is writable, will be created)"
      else
        check "worktree path writable" "fail" "$parent not writable"
      fi
    fi
  else
    # No worktree given; print the canonical layout
    local root
    root="$(cmd_scratch_dir root 2>/dev/null || echo '?')"
    check "worktree path" "ok" "(not specified; default would be $root/wt-<label>)"
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

  # 6. Model auth probe (cheap default candidate)
  #    We pick MiniMax-M3 as the default since it's the only one with
  #    confirmed credentials in this environment. The user can override
  #    by passing a different model and running `models probe <name>`
  #    separately.
  if command -v jcode >/dev/null 2>&1; then
    set +e
    jcode run --model MiniMax-M3 "ok" >/dev/null 2>&1
    local rc=$?
    set -e
    if [[ $rc -eq 0 ]]; then
      check "model auth (MiniMax-M3 default)" "ok" "MiniMax-M3 responds"
    else
      check "model auth (MiniMax-M3 default)" "warn" "MiniMax-M3 unreachable (exit $rc); run 'extension.sh models probe <name>' to find a working model"
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
#   ├── wt-<label>/    # git worktrees (one per worker)
#   └── scratch/       # misc scratch files
#
# Used by root when constructing the spawn prompt's worktree_path arg.
# The convention is documented in swarm/prompt-overlay.md §4.1 and
# keeps worktrees OFF the user's home filesystem and OUT of the repo
# itself — both important on macOS where home may be slow and /tmp
# may be RAM-backed.
#
# Args:
#   (none)             print the scratch root only
#   wt <label>         print $root/wt-<label>
#   scratch            print $root/scratch
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
    short_sha="$(printf '%s' "$abs" | python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.read().encode()).hexdigest()[:8])')"
  fi
  local tmpdir="${LAZIBLE_TMPDIR:-/tmp}"
  root="$tmpdir/jcode/${repo_name}-${short_sha}"
  case "$kind" in
    root)    echo "$root" ;;
    wt)      echo "$root/wt-${2:?usage: extension.sh scratch-dir wt <label>}" ;;
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
      echo "usage: extension.sh scratch-dir [root|wt <label>|scratch|clean [--yes]]" >&2
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
# Output format (fixed column widths for easy grep):
#   AXIS   FILE                                   STATUS
#   ─────────────────────────────────────────────────────────
#   A1 overlay         <repo>/.jcode/prompt-overlay.md   per-project (active)
#   A2 worker policy   <repo>/.jcode/swarm-prompt.md     (not configured)
#   ...
cmd_doctor() {
  printf '%-30s %-50s %s\n' "AXIS" "FILE" "STATUS"
  printf '%-30s %-50s %s\n' "----" "----" "------"
  # A10 scratch dir (derived from cwd; works even without .jcode/)
  printf '%-30s %-50s %s\n' "A10 scratch dir" "$(cmd_scratch_dir root 2>/dev/null || echo '?')" "(derived from cwd)"
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
  # A10 scratch dir (derived path, not a file)
  printf '%-30s %-50s %s\n' "A10 scratch dir" "$(cmd_scratch_dir root 2>/dev/null || echo '?')" "(derived from cwd)"
  echo ""
  echo "Run 'extension.sh help' for invocation details on each axis."
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
  mcp info                             Show per-project MCP config status (jcode-native)
  models [list|probe <name>]           List jcode-known models; probe auth for one
  preflight [--worktree P] [--project P]  Pre-spawn env gate (auth, install, paths)
  scratch-dir [root|wt <label>|scratch|clean [--yes]] Print canonical per-project scratch path under \$TMPDIR
  artifact validate <path>                Validate a typed-artifact JSON file (8-field contract)
  doctor                               Single-shot enumeration of all 10 extension axes

Per-project hooks live at <repo>/.jcode/{pre-merge,verify,notify,pre-spawn}.sh
Per-project role overrides live at <repo>/.jcode/roles/<name>.md
Per-project skills live at <repo>/.jcode/skills/<name>/SKILL.md (jcode-native)
Per-project MCP servers live at <repo>/.jcode/mcp.json (jcode-native)
See docs/EXTENSIONS.md for the full 10×10 boundary-behavior walkthrough.
EOF
    ;;
  *)
    echo "extension.sh: unknown subcommand '$cmd' (try 'help')" >&2
    exit 2
    ;;
esac