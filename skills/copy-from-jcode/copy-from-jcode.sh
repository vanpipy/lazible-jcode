#!/usr/bin/env bash
# copy-from-jcode.sh — snapshot ~/.jcode into lazible-jcode (or vice versa).
#
# Direction:
#   (default)  PULL  ~/.jcode/skills/  →  $REPO_ROOT/skills/
#   --install  INSTALL  $REPO_ROOT/skills/  →  ~/.jcode/skills/  (symlinks)
#
# Swarm config (swarm-prompt.md + roles/*.md) is bundled by default — it
# contains no secrets and is project-agnostic. Pass --exclude-swarm to skip.
#
# Config files (config.toml, mcp.json) are NOT copied by default — they
# contain per-machine secrets. Pass --include-config / --include-mcp to
# override, but the script will print a warning.
#
# Usage:
#   copy-from-jcode.sh                       # pull skills + swarm
#   copy-from-jcode.sh --install            # install skills + swarm (symlinks)
#   copy-from-jcode.sh --include-config     # also copy config.toml
#   copy-from-jcode.sh --include-mcp        # also copy mcp.json
#   copy-from-jcode.sh --exclude-swarm      # skip swarm config
#   copy-from-jcode.sh --force              # overwrite existing files
#   copy-from-jcode.sh --dry-run            # plan only
#   copy-from-jcode.sh --help
set -euo pipefail

JCODE_HOME="${JCODE_HOME:-$HOME/.jcode}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

DIRECTION="pull"          # pull | install
INCLUDE_CONFIG=0
INCLUDE_MCP=0
INCLUDE_SWARM=1           # default ON — swarm config is project-agnostic markdown
FORCE=0
DRY_RUN=0
SKIP_SECRETS_CHECK=0

