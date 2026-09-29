# ~/AGENTS.md — User-Level Global Instructions

> Loaded by jcode at session start via `load_agents_md_files_from_dirs`
> (`crates/jcode-base/src/prompt.rs:949`).
>
> Load order in the system prompt:
> 1. Project `./AGENTS.md` is read first ("Project Instructions")
> 2. This file is read second ("Global Instructions") and appended after
> 3. Both are injected into the system prompt; later-appearing same-section
>    headings take precedence (project file appears earlier in the prompt but
>    has **higher specificity**, so we follow the rule:
>    "specifics override generals")
>
> This file is installed by `./scripts/install` **only when it does not
> already exist**. Subsequent installs never overwrite your edits. To force
> regeneration: `rm ~/AGENTS.md && cd ~/Project/lazible-jcode && ./scripts/install`.

## How projects should layer on top

Projects may declare `<project>/AGENTS.md` with section headings prefixed by
`## Project: ...` or `## User: <topic> (override)`. The override convention
makes conflicts traceable.

**Section heading taxonomy**:

| Prefix | Where it belongs | Who wins on conflict |
| ------ | ---------------- | -------------------- |
| `## User: <topic>`           | this file (user-level)        | project override wins |
| `## User: <topic> (override)`| project file (overrides user) | wins over the user section |
| `## Project: <topic>`        | project file (project-only)   | always wins for project matters |

**Example override in a project file**:

```markdown
# ~/Project/awp/AGENTS.md

## User: Working style (override)
- awp-specific: do NOT touch `pane/audio/*` (lipgloss cache bug).
```

---

## User: Working style

- Commit before `./scripts/install` — it never auto-commits.
- Use `rg` / `fd` / the `edit` tool; never `grep -r` / `find` / `sed -i`.
- Use `python3` (stdlib only, no third-party deps) for config manipulation.
  Scripts in this repo (use-profile, sync-skills, snapshot-config) all follow this.
- Prefer **shell + python** over one-off rust for system maintenance.
- Terse output. Tables over paragraphs. Bullets over prose.

## User: Communication

- Chinese when the user writes in Chinese; English in code, comments, and commit messages.
- Never use em dashes (—); use periods, commas, or line breaks instead.
- Never use semicolons as em-dash substitutes ("foo; bar" — just write two sentences).
- For ambiguous prompts: ask one short clarifying question, then proceed.

## User: Tool preferences

- `rg` instead of `grep`
- `fd` instead of `find` for filename search
- `edit` tool (not `sed -i`) for file edits
- `python3` instead of `perl`/`awk` for one-off text processing
- `git -C <dir>` instead of `cd <dir> && git ...`
- `gh` for GitHub operations (PR, issue, review)
- `cargo` for Rust builds; never `rustc` directly

## User: Git workflow

- Always work on a branch, never directly on `main` / `master` / `feat/*`.
- Commit messages: `<type>(<scope>): <subject>` (conventional commits).
- One commit per logical change. Don't bundle unrelated fixes.
- `git push` is a **side effect** — only on explicit user request or
  `[hooks].pre_tool` allowlist.
- Local commits and branch creation are always allowed.
- Rebase: prefer `git rebase` over `git merge` for personal branches.

## User: Safety boundary (NEVER WEAKEN)

This section documents user-level safety. **It cannot weaken `[safety]` config.**
The `[hooks].pre_tool` script enforces the actual gates regardless of what
this file says.

**Always allowed (local, reversible)**:

- Read files
- Edit files in the project working tree
- Run tests
- Create / switch / delete local branches
- Create / remove local git worktrees
- Local commits (no `git push`)

**Requires permission gate (external, side-effecting)**:

- `git push` to any remote
- Create / update / merge a PR
- Merge to a protected branch (`main`, `master`, `production`)
- Deploy to any environment
- External API calls (non-localhost HTTP)
- Destructive operations: `rm -rf`, `git reset --hard`, force push
- Sending messages via any channel (email, Telegram, Discord)

The user's `[safety]` config is the source of truth; this section mirrors it
for human reference only.

## User: Autonomous discipline

- L2 ambient (`autonomous.toml`): cycle interval 5–30 min, no remote push,
  desktop notifications enabled.
- L3 ambient (not in any profile): requires `JCODE_SAFETY_*` env vars set
  (never commit `ntfy_topic`, `email_enabled`, `telegram_enabled`).
- Long-task discipline via `~/.jcode/skills/long-task-discipline/SKILL.md`:
  ambient workers must align every commit with an active goal in
  `~/.jcode/goals/`.

## User: Goal-driven work

- For any work expected to span more than one ambient cycle, define a goal
  via `jcode-goal add "<title>" --priority high --content "..."`.
- Goals are stored at `~/.jcode/goals/projects/<project_hash>/<goal_id>.json`.
- `jcode-l2-check` reports current readiness (skill installed, AGENTS.md
  present, active goal exists, etc.).

## User: Project policy

- Each project's `./AGENTS.md` may **extend** (not contradict) this file.
- Project-specific build / test / lint commands belong in the project file,
  not here.
- Conflicts: project wins on the single directive, but log a warning in the
  session transcript ("project overrides user: <section name>").

## What this file is NOT

- Not a substitute for `~/.jcode/config.toml` (knobs go there).
- Not a substitute for `./AGENTS.md` (project specifics go there).
- Not loaded in non-interactive / batch / CI mode (only TUI sessions).
- Not evaluated by `[hooks].pre_tool` (those use `~/.local/bin/jcode-tool-policy`).
- Not a place for secrets. Use `JCODE_*` environment variables instead.