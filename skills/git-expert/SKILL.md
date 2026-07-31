---
name: git-expert
description: Use when user asks for git commit, branch, merge, rebase, cherry-pick, stash, reset, revert, reflog, worktree, tag, push, pull, fetch, or any git command. Daily operations, danger defenses, QiPDA commit/branch/worktree conventions.
skill-type: domain
version: 2.1
type: skill
skill-role: guidance
---

# git-expert

> ## STOP — Mandatory Auto-load
>
> Before ANY git command (commit, branch, merge, rebase, push, reset, stash,
> checkout, tag, log, status, diff, fetch, pull, worktree, cherry-pick, reflog,
> revert, blame, etc.) you MUST run:
>
> ```bash
> skill_manage action=read name=git-expert
> ```
>
> even if the user did NOT invoke `/git-expert`. Then execute the wake-up
> checklist, then re-read §1.7 (Author Identity) before any commit. This is
> non-negotiable: author identity is a legal/audit trail and the existing
> history's last commit author is the source of truth if config is missing.

**This skill should be loaded the moment any git command runs.** It runs a wake-up checklist, then keeps the agent on rails for the rest of the session.

## Wake-up Checklist

Run these when the skill is active, before doing anything else:

```bash
git status -sb                              # 1. working tree state
git branch --show-current                   # 2. current branch
git rev-parse --abbrev-ref --symbolic-full-name @{u}  # 3. upstream (or fail)
git log --oneline -5                        # 4. recent context
git config core.hooksPath                   # 5. hooks active?
```

Then:

1. State the current mode from the indicator below (out loud or in the result).
2. Identify which part applies: Part 1 (any repo) or Part 2 (QiPDA — check `AGENTS.md` exists).
3. If `app/` files are uncommitted, expect `v12/v13/v14` to false-positive fail (§2.7).

## STOP gates — these require explicit user confirmation

- `git push --force` to a shared branch (`main`, `release/*`, anything already pushed by others)
- `git reset --hard` to a SHA not in `git reflog`
- `git branch -D` on anything not yet merged
- `git push --mirror`, `git push --delete origin/X` for remote branch or tag
- `--no-verify`, `-c core.hooksPath=/dev/null`, or any hook bypass
- `git filter-repo` / `git filter-branch` (rewrites all history)
- **Author identity overrides** (see §1.7): `git -c user.name=X -c user.email=Y ...`, `git commit --author="X <x@y>"`, `GIT_AUTHOR_NAME=` / `GIT_COMMITTER_NAME=` env vars, AI/bot names like `jcode-bot` without explicit user approval

> **Single-agent by design.** git-expert describes per-file / per-commit rules for one agent. If the user wants parallel work on multiple branches (e.g. split a refactor into N parallel PRs), escalate to `/auto-swarm-planner`; the planner spawns workers that each re-enter this git-expert skill inside its own scope. The integrator phase of the swarm reuses this skill's §2.1 three-gate check before any commit lands.

## Mode Indicator

```
[MODE: git-expert] (inspecting | staging | committing | branching | merging | recovering | pushing)
```

| Phase | Enter when user wants to | Focus |
|-------|--------------------------|-------|
| `inspecting` | "show status / log / diff / blame / reflog" | Read-only — be bold |
| `staging` | "add / unstage / discard" | Local state tweaks |
| `committing` | "commit" | Message format + 3 gates + husky |
| `branching` | "create / switch / delete branch", "worktree" | Navigation |
| `merging` | "merge / rebase / cherry-pick" | History rewrite, conflict |
| `recovering` | "undo / recover / reflog / stash pop" | Mistake undo |
| `pushing` | "push / pull / fetch" | Pre-remote last check |

Switch to `recovering` immediately if user says "oh no", "lost", "undo", "我刚才错了", "撤销".

## When to Use

Any git command. This is the default skill for git work. **Do not** start a git operation without first running the wake-up checklist above.

## Slash Command

```
/git-expert <task>
```

Examples:

```
/git-expert recover from a bad reset --hard
/git-expert cherry-pick two commits from feat/a to release/x
/git-expert write a QiPDA-style commit message
/git-expert open a new branch without breaking current work
```

