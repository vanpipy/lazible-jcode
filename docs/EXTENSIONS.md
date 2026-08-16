# 8×7 extension-mechanism walkthrough

Each axis × 7 sub-cases. Convention: scenarios focus on **boundary
behavior** (what root should do at the edge), not the happy path.

---

## A1: Per-project prompt-overlay  ✅ DONE

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 1.1 | per-project overlay 存在 + 非空 | jcode 优先使用 per-project | ✅ |
| 1.2 | per-project overlay 缺失 | jcode 退到 global | ✅ |
| 1.3 | per-project overlay 存在但为空 | jcode 退到 global（trim 检查） | ✅ (jcode 源码 trim) |
| 1.4 | per-project overlay 是 prepend 短指令 | jcode 拼接后注入 | ✅ (字符串拼接) |
| 1.5 | per-project overlay 是完整 overlay | jcode 完全替换 | ✅ |
| 1.6 | per-project overlay 路径权限拒绝 | jcode 退到 global + 警告 | ✅ (read 失败静默) |
| 1.7 | per-project overlay 引用不存在的 skill | jcode 不验证；worker load 时失败 | ✅ (lazy 语义) |

## A2: Per-project swarm-prompt.md  ⚠️ TRIVIAL (jcode 原生)

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 2.1 | per-project swarm-prompt 存在 | jcode 优先使用 | ✅ (jcode `prompt.rs:75`) |
| 2.2 | per-project 缺失 | jcode 退到 global | ✅ |
| 2.3 | per-project 为空 | jcode 退到 built-in default | ✅ (jcode trim 检查) |
| 2.4 | per-project 重写 model routing | workers 按新路由执行 | ✅ |
| 2.5 | per-project 重写 anti-patterns | workers 看到新反模式 | ✅ |
| 2.6 | per-project 包含 invalid 指令 | workers 可能误执行 | ⚠️ (jcode 不验证内容) |
| 2.7 | per-project 与 global 内容相同 | 行为不变（重复 OK） | ✅ |

A2 由 jcode 原生支持，bundle 仅需文档化"per-project 可用"。

## A3: Per-project verify hook  ✅ DONE

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 3.1 | verify.sh 存在 + executable + exit 0 | 通过 | ✅ |
| 3.2 | verify.sh exit 非零 | verification 失败，阻止 commit | ✅ |
| 3.3 | verify.sh 缺失 | 跳过（absence not failure） | ✅ |
| 3.4 | verify.sh 存在但非 executable | 跳过 + 警告 | ✅ (`[[ -x ]]` 检查) |
| 3.5 | verify.sh 超时 | bash 默认无超时（用户自管） | ⚠️ |
| 3.6 | verify.sh 修改 tracked 文件 | 用户自管（bundle 不阻止） | ⚠️ |
| 3.7 | verify.sh 写入 stderr | stderr 透传，错误信息清晰 | ✅ |

## A4: Per-project role override  ⚠️ TRIVIAL (bundle convention)

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 4.1 | `<repo>/.jcode/roles/<name>.md` 存在 | root 优先读 per-project | 🆕 |
| 4.2 | per-project 缺失 | root 退到 global | ✅ |
| 4.3 | per-project 为空 | root 退到 global + 警告 | 🆕 |
| 4.4 | per-project 是 partial overlay | root append 到 global | 🆕 |
| 4.5 | per-project 是完整重写 | root 使用 per-project | 🆕 |
| 4.6 | per-project 文件名不在 6 角色中 | root 忽略 + 警告（红线下不增加第 7 角色） | 🆕 |
| 4.7 | per-project 破坏 7+1 字段契约 | root 使用 per-project（不强制 schema 校验） | ⚠️ |

**A4 是 bundle convention**，不是 jcode 原生行为。jcode 不自动
load `<cwd>/.jcode/roles/*.md`。Root 需要 explicit fallback:
```
text = read(<cwd>/.jcode/roles/<name>.md)
       || read(~/.jcode/roles/<name>.md)
```
这是 root 在 spawn 时 inline 到 prompt 的内容来源。

