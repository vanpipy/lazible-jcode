---
name: goal
description: >-
  Create or update a goal in `~/.jcode/goals/` via the `/goal` slash command so
  L2 ambient workers have a defined objective. Use when the user says
  `/goal`, "/goal <title>", "/goal add <title> --priority high --content ...",
  "/goal milestone ...", "/goal step ...", or asks to add a milestone/step to
  an existing goal. The skill wraps `jcode-goal` (Python CLI); it never reads
  or writes goal files directly.
allowed-tools: bash, read, todo
---

# `/goal` slash command

Create or update a goal entry under `~/.jcode/goals/` so the L2 ambient cycle
has something to work on. The CLI is `~/.local/bin/jcode-goal` (Python, no
third-party deps). This skill is the chat-side wrapper — it dispatches to the
CLI and reports the outcome.

## Invocation forms

| User says | Action |
| --- | --- |
| `/goal` | Ask the user interactively for title, scope, priority, content |
| `/goal <title>` | Create with default `--priority medium --scope project` |
| `/goal <title> --priority high --content "..."` | Forward all flags to `jcode-goal add` |
| `/goal list` | Run `jcode-goal list` (default: all scopes/statuses) |
| `/goal list --status active` | Forward list filter |
| `/goal show <goal-id>` | Run `jcode-goal show <goal-id>` |
| `/goal rm <goal-id>` | Run `jcode-goal rm <goal-id>` (refuses without `--yes`) |
| `/goal status <goal-id> active\|paused\|complete` | Run `jcode-goal status` |
| `/goal milestone <goal-id> add "<title>"` | Add a milestone to the goal |
| `/goal step <goal-id> <milestone-id> add "<content>"` | Add a step under a milestone |
| `/goal check` | Run `jcode-goal check --json`; report pass/fail with first failure reason |

## Defaults and conventions

- **Scope**: `project` (writes to `~/.jcode/goals/projects/<hash>/`). Use
  `--scope user` only when the goal spans multiple projects (e.g. "clean up
  `~/.jcode/goals/`").
- **Priority**: default `medium`. Use `high` when the ambient cycle should
  pick this up before any other active goal.
- **Content**: one-line imperative ("Implement X", "Refactor Y to Z"). The
  ambient worker reads this verbatim — vague content yields vague work.
- **Milestones**: optional but recommended for >1 PR of work. Naming: use the
  same slug convention as the worker (e.g. `pr-0`, `pr-a`) so cross-project
  consistency holds.
- **Steps**: action verbs, ≤1 sentence each. Example: "spawn implementer
  worker", "merge --no-ff into main".

## Procedure

1. Parse the user's intent (title, flags, subcommand).
2. Resolve the current project's hash automatically via the CLI (do not
   compute it yourself — `jcode-goal add` already does this from `cwd`).
3. Invoke the CLI with the parsed args. Always print the CLI's stdout/stderr
   back to the user; do not silently swallow errors.
4. After a successful `add`, suggest:
   - Adding milestones (`jcode-goal milestone <id> add "..."`)
   - Running `jcode-l2-check` to confirm the goal unblocks the readiness gate
5. After a `check` invocation, report the JSON output as a one-line summary
   (`ok=true, goal=..., pending=N`).

## What this skill does NOT do

- It does not edit `~/.jcode/goals/*.json` directly. Always go through the
  CLI so the schema (priority, status, hash dir) stays consistent.
- It does not decide whether the goal should be `paused` or `complete` — that
  is the user's call (`/goal status <id> <state>`).
- It does not trigger the ambient cycle manually. The autonomous profile
  picks up active goals on the next 5–30 min window.

## Examples

```
/goal "Implement /goal slash command"
→ ~/.local/bin/jcode-goal add "Implement /goal slash command" --priority high

/goal "Refactor auth module" --priority high --content "Split monolithic auth.go into 4 files"
→ ~/.local/bin/jcode-goal add "Refactor auth module" --priority high --content "..."

/goal milestone goal-1790685230-ec40 add "Wire into install"
→ ~/.local/bin/jcode-goal milestone goal-1790685230-ec40 add "Wire into install"

/goal check
→ ~/.local/bin/jcode-goal check --json
```

## Failure modes to surface

- `jcode-goal` not on PATH → tell the user to run `./scripts/install`
- Goal ID not found → suggest `/goal list` to discover IDs
- `check` returns rc=2 (no pending steps) → suggest adding a milestone/step
- `check` returns rc=1 (no active goal) → suggest `/goal "<title>" --priority high`