---

# Part 1 — General Rules (any repo)

## 1.1 Read-only is bold; writes are careful

| Operation | Rule |
|-----------|------|
| `status` `log` `diff` `show` `blame` `reflog` `branch -a` `tag -l` | Run freely |
| `add -p` `restore -p` | OK; `restore -p` discards working tree — read diff first |
| `stash` `stash push` | OK; avoid obscure flags |
| `commit` | ALWAYS run §2.1 gates first |
| `push` | Confirm branch + upstream; no `--force` on shared branches |
| `reset` `clean` `branch -D` | Use `recovering` flow or ask user |

## 1.2 Pre-commit Checklist (always)

Before any `git commit`, run this exact sequence:

```bash
git status -sb                     # see what will be staged
git diff --stat                    # size of the change
git diff                           # review the actual diff
git diff --cached --stat           # what is staged

# Three gates (QiPDA: §2.1)
node_modules/.bin/tsc --noEmit > /tmp/tsc_out.txt && echo "✓ tsc" || cat /tmp/tsc_out.txt
npm run lint 2>&1 | grep " error " | grep -v warning || echo "✓ lint"
node_modules/.bin/jest --no-coverage

# Then commit
git commit -m "type(scope): subject"
```

## 1.3 Common Commands

```bash
# Inspect
git status -sb
git diff --stat
git diff <path>
git log --oneline --graph --all -30
git reflog

# Stage
git add <path>
git add -p
git restore --staged <path>          # unstage, keep work tree
git restore <path>                   # discard work-tree change (irreversible)
git stash push <path>                # stash a single file

# Commit
git commit -m "type(scope): subject"
git commit --amend --no-edit         # NEVER amend a pushed commit
git rebase -i HEAD~3                 # squash local commits

# Branch and worktree
git switch -c feat/foo
git switch -
git worktree add ../repo-feat-foo feat/foo
git worktree list
git worktree remove ../repo-feat-foo

# Stash
git stash push -m "wip: reason"
git stash list
git stash show -p stash@{0}
git stash apply stash@{0}            # apply, keep entry
git stash pop                        # apply and drop

# Merge / rebase / cherry-pick
git fetch origin
git merge origin/main                # three-way, keeps topology
git rebase origin/main               # linear; NEVER rebase pushed commits
git cherry-pick <sha>
git cherry-pick <a>..<b>

# Recover
git reset --hard <sha-from-reflog>
git fsck --lost-found
git restore <sha>:<path>             # single file from a commit
```

## 1.4 Danger Defenses

| Operation | Risk | Defense |
|-----------|------|---------|
| `git reset --hard <sha>` | Discards work tree + stage | `git reflog` first |
| `git clean -fd` | Deletes untracked | `git clean -fdn` dry-run first |
| `git push --force` shared branch | Erases others' commits | `--force-with-lease` or refuse |
| `git branch -D <name>` | Drops unmerged branch | `git branch -d` first |
| `git rebase` pushed commits | Rewrites forks | Default forbidden |
| `git commit --amend` pushed | Same | Never amend pushed |
| `git filter-repo` / `filter-branch` | Rewrites all history | Default forbidden |
| `git push --mirror` | Wholesale overwrite | Permanent ban |
| `-c core.hooksPath=/dev/null` | Skips hooks | Default forbidden |

## 1.5 Conflict Resolution

```
1. git status                  # list conflict files
2. Edit, drop <<<<<< / ===== / >>>>>> markers
3. git add <file>              # mark resolved
4. git status                  # confirm no leftover
5. git rebase --continue       # or: git merge --continue
6. Bail:  rebase→--abort,  merge→--abort,  cherry-pick→--abort
```

Do not blindly run `--theirs` / `--ours`, or `git add` without resolving every marker.

## 1.6 Conventional Commits

```
<type>(<scope>): <subject>            ← ≤ 72 chars, imperative, no period
<body>                                ← one line usually enough
```

