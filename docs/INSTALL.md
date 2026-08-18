# Installation

This repo is a **prompt store + installer** for jcode customizations.
The actual content is the markdown under `swarm/`, `AGENTS.md`, and
`scripts/install.sh` — installing means symlinking them into
`~/.jcode/` so jcode loads them on session start.

## Quick path: from this repo

```bash
git clone https://github.com/vanpipy/lazible-jcode.git
cd lazible-jcode
./scripts/install.sh
```

The wrapper is **linear and unconditional** — it runs 3 steps every
time and overwrites the destination without prompting:

1. Install jcode binary via the standalone upstream installer if no
   `jcode` is on `PATH` yet. Existing binaries are left in place.
   Also installs the `swarm-sweep` helper into `~/.local/bin/` (see
   "Stale swarm workspaces" below).
2. Symlink `swarm/prompt-overlay.md`, `swarm/swarm-prompt.md`,
   and `swarm/roles/*.md` into their canonical locations under `~/.jcode/`.
   `swarm/ARCHITECTURE.md` and `docs/ARCHITECTURE.md` are reference docs
   and are not installed.
3. Auto-init `~/.jcode/mcp.json` from `config/mcp.json.example` so jcode
   has MCP servers (filesystem / git / serena) on first session start.
   Idempotent — skips if the file already exists. See "Step 3" below for
   the per-project override semantics.

Existing files at any destination are backed up to `<dst>.bak.<timestamp>`
before being replaced.

The standalone upstream installer (`jcode-install.sh`) is no longer
bundled here — use the wrapper, or call the upstream installer
directly (see below).

## Upstream-only path

If you do not need the lazible-jcode wrapper, the upstream installer
still works:

```bash
curl -fsSL https://jcode.sh/install | bash
```

This is the upstream path. lazible-jcode's installer is functionally
compatible — it just stays inside the repo so it works offline and is
reviewable.

## Flags

`scripts/install.sh` accepts two flags:

| Flag | Effect |
|---|---|
| `-h`, `--help` | Show usage |
| `--project=PATH` | Default target for the MCP config substitution. The bundle always installs `~/.jcode/mcp.json` (with `PATH` substituted for `/workspace` in the filesystem server scope). When `PATH` is not the bundle's own repo, install additionally inits a per-project override at `<PATH>/.jcode/mcp.json` so multi-project hosts can scope filesystem/git/serena to the right repo. |

The installer runs **3 steps** every time. Steps 1-2 overwrite their
destinations (`.bak.<ts>` backup first); step 3 is idempotent — skips with a
message if either target already exists, never overwrites.

## Step 3: auto-init `~/.jcode/mcp.json`

`.jcode/mcp.json` is gitignored, so a fresh install never ships one.
Without this step, jcode's session start would have no MCP servers and
silently lose filesystem/git/serena tooling. Step 3 mirrors the
"all-config-in-`~/.jcode/`" install pattern (same as `prompt-overlay.md`,
`swarm-prompt.md`, `config.toml`, `roles/*.md`):

1. **3a (always)** — calls `scripts/extension.sh mcp init-global
   --project=$TARGET_PROJECT`. Copies `config/mcp.json.example` to
   `~/.jcode/mcp.json`, substituting the `/workspace` placeholder with
   the target project root. Idempotent — skips if `~/.jcode/mcp.json`
   already exists.

2. **3b (only when `--project=PATH` was given AND `PATH` != bundle repo)**
   — calls `scripts/extension.sh mcp init --project=PATH`. Adds a
   per-project override at `<PATH>/.jcode/mcp.json` so jcode's
   session-start merge picks up project-specific MCP scopes. Skipped
   on default install (where `PATH` is the bundle's own repo) — the
   global config already covers it.

So after `install.sh`, the bundle's MCP config is set up alongside every
other bundle config. For using the bundle in another project:

```bash
# Default: install bundle + init ~/.jcode/mcp.json (scope = bundle's own repo)
./scripts/install.sh

# Install bundle AND init per-project override for your app
./scripts/install.sh --project=/path/to/your/app
```

## Verification

After install:

```bash
command -v jcode          # must print a path
jcode --version
jcode run "say hello"
```

If `jcode` is not on PATH, open a new shell — the upstream installer
adds the launcher dir to `~/.bashrc` / `~/.zshenv` / `~/.profile` /
`~/.config/fish/config.fish` idempotently.

For the bundle's pre-flight environment check (bash ≥ 4, git, writable
HOME and /tmp, curl or wget, optional python3 / jq), see
[ENVIRONMENTS.md](ENVIRONMENTS.md). You can also run it at any time:

```bash
scripts/extension.sh doctor --env
```

## Uninstall

