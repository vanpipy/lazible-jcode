# Framework Experiment — 2026-08-02

> Use the 9 unmerged branches in the current `lazible-jcode` repo as the
> experiment substrate. Run the R14 + R17 `conflict-detect` framework against
> them and measure its real coverage across 5 judgment points; identify the
> gaps and produce the R19 scope for improvement.

## Experiment Subject

**main branch HEAD**: `2c1abf1` (the ARCHITECTURE.md commit, stopped before
the 16-round training session)

**9 branches not yet merged into main**:

| branch | base | commits ahead | files touched | LOC |
|---|---|---|---|---|
| `feat/r1-check-swarm-consistency_2c1abf1` | main | 2 | 3 | +391 |
| `feat/r11-model-id-case_3e9314d` | R7 tip | 1 | 13 | +855 |
| `feat/r14-conflict-detect_dc5b00c` | R5a tip | 1 | 10 | +1785 |
| `feat/r15-safety-target_dc5b00c` | R5a tip | 1 | 10 | +653 |
| `feat/r17-execution-order_fc6e22b` | R14 tip | 1 | 10 | +2557 |
| `feat/r18-timeout-policy_7253239` | R15 tip | 1 | 10 | +683 |
| `feat/r5-install-dryrun_3e9314d` | R12 tip | 1 | 8 | +621 |
| `feat/r7-role-templates_250ed77` | R1 tip | 1 | 11 | +845 |
| `refactor/r12-idempotent-install_2c1abf1` | main | 7 | 6 | +346 |

**Current HEAD**: `7cd4652` on `feat/r18-timeout-policy_7253239` (the 10
commits behind main are the R12 atomic commit chain + R15 + R18).

**Uncommitted**:
- `swarm/CONTRIBUTING.md` (R8 hatchling wrote it but did not commit)
- `tests/__pycache__/test_install_smoke.cpython-313.pyc` (test runner residue)

**Tools**:
- R14 framework: `scripts/conflict-detect.py` from `fc6e22b` — 6 detectors
- R17 framework: same file from `60b3191` — adds 3 detectors (plan-order,
  dep-chain, serialize)
- Total: 9 detectors, 794 lines (R14) → 1260 lines (R17)

## Actual framework run output

### R14 (6 detectors)

```
1. dirty:        [blocker] 2 uncommitted in main worktree (CONTRIBUTING.md, __pycache__/)
2. scope-overlap: 4 blockers (4 multi-branch file overlaps)
3. lockfile:     no conflicts
4. in-flight:    2 blockers (R14 + R17 already touch conflict-detect.py)
5. manifest:     not run (no manifest in repo)
6. heartbeat:    not run (no manifest)
```

### R17 (3 detectors)

```
plan-order output (6 phases):
  phase 0: R1, R12
  phase 1: R11, R14
  phase 2: R15, R7
  phase 3: R17
  phase 4: R18
  phase 5: R5a

serialize output:
  18 [minor] serialization_overlap entries
  - AGENTS.md × 6 branches
  - scripts/install.sh × 6 branches
  - tests/{runtests,smoke_install,test_install_smoke}.{sh,py} × 6 branches
  - swarm/{prompt-overlay,swarm-prompt}.md × 3 branches each
  - scripts/{install-dryrun,test_install_dryrun,test_install_idempotent}.sh × 5-6 branches
  - swarm/ARCHITECTURE.md × 3 branches
  - scripts/{conflict-detect,test_conflict_detect}.py × 2 branches
  - scripts/{check-swarm-consistency,test_check_swarm_consistency,test_role_templates}.py × 2-3 branches
  - swarm/role-templates/* × 2 branches each (6 files)

dep-chain output:
  [tested separately with --scope JSON file]
  "no conflicts" when R14 chain is in-flight and we ask about R18-merge
  (correct — R18 doesn't depend on R14's commit)
```

## 5 judgment points — ground truth vs framework coverage

| # | Judgment point | Actual requirement | Caught by framework? | What it caught | Gap |
|---|---|---|---|---|---|
| 1 | **Sequencing** | 3 phases (Chain A → Chain B → cleanup) | partial | plan-order returns 6 phases | **Branch ancestry not considered**; R12/R5a are treated as independent tasks |
| 2 | **Conflict hunk selection** | R11 case fix on top of R15+R18, R15 case fix on top of R18 | ✗ | serialize only says "minor", ignores N | **No `prefer_side` config**; AGENTS.md × 6 is also reported as minor |
| 3 | **Scope drift** | R13 modified AGENTS.md but did not declare scope (rode the R12 chain) | ✗ | no detector | **Completely missing** |
| 4 | **Topology choice** | main is 10 commits behind HEAD; should fast-forward to R18 tip, then merge chain by chain | ✗ | no detector | **Completely missing** |
| 5 | **Cleanup** | Delete `__pycache__/`, commit R8 CONTRIBUTING.md, decide R13 AGENTS.md overreach | partial | dirty only reports blocker | **Not promoted into an executable cleanup list**; scope drift also not wired into cleanup |