| Type | Use for |
|------|---------|
| `feat` `fix` `refactor` `perf` | Feature / fix / rewrite / perf |
| `test` `docs` `build` `ci` | One category only |
| `chore` | Everything else |
| `revert` | Revert |

## 1.7 Author Identity

Agent MUST NOT fabricate author name or email when committing. Author is
whatever `git config user.name` / `user.email` resolves to (local → global
→ system). Never override, never mask, never attribute to a fake name.

| Situation | Action |
|-----------|--------|
| Config is set | Use it as-is |
| Config missing, history has commits | Pull from most recent: `git log -1 --format='%an <%ae>'`, adopt those values, tell the user |
| Config missing AND history empty (fresh repo) | **Stop**. Ask the user — never initialize an identity unilaterally |

Forbidden patterns:

- `git -c user.name=X -c user.email=Y commit ...` to mask the agent
- `git commit --author="X <x@y>"` to attribute to anyone else
- Inventing an AI/bot name like `jcode-bot` without explicit user approval
- Setting `GIT_AUTHOR_NAME` / `GIT_COMMITTER_NAME` env vars to override config

Rationale: repo history's author is a legal / audit trail. The user owns it.

---

# Part 2 — QiPDA Conventions

ALWAYS read this part if the repo has `AGENTS.md`. The QiPDA-specific rules are stricter than the general ones.

## 2.1 Three Pre-commit Gates (required before `git commit`)

```bash
node_modules/.bin/tsc --noEmit > /tmp/tsc_out.txt \
  && echo "✓ tsc" || cat /tmp/tsc_out.txt
npm run lint 2>&1 | grep " error " | grep -v warning || echo "✓ lint"
node_modules/.bin/jest --no-coverage
```

Pass criteria: no **new** errors / failures. Existing ones must be called out in the commit message or reply.

## 2.2 husky Today

- `pre-commit` → `lint-staged` = `eslint --fix` (no prettier, no jest, no tsc)
- `commit-msg` → `commitlint --edit` for Conventional Commits

husky does **not** run the CI gates. The agent must run them. Default: no `--no-verify`, no `core.hooksPath` bypass.

## 2.3 Commit Style (≤ 2 lines, AGENTS.md rule)

```
fix(order): populate itemDiscounts on /orderPay lines per BFF spec
feat(security): mask member phone and staff name via pillars-security-crypto
feat(shopcart): 明细弹窗对齐算价结果显示活动优惠与券抵扣
fix: shopcart item card layout
merge feat/shopcart-item-card: unit price and discount price on the same row
```

- Common scopes: `order` `shopcart` `pricing` `auth` `coupon` `inventory` `payment` `member` `http` `test` `release`
- Chinese subject is fine
- No body by default; put motivation in PR description

## 2.4 Branch Names

```
feat/<short-snake>
fix/<short-snake>            # or fix/<IATZ-XXXX>
refactor/<short-snake>
bump/<version>
docs/<short-snake>
```

## 2.5 Worktree

`.pi/worktree-local/` is the local worktree root for jcode / pi agents.

```bash
git worktree add .pi/worktree-local/feat-foo -b feat/foo
git worktree list
git worktree remove .pi/worktree-local/feat-foo
```

Each worktree shares one `.git`, with its own working dir, index, and stash.

## 2.6 Merge Style

`git log --graph` shows many `merge feat/xxx into release/YYYYMMDD` nodes. The project uses **long-lived release branches + feature merges**, not squash or rebase.

Do not run interactive rebase on already-merged feature branches — that destroys merge info.

## 2.7 Scope Guards (v12 / v13 / v14) — false-positive alert

`__tests__/validate/v12-v14*.test.js` are scope-pinning regression tests for past PRs. They use `git diff --name-only HEAD -- app/ android/ packages/ env/.env.*` to detect unexpected app changes.

⚠️ These guards only work on a clean working tree. Any uncommitted change in `app/` makes them fail.

- They are **regression tests**, not per-commit gates
- Clean tree → always pass; CI is always green
- **Run jest on a clean HEAD** to avoid false-positive failures

