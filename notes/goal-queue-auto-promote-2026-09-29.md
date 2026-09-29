# Goal queue + auto-promote: design + before/after (2026-09-29)

## Problem statement

Before this change, the orchestrator's `advance_goal()` set
`goal.status = "complete"` when a goal finished. Once a goal completed,
the project's goal directory contained **zero active goals**, so
`load_active_goals()` returned `[]` on every subsequent cycle and the
L2 ambient loop spun idly:

```text
active goal A in_progress  →  done  →  goal_completed  →  A.status=complete
                                                       →  queue empty
                                                       →  next cycle: "no active goals"
```

The user observed that *"active goal 应该是动态运行 维持的状态"* — an active
goal is a runtime state the system maintains, not a static file the user
must refresh after every completion. This note captures the design that
turns the goal set into a dynamic queue.

## Solution: queue + auto-promote

Goals now have a `pending` status (added to `VALID_STATUSES`) that
represents *"queued behind the current active goal"*. When the active
goal completes, the orchestrator automatically promotes the
highest-priority pending goal in the same project to `active`.

### Status lifecycle

| Status | Meaning | Auto-transition |
|--------|---------|-----------------|
| `pending` | queued behind active; eligible for auto-promote | → `active` on goal_completed |
| `active` | orchestrator driving this goal (one per project) | → `complete` when all milestones done |
| `paused` | user-paused; never auto-promoted | manual only |
| `complete` | terminal | — |
| `abandoned` | terminal | — |
| `needs_decision` | terminal (for now) | — |

### Queue semantics

Both `jcode-goal` and `jcode-orchestrate` share one queue ordering:
`priority` rank (high < medium < low) → `created_at` (oldest first).

| Operation | Behavior |
|-----------|----------|
| `jcode-goal add <title>` (queue empty) | creates as `active` (auto-promoted) |
| `jcode-goal add <title>` (queue occupied) | creates as `pending` |
| `jcode-goal queue` | shows the queue head (next to be promoted) |
| `jcode-goal queue --promote` | manually shift head to `active` (only if no current active) |
| `jcode-goal status <id> pending` | re-queue a paused/abandoned goal |
| orchestrator `goal_completed` | auto-promote queue head to `active`; emit `goal_promoted` action |

### Why `pending` and not `paused`

`paused` carries user intent (they paused it). Auto-resuming a paused
goal would override that intent. `pending` is the new neutral queue
state — explicitly authored goals that have not yet been promoted.

## Implementation

| File | Change |
|------|--------|
| `config/bin/jcode-goal` | `VALID_STATUSES += {"pending"}`; `QUEUE_STATUSES` / `TERMINAL_STATUSES` exports; `cmd_add` queue-aware (pending unless queue empty → active); `cmd_queue` new subcommand |
| `config/bin/jcode-orchestrate` | `_peek_queue_head(goal_path)` finds highest-priority pending in same project dir; `advance_goal()` Phase E auto-promotes after `goal_completed` and emits `goal_promoted` action; `cmd_loop` `stopped_reason` is now `queue_empty` / `goal_completed` / `milestone_escalated` / `exhausted` |
| `config/bin/_test_orchestrator.py` | T13: setup_repo_with_pending helper + 3 assertions (pending on add, complete on active, auto-promote on completion) |
| `config/bin/_test_integration.py` | I8: 3-goal queue chain via `--loop 30` — all reach `complete`, `stopped_reason=queue_empty` |

## Before / after

### Before

```bash
$ jcode-goal add "A" --priority high
created ~/.jcode/goals/projects/<hash>/goal-...json
  status: active

$ jcode-goal add "B" --priority medium
created ~/.jcode/goals/projects/<hash>/goal-...json
  status: active              # <-- BUG: two concurrent actives

$ # drive A to completion
$ jcode-orchestrate --once
... goal_completed ...

$ jcode-goal list --status active
(no goals with status=active)   # <-- queue silently drains to empty
$ jcode-l2-check
... [5] no active goal ...     # <-- silently broken
```

### After

```bash
$ jcode-goal add "A" --priority high
created ~/.jcode/goals/projects/<hash>/goal-A.json
  status: active (auto-promoted; queue was empty)

$ jcode-goal add "B" --priority medium
created ~/.jcode/goals/projects/<hash>/goal-B.json
  status: pending (queued behind active goal)   # <-- correct queueing

$ jcode-goal queue
queue head: goal-B (...)

$ # drive A to completion
$ jcode-orchestrate --once
... goal_completed ... goal_promoted goal_id=goal-B ...

$ jcode-goal list --status active
ID       STATUS  PRI  TITLE
goal-B   active  med  B           # <-- B is now active
$ jcode-l2-check
... [5] active goal exists for current project ✓
```

## Behavioral changes worth noting

1. **`cmd_loop --loop N` now chains across the queue.** When a goal
   completes, the next iteration's `load_active_goals()` picks up the
   promoted goal, so a single `--loop 30` invocation drives all queued
   goals. `stopped_reason` is `queue_empty` once the queue drains.
2. **I6 test expectation changed** from `stopped_reason="terminal_action"`
   to `stopped_reason="queue_empty"`. With one goal, after auto-promote
   the queue is empty, which is a more accurate stop reason than the
   old catch-all `terminal_action`.
3. **`jcode-goal add` UX is preserved** for the common case (no active
   goal → first add still becomes active immediately), so no migration
   is needed for existing goal files.

## What this does NOT do

- It does **not** auto-create goals. The L2 ambient scheduler still
  needs the user (or an external signal) to seed the queue.
- It does **not** auto-promote `paused` goals. Pausing is user intent;
  resuming must be explicit (`jcode-goal status <id> pending`).
- It does **not** cross projects. Each project's queue is local; a
  pending goal in project X is invisible to project Y.
