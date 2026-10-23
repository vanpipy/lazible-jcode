# Git Policy

## What the tool policy actually blocks

`[hooks].pre_tool` runs `jcode-tool-policy` on every `Bash` call. It is a
synchronous gate: exit 0 allows, exit 2 blocks and the reason reaches the
model on stderr.

| Action | Result |
| --- | --- |
| `git push` (any branch, any flags) | **blocked** |
| `git commit` on an `ambient/*` branch, project has no active goal | **blocked** |
| `git commit` on an `ambient/*` branch, active goal has no pending step | **blocked** |
| everything else | allowed |

`git push` is blocked unconditionally, including to feature branches and with
`--force`. The rationale: a worker session has no business publishing. The
human runs `git push` outside the session.

Escape hatch for a deliberate push: `JCODE_TOOL_POLICY_BYPASS=1`.

## Branch naming

| Scenario | Branch name |
| --- | --- |
| Ambient autonomous work | `ambient/<topic>` (prefix from `ambient.work_branch_prefix`) |
| Manual task | `agent/<task-id>` |
| Long-running experiment | `exp/<topic>` |

## Commits

- Conventional commits: `type(scope): subject`. Lowercase, imperative, no
  trailing period.
- One commit per logical change. Do not bundle unrelated fixes.
- Never put tokens or absolute user paths in a commit message.
- A single change should not exceed 30 files. Split it.

## Worktree decision (manual)

jcode has no automatic worktree selection. `SwarmSpawnMode` chooses how a
worker is displayed, not where it runs. Decide manually:

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

Use a dedicated worktree when:

- multiple workers touch the same file tree concurrently
- a single change exceeds 30 files
- the change touches the build system, a schema migration, or renames
- an ambient run is long enough that you want to be able to roll it back

Do not use one when:

- a single agent changes a single file
- several workers touch disjoint files (this is the jcode default)

```bash
git worktree add ../<repo>-<task-hash> -b agent/<task-id>
git worktree list
git worktree remove ../<repo>-<task-hash>
git branch -d agent/<task-id>
```

> worktree = **isolation boundary**
> agent = worker that may or may not own a worktree
> one worktree can host multiple agents, one agent can span multiple worktrees
