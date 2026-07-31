---
name: install-jcode
description: Use when the user wants to install, set up, bootstrap, or upgrade jcode on a machine. Detects the platform, package manager, and shell environment, then picks the best install path (Homebrew / install script / source build). Also verifies that `jcode` is on `PATH` and runs a smoke test.
allowed-tools: bash, read, write, edit, agentgrep, todo
---

# install-jcode

Install or upgrade jcode on the current machine.

This skill models the upstream jcode install flow (`jcode.sh/install` +
`scripts/install_release.sh`) but stays inside the `lazible-jcode` repo so it
works offline and without `curl | bash` against jcode.sh.

## When to trigger

User phrases that should activate this skill:

- "install jcode", "set up jcode", "bootstrap jcode"
- "upgrade jcode", "update jcode"
- "I need jcode on this machine"
- "jcode is not on PATH", "jcode not found"

## When **not** to trigger

- The user only wants to configure providers/auth — that is the `provider`
  workflow, not install. Hand off to `jcode provider add` or
  `jcode login --provider <name>` after install completes.
- The user wants to run jcode once interactively to chat — that is
  `jcode run "<prompt>"`, no install needed if a binary is already on PATH.

## Core principle

> Pick the install path that best matches the host, verify every step, and
> never silently fall back from "download a binary" to "compile from source"
> unless the user explicitly opts in.

## Workflow

### 1. Detect platform

```bash
OS="$(uname -s)"
ARCH="$(uname -m)"
SHELL_NAME="$(basename "${SHELL:-sh}")"
```

Map:

| OS      | ARCH    | Artifact                  | Install dir                            |
|---------|---------|---------------------------|----------------------------------------|
| Linux   | x86_64  | `jcode-linux-x86_64`      | `$HOME/.local/bin`                     |
| Linux   | aarch64 | `jcode-linux-aarch64`     | `$HOME/.local/bin`                     |
| Darwin  | arm64   | `jcode-macos-aarch64`     | `$HOME/.local/bin`                     |
| Darwin  | x86_64  | `jcode-macos-x86_64`      | `$HOME/.local/bin`                     |
| Termux  | *       | `jcode-linux-<arch>` + glibc/patchelf | `$HOME/.local/bin`         |
| Windows | x86_64  | `jcode-windows-x86_64`    | `$LOCALAPPDATA\\jcode\\bin`            |
| Windows | aarch64 | `jcode-windows-aarch64`   | `$LOCALAPPDATA\\jcode\\bin`            |

### 2. Choose install path

Prefer, in order:

1. **Homebrew** if `brew --version` succeeds and the OS is macOS or Linux
   (`brew tap 1jehuang/jcode && brew install jcode`).
2. **jcode.sh/install** (`curl -fsSL https://jcode.sh/install | bash`) — the
   fastest, fully verified path.
3. **lazible-jcode's own installer** (`./scripts/install.sh` if running from
   this repo) — same behavior, but driven from this repo so it works offline.
4. **From source** only if the user explicitly says "build from source" or no
   prebuilt artifact exists for the platform.

Never silently fall back from (2) to (4). If no binary exists, ask the user
before kicking off a multi-minute `cargo build --release`.

### 3. Run the installer

In priority order:

```bash
# (preferred) lazible-jcode's bundled installer
./scripts/install.sh
# or the standalone copy that lives next to this SKILL.md:
./skills/install-jcode/jcode-install.sh

# (alternative) upstream installer via HTTPS
curl -fsSL https://jcode.sh/install | bash

# (alternative) from source
git clone https://github.com/1jehuang/jcode.git
cd jcode
cargo build --release
scripts/install_release.sh
```

Always pass `--dry-run` first if the script supports it, so the user sees the
plan before disk writes happen.

### 4. Verify

After the install finishes:

```bash
command -v jcode              # must print a path
jcode --version               # must print a version
jcode run "say hello"         # smoke test
```

If `jcode run` fails, capture the first 50 lines of the error and check:

- **PATH issue** — `$HOME/.local/bin` must be on PATH. The installer's
  `configure_path.sh` adds it to `~/.bashrc`, `~/.zshenv`, `~/.profile`,
  `~/.config/fish/config.fish`. Open a new shell or `source` the relevant rc.
- **Missing dynamic linker** (Termux) — `pkg install glibc patchelf`.
- **Wrong arch** — `uname -m` may report x86_64 on Windows ARM64; check
  `PROCESSOR_ARCHITECTURE`.
- **Quarantine** (macOS) — `xattr -d com.apple.quarantine "$(command -v jcode)"`.

### 5. Offer next steps

After the smoke test, prompt the user:

- "Set up a provider?" → walk through `jcode login --provider <name>` for the
  provider they prefer (Claude, OpenAI, Gemini, Copilot, Alibaba, etc.).
- "Enable browser automation?" → `jcode browser status` then
  `jcode browser setup`.
- "Install skills from lazible-jcode?" → run
  `./skills/copy-from-jcode/copy-from-jcode.sh --install` to symlink the skills
  in this repo into `~/.jcode/skills/`.

## Guardrails

- Never `rm -rf ~/.jcode`. The installer writes to `~/.jcode/builds/` only.
  Removing the user's existing config silently loses auth, sessions, and memory.
- Never write the launcher's PATH line twice. The installer is idempotent;
  let it own that file. Do not append manually.
- Never run `cargo build --release` without explicit user consent when a
  prebuilt binary exists for the platform.
- Never `xattr -d com.apple.quarantine` on a binary that came from outside
  `~/.jcode/builds/` — only on the freshly-installed launcher.

## Companion script

This skill ships a self-contained installer at
`skills/install-jcode/jcode-install.sh`. Run it directly:

```bash
./skills/install-jcode/jcode-install.sh           # install
./skills/install-jcode/jcode-install.sh --dry-run # plan only
./skills/install-jcode/jcode-install.sh --help    # full flag list
```

The script mirrors `jcode.sh/install` but downloads the artifact from the GitHub
release redirect (or builds from source when no prebuilt is available) and
writes to `~/.jcode/builds/` + `~/.local/bin/` using the same symlink layout as
the upstream installer.