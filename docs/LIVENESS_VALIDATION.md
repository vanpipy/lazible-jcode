# Liveness contract validation findings

5-turn interactive validation of the worker-driven liveness contract
(`dd34a14` + `067af2d`).

## Setup

Each turn walks through one scenario as a step-by-step trace with
timestamps, decision points, and verdict. The contract lives in:

- `docs/HEARTBEAT.md` — full contract and rationale
- `swarm/swarm-prompt.md` §12 — worker obligations / root obligations /
  cannot-guarantee
- `swarm/prompt-overlay.md` §1 — root-side responsiveness + passive
  worktree inspection recommendation
- `swarm/roles/*.md` — role-specific heartbeat / stuck / exit-right
  guidance

## Turns

### Turn 1 — Trivial short task (60s reviewer)

- Worker reads diff, writes verdict, commits, reports ready.
- Final commit doubles as heartbeat; no intermediate commit needed.
- Self-alarm scheduled at spawn (1 tool call); never fires because
  worker finishes first.
- No stuck escalation; no root polls.
- Overhead: ≤1 tool call. **Verdict: PASS.**

### Turn 2 — Worker stuck ≥ 3 min on segfaulting test

- Worker writes code, runs `cargo test`, gets SIGSEGV.
- Retries 3× with same result. Identifies deterministic crash.
- Emits `dm --delivery=interrupt {"type":"stuck","options":[...4 paths...]}`
  + self-alarm.
- Root replies "bisect main" (1 word). Worker resumes, finds
  pre-existing segfault in unrelated commit, ships fix.
- **Verdict: PASS.** Structured options enable 1-word root reply.

### Turn 3 — Long productive task (14 min, 6 progress commits)

- 6 commits over 14 min, all within 5-min heartbeat SLA.
- 2 self-alarms fired, both no-ops (recent commits).
- No stuck dm — slow progress is correctly distinguished from no
  progress.
- **Verdict: PASS.** Progress commits are durable heartbeats.

### Turn 4 — Abandonment after root "ack, hold"

- Worker stuck dm emitted at T=200s. Root replies "ack, will get to it"
  (no concrete next step).
- Per the `067af2d` refinement, bare ack does NOT count as concrete
  next step and does NOT extend the 5-min window.
- Worker self-alarm fires at T+4 min, finds no concrete next step.
- Worker exits at T+5 min with `report status: abandoned` carrying
  worktree state, branch, and "next action for root" handoff.
- Root later spawns fresh worker with explicit continuation scope.
- **Verdict: PASS.** Refinement prevents indefinite hang; clean handoff.

### Turn 5 — Worker OOM-killed at T=6 min

- Worker makes 2 progress commits, then OOM-killed mid-task.
- No final commit, no `complete_node`, no dm.
- Per the `067af2d` refinement, root does passive
  `git log <branch>` once per session.
- Root sees last commit's `{"type":"progress",...}` artifact with
  >5 min age and no subsequent `final`. Verdict: silently stuck.
- Root decides (resume / salvage / discard) based on partial work.
- Resume path: fresh worker reads branch state via
  `git show <branch>:<file>` + `git log --format=%B`, continues from
  the embedded "next" step.
- **Verdict: PASS.** Passive inspection recovers state cheaply.

## Net

5/5 turns green. The contract is robust across trivial, productive,
blocked, abandoned, and dead-worker scenarios. The two refinements
landed in `067af2d` (concrete next step + passive inspection) were
the gaps that would have caused false-positive escalation or silent
data loss without them.

## Honest non-guarantees (per `dd34a14`)

- Framework cannot detect truly-dead workers without worker cooperation.
- Root response time is a soft obligation, no hard deadline.
- Worker honesty assumed (good-faith cooperation).
- 8-hour worktree TTL is the cleanup safety net.