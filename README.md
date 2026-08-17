# lazible-jcode

A self-contained bundle of **jcode customization markdown**, versioned
in git, that you can clone onto any machine and use to bootstrap a
consistent jcode environment.

This repo is **not** a fork of [1jehuang/jcode](https://github.com/1jehuang/jcode).
It carries:

- A reference `config.toml` (live snapshot) plus `.example` templates
  that document every supported option
- An **enhanced default main-agent prompt overlay**
  (`swarm/prompt-overlay.md`) that turns the default main agent into a
  swarm-coordinator-first agent
- **Worker swarm policy + role templates** (`swarm/swarm-prompt.md`,
  `swarm/roles/*.md`) for the root session to load when spawning
  workers
- A **human-readable architecture overview** (`swarm/ARCHITECTURE.md`)
  documenting the star topology, contracts, and integration gates
  (not installed — human reference only)

## Layout

```
lazible-jcode/
├── README.md
├── AGENTS.md                          # Maintenance manual for this repo (not installed)
├── config/
│   ├── config.toml                    # Live snapshot of ~/.jcode/config.toml (sanitized)
│   ├── config.toml.example            # Annotated reference (subset)
│   └── mcp.json.example               # Reference ~/.jcode/mcp.json (secrets redacted)
├── swarm/                              # Generic swarm coordination + worker role templates
│   ├── prompt-overlay.md              # Enhanced default main-agent prompt (→ ~/.jcode/prompt-overlay.md)
│   ├── swarm-prompt.md                # Root + worker policy (→ ~/.jcode/swarm-prompt.md)
│   ├── ARCHITECTURE.md                # Human-readable overview (not installed)
│   └── roles/                          # Worker persona templates
│       ├── reviewer.md
│       ├── implementer.md
│       ├── investigator.md
│       ├── migrator.md
│       ├── test-writer.md
│       └── doc-writer.md
├── scripts/
│   ├── install.sh                     # Linear, unconditional, overwrite-by-default installer (3 steps)
│   ├── uninstall.sh                   # Inverse: removes symlinks + optionally the binary
│   └── swarm-sweep.sh                 # Manual cleanup for stale swarm worktrees (→ ~/.local/bin/swarm-sweep)
└── docs/
    ├── INSTALL.md                     # Detailed install / uninstall / troubleshooting
    ├── EXTENSIONS.md                  # Per-project extension points (10 axes)
    ├── ARCHITECTURE.md                # Three-layer view: jcode native + extensions + MCP
    └── INTEGRATIONS.md                # Recommended local MCP server stack
```

## Quick start

```bash
# 1. Clone the repo
git clone https://github.com/vanpipy/lazible-jcode.git
cd lazible-jcode

# 2. Install jcode + overlay + swarm config + .jcode/mcp.json (3 steps, overwrite-by-default; step 3 idempotent)
./scripts/install.sh

# 2b. Or, set up the bundle for a different project (installs bundle + inits that project's .jcode/mcp.json)
./scripts/install.sh --project=/path/to/your/project

# 3. Verify
command -v jcode
jcode --version
jcode run "say hello"
```

The installer is **always idempotent and unconditional**: it runs 3
steps every time, overwrites every destination, and backs up any
pre-existing file at the destination to `<dst>.bak.<timestamp>` first.
Fast path: when a destination is already a symlink to the source
target, it is left unchanged (no backup, no recreate) — so repeated
runs do not accumulate `.bak.<ts>` files.

### Install flags

The accepted flags are:

| Flag | Effect |
|---|---|
| `-h`, `--help` | Show usage |
| `--project=PATH` | Init `.jcode/mcp.json` for PATH (default: the bundle's own checkout). Use when setting up the bundle for another project.

See `docs/INSTALL.md` for full install / uninstall / troubleshooting
detail, including the `--purge`, `--yes`, and `--keep-binary` flags on
`scripts/uninstall.sh`. Pre-flight env checks (bash ≥ 4, git, curl/wget,
writable HOME and /tmp) are documented in `docs/ENVIRONMENTS.md` and run
automatically as `install.sh` step 0.

## What's in the swarm config

The `swarm/` directory carries the root session's coordination rules,
six worker role templates, an enhanced main-agent prompt overlay, and
a human-readable architecture overview. Unlike `skills/`, this is
**not** workflow guidance the model triggers on; it is the literal
prompt + persona content jcode reads.

- `swarm/prompt-overlay.md` — **enhanced default main-agent prompt**.
  Concise subset of the swarm rules that belongs on the *main* prompt:
  invariants, decision flow, hard-spawn-for-code rule. jcode appends
  this to the base system prompt at session start. Installed as
  `~/.jcode/prompt-overlay.md`.
- `swarm/swarm-prompt.md` — project-agnostic coordination policy for
  the root session and every spawned worker: model routing, when to
  spawn, communication discipline, verification gates, worktree
  topology. Installed as `~/.jcode/swarm-prompt.md`.
- `swarm/ARCHITECTURE.md` — the goals, star topology diagram, and
  contracts (invariants + output contract + cross-worker handoff) for
  this overlay bundle. Not installed — human reference only.
- `swarm/roles/*.md` — six persona templates (`reviewer`, `implementer`,
  `investigator`, `migrator`, `test-writer`, `doc-writer`). Installed
  as `~/.jcode/roles/*.md`. The root session prepends the appropriate
  role template to the spawn prompt when constructing a worker.

Worker-only concerns (worktree paths, output schema, per-role
workflow) belong in `swarm-prompt.md` and `roles/*.md`, not in the
main overlay.

### Where the three layers fit

jcode ships a base tool set, prompt layering, lifecycle hooks, and
swarm coordination out of the box. The bundle layers
**per-project extension points** on top (A1-A10 in
`docs/EXTENSIONS.md`) and ships a canonical **local MCP stack**
(filesystem + git + serena; `docs/INTEGRATIONS.md`) that the A4 axis
auto-loads. For the layered view — what is jcode-native, what is
bundle convention, what is MCP — see `docs/ARCHITECTURE.md`.

### Coordination rules at a glance

The overlay enforces a star topology and a typed-artifact contract
across every spawned worker. The headline rules:

- **One root per session**, exactly one coordinator. Workers never
  talk to each other; all handoffs are worker → root → worker.
- **8-field typed artifact** per completion: `status`, `findings`,
  `evidence[]`, `edge_cases_considered[]`, `validation`,
  `open_questions[]`, `confidence`, `what_i_did_not_check[]`. Status
  is one of `completed | partial | needs-info | blocked`. Root reads
  the artifact mechanically; prose-only summaries are rejected.
- **Scope owns files**: workers stage only the files the spawn
  prompt lists. Anything outside goes to `open_questions[]`, never to
  a commit.
- **M3 (silent worker disappearance) is a known limitation**. Two
  layers of cleanup cover the residue at different scopes: a
  session-level reaper (engine-side, automatic) for spawned workers
  that reported back and sat idle, and `swarm-sweep` (manual) for
  the git worktree + branch residue they leave behind. See
  `AGENTS.md` "Cleanup: stale swarm worktrees".
- **Push to `main` requires a verbatim "yes"** in chat, no matter
  what the original task said. Local commits and feature-branch
  pushes are free; the user can `git push` themselves.

For the full rule set, see `swarm/prompt-overlay.md` (main-agent
view) and `swarm/swarm-prompt.md` (worker-policy view).

## What's not in this repo

This bundle covers jcode customization at the **prompt / overlay**
layer. It does not patch or fork the jcode binary itself. If you
want to change jcode's base identity or behavior at compile time,
fork upstream and rebuild; this repo will continue to install on top
of any binary (upstream, canary, fork) without conflict.

If you need skills (e.g. project-specific TDD patterns, framework
guides), install them as plain `SKILL.md` directories under
`~/.jcode/skills/`. This repo no longer ships a `skills/` directory —
the layout is intentionally minimal so project authors can layer
their own skills on top.

## What is and isn't committed

| File / dir | Committed? | Why |
|---|---|---|
| `swarm/**/*.md` | ✅ | Generic swarm config + role templates; no secrets, no per-project state |
| `config/*.example` | ✅ | Reference only, no secrets |
| `config/config.toml` | ✅ | Live snapshot; no API keys live here, only model names and keybindings |
| `~/.jcode/mcp.json` | ❌ | NOT committed. Live MCP server tokens — must remain local. Shape reference: `config/mcp.json.example`. Recommended local-only stack (filesystem + git + serena): `docs/INTEGRATIONS.md` |
| `~/.jcode/builds/`, `cache/`, `logs/`, `sessions/`, `memory/`, telemetry files | ❌ | Runtime state; rebuilt on each session |

## License

MIT, same as upstream jcode. See upstream for full license text.

This repo contains no upstream jcode source code or binary — only
prompt / overlay markdown that loads on top of any jcode install.