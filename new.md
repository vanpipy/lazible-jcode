可以。下面我把前面几轮全部收敛成一套 **jcode Autonomous Coding Framework v1**。这里有一个重要区分：

> **这是基于 jcode 当前能力设计的上层 workflow / configuration architecture，不是声称 jcode 目前已经原生支持下面所有 `~/.jcode/prompts`、profile、workflow schema。**
>
> jcode 当前正在从 agent-first Swarm 向 **DAG-first** 模型演进；DAG、typed handoff、scheduler、verify/critique gates 已经是当前设计重点，但部分能力仍处于迁移/实现阶段。([GitHub][1])

---

# 1. 最终目标

我们要的不是：

```text
User
 ↓
jcode
 ↓
LLM writes code
```

而是：

```text
                         ┌──────────────┐
                         │    Human     │
                         │ Issue / Spec │
                         └──────┬───────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │   Orchestrator  │
                       │  Understand/Plan│
                       └────────┬────────┘
                                │
                           Task DAG
                                │
               ┌────────────────┼────────────────┐
               ▼                ▼                ▼
           Research          Coding           Testing
            Worker           Worker            Worker
               │                │                │
               └────────────────┼────────────────┘
                                │
                                ▼
                         Integration
                                │
                                ▼
                         Review / Critique
                                │
                         ┌──────┴──────┐
                         │             │
                       FAIL          PASS
                         │             │
                         ▼             ▼
                       Repair       E2E/Test
                         │             │
                         └──────┬──────┘
                                ▼
                              PR
                                │
                                ▼
                              Human
```

核心原则只有四个：

1. **AGENTS.md = 项目知识与项目约束**
2. **Global jcode config = agent 行为和 workflow**
3. **DAG = 当前任务的真实状态**
4. **Git + Validation = correctness / safety boundary**

---

# 2. 最终目录结构

我建议全局部分设计成：

```text
~/.jcode/
│
├── config.toml
│
├── profiles/
│   ├── default/
│   │   └── config.toml
│   │
│   ├── autonomous/
│   │   └── config.toml
│   │
│   ├── conservative/
│   │   └── config.toml
│   │
│   └── research/
│       └── config.toml
│
├── prompts/
│   ├── orchestrator.md
│   ├── worker.md
│   ├── reviewer.md
│   └── tester.md
│
├── workflows/
│   ├── feature.md
│   ├── bugfix.md
│   ├── refactor.md
│   └── research.md
│
├── policies/
│   ├── autonomy.md
│   ├── git.md
│   ├── safety.md
│   └── validation.md
│
├── templates/
│   ├── task.md
│   ├── handoff.md
│   └── report.md
│
├── state/
│   ├── tasks/
│   ├── runs/
│   └── logs/
│
└── ambient/
    ├── state.json
    ├── queue.json
    ├── usage.json
    └── logs/
```

其中最后的 `ambient/` 特别贴近 jcode 现在的设计：当前 ambient mode 已经有持久 queue、usage、state、logs 等概念。([GitHub][2])

---

# 3. Repo 本身保持极简

项目里面：

```text
my-project/
│
├── AGENTS.md
├── README.md
├── src/
├── tests/
└── ...
```

不要把：

```text
.jcode/
prompts/
workflows/
```

塞进每一个项目。

原因是：

### Global config

表达：

> **我希望所有 coding agent 怎么工作。**

### `AGENTS.md`

表达：

> **这个 repository 有什么特殊规则。**

这是非常重要的 separation of concerns。

---

# 4. 配置优先级

最终采用：

```text
                  highest priority
                         ▲
                         │
                   User Task
                         │
                  Project AGENTS.md
                         │
                    Profile
                         │
                  Global config
                         │
                         ▼
                  lowest priority
```

但是 **Safety Policy 例外**：

```text
Global Safety
      │
      │ cannot be weakened by repo
      ▼
Global Agent Policy
      │
      ▼
Project AGENTS.md
      │
      ▼
Task
```

例如：

```text
AGENTS.md:
    "agent can push to main"

Global safety:
    "never push main"

最终：
    never push main
```

这是 autonomous agent 必须有的安全底线。

---

# 5. `~/.jcode/config.toml`

我建议第一版直接设计成：

```toml
version = 1

[profile]
active = "autonomous"

[swarm]
mode = "deep"
max_workers = 6
max_retries = 3
max_parallel_tasks = 4

[models]
orchestrator = "strong"
worker = "strong"
reviewer = "strong"
tester = "strong"

[prompts]
orchestrator = "prompts/orchestrator.md"
worker = "prompts/worker.md"
reviewer = "prompts/reviewer.md"
tester = "prompts/tester.md"

[workflow]
default = "feature"

[git]
branch_prefix = "agent/"
auto_branch = true
auto_commit = true
auto_push = false
auto_pr = false
auto_merge = false

[worktree]
strategy = "auto"

[validation]
worker_checks = true
integration_checks = true
review_checks = true
e2e_checks = true

[autonomy]
auto_plan = true
auto_decompose = true
auto_repair = true
auto_review = true
auto_test = true

[safety]
require_permission_for_push = true
require_permission_for_pr = true
require_permission_for_merge = true
require_permission_for_deploy = true
```

注意：

**这是一套我们设计的 configuration schema。不要假定 jcode 当前 CLI 已经直接接受全部这些字段。**

---

# 6. Profile

Profile 是非常值得保留的一层。

## `default`

```toml
[swarm]
mode = "light"
max_workers = 2

[git]
auto_commit = false
auto_push = false

[autonomy]
auto_repair = true
```

适合日常 coding。

---

## `autonomous`

```toml
[swarm]
mode = "deep"
max_workers = 6
max_retries = 3

[git]
auto_branch = true
auto_commit = true
auto_push = false
auto_pr = false

[autonomy]
auto_plan = true
auto_decompose = true
auto_repair = true
auto_review = true
auto_test = true
```

这就是我们的核心模式。

---

## `conservative`

```toml
[swarm]
mode = "light"
max_workers = 2

[git]
auto_commit = false
auto_push = false
auto_pr = false

[autonomy]
auto_repair = false
```

