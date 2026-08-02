# Installation

This repo ships three install paths. Pick whichever fits your situation.

## 1. Quick path: from this repo

```bash
git clone https://github.com/vanpipy/lazible-jcode.git
cd lazible-jcode
./scripts/install.sh
```

This is a wrapper that does **two things**:

1. Validates the checkout and calls the standalone binary installer:
   ```
   scripts/install.sh
   └─ skills/install-jcode/jcode-install.sh
   ```
2. Symlinks this repo's `swarm/prompt-overlay.md` → `~/.jcode/prompt-overlay.md`
   so jcode picks up the enhanced main-agent prompt at session start. It also
   symlinks `swarm/swarm-prompt.md` and `swarm/roles/` to their canonical
   locations.

If you want the standalone installer without the wrapper (no overlay):

```bash
./skills/install-jcode/jcode-install.sh
# or, via the wrapper, with overlay disabled:
./scripts/install.sh --no-overlay
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

`scripts/install.sh` is the wrapper. It consumes its own flags first, then
forwards everything else to `skills/install-jcode/jcode-install.sh`.

### Wrapper-specific (overlay + symlinks)

| Flag | Effect |
|---|---|
| (no flag) | Default: install jcode binary **and** symlink overlay + swarm config |
| `--no-overlay` | Skip the overlay/swarm symlinks; binary install only |
| `--overlay <path>` | Use `<path>` as the overlay source instead of `swarm/prompt-overlay.md` |
| `--refresh` | Force overwrite mismatched symlinks; existing non-symlink files at the destination are backed up to `<dst>.bak` first |
| `--install-skills` | Also symlink each `skills/<name>` into `~/.jcode/skills/`. Default: leave `~/.jcode/skills/` untouched (users may have personal skills) |
| `--skip-binary` | Skip the jcode binary installer (overlay-only refresh on a machine that already has jcode) |
| `--dry-run` | Print the plan; write nothing |

### Forwarded to the binary installer

| Flag | Effect |
|---|---|
| `--version <v>` | Pin a release tag (e.g. `v0.64.2`) |
| `--install-dir <dir>` | Override launcher install dir (default `~/.local/bin`) |
| `--from-source` | `cargo build --release` instead of downloading |
| `--local-artifact <path>` | Use a local tarball/zip instead of downloading |
| `--skip-path` | Do not edit shell rc files |
| `--skip-server-reload` | Do not reload a running jcode server |
| `--no-telemetry` | Skip install-funnel telemetry |

Run `./scripts/install.sh --help` for the full wrapper usage, and
`./skills/install-jcode/jcode-install.sh --help` for the full installer list.

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
./scripts/uninstall.sh            # remove binaries + lazible-jcode-owned symlinks, keep config
./scripts/uninstall.sh --purge    # also remove config, auth, logs, sessions, memory
./scripts/uninstall.sh --keep-overlay  # keep overlay/swarm/roles symlinks, only remove binaries
./scripts/uninstall.sh --dry-run  # plan only
```

The uninstaller only removes symlinks whose target is inside this repo's
checkout (`$REPO_ROOT/*`). Symlinks you created manually that point elsewhere
are preserved. By default it removes:

- The jcode binary (`~/.local/bin/jcode`) and any prior installs
- Symlinks at `~/.jcode/prompt-overlay.md`, `~/.jcode/swarm-prompt.md`,
  `~/.jcode/roles/` that point into this repo

It does **not** touch (without `--purge`):

- `~/.jcode/config.toml`
- `~/.jcode/mcp.json`
- `~/.jcode/auth*`
- `~/.jcode/{logs,sessions,memory,cache,builds}`

It never touches shell rc files. If you want to remove the PATH line the
installer added, edit the rc file by hand.

## Re-install / overwrite

The wrapper is **idempotent**: running `./scripts/install.sh` on a machine
that already has jcode is safe. Default behavior:

| Destination state | What `install.sh` does |
|---|---|
| Does not exist | Creates the symlink |
| Already a symlink to **this** repo | Skips (no change) |
| A symlink to **somewhere else** | Skips with a warning (run with `--refresh` to replace) |
| A **regular file or directory** | Skips with a warning (run with `--refresh` to back up as `<dst>.bak` then replace) |

To force a clean re-link of every overlay + swarm + skill symlink:

```bash
./scripts/install.sh --skip-binary --refresh --install-skills
```

To also force-reinstall the binary:

```bash
./scripts/install.sh --refresh --install-skills
```

To preview without writing:

```bash
./scripts/install.sh --skip-binary --refresh --install-skills --dry-run
```

To use your own overlay file instead of the one in this repo:

```bash
./scripts/install.sh --overlay ~/my-overrides/prompt-overlay.md
```

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
| `skip <name> — exists and is not a symlink (use --refresh to backup + replace)` | A file or directory is already at `~/.jcode/<name>`. Re-run with `--refresh` to back it up as `<name>.bak` then symlink |
| `prompt-overlay.md` not picked up by jcode | Confirm `~/.jcode/prompt-overlay.md` exists and is a symlink to `swarm/prompt-overlay.md` in this repo. `ls -la ~/.jcode/prompt-overlay.md` should show the target. jcode reads it at session start — restart jcode after editing |
| Want to test the overlay without touching your `~/.jcode/` | `./scripts/install.sh --dry-run` prints the full plan without writing anything |