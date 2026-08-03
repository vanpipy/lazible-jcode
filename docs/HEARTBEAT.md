# Heartbeat / Worker Liveness

How the framework knows whether a worker is alive, and what to do when it
isn't. The mechanism has one rule: **git is the source of truth**, and the
commit body is the heartbeat.

## The problem

A swarm root session needs to know three things at all times about each
in-flight worker:

1. **Alive** — is the worker still running, or has it crashed / been
   killed / hung in a tool-call loop?
2. **Productive** — has it actually done work, or is it spinning on the
   same tool call?
3. **Ready to integrate** — has it finished its scope and emitted a typed
   artifact the root can act on?

The first instinct is to spawn a heartbeat daemon that periodically pings
each worker and writes a timestamp. This works, but it has six
unfortunate properties:

- The daemon itself can crash. Now you have a heartbeat-of-the-heartbeat
  problem.
- The timestamp proves the worker *was alive*, not that it *did work*.
- The state is local to the runtime — `git show` from a fresh checkout
  cannot recover it.
- Cross-worker visibility is one-sided: workers don't see each other's
  heartbeats.
- The cost is per-worker-timer; for 10 workers you have 10 timers.
- It is yet another daemon that the framework installer has to ship.

## The commit-as-artifact contract

The framework instead treats **every commit on `<worker_branch>` as a
heartbeat that also carries a payload**. A commit is durable (in git),
auditable (`git show <sha>` reconstructs it), and proves work happened
(diff inside it). The commit body carries a typed JSON artifact that
tells the root session what to do next.

Required structure (single fenced block at the bottom of the commit body):

````
```json artifact
{
  "type": "progress | final",
  "session_id": "<from swarm>",
  "task_id": "<root-supplied>",
  "branch": "<worker_branch>",
  "commit": "<sha>",
  "elapsed_min": <int>,
  "step": "<what the worker is doing right now>",
  "next": "<what the worker plans to do>",
  "confidence": "low | medium | high",
  "blockers": ["..."]
}
```
````

`type: "progress"` for mid-task commits; `type: "final"` for the commit
that completes the spawn scope. See `swarm/swarm-prompt.md` §12 and the
role-specific sections in `swarm/roles/*.md` for details per role.

## Root-session poke protocol

The root session never polls the runtime. After `spawn`, it schedules a
single future wake-up via `schedule(target=resume, wake_in_minutes=8)`.
The wake-up task is short and mechanical:

1. `git -C <worktree_path> log -1 --format=%B <branch>` to read the latest
   artifact.
2. Parse the trailing ```json artifact``` block.
3. If `type: "final"` and `confidence != "low"`, integrate. Otherwise
   poke via `dm --delivery=interrupt` and wait 60 s for ack.
4. If 3 pokes fail, `stop <session_id>` and respawn with same `task_id`.

The full table lives in `swarm/prompt-overlay.md` §1 ("Self-poke via
schedule + git-probe"). The pattern is mandatory after every spawn — no
exceptions.

## Failure modes the artifact contract catches

| Failure                                  | Detection signal                   | Recovery                     |
| ---------------------------------------- | ---------------------------------- | ---------------------------- |
| Worker hung in long thinking             | No new commit at 8 min             | `dm --delivery=interrupt`    |
| Worker died after final commit           | `type: "final"` already on disk    | Root reads via `git show`    |
| Worker reported "done" but didn't commit | Latest commit has no artifact      | Reject the report            |
| Server restart killed worker session     | Git state unchanged                | Resume from `git log`        |
| Worker stuck on a single hard step       | Multiple `progress` artifacts with same `step` | Root interrupts with new scope |
| Silent gap in `delete` / `rename` migration | `progress` artifact's `blockers[]` list | Root catches before next atomic step |

## Why a daemon would have failed

Each row above is something a daemon would either miss (silent gaps,
`type: "final"` after death) or require bespoke logic to handle. The
artifact-as-commit model handles them for free because the worker's
self-report is its work, not a separate signal.

The cost is one fenced block per commit (~200 bytes) and one short
wake-up task at the 8-minute mark. Both are negligible.

## What this is NOT

- **Not** a replacement for `complete_node` / `report`. The artifact
  supports those calls; it does not replace them.
- **Not** an excuse for a worker to skip `complete_node`. The artifact is
  the durable record; the typed handoff is the live one.
- **Not** a guarantee the artifact is correct. A worker can lie. The
  root session cross-checks against the diff, the test output, and
  `git grep` before integration.
- **Not** applicable to the `last_heartbeat` field in
  `.jcode/worktree-manifest.json`. That field exists for the worktree
  cleanup safety net (see `scripts/conflict-detect.py
  detect_heartbeat_stale`); it is a passive detector, not the primary
  liveness signal.

## When the daemon might still be useful

If a future jcode adds a runtime that runs continuously across multiple
worker sessions (e.g. a long-lived planner agent that holds a hot model
connection), a heartbeat may become useful again. Until then, commit-
as-artifact is the right answer: zero infrastructure, full durability.