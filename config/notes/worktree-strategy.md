# Worktree Decision Algorithm (v1, manual)

`new.md` §9 designs the worktree auto-strategy. jcode does not yet implement it.
This file describes the **manual-operation algorithm**, aligned with `new.md`:

```text
Task
  ↓
Analyze file ownership
  ↓
Conflict? ─── yes ──► Dedicated worktree
  │ no
  ↓
Risk? ──────── yes ──► Dedicated worktree
  │ no
  ↓
Shared workspace
```

## When to use a dedicated worktree

- Multiple sweeper agents touch the same file tree concurrently
- A single PR changes more than 30 files
- Touches build system, schema migration, or renames
- Ambient runs a long task that may need to roll back

## When NOT to

- Single agent, single-file change
- Multiple conflict-free sweepers in one worktree (this is the jcode default)

## Commands

```bash
# Create a worktree
git worktree add ../<repo>-<task-hash> -b agent/<task-id>

# List worktrees
git worktree list

# Clean up after task completes
git worktree remove ../<repo>-<task-hash>
git branch -d agent/<task-id>
```

## Relationship with swarm

- worktree = **isolation boundary**
- agent = **worker that may or may not own a worktree**
- One worktree can host multiple agents; one agent may span multiple worktrees

> This principle matches `new.md §9`. jcode source (`SwarmMemberRecord.working_dir`)
> already supports per-agent `working_dir`, but auto-selection is left to the upper layer.