<!--
This file IS the swarm policy. Routing and coordination are passed to
models as a prompt rather than as options in a standard config file.

Install target: ~/.jcode/swarm-prompt.md (symlinked from this file by
scripts/install.sh). jcode loads it when constructing spawn calls.
Per-project override: <cwd>/.jcode/swarm-prompt.md.
-->

# Swarm Policy (global)

Generic coordination rules for the root session and every spawned
worker. Project-specific overrides go in `<cwd>/.jcode/swarm-prompt.md`.

---

## 1. Model & effort routing

Pass `model` explicitly on every spawn. Pass `effort` explicitly too —
the two are independent levers (a quality-model worker can still run at
`low` effort for simple tasks; a fast-model worker at `high` effort is
rarely worth it).

A default routing table:

| Task kind                                                | Effort   |
| -------------------------------------------------------- | -------- |
| Bulk reading / summarization / context fetch             | `none`   |
| Mechanical implementation (typed, well-specified)        | `low`    |
| Doc rewrite / reformat / changelog                       | `none`   |
| Simple test scaffolding (existing patterns)              | `low`    |
| Cross-module refactor / migration                        | `medium` |
| Default worker (unspecified)                             | `medium` |
| Design, investigation, debugging, review, verification   | `high`   |
| Architecture / API design / trade-off analysis           | `high`   |

Choose model by availability. Run `swarm list_models` to confirm which
routes are reachable before pinning one in this table. **Never invent
model names** — verify with `list_models` first.

Rules:

- When the user names a specific model, pass it through (subject to
  availability check).
- **Fallback is fast, not iterative.** Before drafting a spawn prompt,
  run a 1-token auth probe of the chosen model (`extension.sh models
  probe <name>` is the bundle's helper). If the probe fails (auth
  error / unknown route), do NOT iterate on model names. **Omit
  `model`** on the next spawn — the worker inherits the coordinator's
  working model. One probed attempt, then default. Silent iteration is
  the most expensive anti-pattern in spawn hygiene: each failed spawn
  costs ~30s + a worktree.
- `effort: "max"` only when the user explicitly asked — it's
  expensive.
- If a previously unavailable route becomes available, update the
  routing table to match.

---

## 2. When to spawn (root session decides)

Spawn a worker when **all** of the following hold:

- Work is **independently verifiable** (the worker can run gates on
  its slice).
- Work touches **≥ 2 files** OR spans **≥ 2 unrelated areas** of the
  codebase.
- Work has **no strong ordering dependency** on another in-flight
  task.
- Parallel value is **clear**: wall-clock saving > coordination
  overhead.

Spawn for these specific shapes:

- Independent test suites against shared fixtures.
- Review + implementation in parallel (review starts as soon as first
  commit lands).
- Documentation sync + code change when doc is auto-generated or
  near-trivial.
- Multiple language/framework migrations on disjoint surfaces.
- Research, investigation, repo-mapping, architecture review.
- Migration of any single feature across ≥2 modules or directories.

Do **not** spawn when:

