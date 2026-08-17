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
- Worktree context — **for worktree-using roles** (`implementer`,
  `test-writer`, `doc-writer`) include `worktree_path` plus base
  commit SHA and worker branch (`feat/<name>_<short-sha>` /
  `fix/<name>_<short-sha>` / `test/<name>_<short-sha>` /
  `docs/<name>_<short-sha>` / `refactor/<name>_<short-sha>`). **For
  root-cwd roles** (`reviewer`, `investigator`, `migrator`) omit
  `worktree_path`; still pass `worker_branch` (root checks it out in
  root cwd for `migrator`) and `base_commit` (the SHA the worker's
  branch was cut from).

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
- **Workspace isolation** (role-dependent — see overlay §0 for the full
  picture):
  - **Worktree-using roles** (`implementer`, `test-writer`, `doc-writer`):
    each operates in its own git worktree at
    `$TMPDIR/swarm-<user>/<repo>-<short-sha>/wt-<label>/`. The root
    session **never** enters a worker worktree. Cross-worker reading
    happens via `git show <branch>:<file>` or
    `git diff main..<branch>`.
  - **Root-cwd roles** (`reviewer`, `investigator`, `migrator`):
    operate from the root session's cwd. `reviewer` and `investigator`
    are read-only. `migrator` commits directly to `<worker_branch>`
    in root cwd. Workers in either category do not write to other workers'
    worktrees (N/A for root-cwd; for worktree-using, do not enter
    peer worktrees).
  - For worktree-using roles, spawn prompts MUST include worktree
    path, base commit SHA, and worker branch. For root-cwd roles,
    spawn prompts MUST include `worker_branch` (root checks out the
    branch for `migrator`; reviewers/investigators use it as the
    diff anchor) and `base_commit`. `worktree_path` is omitted.

For worktree-using roles, multiple workers editing the same file is
allowed **only** if their changes are on non-overlapping lines **and**
they operate in separate worktrees. Root-cwd roles (`migrator`) are
serialized by definition — never concurrent. When in doubt, serialize.

---

## 7. Verification before claiming done

Workers run **slice-scoped gates** on the `files_touched[]` they
committed. Full-suite regression is **root's responsibility** (see
overlay §5.2), or — for projects with expensive suites — a dedicated
**reviewer worker** operating in "regression auditor" mode. The
worker who produced the diff is the wrong place to run a 30-minute
end-to-end suite: the worktree sits idle, the model context sits
idle, and the same gate gets re-run anyway at integration time.

Three layers. Each owns a different scope:

- **Layer 1 — slice-scoped gates (worker, mandatory).** Run the
  minimum set of gates that catch breakage in your diff. Must run
  before you emit your artifact. Detailed below.
- **Layer 2 — full-suite gates (root, at integration time).** Root
  runs the full suite once per merge in overlay §5.2. The worker's
  Layer 1 result is **evidence**, not a substitute: it answers "did
  this worker break what they touched?", while root's full result
  answers "did the merge break anything anywhere?"
- **Layer 3 — audit regression (optional, dedicated reviewer).**
  When the project has a heavy suite (>2 min) or root's machine is
  busy, delegate the full regression to a `reviewer` worker spawned
  in regression-auditor mode (see `roles/reviewer.md`). The auditor
  runs `<project> test` / `<project> typecheck` / `<project> lint`
  from root cwd against the merged branch and emits the standard
  reviewer artifact. Spawn it after root's merge, before push.

### Layer 1 — slice-scoped gates (the worker's job)

Scope every gate to your `files_touched[]`. The slice guarantee: if
your changes broke typecheck / lint / the targeted tests, the gate
catches it. Cross-file breakage is caught one layer up.

| Gate | Slice-scoped form | What it catches |
|---|---|---|
| Type check | `tsc --noEmit <files>` / `mypy <files>` / `go build ./<pkg>` (Go is module-scoped) | Type errors in your diff |
| Lint | `eslint <files>` / `ruff check <files>` / `golangci-lint run --new-from-rev=<base> <files>` | Style / safety violations in your diff |
| Tests | Run the test files that import your touched files. For TS: `jest <test-file>`. For Python: `pytest <test-file>`. For Go: `go test ./<pkg>` in the package you touched. | Behavior regression in your slice |
| Build | Only when `files_touched[]` includes build config / native deps / asset pipeline (e.g. `package.json`, `Cargo.toml`, `webpack.config.js`, `tsconfig.json`) | Build pipeline breakage |

When a tool doesn't accept scoped invocation (e.g. a black-box
`<project> test` script), pass `<files>` via the project's mechanism
(filter file, test-name pattern, `--testPathPattern`, etc.). If no
scoped form exists, run the smallest subset you can — **never** the
full suite if it takes >2 minutes. Full suite is root's job.

### Layer 1: exceptions

- **Shared infra.** When `files_touched[]` touches build config,
  package manifests, CI, or other shared infrastructure, slice
  typecheck / lint are not sufficient — types and styles in unrelated
  files can break too. Run the smallest meaningful superset: for a
  `tsconfig.json` change, run `tsc --noEmit` on the whole project;
  for a `package.json` change, run `npm run build` even if only one
  dev dep changed. Mark this in `validation` explicitly so root's
  Layer 2 sees the broadened scope.
- **Env-missing gates.** If a gate cannot be run (pnpm missing, no
  network, broken cache), say so explicitly and downgrade
  `confidence: medium` or `low`. "Looks good" is not validation.
