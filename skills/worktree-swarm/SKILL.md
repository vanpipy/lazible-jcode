---
name: worktree-swarm
description: Orchestrate swarm workers on isolated git worktrees. Use when spawning workers that need safe concurrent commits, when cleaning up zombie worktrees, or when checking the swarm manifest. Allocates one worktree per worker under $TMPDIR/swarm-$USER/<repo>-<short-sha>/, symlinks heavy in-repo deps, and tracks active workers in .jcode/worktree-manifest.json with an 8-hour TTL.
allowed-tools: bash, read, write, edit, todo
---

# worktree-swarm

Allocate, teardown, and clean up worker worktrees for swarm spawning.

Each spawned worker that writes code (implementer, test-writer, migrator)
gets its own git worktree. Reviewer / investigator stay on root cwd.
Doc-writer defaults to root cwd, may be assigned a worktree if needed.

See `~/.jcode/swarm-prompt.md §11` for the full coordination spec.

## When to trigger

- "allocate a worktree for worker X"
- "spawn worker X with a fresh worktree"
- "tear down worker X's worktree after merge"
- "clean up zombie / stale worktrees"
- "show active swarm workers"
- "is there an existing worktree for label X?"

## When NOT to trigger

- Spawning workers themselves — that is `swarm spawn`. This skill is the
  *worktree* layer beneath it.
- Editing `swarm-prompt.md` or roles — those are config files.
- For `reviewer` / `investigator` / `doc-writer` (default no-worktree roles),
  skip this skill entirely.

## Workflow

### 1. Detect

```bash
git rev-parse --show-toplevel
git rev-parse --short=7 HEAD
test -d "$REPO_ROOT/.git"
```

Confirm we are in a git repo. If not, abort with "no worktree allocation
without git context, worker uses root cwd".

### 2. Cleanup stale

Always run first:

```bash
~/.jcode/skills/worktree-swarm/worktree-swarm.sh cleanup
```

Removes worktrees whose `created_at` exceeds TTL (8 hours) and whose
branches are not merged into main. Failure here is non-fatal — log and
continue.

### 3. Allocate (per worker that needs worktree)

```bash
~/.jcode/skills/worktree-swarm/worktree-swarm.sh alloc <name> \
    --type feat|fix|chore|docs|refactor|test \
    [--base <sha>] [--no-link]
```

Output format (tab-separated, machine-readable):

```
<worktree_path>\t<branch>
```

Capture both into the spawn prompt. The script:

- creates worktree + branch (`<type>/<name>_<short-sha>`)
- symlinks heavy in-repo deps from main (configurable via
  `.jcode/worktree.toml [symlinks].include`)
- records the worker in `.jcode/worktree-manifest.json`

If a worktree for the same label already exists, the script refuses (use
`teardown` first).

### 4. Spawn worker

```bash
swarm spawn --label "<sanitized_label>" \
            --prompt "..." \
            --model ... --effort ...
```

The spawn prompt **must** include these three fields so the worker knows
its environment:

- `<worktree_path>` — absolute path to the worker's worktree
- `<base_commit>` — fork source SHA
- `<worker_branch>` — branch the worker commits to

The worker's role file (`implementer.md`, `test-writer.md`, `migrator.md`)
already describes how to use the worktree. Confirm `pwd` matches
`<worktree_path>` and `git branch --show-current` matches `<worker_branch>`
before doing anything.

### 5. Integrate (after worker reports `ready`)

In the **main** worktree, on the integration branch:

```bash
git merge --no-ff <worker_branch>
# run full CI gates: tsc / lint / jest / e2e
~/.jcode/skills/worktree-swarm/worktree-swarm.sh teardown <sanitized_label>
```

Teardown removes worktree + branch + manifest entry. Run before the next
spawn.

### 6. Verify

```bash
~/.jcode/skills/worktree-swarm/worktree-swarm.sh list
```

Show all active workers with path, branch, age.

## Guardrails

- **Never** allocate a worktree for `reviewer` / `investigator` /
  `doc-writer` (default no-worktree roles).
- **Never** `--force` over an unmerged worktree without confirming with the
  user.
- **Never** symlink across repos (`/path/to/other-repo/node_modules` →
  `wt-X/node_modules`).
- **Never** install inside a worker worktree. New deps go through root
  (`pnpm install` / `pod install` in main, then re-symlink in worker).
- **Never** delete `.jcode/worktree-manifest.json` manually — use
  `teardown` / `cleanup`.

## Companion script

```bash
~/.jcode/skills/worktree-swarm/worktree-swarm.sh help
~/.jcode/skills/worktree-swarm/worktree-swarm.sh alloc <name> --type feat
~/.jcode/skills/worktree-swarm/worktree-swarm.sh teardown <label>
~/.jcode/skills/worktree-swarm/worktree-swarm.sh cleanup
~/.jcode/skills/worktree-swarm/worktree-swarm.sh list
```

Requires `git`, `python3` (for JSON ops), and writable `.jcode/`.

After install, make the script executable once:

```bash
chmod +x ~/.jcode/skills/worktree-swarm/worktree-swarm.sh
```

(Symlinks preserve the executable bit; this only needs running if you
installed via plain copy.)

## Manifest schema

`.jcode/worktree-manifest.json`:

```json
{
  "version": 1,
  "workers": [
    {
      "label": "feat-foo-a1b2c3d",
      "type": "feat",
      "name": "foo",
      "worktree_path": "/tmp/swarm-x/repo-a1b2c3d/wt-feat-foo-a1b2c3d",
      "branch": "feat/foo_a1b2c3d",
      "base_commit": "a1b2c3d4e5f6",
      "created_at": 1722514800,
      "status": "active"
    }
  ]
}
```

`status` values: `active` (default), `merged` (set by teardown post-merge),
`failed` (set by cleanup).

## Per-project overrides

`.jcode/worktree.toml` (optional):

```toml
[symlinks]
# Deps to symlink from main worktree to each worker worktree.
# Default: node_modules, ios/Pods
include = ["node_modules", "ios/Pods"]

[cleanup]
# How long to keep failed worktrees before auto-cleanup.
# Default: 8 hours
preserve_failed_hours = 8

# Remove worktree + branch automatically after a successful merge.
# Default: true
auto_remove_merged = true
```