---

# 7. 为什么我建议 `deep` 作为 autonomous profile

因为 jcode 最新的 DAG 设计本身已经区分：

### Light

```text
flat fan-out
few workers
low cost
no mandatory critique
```

### Deep

```text
recursive DAG
mandatory decomposition
critique/verify gates
typed handoff
runtime expansion
```

这不是我们凭空设计的，而是 jcode 当前 DAG architecture 本身的方向。([GitHub][1])

所以：

```text
default      → light
autonomous   → deep
```

非常自然。

---

# 8. Workflow 层

Workflow 是：

> **一个任务应该经历哪些阶段。**

不是 agent prompt。

---

## Feature workflow

```text
RECEIVE
   ↓
UNDERSTAND
   ↓
EXPLORE
   ↓
PLAN
   ↓
DECOMPOSE
   ↓
IMPLEMENT
   ↓
VERIFY
   ↓
REVIEW
   ↓
REPAIR ──────┐
   │         │
   └─────────┘
   ↓
INTEGRATE
   ↓
E2E
   ↓
FINAL VALIDATION
   ↓
PR
```

---

## Bugfix

Bugfix 不应该默认搞很大的 swarm：

```text
REPRODUCE
   ↓
DIAGNOSE
   ↓
FIX
   ↓
REGRESSION TEST
   ↓
REVIEW
   ↓
FINAL VALIDATION
```

如果 bug 很复杂，再自动 expand：

```text
DIAGNOSE
    ↓
┌───┼────┐
A   B    C
│   │    │
└───┼────┘
    ↓
ROOT CAUSE
```

---

## Refactor

重点变成：

```text
UNDERSTAND
    ↓
DEPENDENCY ANALYSIS
    ↓
PLAN
    ↓
INCREMENTAL REFACTOR
    ↓
TEST
    ↓
API COMPATIBILITY
    ↓
REVIEW
```

这里不建议一上来疯狂 parallel，因为 refactor 的文件 ownership 往往高度重叠。

---

# 9. Orchestrator

Orchestrator 是整个系统的大脑。

它**不应该亲自写大量代码**。

职责：

```text
Understand
Plan
Decompose
Schedule
Integrate
Review
Repair
```

核心 prompt：

```text
You are the lead software engineer and autonomous task orchestrator.

Your goal is to take the task from specification to verified completion.

You must:

1. Inspect the repository before making changes.
2. Read all applicable AGENTS.md files.
3. Understand architecture and existing conventions.
4. Determine whether the task is atomic or composite.
5. Build a dependency-aware task DAG.
6. Identify independent work.
7. Assign workers according to ownership and dependencies.
8. Avoid unnecessary file conflicts.
9. Require evidence from every worker.
10. Do not trust an agent's claim of success without verification.
11. Run verification after implementation.
12. Turn failures into explicit repair tasks.
13. Run adversarial review before closing the task.
14. Re-run validation after every repair.
15. Review the final diff for unrelated changes.

Do not ask the user for routine implementation decisions.

Ask the user only when:
- requirements are genuinely ambiguous,
- a destructive action is required,
- credentials or secrets are needed,
- an external side effect requires authorization,
- or multiple incompatible product decisions are possible.

Never declare success without evidence.
```

---

# 10. Worker

Worker 不需要知道整个世界。

它拿到：

```text
Task
+
AGENTS.md
+
upstream artifacts
+
scope
```

然后工作。

Prompt：

```text
You are an autonomous implementation worker.

## Task

{TASK}

## Scope

{SCOPE}

## Upstream Context

{UPSTREAM_ARTIFACTS}

## Rules

- Read applicable AGENTS.md.
- Inspect existing code before modifying it.
- Preserve existing architecture.
- Reuse existing abstractions.
- Do not modify unrelated files.
- Do not silently expand scope.
- Run relevant validation.
- Never claim a check passed unless you actually ran it.

## Completion Artifact

Return:

STATUS:
CHANGES:
FILES:
TESTS:
VALIDATION:
EDGE_CASES:
RISKS:
OPEN_QUESTIONS:
CONFIDENCE:
WHAT_I_DID_NOT_CHECK:
```

这个 `HandoffArtifact` 和 jcode 当前 DAG 设计高度一致。官方方案明确考虑 `findings / evidence / validation / edge_cases_considered / open_questions / confidence / what_i_did_not_check` 这样的 typed handoff。([GitHub][1])

---

# 11. Reviewer

Reviewer 必须尽量和 coder 解耦：

```text
You are an independent adversarial code reviewer.

You did not implement the change.

Inspect:

- task requirements
- git diff
- architecture
- tests
- error handling
- API compatibility
- security
- concurrency
- performance
- edge cases

Do not modify files.

For each finding:

SEVERITY:
FILE:
LOCATION:
PROBLEM:
WHY_IT_MATTERS:
SUGGESTED_FIX:

Also report:

WHAT_YOU_DID_NOT_REVIEW:
```

Reviewer 的作用不是：

> “看看代码好不好。”

而是：

> **试图证明它还不能关闭。**

这正好符合 jcode DAG 的 critique/verify gate 思路：gate 发现 gap 后重新向 DAG 注入任务，而不是让 agent 自己说“looks good”。([GitHub][1])

---

# 12. Tester

Tester 不应该只是：

```text
run tests
```

而应该根据 task 理解：

```text
What behavior needs proof?
```

然后：

```text
unit test
integration test
regression test
build
lint
typecheck
E2E
```

Tester artifact：

```text
STATUS: PASS | FAIL

CHECKS:
  - cargo test: PASS
  - cargo clippy: PASS
  - cargo fmt: PASS

FAILURES:
...

COVERAGE:
...

WHAT_I_DID_NOT_CHECK:
...
```

---

# 13. Swarm 拆分原则

这是整个设计最容易做错的地方。

**不要按“我要 5 个 agent”来拆。**

而应该按：

```text
dependency
+
ownership
+
risk
+
parallelism
```

拆。

---

## 规则 1：能独立就并行

```text
A ─────┐
       ├──→ D
B ─────┘
```

---

## 规则 2：有 dependency 就串行

