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
| `scripts/test` | Exercises the real install and uninstall against a sandbox HOME |
| `scripts/doc-check` | Checks the claims in this README against the real scripts |
| `scripts/testlib.sh` | Shared helpers for the two test scripts |
| `scripts/common.sh` | Shared paths and helpers, sourced by both scripts |
| `.gitignore` | Keeps the live secrets out of git |

`config/mcp.json` is the real MCP server list, with the servers you actually
run. It is **not tracked**: `.gitignore` excludes it, because a live MCP
config can carry a bearer token. Nothing in this repo deploys it either. Copy
it to `~/.jcode/mcp.json` yourself if you want those servers live;
`config/mcp.example.json` is the tracked, placeholder-shaped version of the
same file.

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
Run it from this repository so the working directory matches the table:

```
jcode run --json "reply with the single word: ok"
```

| swarm prompt | overlay | input tokens per request |
| --- | --- | --- |
| old | old | 18,440 |
| new | old | 16,163 |
| new | new | 17,867 |
| old | new | 20,144 |

Each cell is the reading the provider gave most often, and each is subject to
the spread described below. In a production log, the cell's own request-size
class matched the value above 94%, 90%, 81% and 95% of the time respectively.
Read a cell as "the usual reading", not as an exact constant.

Swapping only the swarm prompt saves 2,277 input tokens per request. That is
the isolated saving for the tool description, and it is the reason the split
exists. The overlay grew to absorb the policy that used to live in the tool
description, and it costs 1,704 tokens wherever it is carried, so the net
saving of the combined change against the old baseline is smaller: the old
baseline down to 17,867, a saving of 573 tokens per request.

In bytes the move is larger than the net suggests: the tool description shrank
from 17,082 to 4,084 bytes and the overlay grew from 12,143 to 20,138. The
net gain is the small part. The rest of the value is structural: the overlay
is a system-prompt layer that can be edited on its own, and the two files
have different reload behaviour, described below.

Check those byte counts against the files themselves, `wc -c`, before trusting
them. They describe one revision of this repository and will drift.

### The provider's input count varies for the same request shape

The table above is stable, but the provider's own input count is not always
reproducible, and the cause is not in these files. On MiniMax-M3 through
`/v1/chat/completions`, requests that carried the same provider-visible
shape were sometimes reported 108 tokens apart.

`input=` in the log is the provider's own number, not a jcode estimate. On
v0.99.1 the provider's `usage.prompt_tokens` is read in
`crates/jcode-provider-openrouter/src/stream.rs:481`, carried as
`StreamEvent::TokenUsage { input_tokens }`, and written to the log unchanged at
`crates/jcode-app-core/src/agent/turn_loops.rs:845`. jcode's own tokenizer
estimate is a separate field, `Prompt prefix estimate: total=`.

What was measured, on a production log window ending 2026-11-08 23:30, with
694 request fingerprints paired to their completion by session:

- Every `request_hash` was unique, and each one mapped to exactly one
  reported input count. No request hash produced two counts. The hash is the
  first 8 bytes of a SHA-256 of the serialized request
  (`crates/jcode-provider-core/src/fingerprint.rs:43`), so it identifies a
  request but is not by itself proof that two requests had identical bytes.
- Grouping requests by provider-visible shape (`request_json_chars`,
  `item_count`, `system_hash`, `tools_hash`, `tool_count`) produced 105 groups,
  24 of which received two or more different counts. In all 24 the only
  fingerprint fields that differed were `request_hash`, `input_hash`,
  `item_hashes_hash` and `last_item_hash`.
- The common difference was 108 tokens: 16 of the 24 groups split by exactly
  108, four by 109, one by 107, and three by 1. The largest spread anywhere in
  the window was 109 tokens.

The pairing rule matters here, so it is stated rather than assumed. The log
truncates the session name to 20 characters
(`crates/jcode-logging/src/lib.rs:184`), so one log prefix can cover several
distinct sessions: 232 prefixes covered 652 real sessions in this window, and
110 of those prefixes covered more than one. A completion therefore has to be
paired against the right session, and a request that failed never logs a
completion at all. Pairing each completion with the *oldest* outstanding
fingerprint in its prefix mispairs 16 of the 694 rows and adds five spurious
split groups, with spreads up to 2,386 tokens; pairing it with the *most recent*
outstanding fingerprint leaves two fingerprints unpaired instead, which is what
a failed request looks like. Three independent pairings agree on the numbers
above: full session id from the turn-cancel records, full session id from the
session file timestamps, and most-recent-first within the truncated prefix.

