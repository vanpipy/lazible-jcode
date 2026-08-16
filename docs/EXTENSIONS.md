# 9×7 extension-mechanism walkthrough

Each axis × 7 sub-cases. Convention: scenarios focus on **boundary
behavior** (what root should do at the edge), not the happy path.

**Two groups:**

- **jcode-native** (A1–A4): jcode already loads these from
  `<cwd>/.jcode/...` with per-project precedence. Bundle just
  documents them. No bundle-side script needed.

- **bundle convention** (A5–A9): bundle provides
  `scripts/extension.sh` as the single entry point to invoke
  per-project hooks with the right fallback semantics.

---

## Group 1: jcode-native (4 axes)

### A1: Per-project prompt-overlay  ✅

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 1.1 | per-project overlay 存在 + 非空 | jcode 优先使用 per-project | ✅ (`prompt.rs:949`) |
| 1.2 | per-project overlay 缺失 | jcode 退到 global | ✅ |
| 1.3 | per-project overlay 为空 | jcode 退到 global（trim 检查） | ✅ (jcode 源码 trim) |
| 1.4 | per-project overlay 是 prepend 短指令 | jcode 拼接后注入 | ✅ (字符串拼接) |
| 1.5 | per-project overlay 是完整 overlay | jcode 完全替换 | ✅ |
| 1.6 | per-project overlay 路径权限拒绝 | jcode 退到 global + 警告 | ✅ (read 失败静默) |
| 1.7 | per-project overlay 引用不存在的 skill | jcode 不验证；worker load 时失败 | ✅ (lazy 语义) |

### A2: Per-project swarm-prompt.md  ✅

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 2.1 | per-project swarm-prompt 存在 | jcode 优先使用 | ✅ (`prompt.rs:75`) |
| 2.2 | per-project 缺失 | jcode 退到 global | ✅ |
| 2.3 | per-project 为空 | jcode 退到 built-in default | ✅ (jcode trim 检查) |
| 2.4 | per-project 重写 model routing | workers 按新路由执行 | ✅ |
| 2.5 | per-project 重写 anti-patterns | workers 看到新反模式 | ✅ |
| 2.6 | per-project 包含 invalid 指令 | workers 可能误执行 | ⚠️ (jcode 不验证内容) |
| 2.7 | per-project 与 global 内容相同 | 行为不变（重复 OK） | ✅ |

### A3: Per-project skills/  ✅ (新发现)

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 3.1 | `<repo>/.jcode/skills/<name>/` 存在 | jcode 加载，per-project wins over global | ✅ (`skill.rs:264`) |
| 3.2 | per-project skills 目录缺失 | jcode 用 global skills | ✅ |
| 3.3 | per-project skill 与 global 同名 | per-project 覆盖（合并逻辑） | ✅ (`skill.rs:280-285`) |
| 3.4 | per-project skill 缺 SKILL.md | jcode 跳过 + 警告 | ⚠️ (lazy load) |
| 3.5 | per-project skill 引用不存在的资源 | skill load 失败 | ⚠️ (lazy 语义) |
| 3.6 | per-project skills 损坏 | daemon 报错但 global 仍可用 | ⚠️ (jcode 处理) |
| 3.7 | `.agents/skills/` 也存在 | jcode 同时加载 cross-tool skills | ✅ (`skill.rs:314`) |

jcode precedence 链：
```
~/.jcode/skills/   (global)
./.jcode/skills/    (per-project, jcode-native)
./.agents/skills/   (cross-tool convention)
./.claude/skills/   (legacy Claude compatibility)
```

### A4: Per-project MCP servers  ✅ (新发现)

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 4.1 | `<repo>/.jcode/mcp.json` 存在 | jcode 加载 | ✅ (`mcp/protocol.rs:569-583`) |
| 4.2 | mcp.json 缺失 | jcode 用 global `~/.jcode/mcp.json` | ✅ |
| 4.3 | mcp.json JSON 语法错 | jcode 报错，global 仍生效 | ⚠️ (load 失败) |
| 4.4 | mcp.json 引用不存在的 command | server 启动失败 | ⚠️ (runtime 失败) |
| 4.5 | mcp.json 中 server 名与 global 重复 | per-project wins | ✅ (later-overrides) |
| 4.6 | `.mcp.json` 也存在 | jcode 合并（`.jcode/mcp.json` 优先） | ✅ (`mcp/protocol.rs:579-583`) |
| 4.7 | `.claude/mcp.json` 也存在 | 全部合并，per-project 优先 | ✅ |

jcode precedence 链（per-project MCP）：
```
./.jcode/mcp.json       (per-project jcode-native) ← 最高优先
./.mcp.json             (Claude Code 兼容)
./.claude/mcp.json      (legacy 兼容)
~/.jcode/mcp.json       (global fallback)
~/.claude.json          (per-user Claude fallback)
```

