# Repair Loop Policy (v1)

## Current state

The jcode Task DAG engine (`jcode-plan/src/dag/ops.rs`) provides `requeue_failed`,
but the retry upper bound **is not exposed as a configuration field** : it is controlled inside the engine.

## Our discipline

- A single verify / fix node that fails more than 3 times → escalate to a human
- Escalation signals:
  - Insert `Escalating after N retries` notice in the transcript
  - The `[hooks].post_tool` hook records every failure
  - On the 3rd failure, notify a human via `[safety].ntfy` / email

## Interim workaround

- The `jcode-tool-policy` script (pre_tool hook) intercepts the repeated-failure pattern of `delegate_task`
- It maintains a per-session retry counter, stored at `~/.jcode/state/retry-counter/<session>.json`
- When the threshold is exceeded, it forces exit 2 (refuse the retry)

## Long-term direction

- The jcode engine exposes a `MAX_DAG_REQUEUE` configuration field
- This repo will add it to `config/profiles/autonomous.toml`
- Until then, use the interim workaround above