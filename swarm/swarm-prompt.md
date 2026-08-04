<!--
This file IS the swarm config. Swarms are complicated, dynamic systems, so
routing policy is passed to the models as a prompt rather than as options in
a standard config file. Edit freely: override globally at
~/.jcode/swarm-prompt.md or per-project at ./.jcode/swarm-prompt.md.
-->

# Swarm Prompt (global)

Generic, project-agnostic guidance for the root session and every spawned
worker. Project-specific overrides go in `./.jcode/swarm-prompt.md`.

---

## 1. Model & effort routing

**Only MiniMax family models are reliably available.** All Claude and GPT
routes in `swarm list_models` are reported `[unavailable] (no credentials)`.
`gpt-5.6-pro[web]` works via ChatGPT web session but is unusual and not used
for routine spawning.

Routing strategy: differentiate **fast/mechanical** from **quality/deep**
work within the MiniMax family.

| Tier        | Model                   | When                                                 | Effort        |
| ----------- | ----------------------- | ---------------------------------------------------- | ------------- |
| Fast        | `MiniMax-M2.7-highspeed` | Read, summarize, reformat, mechanical impl, simple test scaffolds, doc rewrite | `none` / `low` |
| Quality     | `MiniMax-M3`            | Refactor, migration, debugging, design, review, verification, architecture, default worker | `medium` / `high` |

Pass `model` explicitly on every spawn. Pass `effort` explicitly too — the
two are independent levers (a quality-model worker can still run at `low`
effort for simple tasks; a fast-model worker at `high` effort is rarely
worth it).

| Task kind                                                | Model                   | Effort   |
| -------------------------------------------------------- | ----------------------- | -------- |
| Bulk reading / summarization / context fetch             | `MiniMax-M2.7-highspeed` | `none`   |
| Mechanical implementation (typed, well-specified)        | `MiniMax-M2.7-highspeed` | `low`    |
| Doc rewrite / reformat / changelog                       | `MiniMax-M2.7-highspeed` | `none`   |
| Simple test scaffolding (existing patterns)              | `MiniMax-M2.7-highspeed` | `low`    |
| Cross-module refactor / migration                        | `MiniMax-M3`             | `medium` |
| Default worker (unspecified)                             | `MiniMax-M3`             | `medium` |
| Design, investigation, debugging, review, verification   | `MiniMax-M3`             | `high`   |
| Architecture / API design / trade-off analysis          | `MiniMax-M3`             | `high`   |

Rules:
- Never invent model names. Run `swarm list_models` to verify before adding a
  route to this table.
- When the user names a specific model, pass it through (subject to
  availability check).
- `effort: "max"` only when the user explicitly asked — it's expensive.
- If credentials get configured for Claude/GPT routes later, restore them
  in the table with `[unavailable]` tags removed.

---

## 2. When to spawn (root session decides)

Spawn a worker when **all** of the following hold:

- Work is **independently verifiable** (the worker can run gates on its slice).
- Work touches **≥ 2 files** OR spans **≥ 2 unrelated areas** of the codebase.
- Work has **no strong ordering dependency** on another in-flight task.
- Parallel value is **clear**: wall-clock saving > coordination overhead.

Spawn for these specific shapes:
- Independent test suites against shared fixtures.
- Review + implementation in parallel (review starts as soon as first commit lands).
- Documentation sync + code change when doc is auto-generated or near-trivial.
- Multiple language/framework migrations on disjoint surfaces.
- Research, investigation, repo-mapping, architecture review.
- Migration of any single feature across ≥2 crates or modules.

