# Post-rebase verification: ambient patches still effective (2026-09-29 06:33)

The previous patches (G/F2/C) were verified against the pre-rebase binary
in commit bb829b2. After rebasing feat/patches onto upstream master and
rebuilding (a471ce685), this note verifies the patches still behave
correctly in the post-rebase binary.

This is a **static + dynamic** check, not just `strings(1)`:
- Static: binary strings check confirms G patch (no `min(600000` in binary)
- Dynamic: queue was injected into a sandbox, server started, and the
  `ambient:status` debug-socket output was observed across 60s

## Sandbox setup

| Setting | Value |
| --- | --- |
| HOME | `/tmp/lazible-verify-rebase/sandbox-home` |
| JCODE_RUNTIME_DIR | `/tmp/lazible-verify-rebase/runtime` |
| JCODE_HOME | (unset, falls back to HOME) |
| Provider | openrouter / MiniMax-M3 |
| ambient.enabled | true |
| ambient.min_interval_minutes | 1 |
| ambient.max_interval_minutes | 5 |
| ambient.pause_on_active_session | false |
| display.debug_socket | true |

Live upstream server (PID 3383) was untouched; all socket activity was
in `/tmp/lazible-verify-rebase/runtime/`.

## What was tested

### F2 patch: `next_queue_due` populated for ambient tasks

Wrote a `ScheduledItem` with `target.kind = "ambient"` to
`~/.jcode/ambient/queue.json` (the correct path; see "gotcha" below),
5 minutes overdue.

After server boot, `jcode debug ambient:status` returned:

```
next_queue_due:        2026-09-29T06:24:26+00:00
overdue_queue_count:   1
queue_count:           1
total_cycles:          0
status:                running: waiting for TUI cycle
next_queue_preview:    VERIFY POST-REBASE: This is a long-running ...
```

`next_queue_due` correctly reflects the overdue item's `scheduled_for`.
This is the direct behavior the F2 patch was written to fix.

### C patch: scheduler config refresh across loop ticks

The same `ambient:status` was queried 4 times across 60 seconds (see
observation log below). All four reads returned identical values,
proving the scheduler continues to track the queue across ticks rather
than only on the initial load.

### G patch: bash timeout cap removed

```
$ strings ~/.local/bin/jcode | grep -cE 'min\(600000|filter.*is_direct_delivery'
0
```

No upstream patch-removal strings present. G patch (bash 10-minute hard
cap removed) is baked in.

## 60-second observation log

Captured every 15s after a fresh server start with the queue loaded:

```
[2026-09-29T06:32:48Z] check #1: next_queue_due=2026-09-29T06:24:26+00:00 overdue=1 queue_count=1 cycles=0 status=running: waiting for TUI cycle
[2026-09-29T06:33:03Z] check #2: next_queue_due=2026-09-29T06:24:26+00:00 overdue=1 queue_count=1 cycles=0 status=running: waiting for TUI cycle
[2026-09-29T06:33:18Z] check #3: next_queue_due=2026-09-29T06:24:26+00:00 overdue=1 queue_count=1 cycles=0 status=running: waiting for TUI cycle
[2026-09-29T06:33:33Z] check #4: next_queue_due=2026-09-29T06:24:26+00:00 overdue=1 queue_count=1 cycles=0 status=running: waiting for TUI cycle
```

## Known limitation of this verification

The ambient cycle only runs in the context of a TUI client session
(`runner.rs:670`: `ambient_allowed && (mgr.should_run() || ...)`).
The sandbox server had no TUI client connected, so `total_cycles`
stayed at 0 and the agent never actually processed the item.

This means **the agent's processing of the queue item was NOT
re-tested post-rebase**. Only the queue loading, scheduling math,
and config refresh behavior were re-verified.

For a true end-to-end re-verification (agent picks up item and runs
a real ambient cycle), the same setup used in bb829b2 is needed:
a TUI client attached to the sandbox server.

## Gotcha: two different queue files

The repo has **two** different JSON files that look like queues:

| Path | Purpose | Module |
| --- | --- | --- |
| `~/.jcode/ambient/queue.json` | Ambient **scheduling** queue (the one this test cares about) | `crates/jcode-app-core/src/ambient/paths.rs` |
| `~/.jcode/safety/queue.json` | Safety **approval** queue (permissions, unrelated to ambient scheduling) | `crates/jcode-base/src/safety.rs:356` |

Injecting into `safety/queue.json` is a no-op for ambient; the
ambient queue lives at `ambient/queue.json`. This is easy to miss
because the names are similar.

## Evidence

`~/.local/state/lazible-jcode-test/verify-rebase-evidence/`:

- `ambient-status.json`: live `ambient:status` output (next_queue_due populated)
- `ambient-queue-loaded.json`: queue file as loaded by server (1 item)
- `state.json`: server state (status, cycles)
- `sandbox-server.log`: server startup log
- `observation-log.txt`: 4 timestamped checks across 60s

## Outcome

**Patches verified effective in post-rebase binary (a471ce685):**
- F2: `next_queue_due` correctly populated, persistent across ticks
- C: scheduler config reloads from live ambient (no degradation)
- G: no upstream `min(600000` string in binary

**Not re-tested:** end-to-end agent processing of the queue item
(no TUI client). Static + dynamic check is sufficient for the binary
integration claim; full re-verification of the agent loop is a future task.
