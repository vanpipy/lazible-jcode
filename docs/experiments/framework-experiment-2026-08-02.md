# Framework Experiment — 2026-08-02

> 用当前 lazible-jcode repo 的 9 条未合并分支作为实验场,跑 R14 + R17
> conflict-detect framework,测它在 5 个 judgment point 上的真实覆盖率,
> 找出缺失,产出 R19 优化 scope。

## 实验对象

**main 分支 HEAD**: `2c1abf1`(ARCHITECTURE.md 提交,停在 16 轮训练之前)

**未合并到 main 的 9 条分支**:

| branch | 起点 | commits ahead | 触达文件数 | LOC |
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

**当前 HEAD**: `7cd4652` on `feat/r18-timeout-policy_7253239`(**落后于 main 的 10 个 commit 是 R12 链原子提交 + R15 + R18**)。

**Uncommitted**:
- `swarm/CONTRIBUTING.md`(R8 hatchling 写了没 commit)
- `tests/__pycache__/test_install_smoke.cpython-313.pyc`(test runner 残留)

**工具**:
- R14 framework: `scripts/conflict-detect.py` from `fc6e22b` — 6 detectors
- R17 framework: same file from `60b3191` — adds 3 detectors (plan-order, dep-chain, serialize)
- 共 9 detectors,794 行 (R14) → 1260 行 (R17)

## 实际跑 framework 的输出

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

## 5 个 judgment point 的 ground truth vs framework 覆盖率

| # | Judgment point | 实际要求 | Framework 是否抓到 | 抓到的内容 | gap |
|---|---|---|---|---|---|
| 1 | **Sequencing** | 3 phases(Chain A → Chain B → cleanup) | partial | plan-order 给 6 phases | **未考虑 branch ancestry**,把 R12/R5a 当独立 task |
| 2 | **Conflict hunk 选边** | R11 case fix 在 R15+R18 之上,R15 case fix 在 R18 之上 | ✗ | serialize 只说 "minor" 不管 N | **没 prefer_side 配置**,AGENTS.md × 6 也是 minor |
| 3 | **Scope drift** | R13 修改 AGENTS.md 但未声明 scope(走 R12 链) | ✗ | 无 detector | **完全缺失** |
| 4 | **Topology choice** | main 落后 HEAD 10 commits,应 fast-forward 到 R18 tip 后逐 chain merge | ✗ | 无 detector | **完全缺失** |
| 5 | **Cleanup** | 删除 `__pycache__/`,commit R8 CONTRIBUTING.md,决定 R13 AGENTS.md 越权 | partial | dirty 只报 blocker | **未升格为可执行 cleanup list**,scope drift 也没接到 cleanup |

**实测覆盖率: ~30%**(4 个 point 抓到 partial,1 个完全没)

## 8 个具体 gap

| # | gap | 后果 | R19 模块 |
|---|---|---|---|
| 1 | plan-order 不接受 git-derived scope,要求手工 scopes.json | root 要先跑 git diff 自己拼 JSON | `auto_extract_scope(branches, repo)` — 让 plan-order 直接吃 branches |
| 2 | plan-order 不考虑分支谱系 | 给出错误的 6 phases 而不是 3 | `detect_branch_ancestry(branches)` + 折叠 plan-order phases |
| 3 | serialize severity 永远 minor(除非 lockfile) | AGENTS.md × 6 应该是 blocker | 加 `severity_threshold_n` config(N≥4 升 major,N≥6 升 blocker) |
| 4 | 无 conflict hunk 级别 picker | "serialize or rebase" 不是答案 | `resolve_conflict_hunks(branch_a, branch_b, file, prefer_side)` |
| 5 | 无 scope drift detector | R13 越权改 AGENTS.md 没被任何 detector 抓到 | `detect_scope_drift(branch, declared_scope_files)` + auto-revert policy |
| 6 | 无 topology chooser | root 决定 fast-forward vs --no-ff | `pick_merge_strategy(branches, base)` |
| 7 | 无 cleanup list promoter | dirty 只说 blocker,不说怎么 clean | `cleanup_worktree_artifacts(dirty_paths)` 输出可执行命令 |
| 8 | 无 per-repo guardian file config | 不知道哪些文件算 "off-limits" | `.jcode/conflict-config.yaml` schema 加 `guardian_files` |

## R19 scope 草稿

**目标**:把 framework 覆盖率从 ~30% 推到 ~80%。

**新增 5 detector + 1 fix + 1 schema**:

1. `detect_branch_ancestry(branches)` → 返回 `(parents: dict, chains: list[list[branch]])`
2. `auto_extract_scope(branches, repo)` → 返回 `{branch: [files]}` 从 `git diff main..branch`
3. `detect_scope_drift(branch, declared_scope, repo)` → 比较 diff vs declared,标 out-of-scope commits/hunks
4. `resolve_conflict_hunks(branch_a, branch_b, file, prefer_side, repo)` → 用 `git merge --no-commit` 跑出冲突,按 prefer_side 选 hunk
5. `pick_merge_strategy(branches, base, repo)` → 检查 fast-forward 可行性,返回 "fast-forward" / "merge --no-ff" / "rebase-then-merge"
6. `cleanup_worktree_artifacts(dirty_paths, patterns)` → 把 `__pycache__/` / `.bak.*` / untracked 映射到 `rm` / `git add` 命令
7. **Fix**: plan-order 升级 — 接受 `--branches` 自动 derive scope,内部 fold ancestry chains
8. **Config schema**: `.jcode/conflict-config.yaml` 加
   ```yaml
   guardian_files: [AGENTS.md, README.md, ...]
   severity_threshold_n: {major: 4, blocker: 6}
   prefer_side: worker | main | newer
   cleanup_patterns: ["__pycache__/", "*.bak.*", ...]
   ```

**实现工作**:约 800-1200 行 framework + 400-600 行 test。
**估计**:比 R17 (1 commit, 3 detector) 大 2-3 倍,需要 1 个 implementer + 1 个 doc-writer(写 schema 文档 + R20)。

## R20 scope 草稿

**目标**:把 framework 使用方式写进 overlay + swarm-prompt,确保 root 真的会调用它。

1. overlay 加 "Automation coverage target: 80% in framework, 20% in human" 段
2. swarm-prompt 加 "Pre-merge checklist: run `conflict-detect all` before any merge operation"
3. AGENTS.md 加 "Framework conventions" 段,链接到 conflict-detect.py

## 实验产出

- 本 docs 文件记录实验过程与发现
- memory tag `experiment-2026-08-02` 记录关键 gap 编号
- R19 implementer prompt 用本文件 §"R19 scope 草稿" 作为种子

## 待验证

- R17 mizaru 的 dep-chain CLI 参数 `--scope` 实际上是 JSON 文件路径,help 文本描述正确
- R17 framework 暂无 branch_ancestry 处理 — 已在实验中发现
- 待 R19 落地后,重跑 framework 对比覆盖率
