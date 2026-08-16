# 10×10 extension-mechanism walkthrough

Each axis × 10 sub-cases. Convention: scenarios focus on **boundary
behavior** (what root should do at the edge), not the happy path.

Sub-case categories per axis:
- **.1-.7** — basic presence/absence/permission scenarios
- **.8** — cross-axis interaction (how does this axis interact with others?)
- **.9** — versioning drift (file changes mid-session)
- **.10** — multi-machine sync (git-tracked, shared across machines)

Total: 10 axes × 10 sub-cases = **100 boundary scenarios**.

---

## Group 1: jcode-native (4 axes)

### A1: Per-project prompt-overlay

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 1.1 | per-project overlay 存在 + 非空 | jcode 优先使用 per-project | ✅ |
| 1.2 | per-project overlay 缺失 | jcode 退到 global | ✅ |
| 1.3 | per-project overlay 为空 | jcode 退到 global（trim 检查） | ✅ |
| 1.4 | per-project overlay 是 prepend 短指令 | jcode 拼接后注入 | ✅ |
| 1.5 | per-project overlay 是完整 overlay | jcode 完全替换 | ✅ |
| 1.6 | per-project overlay 路径权限拒绝 | jcode 退到 global + 警告 | ✅ |
| 1.7 | per-project overlay 引用不存在的 skill | jcode 不验证；worker load 时失败 | ✅ |
| 1.8 | overlay 引用 A3 per-project skill | worker 通过 auto-load 拿到 skill | ✅ (jcode-native) |
| 1.9 | overlay 在 spawn 之后变更 | 下次 session 生效（不会 hot-reload） | ✅ (lazy 语义) |
| 1.10 | overlay git-tracked，同事 pull 后用不同机器 | 同 base SHA 下行为一致 | ✅ (text-only, 无 state) |

### A2: Per-project swarm-prompt.md

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 2.1 | per-project swarm-prompt 存在 | jcode 优先使用 | ✅ |
| 2.2 | per-project 缺失 | jcode 退到 global | ✅ |
| 2.3 | per-project 为空 | jcode 退到 built-in default | ✅ |
| 2.4 | per-project 重写 model routing | workers 按新路由执行 | ✅ |
| 2.5 | per-project 重写 anti-patterns | workers 看到新反模式 | ✅ |
| 2.6 | per-project 包含 invalid 指令 | workers 可能误执行 | ⚠️ |
| 2.7 | per-project 与 global 内容相同 | 行为不变 | ✅ |
| 2.8 | swarm-prompt 与 A1 overlay 冲突 | overlay 注入到 base，swarm-prompt 注入到 workers；两者并存 | ✅ (jcode 独立加载) |
| 2.9 | swarm-prompt 在 worker 已 spawn 后变更 | worker 已缓存的 prompt 不变，新 spawn 才生效 | ✅ (lazy 语义) |
| 2.10 | swarm-prompt git-tracked，跨机器 | 同 per-commit SHA 行为一致 | ✅ |

### A3: Per-project skills/

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 3.1 | `<repo>/.jcode/skills/<name>/` 存在 | jcode 加载 | ✅ |
| 3.2 | per-project skills 目录缺失 | jcode 用 global skills | ✅ |
| 3.3 | per-project skill 与 global 同名 | per-project 覆盖 | ✅ |
| 3.4 | per-project skill 缺 SKILL.md | jcode 跳过 + 警告 | ⚠️ |
| 3.5 | per-project skill 引用不存在的资源 | skill load 失败 | ⚠️ |
| 3.6 | per-project skills 损坏 | daemon 报错但 global 仍可用 | ⚠️ |
| 3.7 | `.agents/skills/` 也存在 | jcode 同时加载 | ✅ |
| 3.8 | skill 内部引用 A1 overlay 内容（不允许，但项目可能试） | skill 不知道 overlay 存在；独立 load | ✅ (正交) |
| 3.9 | skill 文件 session 中变更 | jcode `load_from_dir` 在 access 时重读（`skill.rs:264` 注释："edits are visible without daemon restarts"） | ✅ (live-reload) |
| 3.10 | skill git-tracked，跨机器 | SKILL.md 内容相同的机器行为一致；skill 引用的二进制依赖（git-tracked）也跟随 | ⚠️ (deps 跟不跟取决于 repo) |

