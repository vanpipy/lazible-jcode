#!/usr/bin/env bash
# worktree-swarm.sh — allocate / teardown / cleanup worker worktrees.
#
# One worktree per spawned worker under:
#   $TMPDIR/swarm-$USER/<repo>-<short-sha>/wt-<label>/
#
# Heavy in-repo deps (node_modules, ios/Pods) symlinked from main worktree.
# Active workers tracked in .jcode/worktree-manifest.json with 8-hour TTL.
#
# Usage:
#   worktree-swarm.sh alloc <name> [--type T] [--base <sha>] [--no-link]
#       Create worktree + branch + symlinks. Output: <worktree_path>\t<branch>
#   worktree-swarm.sh teardown <label>
#       Remove worktree + branch + manifest entry.
#   worktree-swarm.sh cleanup [--force]
#       Remove entries older than TTL_HOURS (default 8h).
#       Skips branches already merged into main unless --force.
#   worktree-swarm.sh list
#       Print manifest entries (label, path, branch, age).
#   worktree-swarm.sh status <label>
#       Print one tab-separated line for the manifest entry matching <label>:
#       <worktree_path>\t<branch>\t<base_commit>\t<created_at_epoch>\t<age_hours>
#       Exit non-zero with stderr `error: status: no manifest entry for '<label>'`
#       if no entry matches; same shape if the manifest itself is missing.
#   worktree-swarm.sh help
#
# Requires: git, python3.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
REPO_NAME="$(basename "$REPO_ROOT")"
USER_NAME="${USER:-$(id -un)}"
TMPDIR_BASE="${TMPDIR:-/tmp}"
MANIFEST="$REPO_ROOT/.jcode/worktree-manifest.json"
TTL_HOURS=8
VALID_TYPES=(feat fix chore docs refactor test)

export MANIFEST

die() { echo "error: $*" >&2; exit 1; }

usage() {
  sed -n '2,/^# Requirements/!d; /^# Requirements/q; p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

sanitize() {
  echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9-]+/-/g; s/^-+|-+$//g; s/-+/-/g'
}

short_sha() {
  local sha
  sha=$(git -C "$REPO_ROOT" rev-parse --short=7 "${1:-HEAD}" 2>/dev/null) || die "git rev-parse failed"
  echo "$sha"
}

parse_symlink_includes() {
  local config="$REPO_ROOT/.jcode/worktree.toml"
  if [[ ! -f "$config" ]]; then
    echo "node_modules ios/Pods"
    return
  fi
  python3 -c "
import re, os
content = open(os.environ['CONFIG']).read()
m = re.search(r'\[symlinks\](.*?)(?=\n\[|\Z)', content, re.DOTALL)
if not m:
    print('node_modules ios/Pods')
else:
    includes = re.findall(r'\"([^\"]+)\"', m.group(1))
    print(' '.join(includes) if includes else 'node_modules ios/Pods')
" CONFIG="$config"
}

# ── alloc ──────────────────────────────────────────────────────────────────

