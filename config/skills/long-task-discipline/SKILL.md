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

If `active_goal` exists, read its JSON, identify the highest-priority pending
milestone, and constrain all work to that milestone's steps.

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
{"ts":"<ISO8601>","cycle_id":"<N>","goal_id":"<id>","milestone_id":"<id>","action":"<verb>","outcome":"<pass|fail|skip|reject>","duration_s":<N>}
```

This log is the **audit trail** for what the agent tried. Future cycles read
the last 5 lines before starting to avoid repeating failed approaches.

### 4. Cycle budget

- Max **3 worker dispatches** per cycle
- Max **5 minutes** wall-clock per cycle
- If budget is exhausted mid-milestone:
  - Mark the in-progress step as `"status": "paused"` (NOT `"pending"`)
  - Do NOT mark it `"completed"` (work was not finished)
  - Append to history.jsonl with `outcome: "budget_exhausted"`

### 5. Failure escalation

Track per-milestone failure count in a sibling file:
`~/.jcode/goals/projects/<hash>/failure_counts.json`:

```json
{"<milestone_id>": <N>}
```

Increment on each `outcome: "fail"`. When a milestone's count reaches 3:

1. Set `milestone.status = "needs_decision"`
2. Write `last_summary`: `cycle N: milestone <id> escalated after 3 failures — HUMAN INPUT NEEDED: <reason>`
3. Do NOT queue another cycle for this milestone
4. **Wait** for the user to either: (a) revise the milestone, (b) abandon the goal, or (c) reset the failure count

## Anti-patterns (NEVER do)

- ❌ Worker invents its own goal not in `~/.jcode/goals/`
- ❌ Worker modifies files outside the project root (use `git rev-parse --show-toplevel` to verify)
- ❌ Worker bypasses the commit alignment check (Rule 2)
- ❌ Worker writes directly to `~/Project/patched-jcode/crates/...` — that path goes through `./scripts/install` only
- ❌ Worker escalates after only 1 failure (must wait for 3)
- ❌ Worker continues past `needs_decision` without user input
- ❌ Worker modifies `~/.jcode/goals/projects/<hash>/*.json` directly — use `jcode-goal` CLI

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