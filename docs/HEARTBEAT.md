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

### Completion = commit AND `complete_node` (both required)

A worker reaches "completion" when **both** of these happen, in this
order:

1. **Final commit lands on `<worker_branch>`** with a `type: "final"`
   artifact. The commit is the durable record; it survives worker
   death, server restart, cross-swarm boundaries, and offline reviews.
2. **Live handoff fires**: `complete_node` (preferred) or `report` with
   a typed body. The handoff is the live signal that wakes root in the
   current context.

Neither alone is "done". A commit without a handoff leaves root waiting
on the dm channel forever; the failure mode is silent because the
artifact says `step: "complete"`. A handoff without a commit cannot be
audited or recovered later. This split is the gap the 2026-08 silent-stuck
incident exploited: worker committed final, then died before
`complete_node`; root sat waiting until a user message prompted manual
`git log`. The contract now requires root-side passive inspection
(`swarm-prompt.md` §12 root obligation 3) to catch the missing handoff.

If a worker can only fire one signal (e.g. cross-swarm makes the dm
channel unreachable), it MUST fire the other — commit-only or handoff-only
is acceptable but the worker must declare which via `open_questions[]`,
and root's passive inspection must be able to detect either case.

## Liveness contract (worker-driven, root-responsive)

The framework has **no watchdog, no real-time timer, no enforced
deadline**. Every "X minutes" in this contract is a **soft contract**
the LLM session is expected to honor, not a guarantee the runtime
enforces. Be honest about the boundary: there is a layer the contract
*can* cover, and a layer it *cannot*. Mislabeling soft contracts as
hard ones is what produced the original scheduled-self-wakeup
design (root waking itself every 8 minutes via
`schedule(target=resume, wake_in_minutes=8)` to probe worker state)
and led to its removal.

### Worker obligations (liveness source)

The worker is responsible for being observable. Three concrete rules:

1. **Heartbeat channel ≤ 5 min.** Within any 5-minute window during a
   task, the worker MUST emit at least one of:
   - a `progress` commit (preferred — durable + auditable),
   - `dm <root> --delivery=notify` with payload
     `{"type":"heartbeat","step":"...","elapsed_min":N}`,
   - `report` with a typed body.
   Two consecutive misses = contract violation; root is allowed to
   treat the worker as abandoned.
2. **Stuck self-escalation ≥ 3 min.** If the worker has not made
   substantive forward progress for 3 minutes (e.g. looping on a single
   tool call, blocked on missing info, blocked on an external dep),
   the worker MUST `dm <root> --delivery=interrupt` with payload
   `{"type":"stuck","reason":"...","help_needed":"..."}`. Silence is
   not an option; silent hangs are the failure mode this rule kills.
3. **Self-alarm (recommended).** On spawn, the worker SHOULD
   `schedule(target=resume, wake_in_minutes=4, task="if still running,
   commit progress + dm heartbeat")`. This is a self-reminder; the
   runtime wakes the worker, the worker self-checks, the worker emits
   the heartbeat. This costs nothing if the worker is already active.

### Worker exit right (abandonment)

If the worker has emitted `{"type":"stuck"}` and has not received a
**concrete next step from root** within **5 minutes**, the worker is
contractually allowed to abandon the task: stop work, `report status:
abandoned` with a typed artifact explaining the silence, and exit
cleanly. A "concrete next step" is one of: (a) a scope change / scope
split decision, (b) a directive to keep going on the current path with
specific guidance, (c) a `stop` order, (d) a concrete blocker answer
unblocking the worker. A bare "ack, hold" or "noted, will get to it"
without direction does **not** count — those are exactly the replies
that leave the worker hanging, and they do not extend the 5-minute
window. This is **not a failure mode** — it is the contract working.
The alternative (waiting forever) is worse: it costs the worker tokens
and the root never learns the worker is stuck.

### Reminder-loop stall (environmental lock)

If the worker is receiving repeated identical system reminders (e.g.
"N incomplete todos") and the `todo` tool rejects every write with the
same error, the worker is in a **reminder loop** — an environmental
lock where the normal `todo` close-out path is unavailable. The same
contract applies:

1. After 5 consecutive identical reminders with no successful tool
   action, treat this as `{"type":"stuck"}` and dm root with
   `reason: "todo store in reminder loop"`.
2. After the standard 5-min exit-right window without a concrete
   next step, report `status: abandoned` with
   `what_i_did_not_check: ["todo store recovery procedure"]`.
3. Do not waste tokens re-trying the same todo write; the lock will
   not lift from inside the session.

See `docs/TODO_STALL_RECOVERY.md` for the full recovery procedure.

### Root obligations (responsiveness)

The root does not poll. The root does not schedule itself. But when the
root is woken by a worker handoff, the root has two soft obligations:

1. **Priority on `{"type":"stuck"}` and `follow_up`.** When a worker
   reports stuck or asks for help, the root SHOULD respond with `dm`
   within the current context (information, scope expansion, or
   `stop`). There is **no hard deadline** — root is an LLM session and
   may be busy integrating another worker. The worker exit right above
   is the safety valve.
2. **No scheduled self-wakeup.** Root MUST NOT call
   `schedule(target=resume, wake_in_minutes=N)` for the purpose of
   "checking on workers". The scheduled self-wakeup design was
   removed because it added 8 minutes of latency to every spawn
   without helping root notice workers any faster than the worker's
   own handoff. There is no `schedule(target=resume, wake_in_minutes=N)`
   on the spawn path.

