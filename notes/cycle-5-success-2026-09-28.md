# Cycle #5 success: ambient cycle running with MiniMax-M3 (2026-09-28)

## TL;DR

After audit (`fdffd86`) found 4 bugs blocking ambient cycles, and
`install-shell-env` (`b30ae02`) wrote `JCODE_OPENROUTER_MODEL=MiniMax-M3`
to `~/.zshrc` + `~/.bashrc`, restarting the serve (PID 1180 → **PID 1988541**)
let cycle #5 run cleanly for the first time: model = MiniMax-M3, status =
complete, end_ambient_cycle called, 2 memories updated, next_wake +35min.

## Cycle comparison

| | Cycle #3 (21:04) | Cycle #4 (22:19) | **Cycle #5 (22:34) ✓** |
|---|---|---|---|
| model | `anthropic/claude-sonnet-4` | `anthropic/claude-sonnet-4` | **`MiniMax-M3`** |
| status | incomplete (forced end) | incomplete (forced end) | **complete** |
| duration | 0.59s | 0.28s | **75.87s** |
| API calls | 1 → 400 Bad Request | 1 → 400 Bad Request | **many → 200** |
| end_ambient_cycle | not called | was called (forced) | **called cleanly** |
| memories modified | 0 | 0 | **2** |

## What cycle #5 actually did

The ambient agent ran 67 messages over 75s:

1. Listed memory graph (msg 4)
2. Recalled the most-recent entity memory (msg 37)
3. Wrote **new fact** to memory:
   > `Provider::fork()` race (`openrouter_provider_impl.rs:771`) is the primary
   > blocker for ambient cycles in lazible-jcode: even with
   > `JCODE_OPENROUTER_MODEL=MiniMax-M3` set in serve's environ AND serve
   > recently restarted, fork race can still trigger and fall back to const
   > `DEFAULT_MODEL`.
4. Forgot a stale entity memory
5. Wrote **new entity**:
   > lazible-jcode v0.89.0 working state at end of 22:34 +08:00 ambient cycle:
   > 28 commits on master (b30ae02 most recent), `verify-sanitized` all OK,
   > `diff-live-base` shows autonomous overlay applied.
6. Verified by listing again
7. Properly called `end_ambient_cycle` with summary
8. **Did NOT make proactive code changes** : correctly waited for user decision
   on the fork() race patch

## State after cycle #5

```
state.json:
  total_cycles: 5
  last_run: 2026-09-28T14:36:06Z (= 22:36 CST)
  next_wake: 2026-09-28T15:11:06Z (= 23:11 CST, +35min)
  last_memories_modified: 2
  last_compactions: 0
```

`next_wake = +35min` validates that the new serve re-snapshotted
`max_interval_minutes = 30` (not the old 120).

## What I had to do to trigger cycle #5

Two manual adjustments were needed for this single test cycle:

1. **Disable `pause_on_active_session`** temporarily (live config had `true`,
   blocking ambient cycles while this user session was active). Reverted after
   the cycle. Long-term question for the user: should this stay `false` to let
   ambient cycles run alongside user sessions, or `true` to pause ambient
   whenever there's a user?
