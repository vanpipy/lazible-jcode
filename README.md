# lazible-jcode

My [jcode](https://github.com/1jehuang/jcode) configuration.

This repository is **configuration only**. It holds the values that make jcode
run the way I want it to, plus the skills, hooks and helper CLIs that turn
ambient scheduling into goal-driven work.

It does **not** build, patch or distribute the jcode binary.

```text
config/config.toml   →  ~/.jcode/config.toml          verbatim copy
config/skills/*/     →  ~/.jcode/skills/*/            authoritative
config/bin/*         →  ~/.local/bin/*                authoritative
config/policies/     →  (documentation, not loaded at runtime)
config/templates/    →  ~/AGENTS.md on first install only
scripts/install      →  wires all of the above
```

There is no overlay layer. `config/config.toml` is a snapshot of the live
config, and `./scripts/install` copies it into place. To adopt a change you
made in jcode itself, run `./scripts/snapshot-config --apply`.

## Requirements

- `jcode` on `PATH` (installed separately, this repo does not manage it)
- `bash`, `python3` (3.11+), `git`

## Install

```bash
git clone <this-repo> ~/Project/lazible-jcode
cd ~/Project/lazible-jcode
./scripts/install
```

`install` runs 10 phases (preflight, config, skills, shell env, audit hook,
CLIs, prompts, `~/AGENTS.md`, verify, state) and ends with 12 checks. Preview
it first with `./scripts/install --dry-run`.

The repo is the source of truth for everything it owns. Skills, prompts and
CLIs are rewritten on every install, so a stale or missing copy under
`~/.jcode/` cannot drift. `~/AGENTS.md` is the exception: it is only written
when absent, so personal instructions survive.

## Everyday use

```bash
jcode-l2-check                 # is the setup ready?
jcode-goal list                # goals for this project
jcode-goal add "<title>" --priority high
cd <project> && /orchestrate loop 10    # advance 10 control-loop cycles
```

`pre_tool` runs `jcode-tool-policy` on every shell call. It blocks `git push`
and blocks commits on `ambient/*` branches that have no active goal. See
[`config/policies/git.md`](config/policies/git.md).

## Layout

| Path | What it is |
| --- | --- |
| `config/config.toml` | The live config, verbatim. Edit this. |
| `config/bin/` | `jcode-goal`, `jcode-l2-check`, `jcode-tool-policy`, `jcode-orchestrate`, plus their tests |
| `config/skills/` | `/goal`, `/orchestrate`, goal discipline, optimization notes |
| `config/policies/` | Why each setting has the value it has |
| `config/templates/` | Artifact templates (`task.md`, `handoff.md`, `report.md`) |
| `config/share/` | Orchestrator worker prompts (`coder.md`, `reviewer.md`) |
| `scripts/` | install, uninstall, and maintenance helpers |
| `design.md` | What jcode actually implements, and where this repo stops |
| `new.md` | The original vision. Kept as history. |

## Maintenance

```bash
./scripts/snapshot-config --diff     # live vs repo drift
./scripts/snapshot-config --apply    # pull live into the repo
./scripts/sync-skills --from-home --apply   # pull skill edits back into the repo
./scripts/verify-sanitized           # pre-commit leak check
./scripts/uninstall --dry-run        # what would be removed
```

## Docs

- [`config/policies/`](config/policies/) — autonomy levels, git policy, repair loop, audit
- [`scripts/README.md`](scripts/README.md) — every script, what it does, exit codes
- [`design.md`](design.md) — source alignment and known gaps
- [`docs/mermaid-style.md`](docs/mermaid-style.md) — diagram conventions