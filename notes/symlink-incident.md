# Configuration Pollution Incident (2026-09-28)

## Symptoms

`config/config.toml` (HEAD blob) was polluted by the `autonomous` overlay. Direct symptom:
in the commit log `git show HEAD:config/config.toml` contains
`ambient.enabled = true`, `agents.swarm_spawn_mode = "headless"`,
`hooks.post_tool = ["~/.local/bin/jcode-audit-log"]`:
fields that should only appear in `~/.jcode/config.toml` (live).

## Root cause

Timeline (from the incident's perspective):

1. **An earlier session**: `~/.jcode/config.toml` was a symlink pointing at
   `<repo>/config/config.toml`.
2. **An earlier session**: `./scripts/use-profile autonomous` was invoked.
3. At the time, use-profile's Python write path `open(target, 'w')` followed the symlink,
   writing `base + autonomous overlay` into the repo file.
4. **`git add -A`** staged the polluted working-tree config.toml.
5. **`git commit`** committed it.
6. The pollution landed in git history that way.

Pre-fix impact: from commit `32684d6` onward, HEAD's `config/config.toml` always carried
overlay state, until commit `59c5140` explicitly pulled the clean base back from `3be45dc`.

## Fix

- `8fe3f5d`: use-profile / use-profile-reset / snapshot-config all gain symlink detection,
  exit 3 plus remediation hint. `~/.jcode/config.toml` must first be `rm`'d, then `cp`'d into
  a regular file.
- `59c5140`: pull the clean base back from `3be45dc`; add `scripts/diff-live-base` for
  structural diff diagnosis.
- `ae0ef5d`: verify-sanitized gains a live-vs-base drift counter; >20 leaves triggers a warning.

## Detection

```bash
./scripts/verify-sanitized    # look at the "live vs base drift" line
./scripts/diff-live-base      # detailed diff, section by section
```

## Design constraints

Notes for my future self:

- **Repo base** = `config/config.toml` (committed base). Update only via `snapshot-config`
  (manual) or hand-edits; **never** via `use-profile` or any other script that writes live.
- **Live** = `~/.jcode/config.toml` (runtime). Manipulated by `use-profile` /
  `use-profile-reset`.
- **Any script that writes live MUST first check `[[ -L $target ]]`**, otherwise the symlink
  trap recurs.
- **`snapshot-config` writing the repo base MUST also check for symlinks first**, otherwise
  pollution recurs through it.
- **`verify-sanitized` always runs the drift check** (CI-friendly).

## Lessons

1. **Don't assume `git add -A` is safe**. Run `git status` before committing to inspect
   staged files.
2. **Symlinks are a fragile design**. Any tool that writes to a symlink target should
   refuse or at least warn.
3. **Pollution cannot be fully removed by "undoing"**. `git checkout HEAD -- <file>` only
   fixes the working tree, not the HEAD blob; use amend or revert.
4. **Structural diff is not covered by secrets checks**. The original `verify-sanitized`
   only looked for secrets / hardcoded paths and overlooked "live is overlay, base must
   not be overlay" type structural issues. The drift check addresses that.