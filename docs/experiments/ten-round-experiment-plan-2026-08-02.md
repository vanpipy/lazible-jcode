# Ten-Round Experiment Plan — 2026-08-02

> 在 R19 iwazaru 落地后,用 10 轮实验验证 framework 在 DAG 排序 + 并发监控 + 状态清理
> 三大支柱上的真实覆盖率,收集量化证据,识别 R20/R21/R22 的优先级。

## 实验设计原则

每轮实验满足:
- **可重复**:同样的 git 状态、framework 版本、CLI 命令能复现
- **可测量**:有明确的输入(构造场景)、输出(framework 行为)、ground truth(预期行为)
- **可对比**:每轮记录 framework 输出 vs ground truth 的差,数字 ≥ 80% 算 pass
- **可持久化**:每轮结果写入 `docs/experiments/round-<N>.md`,包含原始 command + framework 输出 + 评估

## 10 轮实验清单

### Round 1 — DAG 排序:已知拓扑的小规模

**目标**:验证 `plan_execution_order` 对简单线性 DAG 的排序准确性

**构造**:3 个独立分支(R1→R2→R3 线性,无重叠)
**输入**:tasks.json = 3 tasks
**预期**:phase 0 = R1, phase 1 = R2, phase 2 = R3
**Ground truth**:线性拓扑
**Pass 标准**:phase 顺序与拓扑序一致
**对应 gap**:R19 #2 `detect_branch_ancestry`

### Round 2 — DAG 排序:分支谱系折叠

**目标**:验证谱系折叠(parent child branch 合并到同一 phase)

**构造**:5 个分支(A→B→C 线性 + D, E 与 A 平行)
**输入**:tasks.json = 5 tasks
**预期**:phase 0 = [A, D, E] parallel, phase 1 = B, phase 2 = C (谱系折叠后)
**Ground truth**:谱系折叠后的拓扑
**Pass 标准**:B 和 C 不在 phase 0(因为被 A 折叠)
**对应 gap**:R19 #2

### Round 3 — 并发监控:serialize severity 升级

**目标**:验证 `severity_threshold_n` 配置生效(N≥4 → major, N≥6 → blocker)

**构造**:6 个分支都改同一文件
**输入**:tasks.json = 6 tasks, config with severity_threshold_n
**预期**:`suggest_serialization` 对该文件返回 blocker severity
**Ground truth**:6 branches touching 1 file 应该是 blocker
**Pass 标准**:severity 字段实际升级
**对应 gap**:R19 #3

### Round 4 — 并发监控:scope-drift 检测

**目标**:验证 `detect_scope_drift` 能识别 out-of-scope commit

**构造**:1 个分支,declared scope = ["a.py"],实际 diff = ["a.py", "AGENTS.md"]
**输入**:branch + declared_scope
**预期**:返回 1 个 conflict,severity = blocker(因为 AGENTS.md 是 guardian)
**Ground truth**:AGENTS.md 是 guardian file,out-of-scope = blocker
**Pass 标准**:检测到 AGENTS.md 并标 blocker
**对应 gap**:R19 #5

### Round 5 — 并发监控:prefer_side 配置生效

**目标**:验证 `resolve_conflict_hunks` 按 prefer_side 选边

**构造**:2 个分支改同一文件同一行(branch A 写 "X", branch B 写 "Y")
**输入**:branch_a, branch_b, file, prefer_side="worker"
**预期**:选 branch B 的内容(worker)
**Ground truth**:prefer_side="worker" → B 的内容胜出
**Pass 标准**:实际选择匹配 prefer_side
**对应 gap**:R19 #4

### Round 6 — 状态清理:cleanup patterns 匹配

**目标**:验证 `cleanup_worktree_artifacts` 对 `__pycache__/` / `.bak.*` 的识别

**构造**:在临时 worktree 里 touch `__pycache__/x.pyc`、`tests/foo.bak.123`、`a.tmp`
**输入**:patterns = ["__pycache__/", "*.bak.*", "*.pyc", "*.tmp"]
**预期**:返回 3 个 cleanup action:rm -rf __pycache__/, rm tests/foo.bak.123, rm a.tmp
**Ground truth**:3 个匹配
**Pass 标准**:全部命中
**对应 gap**:R19 #7