do_alloc() {
  local name_raw="$1"; shift
  local type="feat" base_sha="" no_link=0

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --type)    type="$2"; shift 2 ;;
      --base)    base_sha="$2"; shift 2 ;;
      --no-link) no_link=1; shift ;;
      *) die "alloc: unknown flag: $1" ;;
    esac
  done

  local ok=0
  for t in "${VALID_TYPES[@]}"; do [[ "$type" == "$t" ]] && ok=1; done
  [[ $ok -eq 1 ]] || die "alloc: invalid type '$type' (use: ${VALID_TYPES[*]})"

  [[ -z "$base_sha" ]] && base_sha=$(short_sha HEAD)
  [[ ${#base_sha} -gt 7 ]] && base_sha="${base_sha:0:7}"

  local name label wt_path branch
  name=$(sanitize "$name_raw")
  [[ -n "$name" ]] || die "alloc: empty name after sanitize (input: '$name_raw')"

  label="${type}-${name}-${base_sha}"
  wt_path="$TMPDIR_BASE/swarm-$USER_NAME/$REPO_NAME/$base_sha/wt-${label}"
  branch="$type/${name}_${base_sha}"

  [[ -d "$wt_path" ]] && die "alloc: worktree already exists: $wt_path"

  mkdir -p "$(dirname "$wt_path")"
  git -C "$REPO_ROOT" worktree add -b "$branch" "$wt_path" "$base_sha" \
    || die "alloc: git worktree add failed (branch '$branch' may already exist)"

  if [[ $no_link -eq 0 ]]; then
    for dep in $(parse_symlink_includes); do
      if [[ -e "$REPO_ROOT/$dep" ]]; then
        ln -sfn "$REPO_ROOT/$dep" "$wt_path/$dep"
        echo "  linked $dep" >&2
      fi
    done
  fi

  mkdir -p "$(dirname "$MANIFEST")"
  local now_epoch; now_epoch=$(date +%s)
  WORKTREE_PATH="$wt_path" BRANCH="$branch" LABEL="$label" TYPE="$type" \
  NAME="$name" BASE_COMMIT="$base_sha" NOW="$now_epoch" \
  python3 - <<'PY'
import json, os
mf = os.environ["MANIFEST"]
try:
    with open(mf) as f: d = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    d = {"version": 1, "workers": []}
d["workers"].append({
    "label": os.environ["LABEL"],
    "type": os.environ["TYPE"],
    "name": os.environ["NAME"],
    "worktree_path": os.environ["WORKTREE_PATH"],
    "branch": os.environ["BRANCH"],
    "base_commit": os.environ["BASE_COMMIT"],
    "created_at": int(os.environ["NOW"]),
    "status": "active",
})
with open(mf, "w") as f:
    json.dump(d, f, indent=2)
PY

  printf "%s\t%s\n" "$wt_path" "$branch"
}

# ── teardown ───────────────────────────────────────────────────────────────

do_teardown() {
  local label="$1"
  [[ -z "$label" ]] && die "teardown: label required"

  [[ ! -f "$MANIFEST" ]] && die "teardown: no manifest at $MANIFEST"

  local entry wt_path branch
  entry=$(LABEL="$label" python3 - <<'PY'
import json, os
with open(os.environ["MANIFEST"]) as f: d = json.load(f)
for w in d.get("workers", []):
    if w.get("label") == os.environ["LABEL"]:
        print(json.dumps({"path": w["worktree_path"], "branch": w["branch"]}))
        break
PY
)

  [[ -z "$entry" ]] && die "teardown: no manifest entry for '$label'"

  wt_path=$(echo "$entry" | python3 -c "import sys,json; print(json.load(sys.stdin)['path'])")
  branch=$(echo "$entry" | python3 -c "import sys,json; print(json.load(sys.stdin)['branch'])")

  if [[ -d "$wt_path" ]]; then
    git -C "$REPO_ROOT" worktree remove --force "$wt_path" 2>/dev/null || rm -rf "$wt_path"
  fi
  git -C "$REPO_ROOT" branch -D "$branch" 2>/dev/null || true

  LABEL="$label" python3 - <<'PY'
import json, os
with open(os.environ["MANIFEST"]) as f: d = json.load(f)
d["workers"] = [w for w in d.get("workers", []) if w.get("label") != os.environ["LABEL"]]
with open(os.environ["MANIFEST"], "w") as f:
    json.dump(d, f, indent=2)
PY

  echo "torn down $label ($wt_path, $branch)"
}

# ── cleanup ────────────────────────────────────────────────────────────────

do_cleanup() {
  local force=0
  [[ "${1:-}" == "--force" ]] && force=1

  [[ ! -f "$MANIFEST" ]] && { echo "no manifest"; return 0; }

  local now_epoch ttl_secs
  now_epoch=$(date +%s)
  ttl_secs=$((TTL_HOURS * 3600))

  local removed=0

  while IFS= read -r entry; do
    [[ -z "$entry" ]] && continue
    local label path branch age_h
    label=$(echo "$entry" | python3 -c "import sys,json; print(json.load(sys.stdin)['label'])")
    path=$(echo "$entry" | python3 -c "import sys,json; print(json.load(sys.stdin)['path'])")
    branch=$(echo "$entry" | python3 -c "import sys,json; print(json.load(sys.stdin)['branch'])")
    age_h=$(echo "$entry" | python3 -c "import sys,json; print(round(json.load(sys.stdin)['age_h'], 1))")

    if [[ $force -eq 0 ]]; then
      if git -C "$REPO_ROOT" branch --list --merged main | grep -q "^[[:space:]]*${branch}\$"; then
        echo "  skip $label — already merged into main"
        continue
      fi
    fi

    if [[ -d "$path" ]]; then
      git -C "$REPO_ROOT" worktree remove --force "$path" 2>/dev/null || rm -rf "$path"
    fi
    git -C "$REPO_ROOT" branch -D "$branch" 2>/dev/null || true

    LABEL="$label" python3 - <<'PY'
import json, os
with open(os.environ["MANIFEST"]) as f: d = json.load(f)
d["workers"] = [w for w in d.get("workers", []) if w.get("label") != os.environ["LABEL"]]
with open(os.environ["MANIFEST"], "w") as f:
    json.dump(d, f, indent=2)
PY

    echo "  removed $label ($branch, age=${age_h}h)"
    removed=$((removed + 1))
  done < <(python3 -c "
import json, time
with open('$MANIFEST') as f: d = json.load(f)
now = $now_epoch
ttl = $ttl_secs
for w in d.get('workers', []):
    age = now - w.get('created_at', 0)
    if age > ttl:
        print(json.dumps({'label': w['label'], 'path': w['worktree_path'], 'branch': w['branch'], 'age_h': age/3600}))
")

  echo "removed=$removed"
}

# ── list ───────────────────────────────────────────────────────────────────

do_list() {
  [[ ! -f "$MANIFEST" ]] && { echo "(no manifest)"; return 0; }
  python3 - <<'PY'
import json, time, os
mf = os.environ["MANIFEST"]
try:
    with open(mf) as f: d = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    d = {"version": 1, "workers": []}
now = int(time.time())
for w in d.get("workers", []):
    age_h = (now - w.get("created_at", 0)) / 3600
    print(f"{w['label']:40} {w['worktree_path']}  {w['branch']:30} age={age_h:.1f}h")
PY
}

# ── status ─────────────────────────────────────────────────────────────────

do_status() {
  local label="${1:-}"
  [[ -z "$label" ]] && die "status: label required"

  [[ ! -f "$MANIFEST" ]] && die "status: no manifest at $MANIFEST"

  local line
  line=$(LABEL="$label" python3 - <<'PY'
import json, os, time
mf = os.environ["MANIFEST"]
with open(mf) as f:
    d = json.load(f)
target = os.environ["LABEL"]
now = int(time.time())
for w in d.get("workers", []):
    if w.get("label") == target:
        age_h = (now - w.get("created_at", 0)) / 3600
        print("\t".join([
            w["worktree_path"],
            w["branch"],
            w.get("base_commit", ""),
            str(w.get("created_at", 0)),
            f"{age_h:.4f}",
        ]))
        break
PY
)

  [[ -z "$line" ]] && die "status: no manifest entry for '$label'"

  printf '%s\n' "$line"
}

# ── dispatch ───────────────────────────────────────────────────────────────

cmd="${1:-help}"
shift 2>/dev/null || true

case "$cmd" in
  alloc)     do_alloc "$@" ;;
  teardown)  do_teardown "$@" ;;
  cleanup)   do_cleanup "$@" ;;
  list)      do_list ;;
  status)    do_status "$@" ;;
  help|-h|--help) usage ;;
  *) die "unknown subcommand: $cmd (try: help)" ;;
esac