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