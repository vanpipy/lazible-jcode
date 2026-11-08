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

## The three prompt tiers

The swarm guidance is split across three files because jcode loads them at
different costs, in different places.

| File | Loaded as | Cost | Holds |
| --- | --- | --- | --- |
| `config/swarm-prompt.md` | the `swarm` tool description | always-on, every session | model routing, when to spawn, what a brief must carry |
| `config/prompt-overlay.md` | a system-prompt layer | always-on, every session | coordinator policy: delegation, verification, acceptance |
| `config/skills/swarm-engineering/SKILL.md` | a Skill, on demand | only when loaded | the Developer / Tester / Reviewer methods |

`swarm-prompt.md` is the expensive one. It becomes a tool description, so it
is sent on every request in every session, including spawned workers. Keep it
to routing and brief requirements, and put policy in the overlay instead.

Measured on v0.99.1 with `jcode run --json`, using input tokens per request.
Run it from this repository so the working directory matches the table, and
disable the memory sidecar, which injects a variable recall block and adds an
unrelated jitter of about 108 tokens to every sample:

```
JCODE_MEMORY_SIDECAR_ENABLED=false jcode run --json "reply with the single word: ok"
```

With the sidecar off, every cell below is exactly reproducible across repeated
runs. With the sidecar on, each cell splits into two clusters roughly 108
tokens apart, which is a property of the memory injection and not of these
files.

| swarm prompt | overlay | input tokens per request |
| --- | --- | --- |
| old | old | 18,440 |
| new | old | 16,163 |
| new | new | 17,867 |
| old | new | 20,144 |

Swapping only the swarm prompt saves 2,277 input tokens per request. That is
the isolated saving for the tool description, and it is the reason the split
exists. The overlay grew to absorb the policy that used to live in the tool
description, and it costs 1,704 tokens wherever it is carried, so the net
saving of the combined change against the old baseline is smaller: the old
baseline down to 17,867, a saving of 573 tokens per request.

In bytes the move is larger than the net suggests: the tool description shrank
from 17,082 to 4,084 bytes and the overlay grew from 12,143 to 20,130. The
net gain is the small part. The rest of the value is structural: the overlay
is a system-prompt layer that can be edited on its own, and the two files
have different reload behaviour, described below.

Check those byte counts against the files themselves, `wc -c`, before trusting
them. They describe one revision of this repository and will drift.

The overlay is a separate file because jcode reloads it. Editing it mid-session
picks the change up on the next turn. The swarm prompt is read when a session
starts, so changing it affects the next session, not the current one.

That difference is real, not documentation drift. On v0.99.1 the overlay is
re-read from disk on every turn. The swarm prompt is baked into the `swarm`
tool description when the tool registry is built, so within one session the
description stays fixed: editing the file mid-session does not change the
description that session already has.

A worker spawned later does not inherit that. A worker builds its own tool
registry when it starts, so it reads the swarm prompt from disk at that
moment. Editing the file therefore changes the description a *future* worker
gets, while the coordinator that spawned it keeps the description it started
with. Verified on v0.99.1: stamping a marker into the live file left the
running session's tool payload byte-identical, while a worker spawned
immediately afterwards reported the marker in its own swarm tool
description.

The Skill is loaded only when an agent asks for it, which is why it can be
long. It is also the file most likely to be read by a worker that was handed a
brief, so a brief should say which section of it governs the task.

## Native review surfaces

`[autoreview]` and `[autojudge]` are set to `enabled = true` in
`config/config.toml`. What that buys you on v0.99.1 is narrower than it
looks, so the repo documents it precisely rather than promising an automatic
review that does not arrive.

`enabled` seeds the session flag and nothing else. The automatic end-of-turn
hook is at the end of the TUI's local turn path, and it returns early when the
app is in remote mode. The product TUI is built with `new_for_remote`, so it
runs in remote mode, and the hook never fires in the product TUI. The result:

| Surface | What actually happens on v0.99.1 |
| --- | --- |
| `/autoreview status` | Reports the flag, which reads `enabled` from the config |
| `/autoreview now`, `/autojudge now` | Launch a reviewer or judge on demand, in the TUI |
| `/review`, `/judge` | Launch a one-shot review or judge session, in the TUI |
| Automatic end-of-turn trigger | Does not fire in the product TUI |

On demand means the command does not wait for the end-of-turn trigger. In the
product TUI the launch happens straight away when no turn is running, and is
queued until the current turn finishes when one is.

Verified two ways. Observed: a headless `jcode run` in a fresh repository
produced only the requested root session, and the session flags stayed unset;
in the TUI, `/autoreview status` reported enabled while normal turns, turns
after tracked-file changes, and a turn after an explicit `/autoreview on` all
produced no review or judge child session. Confirmed in the v0.99.1 source,
where the trigger checks `app.is_remote` and returns before launching.

The local turn path is not dead code. `jcode ambient run-visible` builds a
local, non-remote app, so the end-of-turn trigger does fire there. The ambient
runner spawns that command when `[ambient] visible = true`. This repo sets
`visible = false`, so ambient cycles run headless and stay outside it.

Headless runs are a separate case: `jcode run`, swarm workers, and headless
ambient cycles have no TUI turn path at all, so the trigger cannot fire there
either.

All of these are client-side TUI commands. A worker or a headless agent cannot
type them into your composer, and no tool exposes them to the model. When an
agent needs independent verification it asks for it in its report, and you run
the command.

The one-shot children are created with `autoreview_enabled` and
`autojudge_enabled` set to false, so a review does not spawn a review of
itself.

This is why the overlay, the skill, and `swarm-prompt.md` tell the agent to
request a review with `now` instead of assuming the flag produced one.

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