```text
A → B → C
```

---

## 规则 3：共享同一个核心文件时尽量不要并行

例如：

```text
A → auth.rs
B → auth.rs
```

不要：

```text
Agent A ─┐
         ├── auth.rs
Agent B ─┘
```

更好：

```text
Agent A
   ↓
auth.rs
   ↓
Agent B
```

---

## 规则 4：research 与 implementation 可以并行

```text
Research
    │
    ├─────────┐
    │         │
    ▼         ▼
Finding     Prototype
    │         │
    └────┬────┘
         ▼
       Implement
```

---

# 14. Worktree 策略

不要：

```text
N agents = N worktrees
```

而采用：

```text
worktree = isolation boundary
```

也就是：

### shared workspace

默认：

```text
Agent A
Agent B
Agent C
    ↓
same worktree
```

适用于：

* 不冲突
* 小任务
* docs
* tests
* research

### isolated worktree

需要时：

```text
main
 │
 └── task/123
       │
       ├── backend worktree
       └── frontend worktree
```

适用于：

* 高冲突
* 大 refactor
* risky change
* 两个实现方案并行

这和 jcode 当前设计完全一致：worktree 是 optional isolation mechanism，而不是 swarm 的必选单位；integration 也由 worktree manager 负责。([GitHub][1])

---

# 15. Git 策略

统一：

```text
main
 │
 └── agent/123-oauth
       │
       ├── worker changes
       ├── tests
       ├── review
       └── validation
              │
              ▼
             PR
```

Agent：

```text
never:
    push main
    merge main
    force push

normally:
    create branch
    commit locally
    validate
```

这也符合 jcode 自己 `AGENTS.md` 的 repository guidance：agent 使用自己的 branch、保持 unrelated work，并且未经用户授权不要 merge。([GitHub][3])

---

# 16. Commit 策略

我建议：

### Worker

可以：

```text
git commit
```

但 commit 应该是：

```text
small
focused
buildable
```

例如：

```text
feat(auth): add OAuth token exchange
test(auth): cover token refresh failure
```

不要：

```text
agent changes
```

---

### Integration

负责：

```text
squash / merge
```

如果你的团队习惯 squash：

```text
worker commits
      ↓
integration
      ↓
squash
      ↓
PR
```

---

# 17. Validation Pipeline

完整 validation：

```text
                 implementation
                       │
                       ▼
                worker checks
                       │
                       ▼
              integration checks
                       │
                       ▼
                reviewer checks
                       │
                       ▼
                  E2E tests
                       │
                       ▼
                 final checks
```

具体分：

### Worker

```text
format
compile
unit tests
```

### Integration

```text
full test
lint
typecheck
build
```

### Review

```text
git diff
architecture
security
edge cases
```

### E2E

```text
real application
real workflow
browser/API
```

---

# 18. 最重要的 Repair Loop

这是 autonomous coding 的核心。

```text
             ┌──────────────┐
             │ Implementation│
             └──────┬───────┘
                    ▼
                Validation
                 /       \
              PASS       FAIL
               │           │
               │           ▼
               │        Diagnose
               │           │
               │           ▼
               │          Fix
               │           │
               │           └──────┐
               │                  │
               └──────────────────┘
```

但我会进一步要求：

**每次 FAIL 都产生一个明确的 DAG node。**

例如：

```text
V17 verify
   │
   ├── FAIL: missing error handling
   │
   ▼
F18 fix error handling
   │
   ▼
V19 verify
```

而不是让原 agent 在 context 里无休止地：

```text
try again
try again
try again
```

这正是 jcode 当前 DAG 设计中的 `verify → fix → re-verify` 模型。([GitHub][1])

---

# 19. Handoff 是整个系统的“消息总线”

我会尽量避免：

```text
Agent A → DM → Agent B
```

作为主要通信方式。

而是：

```text
Task A
  │
  ▼
Artifact A
  │
  ▼
Task B
```

Artifact：

```json
{
  "status": "complete",
  "changes": [
    "Implemented OAuth token exchange"
  ],
  "files": [
    "src/auth/oauth.rs"
  ],
  "validation": [
    "cargo test auth"
  ],
  "edge_cases": [
    "expired token",
    "invalid refresh token"
  ],
  "open_questions": [],
  "confidence": "high",
  "what_i_did_not_check": [
    "production OAuth provider"
  ]
}
```

jcode 当前 DAG proposal 也明确把 **dependency edge 本身作为 data channel**，而不是依赖 agent chat；artifact 默认按 reference 传递，以避免上下文爆炸。([GitHub][1])

这是我认为整个设计里最重要的架构决定之一。

---

# 20. Agent Communication 只留下 Exception Channel

正常：

```text
Task A
 ↓
Artifact
 ↓
Task B
```

只有遇到：

```text
conflict
ambiguity
unexpected shared state
```

才：

```text
Agent A ↔ Agent B
```

也就是：

```text
DAG = normal communication

DM = exception communication
```

这也符合 jcode 当前从 channel-heavy swarm 向 dataflow-first 的迁移方向。([GitHub][1])

---

# 21. Safety Layer

建议把 action 分成：

### Tier 1

自动：

```text
read files
git status
git diff
create branch
create worktree
run tests
build
lint
local commit
```

### Tier 2

需要 permission：

```text
git push
create PR
comment issue
send message
modify CI
deploy
modify account
```

jcode 当前 Safety System 的设计也是把本地、可逆动作和对外产生影响的动作分开，并允许用户配置 custom rules。([GitHub][4])

---

# 22. Autonomous 的真正含义

我建议不要定义成：

> agent 可以什么都做。

而定义成：

> **agent 可以在一个明确的安全边界内完成整个 control loop。**

也就是：

```text
plan
 ↓
execute
 ↓
observe
 ↓
verify
 ↓
repair
 ↓
review
 ↓
repeat
```

但：

```text
external side effect
```

仍然是 gate。

---

# 23. Ambient 放在哪里？

这个问题现在可以回答得很清楚。

**Ambient 不是我们的 coding workflow。**

它应该位于最外层：

