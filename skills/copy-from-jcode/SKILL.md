---
name: copy-from-jcode
description: Use when the user wants to snapshot their live jcode config (~/.jcode/) into the lazible-jcode repo, or sync installed skills from the system into the repo's skills/ directory. Also handles the reverse: install the repo's skills into ~/.jcode/skills/.
allowed-tools: bash, read, write, edit, agentgrep, todo
---

# copy-from-jcode

Sync a live `~/.jcode/` and `~/.jcode/skills/` with the `lazible-jcode` repo.

Two directions:

1. **Pull** — copy the current machine's `~/.jcode/` into this repo's
   `config/` (excluding secrets) and `~/.jcode/skills/` into this repo's
   `skills/`. Default direction.
2. **Install** — symlink this repo's `skills/` into `~/.jcode/skills/` so
   jcode picks them up. Use `--install` or `--symlink`.

This is the bridge between the repo (versioned, shareable) and the local
install (live, machine-specific, contains secrets).

## When to trigger

- "snapshot my jcode config"
- "pull ~/.jcode into the repo"
- "sync my skills into lazible-jcode"
- "install skills from lazible-jcode"
- "I changed my skills locally, sync them back"

## When **not** to trigger

- The user wants to install jcode itself — that is `/install-jcode`.
- The user wants to edit config — open `~/.jcode/config.toml` directly, not
  through this repo.

## Workflow

### 1. Detect

```bash
JCODE_HOME="${JCODE_HOME:-$HOME/.jcode}"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
```

Confirm both exist:

- `$JCODE_HOME/config.toml` and `$JCODE_HOME/mcp.json` for a **pull**
- `$REPO_ROOT/skills/` for an **install**

### 2. Pull direction (default)

Run the companion script:

```bash
./skills/copy-from-jcode/copy-from-jcode.sh
```

Behavior:

- Copies `$JCODE_HOME/config.toml` to `$REPO_ROOT/config/config.toml` only if
  the user passes `--include-config`. Default: skipped (config contains
  secrets + per-machine provider IDs).
- Copies `$JCODE_HOME/mcp.json` to `$REPO_ROOT/config/mcp.json` only with
  `--include-mcp`. Default: skipped.
- Copies every `SKILL.md` from `$JCODE_HOME/skills/*/SKILL.md` into
  `$REPO_ROOT/skills/<name>/SKILL.md`. This is the safe default because
  skills contain no secrets.
- Files in `$REPO_ROOT/skills/` that are not present in `$JCODE_HOME/skills/`
  are left alone (this repo can carry skills not yet installed locally).

Refuses to overwrite without `--force`. Prints a diff first and asks.

### 3. Install direction

```bash
./skills/copy-from-jcode/copy-from-jcode.sh --install
```

Behavior:

- For each subdirectory of `$REPO_ROOT/skills/` that contains a `SKILL.md`,
  create a symlink at `$JCODE_HOME/skills/<name>` pointing to
  `$REPO_ROOT/skills/<name>`.
- Skip already-symlinked entries (idempotent).
- Refuse to overwrite a real directory unless `--force`.

### 4. Verify

After pull:

```bash
git status                       # new SKILL.md files visible as untracked
diff -q "$REPO_ROOT/skills/optimization/SKILL.md" \
        "$JCODE_HOME/skills/optimization/SKILL.md"
```

After install:

```bash
ls -la "$JCODE_HOME/skills/"     # should show symlinks to repo paths
```

## Guardrails

- **Never** copy `auth.json`, `openai-auth.json`, `gemini_oauth.json`, or
  anything in `~/.jcode/pending-login/` into the repo. Refuse if asked.
- **Never** copy the `builds/` directory (immutable binaries + symlinks).
  It has no place in a portable config repo.
- **Never** `--force` over a non-symlink in `--install` mode without
  confirming the user understands they will lose the local skill.

## Companion script

```bash
./skills/copy-from-jcode/copy-from-jcode.sh --help
```