Note what the prefix estimate does and does not show. `Prompt prefix estimate:
total=` is computed from the system prompt and the tool list alone
(`crates/jcode-app-core/src/agent/prompting.rs:81`), and does not count message
content. Its being constant across a split group is therefore a property of how
it is computed, not an independent finding that the two requests were the same
size. The independent evidence that the requests were the same size is
`request_json_chars`: every member of a split group has an identical request
byte count.

The strongest evidence is in the cache accounting. In the 74,177-byte class,
the provider reported `cache_read` values of 17,801 and 17,803 alongside the
higher `input=17975`, against 17,664 and 17,695 alongside `input=17867`. Pair
the two counts that share an uncached remainder and the whole difference lands
in the cached part:

| `input` | `cache_read` | uncached remainder | rows |
| --- | --- | --- | --- |
| 17,867 | 17,695 | 172 | 4 |
| 17,975 | 17,803 | 172 | 11 |

Same remainder, so the uncached tail did not move. The provider counted 108
more tokens and also served 108 more tokens from its cache. The same pattern
holds in the 74,032-byte class, where `17827`/`17695` and `17935`/`17803`
share a remainder of 132.

A replay experiment was run against this, and it does not support the claim
that was originally made for it here, so that claim has been removed rather
than softened. The capture set it read from has been deleted, and the analysis
script that quoted it now prints the figures as a literal string when the
capture directory is missing instead of recomputing them, so the figures cannot
be reproduced. They are also not consistent with the log: the 74,177-byte class
has 89 distinct `request_hash` values in total, so at most 89 distinct request
bodies can exist for it, not the 190 that were quoted, and only 17 production
calls in that class reported 17,975, not 73. The deleted directory held a
bearer credential in its recorded request headers, which is why it was removed.

What is not established: what makes the provider count the same request shape
two ways. The evidence above shows the split is not explained by the request
size, and it points at the provider's cached-prefix accounting, but it
does not identify a provider-side trigger, and it does not exclude every
possible contribution from request content: the split groups do contain
different request hashes, and the fingerprint fields that differ are exactly
the ones that track the conversation content. Treat the table as the
reproducible measurement and the spread as a known provider-side uncertainty of
the same order (108 tokens on a ~17,900-token prompt is about 0.6%). The spread
is small next to the differences the table is comparing, so it does not change
their ordering, but it does mean a single run can read up to 108 tokens above
the value shown.

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
this repo. Verify ends with 6 checks, and the dry run says so too.

Preview first with `./scripts/install --dry-run`. It writes nothing, including
on a machine where `~/.jcode` does not exist yet, and it says what it *would*
do rather than claiming it did something.

The preview also predicts the real run. Preflight checks the same things in
both modes, so a `--dry-run` that reports success is a promise the real
install keeps. It fails the same way and with the same message when a path
is not creatable: a `~/.jcode` that is a regular file, a dangling symlink, or
a home directory that cannot be written to. A path that resolves inside the
repo is refused by the dry run too, with the same message and the same exit
code, so the preview never reports success for an install that is going to
refuse.

### The repo boundary

This repo holds the source of truth. Neither script may write into it or
delete from it, because a symlink in the way would turn a normal install into
repo corruption, or a normal uninstall into data loss.

So every path the scripts touch is resolved through any symlinks first and
checked against the repo before anything happens. `~/.jcode/config.toml`,
`~/.jcode/skills/`, the state directory and the state file are all covered,
in both `install` and `uninstall`.

Each skill's own directory is covered too, not just the skills directory that
holds them. A single skill directory symlinked into the repo is the same
hazard one level down, and it is a separate check: the skills directory can
resolve inside the repo while the skill inside it resolves back out, and only
checking both ends catches that.

The uninstaller asks a slightly different question, because `rm` behaves
differently from a write. `rm -rf` does not follow a final symlink: it
removes the directory *entry*. So the uninstaller checks both where the
path points and where the entry lives, which is the resolved parent plus
the literal last component.

The two disagree in exactly the dangerous shape:

```
~/.jcode/skills              -> <repo>/config/skills
<repo>/config/skills/<skill> -> a directory outside the repo
```

