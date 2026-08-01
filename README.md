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
- A standalone installer (`scripts/install.sh`) and uninstaller (`scripts/uninstall.sh`)
  modeled after the upstream `jcode.sh/install` script, but driven entirely from
  this repo so it works offline and without `curl | bash`
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
│   └── roles/                          # Worker persona templates (reviewer, implementer, ...)
│       ├── reviewer.md
│       ├── implementer.md
│       ├── investigator.md
│       ├── migrator.md
│       ├── test-writer.md
│       └── doc-writer.md
├── scripts/
│   ├── install.sh                     # Repo-level installer (mirrors jcode.sh/install)
│   ├── uninstall.sh
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

# 2. Install jcode using this repo's installer (no curl | bash required)
./scripts/install.sh

# 3. (Optional) Pull the current machine's jcode config into this repo
./skills/copy-from-jcode/copy-from-jcode.sh
```

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

The `swarm/` directory carries the root session's swarm coordination rules and
six worker role templates. Unlike `skills/`, this is **not** workflow guidance
the model triggers on; it is the literal prompt + persona content the root
session reads when constructing spawn calls.

- `swarm/swarm-prompt.md` — project-agnostic guidance for the root session and
  every spawned worker (model routing, when to spawn, communication discipline,
  verification gates). Installed to `~/.jcode/swarm-prompt.md`.
- `swarm/roles/*.md` — six persona templates (`reviewer`, `implementer`,
  `investigator`, `migrator`, `test-writer`, `doc-writer`). Installed as
  `~/.jcode/roles/*.md`.

Sync both directions with `skills/copy-from-jcode/copy-from-jcode.sh` (default
behavior). The `--exclude-swarm` flag skips swarm handling if a project wants
only skills.

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