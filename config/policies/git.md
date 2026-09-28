# Git / Worktree Policy (v1)

## Worktree decision (manual algorithm)

The worktree auto-strategy from `new.md` §9 is **not implemented** in jcode source.
This repo's policy is:

1. **Before each session** run `git status` + `git fetch`, confirm no conflicts on the main branch
2. **New task**: in the main working directory, open branch `agent/<task-id>` (worktree optional)
3. **High conflict / large refactor**: isolate with `git worktree add ../<repo>-agent-<hash> agent/<name>`
4. **worktree ≠ agent**: multiple sweepers may share a worktree, as long as they don't modify the same files

See [`notes/worktree-strategy.md`](../notes/worktree-strategy.md).

## Branch naming

| Scenario | Branch name |
| --- | --- |
| Ambient autonomous work | `ambient/<topic>` (controlled by `work_branch_prefix`) |
| Manual task | `agent/<task-id>` |
| Long-running experiment | `exp/<topic>` |

## Commit conventions

- Commit messages use the `prefix: summary` format (consistent with jcode itself)
- Never paste tokens or paths in commit messages
- A single PR should not exceed 30 file changes; if it does, split it

## Defenses

- The default `[hooks].pre_tool` blocks `git push` to protected branches (`main` / `master` / `production`)
- Blocks `git push --force`
- Does not block `git push` to feature branches