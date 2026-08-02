# Installation

This repo ships three install paths. Pick whichever fits your situation.

## 1. Quick path: from this repo

```bash
git clone https://github.com/vanpipy/lazible-jcode.git
cd lazible-jcode
./scripts/install.sh
```

The wrapper is **linear and unconditional** — it runs 4 steps every time and
overwrites the destination without prompting:

1. Install jcode binary. If `jcode-patches/*.patch` exists, build a canary
   from those patches (via `scripts/build-jcode-canary.sh --replace-main`);
   otherwise call the standalone upstream installer. Either way, the result
   replaces `~/.local/bin/jcode` (the previous binary is backed up as
   `jcode.bak.<ts>`).
2. Symlink `swarm/prompt-overlay.md`, `swarm/swarm-prompt.md`, and
   `swarm/roles/` into their canonical locations under `~/.jcode/`.
3. Symlink each `skills/<name>/SKILL.md` directory into `~/.jcode/skills/<name>`.
4. Symlink `AGENTS.md` to `~/.jcode/AGENTS.md`.

Existing files at any destination are backed up to `<dst>.bak.<timestamp>`
before being replaced.

If you want the standalone installer without the wrapper (no overlay,
no selfdev, no symlinks):

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
./scripts/install.sh
```

If `jcode-patches/*.patch` exists, the canary build path takes over and
`scripts/build-jcode-canary.sh` runs `cargo build --release` against the
patches. If no patch exists, the standalone upstream installer falls back to
downloading a prebuilt tarball. Pin the version with
`./scripts/install.sh --canary-version <v>` (only honored when canary build
runs).

Requires `git` and `cargo` for the canary path.

## Flags

`scripts/install.sh` is intentionally minimal — only one flag:

| Flag | Effect |
|---|---|
| `--canary-version <v>` | Pin the jcode tag the canary build runs against. Only used when `jcode-patches/*.patch` exists. Default: latest |
| `-h`, `--help` | Show usage |

There is **no** `--skip-binary`, `--refresh`, `--install-skills`, `--dry-run`,
`--no-overlay`, or `--enable-selfdev`. Every run does all 4 steps and
overwrites every destination (with `.bak.<ts>` backup first).

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

## Self-development (advanced)

If the overlay isn't strong enough for your taste (because the upstream
`system_prompt.md` still anchors "maximally proactive"), enable selfdev by
placing patches under `jcode-patches/`. When any `*.patch` file exists there,
the wrapper's step 1 automatically builds a canary from those patches and
replaces `~/.local/bin/jcode` (backed up as `jcode.bak.<ts>`). No flag needed.
See `docs/SELFDEV.md` for the full flow.

```bash
# Re-run the wrapper to rebuild the canary against the current patches
./scripts/install.sh --canary-version v0.65.0

# Or run the canary build script standalone (side-by-side, doesn't touch main)
./scripts/build-jcode-canary.sh --jcode-version v0.65.0
```

After the canary replaces `~/.local/bin/jcode`, your regular `jcode` invocation
runs the swarm-tuned build. The original is at
`~/.local/bin/jcode.bak.<timestamp>` for rollback.

To **stop** selfdev and fall back to upstream-only installs, simply remove the
files under `jcode-patches/`. The next `install.sh` will use the upstream
installer instead.

## Re-install / overwrite

The wrapper is **always idempotent and unconditional**: running
`./scripts/install.sh` always runs all 4 steps and always overwrites every
destination. Any pre-existing file or symlink at the destination is backed up
to `<dst>.bak.<timestamp>` first. There is no `--refresh` flag — rerunning
**is** the refresh.

| Destination state | What `install.sh` does |
|---|---|
| Does not exist | Creates the symlink |
| Already a symlink to **this** repo | Removes, backs up the link, re-links (so any drift in the link is corrected) |
| A symlink to **somewhere else** | Removes, backs up as `<dst>.bak.<ts>`, replaces with repo symlink |
| A **regular file or directory** | Moves to `<dst>.bak.<ts>`, replaces with repo symlink |

To pin the canary version:

```bash
./scripts/install.sh --canary-version v0.65.0
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
| `curl: command not found` | Install `curl` |
| `cargo: command not found` | Install Rust via `rustup` (required only when canary build runs) |
| `xattr: com.apple.quarantine` | Re-run after granting the binary once via Finder |
| Quarantine still blocks on macOS | `xattr -d com.apple.quarantine "$(command -v jcode)"` |
| Wrong arch on Windows ARM64 | Check `PROCESSOR_ARCHITECTURE`, not `uname -m` |
| `pkg install glibc patchelf` (Termux) | Required for the prebuilt Linux binary to load |
| Launcher installed but `jcode: not found` | `source ~/.bashrc` or open a new shell |
| Old file / dir at a destination is replaced during rerun | It's backed up as `<dst>.bak.<ts>` automatically; `ls -la ~/.jcode/` to inspect |
| `prompt-overlay.md` not picked up by jcode | Confirm `~/.jcode/prompt-overlay.md` exists and is a symlink to `swarm/prompt-overlay.md` in this repo. `ls -la ~/.jcode/prompt-overlay.md` should show the target. jcode reads it at session start — restart jcode after editing |
| Want to inspect what install.sh would do | `bash scripts/install.sh --help` and read the printed 4-step plan; the script itself does not support `--dry-run` — all runs write |