```text
             Ambient Scheduler
                    │
                    ▼
             Autonomous Task
                    │
                    ▼
              Orchestrator
                    │
                    ▼
                 DAG
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
       Workers   Validation  Review
```

jcode 当前 ambient 是一个**单 agent background loop**，负责 scouting / gardening / proactive work，并且有资源预算、persistent queue、adaptive scheduling；它不是 parallel swarm 本身。([GitHub][2])

所以：

```text
Ambient
  = When should we work?

Orchestrator
  = What should we do?

DAG
  = What remains to be done?

Workers
  = Who does it?

Validation
  = Is it actually correct?
```

这个分层非常漂亮。

---

# 24. 最终系统可以压缩成 6 层

这是我认为最适合长期维护的最终架构：

```text
┌──────────────────────────────────────────┐
│  1. Ambient / Scheduler                  │
│     "When should agent work?"            │
├──────────────────────────────────────────┤
│  2. Global Policy / Profile              │
│     "How autonomous should it be?"       │
├──────────────────────────────────────────┤
│  3. Orchestrator                         │
│     "What needs to happen?"              │
├──────────────────────────────────────────┤
│  4. Task DAG                             │
│     "What depends on what?"              │
├──────────────────────────────────────────┤
│  5. Workers                              │
│     "Actually perform the work."         │
├──────────────────────────────────────────┤
│  6. Git + Validation + Safety            │
│     "Can we trust and ship the result?"  │
└──────────────────────────────────────────┘
```

项目自己的：

```text
AGENTS.md
```

横跨 3～5 层，提供 repo-specific context。

---

# 25. 最终推荐目录

所以我会把 v1 最终定成：

```text
~/.jcode/
│
├── config.toml
│
├── profiles/
│   ├── default/
│   │   └── config.toml
│   ├── autonomous/
│   │   └── config.toml
│   ├── conservative/
│   │   └── config.toml
│   └── research/
│       └── config.toml
│
├── prompts/
│   ├── orchestrator.md
│   ├── worker.md
│   ├── reviewer.md
│   └── tester.md
│
├── workflows/
│   ├── feature.md
│   ├── bugfix.md
│   ├── refactor.md
│   └── research.md
│
├── policies/
│   ├── autonomy.md
│   ├── git.md
│   ├── safety.md
│   └── validation.md
│
├── templates/
│   ├── task.md
│   ├── handoff.md
│   └── report.md
│
├── state/
│   ├── tasks/
│   ├── runs/
│   └── logs/
│
└── ambient/
    ├── state.json
    ├── queue.json
    ├── usage.json
    └── logs/
```

Repo：

```text
project/
│
├── AGENTS.md
├── README.md
├── src/
├── tests/
└── ...
```

---

# 26. 一次完整运行

假设你输入：

```text
Implement OAuth2 login with Google and GitHub.
Add tests and verify the complete login flow.
```

系统应该发生：

```text
                 USER TASK
                     │
                     ▼
               ORCHESTRATOR
                     │
              inspect repo
                     │
              read AGENTS.md
                     │
                     ▼
                 BUILD DAG
                     │
       ┌─────────────┼──────────────┐
       ▼             ▼              ▼
    Research       Backend        Frontend
       │             │              │
       └─────────────┼──────────────┘
                     ▼
                 Integration
                     │
                     ▼
                  Testing
                     │
                  FAIL
                     │
                     ▼
                  Diagnose
                     │
                     ▼
                    Fix
                     │
                     ▼
                   Test
                     │
                     ▼
                  Reviewer
                     │
                  FAIL
                     │
                     ▼
                    Fix
                     │
                     ▼
                  Reviewer
                     │
                    PASS
                     │
                     ▼
                  E2E Test
                     │
                    PASS
                     │
                     ▼
                Final Validation
                     │
                     ▼
                  Local Commit
                     │
                     ▼
                 PR Permission
                     │
                     ▼
                    PR
```

**这才是真正意义上的 autonomous coding。**

不是“让一个 agent 自己写到底”，而是让系统具备一个**可恢复、可验证、可递归扩展的 software-engineering control loop**。

---

# 27. 最后一个非常重要的设计取舍

我会把整个系统的“智能”尽量放在：

```text
LLM
```

但把整个系统的“纪律”放在：

```text
runtime / DAG / Git / validation / safety
```

也就是说：

```text
LLM 决定：
    怎么拆
    怎么实现
    怎么修
    怎么分析

Runtime 决定：
    谁能执行
    什么时候能执行
    dependency 是否满足
    是否可以结束
    是否通过 gate
    是否需要 permission
```

这是比“写一个超级强的 orchestrator prompt”更可靠的架构。

而且这恰好符合 jcode 当前自己的演进方向：**DAG 成为 primary abstraction，worker 变成可替换执行单元；coverage、critique、verify、typed handoff 等质量机制尽量由 runtime enforce，而不是只靠 prompt 要求。**([GitHub][1])

---

## 我会把 v1 的实现优先级定成这样

| Priority | 模块                    | 目标                             |
| -------- | --------------------- | ------------------------------ |
| **P0**   | `AGENTS.md`           | repo-specific context          |
| **P0**   | Global config/profile | 统一 agent policy                |
| **P0**   | Orchestrator prompt   | 建立 autonomous control loop     |
| **P0**   | Task DAG              | dependency + handoff           |
| **P0**   | Validation            | 防止“假完成”                        |
| **P0**   | Git branch/worktree   | isolation + recovery           |
| **P1**   | Reviewer              | adversarial verification       |
| **P1**   | Repair loop           | fail → diagnose → fix → verify |
| **P1**   | E2E/browser           | 产品级验证                          |
| **P1**   | Safety gates          | push/PR/deploy                 |
| **P2**   | Ambient               | 24/7 自动发现任务                    |
| **P2**   | Profiles              | 多种 autonomy 模式                 |
| **P2**   | Metrics               | 成本、成功率、repair rate             |
| **P3**   | Self-improvement      | 根据历史运行优化 workflow              |

**P0 做完，你就已经有一个相当完整的 autonomous coding agent；P1 是把它从“能跑”变成“可靠”；P2 才是把它变成真正 24/7 的 coding system。**