print_help() {
  cat <<EOF
Usage: $0 [options]

Sync between ~/.jcode/ and the lazible-jcode repo.

Direction (choose one):
  (default)              PULL: ~/.jcode/skills/ → \$REPO_ROOT/skills/
  --install              INSTALL: \$REPO_ROOT/skills/ → ~/.jcode/skills/ (symlinks)

Content filters (pull direction only):
  --include-config       Also copy ~/.jcode/config.toml  (warns: may contain secrets)
  --include-mcp          Also copy ~/.jcode/mcp.json     (warns: may contain secrets)
  --exclude-swarm        Skip swarm config (default is to include it)
  --include-swarm        Force include swarm config (default is already on)

Behavior:
  --force                Overwrite existing files / replace non-symlinks
  --dry-run              Plan only
  --allow-secrets        Skip the secrets warning for --include-* flags
  -h, --help             Show this help and exit.

Environment:
  JCODE_HOME             Override ~/.jcode path

By default, swarm config (swarm-prompt.md + roles/*.md) is included in both
directions. It is project-agnostic markdown, never contains secrets.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install)        DIRECTION="install"; shift ;;
    --include-config) INCLUDE_CONFIG=1; shift ;;
    --include-mcp)    INCLUDE_MCP=1; shift ;;
    --include-swarm)  INCLUDE_SWARM=1; shift ;;
    --exclude-swarm)  INCLUDE_SWARM=0; shift ;;
    --force)          FORCE=1; shift ;;
    --dry-run)        DRY_RUN=1; shift ;;
    --allow-secrets)  SKIP_SECRETS_CHECK=1; shift ;;
    -h|--help)        print_help; exit 0 ;;
    *) echo "error: unknown flag: $1" >&2; print_help >&2; exit 1 ;;
  esac
done

info() { printf '\033[1;34m%s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*" >&2; }
err()  { printf '\033[1;31merror: %s\033[0m\n' "$*" >&2; exit 1; }

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[dry-run] %s\n' "$*"
  else
    "$@"
  fi
}

# ── secrets guard ──────────────────────────────────────────────────────────────
warn_about_secrets() {
  if [[ "$SKIP_SECRETS_CHECK" == "1" ]]; then return 0; fi
  cat >&2 <<EOF
warning: copying live config files into a git repo can leak secrets.
  jcode stores provider keys, OAuth tokens, and pending-login state under
  ~/.jcode/. Review the diff carefully and consider adding sensitive fields
  to .gitignore or scrubbing them with 'sops' / 'git-crypt' before commit.

  Use --allow-secrets to suppress this warning.
EOF
}

# ── PULL direction ─────────────────────────────────────────────────────────────
do_pull() {
  if [[ ! -d "$JCODE_HOME" ]]; then
    err "JCODE_HOME not found: $JCODE_HOME — nothing to pull"
  fi

  local src_skills="$JCODE_HOME/skills"
  local dst_skills="$REPO_ROOT/skills"
  mkdir -p "$dst_skills"

  local pulled=0
  local skipped=0

  if [[ ! -d "$src_skills" ]]; then
    info "(no skills installed locally — nothing to pull)"
  else
    for skill_dir in "$src_skills"/*; do
      [[ -d "$skill_dir" ]] || continue
      local name skill_md
      name="$(basename "$skill_dir")"
      skill_md="$skill_dir/SKILL.md"
      [[ -f "$skill_md" ]] || { warn "skip $name — no SKILL.md"; skipped=$((skipped+1)); continue; }

      local dst_dir="$dst_skills/$name"
      if [[ -e "$dst_dir/SKILL.md" ]] && [[ "$FORCE" != "1" ]]; then
        warn "skip $name — already exists in repo (use --force to overwrite)"
        skipped=$((skipped+1)); continue
      fi

      mkdir -p "$dst_dir"
      run cp "$skill_md" "$dst_dir/SKILL.md"
      info "pulled $name"
      pulled=$((pulled+1))
    done
  fi

  # ── swarm pull ────────────────────────────────────────────────────────────
  if [[ "$INCLUDE_SWARM" == "1" ]]; then
    local src_swarm_prompt="$JCODE_HOME/swarm-prompt.md"
    local dst_swarm_dir="$REPO_ROOT/swarm"
    mkdir -p "$dst_swarm_dir/roles"

    if [[ -f "$src_swarm_prompt" ]]; then
      if [[ -e "$dst_swarm_dir/swarm-prompt.md" ]] && [[ "$FORCE" != "1" ]]; then
        warn "skip swarm-prompt.md — already in repo (use --force to overwrite)"
      else
        run cp "$src_swarm_prompt" "$dst_swarm_dir/swarm-prompt.md"
        info "pulled swarm-prompt.md"
      fi
    fi

    local src_roles="$JCODE_HOME/roles"
    if [[ -d "$src_roles" ]]; then
      for role_file in "$src_roles"/*.md; do
        [[ -f "$role_file" ]] || continue
        local role_name
        role_name="$(basename "$role_file")"
        local dst_role="$dst_swarm_dir/roles/$role_name"
        if [[ -e "$dst_role" ]] && [[ "$FORCE" != "1" ]]; then
          warn "skip role $role_name — already in repo (use --force to overwrite)"
          continue
        fi
        run cp "$role_file" "$dst_role"
        info "pulled role $role_name"
      done
    fi
  fi

  if [[ "$INCLUDE_CONFIG" == "1" ]]; then
    warn_about_secrets
    if [[ -f "$JCODE_HOME/config.toml" ]]; then
      if [[ -e "$REPO_ROOT/config/config.toml" ]] && [[ "$FORCE" != "1" ]]; then
        warn "skip config.toml — already in repo (use --force to overwrite)"
      else
        run cp "$JCODE_HOME/config.toml" "$REPO_ROOT/config/config.toml"
        info "pulled config.toml"
      fi
    fi
  fi

  if [[ "$INCLUDE_MCP" == "1" ]]; then
    warn_about_secrets
    if [[ -f "$JCODE_HOME/mcp.json" ]]; then
      if [[ -e "$REPO_ROOT/config/mcp.json" ]] && [[ "$FORCE" != "1" ]]; then
        warn "skip mcp.json — already in repo (use --force to overwrite)"
      else
        run cp "$JCODE_HOME/mcp.json" "$REPO_ROOT/config/mcp.json"
        info "pulled mcp.json"
      fi
    fi
  fi

  info "pulled=$pulled skipped=$skipped"
  if [[ "$DRY_RUN" != "1" ]] && [[ "$pulled" -gt 0 ]]; then
    info "run 'git status' in $REPO_ROOT to see the new SKILL.md files."
  fi
}

# ── INSTALL direction ─────────────────────────────────────────────────────────
do_install() {
  if [[ ! -d "$REPO_ROOT/skills" ]]; then
    err "repo skills dir not found: $REPO_ROOT/skills"
  fi

  mkdir -p "$JCODE_HOME/skills"
  local installed=0
  local skipped=0

  for skill_dir in "$REPO_ROOT/skills"/*; do
    [[ -d "$skill_dir" ]] || continue
    [[ -f "$skill_dir/SKILL.md" ]] || continue
    local name
    name="$(basename "$skill_dir")"
    local target="$JCODE_HOME/skills/$name"

    if [[ -L "$target" ]]; then
      local link_target
      link_target="$(readlink "$target")"
      if [[ "$link_target" == "$skill_dir" ]]; then
        info "already linked $name → $skill_dir"
        skipped=$((skipped+1)); continue
      fi
      if [[ "$FORCE" != "1" ]]; then
        warn "skip $name — symlink exists, points elsewhere: $link_target (use --force)"
        skipped=$((skipped+1)); continue
      fi
      run rm -f "$target"
    elif [[ -e "$target" ]]; then
      if [[ "$FORCE" != "1" ]]; then
        warn "skip $name — $target exists and is not a symlink (use --force to replace)"
        skipped=$((skipped+1)); continue
      fi
      run rm -rf "$target"
    fi

    run ln -s "$skill_dir" "$target"
    info "linked $name → $skill_dir"
    installed=$((installed+1))
  done

  # ── swarm install ─────────────────────────────────────────────────────────
  if [[ "$INCLUDE_SWARM" == "1" ]] && [[ -d "$REPO_ROOT/swarm" ]]; then
    install_swarm_file() {
      local src="$1" dst="$2" label="$3"
      [[ -f "$src" ]] || return 0
      if [[ -L "$dst" ]]; then
        local link_target
        link_target="$(readlink "$dst")"
        if [[ "$link_target" == "$src" ]]; then
          info "already linked $label → $src"
          skipped=$((skipped+1)); return 0
        fi
        if [[ "$FORCE" != "1" ]]; then
          warn "skip $label — symlink points elsewhere: $link_target"
          skipped=$((skipped+1)); return 0
        fi
        run rm -f "$dst"
      elif [[ -e "$dst" ]]; then
        if [[ "$FORCE" != "1" ]]; then
          warn "skip $label — $dst exists and is not a symlink"
          skipped=$((skipped+1)); return 0
        fi
        run rm -f "$dst"
      fi
      run ln -s "$src" "$dst"
      info "linked $label → $src"
      installed=$((installed+1))
    }

    install_swarm_dir() {
      local src="$1" dst="$2" label="$3"
      [[ -d "$src" ]] || return 0
      if [[ -L "$dst" ]]; then
        local link_target
        link_target="$(readlink "$dst")"
        if [[ "$link_target" == "$src" ]]; then
          info "already linked $label → $src"
          skipped=$((skipped+1)); return 0
        fi
        if [[ "$FORCE" != "1" ]]; then
          warn "skip $label — symlink points elsewhere: $link_target"
          skipped=$((skipped+1)); return 0
        fi
        run rm -f "$dst"
      elif [[ -e "$dst" ]]; then
        if [[ "$FORCE" != "1" ]]; then
          warn "skip $label — $dst exists and is not a symlink"
          skipped=$((skipped+1)); return 0
        fi
        run rm -rf "$dst"
      fi
      run ln -s "$src" "$dst"
      info "linked $label → $src"
      installed=$((installed+1))
    }

    install_swarm_file "$REPO_ROOT/swarm/swarm-prompt.md" \
                       "$JCODE_HOME/swarm-prompt.md" \
                       "swarm-prompt.md"
    install_swarm_dir  "$REPO_ROOT/swarm/roles" \
                       "$JCODE_HOME/roles" \
                       "roles/"
  fi

  info "installed=$installed skipped=$skipped"
}

case "$DIRECTION" in
  pull)    do_pull    ;;
  install) do_install ;;
esac