The skill target resolves outside the repo, so a check that only asks
where the path points sees nothing wrong. But the entry `rm` would delete
is the repo's own `config/skills/<skill>`, because the parent
`~/.jcode/skills` *is* `<repo>/config/skills`. The uninstaller now
refuses this shape, exits non-zero, and removes nothing:

```
[uninstall] ERR: /home/you/.jcode/skills/swarm-engineering lives inside this repo
[uninstall] ERR: uninstall refuses to remove it. Fix the symlink first:
[uninstall] ERR:   rm /home/you/.jcode/skills/swarm-engineering && mkdir -p /home/you/.jcode/skills/swarm-engineering
```

The check runs before the first `mkdir`, not when the write happens. A
refusal therefore leaves the repo byte-identical and creates nothing on the
way out. `uninstall` checks every path it intends to remove up front, so a
refusal cannot leave a half-finished uninstall behind with the state file
already gone and the config still present.

If a path does resolve into the repo, the scripts say so and tell you how to
fix it:

```
[install] ERR: /home/you/.jcode/skills resolves inside this repo
[install] ERR: install refuses to touch it. Fix the symlink first:
[install] ERR:   rm /home/you/.jcode/skills && mkdir -p /home/you/.jcode/skills
```

A sibling directory whose name merely resembles the repo is not a match. The
check compares resolved paths, so `~/Project/lazible-jcode-backup` is fine.

### Running it twice

A second install with nothing changed is a no-op. The config, the skills and
the state file are all left byte-identical, and `state.json` keeps the
timestamp of the install that actually wrote it rather than the time the
script last ran.

The timestamp only moves when the config or the skill list actually changed.
So `installed_at` means "when this config was installed", which is what makes
it worth recording. Both triggers are checked: adding or removing a skill
moves the timestamp even when the config is untouched.

Check the current state without touching anything, using
`./scripts/install --check`. It runs the same 6 checks and writes nothing at
all, not even the state file. Unlike `--dry-run`, which previews an install
and skips verification, `--check` actually verifies.

Prompt drift is reported as a warning, not a failure. `install` never writes
`prompt-overlay.md` or `swarm-prompt.md`, so drift is not something a run of
`install` can fix, and a successful install should not report failure over it.
Under `--check` the question is whether anything at all is off, so drift exits
non-zero there.

The warning names the file that drifted, not just the pair, the same way the
skills check names the skill that drifted:

```
  WARN prompt-overlay.md / swarm-prompt.md vs live (differ: swarm-prompt.md)
```

A warning that only said "one of these two differs" would leave the reader
diffing both to find out which one, when the fix is a single copy per file.

## Editing

The repo is the source of truth for `config.toml` and the skills. Change the
repo, then run `./scripts/install`.

```bash
$EDITOR config/config.toml && ./scripts/install
```

Skills in this repo are rewritten on every install, so a hand-edited copy under
`~/.jcode/skills/` cannot drift. `--check` compares the installed skills
against the repo the same way it compares the config, so a skill whose content
has drifted is reported rather than passed over.

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

Every directory under `config/skills/` that holds a `SKILL.md` is a skill this
repo owns, and the installer and the uninstaller both work from that list. Add
a skill by adding the directory; nothing has to be registered anywhere else.
A directory under `config/skills/` without a `SKILL.md` is not a skill, so it
is ignored. A skill under `~/.jcode/skills/` that this repo does not own is
left alone by the uninstaller.

A repo may ship no skills at all. `config/skills/` does not have to exist, and
a repo without it installs cleanly and records an empty skill list.

## Not managed here

- the jcode binary, install it separately
- MCP servers, they live in `~/.jcode/mcp.json`
- `~/AGENTS.md`, yours to edit
- everything else under `~/.jcode`, including runtime state and goal history

Every one of those is something the scripts never write and never remove,
and `scripts/test` checks it: it plants one artifact per category, then
asserts that both the install and `uninstall --full` leave every one of
them byte-identical. The planted paths are the real ones jcode uses on
v0.99.1: `~/.jcode/sessions/`, `~/.jcode/goals/global/`,
`~/.jcode/servers.json`, `~/.jcode/mcp.json`, `~/.local/bin/jcode`,
`~/AGENTS.md`, and a skill directory this repo does not own.

