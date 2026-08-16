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
- A **human-readable architecture overview** (`swarm/ARCHITECTURE.md`)
  documenting the star topology, contracts, and integration gates
- A standalone installer (`scripts/install.sh`) and uninstaller
  (`scripts/uninstall.sh`) that symlinks the above into `~/.jcode/`
  (plus installs the jcode binary via the upstream installer)
- A project-level `AGENTS.md` that jcode loads at session start

## Layout

```
lazible-jcode/
├── README.md
├── AGENTS.md                          # Project-level jcode instructions
├── config/
│   ├── config.toml                    # Live snapshot of ~/.jcode/config.toml (sanitized)
│   ├── config.toml.example            # Annotated reference (subset)
│   └── mcp.json.example               # Reference ~/.jcode/mcp.json (secrets redacted)
├── swarm/                              # Generic swarm coordination + worker role templates
│   ├── prompt-overlay.md              # Enhanced default main-agent prompt (→ ~/.jcode/prompt-overlay.md)
│   ├── swarm-prompt.md                # Root + worker policy (→ ~/.jcode/swarm-prompt.md)
│   ├── ARCHITECTURE.md                # Human-readable overview (→ ~/.jcode/ARCHITECTURE.md)
│   └── roles/                          # Worker persona templates
│       ├── reviewer.md
│       ├── implementer.md
│       ├── investigator.md
│       ├── migrator.md
│       ├── test-writer.md
│       └── doc-writer.md
├── scripts/
│   ├── install.sh                     # Linear, unconditional, overwrite-by-default installer (3 steps)
│   └── uninstall.sh                   # Inverse: removes symlinks + optionally the binary
└── docs/
    └── INSTALL.md                     # Detailed install / uninstall / troubleshooting
```

## Quick start

```bash
# 1. Clone the repo
git clone https://github.com/vanpipy/lazible-jcode.git
cd lazible-jcode

# 2. Install jcode + overlay + swarm config + AGENTS.md (3 steps, overwrite-by-default)
./scripts/install.sh

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

There are no optional flags. The only accepted flags are:

| Flag | Effect |
|---|---|
| `-h`, `--help` | Show usage |

See `docs/INSTALL.md` for full install / uninstall / troubleshooting
detail, including the `--purge`, `--yes`, and `--keep-binary` flags on
`scripts/uninstall.sh`.

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
  this overlay bundle. Installed as `~/.jcode/ARCHITECTURE.md`.
- `swarm/roles/*.md` — six persona templates (`reviewer`, `implementer`,
  `investigator`, `migrator`, `test-writer`, `doc-writer`). Installed
  as `~/.jcode/roles/*.md`. The root session prepends the appropriate
  role template to the spawn prompt when constructing a worker.

Worker-only concerns (worktree paths, output schema, per-role
workflow) belong in `swarm-prompt.md` and `roles/*.md`, not in the
main overlay.

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
| `~/.jcode/mcp.json` | ❌ | NOT committed. Live MCP server tokens — must remain local. Shape reference: `config/mcp.json.example` |
| `~/.jcode/builds/`, `cache/`, `logs/`, `sessions/`, `memory/`, telemetry files | ❌ | Runtime state; rebuilt on each session |

## Note on AGENTS.md

`AGENTS.md` is committed as-is from a prior iteration of this repo and
was intentionally **not** rewritten as part of the cleanup. It still
references files and directories that no longer exist in this bundle
(`skills/`, `jcode-patches/`, tick-era scripts, etc.). Treat it as a
historical structure reference, not as the source of truth for the
current layout. The current layout is documented above and in
`docs/INSTALL.md`. If you want a project-level instruction file that
matches the current repo, copy the relevant sections from this README
into a fresh `AGENTS.md` of your own.

## License

MIT, same as upstream jcode. See upstream for full license text.

This repo contains no upstream jcode source code or binary — only
prompt / overlay markdown that loads on top of any jcode install.