### A4: Per-project MCP servers

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 4.1 | `<repo>/.jcode/mcp.json` 存在 | jcode 加载 | ✅ |
| 4.2 | mcp.json 缺失 | jcode 用 global `~/.jcode/mcp.json` | ✅ |
| 4.3 | mcp.json JSON 语法错 | jcode 报错，global 仍生效 | ⚠️ |
| 4.4 | mcp.json 引用不存在的 command | server 启动失败 | ⚠️ |
| 4.5 | mcp.json 中 server 名与 global 重复 | per-project wins | ✅ |
| 4.6 | `.mcp.json` 也存在 | jcode 合并 | ✅ |
| 4.7 | `.claude/mcp.json` 也存在 | 全部合并，per-project 优先 | ✅ |
| 4.8 | mcp.json 引用 `${SOME_ENV}` 但未设置 | server 启动失败，jcode 不验证 env | ⚠️ — **bundle 可加 `mcp validate` 检查 env** |
| 4.9 | mcp.json session 中变更 | 行为取决于 daemon 实现；通常需要重启 | ⚠️ (out of bundle scope) |
| 4.10 | mcp.json git-tracked 但 `${API_KEY}` 是用户级 | API key 不进 git；需要每个机器单独设置 | ⚠️ (用户责任) |

---

## Group 2: bundle convention (6 axes)

### A5: Per-project role override

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 5.1 | `<repo>/.jcode/roles/<name>.md` 存在 + 非空 | per-project wins | ✅ |
| 5.2 | per-project 缺失 | global fallback | ✅ |
| 5.3 | per-project 为空 | global fallback + 警告 | ✅ |
| 5.4 | role 名不在 6 个中 | exit 2 红线 | ✅ |
| 5.5 | per-project 完全重写 | 使用 per-project | ✅ |
| 5.6 | per-project 破坏 7+1 schema | root 不验证；worker 端 schema check 失败 | ⚠️ |
| 5.7 | per-project 与 global 完全相同 | 行为不变 | ✅ |
| 5.8 | per-project role 引用 A9 pre-spawn 注入的 env var | role 模板不知道 env；不依赖 | ✅ (正交) |
| 5.9 | per-project role 在 worker spawn 之后变更 | 已 spawn 的 worker 不变（cached prompt）；新 spawn 用新版本 | ✅ (lazy) |
| 5.10 | per-project role git-tracked，跨机器 | 同 role-name + sha 下行为一致 | ✅ (text-only) |

### A6: Per-project verify hook

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 6.1 | verify.sh 存在 + executable + exit 0 | 通过 | ✅ |
| 6.2 | verify.sh exit 非零 | verification 失败，阻止 commit | ✅ |
| 6.3 | verify.sh 缺失 | 跳过（absence not failure） | ✅ |
| 6.4 | verify.sh 存在但非 executable | 跳过 + 警告 | ✅ |
| 6.5 | verify.sh 超时 | bash 默认无超时 | ⚠️ |
| 6.6 | verify.sh 修改 tracked 文件 | 不阻止（用户自管） | ⚠️ |
| 6.7 | verify.sh 写入 stderr | stderr 透传 | ✅ |
| 6.8 | verify.sh 与 A7 pre-merge 同时跑 | 各自独立；顺序无定义 | ✅ (无 shared state) |
| 6.9 | verify.sh 产 >100MB 输出 | 输出到 stdout/stderr；可能 OOM（用户责任） | ⚠️ |
| 6.10 | verify.sh git-tracked，跨机器 | hook 内容相同 → 行为相同；环境依赖（node/pnpm）需各机器有 | ⚠️ (依赖管理) |

### A7: Per-project pre-merge hook

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 7.1 | pre-merge.sh 存在 + executable + exit 0 | merge 继续 | ✅ |
| 7.2 | pre-merge.sh exit 非零 | merge 阻止，stderr 透传 | ✅ |
| 7.3 | pre-merge.sh 缺失 | 跳过 | ✅ |
| 7.4 | pre-merge.sh 存在但非 executable | 跳过 + chmod 提示 | ✅ |
| 7.5 | pre-merge.sh 超时（≥5 min） | merge 阻止 + timeout 错误 | ✅ |
| 7.6 | pre-merge.sh 修改 tracked 文件 | 不阻止（用户自管） | ⚠️ |
| 7.7 | pre-merge.sh 写 stderr | 捕获到错误信息 | ✅ |
| 7.8 | pre-merge.sh 在 worker 还活跃时跑 | hook 看 main worktree；不看 worker worktree | ✅ (cwd = main) |
| 7.9 | pre-merge.sh 阻塞在交互 prompt | timeout 触发 → exit 124 → merge 阻止 | ✅ (timeout 兜底) |
| 7.10 | pre-merge.sh 修改 git refs | hook 自己改的，bundle 不阻止；可能 merge 后冲突 | ⚠️ (用户责任) |

