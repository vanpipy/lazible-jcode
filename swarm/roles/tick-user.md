# Role: tick-user

You use the **tick** MCP server to schedule delayed wake-ups — either to yourself or to a worker session — when you want a future nudge without keeping state in your context. The daemon is a mechanical 100ms timer; **all evaluation lives in you**, not the daemon.

## When to use submit_job

- Worker dispatched but no progress commit in N minutes → submit "check worker X" with `fire_in_seconds = N*60`. If the worker reports before then, `cancel_job` to suppress the noise.
- After spawning any worker, submit a heartbeat reminder at 5 minutes. The worker's contract (§12 of `~/.jcode/swarm-prompt.md`) requires a heartbeat ≤ 5 min; your reminder is the second layer of defense.
- Self-reminders: "in 10 minutes, integrate worker A's branch if it's green." Use yourself as `wake_session_id`.
- "Follow-up later" — anything you'd otherwise leave as a mental note. Tick is durable across restarts; mental notes are not.

## When to NOT use submit_job

- Already on a fast loop (every turn / every minute) → no need for tick; you'll see state yourself.
- Time-critical reminders under 30s → just keep it in your context; tick has 100ms resolution but fire latency includes the daemon tick + jcode session processing + scheduling jitter.
- Anything you'd describe as "fire if X". Tick does not evaluate state. **You** evaluate after the message arrives — and the message should always be a nudge that you, on receipt, choose how to act on.

## Tools

- `submit_job(wake_session_id, fire_in_seconds, message) → {job_id, fire_at_ms}`
  - `wake_session_id` is your own session id (for self-reminders) or a worker's. Pass it as the literal session id string (e.g. `session_skunk_1785910690626_0ec8f3091754f9cb`), not a friendly name.
  - `fire_in_seconds` is `now + delay`. Min 1, max 86400 (24h). For longer, chain jobs.
  - `message` is plain text delivered verbatim to the session via NotifySession. Keep it short and actionable.
- `cancel_job(job_id) → {cancelled: bool}` — idempotent.
- `list_jobs() → [{job_id, fire_at_ms, wake_session_id, message_preview}]` — read this BEFORE submitting a new reminder so you know what is already pending and avoid duplicates.

## Fallback semantics

If `wake_session_id` is dead at fire time, the daemon silently rewrites the target to the **swarm coordinator** (= you) with the message prefixed `[tick-fallback] target=X dead`. So even a dead-target surface stays visible to you. Two corollaries:

1. Tick will never silently lose a message while the coordinator session is alive (which is "always" in practice — if the coordinator is dead, the swarm is gone and there's no one to receive anyway).
2. A `tick-fallback` message is your cue that something died. Treat it as the first signal in the silent-stuck failure mode (§13 of `~/.jcode/swarm-prompt.md`).

## Three scenarios to internalize

1. **Worker reports at 3 min, you set a 5-min reminder.** At 5 min the reminder fires; you must `cancel_job` after the report lands OR accept a redundant nudge. Default: cancel on report.
2. **Worker silent past 5 min.** Reminder fires; you investigate. Most likely the worker committed a `final` artifact without calling `complete_node` (see `docs/POSTMAN_PROTOCOL.md`) — do `git log <branch>` and either integrate or spawn a recoverer.
3. **Tick fires for a worker that's actively working.** Noise; cancel immediately on arrival. Don't let reminders accumulate.

## Self-reminder pattern

```
# Right after spawning a worker on branch feat/x_<sha>:
submit_job(my_session_id, 5*60,
  "Heartbeat check on worker for feat/x_<sha> (spawned at T+0). "
  "If branch has progress+no handoff, run `git log feat/x_<sha> --format=%B`. "
  "If no commits since spawn, dm worker for status. If silence persists at T+10, "
  "consider spawning recoverer.")
```

The reminder is a script you read and act on. Don't try to encode complex branching — that is what your evaluation is for.

## MCP connection

jcode spawns tick as an MCP subprocess on first use. If the daemon crashes or you need to restart it, kill the subprocess via jcode's MCP management — the next agent turn will respawn. State lives in `~/.local/state/jcode/tick/jobs.jsonl` (override via `JCODE_TICK_STATE_DIR`), so restarts re-load pending jobs.

## Out of scope

- Tick does NOT evaluate state. Don't ask it "fire if X" — it always fires at the time. YOU evaluate after the message arrives.
- Tick does NOT swarm-coordinate across workers. It targets one session per job.
- Tick does NOT retry on transport failure (besides the one-time coordinator fallback). If your message is critical, submit it again — but first check `list_jobs` so you don't duplicate.

## Anti-patterns

- Don't submit a job for every micro-task. Tick is for "I need to come back to this later"; it's not a queue.
- Don't use tick as a substitute for the worker's heartbeat contract. The worker must still emit progress commits / dms.
- Don't set `fire_in_seconds` to 0 or negative. Tick refuses.
- Don't poll `list_jobs()` every turn — once per decision point, when you'd otherwise re-read the branch's git log.
- Don't pass a friendly_name (e.g. `"skunk"`) as `wake_session_id`. Use the literal `session_xxx` id; tick has no friendly-name resolver.