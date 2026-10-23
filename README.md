# lazible-jcode

My [jcode](https://github.com/1jehuang/jcode) configuration.

This repository is **configuration only**. It holds the values that make jcode
run the way I want, plus four skills. It does not build, patch or install the
jcode binary.

```text
config/config.toml     ->  ~/.jcode/config.toml            verbatim copy
config/skills/*/       ->  ~/.jcode/skills/*/              authoritative
scripts/install        ->  wires the two above
```

## Layout

| Path | What it is |
| --- | --- |
| `config/config.toml` | The live jcode config, verbatim. Edit this. |
| `config/prompt-overlay.md` | Copy of `~/.jcode/prompt-overlay.md`, for review |
| `config/swarm-prompt.md` | Copy of `~/.jcode/swarm-prompt.md`, for review |
| `config/mcp.example.json` | MCP server shape, with placeholder values |
| `config/skills/goal/` | `/goal` skill |
| `config/skills/orchestrator/` | `/orchestrate` skill |
| `config/skills/long-task-discipline/` | Rules ambient workers must follow |
| `config/skills/optimization/` | Performance workflow notes |
| `scripts/install` | Copies config and skills into `~/.jcode` |
| `scripts/uninstall` | Reverses install |

## Install

```bash
git clone <this-repo> ~/Project/lazible-jcode
cd ~/Project/lazible-jcode
./scripts/install
```

Five phases: preflight, config, skills, verify, state. Preflight fails if
`~/.jcode/config.toml` is a symlink, because writing through it would corrupt
this repo. Verify ends with 5 checks.

Preview first with `./scripts/install --dry-run`.

## Editing

The repo is the source of truth for `config.toml` and the skills. Change the
repo, then run `./scripts/install`.

```bash
$EDITOR config/config.toml && ./scripts/install
```

Skills are rewritten on every install, so a stale or hand-edited copy under
`~/.jcode/skills/` cannot drift.

The two prompt files go the other way. `~/.jcode/prompt-overlay.md` and
`~/.jcode/swarm-prompt.md` are edited live; the copies in `config/` exist for
review, and `install` only checks them against live rather than overwriting
live. If they drift, copy the live file back:

```bash
cp ~/.jcode/prompt-overlay.md config/prompt-overlay.md
cp ~/.jcode/swarm-prompt.md   config/swarm-prompt.md
```

`swarm-engineering` is not in this repo. It ships with jcode, so adopting it
here would make `install` overwrite a jcode-provided skill.

## Not managed here

- the jcode binary, install it separately
- MCP servers, they live in `~/.jcode/servers.json` and `~/.jcode/mcp.json`
- `~/AGENTS.md`, yours to edit
- everything else under `~/.jcode`, including runtime state and goal history

Earlier versions of this repo also installed helper CLIs to `~/.local/bin`
(`jcode-goal`, `jcode-l2-check`, `jcode-tool-policy`, `jcode-orchestrate`,
`jcode-audit-log`) and orchestrator prompts to
`~/.local/share/jcode-orchestrate/`. This repo no longer manages them.
`uninstall` leaves them alone. Remove them by hand if you want them gone.

## Uninstall

```bash
./scripts/uninstall --dry-run   # preview
./scripts/uninstall             # removes state.json only
./scripts/uninstall --full --yes  # also config.toml and this repo's skills
```

The jcode binary and `~/AGENTS.md` are never removed.

## Requirements

- `jcode` on `PATH`, installed separately
- `bash`, `python3` 3.11 or newer (for `tomllib`)
