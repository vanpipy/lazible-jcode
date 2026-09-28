# scripts

Install, configure, and maintain the `lazible-jcode` repo. Architecture:

```
install ─── (orchestrator) ── invokes ──┐
                                       │
uninstall ── (inverse)                 │
                                       │
                                       ├── use-profile         # profile overlay
                                       ├── use-profile-reset   # revert to base
                                       ├── install-shell-env   # write ~/.zshrc env
                                       ├── sync-skills         # bidirectional skills sync
                                       ├── jcode-audit-log     # post_tool hook
                                       └── snapshot-config     # reverse-sync config
                                       │
                                       ▼
verify-sanitized               # pre-commit self-check (standalone)
diff-live-base                 # live vs base drift (standalone)
_lib_toml.py                   # shared TOML utilities
```

`install` is the new main entry point (introduced 2026-09-29). It unifies
source management (fork clone + rebase + build) and config management
(profile + skills + env) into a single atomic action.

---

## Main entry points

### `./scripts/install` (**new main entry**)

Orchestrator: clone the fork's `feat/patches` branch → rebase onto the fork's
default branch (**auto-detected** main/master) → cargo build → install binary
to `~/.local/bin/jcode` → wire up the config layer.

```bash
./scripts/install                  # auto install (default)
./scripts/install --dry-run        # print what would happen, no side effects
./scripts/install --force          # allow overwriting existing binary / changing origin
./scripts/install --no-preflight   # skip dep check (for CI)
./scripts/install --help           # show all flags
```

**Every install runs**:

