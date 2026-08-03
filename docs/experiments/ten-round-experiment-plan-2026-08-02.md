# Ten-Round Experiment Plan — 2026-08-02

> After R19 iwazaru lands, run 10 rounds of experiments to verify the
> framework's real coverage on the three pillars (DAG ordering, concurrent
> monitoring, state cleanup). Collect quantitative evidence and identify
> R20/R21/R22 priorities.

## Experiment design principles

Each round must satisfy:

- **Reproducible**: same git state, framework version, CLI command can be
  replayed.
- **Measurable**: explicit inputs (constructed scenario), outputs
  (framework behavior), ground truth (expected behavior).
- **Comparable**: each round records framework output vs ground truth
  delta; ≥80% counts as pass.
- **Persistent**: each round's results write to
  `docs/experiments/round-<N>.md`, including raw command + framework
  output + evaluation.

## 10-round experiment checklist

### Round 1 — DAG ordering: small known topology

**Goal**: verify `plan_execution_order` accuracy on a simple linear DAG.

**Construct**: 3 independent branches (R1 → R2 → R3 linear, no overlap).
**Input**: `tasks.json` = 3 tasks.
**Expected**: phase 0 = R1, phase 1 = R2, phase 2 = R3.
**Ground truth**: linear topology.
**Pass criteria**: phase order matches topological order.
**Maps to gap**: R19 #2 `detect_branch_ancestry`.

### Round 2 — DAG ordering: branch lineage collapse

**Goal**: verify lineage collapse (parent + child branch merged into same
phase).

**Construct**: 5 branches (A → B → C linear + D, E parallel to A).
**Input**: `tasks.json` = 5 tasks.
**Expected**: phase 0 = [A, D, E] parallel, phase 1 = B, phase 2 = C
(after lineage collapse).
**Ground truth**: topology after lineage collapse.
**Pass criteria**: B and C are not in phase 0 (because they collapse with A).
**Maps to gap**: R19 #2.

### Round 3 — Concurrent monitoring: serialize severity escalation

**Goal**: verify `severity_threshold_n` config takes effect (N≥4 → major,
N≥6 → blocker).

**Construct**: 6 branches all touch the same file.
**Input**: `tasks.json` = 6 tasks, config with `severity_threshold_n`.
**Expected**: `suggest_serialization` returns blocker severity for that
file.
**Ground truth**: 6 branches touching 1 file should be blocker.
**Pass criteria**: severity field actually escalates.
**Maps to gap**: R19 #3.

### Round 4 — Concurrent monitoring: scope-drift detection

**Goal**: verify `detect_scope_drift` identifies out-of-scope commits.

**Construct**: 1 branch, declared scope = `["a.py"]`, actual diff =
`["a.py", "AGENTS.md"]`.
**Input**: branch + declared_scope.
**Expected**: returns 1 conflict, severity = blocker (because AGENTS.md is
a guardian).
**Ground truth**: AGENTS.md is a guardian file; out-of-scope = blocker.
**Pass criteria**: detects AGENTS.md and tags blocker.
**Maps to gap**: R19 #5.

### Round 5 — Concurrent monitoring: prefer_side config takes effect

**Goal**: verify `resolve_conflict_hunks` picks by `prefer_side`.

**Construct**: 2 branches change the same line of the same file (branch A
writes "X", branch B writes "Y").
**Input**: `branch_a, branch_b, file, prefer_side="worker"`.
**Expected**: selects branch B's content (worker).
**Ground truth**: `prefer_side="worker"` → B's content wins.
**Pass criteria**: actual selection matches `prefer_side`.
**Maps to gap**: R19 #4.

### Round 6 — State cleanup: cleanup patterns match

**Goal**: verify `cleanup_worktree_artifacts` recognizes `__pycache__/` /
`.bak.*`.

**Construct**: in a temporary worktree, `touch __pycache__/x.pyc`,
`tests/foo.bak.123`, `a.tmp`.
**Input**: `patterns = ["__pycache__/", "*.bak.*", "*.pyc", "*.tmp"]`.
**Expected**: returns 3 cleanup actions: `rm -rf __pycache__/`,
`rm tests/foo.bak.123`, `rm a.tmp`.
**Ground truth**: 3 matches.
**Pass criteria**: all hit.
**Maps to gap**: R19 #7.