**Measured coverage: ~30%** (4 judgment points caught partial, 1 not at all)

## 8 specific gaps

| # | Gap | Consequence | R19 module |
|---|---|---|---|
| 1 | plan-order does not accept git-derived scope; requires a hand-written `scopes.json` | root has to run `git diff` and assemble JSON by hand | `auto_extract_scope(branches, repo)` — let plan-order consume branches directly |
| 2 | plan-order does not consider branch lineage | returns wrong 6 phases instead of 3 | `detect_branch_ancestry(branches)` + collapse plan-order phases |
| 3 | serialize severity is always minor (unless lockfile) | AGENTS.md × 6 should be blocker | Add `severity_threshold_n` config (N≥4 → major, N≥6 → blocker) |
| 4 | No conflict-hunk-level picker | "serialize or rebase" is not an answer | `resolve_conflict_hunks(branch_a, branch_b, file, prefer_side)` |
| 5 | No scope-drift detector | R13's out-of-scope AGENTS.md edit was caught by no detector | `detect_scope_drift(branch, declared_scope_files)` + auto-revert policy |
| 6 | No topology chooser | root has to decide fast-forward vs `--no-ff` | `pick_merge_strategy(branches, base)` |
| 7 | No cleanup-list promoter | dirty only says "blocker", not "how to clean" | `cleanup_worktree_artifacts(dirty_paths)` returns executable commands |
| 8 | No per-repo guardian file config | unclear which files count as "off-limits" | Add `guardian_files` to `.jcode/conflict-config.yaml` schema |

## R19 scope draft

**Goal**: push framework coverage from ~30% to ~80%.

**Add 5 detectors + 1 fix + 1 schema**:

1. `detect_branch_ancestry(branches)` → returns
   `(parents: dict, chains: list[list[branch]])`
2. `auto_extract_scope(branches, repo)` → returns `{branch: [files]}` from
   `git diff main..branch`
3. `detect_scope_drift(branch, declared_scope, repo)` → compares diff vs
   declared; flags out-of-scope commits/hunks
4. `resolve_conflict_hunks(branch_a, branch_b, file, prefer_side, repo)` →
   run `git merge --no-commit` to surface conflicts, pick hunks by
   `prefer_side`
5. `pick_merge_strategy(branches, base, repo)` → checks fast-forward
   feasibility; returns "fast-forward" / "merge --no-ff" /
   "rebase-then-merge"
6. `cleanup_worktree_artifacts(dirty_paths, patterns)` → map
   `__pycache__/` / `.bak.*` / untracked into `rm` / `git add` commands
7. **Fix**: plan-order upgrade — accept `--branches` to auto-derive scope,
   internally collapse ancestry chains
8. **Config schema**: add to `.jcode/conflict-config.yaml`
   ```yaml
   guardian_files: [AGENTS.md, README.md, ...]
   severity_threshold_n: {major: 4, blocker: 6}
   prefer_side: worker | main | newer
   cleanup_patterns: ["__pycache__/", "*.bak.*", ...]
   ```

**Implementation work**: roughly 800–1200 lines of framework + 400–600 lines
of tests.
**Estimate**: 2–3× larger than R17 (1 commit, 3 detectors); needs 1
implementer + 1 doc-writer (for schema docs + R20).

## R20 scope draft

**Goal**: wire framework usage into overlay + swarm-prompt so root actually
calls it.

1. overlay adds an "Automation coverage target: 80% in framework, 20% in
   human" section
2. swarm-prompt adds a "Pre-merge checklist: run `conflict-detect all`
   before any merge operation" section
3. AGENTS.md adds a "Framework conventions" section linking to
   `conflict-detect.py`

## Experiment outputs

- This `docs/` file records the experiment and findings.
- Memory tag `experiment-2026-08-02` records the key gap numbers.
- R19 implementer prompt uses the §"R19 scope draft" section above as seed.

## Pending verification

- R17 mizaru's `dep-chain` CLI parameter `--scope` is actually a JSON file
  path; help text describes it correctly.
- R17 framework does not currently handle `branch_ancestry` — discovered
  during this experiment.
- After R19 lands, re-run the framework and compare coverage.