# Architecture (jcode native + extensions + MCP)

How three layers cooperate to give lazible-jcode its working capability:

```
┌─────────────────────────────────────────────────────────────────┐
│ Layer 3: MCP servers  (filesystem, git, serena, ...)            │
│         → registered as mcp__<server>__<tool> tools             │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2: lazible-jcode  (11 axes: A1-A11)                       │
│         → A1-A4 = jcode-native  /  A5-A11 = bundle convention   │
├─────────────────────────────────────────────────────────────────┤
│ Layer 1: jcode native  (built-in tools, prompt, hooks, swarm)    │
│         → ~35 tool modules + 7 prompt layers + lifecycle hooks  │
└─────────────────────────────────────────────────────────────────┘
```

The bundle does not invent its own substrate. Layer 1 is jcode itself;
Layer 3 is the MCP ecosystem. The bundle's job (Layer 2) is to make
jcode's existing extension points **explicit, project-scoped, and
single-entry-point** — and to ship one canonical MCP stack
(filesystem + git + serena) that all three layers can agree on.

---

## Layer 1: jcode native (the substrate)

**Source**: `~/Project/jcode/crates/jcode-app-core/src/tool/mod.rs`
(`Registry::base_tools`), `~/Project/jcode/crates/jcode-base/src/prompt.rs`,
`~/Project/jcode/docs/`.

### Tool registry

35 native tool modules, registered as base tools (stateless, cached in
a `OnceLock`) + 5 per-session tools (`skill_manage`, `swarm`, `batch`,
`conversation_search`, `integration_tools`). Live-counted 2026-08-16
by `grep insert_tool crates/jcode-app-core/src/tool/mod.rs`:

| Category | Tools |
|---|---|
| File I/O | `read`, `write`, `edit`, `multiedit`, `patch`, `apply_patch`, `ls` |
| Shell + search | `bash`, `agentgrep` |
| Network | `browser`, `webfetch`, `websearch` |
| Workflow | `todo`, `bg`, `schedule`, `initiative` |
| History | `conversation_search`, `session_search`, `jcode_docs` |
| Coordination | `swarm`, `batch` |
| Cross-session | `memory`, `skill_manage` |
| Integrations | `gmail`, `mcp` (MCP management tool itself) |
| Debug | `selfdev`, `invalid`, `debug_socket` |

MCP tools are added **after** the base set via
`register_mcp_tools_for_dir()` (`tool/mod.rs:911`). Names are prefixed
by `dispatch_name()` as `mcp__<server>__<tool>` — verified collision-
free because jcode-native names never start with `mcp__`. Registry is
a `HashMap<String, Arc<dyn Tool>>`; `register()` is
last-write-wins (no explicit guard).