另外值得特别注意：jcode 自己的 `AGENTS.md` 已经强调 runtime verification——单纯 `cargo build` 并不能证明实际运行的是刚构建的代码，甚至建议用独立 socket 做 runtime check。这个例子非常说明为什么我们这里把 **validation 当成系统层，而不是 prompt 里的“请记得测试”**。([GitHub][3])

如果要继续落地，我下一步会直接进入 **v1 implementation spec**：把上面这套东西具体写成 `~/.jcode/config.toml`、4 个 prompt、4 个 workflow、4 个 policy、3 个 template，并定义 **DAG node schema / handoff JSON schema / Git state machine / validation state machine**。这样基本就可以直接拿去实现一个 `jcode-autonomous` wrapper，而不是停留在架构图层面。

[1]: https://github.com/1jehuang/jcode/blob/master/docs/SWARM_TASK_GRAPH.md?utm_source=chatgpt.com "jcode/docs/SWARM_TASK_GRAPH.md at master · 1jehuang/jcode · GitHub"
[2]: https://github.com/1jehuang/jcode/blob/master/docs/AMBIENT_MODE.md?utm_source=chatgpt.com "jcode/docs/AMBIENT_MODE.md at master · 1jehuang/jcode · GitHub"
[3]: https://github.com/1jehuang/jcode/blob/master/AGENTS.md?utm_source=chatgpt.com "jcode/AGENTS.md at master · 1jehuang/jcode · GitHub"
[4]: https://github.com/1jehuang/jcode/blob/master/docs/SAFETY_SYSTEM.md?utm_source=chatgpt.com "jcode/docs/SAFETY_SYSTEM.md at master · 1jehuang/jcode · GitHub"


---

# 28. 校准附录 (2026-09-28)

本节由 `jcode` 校对工作产出。在保留 §1-§27 设计原貌的前提下，把每一处与 jcode 真实状态不符的假设逐条列出，并附 jcode 源码/文档侧的证据。目的：让下游实现者（无论是 `lazible-jcode` bundle 还是将来的 v1 implementation spec）能直接对照本附录落地，而不是拿 §2/§5/§14/§21/§25 的虚构方案去碰壁。

校对来源：`~/Project/jcode`（master 分支，截至 2026-09-28）。所有行号以本次校对时为准；后续若 jcode 改动，可重新 grep。

---

## 28.1 校对目标与结论一览

| 项 | new.md 章节 | 校对结论 | 严重度 |
|---|---|---|---|
| C1 | §2 最终目录结构 | 不实：jcode 不读取这些子目录 | 高 |
| C2 | §5 config.toml schema | 不实：除 `[swarm]/[git]/[autonomy]/[worktree]/[validation]` 这些都不存在 | 高 |
| C3 | §9-12 4 个角色（orchestrator/worker/reviewer/tester） | 部分：bundle 实际已经扩展到 6 个角色 | 中 |
| C4 | §14 worktree 策略 + "worktree manager" | 漂移：worktree-manager 已被 jcode 解构为 scheduler policy；bundle 进一步迁移到 `workspace` 抽象 | 中 |
| C5 | §21 Safety Layer | 部分：runtime tier enforcement 仍是 design-phase（Phases 1-5 全部 TODO） | 中 |
| C6 | §25 最终推荐目录 | 不实：与 §2 同 | 高 |

**汇总：** 27 节里 4 节不实 + 8 节部分不实 + 15 节准确。

---

## C1. §2 "最终目录结构" → 用 jcode 真实机制替代

new.md §2 提出 `~/.jcode/{profiles,workflows,policies,templates,state,ambient}/{...}` 这套子目录。

**校对证据**（jcode 源码 + 文档，零命中）：

```bash
$ grep -rn "profiles\|workflows\|policies\|templates" crates/jcode-config-types/src/lib.rs
# （无任何顶层 struct 匹配这些名字）
```

jcode 当前**唯一**在 `~/.jcode/` 写入用户内容的路径是：

| 文件 | 来源 | 见 `docs/SYSTEM_PROMPT_CONFIG.md` |
|---|---|---|
| `~/.jcode/system-prompt.md` 或 `./.jcode/system-prompt.md` | 完整替换内置 base prompt | line 28-37 |
| `~/.jcode/prompt-overlay.md` 或 `./.jcode/prompt-overlay.md` | 追加在 base prompt 之后 | line 12-13, 21-23 |
| `~/.jcode/swarm-prompt.md` 或 `./.jcode/swarm-prompt.md` | swarm workers 的 model-routing 提示 | line 45-47 |
| `~/.jcode/preferred-tools.md` 或 `./.jcode/preferred-tools.md` | 工具偏好 | line 14 |
| `~/.jcode/AGENTS.md` 或 `./.AGENTS.md` | 用户/项目专属规则 | line 12 |

加载顺序（高→低）在 `SYSTEM_PROMPT_CONFIG.md` 的 "Layers (in order)" 段落：
1. 内置 base system prompt（`crates/jcode-base/src/prompt/system_prompt.md`）
2. Capability modules（Mermaid 等）
3. Self-dev guidance（self-dev session only）
4. AGENTS.md（project + global）
5. Prompt overlay
6. Preferred tools
7. Memory + active skill prompt（dynamic）

**正确替代写法**：

```text
~/.jcode/
├── prompt-overlay.md          ← 第 5 层：orchestrator 行为定义
├── swarm-prompt.md            ← worker dispatch 策略
├── preferred-tools.md         ← 工具偏好（可选）
└── roles/                     ← bundle 扩展：每个角色一个 .md
    ├── implementer.md
    ├── reviewer.md
    ├── test-writer.md
    ├── migrator.md
    ├── investigator.md
    └── doc-writer.md
```

**实现位置**：`lazible-jcode` 的 `install.sh` 把 `swarm/{prompt-overlay.md, swarm-prompt.md, roles/*.md}` symlink 到上述路径。

---

## C2. §5 config.toml schema → 用 jcode 真实 schema 替代

new.md §5 提出 `[profile]/[swarm]/[models]/[prompts]/[workflow]/[git]/[worktree]/[validation]/[autonomy]/[safety]` 这套块。**除了 `[safety]` 字段名撞名之外，其余全部不存在的字段**。

