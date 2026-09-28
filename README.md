# lazible-jcode

jcode config + patch workflow. `./scripts/install` does it all in one command: clone fork → rebase → build → install binary → wire config.

The source fork lives at `./patched-jcode` : a symlink at the repo root that defaults to `~/Project/patched-jcode` (vanpipy/jcode's `feat/patches` branch). Override with `JCODE_SOURCE_DIR=...` if you keep your clone elsewhere.

---

## One-shot install

```bash
git clone <repo> ~/Project/lazible-jcode
cd ~/Project/lazible-jcode

# First time only: clone the fork (install creates the patched-jcode symlink
# automatically on first run if you point JCODE_SOURCE_DIR at the clone location)
git clone https://github.com/vanpipy/jcode.git ~/Project/patched-jcode
cd ~/Project/patched-jcode
git checkout -B feat/patches
# ... edit source + commit ...

# Run install (creates patched-jcode symlink → ~/Project/patched-jcode,
# fetch + rebase + build + wire + verify + state.json)
cd ~/Project/lazible-jcode
./scripts/install
```

After that, every time you commit new patches in `./patched-jcode` (or wherever `JCODE_SOURCE_DIR` points), just rerun `./scripts/install` : it auto-rebases onto the fork's default branch, rebuilds, and installs the new binary.

---

## Common commands

```bash
./scripts/install                       # auto install
./scripts/install --dry-run             # show what would happen, no side effects
./scripts/install --help                # all flags
JCODE_BUILD=debug ./scripts/install     # debug build (target/debug)
JCODE_NO_PUSH=1   ./scripts/install     # skip auto push of feat/patches
JCODE_SOURCE_DIR=~/work/jcode ./scripts/install   # use a fork clone at a custom path

./scripts/uninstall --dry-run           # show what would be removed
./scripts/uninstall                     # remove binary + state (with confirmation)
./scripts/uninstall --full --yes        # also remove config + skills + shell env
```

---

## Install pipeline (runs every time)

1. **Pre-flight**: check deps (bash / python3 / git / cargo)
2. **Source**: ensure `./patched-jcode` symlink → `$JCODE_SOURCE_DIR`; clone fork if missing
3. **Branch**: checkout `feat/patches` (create from fork's default branch if missing : **auto-detected**)
4. **Rebase**: `git rebase <baseline>` (runs every time; conflict = exit 4)
5. **Build**: `cargo build --release --bin jcode`
6. **Install binary**: `~/.local/bin/jcode` (existing binary backed up as `.bak.<timestamp>`)
7. **Wire config**: cp `config.toml` + profile + skills + shell env + audit log
8. **Verify**: 7 checks (binary / source / origin / config / profile / skills / shell env)
9. **State**: write `~/.local/state/lazible-jcode/state.json`

---

## Key constraints

- **`install` does not commit**. You must commit your patches in `$JCODE_SOURCE_DIR` first. A dirty working tree (tracked **or** untracked changes) → exit 3.
- **`~/.jcode/config.toml` must not be a symlink** → exit 1. Fix: `rm ~/.jcode/config.toml && cp config/config.toml ~/.jcode/config.toml`
- **`install` overwrites live config**. Snapshot first with `./scripts/snapshot-config`, then install.
- **`~/Project/jcode` (upstream clone) is never touched** : install only operates on the fork at `./patched-jcode`.

---

## Always preserved during uninstall

- `./patched-jcode` symlink (and the fork clone it points at, default `~/Project/patched-jcode/`)
- `~/Project/patched-jcode/` (real fork clone, source + all your patches)
- `~/Project/jcode/` (upstream clone, if present)
- `~/.jcode/ambient/, state/, sessions/, logs/` (runtime state)

---

## Sub-tools

```bash
./scripts/use-profile                    # apply profile (default: autonomous)
./scripts/use-profile-reset              # revert to base
./scripts/install-shell-env --apply      # write JCODE_OPENROUTER_MODEL into shell rc
./scripts/install-shell-env --status     # check current state
./scripts/sync-skills --to-home --apply  # config/skills → ~/.jcode/skills
./scripts/snapshot-config                # live ~/.jcode/config.toml → repo (sanitized)
./scripts/verify-sanitized               # pre-commit self-check
./scripts/diff-live-base                 # diff live config vs repo base
```

Full list: [`scripts/README.md`](scripts/README.md).
