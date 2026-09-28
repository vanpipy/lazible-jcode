# `lazible-jcode` Configuration Design (v1, source-executable version)

> This document maps the vision in `new.md` against the actual `~/Project/patched-jcode` source line by line,
> marking what is already implemented, what is genuinely new in `new.md`, and what still has to be filled in
> inside this new repo. All references use source locations (crate / file / line).

`new.md` remains the **vision layer**, answering *what we want jcode to look like in the future*;
this document is the **executable layer**, answering *can this `config/config.toml` run today, and if
not, where does the missing piece go*.

> **Implementation status note** (2026-09-28): the original design had 4 profiles (default / autonomous / conservative / research).
> In practice only `autonomous` survives : the other three were either empty overlays (no-op), had all fields already baked
> into base, or referenced hook scripts not yet implemented (Conservative's pre_tool gate). Currently **1 profile**, see
> [`config/profiles/README.md`](config/profiles/README.md). The multi-profile architecture referenced later in this document
> is kept as historical design context.

---

## 1. Assessment conclusion (one sentence)

**80% of what `new.md` describes already exists in jcode source** : it just isn't organized under `new.md`'s names.
The remaining 20% is what `new.md` genuinely introduces (profile directory, worktree auto-strategy,
permission-gate abstraction, repair-loop retry ceiling, etc.), and it needs to land in `lazible-jcode`
via **patch files + profile directory convention**, without modifying jcode source.

### 1.1 Feasibility matrix

| `new.md` concept | Source reality | Where it lands |
| --- | --- | --- |
| `~/.jcode/config.toml` single-file config | ✅ implemented (`jcode-base/src/config.rs`, `jcode-config-types/src/lib.rs`) | `config/config.toml` |
| `[display] / [keybindings] / [provider] / [ambient] / [hooks] / [safety] / [notifications]` etc. sections | ✅ implemented (30+ `[section]`s) | existing `config/config.toml` |
| `profiles/` (default / autonomous / conservative / research) | ❌ no such concept in source | new `config/profiles/` (overlay, not switch) |
| `prompts/` (orchestrator.md / worker.md / reviewer.md / tester.md) | ⚠️ source has skills (SKILL.md format) but no orchestrator prompt library | borrow the skills system, `config/skills/` |
| `workflows/` (feature.md / bugfix.md etc.) | ⚠️ source has no workflow file, but has `/overnight` command + DAG scheduler | carried in this repo's `WORKFLOWS.md`, not in config |
| `policies/` (autonomy / git / safety / validation) | ⚠️ `[safety]` is implemented (ntfy / email / telegram / discord); the rest expressed via `[ambient]` and hooks | existing `config.toml` + `[hooks]` + external scripts |
| `templates/` (task.md / handoff.md / report.md) | ⚠️ `handoff artifact` is implemented (`SWARM_TASK_GRAPH.md`), but no markdown templates | `config/templates.md` doc |
| `state/` `runs/` `logs/` | ✅ implemented (`~/.jcode/state/`, `~/.jcode/state/runs/`) | all gitignored |
| `ambient/state.json` `queue.json` `usage.json` | ✅ implemented (`app-core/src/ambient.rs`: `AmbientState`, `ScheduledItem`) | all gitignored |
| `AGENTS.md` as project-level config | ✅ implemented via `load_agents_md_files_from_dirs` (`jcode-base/src/prompt.rs:864`) | `AGENTS.md` inside project, not in this repo |
| `~/AGENTS.md` global layer | ✅ same as above | user's `$HOME/AGENTS.md`, not in this repo |
| Skill system | ✅ fully implemented (`~/.jcode/skills/`, `~/.agents/skills/`, `.jcode/skills/`, etc.) | `config/skills/` (portable) |
| Task DAG (orchestrator → workers → repair) | ✅ **implemented as the core** (`jcode-plan/src/dag/`, `SWARM_TASK_GRAPH.md`) | owned by jcode engine; this repo only configures behavior |
| Autonomous Coding Control Loop (Diagnose → Repair → Execute → Verify) | ✅ in `app-core/src/overnight.rs` (1275 lines) + `app-core/src/ambient.rs` | `config.toml` parameter knobs |
| Safety Boundary / Permission Gate | ✅ via `HooksConfig.pre_tool` (`config.rs:848-852`) | `config.toml [hooks]` section |
| Worktree auto-strategy | ⚠️ `SwarmSpawnMode` exists, but auto worktree selection is not implemented | `config/notes.md` documents the manual algorithm |
| DAG edge is normal communication / chat is the exception | ✅ DAG data-flow design, `SWARM_TASK_GRAPH.md §5` finalized | engine level |

**Conclusion**: what this repo has to do is **not to reinvent**, but rather:

1. **Solidify the real config that already exists** → `config/config.toml` (already there, needs to align fields with source)
2. **Introduce a `profiles/` overlay layer** → addresses the multi-profile vision from `new.md` §2
3. **Introduce `skills/`** → the bidirectional sync strategy with `~/.jcode/skills/`
4. **Introduce `policies/`** → orchestration layer, not config layer (wrap with scripts)
5. **Maintain `.gitignore` discipline** → already exists, needs review

---

## 2. Source reality (by crate / doc)

### 2.1 Configuration schema (implemented)

| Section / item | Source |
| --- | --- |
| `[keybindings]` | `jcode-config-types/src/keybindings.rs:639` |
| `[dictation]` | `jcode-base/src/config.rs` nearby |
| `[display]` + `[display.native_scrollbars]` + `[display.colors]` | `jcode-config-types/src/display.rs:238` |
| `[features]` (check_updates / memory / swarm / mermaid / auto_poke / message_timestamps / persist_memory_injections / kv_cache_miss_notices / update_channel) | `jcode-config-types/src/lib.rs:1072-1119` |
| `[websearch]` + `engine` enum (Duckduckgo/Bing/Searxng) | `jcode-config-types/src/lib.rs:1122-1189` |
| `[tools]` (profile / enabled / disabled / disable_base_tools) | `jcode-base/src/config.rs:548-575` |
| `[acp]` (profile / tool_profile) | `jcode-base/src/config.rs:550-560` |
| `[auth]` (trusted_external_sources) | `jcode-config-types/src/lib.rs:510-518` |
| `[provider]` (default_model / default_provider / openai_reasoning_effort / openai_service_tier / openai_native_compaction_mode / cross_provider_failover / same_provider_account_failover / stream_idle_timeout_secs / max_retries / retry_backoff_cap_secs) | `jcode-config-types/src/lib.rs:1191-1260` |
| `[providers]` (`NamedProviderConfig` instances) | `jcode-config-types/src/lib.rs:439-507` |
| `[agents]` (swarm_model / swarm_spawn_mode / swarm_strip_layout / memory_* / embedding_* / swarm_max_concurrent_agents) | `jcode-config-types/src/lib.rs:521-647` |
| `[terminal]` (spawn_hook / focus_hook / preferred) | `jcode-config-types/src/lib.rs:717-761` |
| `[hooks]` (turn_start / turn_end / session_start / session_end / pre_tool / post_tool / pre_tool_timeout_ms) | `jcode-config-types/src/lib.rs:775-874` |
| `[ambient]` (enabled / provider / model / allow_api_keys / api_daily_budget / min_interval_minutes / max_interval_minutes / pause_on_active_session / proactive_work / work_branch_prefix / visible) | `jcode-config-types/src/lib.rs:1263-1306` |
| `[notifications]` (turn_complete / turn_complete_min_secs / turn_complete_todo_min_secs / turn_complete_only_when_unfocused / turn_complete_sound) | `jcode-config-types/src/lib.rs:1313-1345` |
| `[safety]` (ntfy_topic / ntfy_server / desktop_notifications / email_* / telegram_* / discord_* / jade_relay_*) | `jcode-config-types/src/lib.rs:1348-1448` |
| `[gateway]` (enabled / port / bind_addr) | `jcode-config-types/src/lib.rs:1451-1470` |
| `[compaction]` (mode: Reactive/Proactive/Semantic + 10 parameters) | `jcode-config-types/src/lib.rs:351-400` |
| `[power]` (prevent_sleep_while_streaming) | `jcode-config-types/src/lib.rs:1473-1493` |
| `[autoreview]` `[autojudge]` | `jcode-config-types/src/lib.rs:877-922` |
| `[launch_hotkeys]` + `[[launch_hotkeys.entries]]` | `jcode-config-types/src/lib.rs:1496-1539` |
| `[sponsors]` | `jcode-config-types/src/lib.rs:886-912` |

**Environment variable overrides** (153 `JCODE_*` variables, `config/env_overrides.rs`),
all named `JCODE_<SECTION>_<FIELD>` and applied via `apply_env_overrides` in `Config::load`,
overriding the corresponding TOML fields.

### 2.2 Resolution paths and directory conventions

Source: `jcode-storage/src/lib.rs:150-219`

```text
~/.jcode/                                  JCODE_HOME=$HOME/.jcode
├── config.toml                            main config (Config::path())
├── mcp.json                               MCP servers (auto-migrated from ~/.claude/mcp.json on first launch)
├── skills/                                global skills (auto-migrated from ~/.claude/skills, ~/.codex/skills on first launch)
├── ambient/
│   ├── state.json                         AmbientState
│   ├── queue.json                         ScheduledQueue
│   ├── visible_cycle.json                 VisibleCycleContext
│   └── cycle_result.json                  AmbientCycleResult
├── missions/<session_id>.json             Mission
├── sessions/                              session history (gitignored)
├── state/                                 persistent cross-restart state
│   └── runs/                              per-overnight-run artifacts
├── builds/                                binary channel
│   ├── stable/jcode
│   ├── current/jcode
│   └── versions/<version>/jcode
└── logs/

~/.config/jcode/                           app_config_dir(), sandboxed mode only

./AGENTS.md                                project-level instructions (injected into prompt)
./.jcode/skills/                           project-level skill (overrides global same-name skill)
./.jcode/mcp.json                          project-level MCP (overrides global)
./.mcp.json, ./.claude/mcp.json            Claude Code project config compatibility

~/AGENTS.md                                user global instructions
~/.agents/skills/, ~/.claude/skills/       cross-tool skill sharing
~/.claude/plugins/                         Claude Code plugins (auto-import skills)
```

### 2.3 Skill system (`jcode-base/src/skill.rs`)

`SkillRegistry` load order (global → project):

1. `~/.claude/plugins/.../skills/*/SKILL.md` (Claude plugins)
2. `~/.jcode/skills/*/SKILL.md`
3. `~/.agents/skills/*/SKILL.md`
4. `./.jcode/skills/*/SKILL.md` (project overlay, **per-session**, re-read each time)
5. `./.agents/skills/*/SKILL.md`
6. `./.claude/skills/*/SKILL.md`

The project overlay **overrides** the global on name collision. Same-name priority: user's own skills > plugins.

### 2.4 Task DAG (`jcode-plan/src/dag/`)

Source: `docs/SWARM_TASK_GRAPH.md` (605 lines, authoritative design)

```text
Mode    = Deep | Light
Origin  = Seed | Expand | Gap | Gate
Kind    = Explore | Implement | Verify | Fix | Synthesize | Critique

Engine ops:  seed, expand_node, complete_node, fail_node,
             inject_from_gate, requeue_failed, assemble_input, dispatch

Limits:      MAX_PLAN_ITEMS = 1024, MAX_SWARM_MEMBERS = 1000
             LIGHT_MODE_SUGGESTED_WORKERS (constant)
             GATE_COVERAGE_ENUMERATION_CAP (gate validation coverage)
```

This stack is **already implemented and is replacing the old agent-first swarm**, in very high agreement
with `new.md` §6. This repo does not own that design.

### 2.5 Ambient / Overnight / Mission (runtime)

| Module | Path | Purpose |
| --- | --- | --- |
| `AmbientManager` | `app-core/src/ambient.rs` | Cycle scheduling, visible mode |
| `ambient_runner.rs` / `ambient_scheduler.rs` | same directory | runner is the no-TUI mode, scheduler is the rotating trigger |
| `Mission` | `app-core/src/mission.rs:197` | per-session long-running goals (`Active/Paused/Blocked/NeedsDecision/BudgetLimited/Complete/Abandoned`) |
| `Goal` | `jcode-task-types/src/lib.rs` (it's task-types in practice : name is misleading) | cross-session long goals (`Draft/Active/Paused/Blocked/Completed/Archived/Abandoned`) + milestones |
| `/overnight` | `jcode-overnight-core/src/lib.rs:951` | overnight long-running manifest + task cards |

### 2.6 Hooks (gate mechanism)

Source: `jcode-config-types/src/lib.rs:775-874` + `docs/HOOKS.md`

```text
turn_start / turn_end / session_start / session_end
pre_tool / post_tool
pre_tool_timeout_ms = 5000

pre_tool is a **synchronous gate**: exit 0 passes, exit 2 rejects (stderr to the model), other failures pass through.
Other hooks are **fire-and-forget**.
```

This is the implementation of Permission Gate from new design §13.

---

## 3. What `new.md` genuinely introduces (gap)

Below are the concepts `new.md` envisions that **jcode source does not currently have**. This repo needs to
decide how to host them.

### 3.1 `profiles/` multi-profile switching

`new.md` envisions: `profiles/default/`, `profiles/autonomous/`, `profiles/conservative/`, `profiles/research/`.

**Reality**: jcode has no profile switching; only single-field pins like `JCODE_TOOL_PROFILE` / `JCODE_ACP_PROFILE` /
`agents.swarm_model`.

**This repo's decision**:

- `config/profiles/` holds **profile description files** (TOML snippets), only as an **overlay**, not a format jcode reads directly
- A profile lives at `config/profiles/<name>.toml`, describing:
  - which sections of `config.toml` it covers
  - the shell script `scripts/use-profile <name>` merges the overlay with base into `~/.jcode/config.toml`
- **Rationale**: avoid modifying jcode source; let users switch between roles (conservative vs autonomous) without manual edits

### 3.2 `workflows/` workflow templates

`new.md` §5 designs the Feature Workflow diagram.

**Reality**: jcode has the `/overnight` slash command (`overnight-core/src/lib.rs:951`) and the Task DAG engine
(`jcode-plan/src/dag/`). But **no declarative workflow file**.

**This repo's decision**:

- `config/WORKFLOWS.md` documents the procedures as instructions for humans / agents
- Does not enter jcode config, because jcode already covers via DAG + overnight

### 3.3 `policies/autonomy.md` autonomy levels

`new.md` §2 envisions four policy files: autonomy / git / safety / validation.

**Reality**:

- `[safety]` is implemented (notification channels for external side-effects)
- `[ambient]` already has `enabled` + interval fields
- `[hooks].pre_tool` already provides a permission gate
- **No centralized file declaring autonomy levels**

**This repo's decision**:

- `config/policies/autonomy.md` is a **markdown memo** that describes the default autonomy tiers in this repo
- Runtime behavior is expressed jointly via `[ambient]` and `[hooks]`
- Example: autonomous profile → `[ambient].enabled = true`, enable `[hooks].post_tool`, enable `[safety].email_enabled = true`

### 3.4 `templates/` handoff artifact templates

`new.md` §7 calls out "DAG edges are Typed Handoff".

**Reality**: `jcode-plan/src/dag/` already has the typed-handoff concept; the schema lives in source
(`SWARM_TASK_GRAPH.md` §6.3). But **no editable markdown templates** for humans / agents to consult while writing.

**This repo's decision**:

- `config/templates/handoff.md`, `config/templates/task.md`, `config/templates/report.md`
- Distributed as skill content, so the orchestrator agent consults them when emitting a handoff

### 3.5 Worktree auto-strategy

`new.md` §9 designs the auto worktree selection algorithm (file-conflict + risk based).

**Reality**: `SwarmSpawnMode` selects visible / headless / inline / auto, but **no worktree selection**.
- swarm references working directories via the `working_dir: Option<PathBuf>` field, with no automatic worktree decision.

**This repo's decision**:

- `config/notes/worktree-strategy.md` documents the manual decision algorithm (readable by this repo's scripts)
- Does not enter jcode config; jcode behavior is steered via spawn hooks + user's launch_hotkey entries

### 3.6 Repair-loop retry ceiling

`new.md` §12 envisions a `Retry Count < 3?` guard.

**Reality**: the DAG engine's `requeue_failed` lives in `jcode-plan/src/dag/ops.rs`, but retry counts are managed
inside the DAG : no user-level parameter is exposed.

**This repo's decision**: **no configurable item today**. `config/notes/repair-loop.md` notes this as a future jcode
engine parameter; it does not enter config.

---

## 4. `lazible-jcode` repo layout (v1 proposal)

```text
lazible-jcode/
├── README.md                       # what this repo is and how to use it
├── new.md                          # vision layer (v1 design original)
├── design.md                       # this file: source alignment + executable design
├── config.toml                     # ❌ should not be at root; use config/config.toml
├── config/
│   ├── config.toml                 # sanitized snapshot (committed)
│   ├── mcp.json                    # ❌ gitignore (use mcp.example.json as template)
│   ├── mcp.example.json            # committed: MCP server schema demo
│   ├── profiles/                   # new in v1: profile overlays
│   │   ├── README.md
│   │   ├── default.toml            # explicit empty overlay (baseline)
│   │   ├── autonomous.toml         # enable ambient, turn on notifications
│   │   ├── conservative.toml       # ambient off, compact notifications
│   │   └── research.toml           # heavier model, more memory rerank
│   ├── policies/                   # new in v1: declarative policy descriptions
│   │   ├── README.md
│   │   ├── autonomy.md             # autonomy levels + recommended config pointers
│   │   ├── git.md                  # worktree decision (manual algorithm)
│   │   └── repair-loop.md          # repair-loop guards (points at jcode engine)
│   ├── templates/                  # new in v1: handoff templates
│   │   ├── handoff.md
│   │   ├── task.md
│   │   └── report.md
│   ├── skills/                     # portable skill set (pushed into scenarios)
│   │   ├── README.md
│   │   └── optimization/           # example: copy from ~/Project/jcode/.jcode/skills/optimization
│   │       └── SKILL.md
│   └── notes/                      # design notes (not loaded at runtime)
│       ├── worktree-strategy.md
│       ├── repair-loop.md
│       └── mermaid-style.md        # Mermaid rendering conventions (see docs/MERMAID_RENDERING_REDESIGN.md)
├── scripts/
│   ├── README.md
│   ├── use-profile                 # merge base + profile into ~/.jcode/config.toml
│   ├── sync-skills                 # bidirectional sync between config/skills/ and ~/.jcode/skills/
│   ├── snapshot-config             # copy ~/.jcode/config.toml → config/config.toml and scrub
│   └── verify-sanitized            # ensure committed config has no token / path leaks
└── .gitignore                      # already exists, needs review
```

### 4.1 Commit / not-commit matrix

| Path | Commit? | Note |
| --- | --- | --- |
| `config/config.toml` | ✅ | scrubbed snapshot. Maintained by `snapshot-config` |
| `config/mcp.json` | ❌ | contains tokens, must stay local; use `.gitignore` |
| `config/mcp.example.json` | ✅ | token-less MCP server shape example |
| `config/profiles/*.toml` | ✅ | overlay snippets, no sensitive fields |
| `config/policies/*.md` | ✅ | markdown |
| `config/templates/*.md` | ✅ | markdown |
| `config/skills/*` | ✅ | shares skill content with jcode, portable |
| `.jcode/*` | ❌ | runtime state (contains worktree path, session_id) |
| `*.log` `target/` | ❌ | build artifacts |
| `~/AGENTS.md` `~/.jcode/*` | n/a | user-local |

---

## 5. Reconciliation with the existing `config/config.toml`

`config/config.toml` already exists (4459 bytes). Section-by-section reconciliation:

| Section | Status | Source field (`jcode-config-types`) | Action |
| --- | --- | --- | --- |
| `[keybindings]` | ✅ | `KeybindingsConfig` | keep |
| `[dictation]` | ✅ | `dictation` | keep |
| `[display]` | ✅ | `DisplayConfig` | keep |
| `[features]` | ✅ | `FeatureConfig` | keep |
| `[websearch]` | ✅ | `WebSearchConfig` | keep |
| `[tools]` | ✅ | `tools` | keep |
| `[acp]` | ✅ | `acp` | keep |
| `[auth]` | ✅ | `AuthConfig` | keep |
| `[provider]` | ✅ | `ProviderConfig` | keep |
| `[providers]` | empty | `NamedProviderConfig` map | keep (empty = use built-ins) |
| `[agents]` | ✅ | `AgentsConfig` | keep |
| `[terminal]` | empty | `TerminalConfig` | keep |
| `[hooks]` | ✅ | `HooksConfig` | keep |
| `[ambient]` | ✅ | `AmbientConfig` | keep |
| `[safety]` | ✅ | `SafetyConfig` | keep |
| `[notifications]` | ✅ | `NotificationsConfig` | keep |
| `[gateway]` | ✅ | `GatewayConfig` | keep |
| `[compaction]` | ✅ | `CompactionConfig` | keep |
| `[power]` | ✅ | `PowerConfig` | keep |
| `[autoreview]` | ✅ | `AutoReviewConfig` | keep |
| `[autojudge]` | ✅ | `AutoJudgeConfig` | keep |
| `[launch_hotkeys]` + `[[launch_hotkeys.entries]]` | ✅ | `LaunchHotkeysConfig` + entries | keep |

**Action items**:

- Field names and defaults already align with source
- Only gap: comment out empty sections (`[terminal]` / `[providers]`) so it's clear what to fill in
- For sensitive fields inside empty `[safety]` (e.g. `ntfy_topic`), keep env placeholder `~/<VAR>` instead of an empty string

---

## 6. Profile overlay design (new mechanism in v1)

### 6.1 Semantics

`profile` is not a jcode runtime concept. This repo defines it as:

> A TOML overlay that describes the difference from `config/config.toml`.

### 6.2 File format

Example `config/profiles/autonomous.toml`:

```toml
# autonomous profile : enable ambient + heavy notifications
[ambient]
enabled = true
allow_api_keys = true
proactive_work = true
min_interval_minutes = 5
max_interval_minutes = 30

[safety]
desktop_notifications = true
email_enabled = true

[hooks]
post_tool = ["~/.local/bin/jcode-audit-log"]
```

### 6.3 Merge algorithm (`scripts/use-profile`)

```bash
#!/usr/bin/env bash
# Merge base + profile into ~/.jcode/config.toml, without touching source files in the repo.
set -euo pipefail

profile="${1:-default}"
repo="$(cd "$(dirname "$0")/.." && pwd)"
base="${repo}/config/config.toml"
overlay="${repo}/config/profiles/${profile}.toml"
target="${JCODE_HOME:-$HOME/.jcode}/config.toml"

[[ -f "$overlay" ]] || { echo "unknown profile: $profile" >&2; exit 1; }

# Merge strategy: base sections as the floor, overlay sections override (deep merge).
# Simplified implementation: every jcode-supported section is map-of-maps / scalar : no list merges.
python3 - <<'PY' "$base" "$overlay" "$target"
import sys, tomllib
base = tomllib.loads(open(sys.argv[1]).read())
overlay = tomllib.loads(open(sys.argv[2]).read())
def deep(a, b):
    for k, v in b.items():
        if k in a and isinstance(a[k], dict) and isinstance(v, dict):
            deep(a[k], v)
        else:
            a[k] = v
deep(base, overlay)
with open(sys.argv[3], 'w') as f:
    f.write(toml_dump(base))
PY
```

Note: `tomllib` ships with Python 3.11+; for older Python, fall back to `tomli`.

### 6.4 Relationship with the jcode engine

- jcode never reads `config/profiles/`
- `scripts/use-profile` writes the merged result into `~/.jcode/config.toml`; jcode only sees the latter
- Therefore profile is a **shell-time abstraction** and does not affect jcode startup performance

---

## 7. Skills bidirectional sync (new mechanism in v1)

### 7.1 Reality

jcode skill sources:

1. `~/.jcode/skills/` (jcode global)
2. `~/.agents/skills/` (cross-tool)
3. `~/.claude/plugins/.../skills/` (Claude plugins)
4. `./.jcode/skills/`, `./.agents/skills/`, `./.claude/skills/` (project overlay)

`config/skills/` is the **portable skill set owned by this repo**.

### 7.2 Sync strategy

`scripts/sync-skills`:

- `--to-home`: copy `config/skills/` into `~/.jcode/skills/` (does not overwrite same-name user skills)
- `--from-home`: reverse direction (user-local edits flow back into the repo)
- `--to-project <dir>`: copy `config/skills/` into `<dir>/.jcode/skills/`
- Dry-run by default

### 7.3 Relationship with `.jcode/skills/optimization`

`~/Project/jcode/.jcode/skills/optimization/SKILL.md` is a **skill shipped with the source repo**,
not a user-distribution channel. This repo can borrow it initially, but its goal is to distribute
the user's own skills.

---

## 8. `.gitignore` review

`.gitignore` already exists; item by item:

```text
config/*           ← ignore everything under config/
!config/config.toml
config/mcp.json   ← belt and suspenders

.jcode/*          ← runtime state
.git-commit-msg/  ← harness temp dir
.git-spawn-scope/
.git-tmp/
```

**Additions for v1**:

```text
# profile drafts
config/profiles/*.local.toml

# locally-derived skills (experiments before syncing to home)
config/skills/.scratch/

# merged artifacts
config/.merged/
config/.snapshot-tmp/

# macOS / editor / build
.DS_Store
.vscode/ .idea/
target/
```

---

## 9. Verification flow (v1)

`scripts/verify-sanitized` must pass these checks:

1. `config/config.toml` parses via `toml` / `tomllib`
2. Known sensitive keys (`api_key`, `token`, `secret`, `password`) have empty string / placeholder values
3. Absolute paths must start with `~/` or `$HOME/` (no hard-coded `/home/...`)
4. Profile files follow the same rules
5. Skill content has no token (loose grep for `^[A-Za-z0-9_-]{40,}$`)

Behavior can be verified via `cargo run --bin jcode -- ...` or `jcode self-dev --build`.

---

## 10. Per-item mapping to `new.md`

| new.md § | Title | Where this doc addresses it |
| --- | --- | --- |
| 1 | Overall architecture | §2 (source component inventory) |
| 2 | Global config + project config | §1.1 + §5 |
| 3 | `~/.jcode` directory | §2.2 (resolution paths) |
| 4 | Autonomous Coding Control Loop | §2.5 (ambient + overnight) |
| 5 | Feature Workflow | §3.2 (no workflow file; owned by jcode engine) |
| 6 | Swarm / DAG | §2.4 (Task DAG) |
| 7 | Worker and Handoff | §3.4 (handoff templates) |
| 8 | Git / Worktree | §3.5 (no auto worktree strategy) |
| 9 | Worktree Auto Strategy | §3.5 |
| 10 | Validation Pipeline | §2.6 (hooks pre_tool + DAG verify gate) |
| 11 | Review Gate | §2.4 (`NodeKind::Critique`) |
| 12 | Repair Loop | §3.6 (no configurable retry ceiling) |
| 13 | Safety Boundary | §2.6 (hooks + `[safety]`) |
| 14 | Ambient + Autonomous | §2.5 |
| 15 | Six-layer architecture | §1.1 (feasibility matrix) + §2 |

---

## 11. Implementation checklist

| Step | Content | Verification |
| --- | --- | --- |
| 1 | Reconcile `config/config.toml` against the source schema | `toml parse` passes |
| 2 | Add `config/profiles/*.toml` (4 profiles) | `scripts/use-profile default` does not modify base |
| 3 | Add `config/policies/*.md` (3 files) | `git diff` only adds |
| 4 | Add `config/templates/*.md` (3 files) | same as above |
| 5 | Add `config/skills/optimization/SKILL.md` (borrowed) | jcode loads it at startup |
| 6 | Add `config/notes/*.md` (3 files) | markdown renders correctly |
| 7 | Add `scripts/use-profile`, `sync-skills`, `snapshot-config`, `verify-sanitized` | `shellcheck` passes |
| 8 | Review `.gitignore` | `git status` is clean |
| 9 | Update `README.md` | readable |
| 10 | Commit | CI / pre-commit passes |

---

## 12. What this repo does NOT cover

- **Modifying jcode source**: this repo does not touch `~/Project/jcode/crates/`
- **AGENTS.md content**: each project has its own AGENTS.md; this repo does not own any
- **Runtime state**: nothing under `~/.jcode/state/`, `~/.jcode/sessions/` etc. enters git
- **Binary channel**: `~/.jcode/builds/` is managed by `scripts/install*.sh`

---

## 13. References (inside the jcode repo)

- `docs/SWARM_TASK_GRAPH.md` : Task DAG authoritative design
- `docs/SWARM_ARCHITECTURE.md` : legacy swarm design (superseded by DAG version)
- `docs/AMBIENT_MODE.md` : Ambient mode design
- `docs/SAFETY_SYSTEM.md` : Safety system
- `docs/HOOKS.md` : Hooks (permission gate)
- `docs/MEMORY_ARCHITECTURE.md` : Memory system
- `docs/SERVER_ARCHITECTURE.md` : Server architecture
- `docs/SYSTEM_PROMPT_CONFIG.md` : System prompt injection
- `docs/MERMAID_RENDERING_REDESIGN.md` : Mermaid rendering
- `.jcode/skills/optimization/SKILL.md` : Skill example
- `.jcode/semantic-todo-migration-spec.md` : Todo semantic migration (matches todo tool fields)