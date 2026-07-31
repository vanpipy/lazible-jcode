#!/usr/bin/env bash
# scripts/install.sh — repo-level entry point.
#
# Thin wrapper that:
#   1. Validates the lazible-jcode checkout (looks for skills/, config/, etc.)
#   2. Invokes the standalone installer that ships with the install-jcode skill
#
# Usage:
#   ./scripts/install.sh                       # install latest
#   ./scripts/install.sh --version v0.64.2     # pin a version
#   ./scripts/install.sh --dry-run             # plan only
#   ./scripts/install.sh --from-source         # cargo build --release
#
# For the full flag set, see ./skills/install-jcode/jcode-install.sh --help.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
installer="$repo_root/skills/install-jcode/jcode-install.sh"

if [[ ! -x "$installer" ]]; then
  echo "error: installer not found or not executable: $installer" >&2
  echo "       run: chmod +x '$installer'" >&2
  exit 1
fi

# Sanity-check the lazible-jcode layout so we don't run from a wrong cwd.
for required in AGENTS.md README.md config skills; do
  if [[ ! -e "$repo_root/$required" ]]; then
    echo "error: lazible-jcode checkout looks incomplete: missing $repo_root/$required" >&2
    exit 1
  fi
done

exec "$installer" "$@"