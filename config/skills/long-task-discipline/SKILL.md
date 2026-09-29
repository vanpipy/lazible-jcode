# Long-Task Discipline

> Goal-driven constraint for L2 ambient workers.
> Loaded by jcode at session start when ambient is enabled
> (see `~/.jcode/skills/` resolution order in `crates/jcode-base/src/skill.rs`).

## Purpose

Constrain L2 ambient workers to operate against a defined goal in
`~/.jcode/goals/` rather than free-form exploration. Without this discipline,
ambient cycles drift into "check-in + queue maintenance" mode (observed in
cycle #12 `last_summary`: "post-squash routine check-in" with no user-driven
output). This skill forces every cycle to advance a concrete milestone.

## Loop ownership (NEW: orchestrator is the loop)

The Autonomous Coding Control Loop (new.md §4) is owned by
`jcode-orchestrate --once` (NOT by this skill). This skill's job is
**dispatch + cycle bookkeeping**, not step execution:

1. Decide which goal to advance (this skill)
2. Call `jcode-orchestrate --once --cwd $(pwd)` to perform ONE transition
3. Read its action list (spawn_coder | step_done | spawn_reviewer |
   review_done | milestone_escalated | goal_completed)
4. Record to history.jsonl (this skill)
5. Schedule next ambient wake (this skill)

The orchestrator owns Phase A–D (step advance, milestone close, reviewer
verdict, goal completion). This skill does NOT manually advance steps,
spawn workers, parse verdicts, or maintain per-step state. Hand-rolling
any of that duplicates the orchestrator and bypasses its review gate.

## Rules

### 1. Goal lookup (must do first thing each cycle)

```bash
# Compute current project's hash (16 hex chars of sha256 of repo root)
project_root=$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")
project_hash=$(printf '%s' "$project_root" | sha256sum | cut -c1-16)

# Look up active goals for this project
active_goal=$(jq -s -r '[.[] | select(.status == "active")] | sort_by(.priority) | .[0].id // empty' \
    ~/.jcode/goals/projects/$project_hash/*.json 2>/dev/null)
```

If `active_goal` is empty:

1. Write a `last_summary` line: `no active goal for project <hash>; run 'jcode-goal add "..."'`
2. **Stop.** Do not invent a goal. Do not free-form explore. Cycle exits with no worker dispatch.

If `active_goal` exists, proceed to Rule 1.5 (delegate to orchestrator).

### 1.5. Cycle body: delegate to jcode-orchestrate

```bash
# Run ONE transition. Orchestrator handles phase A-D internally.
output=$(jcode-orchestrate --once --cwd "$project_root" 2>&1)
echo "$output"

# Parse actions for history.jsonl and stop conditions
actions=$(echo "$output" | grep -E '^\s+→ ' | sed 's/^\s*→\s*//')
echo "$actions" | head -1 > ~/.jcode/goals/projects/$project_hash/last_action
```

If `output` contains `goal_completed` or `milestone_escalated`:

- `milestone_escalated` → write `last_summary` with
  `cycle N: milestone <id> ESCALATED, HUMAN INPUT NEEDED`
  and **stop** the loop (do not queue another cycle).
- `goal_completed` → write `last_summary` with
  `cycle N: goal <id> completed` and continue to next goal.

Otherwise the cycle exits normally; the next ambient wake (5–30 min)
will call `--once` again.

### 2. Commit alignment (pre-commit gate)

Before any commit on an `ambient/*` branch:

- Diff the working tree against `HEAD`
- For each modified file, identify which milestone step it advances
- If the diff does not advance **any** pending step of the active goal:
  - **Revert** the changes (`git checkout -- .`)
  - Append a record to `~/.jcode/goals/projects/<hash>/history.jsonl`:
    `{"ts":..., "cycle_id":..., "action":"reject_off_goal", "files":..., "reason":"diff does not advance any pending milestone"}`
  - Write `last_summary`: `cycle N: rejected off-goal commit (X files modified, no milestone match)`

