#!/usr/bin/env bash
# configure_path.sh — idempotently add a directory to PATH in bash/zsh/fish rc files.
# Sourced by jcode-install.sh and scripts/install.sh. Not meant to be run directly.
#
# Public entry point:
#   jcode_configure_path <install_dir>
#
# Behavior mirrors upstream jcode:
#   - For POSIX shells, append `export PATH="<dir>:$PATH"` once, only if missing.
#   - For fish, append a `set -gx PATH <dir> $PATH` block once.
#   - We only create ~/.profile (never ~/.bash_profile) so we don't override the
#     user's existing login-shell file lookup order.
#   - Existing custom rc files (.zshrc, .zprofile, .bash_profile) are patched
#     in place when present, but never created from scratch.
set -euo pipefail

jcode_configure_path() {
  local install_dir="$1"
  [[ -n "$install_dir" ]] || { echo "configure_path: install_dir is required" >&2; return 1; }

  local path_line="export PATH=\"$install_dir:\$PATH\""
  local added_to=""
  local rc create

  _have() { command -v "$1" >/dev/null 2>&1; }

  # POSIX rc: create=Yes for files we own, No for files we only patch if present.
  ensure_posix_rc() {
    rc="$1"
    create="$2"
    if [[ ! -f "$rc" ]]; then
      [[ "$create" == "yes" ]] || return 0
      mkdir -p "$(dirname "$rc")"
    fi
    if ! grep -qF "$install_dir" "$rc" 2>/dev/null; then
      printf '\n# Added by jcode installer\n%s\n' "$path_line" >> "$rc"
      added_to="$added_to $rc"
    fi
  }

  # fish has its own syntax and does not read POSIX rc files.
  ensure_fish_rc() {
    create="$1"
    rc="${XDG_CONFIG_HOME:-$HOME/.config}/fish/config.fish"
    if [[ ! -f "$rc" ]]; then
      [[ "$create" == "yes" ]] || return 0
      mkdir -p "$(dirname "$rc")"
    fi
    if ! grep -qF "$install_dir" "$rc" 2>/dev/null; then
      {
        printf '\n# Added by jcode installer\n'
        printf 'if not contains "%s" $PATH\n' "$install_dir"
        printf '    set -gx PATH "%s" $PATH\n' "$install_dir"
        printf 'end\n'
      } >> "$rc"
      added_to="$added_to $rc"
    fi
  }

  # zsh: ~/.zshenv is read for every zsh invocation (login, interactive, scripts).
  if _have zsh || [[ "$(uname -s)" == "Darwin" ]] || [[ -f "$HOME/.zshenv" ]] || [[ -f "$HOME/.zshrc" ]]; then
    ensure_posix_rc "$HOME/.zshenv" yes
  fi

  # bash: ~/.bashrc for interactive shells, ~/.profile for login shells.
  if _have bash || [[ -f "$HOME/.bashrc" ]] || [[ -f "$HOME/.bash_profile" ]]; then
    ensure_posix_rc "$HOME/.bashrc" yes
  fi
  ensure_posix_rc "$HOME/.profile" yes

  # fish: only set up when fish is installed or already configured.
  if _have fish || [[ -f "${XDG_CONFIG_HOME:-$HOME/.config}/fish/config.fish" ]]; then
    ensure_fish_rc yes
  fi

  # Patch other common startup files when they already exist (no creation).
  for rc in "$HOME/.zshrc" "$HOME/.zprofile" "$HOME/.bash_profile"; do
    ensure_posix_rc "$rc" no
  done

  if [[ -n "$added_to" ]]; then
    printf '\033[1;34mAdded %s to PATH in:%s\033[0m\n' "$install_dir" "$added_to"
  fi
}