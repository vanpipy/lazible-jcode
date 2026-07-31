# Installation

This repo ships three install paths. Pick whichever fits your situation.

## 1. Quick path: from this repo

```bash
git clone https://github.com/vanpipy/lazible-jcode.git
cd lazible-jcode
./scripts/install.sh
```

This is a wrapper that validates the checkout and calls the standalone installer
that lives next to the `/install-jcode` skill:

```
scripts/install.sh
└─ skills/install-jcode/jcode-install.sh
```

If you want the standalone installer without the wrapper:

```bash
./skills/install-jcode/jcode-install.sh
```

## 2. Use the upstream installer

If you do not need the lazible-jcode wrapper, the upstream installer still
works:

```bash
curl -fsSL https://jcode.sh/install | bash
```

This is the upstream path. lazible-jcode's installer is functionally
compatible — it just stays inside the repo so it works offline and is
reviewable.

## 3. From source

```bash
./scripts/install.sh --from-source
```

Requires `git` and `cargo`. Builds `1jehuang/jcode` at the latest tag (or a
pinned version with `--version`).

## Flags

| Flag | Effect |
|---|---|
| `--dry-run` | Print the plan without writing anything |
| `--version <v>` | Pin a release tag (e.g. `v0.64.2`) |
| `--install-dir <dir>` | Override launcher install dir (default `~/.local/bin`) |
| `--from-source` | `cargo build --release` instead of downloading |
| `--local-artifact <path>` | Use a local tarball/zip instead of downloading |
| `--skip-path` | Do not edit shell rc files |
| `--skip-server-reload` | Do not reload a running jcode server |
| `--no-telemetry` | Skip install-funnel telemetry |

Run `./skills/install-jcode/jcode-install.sh --help` for the full list.

## Verification

After install:

```bash
command -v jcode          # must print a path
jcode --version
jcode run "say hello"
```

If `jcode` is not on PATH, open a new shell — `configure_path.sh` adds the
launcher dir to `~/.bashrc` / `~/.zshenv` / `~/.profile` /
`~/.config/fish/config.fish` idempotently.

## Uninstall

```bash
./scripts/uninstall.sh            # remove binaries, keep config
./scripts/uninstall.sh --purge    # remove everything
./scripts/uninstall.sh --dry-run  # plan only
```

The uninstaller never touches shell rc files. If you want to remove the
PATH line the installer added, edit the rc file by hand.

## Sync installed skills

After editing a skill in this repo, install it locally with:

```bash
./skills/copy-from-jcode/copy-from-jcode.sh --install
```

This symlinks `$REPO_ROOT/skills/<name>` → `~/.jcode/skills/<name>` so jcode
picks it up without copying.

To snapshot the live `~/.jcode/skills/` back into the repo:

```bash
./skills/copy-from-jcode/copy-from-jcode.sh
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `curl: command not found` | Install `curl` or use `--from-source` |
| `cargo: command not found` | Install Rust via `rustup` |
| `xattr: com.apple.quarantine` | Re-run after granting the binary once via Finder |
| Quarantine still blocks on macOS | `xattr -d com.apple.quarantine "$(command -v jcode)"` |
| Wrong arch on Windows ARM64 | Check `PROCESSOR_ARCHITECTURE`, not `uname -m` |
| `pkg install glibc patchelf` (Termux) | Required for the prebuilt Linux binary to load |
| Launcher installed but `jcode: not found` | `source ~/.bashrc` or open a new shell |