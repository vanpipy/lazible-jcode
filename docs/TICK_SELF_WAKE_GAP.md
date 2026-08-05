<!--
This file documents a protocol gap discovered in the tick MCP self-reminder
path on 2026-08-05. The symptom: `mcp__tick__submit_job(wake_session_id=<my
own session>, fire_in_seconds=N, message=X)` removes the job from the heap
but the message never reaches the target session's input stream. The
runtime silently swallows it.
-->

# tick self-wake silent loss

**TL;DR**: `mcp__tick__submit_job(wake_session_id=<your own session_id>)`
is silently swallowed by the jcode runtime. The daemon fires the job
(removes it from `jobs.jsonl`), but the message never appears as a new
turn. Reproduced twice on 2026-08-05. Workaround: use tick only for
**cross-session** wake-ups (root → worker) or write a durable reminder
into git instead.

## Scope

| | |
|---|---|
| Discovered | 2026-08-05 |
| Repo | `lazible-jcode` at `ffa4e25` |
| Affected component | `tick` MCP `submit_job` |
| Affected invocation | self-target (`wake_session_id` == caller's session_id) |
| Status | daemon-side detection + refusal being added in branch `fix/tick-self-wake-detect_ffa4e25` |

## Empirical reproductions

### Reproduction #1: 10 second self-reminder

| Field | Value |
|---|---|
| `session_id` (target) | `session_scorpion_1785938338978_44006e3129ac7ecd` (caller's own) |
| `fire_in_seconds` | `10` |
| `message` | `"Say hi"` |
| Submitted at | `2026-08-05T14:02:21.527Z UTC` (`job_id=1785938541527-b4be34`) |
| Fires at | `2026-08-05T14:02:31.527Z UTC` |
| User next turn | `2026-08-05T14:03:18.564Z UTC` (a diagnostic question, NOT the payload) |
| Daemon-side outcome | job removed from `jobs.jsonl`; no `[tick-fallback]` prefix |
| Session-side outcome | `"Say hi"` never appears in conversation context |

### Reproduction #2: 30 second self-reminder

| Field | Value |
|---|---|
| `session_id` (target) | `session_scorpion_1785938338978_44006e3129ac7ecd` |
| `fire_in_seconds` | `30` |
| `message` | `"Say hi"` |
| Submitted at | `2026-08-05T14:04:42.953Z UTC` (`job_id=1785938682953-8d3bf9`) |
| Fires at | `2026-08-05T14:05:12.953Z UTC` |
| User next turn | `2026-08-05T14:08:28.605Z UTC` (manual, "bad one") |
| Daemon-side outcome | job removed from `jobs.jsonl`; no `[tick-fallback]` prefix |
| Session-side outcome | `"Say hi"` never appears in conversation context |

Both attempts confirmed the daemon-remove + session-noop pattern. The
30-second test was specifically chosen to rule out "window jitter" as
an explanation; the failure mode reproduces across an order of
magnitude in delay.

## Root cause analysis

### Daemon-side

The `tick` daemon (`tick/internal/notifier/notifier.go`) sends
`NotifySession` over jcode's unix socket. The wire shape is:

```json
{"type":"notify_session","id":N,"session_id":"session_X","message":"..."}
```

The daemon reads one response line; success ⇒ job removed from store.

```go
// tick/main.go:101 (excerpt)
sched := scheduler.New(func(j job.Job) error {
    if err := notif.NotifySession(ctx, j.WakeSessionID, j.Message); err != nil {
        fmt.Fprintf(os.Stderr, "tick: fire %s failed: %v\n", j.ID, err)
        return err
    }
    // Persist: remove from store on successful fire.
    _ = st.Remove(j.ID)
    return nil
})
```

A `{"type":"error"}` response triggers the coordinator-fallback path
(`tick/internal/notifier/notifier.go:124`) which prefixes the message
with `[tick-fallback]`. The two reproductions produced neither:

- No error response (otherwise the job would not have been removed from
  store).
- No `[tick-fallback]` prefix.

The daemon therefore concludes a successful fire — and the upstream
runtime is the only place the message could have been dropped.

### Runtime-side (hypothesis)

jcode's `NotifySession` handler (upstream, in
`crates/jcode-app-core/src/server/socket.rs` — not in this repo) most
likely acks success even when the message won't reach the session.
This would happen if:

- The target session is in "waiting for user input" state.
- The runtime decides there is no turn boundary to interrupt.
- The handler returns a success response, but does not queue the
  message into the session's input stream.

This hypothesis matches the symptom exactly: no error, no fallback,
no delivery. It is consistent with how LLM session loops typically
decide whether an out-of-band notification can land.

### Why cross-session tick works

When the wake target is a worker session (not the coordinator), the
worker is typically mid-task, mid-tool-call, or mid-think — i.e. has
a turn boundary to interrupt. `NotifySession` can intercept that
turn and inject the payload. This shape is reliable and is the
intended primary use case for tick.

## Daemon-side fix

Branch `fix/tick-self-wake-detect_ffa4e25` adds a typed
`notifier.ErrSelfWake`. On entry to `NotifySession`:

1. If `repoPath != ""`, call `coordinator.Lookup(repoPath)` to get the
   coordinator session id.
2. If the lookup succeeds AND the wake target equals the coordinator
   id, return `ErrSelfWake` immediately — no socket I/O.
3. If the lookup errors (no swarm JSON / unreadable), proceed
   normally (fail-safe).
4. If the target differs from the coordinator, proceed normally.

Combined with the existing behavior, this means:

- **Failed self-wakes stay in `jobs.jsonl`** instead of being
  silently removed (since the daemon only `st.Remove(j.ID)` on success).
- **`list_jobs()` reports them indefinitely** as a post-mortem
  warning — visible to anyone checking daemon state.
- **Stderr log shows the reason** for operators tailing the daemon.

Why not a runtime-side fix? The runtime is in upstream jcode's Rust
crates (out of repo scope). A daemon-side refusal is the lowest-effort,
highest-signal mechanism available inside this repo.

## Workarounds (until the fix is integrated)

| Need | Instead of | Do this |
|---|---|---|
| Remind self after N seconds | `submit_job(my_session, N, "...")` | Write the reminder into a file in the working directory, commit it, or just hold it in your context. |
| Soft loop on a worker | `submit_job(my_session, N, "check worker X")` | Use `python3 scripts/swarm-state-monitor.py tick` inline at your next decision point instead. |
| Cross-session reminder (legitimate use) | `submit_job(worker_session, N, "...")` | Keep using this — it's the working path. |

Avoid the canonical "self-reminder pattern" from
`swarm/roles/tick-user.md` §"Self-reminder pattern" — it advertises
the broken path. The fix updates that section.

## Operator checklist

If you suspect you're hitting this:

1. **Confirm via `list_jobs()`** after submit + fire window. If
   submit → fire → empty list but no message arrived, the daemon
   thinks success, but you got nothing.
2. **Check daemon stderr** (`tick mcp` writes to stderr): look for
   `tick: fire <job_id> failed:` lines. Their absence confirms
   "success-without-delivery", which is the silent-self-wake signature.
3. **Verify the target** is your own coordinator id (run
   `swarm list` and compare to your `session_id` from `swarm status`).
4. **Switch workarounds** per the table above.

## Related

- `swarm/roles/tick-user.md` §"When to NOT use submit_job" — updated
  to call out self-wake.
- `tick/README.md` §"Behavior" — added the daemon-side detection
  bullet.
- `tick/internal/notifier/notifier.go` — `ErrSelfWake` definition.
- `tick/internal/notifier/notifier_test.go` — four new test cases
  covering detect / no-fallback / mismatch / lookup-error fail-safe.

## Status

| Date | Change |
|---|---|
| 2026-08-05 | Gap discovered, two reproductions captured. |
| 2026-08-05 | `docs/TICK_SELF_WAKE_GAP.md` written (this file). |
| 2026-08-05 | `fix/tick-self-wake-detect_ffa4e25` branch opened by implementer worker; pending integration into main. |