---

## Group 2: bundle convention (5 axes)

### A5: Per-project role override  ✅

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 5.1 | `<repo>/.jcode/roles/<name>.md` 存在 + 非空 | per-project wins | ✅ (extension.sh) |
| 5.2 | per-project 缺失 | global fallback | ✅ |
| 5.3 | per-project 为空 | global fallback + 警告 | ✅ (extension.sh) |
| 5.4 | role 名不在 6 个中 | exit 2 红线 | ✅ |
| 5.5 | per-project 完全重写 | 使用 per-project | ✅ |
| 5.6 | per-project 破坏 7+1 schema | root 不验证；worker 端 schema check 失败 | ⚠️ (lazy 语义) |
| 5.7 | per-project 与 global 完全相同 | 行为不变 | ✅ |

### A6: Per-project verify hook  ✅

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 6.1 | verify.sh 存在 + executable + exit 0 | 通过 | ✅ |
| 6.2 | verify.sh exit 非零 | verification 失败，阻止 commit | ✅ |
| 6.3 | verify.sh 缺失 | 跳过（absence not failure） | ✅ |
| 6.4 | verify.sh 存在但非 executable | 跳过 + 警告 | ✅ |
| 6.5 | verify.sh 超时 | bash 默认无超时 | ⚠️ (用户自管) |
| 6.6 | verify.sh 修改 tracked 文件 | 不阻止（用户自管） | ⚠️ |
| 6.7 | verify.sh 写入 stderr | stderr 透传 | ✅ |

### A7: Per-project pre-merge hook  ✅

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 7.1 | pre-merge.sh 存在 + executable + exit 0 | merge 继续 | ✅ |
| 7.2 | pre-merge.sh exit 非零 | merge 阻止，stderr 透传 | ✅ |
| 7.3 | pre-merge.sh 缺失 | 跳过 | ✅ |
| 7.4 | pre-merge.sh 存在但非 executable | 跳过 + chmod 提示 | ✅ |
| 7.5 | pre-merge.sh 超时（≥5 min） | merge 阻止 + timeout 错误 | ✅ |
| 7.6 | pre-merge.sh 修改 tracked 文件 | 不阻止（用户自管） | ⚠️ |
| 7.7 | pre-merge.sh 写 stderr | 捕获到错误信息 | ✅ |

### A8: Per-project notify hook  ✅

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 8.1 | notify.sh 存在 + status=completed | 脚本被调用，记录成功 | ✅ |
| 8.2 | notify.sh 失败 | 不影响 worker result（旁路） | ✅ |
| 8.3 | notify.sh 缺失 | 跳过 | ✅ |
| 8.4 | notify.sh 处理 partial | 同 completed 调用 | ✅ |
| 8.5 | notify.sh 处理 needs-info | 同上 | ✅ |
| 8.6 | notify.sh 处理 blocked | 同上 + 可选 alarm | ✅ |
| 8.7 | notify.sh 在 worktree 中运行 | cwd 是主 worktree，非 worker worktree | ✅ |

A8 参数合约：`extension.sh notify <status> <worker_label> <artifact_path>`
旁路：notify 失败 → stderr warning + exit 0（不阻塞主流程）

### A9: Per-project pre-spawn hook  ✅

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 9.1 | pre-spawn.sh 存在 | 每个 spawn 前调用一次 | ✅ |
| 9.2 | pre-spawn.sh 失败 | spawn 阻止（abort） | ✅ |
| 9.3 | pre-spawn.sh 缺失 | 跳过 | ✅ |
| 9.4 | pre-spawn.sh 设置 env vars（KEY=VALUE） | 解析到 `--exports FILE` | ✅ |
| 9.5 | pre-spawn.sh 创建 worktree | 由 root 接手使用 | 🆕 (未实测) |
| 9.6 | pre-spawn.sh 写日志 | 项目日志记录 | ✅ |
| 9.7 | pre-spawn.sh 输出非 KEY=VALUE 行 | 静默丢弃 | ✅ (regex 过滤) |

---

## 实施状态

| 轴 | 状态 | 实现位置 |
|---|---|---|
| A1 overlay | ✅ | jcode-native + docs |
| A2 worker policy | ✅ | jcode-native + docs |
| A3 skills/ | ✅ | jcode-native + docs |
| A4 mcp.json | ✅ | jcode-native + docs |
| A5 role override | ✅ | `scripts/extension.sh role` |
| A6 verify | ✅ | `scripts/extension.sh verify` |
| A7 pre-merge | ✅ | `scripts/extension.sh pre-merge` |
| A8 notify | ✅ | `scripts/extension.sh notify` |
| A9 pre-spawn | ✅ | `scripts/extension.sh pre-spawn` |

9 axes × 7 sub-cases = 63 boundary scenarios.
7 axes bundle-shipped, 4 jcode-native + 5 bundle conventions.