**校对证据**（jcode 源码，22 个一级 section）：

`crates/jcode-config-types/src/lib.rs` 中所有顶层 struct（grep `^pub struct`）：

| Struct | 行号 | 对应 `[section]` | 用途 |
|---|---|---|---|
| `CompactionConfig` | 353 | `[compaction]` | 上下文压缩策略 |
| `AuthConfig` | 512 | `[auth]` | 信任的外部 source |
| `AgentsConfig` | 523 | `[agents]` | swarm spawn mode、并发上限、memory sidecar |
| `AutoReviewConfig` | 879 | `[autoreview]` | 自审开关 |
| `AutoJudgeConfig` | 917 | `[autojudge]` | 自评开关 |
| `KeybindingsConfig` | 927 | `[keybindings]` | 键位 |
| `FeatureConfig` | 1075 | `[features]` | 功能开关 |
| `WebSearchConfig` | 1158 | `[websearch]` | 搜索引擎 |
| `ProviderConfig` | 1193 | `[provider]` | 模型默认/重试/跨 provider failover |
| `AmbientConfig` | 1265 | `[ambient]` | 后台模式 |
| `NotificationsConfig` | 1315 | `[notifications]` | TUI 桌面通知（与 safety 不同） |
| `SafetyConfig` | 1350 | `[safety]` | ntfy/email/telegram/discord/jade_relay |
| `GatewayConfig` | 1453 | `[gateway]` | WebSocket gateway |
| `PowerConfig` | 1475 | `[power]` | 防休眠 |
| `LaunchHotkeysEntry` | 1506 | `[launch_hotkeys]` | 全局热键 |

**零命中**：无 `ProfileConfig`、无 `WorkflowConfig`、无 `AutonomyConfig`、无 `GitConfig`、无 `WorktreeConfig`、无 `ValidationConfig`。

**唯一能"自定"profile 行为的字段**：

- `AgentsConfig.swarm_max_concurrent_agents`（默认 32，`crates/jcode-config-types/src/lib.rs:601`）—— 限制 live workers
- `ProviderConfig.default_model` —— 模型选择
- `AmbientConfig.work_branch_prefix`（默认 `"ambient/"`，`lib.rs:1285-1303`）—— ambient 用 branch 前缀

**profile → effort 映射在 prompt 层而非 config 层**。jcode 只识别两个 sentinel（`crates/jcode-base/src/prompt.rs`）：

```rust
pub const SWARM_EFFORT: &str = "swarm";           // line 101：light fan-out
pub const SWARM_DEEP_EFFORT: &str = "swarm-deep"; // line 110：deep task graph
```

`SWARM_DEEP_EFFORT_DIRECTIVE`（`prompt.rs:119`）在 deep mode 自动注入 system prompt，它**已经包含**：
- `swarm task_graph { mode: "deep" }` 的正确用法
- 7 字段 typed handoff（findings / evidence / validation / open_questions / confidence / what_i_did_not_check）
- critique/verify gate 的强制约束
- `inject_gap` 的正确使用

所以 §9 orchestrator 的 15 条 prompt 在 deep mode 下**完全不需要自己写**——engine 已经在 directive 里写好了。Orchestrator overlay 只需要补 profile 选择 + workflow 选择 + safety tier 三件事。

**正确替代 config.toml schema**：

```toml
# 真正可用的（且 jcode 会读的）：
[provider]
default_model = "..."

[agents]
swarm_max_concurrent_agents = 32
swarm_spawn_mode = "inline"   # visible | headless | inline | auto

[ambient]
enabled = false
work_branch_prefix = "ambient/"
min_interval_minutes = 5
max_interval_minutes = 120

[safety]
ntfy_server = "https://ntfy.sh"
desktop_notifications = true
# ... ntfy/email/telegram/discord/jade_relay 见 lib.rs:1350-1411

# 由 orchestrator 在 prompt 时设置（不是 config）：
# effort = "swarm"        # light fan-out
# effort = "swarm-deep"   # DAG-first + gates + typed handoff
```

---

## C3. §9-12 4 个角色 → 6 个角色

new.md §9-12 提了 4 个角色：orchestrator / worker / reviewer / tester。但 §10 worker 实际上**不是一个角色**，它是一组不同 spec 的子集。

**校对证据**：bundle (`lazible-jcode`) 实际把 worker 拆成 5 个不同 persona：

| new.md 角色 | bundle 实际角色 | 文件 |
|---|---|---|
| worker (general) | `implementer` | `swarm/roles/implementer.md` |
| （无） | `migrator` | `swarm/roles/migrator.md`（cross-module refactor） |
| （无） | `investigator` | `swarm/roles/investigator.md`（read-only research） |
| （无） | `doc-writer` | `swarm/roles/doc-writer.md`（pure markdown） |
| reviewer | `reviewer` | `swarm/roles/reviewer.md` |
| tester | `test-writer` | `swarm/roles/test-writer.md` |

理由：
- `migrator` 在 refactor workflow 中承担高所有权重叠的特殊规格
- `investigator` 在 research workflow 中只读不写，harness 可以放心派给强模型做大量阅读
- `doc-writer` 把纯 markdown 修改与代码修改分开，让 review 历史干净

§10 worker 的 9 字段 artifact（STATUS / CHANGES / FILES / TESTS / VALIDATION / EDGE_CASES / RISKS / OPEN_QUESTIONS / CONFIDENCE / WHAT_I_DID_NOT_CHECK）与引擎真实契约**有偏移**：

引擎真实契约（`crates/jcode-plan/src/dag/mod.rs:260-284`）：

```rust
pub struct HandoffArtifact {
    pub findings: String,
    pub evidence: Vec<String>,                  // 自由形式字符串，非对象
    pub edge_cases_considered: Vec<String>,
    pub validation: Option<String>,
    pub open_questions: Vec<String>,
    pub confidence: Option<String>,             // 解析为 low|medium|high
    pub what_i_did_not_check: Vec<String>,
}
```