Tool definitions are **sorted by name before returning** to the API
(`definitions()` `sort_by`), which preserves prompt-cache locality
across calls. MCP tools participate in this sort — that is why the
"advertise-early" path (`tool/mod.rs:981-1041`) registers proxy tools
from the on-disk schema cache **before** the live connection settles:
it avoids the prompt-cache miss that the cold connection would
otherwise cause (issue #206 Phase 2).

### System prompt (7 layers, ordered)

From `docs/SYSTEM_PROMPT_CONFIG.md` and `prompt.rs::build_prompt`:

1. **Base prompt** — `crates/jcode-base/src/prompt/system_prompt.md`,
   overridable by `./.jcode/system-prompt.md` or `~/.jcode/system-prompt.md`
   (first non-empty wins; whitespace-only falls back to default).
2. Capability modules (e.g. Mermaid rendering guidance).
3. Self-dev guidance (self-dev sessions only).
4. **AGENTS.md** — `<cwd>/AGENTS.md` → `~/AGENTS.md` (concatenated).
5. **Prompt overlay** — `<cwd>/.jcode/prompt-overlay.md` → `~/.jcode/prompt-overlay.md`
   (concatenated; both included when present).
6. **Preferred tools** — `<cwd>/.jcode/preferred-tools.md` → `~/.jcode/preferred-tools.md`
   (concatenated).
7. Memory + active skill (dynamic; not cached).

`prompt.rs::load_swarm_prompt` is a separate channel for worker-side
routing rules: `<cwd>/.jcode/swarm-prompt.md` → `~/.jcode/swarm-prompt.md`
→ built-in `DEFAULT_SWARM_PROMPT`. It is **not** part of the main
prompt — only injected when the swarm tool spawns a worker.

### Lifecycle hooks

From `docs/HOOKS.md`: `pre_tool`, `post_tool`, `session_start`,
`session_end`, `turn_end`. Set in `~/.jcode/config.toml`
`[hooks]` table or via `JCODE_HOOK_*` env. The hook contract is
JSON-payload-over-env (`JCODE_HOOK_PAYLOAD`, capped 16 KB), with
`pre_tool` gating and `post_tool` observing.

`pre_tool_timeout_ms` (default 5000) applies only to gate hooks.

### Swarm / spawn

From `docs/SWARM_ARCHITECTURE.md`: star topology with **one
coordinator per session**. Mode-gated spawning: light + ad hoc =
no children of children; deep mode = recursive. Each spawned worker's
`report_back_to_session_id` reconstructs the ancestry chain. The
session-level reaper (engine-side, automatic, ~30 min idle threshold,
configurable, `0` disables) handles M3 silent disappearance;
`extension.sh workspace destroy|clean` and the legacy `swarm-sweep`
helper (bundle-shipped) handle the workspace-level residue.

---

## Layer 2: lazible-jcode extension mechanism

Single entry point: `scripts/extension.sh <subcommand>`. Discovery:
`extension.sh doctor` enumerates the A1-A11 surface in fixed columns.

| Axis | File | Loaded by | Type |
|---|---|---|---|
| **A1** | `<repo>/.jcode/prompt-overlay.md` | jcode direct (layer 5 of prompt) | jcode-native |
| **A2** | `<repo>/.jcode/swarm-prompt.md` | jcode direct (load_swarm_prompt) | jcode-native |
| **A3** | `<repo>/.jcode/skills/<n>/SKILL.md` | jcode direct (skill.rs auto-discover) | jcode-native |
| **A4** | `<repo>/.jcode/mcp.json` | jcode direct (mcp/protocol.rs) | jcode-native |
| **A5** | `<repo>/.jcode/roles/<n>.md` | `extension.sh role` | bundle convention |
| **A6** | `<repo>/.jcode/verify.sh` | `extension.sh verify` | bundle convention |
| **A7** | `<repo>/.jcode/pre-merge.sh` | `extension.sh pre-merge` | bundle convention |
| **A8** | `<repo>/.jcode/notify.sh` | `extension.sh notify` (bypass) | bundle convention |
| **A9** | `<repo>/.jcode/pre-spawn.sh` | `extension.sh pre-spawn` (env inject) | bundle convention |
| **A10** | (none — derived path) | `extension.sh scratch-dir` | bundle derived |

**Design note**: A1-A4 are not bundle inventions. They are
**re-statements of jcode's existing extension points** under a single
discoverable surface. Anything you put at A1-A4 is loaded by jcode
itself — the bundle just provides the names, the per-project
defaults, and a `doctor` view to make the surface legible.

A5-A9 are bundle conventions because jcode does not natively
understand per-project role overrides, verify gates, pre-merge gates,
notify sinks, or pre-spawn env injection. Each convention is a file
at `<repo>/.jcode/<name>.sh`; absence is not failure (all hooks
return exit 0 when missing); bypass vs. strict semantics differ per
axis (`notify` is bypass, `pre-merge` is strict).

The full 11×11 boundary-behavior walkthrough (121 scenarios across
A1-A11) is in `docs/EXTENSIONS.md`.

---

## Layer 3: MCP as the A4 axis implementation

**MCP is not an independent third layer. It is the A4 axis made real.**

A4 says "jcode loads `<cwd>/.jcode/mcp.json` automatically". The
bundle ships one recommended stack (`config/mcp.json.example`,
3 servers: filesystem + git + serena; sqlite dropped after live
verification that all current sqlite MCPs fail JSON-RPC — see
`docs/INTEGRATIONS.md` "Why no sqlite MCP").

### jcode's MCP config discovery order

From `crates/jcode-base/src/mcp/protocol.rs::load_for_dir`
(verified 2026-08-16):

1. `~/.jcode/mcp.json` — jcode global
2. `~/.claude.json` — Claude Code user config (`mcpServers` + per-project)
3. `~/.claude/mcp.json` — legacy Claude Code global
4. **Per-project chain** (later wins on same server name):
   - `./.jcode/mcp.json` — bundle's A4 (highest per-project priority)
   - `./.mcp.json` — Claude Code project config
   - `./.claude/mcp.json` — legacy

Disabled servers stay configured (visible to `mcp` management tool)
but are **not** spawned or shown as connecting (issue #436).

### Tool registration after discovery

1. `McpManagementTool` is registered immediately (the `mcp` tool).
2. For each enabled server, `register_mcp_tools_for_dir()` reads the
   on-disk schema cache (`McpSchemaCache`) and registers proxy tools
   under `mcp__<server>__<tool>` **before** the connection settles.
3. A `tokio::spawn` task does the live `connect_all()` in the
   background, refreshes the on-disk schema cache, and re-registers
   tools (idempotent — the live schema simply replaces the cached
   proxy).
4. The `McpStatus` server event streams the
   `connecting → live:<count>` transition to the TUI.

### Tool naming guarantees

`McpTool::dispatch_name()` formats `mcp__<server>__<tool>`, replacing
`-` with `_`. This means:

- jcode-native tools (no `mcp__` prefix) **cannot collide** with MCP
  tools by construction.
- Cross-server collision within MCP is possible only if two servers
  define the same `name` and `server_name`. Verified live: filesystem
  14 + git 28 + serena 29 = 71 distinct `mcp__*` names.

### Bundle's MCP-side helpers

| Helper | Subcommand | Purpose |
|---|---|---|
| `extension.sh mcp info` | (one-shot) | Print active config path + server count |
| `extension.sh doctor` (A4 row) | (one-shot) | Show per-project vs. global wiring status |
| `extension.sh preflight` | (gate) | Verify jcode + bundle + scratch dir before spawn |

---

## Layer interaction: concrete scenarios

### Scenario 1: New project onboarding

| Step | Layer | Action |
|---|---|---|
| 1 | Layer 1 | jcode reads `~/.jcode/config.toml` + per-project `AGENTS.md` |
| 2 | Layer 1 | jcode loads `./.jcode/prompt-overlay.md` if present |
| 3 | Layer 1 | jcode loads `./.jcode/swarm-prompt.md` for spawned workers |
| 4 | Layer 1 | jcode auto-discovers `./.jcode/skills/` |
| 5 | Layer 1 | jcode auto-loads `./.jcode/mcp.json` → A4 axis (Layer 3 entry) |
| 6 | Layer 2 | Root runs `extension.sh doctor` to see A1-A11 status |
| 7 | Layer 3 | filesystem + git + serena connect; 71 tools registered |

### Scenario 2: Single-file typo (≤ 2 lines, **no MCP**)

Layer 1 only. `edit file_path="README.md" old_string="..." new_string="..."`.
The bundle's overlay §1 reserves this shape for the root session; spawning
an `implementer` worker for it is anti-pattern #1 in `swarm-prompt.md` §9.

### Scenario 3: Cross-file symbol refactor

Three layers cooperate:

```
[Layer 1 — jcode-native]
  read file="src/auth.rs"
  ls path="src/"

[Layer 3 — serena MCP]
  find_symbol name_path="authenticate" relative_path="src/auth.rs"
  find_referencing_symbols name_path="authenticate" relative_path="src/auth.rs"
  replace_symbol_body name_path="authenticate" relative_path="src/auth.rs" body="..."
  rename_symbol name_path="authenticate" new_name="verify_credentials" relative_path="src/auth.rs"

[Layer 2 — bundle convention]
  extension.sh verify          # A6: project verify gate (optional)
  extension.sh pre-merge ...   # A7: cross-worker integration gate (optional)
```

The root session decides **which layer handles each step**. The default
rule (overlay §1, prompt-overlay.md): small + one-off → Layer 1;
structured + batched → Layer 3; cross-cutting gate → Layer 2.

### Scenario 4: Long-running initiative (multi-session)

- **Layer 1 hooks** (`[hooks]` in config.toml): every tool call emits
  `pre_tool` / `post_tool` events with `JCODE_HOOK_PAYLOAD` (capped 16 KB).
- **Layer 2 A8 notify hook**: each worker completion fires `notify.sh`
  with `status` + `label` + `artifact`; bypass mode = failure does not
  block the workflow.
- **Layer 2 A9 pre-spawn hook**: env vars injected into workers via
  `--exports FILE` protocol.
- **Layer 1 memory**: cross-session facts via `memory remember` /
  `recall` (the bundle's `swarm/swarm-prompt.md` §10 names what belongs
  in project memory vs. artifact).

---

## Design insights from source

| Insight | Source |
|---|---|
| MCP tool names cannot collide with jcode-native names | `dispatch_name()` enforces `mcp__<server>__<tool>` prefix; `tool_name_is_allowed()` checks `mcp__` as wildcard |
| Tool definitions are sorted before sending to API | `definitions()` `sort_by(a.name, b.name)` — preserves prompt-cache locality |
| Advertise-early prevents first-call prompt-cache miss | `register_mcp_tools_for_dir()` proxies from on-disk schema cache before live connection; live re-registration is idempotent (#206 Phase 2) |
| Per-project config overrides global by server name | `load_for_dir()` merges with `merge_servers_preferring_runnable()` |
| Disabled MCP servers stay visible but do not spawn | `is_enabled()` filter in `register_mcp_tools_for_dir()` (#436) |
| Lazy swarm-prompt loading — workers see edits on next spawn | `load_swarm_prompt()` reads at spawn time; running workers keep their captured prompt (per `docs/SYSTEM_PROMPT_CONFIG.md`) |
| Skills live-reload without daemon restart | `skill.rs::load_from_dir` re-reads on access (per `docs/EXTENSIONS.md` A3.9) |
| `preferred-tools.md` is a soft prompt addition | Plain text injected into the prompt — does not alter the registry or disable any tool |

---

## Failure-mode boundaries (what each layer falls back to)

| Failure | Layer responsible | Fallback |
|---|---|---|
| `~/.jcode/mcp.json` JSON-broken | Layer 3 | jcode logs error, global remains in effect (per A4.3 in EXTENSIONS.md) |
| MCP server unreachable | Layer 3 | Tool call errors; Layer 1 `bash` + curl for fallback |
| `${VAR}` unset in `mcp.json` | Layer 3 | Server fails to start (jcode does not pre-validate env — A4.8) |
| `AGENTS.md` references unknown skill | Layer 1 | Skill load fails; jcode does not pre-validate (A1.7) |
| Worker merge fails pre-merge gate | Layer 2 (A7) | Merge blocked, exit code propagated; worker retry path |
| Notify hook errors | Layer 2 (A8) | Bypass: workflow continues, stderr surfaces warning |
| Pre-spawn hook errors | Layer 2 (A9) | Strict: spawn aborts, exit code propagated |
| Verify hook errors | Layer 2 (A6) | Bundle's verification step 6 fails (currently no timeout — A6.5) |
| Overlay misconfigured | Layer 2 (A1) | jcode falls back to global (per `prompt.rs::load_prompt_overlay_files_from_dir`) |
| `mcp list` shows 0/3 connected | Layer 3 | First-run cold start: `uvx`/`npx` may exceed 30s backoff; smoke-test once then `mcp reload` (per `docs/INTEGRATIONS.md` "First-run timeout note") |

---

## Boundaries this doc does NOT cover

- **`EXTENSIONS.md`** has the full 10×10 (100-scenario) boundary walkthrough. This doc explains the **architecture**; `EXTENSIONS.md` enumerates the **edge cases**.
- **`INTEGRATIONS.md`** has the per-MCP-server usage notes (when to pick filesystem vs. bash, git vs. shell git, serena vs. read/grep). This doc names MCP as the A4 axis; `INTEGRATIONS.md` documents the servers.
- **`swarm/ARCHITECTURE.md`** documents the star-topology coordination model between root and workers. This doc names Layer 2; `swarm/ARCHITECTURE.md` is the swarm contract.

Cross-references stay intentional. **One doc per concern; no duplication.**