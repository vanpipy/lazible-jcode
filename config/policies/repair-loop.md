# Repair Loop Policy

## Where the retry budget actually lives

There is no config field for it. Two independent budgets exist, both owned by
`jcode-orchestrate` and stored per goal in
`~/.jcode/goals/projects/<hash>/<goal>.json`:

| Budget | Default | Behaviour when exceeded |
| --- | --- | --- |
| `step.max_retries` | 3 | step goes `escalated`, human is notified |
| `milestone.review_max_retries` | 3 | milestone goes `escalated`, human is notified |

Set them when the step or milestone is created:

```bash
jcode-goal step <goal-id> <milestone-id> add "<content>" --max-retries 3
jcode-goal milestone <goal-id> add "<title>" --review-max-retries 3
```

The orchestrator owns the counters. `config/skills/long-task-discipline/SKILL.md`
records the outcome but never keeps its own count.

## Escalation signals

When a budget is exhausted the orchestrator emits `step_escalated` or
`milestone_escalated` and prints a `NOTIFY:` line to stderr. The ambient cycle
stops there and waits for the user. Nothing retries past that point.

Recovery is manual and explicit:

```bash
jcode-goal step <goal-id> <milestone-id> add "<content>" --attach-findings "..."
jcode-goal status <goal-id> pending      # re-queue
jcode-goal rm <goal-id>                   # abandon
```

## The DAG's own requeue limit

The jcode Task DAG engine (`jcode-plan/src/dag/ops.rs`) provides
`requeue_failed`. Its retry ceiling lives inside the engine and is **not**
exposed as a config field. `MAX_PLAN_ITEMS = 1024` and
`MAX_SWARM_MEMBERS = 1000` bound the plan size, not the retry count.

Exposing it would mean adding a field to `jcode-config-types` and reading it in
`ops.rs`. That is a jcode source change and does not belong in this repo.

## Interim rule

A single verify or fix step that fails three times escalates to a human. Do
not add workarounds that retry forever.