- Work is a single file or ≤ 2 lines of trivial change.
- Tasks have tight ordering (B depends on A's API shape).
- The work is a question / explanation / single grep.
- You are about to abort or redo the work within the next turn.

When in doubt: **spawn**. The bar to *not* spawn is strictly higher
than the bar to spawn. Serial execution is the exception, reserved for
the narrow "single file / ≤2 lines / one binary yes-no" shape above.
Spawning is for *every non-trivial task*, not just ceremony; the
throughput benefit compounds with focused attention you free up for
integration.

---

## 3. Spawn hygiene

Every spawn call **must** include:

- `label` — short, nonblank, describes role (e.g. `"api reviewer"`,
  `"test scaffolder"`). Missing label is rejected by the tool.
- `prompt` or `initial_message` — a concrete task, not "help with the
  project". An idle agent with no task wastes resources and confuses
  the swarm UI.
- `model` + `effort` — explicit unless inheritance is intentional.
- Worktree context — `worktree_path`, base commit SHA, worker branch
  (`feat/<name>_<short-sha>` / `fix/<name>_<short-sha>` / etc.).

Workers must **never** spawn their own children. If a worker thinks it
needs help, it reports back to the root with a `follow_up` listing the
missing capability, and the root decides.

---

## 4. Communication: prefer dataflow over chat

Use these primitives in this order of preference:

1. **`complete_node` with typed artifact** — primary handoff. Forces
   the worker to produce `status` plus `findings`, `evidence[]`,
   `edge_cases_considered[]`, `validation`, `open_questions[]`,
   `confidence`, and `what_i_did_not_check[]` (matching the overlay's
   invariant 4). The `status` field uses the 4-state enum — see §3
   discipline section in the overlay for the full meaning of each state.
2. **`dm` to a specific worker** — for follow-up questions or to
   assign more work to an existing agent.
3. **`broadcast` to your spawned subtree** — rare, only for genuine
   stop/recall events. Never for "FYI" chatter.
4. **`channel`** — discouraged legacy primitive. Prefer DMs and
   task-graph. Subscribe only when there's a durable shared concern.

Workers reporting back to root: use `report` action with
`status: "ready"` and a typed artifact. `status: "blocked"` requires a
`blockers[]` list.

---

## 5. Confidence and honesty

Every completion artifact **must** declare `confidence: low | medium | high`.

- `high` — work fully verified against an explicit check (test, lint,
  typecheck, manual reproduction). All edge cases enumerated.
- `medium` — work verified against a subset of checks; some uncertainty
  remains about edge cases the worker did not enumerate.
- `low` — work partially done, or verification relied on the worker's
  judgment rather than an observation. Must be reported honestly.
  Two cases that are always `low`:
  - Discovered dependencies outside the spawn scope that were left
    unhandled (e.g., user asked to delete a facade, you found 3
    production call sites still using the old import).
  - A new public API does not match the call-site usage patterns it is
    meant to serve (must explicitly explain why this is correct,
    otherwise it does not count as `low`).

`low` is **not** failure — it routes follow-up work automatically. The
`what_i_did_not_check[]` list is mandatory: "Nothing" is only valid
when truly exhaustive. Reviewers use this list to decide where to
drill.

---

## 6. Scope and ownership

Each spawned worker owns a **tight, named scope**:

- State the scope in the spawn prompt as a bullet list: "I will touch
  files A, B, C. I will not touch X, Y, Z."
- Stage and commit **only** files in your scope. Never bundle
  unrelated edits.
- If you discover a needed change outside your scope, **report it** in
  the artifact's `open_questions[]` rather than editing it.
- Conflicts with another in-flight worker → do not stomp. Report the
  conflict with file paths and let the root session arbitrate.
- **Workspace isolation**: each worker operates in its own git worktree
  at `$TMPDIR/swarm-<user>/<repo>-<short-sha>/wt-<label>/`. The root
  session **never** enters a worker worktree. Cross-worker reading
  happens via `git show <branch>:<file>` or
  `git diff main..<branch>`. Spawn prompts MUST include the worktree
  path, base commit SHA, and worker branch.

Multiple workers editing the same file is allowed **only** if their
changes are on non-overlapping lines **and** they operate in separate
worktrees. When in doubt, serialize.

---

## 7. Verification before claiming done

A worker must run the project's actual gates on its slice, not
hand-wave:

- Type checks (`tsc --noEmit` / equivalent for the language).
- Linter (project's actual linter, not generic ESLint).
- Tests (run the project's test runner against changed files).
- Build (when changes touch build config, native deps, or asset
  pipeline).

Report results verbatim in the artifact's `validation` field. "Looks
good" is not validation. If a gate cannot be run (e.g. env missing),
say so explicitly and downgrade `confidence` accordingly.

For changes to shared infrastructure (build, CI, deps), require an
end-to-end verification — not just "tests pass on my slice".

---

## 8. Decomposition patterns

Prefer this decomposition order:

1. **Task-graph (DAG)** when there are 3+ nodes with explicit
   dependencies. Use `task_graph` then `expand_node` for sub-tasks and
   `complete_node` for handoffs. Lets the system enforce gating and
   ordering.
2. **Parallel ad-hoc spawn** when 2-4 independent tasks with no
   dependencies. Single `assign_next` / `fill_slots` loop, no DAG
   needed.
3. **Sequential** when dependencies are tight or work is small.

For deep mode, the spawner may decompose further only when it
materially improves coverage. Decomposition for its own sake creates
coordination debt.

---

## 9. Anti-patterns

- **Spawning for trivial work.** Spawning is overhead. A 5-line fix
  in one file should not become a 3-agent swarm.
- **Spawning to "look thorough".** More agents ≠ better answer.
  Three workers guessing at the same thing is worse than one worker
  who knows.
- **Bundling unrelated changes in one commit.** Each scope owns its
  commits.
- **Reporting `confidence: "high"` without a real check.** The closed
  feedback loop must name a concrete observation, not "looks correct".
- **Asking the user to clarify scope mid-flight.** If the scope is
  ambiguous, stop and ask the root session (or the user) **before**
  starting work.
- **Using channels/broadcast for status updates.** Use DMs and
  `report`.
- **Forgetting `label`.** The tool rejects, but the retry wastes a
  turn.

---

## 10. Memory and context

Spawned workers should:

- `memory recall` early in the session for project-specific facts
  that the root session has already established.
- `memory remember` (with `scope: "project"` and a `tag`) for facts
  that future workers will also need.
- Never overwrite a `project`-scope memory without first `recall`ing
  the existing entry to confirm the new value is consistent.

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

Swarms above ~2 concurrent workers collide on shared working trees
(silent `git add` loss, `git status` cross-contamination, half-baked
mixed reads). Each worker gets a dedicated git worktree. Root
integrates. 1 worker : 1 worktree, no sharing, no nesting.

**Canonical layout + per-status lifecycle + root responsibilities**:
see `~/.jcode/prompt-overlay.md` §4.1 + §4.3. Worker perspective
below.

### Dependency link (manual, not install)

Workers **never run package managers** (pnpm / yarn / cocoapods may
be missing). Symlink heavy in-repo deps from main worktree; rely on
user-level caches for the rest.

- `node_modules`, `ios/Pods`, similar heavy in-repo dirs: symlink
  from main
- `~/.gradle`, npm cache, `~/.cargo`: already shared, no action
- New dep needed: worker reports via `open_questions[]`, root
  installs in main, worker re-links. **Never** install inside worker
  worktree.

### Cross-worker visibility

Default: invisible. Workers see only base commit state.

When worker A needs worker B's output: A reports `open_questions[]`,
root decides to merge B → base → rebase A, or serialize.

Workers **never merge each other directly** — that pollutes history
with noise commits.

### Fallback

Spawn context without `.git/`: skip worktree allocation, worker uses
root cwd. swarm-prompt must flag this fallback explicitly, never
pretend a worktree exists.