- **Trivial slices.** For a 1-line typo fix in one file, the slice
  gate is `cat <file>` + a `git diff` review. State that.

### Reporting

Report results verbatim in the artifact's `validation` field:

```
validation: "tsc --noEmit src/foo.ts: 0 errors; eslint src/foo.ts: clean; jest src/foo.test.ts: 3/3 pass"
```

`what_i_did_not_check[]` must list what you did **not** run (the full
suite, e2e, browser smoke, cross-file typecheck, etc.). "Nothing" is
only valid when truly exhaustive. The reader uses this list to
decide whether to schedule a Layer 3 regression audit.

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
- **Trusting serena's symbol index for files you have just modified.**
  Serena's MCP server inherits the project's `--project` path (anchored
  to the main repo) — it does NOT re-index per worktree. Post-edit
  `find_symbol` / `find_referencing_symbols` return main-repo HEAD
  results, silently missing your edits. Use `read` + `agentgrep` for
  post-edit verification. See §14.
- **Running the project's full test suite from the worker worktree.**
  The full suite belongs to root (overlay §5.2 Layer 2) or a dedicated
  `regression-auditor` reviewer (Layer 3). Running it from a worker
  worktree pins the worktree + the model's context for minutes and
  produces zero additional signal — root will re-run the same gate at
  integration time. The worker runs only the slice-scoped gates that
  catch breakage in its `files_touched[]` (see §7 Layer 1).

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
mixed reads). Workers that own file changes get a dedicated git
worktree. Root integrates. 1 worktree-using worker : 1 worktree, no
sharing, no nesting.

**Worktree-using roles** (3 of 6): `implementer`, `test-writer`,
`doc-writer`. They write files and need isolation from each other and
from the root cwd.

**Root-cwd roles** (3 of 6): `reviewer`, `investigator`, `migrator`.
Reviewer and investigator are read-only — they use git commands
(`git show`, `git diff`, `git log`) from the root cwd. Migrator owns
file changes but operates serially; it checks out `<worker_branch>`
directly in the root cwd so root can quickly inspect/squash/merge
without a separate worktree directory.

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

---

## 13. Author attribution

Every commit you author **must** carry your real identity. You do not
get to choose it — you must discover it.

### Discovery order (do not skip)

1. **Do not fabricate.** Never invent a name or email.
2. **Git config.** Run `git config user.name` and `git config user.email`
   in the repo root (or worktree root for workers). If both return
   non-empty values, use them.
3. **Project memory.** If git config is absent or empty, run
   `memory recall` with a query like `"author"`. If a `project`-scope
   entry exists with name and email, use it.
4. **Git log fallback.** If memory is also empty, run:
   ```
   git log -1 --format="%an <%ae>"
   ```
   Use the last commit's author on the current branch. If the repo has
   no commits yet, abort with `status: blocked`.

### Applying the author

When creating a commit, pass the discovered `name` and `email` to the
`author` field of `git commit`:

```json
{ "author": { "name": "Alice Chen", "email": "alice@example.com" } }
```

Root session and every worker: the same rule applies. Each worker's
worktree may have a different last-commit author (if cut from a shared
base); run the fallback command inside the worktree's directory, not
from the root session's cwd.

### Storing for next time

After discovering the author, store it in project memory so future
sessions in this repo skip the fallback step:

```
memory remember content="author: Alice Chen <alice@example.com>"
  scope=project tag=author
```

### Anti-patterns

- **Committing as "jcode" or "assistant".** Always discover the real
  identity. Fabricated author names break `git blame` and policy
  compliance (e.g. DCO sign-off).
- **Using a different author per file.** One author per commit; the
  author applies to all files in that commit.

---

## 14. Code intelligence in worktrees (serena caveat)

The serena MCP server, when registered (A4 axis), starts with
`--project <main-repo-path>` taken from `mcpServers.serena.args`. That
path is fixed for the lifetime of the jcode session — it is NOT
re-bound per worktree. Consequence:

- **Before editing**: serena is correct for code-intelligence
  exploration of the main repo (reading the call graph you are about
  to modify, finding all references pre-rename, getting a file's
  structural overview). Tree-sitter indexes the main repo and is
  fresh as of your last commit on main.
- **After editing**: do **not** trust serena's symbol index for files
  you have just modified. Its index is anchored to main; your
  worktree edits are invisible. Use jcode-native `read <file>` and
  `agentgrep <pattern> <worktree-path>/<glob>` instead.
- **Verification of intent** ("did my edit land the way I expect?"):
  re-read the file via `read`, or grep via `agentgrep` against the
  absolute worktree path. Do not ask serena.

The bundle ships a deterministic detector:

```bash
scripts/extension.sh mcp worktree-hint "$WORKTREE_PATH"
# Output is line-oriented; grep for the status:
#   serena: live (project=...)                          ← editing in main repo
#   serena: stale (sees <main-repo> only; worktree edits invisible)
#   serena: not-configured                              ← no serena in MCP config
# Exit 0 always (informational, not a gate).
```

Run this at spawn start. If the line says `stale`, plan your
verification accordingly: pre-edit use serena, post-edit use
`read` + `agentgrep`. Mark `confidence: low` on the artifact if a
gate relied on serena results against worktree files; that is
honest reporting, not failure — see §5.

This caveat is bundle-level, not engine-level. The jcode engine does
not currently support per-spawn MCP project rebind; until it does,
the worktree-hint check is the worker's only way to know whether
serena is safe to trust for the file in front of them.