Do **not** spawn when:
- Work is a single file or ≤ 2 lines of trivial change.
- Tasks have tight ordering (B depends on A's API shape).
- The work is a question / explanation / single grep.
- You are about to abort or redo the work within the next turn.

When in doubt: **spawn**. The bar to *not* spawn is strictly higher than
the bar to spawn. Serial execution is the exception, reserved for the
narrow "single file / ≤2 lines / one binary yes-no" shape above. Spawning
is for *every non-trivial task*, not just ceremony; the throughput
benefit compounds with focused attention you free up for integration.

---

## 3. Spawn hygiene

Every spawn call **must** include:

- `label` — short, nonblank, describes role (e.g. `"api reviewer"`,
  `"test scaffolder"`). Missing label is rejected by the tool.
- `prompt` or `initial_message` — a concrete task, not "help with the project".
  An idle agent with no task wastes resources and confuses the swarm UI.
- `model` + `effort` — explicit unless inheritance is intentional.

Workers in `light-swarm` mode must **never** spawn their own children. If a
worker thinks it needs help, it reports back to the root with a `follow_up`
listing the missing capability, and the root decides.

Recursive spawning is only available in `swarm-deep` mode. Default is light.

---

## 4. Communication: prefer dataflow over chat

Use these primitives in this order of preference:

1. **`complete_node` with typed artifact** — primary handoff. Forces the worker
   to produce `findings`, `evidence[]`, `edge_cases_considered[]`, `validation`,
   `open_questions[]`, `confidence`, and `what_i_did_not_check[]`.
2. **`dm` to a specific worker** — for follow-up questions or to assign more work
   to an existing agent.
3. **`broadcast` to your spawned subtree** — rare, only for genuine stop/recall
   events. Never for "FYI" chatter.
4. **`channel`** — discouraged legacy primitive. Prefer DMs and task-graph.
   Subscribe only when there's a durable shared concern.

Workers reporting back to root: use `report` action with `status: "ready"` and a
typed artifact. `status: "blocked"` requires a `blockers[]` list.

---

## 5. Confidence and honesty

Every completion artifact **must** declare `confidence: low | medium | high`.

- `high` — work fully verified against an explicit check (test, lint, typecheck,
  manual reproduction). All edge cases enumerated.
- `medium` — work verified against a subset of checks; some uncertainty remains
  about edge cases the worker did not enumerate.
- `low` — work partially done, or verification relied on the worker's judgment
  rather than an observation. Must be reported honestly.
- Discovered dependencies outside the spawn scope that were left unhandled
  (e.g., user asked to delete a facade, you found 3 production call sites
  still using the old import, but the user did not ask for migration).
- A new public API does not match the call-site usage patterns it is meant
  to serve (must explicitly explain why this is correct, otherwise it does
  not count as `low` confidence).

`low` confidence is **not** failure. It routes follow-up work automatically. A
fake `high` is far worse than an honest `low`.

The `what_i_did_not_check` list is mandatory. "Nothing" is a valid answer only
when truly exhaustive; otherwise list the gaps. Reviewers use this list to
decide where to drill.

---

## 6. Scope and ownership

Each spawned worker owns a **tight, named scope**:

- State the scope in the spawn prompt as a bullet list: "I will touch files A,
  B, C. I will not touch X, Y, Z."
- Stage and commit **only** files in your scope. Never bundle unrelated edits.
- If you discover a needed change outside your scope, **report it** in the
  artifact's `open_questions[]` rather than editing it.
- Conflicts with another in-flight worker → do not stomp. Report the conflict
  with file paths and let the root session arbitrate.
- **Workspace isolation**: each worker operates in its own git worktree at
  `$TMPDIR/swarm-$USER/<repo>-<short-sha>/wt-<label>/`. The root session
  **never** enters a worker worktree. Cross-worker reading happens via
  `git show <branch>:<file>` or `git diff main..<branch>`. Spawn prompts MUST
  include the worktree path, base commit SHA, and worker branch.

Multiple workers editing the same file is allowed **only** if their changes are
on non-overlapping lines **and** they operate in separate worktrees. When in
doubt, serialize.

---

## 7. Verification before claiming done

A worker must run the project's actual gates on its slice, not hand-wave:

- Type checks (`tsc --noEmit` / equivalent for the language).
- Linter (project's actual linter, not generic ESLint).
- Tests (run the project's test runner against changed files).
- Build (when changes touch build config, native deps, or asset pipeline).

Report results verbatim in the artifact's `validation` field. "Looks good" is
not validation. If a gate cannot be run (e.g. env missing), say so explicitly
and downgrade `confidence` accordingly.

For changes to shared infrastructure (build, CI, deps), require an end-to-end
verification — not just "tests pass on my slice".

---

## 8. Decomposition patterns

Prefer this decomposition order:

1. **Task-graph (DAG)** when there are 3+ nodes with explicit dependencies.
   Use `task_graph` then `expand_node` for sub-tasks and `complete_node` for
   handoffs. Lets the system enforce gating and ordering.
2. **Parallel ad-hoc spawn** when 2-4 independent tasks with no dependencies.
   Single `assign_next` / `fill_slots` loop, no DAG needed.
3. **Sequential** when dependencies are tight or work is small.

For deep mode, the spawner may decompose further only when it materially
improves coverage. Decomposition for its own sake creates coordination debt.

---

## 9. Anti-patterns

- **Spawning for trivial work.** Spawning is overhead. A 5-line fix in one file
  should not become a 3-agent swarm.
- **Spawning to "look thorough".** More agents ≠ better answer. Three workers
  guessing at the same thing is worse than one worker who knows.
- **Deep nesting in light mode.** Workers spawning workers in light mode is
  rejected. Don't try to bypass by phrasing the spawn as a "review".
- **Bundling unrelated changes in one commit.** Each scope owns its commits.
- **Reporting `confidence: "high"` without a real check.** The closed feedback
  loop must name a concrete observation, not "looks correct".
- **Asking the user to clarify scope mid-flight.** If the scope is ambiguous,
  stop and ask the root session (or the user) **before** starting work.
- **Using channels/broadcast for status updates.** Use DMs and `report`.
- **Forgetting `label`.** The tool rejects, but the retry wastes a turn.

---

## 10. Memory and context

Spawned workers should:

- `memory recall` early in the session for project-specific facts that the
  root session has already established.
- `memory remember` (with `scope: "project"` and a `tag`) for facts that
  future workers will also need.
- Never overwrite a `project`-scope memory without first `recall`ing the
  existing entry to confirm the new value is consistent.

Facts that belong in project memory:
- Branch / merge conventions.
- Required CI gates and what counts as passing.
- Architectural invariants (e.g. "all timers go through service X").
- Forbidden patterns and why.
- Naming conventions for new modules.

Facts that do **not** belong in memory:
- Implementation details of a single task (use the artifact instead).
- Anything derivable from the codebase in < 30 seconds.
- Anything secret / credential-shaped.

---

## 11. Workspace isolation via git worktree

Swarms above ~2 concurrent workers collide on shared working trees (silent
`git add` loss, `git status` cross-contamination, half-baked mixed reads).
The fix: each worker gets a dedicated git worktree. Root session integrates.

### Topology

```
main worktree (root session, integration only)
$TMPDIR/swarm-$USER/<repo>-<short-sha>/
    ├── wt-<label-1>/  ← worker 1
    └── wt-<label-2>/  ← worker 2
```

### Allocation

- **1 worker : 1 worktree**, no sharing, no nesting
- Path: `$TMPDIR/swarm-$USER/<repo>-<short-sha>/wt-<label>/`
  - `$TMPDIR` falls back to `/tmp` on Linux; per-user on macOS; `%TEMP%` on Windows
  - `<short-sha>` = base commit 7-char SHA (fork origin)
- Branch: `feat/<name>_<short-sha>` / `fix/<name>_<short-sha>` /
  `chore|docs|refactor|test/<name>_<short-sha>`. Same `<short-sha>` across
  same-origin workers.
- **Root session never enters a worker worktree.**

### Lifecycle

- Spawn: root builds worktree + branch + dep symlinks **before** handing off prompt
- `ready`: worktree + branch persist
- `blocked`: worktree persists for inspection
- Root merge success: `git worktree remove` + `git branch -D`
- Worker timeout / abort: worktree persists for **8 hours**, cleaned by root
  before next spawn (`.jcode/worktree-manifest.json` is the source of truth)

### Dependency link (manual, not install)

Workers **never run package managers** (pnpm / yarn / cocoapods may be
missing). Symlink heavy in-repo deps from main worktree; rely on user-level
caches for the rest.

- `node_modules`, `ios/Pods`, similar heavy in-repo dirs: symlink from main
- `~/.gradle`, npm cache, `~/.cargo`: already shared, no action
- New dep needed: worker reports via `open_questions[]`, root installs in
  main, worker re-links. **Never** install inside worker worktree.

### Cross-worker visibility

Default: invisible. Workers see only base commit state.

When worker A needs worker B's output: A reports `open_questions[]`, root
decides to merge B → base → rebase A, or serialize.

Workers **never merge each other directly** — that pollutes history with
noise commits.

### Fallback

Spawn context without `.git/`: skip worktree allocation, worker uses root
cwd. swarm-prompt must flag this fallback explicitly, never pretend a
worktree exists.

### Safety target (per session)

Loss rate = `(dispatched - landed) / dispatched`, where `dispatched` is spawn calls and `landed` is branches root merged with green gates. Target 0%, hard ceiling 3%. Above ceiling, pause and run `scripts/conflict-detect.py all`. TDD covers single-slice correctness; the framework covers multi-slice safety. Both are required.

Per-repo config at `.jcode/conflict-config.yaml` (lockfile list, heartbeat TTL, ignored paths).

---

## 12. Liveness: worker-driven heartbeat + root responsiveness

The framework has **no watchdog, no enforced timer, no real-time
deadline**. Every "X minutes" in this section is a **soft contract** —
LLM-followed discipline, not runtime-enforced. Be honest about the
boundary.

The contract is **two-sided** but liveness is **worker-driven**:
workers make themselves observable; root responds when woken.

### The artifact contract (unchanged)

Every worker commit on `<worker_branch>` **must** embed a typed artifact
in the commit body. The artifact is the worker's self-report at the
moment of commit, and it is the primary signal root uses to reason
about worker state.

Required structure (single fenced JSON block at the bottom of the
commit body):

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
that completes the spawn scope (paired with `complete_node` / `report`).

### Worker obligations (liveness source)

Three concrete rules; see `docs/HEARTBEAT.md` for the rationale:

1. **Heartbeat channel ≤ 5 min.** Within any 5-minute window during a
   task, the worker MUST emit at least one of:
   - a `progress` commit (preferred — durable + auditable),
   - `dm <root> --delivery=notify` with payload
     `{"type":"heartbeat","step":"...","elapsed_min":N}`,
   - `report` with a typed body.
   Two consecutive misses = contract violation; root is allowed to
   treat the worker as abandoned.
2. **Stuck self-escalation ≥ 3 min.** If the worker has not made
   substantive forward progress for 3 minutes, it MUST
   `dm <root> --delivery=interrupt` with payload
   `{"type":"stuck","reason":"...","help_needed":"..."}`.
   Silence is not an option.
3. **Self-alarm (recommended).** On spawn, the worker SHOULD
   `schedule(target=resume, wake_in_minutes=4, task="if still running,
   commit progress + dm heartbeat")`. Self-reminder; wakes the worker,
   worker self-checks, worker emits the heartbeat. Free if the worker
   is already active.

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

### Root obligations (responsiveness, soft)

1. **Priority on `{"type":"stuck"}` and `follow_up`.** When a worker
   reports stuck or asks for help, root SHOULD respond with `dm`
   within the current context (information, scope expansion, or
   `stop`). There is **no hard deadline** — root is an LLM session.
   The worker exit right above is the safety valve.
2. **No scheduled self-wakeup.** Root MUST NOT call
   `schedule(target=resume, wake_in_minutes=N)` for the purpose of
   "checking on workers". The previous scheduled self-wakeup design
   was removed because it added 8 minutes of latency to every spawn
   without helping root notice workers any faster than the worker's
   own handoff. There is no `schedule(target=resume, wake_in_minutes=N)`
   on the spawn path.

   **Exception (cross-swarm contexts).** If root is known to be in a
   cross-swarm state — i.e., any active worker has `blockers[]`
   containing `cross-swarm: dm channel unreachable` — root may use
   `schedule(target=ambient, ...)` if the runtime supports it. The
   5-min forced-tick is NOT available otherwise; root relies on the
   next natural wakeup to surface silent dead workers.
3. **Mandatory passive inspection at every decision point.** Workers
   emit two signals on completion: a durable commit (with embedded
   artifact) and a live handoff (`complete_node` / `report`). The two
   are not redundant — the commit is auditable from `git show`, the
   handoff wakes root. Either may be lost: commits survive worker
   death but not user-invisible state; live handoffs do not survive
   cross-swarm boundaries or worker crashes between commit and
   `complete_node`. **Root MUST inspect** every active
   `<worker_branch>` via `git log <branch> --format=%B` at each of:
   - **a user message arrives** — before composing the next action;
   - **a worker handoff arrives** — to cross-check the handoff against
     the commit's artifact (artifact SHA must equal `HEAD` of branch;
     `type` must be `final`, not `progress`);
   - **root's natural reflection between actions** — between finishing
     one integration step and starting the next — `git log <branch>`
     must show at least one progress commit per active worker since
     the previous decision point; otherwise the worker is silently
     stuck even without a `stuck` dm (see Turn 5 in
     `docs/LIVENESS_VALIDATION.md`).

   Decision points are moments when root is already awake and
   processing — not a forced schedule. **This is aspirational, not
   enforceable.** LLM sessions have no real-time timer; root cannot
   force itself to wake on a fixed cadence. Silent dead workers are
   caught on the next wakeup, not on a 5-min clock.
   This is not a poll — it is a passive read. Cost: one tool call per
   branch per decision point. The `last_heartbeat` field in
   `.jcode/worktree-manifest.json` is the worktree-cleanup detector;
   it does not satisfy this obligation.
4. **Smart Postman tick.** When the passive inspection surfaces a
   silent or dead worker, root MUST run a one-shot
   `python3 scripts/swarm-state-monitor.py tick` and act on the
   classification table. The script is the structured replacement for
   ad-hoc `git log` polls. See §13 for the full protocol.

### Inspection-confirmation gate (avoid premature re-dispatch)

To avoid hindering a worker that is still legitimately working, root
MUST NOT re-dispatch, reset, or spawn a recoverer based on a single
silent/dead classification. The protocol:

1. **First observation** (postman tick returns `silent` or `dead`):
   root notes the observation. No action yet — worker may be doing
   long-running work.
2. **Second observation** (next postman tick, after root has done
   intervening work): root runs `tick` again. If the classification is
   still `silent` or `dead`, increment the confirmation counter.
3. **Third observation confirms unhealthy state**: NOW root has enough
   signal to spawn a recoverer (see §13). Pick the recovery action
   below.

This is **not** a fixed timer. "Three observations" means three actual
postman ticks at three separate decision points — not three rounds of
`tick` in a tight loop. Slow workers get more time; the gate is about
avoiding *false positives*, not about being fast.

### Three recovery actions (only after 3+ confirmations)

1. **Continue.** Worker has a specific blocker only you can answer
   (missing decision, missing info, scope ambiguity). Reply via `dm`
   with the concrete answer; worker resumes. Cheapest option; use
   when the work is on track and the blocker is small.

2. **Reset.** Worker is fundamentally stuck — wrong scope, dead-end
   approach, conflicting requirements. `stop` the worker. Spawn a
   fresh worker with corrected scope, optionally prepended with
   `git show <old_branch>:<files>` to preserve any useful partial
   work. Use when continuing would waste more tokens than starting
   fresh.

3. **Recover.** Worker died (OOM, killed, network drop) before
   `complete_node`. The branch has progress commits but no final.
   Spawn a `recoverer` worker (§13) with the recovery context:
   `git log <branch> --format=%B` to read the latest artifact's
   `next:` field, then `assign_task` with explicit
   "classify and finish/salvage/dead". The recoverer returns a
   `finishable / salvageable / dead` classification.

### Why worker-driven, not heartbeat daemon

| Concern | Heartbeat daemon | Worker-driven liveness |
|---|---|---|
| Survives server restart | No (in-memory) | Yes (commits survive; `git show` recovers) |
| Survives worker death | No | Yes (final commit's artifact reconstructs handoff) |
| Proves work happened | No (only "alive") | Yes (artifact has step + findings) |
| Cost | Per-worker timer + manifest writes | Worker self-discipline; ~0 infra |
| Cross-worker visibility | Root only (manifest is private) | Anyone with `git show` |
| Honors honest silence | No (treats as failure) | Yes (long thinking is allowed; report says so) |

The `last_heartbeat` field declared in `.jcode/worktree-manifest.json`
is a **passive** detector for the worktree cleanup safety net. It is
**not** the primary liveness signal. The primary signal is the latest
commit on `<worker_branch>` and its embedded artifact, supplemented by
worker `dm` heartbeats and `{"type":"stuck"}` escalations.

### What the framework CANNOT guarantee

Out-of-band; only runtime changes (added in a future jcode) could fix:

- Real-time detection of a truly dead worker (OOM, network partition,
  worker process killed without flush). Neither heartbeat nor
  stuck-escalation can fire. Recovery is `git show <branch>` on root's
  next conscious turn.
- Root response time (root is an LLM).
- Worker honesty (root cross-checks artifact against diff + tests).

### Failure modes the contract catches

- **Worker stuck on a hard step** — emits `{"type":"stuck"}`. Root
  `dm`s back, expands scope, or stops.
- **Worker silent because busy thinking** — mid-task `progress` commit
  or heartbeat dm keeps root informed.
- **Worker hung on long test / install** — self-alarm `schedule` fires,
  worker self-checks, emits heartbeat or stuck dm.
- **Worker honest-but-too-quiet** — two consecutive 5-min heartbeat
  misses; worker exit right; root treats as abandoned.
- **Root did not respond to stuck** — 5 min since `{"type":"stuck"}`;
  worker `report status: abandoned`.
- **Worker dies after committing but before reporting** — final commit's
  artifact is `type: "final"`. Root recovers via `git show`. No data loss.
- **Worker reports "done" but commit is missing** — root rejects artifact;
  worker must commit before claim is honored.
- **Server restart kills worker session** — git state is unchanged. On
  next root session, the latest commit + artifact reveal state.
- **Worker committed final but did not call `complete_node`** — commit
  carries `type: "final"` artifact, no live handoff arrives. Root's
  mandatory passive inspection (§12 root obligation 3) catches it on
  the next decision point: `git log <branch>` shows `final` + 0 newer
  commits → integrate or surface to user. The durable half survived
  without the live half.
- **Cross-swarm handoff** — worker and root are in different swarms; dm
  channel is unreachable from worker side. Worker commits and
  `open_questions[]` mentions `cross-swarm, commits-only`; root's
  passive inspection sees the commit and integrates. See
  `docs/HEARTBEAT.md` §"Cross-swarm handoff gap".

### Anti-patterns

- Don't skip the artifact block "because it's just a WIP commit". WIP commits
  are precisely the ones the root needs to see during long tasks.
- Don't put the artifact in the commit *subject* — keep it in the body so
  `git log --oneline` stays readable.
- Don't use a single fenced block that mixes JSON and prose; the parser
  will choke on stray braces. Use a clean JSON object.
- Don't poll `swarm status <session>` more than once per minute — runtime
  status lags reality and adds noise.
- Don't `dm` root "just to check in" — heartbeats are LLM-disciplined;
  random dms add noise to root's queue.
- Don't silently wait forever after emitting `{"type":"stuck"}` —
  exit right exists for a reason. 5 minutes and out.
- Don't trust `status: ready` from a worker that has no commit on its
  branch. Reject the artifact; require the commit first.

---

## 13. Smart Postman: root-side tick protocol

The Smart Postman is the **operating rhythm** of root. It is not a
worker, not a daemon, not a watchdog. It is a **tick protocol** that
root runs inline at decision points to take the "wait and see" out of
"wait and see what the worker is doing".

### Why this exists

The previous architecture asked root to "passively inspect" at every
decision point (§12 root obligation 3). That works for **healthy**
workers but fails for **silent** and **dead** workers, where root
either keeps waiting or makes a one-off `git log` call by hand. The
Smart Postman replaces ad-hoc inspection with a structured tick:

```
python3 scripts/swarm-state-monitor.py tick
```

The script returns a single classification table — `healthy /
progressing / quiet / silent / dead` — for every active worker
branch. Root reads the table once and acts.

### Tick cadence

The tick is **not** on a fixed timer. Root runs it at decision points:

- **User message arrives** — before composing the next action.
- **Worker handoff arrives** — to cross-check.
- **Root's natural reflection between actions** — between finishing
  one integration step and starting the next.
- **Per-task natural break** — when root is about to integrate or
  spawn something new.

Decision points are moments when root is already awake and
processing — not a forced schedule. **This is aspirational, not
enforceable.** LLM sessions have no real-time timer; the tick fires
on the next wakeup, not on a 5-min clock. Idling for hours on a
known-silent worker is no longer acceptable; the postman tick forces
periodic re-classification whenever root is awake and processing.

### Tick output

The script prints a table plus a JSON block. Example:

```
branch                                            class            age  artifact    conf      rationale
feat/liveness-hardening                           silent          542m  final       high      final commit 542m ago, no handoff, past silent SLA
feat/swarm-artifact-liveness_b1d4bb6              dead           1514m  —           —         commit 1514m ago without artifact, past dead SLA
```

Root's output discipline:

1. **Read the table once** — paste the worst-classified branch into
   the next prompt as context.
2. **Decide per branch** — `healthy` and `progressing` need no
   action; `quiet` may need a `dm` heartbeat reminder; `silent` and
   `dead` enter the inspection-confirmation gate.
3. **Do not stay in the loop** — if the table has been
   `silent/dead` for ≥ 3 ticks, spawn a recoverer. Don't keep
   re-reading.

### Classification thresholds

Defaults: `quiet` ≤ 5min, `silent` 5-15min, `dead` > 15min for
`progress` artifact and > 30min for `final` without handoff.
Override via env vars:

- `POSTMAN_QUIET_MIN` (default 5)
- `POSTMAN_SILENT_MIN` (default 15)
- `POSTMAN_DEAD_MIN` (default 30)

Per-repo overrides belong in `.jcode/conflict-config.yaml` (future
work; MVP uses env vars).

### Recovery spawn (recoverer role)

When the inspection-confirmation gate passes (3 ticks silent/dead),
root spawns a **recoverer** worker (`swarm/roles/recoverer.md`):

```
spawn(
  label="recoverer",
  role="agent",
  model="MiniMax-M3",
  effort="medium",
  prompt="""
    Branch: <branch>
    Last commit: <sha>
    Last artifact: <type> (confidence=<c>)

    Classify the dead/silent branch and finish / salvage / dead it.
    Do not introduce new feature work.
    Run ./scripts/conflict-detect.py all before deciding.
    Run the project's gates on the partial state.
    Return a typed artifact with classification + suggested_action.
  """,
)
```

The recoverer is the only role that may amend the dead branch's
last commit (one amend only, residual fix only). Anything more
goes to a new commit.

### Why postman is inline, not a background task

A background postman would solve the "root waits in silence" problem,
but it would conflict with the framework's no-scheduled-self-wakeup
rule (§12 root obligation 2). The postman is **inline** because:

1. Root is already the one making decisions; co-locating the tick
   with decision points keeps "observe" and "decide" in the same
   context window.
2. jcode runtime may eventually add a `target=ambient` wake
   mechanism that suggests "postman tick?" without forcing root to
   sleep. That is a future extension, not MVP.
3. Inline ticks have no latency — root reads the table within the
   same prompt turn as the prior decision.

### Anti-patterns

- Don't run `swarm-state-monitor.py tick` more than once per decision
  point — that's a poll, not a tick. One call, classify, decide.
- Don't promote a `quiet` worker to `silent` based on a single
  observation. The 3-tick gate exists for a reason.
- Don't spawn a recoverer for a `healthy` worker. The postman table
  is the source of truth; do not act on vibes.
- Don't replace the table with hand-rolled `git log` calls. The
  script exists precisely to make that ad-hoc polling unnecessary.
- Don't override `POSTMAN_QUIET_MIN=0` to "always be quiet". That
  just means every worker classifies as silent — the table becomes
  useless.