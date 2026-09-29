# ~/AGENTS.md — User-Level Global Instructions

> Loaded by jcode at session start via `load_agents_md_files_from_dirs`
> (jcode-base `src/prompt.rs:949`). Load order: project `./AGENTS.md`
> first, then this file appended. Later same-section headings win
> ("specifics override generals").
>
> Installed by `./scripts/install` only when `~/AGENTS.md` does not
> exist. Install never overwrites user edits. To regenerate:
> `rm ~/AGENTS.md && ./scripts/install`.

## How projects should layer on top

Use the prefix convention so conflicts are traceable.

| Prefix | Where it belongs | Wins on conflict |
| ------ | ---------------- | ---------------- |
| `## User: <topic>` | this file (user-level) | project override |
| `## User: <topic> (override)` | project file | wins |
| `## Project: <topic>` | project file | always |

Example: `## User: Working style (override)` in `<project>/AGENTS.md`
overrides the matching section here.

---

## User: Working style

- Commit before `./scripts/install`. It never auto-commits.
- Use `rg` / `fd` / the `edit` tool. Never `grep -r` / `find` / `sed -i`.
- Use `python3` (stdlib only) for config manipulation.
- Prefer **shell + python** over one-off rust for system maintenance.
- Terse output. Tables over paragraphs. Bullets over prose.

## User: Communication

- Chinese when the user writes in Chinese. English in code, comments, commit messages.
- Never use em dashes (`—`). Use periods, commas, or line breaks instead.
- Never use semicolons as em-dash substitutes. Write two sentences instead.
- For ambiguous prompts: ask one short clarifying question, then proceed.

## User: Tool preferences

- `rg` not `grep`. `fd` not `find`.
- `edit` tool, not `sed -i` or in-shell perl/awk.
- `git -C <dir>` instead of `cd <dir> && git ...`.
- `gh` for GitHub (PR, issue, review).
- `cargo` for Rust builds. Never `rustc` directly.

## User: Git workflow

- Always on a branch. Never directly on `main` / `master` / `feat/*`.
- Commit messages: `<type>(<scope>): <subject>` (conventional commits).
- One commit per logical change. Don't bundle unrelated fixes.
- Local commits and branch creation are always allowed.
- `git push` is a side effect. Only on explicit user request or
  `[hooks].pre_tool` allowlist.
- Prefer `git rebase` over `git merge` for personal branches.

## User: Safety boundary (NEVER WEAKEN)

`[hooks].pre_tool` enforces these regardless of what this file says.

**Always allowed**: read files, edit project working tree, run tests,
create/switch/delete local branches and worktrees, local commits.

**Permission gate required**: `git push`, PR create/update/merge, merge
to protected branch (`main` / `master` / `production`), deploy,
non-localhost HTTP, destructive ops (`rm -rf`, `git reset --hard`, force
push), sending messages via any channel.

## User: Autonomous discipline

- L2 ambient (`autonomous.toml`): cycle interval 5 to 30 min, no remote
  push, desktop notifications enabled.
- L3 ambient: requires `JCODE_SAFETY_*` env vars set. Never commit
  `ntfy_topic`, `email_enabled`, `telegram_enabled`.
- Long-task discipline: ambient workers must align every commit with an
  active goal in `~/.jcode/goals/` (see long-task-discipline skill).

## User: Goal-driven work

- For work spanning more than one ambient cycle, define a goal via
  `jcode-goal add "<title>" --priority high --content "..."`.
- Goals live at `~/.jcode/goals/projects/<project_hash>/<goal_id>.json`.
- `jcode-l2-check` reports readiness (skill, AGENTS.md, active goal).
- Autonomous Coding Control Loop (new.md §4) is owned by
  `jcode-orchestrate --once`. Ambient scheduler invokes it. It is not
  a daemon. Manual advance: `cd <project> && /orchestrate loop 10`.

## User: Coder != Reviewer (new.md §11)

Orchestrator spawns two distinct worker roles per milestone. Never the
same session.

| Role | Label | Prompt |
| --- | --- | --- |
| Coder | `coder:<mid>:<sid>` | `~/.local/share/jcode-orchestrate/prompts/coder.md` |
| Reviewer | `reviewer:<mid>` | `~/.local/share/jcode-orchestrate/prompts/reviewer.md` |

**Enforcement**: distinct `session_id` (`SwarmMemberRecord`), distinct
label prefix, reviewer prompt forbids code modification ("Do not modify
code. Report only."). Verdict is a JSON object: `verdict` (`clean` /
`findings`), `findings[]` (`step_id`, `severity`, `location`, `issue`),
`confidence` (0.0 to 1.0). Parse failure = conservative default
(findings + 0.0 confidence).

**On `verdict=findings`**: orchestrator increments `review_retry_count`.
A finding with a matching `step_id` resets only that step. A general
finding (no `step_id`) resets the whole milestone. If
`review_retry_count >= review_max_retries` (default 3), milestone is
`escalated` and the cycle stops. Ambient scheduler waits for human input.

**Never bypass the review gate to ship faster.** The reviewer is the
quality boundary.

## User: Project policy

- Each project's `./AGENTS.md` may extend (not contradict) this file.
- Project-specific build / test / lint commands belong in the project file.
- Conflicts: project wins on the single directive, but log a warning in
  the session transcript ("project overrides user: <section name>").

## What this file is NOT

- Not a substitute for `~/.jcode/config.toml` (knobs go there).
- Not a substitute for `./AGENTS.md` (project specifics go there).
- Not loaded in non-interactive / batch / CI mode (TUI only).
- Not evaluated by `[hooks].pre_tool` (that is `jcode-tool-policy`).
- Not a place for secrets. Use `JCODE_*` environment variables instead.
