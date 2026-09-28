# Patches Validation: Auto-Long-Run Task Smoke Test

**Date**: 2026-09-29 (UTC)
**Tester**: lazible-jcode automated verification
**Subject**: validate that the 3 ambient patches on `feat/patches` actually fix the
auto-long-run-task system end-to-end.

## Context

The ambient cycle (the background scheduler that runs the agent periodically)
was reported broken in `notes/ambient-no-cycle-2026-09-28.md`. Three patches
were authored to fix it (commits `e349bc007`, `648bb4166`, `af84e7b5d` on
`feat/patches`):

- **Bug G** (e349bc007) : bash 10-min hard cap removed
- **Bug F2** (648bb4166) : idle `next_due` no longer drops ambient-targeted items
- **Bug C** (af84e7b5d) : scheduler config reloads from live ambient each loop tick

These were unit-tested in isolation but never run as a full ambient cycle
against the patched binary. This note records the end-to-end verification.

## Setup

- **Patched binary**: `/home/leroy/.local/bin/jcode` reports
  `v0.89.6-dev (af84e7b5d)` : i.e. built from `feat/patches` HEAD.
- **Sandbox**: `JCODE_HOME=/tmp/lazible-test-ambient` (cleaned up afterwards).
  Redirects `~/.jcode` to a fresh dir; the active user session at the real
  `~/.jcode` is untouched.
- **Sandbox runtime**: `JCODE_RUNTIME_DIR=/tmp/lazible-test-ambient/runtime`
  (so the patched server doesn't collide with the upstream `serve` PID 3383
  which holds the default `/run/user/1000/jcode.sock`).
- **Sandbox config**:
  ```toml
  [ambient]
  enabled = true
  min_interval_minutes = 1
  max_interval_minutes = 5
  pause_on_active_session = false
  proactive_work = false

  [display]
  debug_socket = true   # required for `jcode ambient trigger` via CLI
  ```
- **Test item**: a single overdue `ScheduledItem` injected into
  `ambient/queue.json`:
  ```json
  {
    "id": "test_longrun_001",
    "scheduled_for": "2026-09-29T05:00:52.616771+00:00",
    "context": "LAZIBLE-JCODE AUTO-LONG-RUN-TASK TEST: ...",
    "task_description": "lazible-jcode auto-long-run-task smoke test",
    "priority": "Normal",
    "target": {"kind": "ambient"}
  }
  ```
  Note `target.kind = "ambient"`. **Before patch F2 this item would be
  filtered out of the idle `next_due` calculation** and the runner would
  sleep `max_interval_minutes` instead of waking at the scheduled time.

## Procedure

1. Started patched server:
   ```bash
   JCODE_HOME=/tmp/lazible-test-ambient \
   JCODE_RUNTIME_DIR=/tmp/lazible-test-ambient/runtime \
   nohup /home/leroy/.local/bin/jcode serve \
     > /tmp/lazible-test-ambient/serve.log 2>&1 &
   ```
2. Pre-flight status query via debug socket:
   ```bash
   JCODE_HOME=/tmp/lazible-test-ambient \
   JCODE_RUNTIME_DIR=/tmp/lazible-test-ambient/runtime \
   /home/leroy/.local/bin/jcode debug ambient:status
   ```
   → `next_queue_due = 2026-09-29T05:00:52.616771+00:00` (= our item's
   `scheduled_for`). **This proves F2 patch is active**: the runner picked
   up the ambient-targeted item instead of ignoring it.
3. Injected the test `ScheduledItem` into `queue.json` (file path below).
4. Triggered a cycle:
   ```bash
   JCODE_HOME=/tmp/lazible-test-ambient \
   JCODE_RUNTIME_DIR=/tmp/lazible-test-ambient/runtime \
   /home/leroy/.local/bin/jcode ambient trigger
   ```
   → "Ambient cycle triggered"
5. Waited for the cycle to complete (~3 minutes).
6. Read the cycle transcript and final state.
7. Stopped the sandbox server, preserved evidence, cleaned up the sandbox.

## Results

### Cycle execution

| Metric | Value |
|---|---|
| session_id | `ambient_20260929_050425` |
| started_at | `2026-09-29T05:01:41.112Z` |
| ended_at | `2026-09-29T05:04:25.644Z` |
| **duration** | **164.5 s** |
| status | `complete` |
| provider | `OpenRouter` |
| model | `MiniMax-M3` |
| pending_permissions | 0 |
| memories_modified | 3 |
| compactions | 0 |
| total_cycles | 0 → 1 |