差异：
- 引擎没有 `STATUS` / `CHANGES` / `FILES` / `TESTS` / `RISKS` 字段。bundle 增加 `status` ∈ {completed, partial, needs-info, blocked} 作为 prompt 层判别 accept/reject 的依据，引擎不读。
- `evidence` 是 `Vec<String>` 而非 `{commit, files_changed}` 对象。文件:行号、commit SHA 都是字符串。
- `confidence` 在 deep mode 必须可解析为 `low|medium|high`（`crates/jcode-plan/src/dag/ops.rs:737` 的 `validate_artifact` 拒绝 unparseable 值）。

**建议修正 §10 prompt 的 `## Completion Artifact` 段**：

```text
## Completion Artifact

返回必须以 ```json 围栏结束，结构如下：

{
  "status": "completed" | "partial" | "needs-info" | "blocked",
  "findings": "<string>",
  "evidence": ["<path:line>", "<commit-sha>", ...],
  "edge_cases_considered": ["..."],
  "validation": "<cmd + result>",
  "open_questions": ["..."],
  "confidence": "low" | "medium" | "high",
  "what_i_did_not_check": ["..."]
}

字段约束：
- findings 必须 non-empty（trim 后）。
- what_i_did_not_check 必须 non-empty（deep mode 引擎强约束）。
- confidence 必须可解析为 low|medium|high。honest "low" 是被欢迎的。
- evidence 中请引用 path:line 或 commit SHA，而非空泛断言。
```

---

## C4. §14 worktree 策略 → workspace 抽象

new.md §14 提出 "worktree = isolation boundary" + "integration 也由 worktree manager 负责"。

**校对证据**：

jcode 当前架构（`docs/SWARM_TASK_GRAPH.md` §1）：
> "Coordinator / worktree-manager roles demote to scheduler policy, not user-facing concepts."

也就是 `worktree-manager` 已经**不再是顶层角色**，被解构为 scheduler 内部策略。

`crates/jcode-app-core/src/server/swarm.rs:69` 还有一个 `swarm_spawn_depth()` 函数，但它**只是深度计算函数**（给 lifecycle/diagnostic 用），不再是 depth 限制。真正的 cap 是 `crates/jcode-swarm-core/src/lib.rs:60`：

```rust
pub const MAX_SWARM_MEMBERS: usize = 1000;  // 单一成员上限
```

**`MAX_SWARM_SPAWN_DEPTH` 在代码里已不存在**（只有 `SWARM_TASK_GRAPH.md:579` 的注释提到它"被移除"）。

`lazible-jcode` 的 bundle 进一步演化（见 `INSTALL.md` + `AGENTS.md` "Cleanup: stale workspaces"）：

```text
隔离单元 = workspace（不是 worktree）

shape:
  $TMPDIR/jcode/<repo>-<short-sha>/ws-<label>/
                                   ↑
                              workspace 而不是 worktree

cleanup:
  extension.sh workspace destroy <label>
  extension.sh workspace clean --yes
  swarm-sweep --yes               # legacy worktree residue
```

**建议 §14 改写为**：

```text
# 14. Workspace 策略

隔离单元是 workspace（`$TMPDIR/jcode/<repo>-<short-sha>/ws-<label>/`），不是
git worktree。jcode 已经把 worktree-manager 角色解构为 scheduler policy
（SWARM_TASK_GRAPH.md §1），bundle 在此基础上完全切到 workspace 模型。

默认：
  - 一个 swarm 共享一个 workspace（不是 N 个 worktree）
  - workspace 内多个 worker 通过 file ownership + DAG 调度避免冲突
  - 单文件被多个 worker 改的情况少见；见到就 rebase + integrate

需要 isolated workspace：
  - 大 refactor 且 ownership 不清晰
  - 两个并行实现方案（A/B test）
  - risky change 想隔离爆炸半径

清理：
  - 一次性：extension.sh workspace destroy <label>
  - 批量：extension.sh workspace clean --yes
  - legacy worktree 残留：swarm-sweep --yes

上限：单 swarm 至多 1000 live workers
（crates/jcode-swarm-core/src/lib.rs:60 MAX_SWARM_MEMBERS）。
```

---

## C5. §21 Safety Layer → 加 runtime tier design-phase caveat

new.md §21 把 Tier 1 / Tier 2 描述成 jcode 当前已具备的能力。

**校对证据**（`docs/SAFETY_SYSTEM.md`）：

- line 3：`> **Status:** Design`
- line 7："Currently the only consumer is ambient mode, but the system is intentionally decoupled so it can be reused for future features."
- line 511-540 "Implementation Phases"：Phase 1-5 全部 `[ ]` 未勾选
  - Phase 1：classifier / queue / request_permission / logger / summary
  - Phase 2：notification channels
  - Phase 3：review interfaces
  - Phase 4：configuration
  - Phase 5：intelligence

`docs/SAFETY_SYSTEM.md` 最后更新：`2026-02-08`。

**§21 实际状态**：
- ✅ Tier 1 / Tier 2 分类设计已成型（jcode SWARM_ARCHITECTURE 也有提及）
- ❌ Runtime tier enforcement 未实现——engine 不会主动拦截
- ⚠️ Ambient 模式下有最小化可用版本（review queue + 通知），其它模式（interactive swarm、autonomous）**没有 runtime gate**

**bundle 当前的应对**（见 `lazible-jcode/docs/AUTONOMOUS_FRAMEWORK.md` §7）：

> "Honest gap: until jcode's runtime tier system lands (Phases 1-5 of SAFETY_SYSTEM.md), this is a **prompt-level gate, not a runtime-level gate**. A misbehaving agent that ignores the overlay's prompt-level instruction CAN push to a non-main branch (or attempt other Tier 2 actions). The overlay reduces the risk to 'the agent would have to actively choose to violate its own instructions'; it does not eliminate it."

**建议 §21 追加 caveat**：

```text
**重要 caveat**：以上 Tier 1 / Tier 2 分类在 jcode 当前是 **design-phase**，
SAFETY_SYSTEM.md 全部 Phase 1-5 都是 TODO（最后更新 2026-02-08）。