### A8: Per-project notify hook

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 8.1 | notify.sh 存在 + status=completed | 脚本被调用，记录成功 | ✅ |
| 8.2 | notify.sh 失败 | 不影响 worker result（旁路） | ✅ |
| 8.3 | notify.sh 缺失 | 跳过 | ✅ |
| 8.4 | notify.sh 处理 partial | 同 completed 调用 | ✅ |
| 8.5 | notify.sh 处理 needs-info | 同上 | ✅ |
| 8.6 | notify.sh 处理 blocked | 同上 + 可选 alarm | ✅ |
| 8.7 | notify.sh 在 worktree 中运行 | cwd 是主 worktree，非 worker worktree | ✅ |
| 8.8 | artifact >4000 chars（jcode MAX_SWARM_COMPLETION_REPORT_CHARS） | jcode 截断；hook 看到截断版本 | ⚠️ (jcode 上游) |
| 8.9 | artifact 缺 8 字段之一 | hook 拿到缺字段 artifact；hook 自身决定怎么处理 | ⚠️ — **bundle 可加 `artifact validate` 在 notify 前检查** |
| 8.10 | notify.sh 在多 worker 并发完成时 | 每个 worker completion 独立调用一次 hook；并发可能 race | ⚠️ (用户自管 file locking) |

### A9: Per-project pre-spawn hook

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 9.1 | pre-spawn.sh 存在 | 每个 spawn 前调用一次 | ✅ |
| 9.2 | pre-spawn.sh 失败 | spawn 阻止（abort） | ✅ |
| 9.3 | pre-spawn.sh 缺失 | 跳过 | ✅ |
| 9.4 | pre-spawn.sh 设置 env vars（KEY=VALUE） | 解析到 `--exports FILE` | ✅ |
| 9.5 | pre-spawn.sh 创建 worktree | 由 root 接手使用 | 🆕 (未实测) |
| 9.6 | pre-spawn.sh 写日志 | 项目日志记录 | ✅ |
| 9.7 | pre-spawn.sh 输出非 KEY=VALUE 行 | 静默丢弃 | ✅ |
| 9.8 | KEY 以数字开头（invalid bash var） | regex `^[A-Z_][A-Z0-9_]*=` 拒绝 → 丢弃 | ✅ |
| 9.9 | 重复 KEY（pre-spawn 输出两次 FOO=bar） | 后写入覆盖前写入；最终 exports 文件含一个 export FOO=bar | ⚠️ (last-write-wins) |
| 9.10 | pre-spawn.sh 引用未设置的 env var | bash 自己出错 → exit 非零 → spawn abort | ✅ (strict mode) |

### A10: Per-project scratch dir

| # | 场景 | 期望 | 状态 |
|---|---|---|---|
| 10.1 | cwd 在 git repo 内 | path 含 `<repo-name>-<short-sha>` | ✅ |
| 10.2 | cwd 非 git repo | 退到 hash 化的稳定 key | ✅ |
| 10.3 | `$LAZIBLE_TMPDIR` 已设置 | 覆盖默认 `/tmp` | ✅ |
| 10.4 | `wt <label>` 子命令 | 输出 `$root/wt-<label>` | ✅ |
| 10.5 | `scratch` 子命令 | 输出 `$root/scratch` | ✅ |
| 10.6 | 跨子目录同 repo | path 相同（依赖 `git rev-parse --show-toplevel`） | ✅ |
| 10.7 | cwd 在 jcode session 内（`$TMPDIR` 被 override） | bundle 强制 `/tmp` | ✅ |
| 10.8 | scratch dir 已有上次残留 | bundle 不自动清理；提供 `scratch-dir clean` 子命令 | 🆕 — **待实现** |
| 10.9 | 不同 repo 同名（`<basename>` 撞车） | 短 SHA 区分；hash 兜底（不同 cwd → 不同 SHA） | ✅ |
| 10.10 | scratch dir 只读（权限问题） | bundle 不创建；root 报错 | ⚠️ (用户责任) |

---

## 第 2 步：识别 gap

10×10 走查暴露的 bundle 缺口：

| Gap | 来源 | 优先级 |
|---|---|---|
| **G1**: `extension.sh scratch-dir clean` | A10.8 | HIGH（stale residue 是常见痛点） |
| **G2**: `extension.sh artifact validate <file>` | A8.9 | HIGH（hook 收到缺字段 artifact 时 bundle 应能查） |
| **G3**: `extension.sh mcp validate --env` | A4.8 | MEDIUM（mcp.json env var 检查） |
| **G4**: `extension.sh verify` 加 timeout | A6.5 | MEDIUM（verify.sh 现在无 timeout，可能挂死） |
| **G5**: `extension.sh scratch-dir clean` 跨 `<short-sha>` 清 | A10.10 + multi-machine | LOW（不是 immediate 痛点） |

**Top 2 实施**（G1 + G2）：
1. `extension.sh scratch-dir clean` — 清当前项目的所有 wt-* + scratch 内容（dry-run by default）
2. `extension.sh artifact validate <file>` — 验证 typed artifact 有 8 个 contract fields

跳过 G3-G5（不是 immediate 痛点，且 G3 需要读取 server config schema，复杂度高）。