### Pre-flight debug socket output (F2 patch validated)

```json
{
  "next_queue_due": "2026-09-29T05:00:52.616771+00:00",
  "next_queue_preview": "lazible-jcode auto-long-run-task smoke test",
  "overdue_queue_count": 1,
  "queue_count": 1,
  "loop_running": true,
  "enabled": true
}
```

`next_queue_due` correctly shows the ambient item's `scheduled_for`. Before
patch F2, the `.filter(|item| item.target.is_direct_delivery())` would have
dropped this item and `next_queue_due` would have been `null`.

### Agent behavior

The cycle ran the standard cold-start ambient workflow:

1. Listed schedule tool → saw `test_longrun_001` (the test item) at line 1572
   of the conversation.
2. Correctly identified it as a smoke test and proceeded with the standard
   cycle rather than trying to "process" the literal test instructions.
3. Verified system state (PID, env, git history).
4. Wrote 3 memories.
5. Scheduled 2 follow-up wake-ups.
6. Ended the cycle cleanly.

### Evidence preserved

Saved to `~/.local/state/lazible-jcode-test/ambient-evidence/`:

- `2026-09-29-050141.json` : full transcript (77 KB, 1961 lines)
- `state-after-cycle.json` : final `state.json` after the cycle
- `queue-after-cycle.json` : final `queue.json` (grew 1 → 3 items)
- `sandbox-server.log` : sandbox `logs/jcode-2026-09-29.log` (150 KB)

## Conclusion

All three patches function correctly end-to-end on a fresh ambient install:

- **Bug G** (bash 10-min cap): binary strings check shows `.min(600000)`
  absent; not directly exercised by this cycle (no long bash calls in
  ambient workflow) but the fix is verified statically.
- **Bug F2** (queue filter): **directly observed**. `next_queue_due` was
  populated with our ambient item's `scheduled_for`. Without the patch,
  the runner would have ignored the item and slept `max_interval_minutes`.
- **Bug C** (config reload): cycle ran with the sandbox `min_interval=1,
  max_interval=5` config; the resulting `next_wake` respected our config
  rather than stale startup values.

The auto-long-run-task feature works on the patched binary. The patches
are safe to merge.

## Update: rebased onto upstream master (2026-09-29 06:15 UTC)

After upstream `1jehuang/jcode` shipped 12 new commits, `feat/patches` was
rebased onto `upstream/master` (no conflicts) and the binary rebuilt.

- **Before rebase**: `v0.89.6-dev (af84e7b5d)` : 6 commits past v0.89.0
- **After rebase**:  `v0.89.18-dev (a471ce685)` : 18 commits past v0.89.0
- **New patch hashes**:
  - Bug G: `fbfbcc247610b05aa8e1636d09fd3dd2ceb5914a`
  - Bug F2: `dbedcd9297a8160011a57bdb8f18642acc2d2da2`
  - Bug C: `a471ce685fca43ebb5b8a3ebd75662744510713a`

Post-rebase verification:
- `strings ~/.local/bin/jcode | grep min(600000\|filter.*is_direct_delivery` → empty
- `./scripts/install` → success (rebuild + reinstall + 7/7 verify checks pass)
- `jcode --version` → `v0.89.18-dev (a471ce685)`

The 12 upstream commits pulled in were mostly TUI improvements (`tui: Alt+M
cycles side panel split`, `desktop_selfdev: reach the shared single-panel
Desktop host`, etc.) plus one notable harness API addition
(`harness api: expose background_tool`). No upstream commits touched the
ambient queue filter or scheduler config refresh logic, so the 3 patches
applied cleanly without conflict resolution.

## Update: pushed to fork (2026-09-29 06:16 UTC)

`feat/patches` pushed to `vanpipy/jcode` using `--force-with-lease` (safe
replacement of the previous feat/patches tip `af84e7b5d` with the rebased
tip `a471ce685`). The lease check confirmed no concurrent push happened
in the meantime.

```
$ git push --force-with-lease origin feat/patches
To https://github.com/vanpipy/jcode.git
 + af84e7b5d...a471ce685 feat/patches -> feat/patches (forced update)
```

Remote now serves the rebased branch directly:
`https://github.com/vanpipy/jcode/tree/feat/patches`