- 当前只在 ambient mode 下有最小化的 review queue + ntfy/email 通知
  （[safety] 配置块生效）
- 其它模式（interactive swarm、autonomous）下没有 runtime gate
- bundle 当前的方案是 **prompt-level gate**：在
  `swarm/prompt-overlay.md` §6 写明 tier 分类与拒绝策略，
  并强制 worker 把 push / PR / 任何"对外副作用"动作转给 orchestrator 走 verbatim user OK

直到 SAFETY_SYSTEM Phase 4 完成（即 [safety] 配置支持 per-action
promote/demote rules），bundle 都无法做到 runtime enforcement。
```

---

## C6. §25 "最终推荐目录" → 用 bundle 真实形态替代

new.md §25 重复了 §2 的虚构目录。

**校对证据**：与 C1 相同。

**正确替代写法**（与 §2 一致）：

```text
# 25. v1 实际形态

jcode-native（无 bundle）：
  ~/.jcode/
  ├── prompt-overlay.md           ← orchestrator 行为
  ├── swarm-prompt.md             ← worker dispatch
  ├── preferred-tools.md          ← 工具偏好
  └── ...                         ← ambient/state/logs/runtime 由 jcode 自己管

lazible-jcode bundle（v1 实现）：
  ~/.jcode/
  ├── prompt-overlay.md           ← symlink → swarm/prompt-overlay.md
  ├── swarm-prompt.md             ← symlink → swarm/swarm-prompt.md
  ├── preferred-tools.md
  ├── roles/                      ← symlink → swarm/roles/*.md
  │   ├── implementer.md
  │   ├── reviewer.md
  │   ├── test-writer.md
  │   ├── migrator.md
  │   ├── investigator.md
  │   └── doc-writer.md
  └── mcp.json                    ← MCP server (filesystem/git/serena)

Repo（每个项目）：
  project/
  ├── AGENTS.md                   ← repo-specific 约束
  ├── README.md
  ├── src/
  ├── tests/
  └── .jcode/                     ← 可选 per-project overlay
      └── prompt-overlay.md       ← project-level 覆盖
```

---

## 28.2 校对方法学（可复用）

校对三步走，每次只需要重做 §3：

1. **引用真实性**：new.md 引用的 jcode docs URL 全部命中实际文件？grep `docs/SWARM_TASK_GRAPH.md` / `docs/AMBIENT_MODE.md` / `AGENTS.md` / `docs/SAFETY_SYSTEM.md`。
2. **源码级事实验证**：new.md 引用的具体结构 / 函数 / 常量在 jcode 源码里真实存在？精确到 file:line。例如：
   - `crates/jcode-base/src/prompt.rs:119` → `SWARM_DEEP_EFFORT_DIRECTIVE`
   - `crates/jcode-plan/src/dag/mod.rs:260` → `HandoffArtifact`（注意：bundle 文档写 :262，实际是 :260，差 2 行）
   - `crates/jcode-plan/src/dag/ops.rs:703` → `validate_artifact`
   - `crates/jcode-plan/src/dag/ops.rs:789` → `validate_gate_pass`
   - `crates/jcode-swarm-core/src/lib.rs:60` → `MAX_SWARM_MEMBERS = 1000`
3. **配置 schema 验证**：grep `crates/jcode-config-types/src/lib.rs` 中所有 `pub struct`，与 new.md 提出的 config 字段名比对。零命中即"不实"。

---

## 28.3 落地优先级（与 §27 优先级合并）

| 优先级 | 任务 | 关联附录 |
|---|---|---|
| **P0-A** | 校准 new.md（即本附录，§1-§27 保持不动，附录提供 bridge） | 本节 |
| **P0-B** | bundle 已有 `swarm/prompt-overlay.md` + `roles/*.md` 引用但仓库里**没这些文件**——补全 `swarm/` 目录（7 个文件） | C1, C3 |
| **P0-C** | bundle 引用 `scripts/extension.sh` 但仓库里**没这文件**——补全 | C4 |
| **P1-A** | SAFETY_SYSTEM Phase 1-5 TODO 监控；runtime tier 一旦可用，把 prompt-level gate 切换为 runtime gate | C5 |
| **P1-B** | 监视 `crates/jcode-base/src/prompt.rs:119` 的 `SWARM_DEEP_EFFORT_DIRECTIVE` 文本变化；如果 engine 加新的字段，bundle 的 artifact 契约同步加 | C3 |
| **P2-A** | `MAX_SWARM_MEMBERS` 上限从 1000 调整；`agents.swarm_max_concurrent_agents` 默认 32 调整 | C4 |
| **P3** | self-improvement：根据真实使用数据反推 workflow 缺什么 | §27 原表 |

---

## 28.4 不在校对范围内的事项

- jcode 自身 `AGENTS.md` 的内容是约束 jcode 开发者，不是 bundle 的约束，**new.md §15 + §27 关于此的引用正确**，无需校准
- `new.md` §3 "Repo 极简"（不要把 `.jcode/` 塞进每个项目）—— 这一原则与 jcode 设计一致，**正确**
- `new.md` §4 配置优先级（safety 例外）—— 与 jcode AGENTS.md 一致，**正确**
- `new.md` §6/§7 4 profile / deep=autonomous —— bundle 已坍缩为 2 effort rung（`swarm`/`swarm-deep`），prompt 层映射，**正确**
- `new.md` §19 handoff 作为消息总线 —— 与 `SWARM_TASK_GRAPH.md` §5 完全一致，**正确**
- `new.md` §20 DM = 异常通道 —— 与 `SWARM_TASK_GRAPH.md` §8a 一致；migration step 3-4 仍在进行中，**正确**
- `new.md` §23 ambient = scheduler —— 与 `AMBIENT_MODE.md` 完全一致，**正确**
- `new.md` §24 6 层模型 —— 与 bundle mapping 对齐，**正确**
- `new.md` §27 LLM=智能 + runtime=纪律 —— 与 jcode DAG 演进方向完全一致，**正确**

---

*附录作者：jcode 对照校对。证据文件：本附录 + 上文 §1-§27 的校对报告引用 + `~/Project/jcode` 源码与文档。*
