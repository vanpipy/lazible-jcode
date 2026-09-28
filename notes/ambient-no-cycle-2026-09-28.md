# Audit: Why 21:00-22:00 saw no autonomous tasks (2026-09-28)

## Conclusion (TL;DR)

The ambient runner triggered cycle #3 (headless) at 21:04:01 CST, but the API call
**returned 400 Bad Request immediately because of a wrong model name** (forced end within 0.5s). After the cycle,
`next_wake` was computed as +2 hours (23:04 CST), because the scheduler captured the old
`max_interval_minutes=120` config at startup, and the runtime-reloaded `max=30` never took effect.
So in the entire 21:04 → 22:00 window, there was only one 0.5s ineffective cycle that did no work.

## What actually ran

| Time | Event |
|---|---|
| 21:04:01.117 | Ambient runner: starting ambient cycle |
| 21:04:01.302 | API call starting: 2 messages, 34 tools |
| 21:04:01.310 | **API stream attempt 1/8, model=`anthropic/claude-sonnet-4`, endpoint=`https://api.minimaxi.com/v1/chat/completions`, auth=`MINIMAX_API_KEY`** |
| 21:04:01.583 | HTTP connection established in 272ms (**status=400 Bad Request**) |
| 21:04:01.585 | agent error without calling end_ambient_cycle |
| 21:04:01.593 | sending continuation message |
| 21:04:01.718 | **forced end after 2 attempts** |
| 21:04:01.734 | cycle complete: **0 memories modified, 0 compactions** |
| 21:04:01.769 | **next cycle in 7200s** (= 2 hours) |
| 21:04 ~ 22:00 | runner wakes every 30s, repeating "not time to run, sleeping 30s" |

## Root cause (chain)

### Bug A: ambient cycle used the wrong model name

