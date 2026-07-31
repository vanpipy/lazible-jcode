---
name: auto-swarm-planner
description: Detect when a coding task is worth fanning out to multiple agents (multi-file refactor, cross-cutting feature, parallel investigation), draft a plan, get user approval, spawn workers via the `swarm` tool, coordinate via DMs + task graph, integrate with project gates. Use when the user asks for parallel work, multi-agent collaboration, or when the auto-trigger criteria (≥ 3 files + ≥ 2 independent subtasks + clear parallel value) match.
skill-type: orchestration
version: 1.0
type: skill
skill-role: guidance
---

# auto-swarm-planner

**Description:** Detect when a coding task is worth fanning out to multiple agents (multi-file refactor, cross-cutting feature, parallel investigation), draft a plan, get user approval, spawn workers via the `swarm` tool, coordinate via DMs and typed handoff artifacts, and integrate results through the project's existing gates.

Coordinator skill for the `swarm` tool. Detects parallelizable tasks, plans fan-out, spawns workers, coordinates via DMs and typed handoff artifacts, and integrates results through the project's existing gates.

## When to Use

Apply when **all** of these hold:

- The task touches ≥ 3 files, modules, or independent subsystems
- It decomposes into ≥ 2 logically independent subtasks (no circular deps)
- Parallel execution would clearly beat serial (wall-clock reduction ≥ 30%)

Skip if:

