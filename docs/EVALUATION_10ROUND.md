# 10-Round Test Evaluation — lazible-jcode post-deploy

- Date: 2026-08-04
- Origin/main baseline: 7009dc2
- Local HEAD: f678431
- Evaluator: root session (no workers spawned for this evaluation — all rounds are observational)
- Local install state: canary v0.67.0 + swarm-coordinator-first patch applied

## Headline metric

| Metric | Value |
|--------|-------|
| Dispatched (current session) | 4 (consistency-fixer, overlay-refactor, install-wirer, postman-tooling) |
| Landed (merged into main)    | 4 |
| Lost                         | 0 |
| **Loss rate**                | **0%** (target 0%, hard ceiling 3%) |

Across the full repo history since 7009dc2:

| Metric | Value |
|--------|-------|
| Total commits | 15 |
| Merges | 4 |
| Worker branches ever created (this session, reflog) | 4 |
| Worker branches currently existing | 0 (all merged + cleaned) |

## Round-by-round results

### R1: Static gates — PASS

9 shell scripts parse, 4 python scripts compile, 0 errors.

```
install.sh                OK
uninstall.sh              OK
build-jcode-canary.sh     OK
sync-jcode-source.sh      OK
install-dryrun.sh         OK
test_install_idempotent.sh OK
test_install_dryrun.sh    OK
jcode-install.sh          OK
copy-from-jcode.sh        OK
swarm-state-monitor.py    OK
check-swarm-consistency.py OK
check-liveness-contract.py OK
conflict-detect.py        OK
```

### R2: test_swarm_state_monitor — 12/12 PASS

| Class | Tests |
|-------|-------|
| TestArtifactParsing | 3 |
| TestClassify | 4 (incl. missing_commits_are_dead) |
| TestTickAgeFilter | 3 (incl. all_filtered_uses_single_clean_message — the post-merge UX fix) |
| TestTickCLI | 2 |

### R3: test_check_swarm_consistency — 10/10 PASS

Includes the new `test_default_roles_dir_resolves_symlinks` (the PATH install fix).
Without that fix, the script fails with "FAIL: roles directory not found" when
invoked via the ~/.jcode/scripts/ symlink.

### R4: test_install_idempotent — Modes A/B/C/D ALL PASSED

| Mode | Behavior | Result |
|------|----------|--------|
| A (overwrite) | rerun backs up + re-links | 1 → 8 .bak files |
| B (idempotent) | rerun skips already-correct symlinks | 1 → 1 .bak files (no growth) |
| C (target drift) | changing symlink target triggers re-link even in IDEMPOTENT=1 | PASS |
| D (--help) | --help mentions IDEMPOTENT=1 + Environment variables | PASS |

### R5: install-dryrun — PASS

5 steps planned cleanly, no destructive side effects on the real `~/.jcode/`.
Output mirrors what a real install would do.

### R6: test_role_templates — PASS

6 expected template files exist; all parse with required keys; all have valid
confidence value.

### R7: test_conflict_detect — 104/104 PASS

The big one. Covers scope_overlap, lockfile contention, in-flight overlap,
dirty state, manifest corruption, heartbeat stale. Includes CLI exit codes
(0 clean / 1 major / 2 blocker), auto-extract-scope, cleanup-artifacts, and
branch-ancestry dataclass.

### R8: PATH-installed smoke — 6/6 PASS

| Script | exit |
|--------|------|
| check-swarm-consistency.py | 0 (PASS) |
| swarm-state-monitor.py tick | 0 (clean "(no worker branches found)") |
| swarm-state-monitor.py tick --include-stale | 0 |
| check-liveness-contract.py | 0 (4 PASS — passive-inspection rule added since R3) |
| install-dryrun.sh | 0 (DRYRUN: PASS) |
| conflict-detect.py --help | 0 |

All scripts invokable from any cwd via PATH-installed symlinks.

### R9: Postman E2E on synthetic branches — 6/6 PASS

The P2 audit follow-up. New file `scripts/test_postman_e2e.py` creates 6
synthetic branches in a temp git repo, runs `tick` twice (default + --include-stale),
and asserts:

| Branch | Artifact | Age | Expected | Actual |
|--------|----------|-----|----------|--------|
| postman-e2e-healthy | final | 2m | healthy | **healthy** |
| postman-e2e-progressing | progress | 3m | progressing | **progressing** |
| postman-e2e-quiet | progress | 8m | quiet | **quiet** |
| postman-e2e-silent | progress | 20m | silent | **silent** |
| postman-e2e-dead | progress | 45m | dead | **dead** |
| postman-e2e-ancient | progress | 25h | hidden by default, dead with --include-stale | **PASS** |

Surfaced during the test: `time.gmtime()` vs `time.localtime()` matters for
`GIT_AUTHOR_DATE`. The test uses `localtime` and documents the gotcha.

### R10: Loss rate + summary

| Dispatch | Land | Lost | Rate |
|----------|------|------|------|
| 4 | 4 | 0 | **0%** |

All 4 worker branches (consistency-fixer, overlay-refactor, install-wirer,
postman-tooling) merged into main with --no-ff. Zero conflict resolution
needed because each worker owned a disjoint file set (per the scope prompts).

## Bugs discovered and fixed during evaluation

1. **install.sh Text file busy** (deploy-time): the running jcode binary
   can't be replaced in-place. Worked around per docs/MANUAL_BINARY_SWAP.md
   via `mv` + `cp`. Working tree remained usable.

2. **scripts/*.py missing +x bit** (deploy-time): 4 files (`conflict-detect.py`,
   `test_conflict_detect.py`, `test_role_templates.py`, `test_swarm_state_monitor.py`)
   were checked in as 0644. After install.sh symlinks scripts/ into PATH, those
   scripts fail with Permission denied on direct invocation. Fixed via `chmod +x`.

3. **check-swarm-consistency.py __file__ symlink bug**: the script used
   `os.path.dirname(__file__)` for default `--roles-dir`, but `__file__` is
   the symlink path (not realpath) when invoked via the PATH-installed symlink.
   Caused every CLI invocation from outside the repo to fail with
   "roles directory not found: /home/leroy/.jcode/swarm/roles".
   Fixed via `os.path.realpath(__file__)`. Test added in same commit.

4. **test_postman_e2e.py timezone bug** (during this round): first attempt
   used `time.gmtime()` which produces UTC iso strings; git interpreted them
   as local time, anchoring commits 8 hours in the past on this UTC+8 system.
   Fixed via `time.localtime()` and documented in docstring.

## Verdict

**10/10 rounds pass.** Framework is production-correct for the surface area
covered by existing tests + the new E2E. The Smart Postman classification
logic is verified against a controlled reference clock.

## What this evaluation did NOT cover

- **Real worker dispatch under contention**: no live worker spawned during
  this session. The E2E test simulates branches, not actual swarm-tool spawn
  → worker lifecycle.
- **Cross-worker handoff under load**: A→B dependency, git show across
  worktrees, conflict resolution — these would need a worker-spawning test
  harness, beyond scope here.
- **Long-running stability**: no soak test (e.g., 24h continuous dispatch).
- **Heartbeat SLA enforcement**: `--include-stale` was tested; the actual
  5-min heartbeat from a real worker process was not (would need a test
  harness that opens a worker session).

For full coverage, see `docs/LIVENESS_VALIDATION.md` (5-turn interactive
walkthrough) which covers these scenarios qualitatively.