`~/.jcode/sessions/session_boar_1790600641203_a6718e082b4de60c.json` (the ambient session created by cycle #3) shows:

```json
{
    "provider_key": "minimax",
    "model": "anthropic/claude-sonnet-4",
    "working_dir": "/home/leroy/Project/agentic-with-pi",
}
```

`provider_key=minimax` is correct (OpenRouter bridged via env var to MiniMax), but
`model=anthropic/claude-sonnet-4` is wrong : this is OpenRouter's hardcoded
default model.

**Mechanism**: `Provider::fork()` (`openrouter_provider_impl.rs:771`) uses
`try_read()` to read the shared provider's `model: Arc<RwLock<Option<String>>>`. If
the read/write lock is held by the user session (even briefly), `try_read()` fails → `unwrap_or_default()` is used → for `Option<String>` that's `None` → at
`lib.rs:1307` / `lib.rs:1541` / `lib.rs:1660` all three sites have
`.unwrap_or_else(|| DEFAULT_MODEL.to_string())`, with `DEFAULT_MODEL` in
`lib.rs:64` being `"anthropic/claude-sonnet-4"`.

```rust
// openrouter_provider_impl.rs:771
fn fork(&self) -> Arc<dyn Provider> {
    Arc::new(Self {
        ...
        model: Arc::new(RwLock::new(
            self.model.try_read().map(|m| m.clone()).unwrap_or_default(),
        )),
        ...
    })
}
```

```rust
// lib.rs:64
const DEFAULT_MODEL: &str = "anthropic/claude-sonnet-4";
```

### Bug B: MiniMax API does not recognize `anthropic/claude-sonnet-4`

The endpoint is `https://api.minimaxi.com/v1/chat/completions` (OpenAI-compatible
path). MiniMax only recognizes its own model names (`MiniMax-M3`, `MiniMax-M2.7`, etc.), not
`anthropic/claude-sonnet-4`-style cross-vendor names. Returns 400 Bad Request.

Evidence:
```
[2026-09-28 21:04:01.310] API stream attempt 1/8 over HTTPS transport
    (model: anthropic/claude-sonnet-4, endpoint: https://api.minimaxi.com/v1, auth: MINIMAX_API_KEY)
[2026-09-28 21:04:01.583] HTTP connection established in 272ms (status=400 Bad Request)
```

### Bug C: scheduler did not reload `max_interval_minutes=30`

After cycle #3 completed, the runner called `scheduler.calculate_interval(None)` to compute the next sleep.
`AdaptiveScheduler` snapshotted `config().ambient` once at `run_loop` startup
(`runner.rs:575-583`), and never re-reads it. So `max` used the old value of 120 min,
**2 hours = 7200s**:

```rust
// runner.rs:820 (next_wake setter)
let interval = scheduler.calculate_interval(None);
let sleep_secs = interval.as_secs().max(30);   // 7200
s.status = AmbientStatus::Scheduled {
    next_wake: Utc::now() + chrono::Duration::seconds(sleep_secs as i64),
    // → next_wake = 21:04:01 + 7200s = 23:04:01
};
```

`runner.rs:813` log confirms:
```
[2026-09-28 21:04:01.769] Ambient runner: next cycle in 7200s
```

The reloaded `max_interval_minutes=30` (in live config) will never be seen by this
scheduler process.

### Bug D (minor): trigger does not actually force a cycle

I manually ran `JCODE_DEBUG_CONTROL=1 jcode ambient trigger`, the runner was nudged awake:
```
[2026-09-28 14:01:54.986] Ambient runner: nudged awake
[2026-09-28 14:01:54.986] Ambient runner: not time to run, sleeping 30s
```

`trigger()` (`runner.rs:131-141`) only updates the runner's in-memory `state.status`
to `Idle`, but `should_run` reads from `AmbientManager::new()` (re-loaded from disk) → disk state is still `Scheduled` (trigger doesn't update disk) → false.

So `jcode ambient trigger` in the current jcode version cannot force an immediate cycle. To make it actually run:
1. First modify disk `~/.jcode/ambient/state.json` to `{"status": "Idle"}`
2. Then trigger

I tried both (see console output), but the state.json edits didn't take effect immediately : the loop probably persisted next_wake=15:04 again in the instant I was editing.

## Can autonomous.toml fix this?

**Not currently.** Because `runner.rs:575-583` only reads from ambient:
```rust
ambient_scheduler_config = AmbientSchedulerConfig {
    min_interval_minutes: amb_config.min_interval_minutes,
    max_interval_minutes: amb_config.max_interval_minutes,
    pause_on_active_session: amb_config.pause_on_active_session,
    ..Default::default()
};
```

It **does not read** `amb_config.provider` / `amb_config.model` (although
`AmbientConfig` has those two fields, and env can also override them via
`env_overrides.rs:562-565`). So even if autonomous.toml adds
`[ambient] provider="minimax" model="MiniMax-M3"`, the ambient runner will not pick it up.

This means: **ambient cycle necessarily inherits the serve main provider's current model**,
and that, via the fork() race, can easily land on DEFAULT_MODEL.

## Immediate fixes (sorted by cost, low → high)

### Fix 1: Set initial model via environment variable (no jcode change)

```bash
export JCODE_OPENROUTER_MODEL=MiniMax-M3
```

This way the provider is initialized with MiniMax-M3, **and subsequent forks won't fall back to DEFAULT_MODEL**
(unless the user session actively calls `set_model` to switch back). env var is read at `lib.rs:1285`.

**Limitation**: if the user session switches models mid-stream and then switches back, the ambient fork can still land on DEFAULT_MODEL.

### Fix 2: Restart serve (no jcode change)

`kill <serve_pid>` and let systemd / launcher restart serve. After restart:
- Provider initializes its model from the env var (if `JCODE_OPENROUTER_MODEL` is set)
- Scheduler snapshots `max_interval_minutes` = new value 30
- next_wake computed as +30 min instead of +2h

**Cost**: all active sessions are interrupted, but ambient state is persisted.

### Fix 3: Patch runner.rs to read ambient.provider/model

Patch `runner.rs:572-583` to also read ambient.provider/model, and at the start of `run_cycle_direct` call `provider.set_model(ambient.model?)`. This is the root fix, but requires modifying jcode source.

### Fix 4: Document serve restart in autonomous.toml comment

No patch. In the comments of autonomous.toml, write:
> "after applying this profile, you MUST restart `jcode serve` (kill the old serve) so the ambient scheduler re-snapshots max_interval_minutes and so the new provider uses the model from the env var"

i.e. make "must restart serve" an explicit step in the profile.

## My recommended steps (per user expectation)

If the user wants to see "cycles actually running between 21:00-22:00" right away:

1. **Write `notes/ambient-no-cycle-2026-09-28.md`**: preserve this audit (already done)
2. **Modify autonomous.toml**: in the comment, document the need to restart serve
3. **Temporarily set `JCODE_OPENROUTER_MODEL=MiniMax-M3`** in shell rc
4. **kill serve to let systemd restart it** (or manually restart)

Awaiting user decision.

## Source-code references

- `runner.rs:64`: `const DEFAULT_MODEL: &str = "anthropic/claude-sonnet-4";`
- `runner.rs:131-141`: `trigger()` updates in-memory state
- `runner.rs:575-583`: scheduler snapshots config once
- `runner.rs:813-820`: post-cycle next_wake uses the scheduler's stale `max`
- `openrouter_provider_impl.rs:771`: `fork()` uses `try_read` to grab model
- `lib.rs:1307/1541/1660`: fallback to DEFAULT_MODEL when model is None
- `env_overrides.rs:562-565`: `JCODE_AMBIENT_PROVIDER` / `JCODE_AMBIENT_MODEL`
  only write to config fields; runner doesn't read them
- `manager.rs:36-50`: `should_run()` reads disk state (not in-memory)

---

## Bug E (added 2026-09-28 22:37 CST): `pause_on_active_session` is dead config

The field `active_user_sessions: RwLock<usize>` is defined at `runner.rs:53`, with the comment
"Number of active user sessions (for pause logic)", initialized to 0 (`runner.rs:71`).

**No code in the whole codebase ever writes to it**:
```bash
$ grep -rn "active_user_sessions\." ~/Project/patched-jcode/ --include='*.rs'
crates/jcode-app-core/src/ambient/runner.rs:177:        let active_sessions = *self.inner.active_user_sessions.read().await;  // READ
crates/jcode-app-core/src/ambient/runner.rs:272:        "active_user_sessions": active_sessions,                              // JSON output
crates/jcode-app-core/src/ambient/runner.rs:596:        let active_sessions = *self.inner.active_user_sessions.read().await;  // READ
crates/jcode-app-core/src/ambient/runner.rs:871:        let active_sessions = *self.inner.active_user_sessions.read().await;  // READ
# (no .write calls)
```

`should_pause()` in `scheduler.rs:251`:
```rust
self.config.pause_on_active_session && self.user_active
```

And `user_active` is inferred by `runner.rs:597`'s `scheduler.set_user_active(active_sessions > 0)` : since `active_user_sessions` is always 0, `user_active` is always `false`,
`should_pause()` always returns `false`.

**Practical consequences**:
- Regardless of `pause_on_active_session = true` or `false`, ambient cycles fire on `next_wake`, **completely ignoring whether the user is present**
- When the user is online and ambient interrupts them, they "assume the cycle should pause but it actually ran"
- User sets `pause_on_active_session = false` to force a run → same as before

**Minimal fix** (jcode source patch, not done):
```rust
// When App starts a user session
runner.handle.active_user_sessions.fetch_add(1, ...);
// When App closes a user session
runner.handle.active_user_sessions.fetch_sub(1, ...);
```

Or simpler:
```rust
// On the serve side, maintain a HashSet<session_id>; notify the runner on each spawn/delete
```

**Impact on lazible-jcode**:
- `pause_on_active_session = true` in autonomous.toml is a **no-op**
- But this actually makes testing more predictable: cycle #6 will fire on next_wake naturally, no need to worry about user-active blocking
- If the user actually wants the cycle to auto-pause while user is online, **jcode's bug must be fixed first**; lazible-jcode config changes do nothing

**Discovery time**: traced after cycle #5 when investigating whether `pause_on_active_session` actually takes effect.

---

## Bug F (added 2026-09-28 23:14 CST): runner does not use state.next_wake

When cycle #5 ended at 22:36:06, the agent called `schedule_ambient(wake_in_minutes=35)` which wrote `state.next_wake = 23:11:06.573`. But the runner at the same moment used its own computed sleep timer:

```rust
// runner.rs:812-823 (after cycle ends)
let interval = scheduler.calculate_interval(None);  // always returns max_interval_minutes
let sleep_secs = interval.as_secs().max(30);          // 30 min if max=30
{
    let mut s = self.inner.state.write().await;
    if matches!(s.status, AmbientStatus::Running{..} | AmbientStatus::Idle) {
        s.status = AmbientStatus::Scheduled {
            next_wake: Utc::now() + chrono::Duration::seconds(sleep_secs as i64),
        };
        let _ = s.save();   // overwrites agent's next_wake = 23:11 with now+1800 = 23:06
    }
}
tokio::time::sleep(sleep_secs);  // actually sleeps 1800s, not the agent's 35 min
```

Log evidence:
```
[22:36:06] Ambient runner: next cycle in 1800s           ← runner's clock (max=30 min)
[22:36:06] Ambient runner: not time to run, sleeping 1800s
[23:06:06] Ambient runner: not time to run, sleeping 1800s  ← idle check, still not at state.next_wake
```

Cycle #6 actually ran at `23:36:06` (not `23:11:06`). `state.next_wake` is a "decoration" in scheduling : only consulted when ambient actively runs or is nudged for an early check; the runner's own sleep timer is `max`.

**Impact on lazible-jcode**:
- `max_interval_minutes=30` in live config is effective for **cycle interval**
- But an agent's `schedule_ambient(35)` request is overwritten by the runner to 30 min
- To make `schedule_at(specific time)` or `wake_in_minutes=X` take effect exactly, **jcode needs to rewrite `runner.rs:812-823`** so sleep_secs reads `state.next_wake - now`. Patch not applied yet (user decision).

**Distinguishing Bug C and Bug F**:
- **Bug C**: scheduler snapshots `max_interval_minutes` at startup, never reloads. Symptom: old value 120 min takes effect; restart serve to reload.
- **Bug F**: runner computes sleep from `max` each time, ignoring agent's schedule request. Symptom: agent calls `schedule_ambient(35)` get overwritten to `max=30 min`.

Both bugs are independent; both make next_wake unreliable.

### Bug F correction (2026-09-28 23:38 CST, after cycle #6)

**Original Bug F said runner overwrites state.next_wake; that was wrong.** When cycle #5 ended, the agent called `schedule_ambient(35)` **and** `end_ambient_cycle(next_schedule={wake_in_minutes: 35})`.
**The latter's `next_schedule` reaches `persistence.rs:34-49`'s `record_cycle`**, which writes `state.status = Scheduled { next_wake }` per `req.wake_at.unwrap_or(now + wake_in_minutes*60s)`.
So **state.next_wake = 22:36:06 + 35min = 23:11:06** was strictly preserved (not overwritten).

**The condition in `runner.rs:812-823` (`if matches!(s.status, Running|Idle)`)**
makes it fallback to `max` when `record_cycle` has **not** set next_wake. Real behavior is "if agent's end_ambient_cycle set next_wake, it's not overwritten"; the two paths run in parallel.

**The real bug (renamed Bug F2)** is in the **idle check loop**:

```rust
// runner.rs:644-647
let next_direct_due = mgr
    .queue()
    .items()
    .iter()
    .filter(|item| item.target.is_direct_delivery())  // ← only looks at Session/Spawn
    .map(|item| item.scheduled_for)
    .min();
```

`ScheduleTarget::is_direct_delivery()` only returns true for `Session` and `Spawn`
(`ambient.rs:106-109`). `schedule_ambient` uses `ScheduleTarget::Ambient`
(**the default**, ambient.rs:99), **which is dropped by this filter**.

Consequence: the idle check loop cannot get `next_direct_due` (unless there are Session/Spawn items),
lines 681-684 fall back to `next_direct_secs = interval`, `sleep_secs = interval.min(interval) = interval = 1800s`.
The runner **always sleeps 30 min** (`max_interval_minutes`), never waking up early
because queue ambient items become due or `state.next_wake` is approaching.

**To be clear**: `state.next_wake` is checked by `should_run` (`manager.rs:45`'s
`Utc::now() >= *next_wake`), so when the runner finally wakes up it can read an expired
next_wake and trigger a cycle. **The problem is not that next_wake is ignored : it's that idle sleep
doesn't shorten** to next_wake time.

Log evidence (cycle #5 → #6):
```
[22:36:06] next cycle in 1800s    ← runner post-cycle sleep
[22:36:06] not time to run, sleeping 1800s  ← idle wake-up + re-sleep
[23:06:06] not time to run, sleeping 1800s  ← 60 min later (2×30), state.next_wake long since expired but the queue filter ignores it
[23:36:06] starting ambient cycle  ← cycle #6 actually ran 2×30=60min later, not 35min
```

**Cycle #6 actually ran at 23:36:06** (recorded in state.json total_cycles=6),
**not at 23:11:06 nor 23:06+1×30**. It happened because after two consecutive idle-loop 30-min sleeps,
state.next_wake (23:11:06) had finally **expired** and `should_run` returned true.

## Example: cycle #7 prediction

Cycle #6 ended at 23:36:44 CST, agent set `next_schedule.wake_in_minutes=120`
→ `state.next_wake = 25:36:44 CST`. The runner idle-sleeps for 30 min each time,
and after each wake-up calls `should_run`:

```
 24:06:44  now < state.next_wake (60 min away)  → sleep 30 min
 24:36:44  now < state.next_wake (60 min away)  → sleep 30 min
 25:06:44  now < state.next_wake (30 min away)  → sleep 30 min
 25:36:44  now ≥ state.next_wake                → cycle #7 triggers
```

Cycle #7 fires at **25:36:44 CST** (not 24:06:44). On the surface it agrees with
+120 min, but the runner only sees the expired state.next_wake 30 min after the fact : any `wake_in_minutes < 30` gets quantized up to a 30-min multiple.

### Bug F2 patch sketch (not applied)

**Full fix**: idle sleep must consider state.next_wake plus all queue targets:

```rust
// runner.rs:676-690 before
if !should_run {
    let sleep_secs = if ambient_allowed {
        let interval = scheduler
            .calculate_interval(None)
            .as_secs()
            .max(MAX_IDLE_POLL_SECS);
        let next_direct_secs = next_direct_due
            .map(|next| (next - Utc::now()).num_seconds().max(0) as u64)
            .unwrap_or(interval);
        interval.min(next_direct_secs.max(1))   // ← does not consider state.next_wake
    } else { ... };
}

// after
if !should_run {
    let sleep_secs = if ambient_allowed {
        let interval = scheduler
            .calculate_interval(None)
            .as_secs()
            .max(MAX_IDLE_POLL_SECS);
        let next_due_secs = mgr
            .queue()
            .items()
            .iter()
            .map(|item| item.scheduled_for)
            .filter_map(|t| {
                let diff = (t - Utc::now()).num_seconds();
                if diff > 0 { Some(diff as u64) } else { None }
            })
            .min()
            .unwrap_or(interval);
        // also consider state.next_wake
        let next_wake_secs = match &state.status {
            AmbientStatus::Scheduled { next_wake } => {
                let diff = (*next_wake - Utc::now()).num_seconds().max(0) as u64;
                Some(diff)
            }
            _ => None,
        };
        interval.min(next_due_secs.max(1)).min(next_wake_secs.unwrap_or(interval).max(1))
    } else { ... };
}
```

**Minimal patch** (only fixes the queue filter): remove the filter at `runner.rs:644-647`:

```rust
// before
let next_direct_due = mgr.queue().items().iter()
    .filter(|item| item.target.is_direct_delivery())  // ← ambient is dropped
    .map(|item| item.scheduled_for).min();

// after
let next_direct_due = mgr.queue().items().iter()
    .map(|item| item.scheduled_for).min();
```

The minimal patch does not fix "wake up early when state.next_wake is approaching"; it only fixes "wake up early when a schedule_ambient queue item becomes due". The full fix is required for comprehensive coverage.

Cost: full patch ~15 lines; minimal patch 1 line. Both require restarting serve.

---

## Bug F patch sketch (original version, not applied)

Change `runner.rs:812-823` to read state.next_wake instead of using max:

```rust
// before
let interval = scheduler.calculate_interval(None);
let sleep_secs = interval.as_secs().max(30);
s.status = AmbientStatus::Scheduled {
    next_wake: Utc::now() + chrono::Duration::seconds(sleep_secs as i64),
};
s.save();
tokio::time::sleep(sleep_secs);

// after (reads state.next_wake)
let now = Utc::now();
let next_wake_target = s.status.next_wake_if_scheduled()
    .unwrap_or_else(|| now + chrono::Duration::minutes(s.config.max_interval_minutes as i64));
let sleep_secs = (next_wake_target - now).num_seconds().max(30) as u64;
tokio::time::sleep(sleep_secs);
// state.next_wake keeps whatever the agent set
```

The outer idle check loop (`runner.rs:676-701`) already has the logic `interval.min(next_direct_secs.max(1))` that reads state.next_wake; we just need to sync that path into the loop above.

Cost: ~10 line patch. Requires restarting serve to take effect.

### Bug F user-visible evidence (2026-09-28 23:15 CST)

When cycle #5 ended (22:36 CST), the agent called `schedule_ambient(wake_in_minutes=35)`,
which wrote 2 ambient items with `scheduled_for=23:11:01/23:11:06 CST` into `queue.json`.

But at 23:06:06 CST (runner woke), it directly ran `sleeping 1800s` (ignoring `state.next_wake=23:11:06`),
and as of 23:15 CST, those 2 items have **been overdue 4+ minutes and still haven't fired**.
They will not fire until ~23:36:06 CST when cycle #6 starts and pulls them from the queue (FIFO),
rather than triggering exactly at `scheduled_for`.

```
[22:36:06.589] Ambient runner: next cycle in 1800s       ← overwrites the agent-set 35min
[22:36:06.597] Ambient runner: not time to run, sleeping 1800s
[23:06:06.607] Ambient runner: not time to run, sleeping 1800s   ← should have woken at 23:11 but didn't
[23:15:32 CST now] queue.json has 2 items overdue, not triggered
```

This shows Bug F is not only "the agent's wake_in_minutes is ignored" : **any next-wakeup gets pushed back by max_interval_minutes**. It also explains why observed cycle intervals are always 30 min (max=30), while the agent's schedule never takes effect.

---

## Bug G (2026-09-28 23:40 CST): bash tool silently caps timeout at 10 min

**The earlier diagnosis ("bg wait has a 10-min hard cap") was not quite right.** It's the bash tool itself (not the bg wrapper) that clamps every call to 600000 ms (10 min):

```rust
// crates/jcode-app-core/src/tool/bash.rs:1147  (execute_background path = bg tool)
let timeout_ms = params.timeout.map(|timeout| timeout.min(600000));

// crates/jcode-app-core/src/tool/bash.rs:788   (execute_reload_persistable_foreground)
let timeout_ms = params.timeout.unwrap_or(DEFAULT_TIMEOUT_MS).min(600000);

// crates/jcode-app-core/src/tool/bash.rs:1002  (detached/streaming path)
let timeout_ms = params.timeout.unwrap_or(DEFAULT_TIMEOUT_MS).min(600000);

// bash.rs:27
const DEFAULT_TIMEOUT_MS: u64 = 120000;  // default = 2 min
```

**Meaning**: passing `timeout: 1800000` (30 min) to the bash tool gets silently clamped to 600000 ms (10 min), and reports **exit code 124** (default `bash_destructive_gate.rs:64` description: `Timeout in MILLISECONDS (not seconds), e.g. 600000 = 10min; kills with exit 124`).
But the doc (bash.rs:80) says "pass a larger value (e.g. 600000 = 10min) or omit `timeout`", suggesting you can pass larger values : **this doesn't match reality**.

**Example: cycle-6-watcher.sh (task 452838zajc)**:
- I passed `timeout_seconds: 1700` (28 min) to `bg wait`.
- The `bg` tool calls `execute_background`, which clamps to 600000 ms.
- 23:14:12 CST start → 23:24:12 CST killed (exactly 600s), exit 124.

**The meaning of Bug F2 patch still holds**: just fixing "runner idle filter" fixes the schedule_ambient on-time issue. But **all bg tasks that need >10 min to run** must use a workaround that escapes the bash tool's timeout control (e.g. `nohup bash script &`),
and this will keep biting until Bug G is patched.

### Bug G patch sketch (not applied)

Lift the cap at all three sites `bash.rs:1147`, `788`, `1002`, and update the doc (bash.rs:80) to say "may exceed 10 min":

```rust
// before
let timeout_ms = params.timeout.map(|timeout| timeout.min(600000));

// after (drops the hard cap)
let timeout_ms = params.timeout.unwrap_or(DEFAULT_TIMEOUT_MS);
```

Cost: 3-line patch. Requires restarting serve.

---

## Empirical table: cycles 0–5 (2026-09-28)

```
cycle# | started          | duration   | model                       | status      | summary
───────┼──────────────────┼────────────┼─────────────────────────────┼─────────────┼─────────────────────────────────────────────
  #1   | 10:05:54 → 11:00 | 3356 s     | anthropic/claude-sonnet-4   | incomplete  | Visible cycle ended (user closed window)
  #2   | 11:04:00 → 11:04 | 0.6 s      | anthropic/claude-sonnet-4   | incomplete  | Cycle ended without calling end_ambient_cycle
  #3   | 13:04:01 → 13:04 | 0.6 s      | anthropic/claude-sonnet-4   | incomplete  | Cycle ended without calling end_ambient_cycle
  #4   | 14:19:39 → 14:19 | 0.3 s      | anthropic/claude-sonnet-4   | incomplete  | forced end after 2 attempts
  #5   | 14:34:50 → 14:36 | 76 s       | MiniMax-M3                  | complete    | (end_ambient_cycle called normally)
```

**How to read**:
- Cycles #1–#4 all used `anthropic/claude-sonnet-4` (**not** the configured `MiniMax-M3`), all incomplete.
- Cycle #5 was the first to complete after the serve restart + env var fix, model = `MiniMax-M3`, status = `complete`.
- Transition point: between cycle #4 (14:19) and cycle #5 (14:34). `install-shell-env` (b30ae02) plus `kill -9 1945981 + jcode serve` (PID 1988541).
- This shows that **fork() race + env var fix** is the necessary and sufficient condition for cycle #5 success.

**Bug A evidence**: cycles #1–#4 all used model=claude-sonnet-4 even though the config file specifies MiniMax-M3 (in jcode.toml: `provider = "openrouter"`, `model = "MiniMax-M3"`). The race window is in `Provider::fork()` creating the child provider : it randomly swaps in the default model under contention, and the env var fix completely covers it.

---

## Source-code references (additional)

- `debug_ambient.rs:30-37`: `ambient:trigger` debug command triggers trigger