```bash
# Pre-jest cleanliness check
git status -sb | grep -q "nothing to commit" \
  || echo "WARN: uncommitted changes; v12/v13/v14 will false-positive fail"

# Or stash temporarily
git stash --include-untracked
node_modules/.bin/jest --no-coverage
git stash pop
```

If you see v12/v13/v14 failing locally with files YOU just changed, do **not** assume the code is wrong. Check the cleanliness first.

## 2.8 QiPDA Anti-Patterns (in addition to §1.4)

| Anti-pattern | Why bad in QiPDA |
|--------------|------------------|
| "Fix CI" + feature in same commit | Hard to revert or cherry-pick mid-release |
| Amend a pushed commit | Breaks other branches / ongoing merges |
| Squash merge instead of merge commit | Loses `merge feat/xxx: ...` history nodes |
| Commit directly to `master` / `release/*` | Project uses long-lived branches + merge commits |
| Run jest with dirty work tree | Triggers v12/v13/v14 false positives |

---

# Part 3 — Troubleshooting (switch to `recovering` mode)

| Symptom | Fix |
|---------|-----|
| Bad `reset --hard` | `git reflog` → `git reset --hard <sha>` |
| Forgot to stage a file | `git add <file> && git commit --amend --no-edit` (only if not pushed) |
| Pushed commit + forgot file | `git add <file> && git commit --fixup=<sha> && git rebase -i --autosquash <sha>~1` |
| Wrong message on pushed commit | Not pulled → amend + `--force-with-lease`. Pulled → new commit, never rewrite |
| husky hook failed | `git commit -m "..."` without `--no-verify`, read error; or run `yarn lint-staged` directly |
| v12 / v13 / v14 false-positive fail | See §2.7; run jest on a clean tree |
| Dangling commit | `git fsck --lost-found`, then `git show <sha>` and `git cherry-pick <sha>` |
| Mid-merge regret | `git merge --abort` / `git rebase --abort` / `git cherry-pick --abort` |
| Stash lost | `git fsck --lost-found` (reflog keeps 90 days) |
| Detached HEAD | `git switch -c <new-branch>` to save the work |

---

# Part 4 — Anti-Patterns (general)

| Anti-pattern | Do this instead |
|--------------|------------------|
| `git add .` blindly | `git add -p` or `git add <specific path>` |
| `git commit -m "fix"` vague | `fix(scope): subject with reason` |
| Subject > 72 chars or body > 1 line | Short subject; motivation in PR description |
| `git push --force` to main / release | `--force-with-lease` or refuse |
| `git reset --hard` without reflog | `git reflog` first |
| `git commit --amend` on pushed | New commit that fixes it |
| `git stash` as long-term backup | Commit it if you want to keep it |
| `git clean -fd` with no dry-run | `git clean -fdn` first |
| `git checkout <sha>` to detached HEAD | `git switch -c <new-branch> <sha>` |
| Commit large binaries | `.gitignore` + LFS |
| Commit secrets / tokens / .env | `pillars-security-crypto` or pre-commit secret scan |
| `git fetch && git reset --hard origin/main` | `git pull --rebase` or `git merge` |
| `--no-verify` / `core.hooksPath` bypass | Run the gates manually |

---

# Quick Reference (one-liner per action)

```bash
# State
git status -sb
git diff --cached --stat

# Stage
git add <path>                              git restore --staged <path>

# Commit
git commit -m "type(scope): subject"        git commit --amend --no-edit

# Branch
git switch -c feat/foo                      git switch -
git branch -d <merged>                      git branch -D <unmerged-need-ask>

# Worktree
git worktree add .pi/worktree-local/<x> -b <branch>
git worktree remove .pi/worktree-local/<x>

# Stash
git stash push -m "wip"                     git stash pop
git stash show -p stash@{0}

# Merge / rebase / pick
git merge origin/main                       git rebase origin/main
git cherry-pick <sha>                       git cherry-pick <a>..<b>

# Recover
git reflog                                  git fsck --lost-found
git reset --hard <reflog-sha>               git restore <sha>:<path>

# Remote
git fetch origin                            git pull --rebase
git push                                    git push --force-with-lease
```