1. Pre-flight: check deps (bash / python3 / git / cargo / rustc), path writability
2. Source: ensure `./patched-jcode` symlink at repo root; clone fork into `$JCODE_SOURCE_DIR` (default `~/Project/patched-jcode`) if missing; otherwise fetch + verify origin
3. Branch: checkout `feat/patches` (create from fork's default branch if missing : **auto-detects main/master**)
4. **Rebase**: `git rebase <baseline>` (runs every install; conflict = exit 4)
5. Build: `cargo build --release --bin jcode` (with `JCODE_BUILD_VERSION` + `JCODE_BUILD_GIT_HASH` injected so the embedded version string tracks HEAD)
6. Install binary: `~/.local/bin/jcode` (existing binary backed up if present)
7. Wire config: cp `config.toml` + `use-profile` + `sync-skills` + `install-shell-env`
   + `jcode-audit-log`
8. Verify: 7 checks (binary callable / binary matches source /
   origin is vanpipy fork / config not symlink / profile applied
   / skills synced / shell env installed)
9. State: write `~/.local/state/lazible-jcode/state.json`

**Key constraints**:

- install **does not commit**: you must commit your patches in `$JCODE_SOURCE_DIR`
  (default `~/Project/patched-jcode`) before running install. Dirty working tree
  (tracked **or** untracked changes) → exit 3
- Every install rebases: your patches are always replayed onto the latest fork default branch (main / master auto-detected)
- `~/Project/jcode` (existing upstream clone) is never touched
- `~/.jcode/config.toml` must not be a symlink (exit 1)
- The repo carries a `patched-jcode` symlink at its root, so every script in the
  repo can reference `${REPO}/patched-jcode` instead of a hardcoded absolute path

**Environment variables**:

- `JCODE_BUILD=debug` : use debug profile (faster, skips optimizations)
- `JCODE_NO_PUSH=1` : skip auto push of `feat/patches` to origin
- `JCODE_SOURCE_DIR=<path>` : override where the fork clone lives (default
  `~/Project/patched-jcode`); install keeps the `patched-jcode` symlink in sync

**Exit codes**:

| code | meaning |
| --- | --- |
| 0 | success |
| 1 | preflight failed (missing deps / path conflict / symlink config) |
| 2 | source dir origin mismatch (unless `--force`) |
| 3 | working tree dirty (must commit before install) |
| 4 | rebase conflict (user must resolve manually) |
| 5 | cargo build failed |
| 6 | verify failed |

**Rebase conflict recovery**:

```bash
cd $JCODE_SOURCE_DIR   # default ~/Project/patched-jcode

# option 1: resolve the conflict
#   (edit conflicted files)
git add <resolved-files>
git rebase --continue

# option 2: abandon patches, start fresh from fork default branch
git rebase --abort
git reset --hard <baseline>      # origin/main or origin/master (auto-detected)

# option 3: skip the current patch
git rebase --skip

# then rerun
./scripts/install
```

### `./scripts/uninstall` (**new main entry**)

Inverse: remove the artifacts left behind by install.

```bash
./scripts/uninstall                  # default: only binary + state (needs confirmation)
./scripts/uninstall --dry-run        # print what would be removed, no side effects
./scripts/uninstall --full           # also remove config + skills + shell env (needs --yes)
./scripts/uninstall --yes            # skip all confirmation prompts
./scripts/uninstall --help           # show all flags
```

**Default behavior** (low destruction) : removes:

- `~/.local/bin/jcode`
- `~/.local/bin/jcode.bak.*`
- `~/.local/bin/jcode-audit-log`
- `$XDG_STATE_HOME/lazible-jcode/state.json` (default `~/.local/state/lazible-jcode/state.json`)

**`--full`** (high destruction, needs `--yes` or interactive confirmation) : also removes:

- `~/.jcode/config.toml`
- `~/.jcode/skills/<install-contributed>` (matched against `config/skills/`)
- The jcode env block in `~/.zshrc` + `~/.bashrc`

**Always preserved** (default and `--full`):

- `${REPO}/patched-jcode` symlink (the canonical in-repo entry point for the source tree)
- `$JCODE_SOURCE_DIR/` (**source + your patches** : the symlink's target, default `~/Project/patched-jcode/`)
- `~/Project/jcode/` (your upstream clone, if any)
- `~/.jcode/ambient/, state/, sessions/, logs/` (runtime state)

---

## Standalone tools (called by `install`, but also usable manually)

### `./scripts/use-profile`

Deep-merge `config/config.toml` with `config/profiles/<name>.toml` into
`~/.jcode/config.toml`. Default profile = `autonomous`.

```bash
./scripts/use-profile           # default: autonomous
./scripts/use-profile default   # switch to base (currently an empty overlay)
./scripts/use-profile-reset     # pull a clean base from git HEAD (no overlay)
```

### `./scripts/install-shell-env`

Write `JCODE_OPENROUTER_MODEL=MiniMax-M3` into `~/.zshrc` + `~/.bashrc`.
This is the defense layer for Bug A (the `Provider::fork()` race env var mitigation).

```bash
./scripts/install-shell-env                # dry-run: show what would be written
./scripts/install-shell-env --apply        # actually write
./scripts/install-shell-env --remove       # inverse: remove the installed block
./scripts/install-shell-env --status       # check current state (no writes)
```

### `./scripts/sync-skills`

Bidirectional sync between `config/skills/` and `~/.jcode/skills/` /
project `.jcode/skills/`.

```bash
./scripts/sync-skills --to-home --apply                # → ~/.jcode/skills/
./scripts/sync-skills --from-home --apply              # ← ~/.jcode/skills/
./scripts/sync-skills --to-project /path/to/repo --apply  # → <repo>/.jcode/skills/
./scripts/sync-skills --to-home --apply --overwrite    # overwrite same-named skill (default: skip)
./scripts/sync-skills --help
```

Default is dry-run; `--apply` actually writes.

**Important constraint**: by default `--to-home` **does not overwrite** an
existing same-named skill (unless `--overwrite`). Since `install` calls the
default mode:

- **First install**: `config/skills/*` → `~/.jcode/skills/` (copied)
- **Subsequent installs**: existing skills are **skipped** (not updated)

If you edit a skill in `config/skills/<name>/SKILL.md` and want
`~/.jcode/skills/<name>/` to update:

```bash
./scripts/sync-skills --to-home --apply --overwrite
# or
rm -rf ~/.jcode/skills/<name> && ./scripts/install
```

### `./scripts/snapshot-config`

Copy `~/.jcode/config.toml` **back to** `config/config.toml` after sanitizing.
The inverse of install (but only touches the config layer, not the source).

```bash
./scripts/snapshot-config       # ~/.jcode → config/ (sanitized)
./scripts/snapshot-config --help
```

### `./scripts/jcode-audit-log`

The `autonomous` profile's `post_tool` observer hook. Each tool call appends
a line to `~/.local/share/lazible-jcode/audit.log` (jsonl).

`install` automatically copies it to `~/.local/bin/jcode-audit-log` and chmods.
Manual copy:

```bash
cp scripts/jcode-audit-log ~/.local/bin/jcode-audit-log
chmod +x ~/.local/bin/jcode-audit-log
```

---

## Pre-commit self-check (standalone, unrelated to install)

### `./scripts/verify-sanitized`

```bash
./scripts/verify-sanitized
```

Checks:

1. `config/config.toml` parses with `tomllib`
2. Known sensitive keys (`api_key`, `token`, `secret`, `password`) are empty / placeholder values
3. Absolute paths start with `~/` or `$HOME/` (no `/home/...`)
4. Profile files follow the same rules
5. Skill content has no tokens (rough grep for `^[A-Za-z0-9_-]{40,}$`)

### `./scripts/diff-live-base`

Structural diff (per section, optional) between live `~/.jcode/config.toml`
and the repo base.

```bash
./scripts/diff-live-base                # all sections
./scripts/diff-live-base --section ambient
```

---

## Shared utilities

### `./scripts/_lib_toml.py`

TOML emitter + merge + secret mask, shared by `use-profile` / `snapshot-config`.
No external deps (uses stdlib `tomllib`, custom emit, runs in PEP 668 environments too).

---

## Safety constraints (inherited by every script)

- Every script that writes `~/.jcode/config.toml` **refuses symlinks** (to
  prevent overwriting the repo base). If you see `exit 3`, first run
  `cp config/config.toml ~/.jcode/config.toml` to replace the symlink.
- `snapshot-config` also refuses symlinks.
- `verify-sanitized` treats symlinks as a **warning** (does not fail).
- `install` rejects a symlink config during preflight (exit 1).

## Design constraints

- Scripts **do not modify files inside this repo** (except `snapshot-config`,
  which you commit manually).
- All write targets are `~/.jcode/`, `~/.local/`, `~/Project/`, or a
  user-specified project directory.
- Default is dry-run or needs confirmation; explicit `--apply` / `--yes` /
  `--force` to actually take effect.
- No macOS / Linux assumptions : POSIX sh + Python 3.11+ (`tomllib`).
- TOML parse via `tomllib`; emit via `_lib_toml.py` (no `tomli_w` dependency).

## Typical workflow

### First-time install

```bash
# 1. clone lazible-jcode repo
git clone <lazible-jcode-url> ~/Project/lazible-jcode
cd ~/Project/lazible-jcode

# 2. write patches on the fork
git clone https://github.com/vanpipy/jcode.git ~/Project/patched-jcode
cd ~/Project/patched-jcode
git checkout -B feat/patches origin/master
# ... edit files ...
git add -A && git commit -m "fix: Bug F2 : runner idle filter"

# 3. run install
cd ~/Project/lazible-jcode
./scripts/install
```

### Subsequent updates (after committing new patches)

```bash
cd $JCODE_SOURCE_DIR   # default ~/Project/patched-jcode (also accessible via ./patched-jcode from repo root)
# ... edit more files ...
git add -A && git commit -m "fix: Bug G : bash tool timeout cap"

cd ~/Project/lazible-jcode
./scripts/install         # auto fetch + rebase + rebuild + reinstall
```

### Uninstall

```bash
cd ~/Project/lazible-jcode
./scripts/uninstall --dry-run     # show what would be removed
./scripts/uninstall              # actually remove binary + state (needs confirmation)
./scripts/uninstall --full --yes  # also remove config + skills + shell env
```

The source tree at `${REPO}/patched-jcode` (and its target at `$JCODE_SOURCE_DIR`)
is always preserved.
