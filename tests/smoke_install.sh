#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
: "${HOME:?HOME must be set to a sandbox directory}"
work="$HOME/.install-smoke-fixture"
rm -rf "$work"
mkdir -p "$work"
checkout="$work/repo"
mkdir -p "$checkout"
cp -a "$repo_root/AGENTS.md" "$repo_root/README.md" "$repo_root/config" \
  "$repo_root/skills" "$repo_root/swarm" "$repo_root/scripts" "$checkout/"
# Force the no-patches branch and make step 1 deterministic/offline.
rm -rf "$checkout/jcode-patches"
mkdir "$checkout/jcode-patches"
cat > "$checkout/skills/install-jcode/jcode-install.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p "${JCODE_INSTALL_DIR:-$HOME/.local/bin}"
printf '#!/usr/bin/env bash\nexit 0\n' > "${JCODE_INSTALL_DIR:-$HOME/.local/bin}/jcode"
chmod +x "${JCODE_INSTALL_DIR:-$HOME/.local/bin}/jcode"
STUB
chmod +x "$checkout/skills/install-jcode/jcode-install.sh"

JCODE_HOME="$HOME/.jcode" JCODE_INSTALL_DIR="$HOME/.local/bin" \
  bash "$checkout/scripts/install.sh"

expected=(prompt-overlay.md swarm-prompt.md ARCHITECTURE.md roles)
for entry in "${expected[@]}"; do
  test -L "$HOME/.jcode/$entry"
  target=$(readlink -e "$HOME/.jcode/$entry")
  test -n "$target"
done
# The four required names must all be present. Installer-created backups are allowed.
test -n "$(find "$HOME/.jcode/skills" -mindepth 1 -maxdepth 1 -print -quit)"
test -L "$HOME/.jcode/AGENTS.md"
test -n "$(readlink -e "$HOME/.jcode/AGENTS.md")"
printf 'PASS: install smoke structure\n'