- Single file or ≤ 2 small edits — direct execution is faster
- Hard sequential dependency (B strictly waits on A's output)
- A single agent's context already covers everything

## Slash Command

```
/auto-swarm-planner <task>
```

Examples:

```
/auto-swarm-planner refactor pricing engine across 4 modules
/auto-swarm-planner audit auth + payment + inventory for race conditions
/auto-swarm-planner split this into parallel PRs
```

## Mode Indicator

```
[MODE: auto-swarm-planner] (detecting | proposing | coordinating | integrating | reporting)
```

| Phase | Enter when | Focus |
|-------|-----------|-------|
| `detecting` | "is this swarm-shaped?" | Score 3 axes; gate the decision |
| `proposing` | Decision = yes | Plan + ask permission in chat |
| `coordinating` | User says yes | Spawn + monitor + sync |
| `integrating` | All workers report ready | Merge artifacts, run project gates |
| `reporting` | Integration done | Single distilled message to user |

## 1. Detection (3-axis score)

Before deciding "swarm", score the task:

| Axis | Threshold | How to check |
|------|-----------|--------------|
| **File spread** | ≥ 3 files | `git status -sb`, `git diff --stat` |
| **Logical split** | ≥ 2 independent | Subjective; argue in proposal |
| **Parallel value** | ≥ 30% wall-clock reduction | Heuristic; if sequential ≈ parallel, don't swarm |

If any axis fails, do the work directly. Swarm overhead (~10s setup + ~5s/agent teardown per worker) is not free.

## 2. Proposal & Permission

Before any `swarm.spawn`, present the plan and ask the user to confirm:

```
Plan: <one-sentence rationale>
Subtasks:
  A. <worker-1-label>: <scope + deliverable>
  B. <worker-2-label>: <scope + deliverable>
  …
Models (per swarm-prompt routing guide):
  - explore / debug / review / verify -> claude-api:claude-fable-5
  - implement                          -> gpt-5.5 (effort: low)
  - bulk read / summarize             -> gpt-5.5 (effort: none)
Coordination:
  - mode: light (simple fan-out) | deep (gated DAG with critique/verify nodes)
  - DMs only; no broadcast / channels for ordinary sync
Conflicts: <where workers may collide + mitigation>
Gates the integrator will run after workers finish:
  - <project-specific gates, e.g. tsc / lint / jest>
  - <scope guards, e.g. v12-v14>
Approve? (y / adjust / cancel)
```

**No `request_permission` tool exists** in this environment — ask in plain chat. Do not spawn until the user replies `y` (or equivalent).

## 3. Coordination

### 3.1 Pre-flight

```text
swarm action=list_models        # confirm available routes for this env
git status -sb && git diff --stat
```

### 3.2 Spawn workers

Per subtask:

```
swarm action=spawn
  label        = "<short role>"      # required; shown in UI chip
  prompt       = "<concrete task>"   # never spawn empty
  model        = "<see Phase 2>"
  effort       = "<see Phase 2>"
  working_dir  = "<absolute path>"
  spawn_mode   = inline | headless   # inline renders gallery viewport
```

**Hard constraints** (from the `swarm` tool itself):

- Only the root session may `spawn` in normal / light mode. Workers report back; they do not spawn grandchildren.
- Spawning without `prompt` creates an idle agent — always include the initial task.
- Each spawn returns a session id. Store it for later `dm` / `status` / `stop`.

### 3.3 Track work via task graph (recommended)

`swarm.action=task_graph` with `mode=light` (simple fan-out) or `mode=deep` (gated DAG with critique / verify nodes).

Each node:

```
{
  id:         "pricing-gate-impl",
  content:    "Implement app/hooks/pricingGate.ts per the spec",
  kind:       "implement",            // explore | implement | verify | fix | synthesize
  depends_on: ["pricing-spec"],       // prerequisite ids
  priority:   1                       // scheduling hint
}
```

### 3.4 Require typed handoff artifacts

When a worker reports back, require a structured `complete_node` artifact:

```
{
  findings:              ["..."],     // concrete results
  evidence:              ["file:line", "log snippet"],
  edge_cases_considered: ["..."],
  validation:            "tsc + lint + jest green; covered paths: 13/14",
  open_questions:        ["..."],
  confidence:            "high",      // or "low" — report honestly
  what_i_did_not_check:  ["..."]      // routes follow-up work
}
```

**Deep-mode gates** refuse to close while any sibling has `confidence: low`. Either `inject_gap` to add a fix node, or list the low-confidence id in `findings` so the gate accepts close.

### 3.5 Communication discipline

| Use | Avoid |
|-----|-------|
| `dm` (`to_session`) for point-to-point | `broadcast` for ordinary chatter |
| `complete_node` artifact for handoff | `channel` posts as a coordination bus |
| `await_members` for sync points | Polling `status` repeatedly |
| `share` / `share_append` for tiny cross-worker state | Repo + typed artifacts as the medium |

`broadcast` is reserved for whole-subtree events (e.g. abort).

## 4. Integration

When every worker reports `ready` / `completed`:

1. **Pull artifacts** — every `complete_node` finding + every diff
2. **Resolve conflicts** — workers may have edited the same file; coordinate via DM, never silently overwrite
3. **Run the project's 3-gate check** (see `git-expert` §2.1: `tsc`, `npm run lint`, `jest --no-coverage`)
4. **Run project-specific gates** (e.g. QiPDA v12-v14 scope guards) — only on a clean tree; `git stash --include-untracked` if needed
5. **Re-verify `low` confidence** — if any worker reported low confidence on a path the user cares about, gate won't close; address or explicitly document

## 5. Report

Collapse all worker output into one user-facing message:

- What was done (file paths, commits if any)
- What was NOT done (`open_questions`, gaps)
- Confidence per subtask
- Next step (commit / PR / re-test / hand back to user)

Do **not** paste raw worker transcripts — distill.

## Interaction with Other Skills

| Companion | When loaded together |
|-----------|----------------------|
| `/git-expert` | Phase 4 commits go through git-expert gates |
| `/rn-dev` | Each worker still follows rn-dev (modular arch, gates, anti-patterns) |
| `/optimization`, `/todo-planning-skill` | Use for sub-tasks inside individual workers |

`git-expert` and `rn-dev` remain single-agent by design — they describe per-file / per-worker rules. `auto-swarm-planner` is the **only** layer that fans out.

## Anti-Patterns

| ❌ Don't | ✅ Do |
|----------|-------|
| Spawn "to explore" with empty prompt | Every spawn carries a concrete task |
| Swarm for ≤ 2 trivial edits | Do it yourself |
| `broadcast` for normal sync | `dm` to specific session |
| Channel / shared-context as coordination bus | `complete_node` artifact |
| Let workers edit the same file blind | Pre-assign files; coordinate via DM |
| Skip the 3-gate check after workers finish | Integrator runs gates |
| Report low confidence as "done" | Fix it or surface it to the user |
| Use swarm for git-expert commit flows | git-expert is single-agent by design |
| Spawn children inside a worker | Only the root session spawns |

## Quick Reference

```text
# Detection
git status -sb              # file spread
git diff --stat             # change size
git log --oneline -5        # context

# Pre-flight
swarm action=list_models    # confirm routes

# Spawn (one per subtask)
swarm action=spawn label="..." prompt="..." model="..." effort="..." working_dir="..."

# Track
swarm action=task_graph mode=light|deep nodes=[...]
swarm action=assign_task target_session="..." task_id="..."
swarm action=await_members mode=all

# Close
swarm action=complete_node node_id="..." artifact={...}

# Cleanup
swarm action=cleanup
```

## Tips

- Prefer `mode=light` unless you need gated critique / verify nodes
- `confidence: low` is a request for help — address before reporting done
- `deep` mode is the only one that supports `expand_node` / `inject_gap`; `light` is faster but less rigorous
- Give every worker the full project context (AGENTS.md summary, current branch, expected gates) in the spawn prompt — they start cold
- After a swarm run, run `swarm action=cleanup` to release idle agents