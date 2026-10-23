# lazible-jcode

My [jcode](https://github.com/1jehuang/jcode) configuration.

This repository is **configuration only**. It holds the values that make jcode
run the way I want, plus one skill. It does not build, patch or install the
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
| `config/skills/swarm-engineering/` | The swarm coordination skill |
| `scripts/install` | Copies config and skills into `~/.jcode` |
| `scripts/uninstall` | Reverses install |
| `scripts/common.sh` | Shared paths and helpers, sourced by both scripts |

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

Check the current state without touching anything, using
`./scripts/install --check`. It runs the same 5 checks and writes nothing at
all, not even the state file. Unlike `--dry-run`, which previews an install
and skips verification, `--check` actually verifies.

Prompt drift is reported as a warning, not a failure. `install` never writes
`prompt-overlay.md` or `swarm-prompt.md`, so drift is not something a run of
`install` can fix, and a successful install should not report failure over it.
Under `--check` the question is whether anything at all is off, so drift exits
non-zero there.

## Editing

The repo is the source of truth for `config.toml` and the skills. Change the
repo, then run `./scripts/install`.

```bash
$EDITOR config/config.toml && ./scripts/install
```

Skills in this repo are rewritten on every install, so a hand-edited copy under
`~/.jcode/skills/` cannot drift.

The two prompt files go the other way. `~/.jcode/prompt-overlay.md` and
`~/.jcode/swarm-prompt.md` are edited live; the copies in `config/` exist for
review, and `install` only checks them against live rather than overwriting
live. If they drift, copy the live file back:

```bash
cp ~/.jcode/prompt-overlay.md config/prompt-overlay.md
cp ~/.jcode/swarm-prompt.md   config/swarm-prompt.md
```

`swarm-engineering` exists only here. jcode does not ship it, so this repo
is its only source. Keep it under `config/skills/` and do not delete it, or
you lose the skill.

## Not managed here

- the jcode binary, install it separately
- MCP servers, they live in `~/.jcode/servers.json` and `~/.jcode/mcp.json`
- `~/AGENTS.md`, yours to edit
- everything else under `~/.jcode`, including runtime state and goal history

Earlier versions of this repo installed helper CLIs to `~/.local/bin` and
orchestrator prompts to `~/.local/share/jcode-orchestrate/`. This repo no
longer manages them; all of them have since been deleted from the machine, and
`uninstall` never touched them.

The `[hooks]` block that referenced two of those CLIs is gone too. Nothing now
gates a remote push or a commit on an `ambient/*` branch, and the
`~/.jcode/audit.log` trail those hooks maintained has been deleted.

## Uninstall

```bash
./scripts/uninstall --dry-run   # preview
./scripts/uninstall             # removes state.json only
./scripts/uninstall --full --yes  # also config.toml and this repo's skills
```

The jcode binary and `~/AGENTS.md` are never removed. `--full` does remove
`~/.jcode/skills/swarm-engineering/`. jcode does not ship that skill, so
this repo is its only source. To get it back, run `./scripts/install`.

## Requirements

- `jcode` on `PATH`, installed separately
- `bash`, `python3` 3.11 or newer (for `tomllib`)