### Round 7 — DAG 排序:pick_merge_strategy

**目标**:验证 `pick_merge_strategy` 对 fast-forward / --no-ff / rebase 的判断

**构造**:3 个场景
  - 场景 A:branch 是 main 的 fast-forward 后裔 → "fast-forward"
  - 场景 B:branch 与 main 有分叉但无冲突 → "merge --no-ff"
  - 场景 C:branch 与 main 有冲突 → "rebase-then-merge"
**预期**:3 个场景返回 3 个不同策略
**Ground truth**:策略选择
**Pass 标准**:3 个场景正确分类
**对应 gap**:R19 #6

### Round 8 — DAG 排序:auto_extract_scope

**目标**:验证 `auto_extract_scope(branches, repo)` 直接从 git diff 提取

**构造**:3 个分支已知 diff(用 git show 验证)
**输入**:branches + repo path
**预期**:返回的 scope_files 与 git diff --name-only 一致
**Ground truth**:git diff 输出
**Pass 标准**:文件集完全一致(顺序不要求)
**对应 gap**:R19 #1

### Round 9 — 并发监控:guardian_files config 加载

**目标**:验证 `.jcode/conflict-config.yaml` schema 正确加载并生效

**构造**:写一个 minimal valid config 文件,guardian_files = ["AGENTS.md"]
**输入**:config file path
**预期**:`detect_scope_drift` 看到 AGENTS.md 自动升级为 blocker
**Ground truth**:配置生效
**Pass 标准**:bad config 报错,good config 通过
**对应 gap**:R19 #8

### Round 10 — 端到端:9 分支合并覆盖率

**目标**:用真实的 9 个未合并分支跑 framework 全套,测量 loss-rate

**构造**:当前 repo 状态(9 branches + 1 uncommitted + __pycache__/ 污染)
**输入**:实际 repo
**预期**:
  - DAG 排序:输出 ≤ 3 phases(谱系折叠后)
  - 并发监控:标出 AGENTS.md × 6 + scripts/install.sh × 6 都是 blocker
  - 状态清理:输出 cleanup list(commit CONTRIBUTING.md, rm __pycache__/)
**Ground truth**:人工评估的合并路径
**Pass 标准**:framework 输出能让 root 在 1 步之内决定 merge 顺序,不需要再读 18 个文件的 git diff
**Coverage target**:≥ 80% 的合并决策由 framework 直接给出

## 10 轮实验时间表

| 阶段 | 事件 | 估计时间 |
|---|---|---|
| **Pre-flight** | R19 iwazaru 落地 + 全套 framework 可用 | 等 R19 ready |
| **Round 1-3** | DAG 排序 + serialize 升级 | R19 落地后立即 |
| **Round 4-5** | scope-drift + prefer_side | 同上 |
| **Round 6** | cleanup patterns | 同上 |
| **Round 7-8** | topology + auto_extract | 同上 |
| **Round 9** | config schema 加载 | 同上 |
| **Round 10** | 端到端 + loss-rate 测量 | 最后 |
| **Post** | 写最终报告 `docs/experiments/ten-round-results-2026-08-02.md` | 收尾 |

## 评估指标

每轮记录:
- **pass / fail / partial**
- **实测覆盖率**:`passes / total_decisions`
- **framework 行为**:原始 CLI 输出
- **ground truth**:人工评估
- **gap 编号**:对应 R19 8 gaps 中的哪一条

最终汇总:
- **总覆盖率**(10 轮平均)
- **单支柱覆盖率**(DAG / monitor / cleanup 各几条 pass)
- **R19 是否达标 80%**
- **R20/R21/R22 优先级**(哪条 gap 仍然 missing,排入下一轮)

## 不在范围

- 不写代码(框架是 R19 iwazaru 的工作)
- 不修 framework bug(R19 范围内的事,记到 `open_questions[]`)
- 不真正合并分支(那是 R20/R21 之后的事)

## 产出文件

- `docs/experiments/round-<1-10>-<date>.md` — 每轮 1 个文件,固定 schema
- `docs/experiments/ten-round-results-2026-08-02.md` — 汇总
- memory tag `experiment-2026-08-02-10r` — 最终 coverage 数字