### Round 7 — DAG ordering: pick_merge_strategy

**Goal**: verify `pick_merge_strategy` correctly judges fast-forward /
`--no-ff` / rebase.

**Construct**: 3 scenarios:
  - Scenario A: branch is fast-forward descendant of main → "fast-forward"
  - Scenario B: branch diverged from main but no conflicts → "merge --no-ff"
  - Scenario C: branch diverged with conflicts → "rebase-then-merge"
**Expected**: 3 scenarios return 3 different strategies.
**Ground truth**: strategy selection.
**Pass criteria**: 3 scenarios correctly classified.
**Maps to gap**: R19 #6.

### Round 8 — DAG ordering: auto_extract_scope

**Goal**: verify `auto_extract_scope(branches, repo)` extracts directly
from `git diff`.

**Construct**: 3 branches with known diff (verified via `git show`).
**Input**: branches + repo path.
**Expected**: returned `scope_files` matches `git diff --name-only`.
**Ground truth**: `git diff` output.
**Pass criteria**: file sets identical (order not required).
**Maps to gap**: R19 #1.

### Round 9 — Concurrent monitoring: guardian_files config loaded

**Goal**: verify `.jcode/conflict-config.yaml` schema loads correctly and
takes effect.

**Construct**: write a minimal valid config file with
`guardian_files = ["AGENTS.md"]`.
**Input**: config file path.
**Expected**: `detect_scope_drift` sees AGENTS.md and auto-escalates to
blocker.
**Ground truth**: config takes effect.
**Pass criteria**: bad config errors out; good config passes.
**Maps to gap**: R19 #8.

### Round 10 — End-to-end: 9-branch merge coverage

**Goal**: run the full framework against the real 9 unmerged branches and
measure loss-rate.

**Construct**: current repo state (9 branches + 1 uncommitted +
`__pycache__/` pollution).
**Input**: actual repo.
**Expected**:
  - DAG ordering: output ≤ 3 phases (after lineage collapse)
  - Concurrent monitoring: flag AGENTS.md × 6 + `scripts/install.sh` × 6 as
    blocker
  - State cleanup: output cleanup list (commit `CONTRIBUTING.md`, remove
    `__pycache__/`)
**Ground truth**: human-evaluated merge path.
**Pass criteria**: framework output lets root decide merge order in 1 step
without re-reading 18 files' `git diff`.
**Coverage target**: ≥ 80% of merge decisions produced directly by the
framework.

## 10-round experiment timeline

| Stage | Event | Estimated time |
|---|---|---|
| **Pre-flight** | R19 iwazaru lands + full framework available | wait for R19 ready |
| **Round 1-3** | DAG ordering + serialize escalation | immediately after R19 |
| **Round 4-5** | scope-drift + prefer_side | same |
| **Round 6** | cleanup patterns | same |
| **Round 7-8** | topology + auto_extract | same |
| **Round 9** | config schema loading | same |
| **Round 10** | end-to-end + loss-rate measurement | last |
| **Post** | write final report `docs/experiments/ten-round-results-2026-08-02.md` | wrap-up |

## Evaluation metrics

Per round, record:

- **pass / fail / partial**
- **Measured coverage**: `passes / total_decisions`
- **Framework behavior**: raw CLI output
- **Ground truth**: human evaluation
- **Gap number**: which of R19's 8 gaps this maps to

Final aggregation:

- **Total coverage** (10-round average)
- **Per-pillar coverage** (DAG / monitor / cleanup — how many pass each)
- **Did R19 hit the 80% target?**
- **R20/R21/R22 priorities** (which gaps are still missing, queue for next
  round)

## Out of scope

- Writing code (framework is R19 iwazaru's job)
- Fixing framework bugs (R19's scope; record into `open_questions[]`)
- Actually merging branches (that's after R20/R21)

## Output files

- `docs/experiments/round-<1-10>-<date>.md` — one file per round, fixed
  schema
- `docs/experiments/ten-round-results-2026-08-02.md` — aggregation
- Memory tag `experiment-2026-08-02-10r` — final coverage number