`~/.jcode/servers.json` is not the MCP config, despite the file name
being adjacent to it. On v0.99.1 it is the registry of *running* jcode
servers, one entry per server with its socket path, pid and git hash
(`crates/jcode-base/src/registry.rs:5`). The MCP server list is
`~/.jcode/mcp.json`, which jcode reads as its own global MCP config
(`crates/jcode-base/src/mcp/protocol.rs:725`). Neither file is touched
here.

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

A refusal to touch the repo is checked before anything is removed, so
`uninstall` either removes the whole set or removes nothing.

## Testing

```bash
./scripts/test
./scripts/doc-check
```

`scripts/test` runs the real `scripts/install` and `scripts/uninstall`, not a
copy of their logic. Every check drives the actual script with `HOME` pointed
at a throwaway directory and asserts on the real output and the real filesystem
state. The sandbox is removed on exit, and the real `~/.jcode` is never
touched.

It covers the paths that are easy to get wrong: that `--dry-run` and
`--check` write nothing, that `--dry-run` exits 0 on a clean `HOME`, that
neither dry-run claims it installed or removed something, that a real install
writes all three of config, skills and state, that a second install changes
nothing, and that `uninstall` never reaches the jcode binary.

It also covers the files this repo does not manage. One artifact per
category is planted, and the suite asserts that the install and
`uninstall --full` both leave every one of them byte-identical: the
sessions, the goal history, `servers.json`, `mcp.json`, `~/AGENTS.md`,
the binary, and a skill this repo does not own.

And it covers the dependency check. The installer parses the config with
`tomllib`, so `python3` has to be 3.11 or newer. The suite runs the
installer against a `python3` that reports itself as 3.10 and asserts
that preflight refuses it, that the refusal names the version, and that
nothing was written when it refused.

It also checks fidelity. For each shape of home directory, the `--dry-run`
and the real install have to reach the same verdict, because a preview that
promises a success the real run cannot deliver is worse than no preview.
That includes the repo boundary: a dry run against a redirected path refuses
the same way the real run does.

It also covers the edges of the skill list. A repo with no skills at all
installs cleanly and records an empty list, and a repo with two skills
installs and removes both of them.

And it checks the repo boundary. The scripts are pointed at a throwaway copy
of this repo with `~/.jcode` symlinked into it, and the suite asserts that
the copy comes out byte-identical, that the scripts exit non-zero, and that
a refused uninstall removes nothing at all.

`scripts/doc-check` checks the other direction. It reads this README and
turns its claims into assertions: that the phase list matches the installer's
real phases, that the refusal message quoted above is the message the
installer actually prints, that the paths this section lists are the paths
that are refused, and that a refusal leaves the repo byte-identical. It fails
if this file and the scripts disagree.

That matters because a README can drift from the code while every other test
still passes. A claim in prose has no test behind it unless something checks
it, and a check that only reads this file would only prove the file is
self-consistent. So `doc-check` runs the real scripts and compares what they
do against what is written here.

A refusal has to be a refusal, not just a failure. The boundary checks ask
whether the installer refused *for the repo boundary*, not whether it exited
non-zero. An installer that failed for some unrelated reason would satisfy a
weaker check, and the boundary claim would look proven by a script that never
checked a single path. The refusal also has to name the path it is about, so
a refusal about some other path cannot satisfy a check about this one.

The fingerprint those checks rest on hashes file *content*, not file size.
A size-only fingerprint misses any change that keeps the same length, and
`state.json` is exactly that case: a different timestamp of exactly the same
length.

Every check has been shown to fail against the code it is meant to catch:
each fix was reverted in a scratch copy and the suite was confirmed to fail
against the broken code. The same is true of the claims in this README: each
one has been broken in a scratch copy and confirmed to fail the check written
for it.

Exit code 0 means every check passed.

## Requirements

- `jcode` on `PATH`, installed separately
- `bash`, `python3` 3.11 or newer (for `tomllib`)

The `python3` version is not a suggestion, and the installer checks it
before it writes anything. `tomllib` landed in Python 3.11, and the
installer parses the installed config with it. On an older `python3` the
install would copy the config, copy the skills, and only then fail its
own verification, leaving a half-finished install behind with no state
file. Instead, preflight refuses up front and the dry run predicts the
same refusal with the same message:

```
[install] ERR: python3 3.10 is too old; tomllib needs 3.11 or newer
[install] ERR: the installed config is parsed with tomllib, so an older python3 cannot install it
```
