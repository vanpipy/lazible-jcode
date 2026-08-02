# lazible-jcode

A self-contained bundle of **jcode configuration and skills**, versioned in git,
that you can clone onto any machine and use to bootstrap a consistent jcode
environment.

This repo is **not** a fork of [1jehuang/jcode](https://github.com/1jehuang/jcode).
It carries:

- Skills (`skills/<name>/SKILL.md`) compatible with jcode's skill loader — these
  are **actual copies** of skills from a live `~/.jcode/skills/` install
- A reference `config.toml` (live snapshot) plus `.example` templates that
  document every supported option
- An **enhanced default main-agent prompt overlay** (`swarm/prompt-overlay.md`)
  that turns the default main agent into a swarm-coordinator-first agent
- **Custom jcode patches** (`jcode-patches/`) that rewrite the **base** system
  prompt itself (not just an overlay), so the swarm-coordinator-first
  behavior is baked into the jcode binary at build time. Maintained via a
  reusable patch + build script + sync flow. See `docs/SELFDEV.md`.
- A standalone installer (`scripts/install.sh`) and uninstaller
  (`scripts/uninstall.sh`) modeled after the upstream `jcode.sh/install`
  script, but driven entirely from this repo so it works offline and without
  `curl | bash`
- A `copy-from-jcode.sh` helper that snapshots a live `~/.jcode/` into this repo

## Layout

```
lazible-jcode/
├── README.md
├── AGENTS.md                          # Project-level jcode instructions
├── config/
│   ├── config.toml                    # Live snapshot of ~/.jcode/config.toml (sanitized)
│   ├── config.toml.example            # Annotated reference (subset)
│   ├── mcp.json.example               # Reference ~/.jcode/mcp.json (secrets redacted)
│   └── providers.example.toml         # Reference provider profiles
├── skills/
│   ├── install-jcode/
│   │   ├── SKILL.md                   # "/install-jcode" skill
│   │   └── jcode-install.sh           # Standalone installer for jcode
│   ├── copy-from-jcode/
│   │   ├── SKILL.md                   # "/copy-from-jcode" skill
│   │   └── copy-from-jcode.sh         # Snapshot ~/.jcode into this repo
│   ├── optimization/
│   │   └── SKILL.md                   # Ported from 1jehuang/jcode/.jcode/skills
│   ├── auto-swarm-planner/
│   │   └── SKILL.md                   # Copied from a live ~/.jcode/skills
│   ├── git-expert/
│   │   └── SKILL.md                   # Copied from a live ~/.jcode/skills
│   └── rn-dev/
│       └── SKILL.md                   # Copied from a live ~/.jcode/skills
├── swarm/                              # Generic swarm coordination + worker role templates
│   ├── swarm-prompt.md                 # Bundled root-session prompt (becomes ~/.jcode/swarm-prompt.md)
│   ├── prompt-overlay.md               # Enhanced default main-agent prompt (→ ~/.jcode/prompt-overlay.md)
│   └── roles/                          # Worker persona templates (reviewer, implementer, ...)
│       ├── reviewer.md
│       ├── implementer.md
│       ├── investigator.md
│       ├── migrator.md
│       ├── test-writer.md
│       └── doc-writer.md
├── scripts/
│   ├── install.sh                     # Linear, unconditional, overwrite-by-default installer (4 steps)
│   ├── uninstall.sh                   # Removes binary + lazible-jcode-owned symlinks
│   ├── build-jcode-canary.sh          # selfdev: clone jcode + apply patch + cargo build canary
│   ├── sync-jcode-source.sh           # selfdev: pull upstream + re-validate patches
│   └── lib/
│       └── configure_path.sh
├── docs/
│   └── INSTALL.md
└── .gitignore
```

## Quick start

```bash
# 1. Clone the repo
git clone https://github.com/vanpipy/lazible-jcode.git
cd lazible-jcode

# 2. Install jcode + overlay + skills + AGENTS.md (one command, overwrite-by-default).
./scripts/install.sh

# 3. (Optional) Pull the current machine's jcode config into this repo
./skills/copy-from-jcode/copy-from-jcode.sh
```

If `jcode-patches/*.patch` exists in the repo, step 1 builds a canary from
those patches and replaces `~/.local/bin/jcode` automatically. If no patch
exists, the upstream installer runs instead. Either way the result overwrites
the binary unconditionally.

### Install options

`scripts/install.sh` is intentionally minimal — only two flags:

| Flag | Effect |
|---|---|
| `--canary-version <v>` | Pin the jcode tag used for the canary build (only matters when `jcode-patches/*.patch` exists). Default: latest |
| `--clean` | Pass through to the canary builder: wipe the source-dir (`~/Project/jcode`) before re-cloning. Use when a previous build polluted the working tree. Slower on rerun |
| `-h`, `--help` | Show usage |

The script **always** runs all 4 steps, **always** overwrites the destination,
and **always** backs up any pre-existing file at the destination to
`<dst>.bak.<timestamp>` first. There are no `--skip-*` / `--refresh` /
`--dry-run` flags.

To pin the canary build:

```bash
./scripts/install.sh --canary-version v0.65.0
```

To force a clean re-clone (when a previous build polluted the source-dir):

```bash
./scripts/install.sh --clean
```

Run `./scripts/install.sh --help` for the full usage block.

## Skills

| Skill | Trigger | Purpose | Source |
|---|---|---|---|
| `/install-jcode` | "install jcode", "set up jcode" | Detect platform, pick the best install path, verify, smoke-test | repo-authored |
| `/copy-from-jcode` | "copy jcode config", "snapshot ~/.jcode" | Snapshot a live `~/.jcode/` into this repo's `config/` and `skills/` directories | repo-authored |
| `/auto-swarm-planner` | "fan out", "parallel work", "swarm" | Detect swarm-shaped tasks, plan fan-out, spawn workers, coordinate via DMs + typed handoff artifacts | live `~/.jcode/skills/` |
| `/git-expert` | any git command | Wake-up checklist, danger defenses, QiPDA conventions, pre-commit gates | live `~/.jcode/skills/` |
| `/rn-dev` | RN / Android / TS work | Modular 3-tier architecture, debug gates, toolchain, pre-commit CI gates, Detox E2E | live `~/.jcode/skills/` |
| `/optimization` | "optimize", "performance", "latency" | Define metrics, attribute bottlenecks, macro before micro | ported from upstream |

All skills follow the upstream jcode format: a directory under `.jcode/skills/`
(or this repo's `skills/`) containing a `SKILL.md` with YAML frontmatter:

```yaml
---
name: <skill-name>
description: <when to trigger>
skill-type: <domain | orchestration | ...>
version: <semver>
type: skill
skill-role: guidance
---
```

## Swarm config

The `swarm/` directory carries the root session's swarm coordination rules,
six worker role templates, and an enhanced main-agent prompt overlay. Unlike
`skills/`, this is **not** workflow guidance the model triggers on; it is the
literal prompt + persona content the root session reads when constructing
spawn calls.

- `swarm/swarm-prompt.md` — project-agnostic guidance for the root session and
  every spawned worker (model routing, when to spawn, communication discipline,
  verification gates). Installed to `~/.jcode/swarm-prompt.md`.
- `swarm/roles/*.md` — six persona templates (`reviewer`, `implementer`,
  `investigator`, `migrator`, `test-writer`, `doc-writer`). Installed as
  `~/.jcode/roles/*.md`.
- `swarm/prompt-overlay.md` — **enhanced default main-agent prompt**. Concise
  subset of the swarm rules that belongs on the *main* prompt: model routing,
  spawn-when rules, hygiene, decomposition order, verification anti-patterns.
  jcode appends this to the base system prompt at session start. Installed as
  `~/.jcode/prompt-overlay.md` by `scripts/install.sh`. Worker-only concerns
  (worktree paths, output schema, per-role workflow) belong in
  `swarm-prompt.md`, not here.

Sync all three via `scripts/install.sh` (default). `skills/copy-from-jcode/copy-from-jcode.sh`
also still works for `swarm-prompt.md` + `roles/`, but does not manage the
overlay — use `install.sh` for that.

## Self-development (custom jcode build)

The overlay (above) is **additive** — it sits after jcode's base system prompt
in the prompt concatenation order. To make the swarm-coordinator-first
behavior truly baked-in, lazible-jcode ships patches against jcode's source in
`jcode-patches/`. When the repo has any `*.patch` file there, `scripts/install.sh`
step 1 automatically builds a canary from those patches and replaces
`~/.local/bin/jcode` (backed up as `jcode.bak.<ts>`). No flag needed.

```bash
# Re-run the installer to rebuild the canary against the current patches:
./scripts/install.sh --canary-version v0.65.0

# Or run the canary build script standalone (side-by-side, doesn't touch main):
./scripts/build-jcode-canary.sh --jcode-version v0.65.0
```

The patch replaces the upstream identity line "maximally proactive coding
agent" with "swarm-coordinator-first coding agent" inside
`crates/jcode-base/src/prompt/system_prompt.md` (which is compiled into the
binary via `include_str!`). See `docs/SELFDEV.md` for the full flow including
re-syncing against upstream jcode releases.

To **stop** selfdev and fall back to upstream-only installs, simply remove the
files under `jcode-patches/`. The next `install.sh` will use the upstream
installer instead.

## What is and isn't committed

| File / dir | Committed? | Why |
|---|---|---|
| `skills/<name>/SKILL.md` | ✅ | Skills are pure markdown; safe |
| `swarm/**/*.md` | ✅ | Generic swarm config + role templates; no secrets, no per-project state |
| `config/*.example` | ✅ | Reference only, no secrets |
| `config/config.toml` | ✅ | Live snapshot; no API keys live here, only model names and keybindings |
| `config/mcp.json` | ❌ | Contains live MCP server tokens — **must remain local** |
| `~/.jcode/builds/`, `cache/`, `logs/`, `sessions/`, `memory/`, telemetry files | ❌ | Runtime state; rebuilt on each session |

## License

MIT, same as upstream jcode. See upstream for full license text.

The `jcode-patches/` directory contains patches against the upstream jcode
source. The patches themselves are MIT-licensed (matching upstream); the
resulting built binary is governed by the upstream jcode license — see
upstream for full text.