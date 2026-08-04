# 10-Round Worktree-Swarm E2E Evaluation

**Date:** 2026-08-04
**Initiative:** postman-framework-hardening
**Scope:** End-to-end validation of `skills/worktree-swarm/worktree-swarm.sh`
plus the git-worktree topology it manages.

## Goal

Cover the full lifecycle of a worker worktree (alloc → edit → commit → merge-ready →
teardown) across 10 distinct scenarios. Each round is an independent unittest
method that calls the real shell script via subprocess — no mocks.

## Results

All 10 rounds pass on the first clean run AND on a re-run (idempotent).

| #  | Round                              | Validates                                                                                  | Result |
|----|------------------------------------|--------------------------------------------------------------------------------------------|--------|
| R1 | alloc single worktree              | path/branch/manifest shape                                                                 | PASS   |
| R2 | alloc 3 worktrees parallel         | each gets distinct path + branch; no collisions                                           | PASS   |
| R3 | per-worktree isolation             | edits in different worktrees don't cross-contaminate                                       | PASS   |
| R4 | list output consistency            | `list` output matches manifest + actual `git worktree list`                                | PASS   |
| R5 | double-alloc refused               | re-alloc with same label exits non-zero; teardown + re-alloc succeeds                      | PASS   |
| R6 | cleanup --force removes stale      | TTL-expired worktrees disappear after `cleanup --force`                                    | PASS   |
| R7 | --base flag custom SHA             | new branch forks from the specified SHA, not HEAD                                          | PASS   |
| R8 | git ops inside worktree            | status / add / commit / log all work as expected                                           | PASS   |
| R9 | cross-worktree merge               | `git merge-tree main <branch>` exits 0 — merge would succeed (non-destructive)             | PASS   |
| R10| 3 sequential workers, full lifecycle| loss rate = 0% (3 dispatched, 3 landed)                                                   | PASS   |

## Bugs surfaced during this evaluation

### B1. `worktree-swarm.sh` shipped without +x bit

**Symptom.** Symlinked into `~/.jcode/scripts/` by install.sh step 5, but PATH-installed
copy refused to execute (`Permission denied`). Same bug class as `chore(scripts): chmod +x`
(7a2a1e4).

**Fix.** `fix(skills): chmod +x worktree-swarm.sh for PATH install` (commit 1cd3795).

### B2. Tests initially polluted `main` with marker files

**Symptom.** First attempt at R9/R10 actually merged the worker branch into main
(`git merge --no-ff`). Re-running the test failed because the marker files were
already tracked in main, so `git add marker` saw nothing to add → `git commit` exited 1
with "nothing to commit".

**Fix.** Two changes:
- Use `uuid.uuid4().hex[:8]` for marker filenames so each invocation gets a fresh
  untracked file.
- Use `git merge-tree main <branch>` (non-destructive) instead of `git merge`. The merge
  compatibility is still validated (merge-tree exits 0 on a clean merge) but main stays
  untouched across runs.

Captured in `test(worktree-swarm): E2E test orchestrator with 10 rounds` (commit 8d9d9d3).

## Run

```
python3 -m unittest scripts.test_worktree_swarm_e2e -v
```

Wall-clock: ~4s for the full 10-round suite on this host.

## Files

- `scripts/test_worktree_swarm_e2e.py` — 521-line test orchestrator (10 unittest methods,
  one shared `force_cleanup_all` helper, robust `setUp`/`tearDownClass`).
- `skills/worktree-swarm/worktree-swarm.sh` — mode changed from 0644 to 0755.

## Loss rate

`dispatched = landed = 10` for this orchestrator (1 spawn per round, each lands).
Worker loss rate = 0%. Well under the 3% ceiling from POSTMAN_PROTOCOL.md.