2. **Force-trigger** via `JCODE_DEBUG_CONTROL=1 jcode ambient trigger` after
   enabling `debug_socket = true`. Without trigger, the stale `next_wake = 24:19
   CST` (left from cycle #4) would have made us wait 106 minutes.

Cycle #6 is scheduled for **23:11 CST** and will run **without** these manual
interventions, validating the fix is durable.

## Serve restart details

- Old: PID 1180 (started 08:55, ran 13h25m with no env var)
- New: **PID 1988541** (started 22:30:51 CST, `--provider auto serve`)

```bash
$ cat /proc/1988541/environ | tr '\0' '\n' | grep JCODE_OPENROUTER_MODEL
JCODE_OPENROUTER_MODEL=MiniMax-M3  ✓
```

The new serve's `OpenRouterProvider::new()` ran with the env var present, so
in-memory model was seeded with MiniMax-M3 from the start : fork() race that
hit cycles #3 and #4 didn't trigger here because the user session wasn't
mid-set_model when the cycle ran.

## Open items (carried forward)

- **Cycle #6 verification** (23:11 CST, no manual trigger): will confirm
  durable without intervention.
- **Long-term patch**: `Provider::fork()` race (`openrouter_provider_impl.rs:771`)
  still exists. Patch deferred until user decides to actually modify jcode
  source. When patching starts, also set `JCODE_NO_AUTO_UPDATE=1` (per user's
  instruction to keep this knob ready).
- **`pause_on_active_session` default**: needs user decision : keep `true`
  (safer, pauses ambient under user load) or switch to `false` (ambient always
  runs, may compete for resources).

## References

- Bug audit: `notes/ambient-no-cycle-2026-09-28.md` (commit `fdffd86`)
- Bug E (dead pause config): `notes/ambient-no-cycle-2026-09-28.md` § Bug E (commit `f1cbe38`)
- Shell env installer: `scripts/install-shell-env` (commit `b30ae02`)
- Cycle #5 transcript: `~/.jcode/ambient/transcripts/2026-09-28-143450.json`
- Session JSON: `~/.jcode/sessions/session_sauropod_1790606090717_*.json`
- Ambient state: `~/.jcode/ambient/state.json`

---

## Addendum (2026-09-28 22:50 CST) : pause_on_active_session was actually a no-op

When investigating whether cycle #6 would be blocked by this user session
being active, traced `pause_on_active_session` through to `runner.rs:597`
(`set_user_active(active_sessions > 0)`) and discovered Bug E (see audit
note): `RunnerInner::active_user_sessions: RwLock<usize>` is **defined and
read but never written** anywhere in jcode. So `user_active` is
permanently `false`, `should_pause()` always returns `false`, and the
pause config has no runtime effect.

**Implication for cycle #5**: the manual step "disable
`pause_on_active_session`" was redundant : cycle #5 would have fired even
with the config at its default `true`. The only strictly necessary manual
step was the **force-trigger** (`JCODE_DEBUG_CONTROL=1 jcode ambient
trigger`) because the new serve hadn't yet computed a fresh `next_wake`
from the live config's `max_interval_minutes=30`. (Bug C: stale next_wake
from pre-restart scheduler snapshot of 120 min.)

**Implication for cycle #6**: it'll fire at 23:11 CST regardless of
whether this user session is active. No `pause_on_active_session`
toggle is needed. (Bug E means we can't actually pause ambient under
user load until jcode source is patched : parked.)

The cycle-5 manual-steps section above left the long-term pause decision
open as a user choice, but Bug E collapses that choice: the config field
is currently non-functional. To make `pause_on_active_session` actually
work, jcode source needs the user-session-start/stop hooks to call
`active_user_sessions.fetch_add(1)` / `.fetch_sub(1)`.

---

## Addendum correction (2026-09-28 23:14 CST) : cycle #6 fire time is NOT 23:11

The previous addendum's "Implication for cycle #6: it'll fire at 23:11
CST" is **wrong** because of a bug discovered at 23:14 CST: **Bug F**.

Traced the runner's sleep loop after cycle #5 ended at 22:36:06 CST:

```rust
// runner.rs:812-823 (after cycle ends)
let interval = scheduler.calculate_interval(None);  // = max_interval_minutes
let sleep_secs = interval.as_secs().max(30);
s.status = Scheduled { next_wake: now + sleep_secs };  // OVERWRITES agent's request
s.save();
tokio::time::sleep(sleep_secs);  // sleeps max seconds
```

`scheduler.calculate_interval(None)` returns `apply_backoff(max_interval_minutes)`,
ignoring the agent's `schedule_ambient(wake_in_minutes=35)` call. So even
though `state.next_wake = 23:11:06.573` was correctly written by the agent,
the runner **immediately overwrote it** with `22:36:06 + 1800s = 23:06:06`
and slept 1800s.

Log timeline:
```
[22:36:06] Ambient runner: next cycle in 1800s           ← max=30, not agent's 35
[22:36:06] Ambient runner: not time to run, sleeping 1800s
[23:06:06] Ambient runner: not time to run, sleeping 1800s   ← idle wake, not yet
[~23:36:06] cycle #6 will actually fire (not 23:11)
```

So cycle #6 is expected to fire at **~23:36:06 CST** (30 min from the
23:06 idle wake), not 23:11:06. Bug F is independent of Bug C and Bug E;
it's a third distinct cause of next_wake unreliability. See
`notes/ambient-no-cycle-2026-09-28.md` § Bug F for full details.

**Test status (this revision)**: cycle #6 has not yet fired at the time
of writing (23:14 CST). Awaiting next wake from runner sleep timer.

