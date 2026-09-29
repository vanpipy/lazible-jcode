---
name: orchestrator
description: >-
  Run a single cycle of the Autonomous Coding Control Loop via the
  `/orchestrate` slash command. Use when the user says `/orchestrate`,
  "/orchestrate --dry-run", "/orchestrate --once", or asks to advance
  a goal one step. The skill wraps `jcode-orchestrate` (Python CLI)
  which implements new.md §4; it never reads or writes goal files
  directly.
allowed-tools: bash, read, todo
---

# `/orchestrate` slash command

Advance the Autonomous Coding Control Loop (new.md §4) by one cycle.
The CLI is `~/.local/bin/jcode-orchestrate` (Python, no third-party
deps). This skill is the chat-side wrapper. It dispatches to the
CLI and reports the outcome.

The orchestrator owns the **state machine** (Receive → Schedule →
Execute → Observe → Verify → Review → FinalValidation/Diagnose/
Repair/Escalate). It is **not** a daemon; it advances one transition
per `--once` call. The ambient scheduler (long-task-discipline) calls
it repeatedly.

## Invocation forms

| User says | Action |
| --- | --- |
| `/orchestrate` | Run `jcode-orchestrate --once --cwd $(pwd)`; print actions |
| `/orchestrate --dry-run` | Run with `--dry-run --fake-report '{"verdict":"clean",...}'`; advances state without spawning real workers |
| `/orchestrate --json` | Print machine-readable actions as JSON |
| `/orchestrate loop N` | Run `--once` N times sequentially; stop on first `goal_completed` or `milestone_escalated` |
| `/orchestrate status` | Read all active goals; show their current milestone/step status |

## Defaults and conventions

- **CWD**: pass the current project's cwd so the orchestrator hashes
  to the right `projects/<hash>/` dir. Use `--cwd "$(pwd)"`.
- **Fake report** (dry-run only): default to
  `{"verdict":"clean","findings":[],"confidence":1.0}` so state
  advances end-to-end. Override with `--fake-report` to test failure
  paths (`{"verdict":"findings","findings":[{...}],"confidence":0.8}`).
- **One action per cycle**: a single `--once` call performs at most
  one transition (spawn_coder OR step_done OR spawn_reviewer OR
  review_done). To walk a full goal, call repeatedly.
- **Stop on terminal action**: stop dispatching when the action list
  contains `goal_completed` or `milestone_escalated`.

## What `/orchestrate` does NOT do

- It does not spawn workers itself. It calls `swarm spawn --label
  "coder:<mid>:<sid>"` (or `reviewer:<mid>`) for the active step.
- It does not edit goal files directly. The orchestrator reads/writes
  through its own state mutation, never via `jcode-goal` calls.
- It does not invoke the verifier for steps without `verify_cmd`.
  Such steps complete trivially on `coder_session_id` reaching
  terminal lifecycle.
- It does not auto-trigger PR / HumanGate (safety §13).
- It does not retry forever; review budget is `review_max_retries`
  per milestone (default 3), step budget is `max_retries` per step
  (default 3).

## Procedure

1. Parse the user's invocation (cycle count, dry-run, json).
2. Resolve cwd (default: current shell's pwd).
3. Invoke `jcode-orchestrate` with the parsed args.
4. Print stdout (actions) to the user verbatim. Do not paraphrase
   the JSON. If `--json` was passed, pretty-print the first action
   and the count.
5. If `milestone_escalated` appears, **stop the loop** and prompt
   the user for input. Do not invent a recovery.

## Example output

```
$ /orchestrate --once
goal: goal-1790687169-91bc (Test orchestrator flow)
  → spawn_coder milestone_id=m-0 step_id=m-0-step-0 label=coder:m-0:m-0-step-0 session_id=DRYRUN-m-0-step-0 dry_run=True

$ /orchestrate loop 4
goal: goal-1790687169-91bc (Test orchestrator flow)
  → spawn_coder milestone_id=m-0 step_id=m-0-step-0 label=coder:m-0:m-0-step-0 session_id=DRYRUN-m-0-step-0 dry_run=True
  → step_done step_id=m-0-step-0
  → spawn_coder milestone_id=m-0 step_id=m-0-step-1 label=coder:m-0:m-0-step-1 session_id=DRYRUN-m-0-step-1 dry_run=True
  → step_done step_id=m-0-step-1
  → milestone_in_progress milestone_id=m-0
  → spawn_reviewer milestone_id=m-0 label=reviewer:m-0 session_id=DRYRUN-m-0 dry_run=True
  → review_done milestone_id=m-0 verdict=clean confidence=1.0
  → goal_completed goal_id=goal-1790687169-91bc
```

## Failure modes to surface

- `jcode-orchestrate` not on PATH → tell user to run `./scripts/install`
- `no active goals` → suggest `/goal add "..."` first
- `milestone_escalated` action → pause and ask user (cannot auto-recover)
- `swarm spawn` failure → check `swarm list`; surface stderr

## Layering

`/orchestrate` sits **above** `/goal`:

```
/goal → input channel (jcode-goal add/milestone/step/show/list)
/orchestrate → execution channel (jcode-orchestrate --once)
```

The ambient scheduler (long-task-discipline) calls
`jcode-orchestrate --once` from inside its cycle, never directly
modifying goal files.

## Cross-reference

- new.md §4, Autonomous Coding Control Loop
- new.md §5, Feature Workflow (milestone, review, validate)
- new.md §11, Coder != Reviewer (enforced via label + prompt)
- new.md §13, PR/HumanGate not auto-triggered
- `config/share/jcode-orchestrate/prompts/reviewer.md`, verdict schema
- `config/share/jcode-orchestrate/prompts/coder.md`, step schema