## A5: required_skills[] spawn field  ✅ DONE

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 5.1 | spawn 不传 required_skills | root 从 role `## Skills to load` 读默认 | ✅ |
| 5.2 | spawn 传 required_skills=["/x"] | root 显式覆盖 | ✅ |
| 5.3 | required_skills=["/x","/y"] | root 注入两次 load | ✅ |
| 5.4 | role 文件没有 `## Skills to load` 段 | root 跳过 skill 注入 | ✅ |
| 5.5 | role 文件段落存在但内容空 | root 跳过（empty list） | ✅ |
| 5.6 | required_skills 引用不存在的 skill | worker load 时失败 | ⚠️ (lazy) |
| 5.7 | required_skills 与 role 默认重复 | root 注入一次（去重） | ✅ (overwrite wins) |

## A6: Pre-merge hook  🆕 NEW

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 6.1 | pre-merge.sh 存在 + executable + exit 0 | merge 继续 | 🆕 |
| 6.2 | pre-merge.sh exit 非零 | merge 阻止，错误透传 | 🆕 |
| 6.3 | pre-merge.sh 缺失 | 跳过（absence not failure） | 🆕 |
| 6.4 | pre-merge.sh 存在但非 executable | 跳过 + chmod 提示 | 🆕 |
| 6.5 | pre-merge.sh 修改 tracked 文件 | merge 阻止 + 提示用户 | 🆕 |
| 6.6 | pre-merge.sh 超时（≥5 min） | merge 阻止 + 错误 | 🆕 |
| 6.7 | pre-merge.sh 写 stderr | 捕获到错误信息 | 🆕 |

A6 参数合约：
```
./.jcode/pre-merge.sh <branch> <base_commit> <role>
exit 0 → merge proceeds
exit non-zero → merge blocked, stderr surfaced
```

## A7: Completion notify  🆕 NEW

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 7.1 | notify.sh 存在 + status=completed | 脚本被调用，记录成功 | 🆕 |
| 7.2 | notify.sh 失败 | 不影响 worker result（旁路） | 🆕 |
| 7.3 | notify.sh 缺失 | 跳过 | 🆕 |
| 7.4 | notify.sh 处理 partial | 同 completed 调用 | 🆕 |
| 7.5 | notify.sh 处理 needs-info | 同上 | 🆕 |
| 7.6 | notify.sh 处理 blocked | 同上 + 可选 alarm | 🆕 |
| 7.7 | notify.sh 在 worktree 中运行 | cwd 是主 worktree，非 worker worktree | 🆕 |

A7 参数合约：
```
./.jcode/notify.sh <status> <worker_label> <artifact_json_path>
```
旁路执行：notify 失败不影响主流程。

## A8: Pre-spawn hook  🆕 NEW

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 8.1 | pre-spawn.sh 存在 | 每个 spawn 前调用一次 | 🆕 |
| 8.2 | pre-spawn.sh 失败 | spawn 阻止（abort） | 🆕 |
| 8.3 | pre-spawn.sh 缺失 | 跳过 | 🆕 |
| 8.4 | pre-spawn.sh 设置 env vars | export 到 spawn 子进程 | 🆕 |
| 8.5 | pre-spawn.sh 创建 worktree | 由 root 接手使用 | 🆕 |
| 8.6 | pre-spawn.sh 写日志 | 项目日志记录 | 🆕 |
| 8.7 | pre-spawn.sh 慢（≥30s） | spawn 延迟但不阻止 | ⚠️ (无超时) |

A8 参数合约：
```
./.jcode/pre-spawn.sh <label> <role> <files_touched_count>
exit 0 → spawn proceeds
exit non-zero → spawn aborted
stdout 中若有 KEY=VALUE 行，被 root 解析为 env vars
```

---

## 实施优先级

| 轴 | 价值 | 实施成本 | 优先级 |
|---|---|---|---|
| A6 pre-merge hook | HIGH（cross-worker integration gate） | LOW（文档 + 1 个示例） | 1️⃣ |
| A7 notify | MEDIUM（observability） | LOW | 2️⃣ |
| A8 pre-spawn | LOW（场景少） | LOW | 3️⃣ |
| A2 + A4 文档化 | HIGH（zero-cost 文档化） | TRIVIAL | 4️⃣ |