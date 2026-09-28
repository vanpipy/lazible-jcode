# jcode-audit-log : post_tool observer hook

The `autonomous` profile enables `[hooks].post_tool`, pointing by default to
`~/.local/bin/jcode-audit-log`. This file describes that hook's semantics and design.

## Purpose

`post_tool` is a jcode **observer** hook (jcode-base/src/hooks.rs marks it as
fire-and-forget) : the script's stdout / exit code **does not** affect jcode behavior;
failures are only recorded in the jcode log and never interrupt tool calls.

We use it for **behavioral auditing**: after each tool call we append a line to
`~/.jcode/audit.log`, recording timestamp / event / tool / status / duration /
output bytes / cwd.

## Environment variables

When jcode calls the hook, it passes metadata via environment variables
(`jcode-base/src/config/env_overrides.rs apply_event_env`):

| Variable | Type | Meaning |
|---|---|---|
| `JCODE_HOOK_EVENT` | string | Event name, currently fixed at `post_tool` |
| `JCODE_HOOK_SESSION_ID` | string | Unique session id |
| `JCODE_HOOK_CWD` | string | Directory where the tool call happened |
| `JCODE_HOOK_TOOL_NAME` | string | Tool name (bash / read / edit / ...) |
| `JCODE_HOOK_STATUS` | string | `ok` / `error` / `denied` |
| `JCODE_HOOK_DURATION_MS` | integer | Tool execution duration (milliseconds) |
| `JCODE_HOOK_OUTPUT_BYTES` | integer | Tool output size in bytes |
| `JCODE_HOOK_PAYLOAD` | string (JSON) | Full event payload |

## Output format

Each line in `audit.log`:

```
[2026-09-28T18:23:44+08:00] event=post_tool tool=bash status=ok duration_ms=8 output_bytes=2396 cwd=/home/leroy/Project/lazible-jcode
```

Field order is fixed for easy `awk` / `cut` processing.

## Installation

Source lives at `scripts/jcode-audit-log` (in this repo). On a new machine:

```bash
cp scripts/jcode-audit-log ~/.local/bin/jcode-audit-log
chmod +x ~/.local/bin/jcode-audit-log
```

`use-profile` writes `hooks.post_tool = ["~/.local/bin/jcode-audit-log"]`;
if the script path isn't in PATH, the hook is still spawned by jcode (jcode
calls `exec` directly), so no explicit registration is needed.

## Privacy note

`audit.log` records each tool's `cwd` (absolute path) plus `output_bytes`
(size only : not content). It **does not** record payload content. If you
want to audit "did a secret leak?", a sudden spike in `output_bytes` is a
rough signal : worth pairing with a simple `awk` monitor.

## Not a gate

`post_tool` cannot act as a permission gate : it is an **observer**, not a
decision maker. For gating, use `pre_tool` + exit code 2 (jcode
`jcode-base/src/hooks.rs`). The L0 hardened profile (the inverse of
`autonomous`) is not yet implemented as a profile here; if needed, write a
base or local override by hand.