```bash
./scripts/uninstall.sh                  # remove symlinks, keep config
./scripts/uninstall.sh --purge --yes    # also remove config + auth + logs
./scripts/uninstall.sh --keep-binary    # keep jcode binary, remove symlinks
./scripts/uninstall.sh --dry-run        # plan only
```

The uninstaller only removes symlinks whose target is inside this
repo's checkout (`$REPO_ROOT/*`). Symlinks you created manually that
point elsewhere are preserved. By default it removes:

- Symlinks at `~/.jcode/prompt-overlay.md`, `~/.jcode/swarm-prompt.md`,
  and `~/.jcode/roles/` that point into this repo.
- The jcode binary (`~/.local/bin/jcode`) and prior backup installs
  (`jcode.bak.*`), unless `--keep-binary` is passed.
- The `swarm-sweep` helper at `~/.local/bin/swarm-sweep`, unless
  `--keep-binary` is passed (it shares the same keep flag because
  the two binaries are installed side by side).

It does **not** touch (without `--purge`):

- `~/.jcode/mcp.json`
- `~/.jcode/auth*`
- `~/.jcode/{logs,sessions,memory,cache,builds}`

It never touches shell rc files. If you want to remove the PATH line
the upstream installer added, edit the rc file by hand.

## Stale swarm workspaces

When a spawned worker disappears mid-task (M3 silent failure) or
finishes without cleanup, the workspace directory + branch it
created sit in the repo / `$TMPDIR` indefinitely. Two cleanup paths:

```bash
# Per-workspace: remove one workspace directory + branch
scripts/extension.sh workspace destroy <label>

# Bulk: sweep all manifests marked destroyed/completed
scripts/extension.sh workspace clean --yes

# Legacy: bulk for the old worktree convention
swarm-sweep --yes        # actually remove them
swarm-sweep --max-age=3  # threshold in days (default: 7)
```

The `swarm-sweep` script only touches paths matching the swarm
convention `$TMPDIR/swarm-<user>/<repo>-<short-sha>/wt-<label>/`
(legacy worktree shape) or the new workspace shape
`$TMPDIR/jcode/<repo>-<short-sha>/ws-<label>/`. The main worktree
and any manual feature worktrees are NEVER touched. The
`workspace destroy` / `clean` commands are the primary cleanup
path for new projects; `swarm-sweep` remains for legacy residue.

This is the workspace-level cleanup layer — distinct from the
session-level reaper inside the orchestrator (which closes idle
spawned workers automatically). See `AGENTS.md` "Cleanup: stale
workspaces" for the full description of both layers.

`swarm-sweep` is installed into `~/.local/bin/swarm-sweep` by
`scripts/install.sh` (step 1, alongside jcode). Removing it happens
via `scripts/uninstall.sh --yes`.

## Re-install / overwrite

The wrapper is **always idempotent and unconditional**: running
`./scripts/install.sh` always runs all 3 steps and always overwrites
every destination. Any pre-existing file or symlink at the destination
is backed up to `<dst>.bak.<timestamp>` first (except the fast path in
the table below). There is no `--refresh` flag — rerunning **is** the
refresh.

| Destination state | What `install.sh` does |
|---|---|
| Does not exist | Creates the symlink |
| Already a symlink to **this** repo | **Fast path**: leaves the link unchanged (no backup, no recreate) |
| A symlink to **somewhere else** | Removes, backs up as `<dst>.bak.<ts>`, replaces with repo symlink |
| A **regular file or directory** | Moves to `<dst>.bak.<ts>`, replaces with repo symlink |

## Troubleshooting

| Symptom | Fix |
|---|---|
| `curl: command not found` | Install `curl` |
| `xattr: com.apple.quarantine` | Re-run after granting the binary once via Finder |
| Quarantine still blocks on macOS | `xattr -d com.apple.quarantine "$(command -v jcode)"` |
| Wrong arch on Windows ARM64 | Check `PROCESSOR_ARCHITECTURE`, not `uname -m` |
| `pkg install glibc patchelf` (Termux) | Required for the prebuilt Linux binary to load |
| Launcher installed but `jcode: not found` | `source ~/.bashrc` or open a new shell |
| Old file / dir at a destination is replaced during rerun | It's backed up as `<dst>.bak.<ts>` automatically; `ls -la ~/.jcode/` to inspect |
| `prompt-overlay.md` not picked up by jcode | Confirm `~/.jcode/prompt-overlay.md` exists and is a symlink to `swarm/prompt-overlay.md` in this repo. `ls -la ~/.jcode/prompt-overlay.md` should show the target. jcode reads it at session start — restart jcode after editing |
| Want to inspect what install.sh would do | `bash scripts/install.sh --help` and read the printed 3-step plan; the script itself does not support `--dry-run` — all runs write |