### What the framework CANNOT guarantee

These are out-of-band. No contract can fix them; only runtime changes
(added in a future jcode) could.

- **Real-time detection of a truly dead worker.** If the worker
  process is OOM-killed, network-partitioned, or the worker session
  is otherwise killed without an opportunity to flush, neither the
  heartbeat nor the stuck-escalation can fire. The framework has no
  watchdog. The recovery is `git show <branch>` on root's next
  conscious turn.
- **Root response time.** Root is an LLM. If root is thinking through
  a 10-minute plan or integrating a complex worker branch, it will
  not respond to a stuck worker in 5 minutes. The worker's exit right
  exists *because* this is true.
- **Worker honesty.** A worker can lie about its state in a heartbeat
  or stuck report. Root cross-checks against the diff, the test
  output, and `git grep` before integration; that is the only defense.

### Failure modes the contract catches

| Failure                                  | Detection signal                                | Recovery                          |
| ---------------------------------------- | ----------------------------------------------- | --------------------------------- |
| Worker stuck on a hard step              | `{"type":"stuck"}` dm from worker               | Root `dm`s back, expands scope, or stops |
| Worker silent because busy thinking      | Mid-task `progress` commit or heartbeat dm     | Root reads latest commit on branch |
| Worker hung on long test / install       | Self-alarm `schedule` fires, worker self-checks | Worker emits heartbeat or stuck dm |
| Worker honest-but-too-quiet              | Two consecutive 5-min heartbeat misses          | Worker exit right; root treats as abandoned |
| Root did not respond to stuck            | 5 min since `{"type":"stuck"}`                  | Worker `report status: abandoned` |
| Worker dies after final commit           | `type: "final"` already on disk                 | Root reads via `git show`         |
| Worker reports "done" but didn't commit  | Latest commit has no artifact                   | Root rejects report               |
| Server restart killed worker session     | Git state unchanged                             | Root reads via `git log`          |

## Cross-swarm handoff gap

The contract above assumes root and worker share a swarm and the dm
channel reaches the worker. **Neither is always true.** Two real
situations break the assumption:

1. **Cross-swarm workers.** Root session ID is `session_hedgehog_…`;
   worker session ID is `session_skunk_…` (a different swarm entirely,
   e.g. the worker was spawned by a separate orchestration step or a
   selfdev run). The worker's `dm <root_session_id>` call returns a
   routing error — the worker cannot reach root, full stop. The
   worker MUST detect this on its first attempted dm (it has no
   fallback channel) and switch to commits-only mode:

   - Continue making `progress` and `final` commits with the
     artifact's `confidence` field set honestly.
   - Do NOT emit `{"type":"stuck"}` (it cannot be delivered).
   - Set the artifact's `blockers[]` to
     `["cross-swarm: dm channel unreachable, commits-only mode"]` so
     root's inspection sees why no handoff arrived.
   - Surface the cross-swarm status in the worker's final
     `open_questions[]`.

2. **Worker crash between commit and handoff.** The worker's last
   action is `git commit` writing `type: "final"`. Before
   `complete_node` returns to the runtime, the worker is killed
   (OOM, network partition, user abort). The commit is durable; the
   handoff is gone.

Both situations look identical from root's perspective: a `final`
commit on the worker branch, no live handoff, no dm in queue. Root's
mandatory passive inspection (`swarm-prompt.md` §12 root obligation 3)
is the only thing that catches either case. There is no runtime
signal that distinguishes "worker is fine, just slow on handoff" from
"worker is gone". The contract therefore requires root to inspect at
**every** decision point, not just on user prompts — a worker that
commits `final` and then sits idle for 5 minutes is, by the contract,
silently stuck and the partial-or-complete work should be surfaced.

The `cross-swarm` status is also visible to root via the artifact's
`blockers[]` field. If root's passive inspection reads a `final`
artifact whose `blockers[]` lists `cross-swarm: …`, root knows the
worker is alive but on the wrong swarm and can spawn a small relay
worker (or simply integrate directly via `git show` / `git fetch`).

## Why a daemon would have failed

Each row above is something a daemon would either miss (silent gaps,
`type: "final"` after death) or require bespoke logic to handle. The
artifact-as-commit model handles them for free because the worker's
self-report is its work, not a separate signal.

The cost is one fenced block per commit (~200 bytes) plus, on long
tasks, a 4-minute self-reminder. No timers, no manifest writes, no
scheduled wake-ups on the root side.

## What this is NOT

- **Not** a replacement for `complete_node` / `report`. The artifact
  supports those calls; it does not replace them.
- **Not** an excuse for a worker to skip `complete_node`. The artifact is
  the durable record; the typed handoff is the live one.
- **Not** a guarantee the artifact is correct. A worker can lie. The
  root session cross-checks against the diff, the test output, and
  `git grep` before integration.
- **Not** a hard real-time guarantee. Heartbeats are LLM-followed soft
  contracts. A worker that is truly dead cannot heartbeat, and the
  framework has no watchdog for that.
- **Not** applicable to the `last_heartbeat` field in
  `.jcode/worktree-manifest.json`. That field exists for the worktree
  cleanup safety net (see `scripts/conflict-detect.py
  detect_heartbeat_stale`); it is a passive detector, not the primary
  liveness signal.
- **Not** an excuse for root to ignore a `{"type":"stuck"}`. The
  worker exit right is the safety valve, not a license to be slow.