### 3. History append (every cycle)

At the end of every cycle, append one line to `~/.jcode/goals/projects/<hash>/history.jsonl`:

```json
{"ts":"<ISO8601>","cycle_id":"<N>","goal_id":"<id>","milestone_id":"<id>","action":"<verb>","outcome":"<pass|fail|skip|reject|escalated>","duration_s":<N>}
```

The `action` field is the first orchestrator action (e.g. `spawn_coder`,
`step_done`, `review_failed`, `goal_completed`). `outcome` maps:

| Orchestrator action | outcome |
| --- | --- |
| `step_done`, `review_done` (verdict=clean) | `pass` |
| `step_failed`, `step_escalated`, `review_failed` | `fail` |
| `milestone_escalated` | `escalated` |
| `spawn_coder`, `spawn_reviewer` | (in_progress; outcome=skip on next cycle) |
| `goal_completed` | `pass` |

### 4. Cycle budget

- Max **3 worker dispatches** per cycle (each `--once` call = 1 dispatch)
- Max **5 minutes** wall-clock per cycle
- If budget is exhausted mid-milestone:
  - Do NOT mark anything (orchestrator owns state). Just exit.
  - Append to history.jsonl with `outcome: "budget_exhausted"`
  - Next ambient wake will resume

### 5. Failure escalation

The orchestrator owns the per-milestone retry counters
(`review_retry_count`, `review_max_retries`, `step.retry_count`,
`step.max_retries`). This skill does NOT maintain separate counters.

When the orchestrator emits `milestone_escalated`:

1. Write `last_summary`: `cycle N: milestone <id> escalated, HUMAN INPUT NEEDED: <reason>`
2. Do NOT queue another cycle for this milestone
3. **Wait** for the user to either: (a) revise the milestone via
   `jcode-goal step <gid> <mid> add <content> --attach-findings "..."`,
   (b) reset via `jcode-goal milestone <gid> reset <mid>`, or
   (c) abandon via `jcode-goal rm <gid>`

## Anti-patterns (NEVER do)

- ❌ Worker invents its own goal not in `~/.jcode/goals/`
- ❌ Worker modifies files outside the project root (use `git rev-parse --show-toplevel` to verify)
- ❌ Worker bypasses the commit alignment check (Rule 2)
- ❌ Worker writes directly to `~/Project/patched-jcode/crates/...`. That path goes through `./scripts/install` only.
- ❌ Worker **manually advances steps / spawns workers / parses verdicts**.
   That is the orchestrator's job (Rule 1.5). Always call
   `jcode-orchestrate --once`.
- ❌ Worker continues past `milestone_escalated` without user input.
- ❌ Worker modifies `~/.jcode/goals/projects/<hash>/*.json` directly. Use `jcode-goal` CLI.

## Layering (in order of authority)

```
[ambient] config          → when to wake, how often
[safety] config           → what side effects are forbidden (NEVER weakened)
~/AGENTS.md               → user preferences (working style, communication)
./AGENTS.md               → project specifics (may override user sections)
~/.jcode/skills/...       → domain-specific constraints
  └── long-task-discipline (THIS)  → goal discipline (last word on "what to work on")
```

This skill does not weaken safety; it does not override AGENTS.md; it
constrains **what** to work on, given that the context already specifies **how**
and **why**.

## Relationship with the validation pipeline (new.md §10)

Each milestone step in a goal maps to one or more DAG nodes:

```
milestone step → DAG NodeSpec (kind: Implement | Verify | Fix)
             → Verify gate runs after each implement
             → on gate FAIL → inject_from_gate → Fix node → re-verify
             → on milestone complete → next milestone's first step
```

The repair loop (Rule 5) wraps the DAG's `requeue_failed` (ops.rs:547) with a
per-milestone counter. Without this skill, the DAG can requeue_failed forever;
with this skill, after 3 failures the cycle escalates to the user.