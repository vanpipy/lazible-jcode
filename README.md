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
| `.gitignore` | Keeps the live secrets out of git |

`scripts/` holds the two installers and the helpers they share, and nothing
else. There is no test suite in this repository: the checks it used to carry
against itself are in the file history at commit `39ce723`, and the
[Verification](#verification) section says what that costs and what to read
by hand instead.

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
| `config/prompt-overlay.md` | a system-prompt layer | always-on, every session | the always-on global policy: delegation, verification, acceptance, and the worker-facing rules |
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

In bytes the move was larger than the net suggested. The tool description
shrank from 17,082 bytes before the split to 4,084 bytes at the revision this
table was measured (commit `58a2699`, 2026-11-08), and the overlay grew from
12,143 bytes before the split to 20,134 at that same revision. The net gain
is the small part. The rest of the value is structural: the overlay is a
system-prompt layer that can be edited on its own, and the two files have
different reload behaviour, described below.

Those byte counts describe one revision and will drift. The sizes in the table
below are measured again after every change to the tiers. Check them against
the files themselves, `wc -c`, before trusting any figure in this file.

The swarm prompt's size is the one that matters for cost, because it is sent on
every request in every session. It is held under a ceiling, and the ceiling is
a number to check by hand rather than a judgement to leave to review.

All three tiers are held under a ceiling now, at the size each one can carry
without losing policy:

| Tier | Ceiling | Size now | Headroom | Why its bytes cost |
| --- | --- | --- | --- | --- |
| `config/swarm-prompt.md` | 6,000 | 5,959 | 41 | sent on every request in every session |
| `config/prompt-overlay.md` | 33,500 | 33,180 | 320 | loaded once per session |
| `config/skills/swarm-engineering/SKILL.md` | 37,500 | 35,938 | 1,562 | loaded only when the Skill is activated |

The swarm prompt's ceiling is the strict one, because it is the only tier whose
bytes are paid on every request, and the two always-on tiers sit close to
theirs. `wc -c` against the files themselves is the check now. Nothing fails
when a tier grows past its number; the number is here so that the growth is
visible.

A ceiling is a measured target, not a guess. The three ceilings were
re-measured at revision `349d065`, where the files weighed 5,999, 33,490 and
37,091 bytes, and each ceiling is that size rounded up to the next 500 bytes:
6,000, 33,500 and 37,500. The ceilings do not move with the files; the sizes
in the table do. A ceiling derived from the current size would be a change
detector rather than a budget: it could tell you that a file grew, but not
that it is too large for its purpose.

The structure of the tiers was asserted the same way, by a suite that is no
longer in the tree. What it checked is worth keeping in the reader's head:
the heading hierarchy of the overlay and the Skill is well formed, every
numbered heading sits at the depth its number implies, and the section
references between the files resolve to headings that exist. A renamed
heading is now a broken reference rather than a failed check, so the
cross-references in this README and in the three prompt files are the ones to
read after a rename.

### What the compression pass cut

The three tiers were rewritten to fit their ceilings, and the rewrite was
measured rather than asserted. A rule-preservation tool compared every rule of
the revision the pass started from against the rewrite and reported none gone
on any of the three files, and a protected-content contract held 126 exact
strings and heading references across the tiers. Both are in the file history
at commit `39ce723`; neither is in the tree now, so this paragraph records
what was measured rather than what you can rerun.

What the pass removed was prose that repeated a rule stated beside it:
explanations of a threshold that the threshold already makes plain, examples
that carried no claim of their own, the reasoning behind rules the rules
already give, and the version-specific detail in the review-surface
description. The rules themselves stayed: the four thresholds that end an
investigation, the read-phase budget, the rule that the end event binds the
next action, the rule that the second read of a path needs a reason, the rule
that the verification phase ends at the first of four conditions, and the rule
that the report is the last call.

A rewrite can lose a rule without losing a word, and it was the rule check
that found it. A rule was recognised by its deontic marker, so a sentence that kept every
content word but dropped its "must" stopped being a rule and stopped being
checked. Every such sentence was restored with its marker, and the restored
wording is what the files carry now.

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

Those three bullets are reproducible from the production log alone, and the
analysis script is kept outside this repo because it reads the machine's log
directory. It is a read-only script, and the pairing rule it applies is
described below. Running it against the same log window reproduces the
figures: 694 paired rows, 105 shape groups, 24 split groups, and the delta
histogram `{1: 3, 107: 1, 108: 16, 109: 4}`. What is *not* reproducible is
anything that relied on the captured wire bodies, because that capture set was
deleted. The section below says which is which.

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

## Bounded swarm investigation

The three prompt files carry one shared safeguard: a swarm lane must be
finite, and the coordinator must enforce that.

The failure this prevents is specific. A worker given a broad brief does not
repeat the same command. It keeps *refining* and *broadening* the candidate
space, adding a target after each answer, and the lane never ends on its own.
In a corpus of 168 coordinator-spawned lanes, 27 were investigation lanes.
Their completed runs spanned 2 to 202 tool calls, with a median of 70, and
several ran far past the point where their target list was already covered.

A raw tool-call cap does not fix this, because the cap cannot distinguish a
worker that is still productively searching from one that has already
finished. The safeguard is therefore split in two.

**The worker side** decides when its own investigation is over, using four
named thresholds rather than a judgement call. The first match wins:

| Threshold | Meaning |
| --- | --- |
| Target exhausted | Every item in the target set has a verdict. An item already implemented is a completed check, not a gap. |
| Verdict established | Every acceptance criterion has a conclusion that names its source: a file and a line, or a command and its output. |
| Budget reached | The tool-call budget is spent. Report what is done, mark the rest unverified, stop. |
| Blocked | The next question needs access the worker does not have. Report the blocker, do not widen the search. |

**A lane that is blocked at the budget ends on "blocked", not "budget reached".**

A new question reopens a closed investigation only when it could change a
verdict already reported, contradicts evidence already collected, or covers
an acceptance criterion never checked. "It would be nice to confirm" is not
one of them.

The default budget is 20 tool calls, which fits a focused single-target lane.
It bounds the *investigation* phase only. A lane that implements code and
runs tests is not an investigation lane, and capping it would truncate real
work. The coordinator sets a larger number before dispatch when it expects a
wide lane.

**The coordinator side** enforces the bound, because a brief is a request and
a worker that has already met its criteria will not stop on request alone.
The escalation order is fixed:

1. Check the lane with `swarm list`, which shows status, last activity age,
   and stall state.
2. Message the lane, asking for what it has with the rest marked unverified.
   Name the requirement it still owes, and say it must not open new targets.
3. Do not repeat the message. A worker that ignored one request to wrap up
   has shown it will not honour a soft instruction.
4. `swarm stop` the lane. The coordinator owns its own spawned workers, so
   this works without `force`. `force` is for sessions this coordinator did
   not spawn, and it refuses otherwise by design.
5. Record the loss in the todo row: which targets were completed, which were
   left unverified, and that the remainder is not covered.

`swarm stop` persists the session as closed, and the transcript on disk keeps
what the worker had already written, so a stopped lane is a partial result
rather than a total loss. The unwritten remainder is still lost, which is why
stopping is the last step and not the first.

The three files that carry this:

| File | What it holds |
| --- | --- |
| `config/prompt-overlay.md` | Section 2.2.1 and 2.2.2 hold the thresholds and the budget. Section 12.8 holds the escalation order. |
| `config/swarm-prompt.md` | The brief fields that keep a lane finite, and the same escalation order. |
| `config/skills/swarm-engineering/SKILL.md` | Section 2.3.1 and 2.3.2 hold the thresholds and the budget. Section 11.1 holds the escalation order. |

The overlay and the swarm prompt are always-on in every session, including
spawned workers, so the worker side reaches a worker that never loads the
Skill. The Skill carries the same rules in more detail for a worker that does
load it.

## Bounding the read phase of a direct task

The safeguard above bounds a *delegated* lane, because a brief carries the
bound. A direct task has no brief, so nothing bounded its read phase. That is
where the same failure appeared, and it was the larger half of it.

The evidence, from a corpus of 334 sessions with at least 20 messages, 191 of
them root sessions and 143 swarm workers. Every figure in the table below is a
measurement of this repository's own corpus of sessions, not a budget:

| Measurement | Value |
| --- | --- |
| Sufficiency declarations ("I have the design. Let me ...") followed by a tool call | 1,953 |
| Of those, in root, primary sessions rather than delegated lanes | 78% |
| Of those, followed by another read, search, or browse | 77% |
| Read-tool calls that repeated a path already read in full earlier in the same session | 43% of 7,269 |
| Sessions containing at least one repeated read | 44% |
| Tool calls before the first mutation, median | 39 |
| Sessions whose first mutation came after more than 60 calls, measured in that corpus | 31% |
| Tool calls *after* the last mutation, median | 14 |
| Worst observed tail after the last mutation | 774 calls, with the target change unimplemented |

That last row is the clearest signal. A session that reads for 774 calls after
its last file write is not verifying anything. Its read phase never ended. The
session in question did make a handful of file writes, but none of them were
the change it was asked for, so the tail was not verification of anything.

The three prompt files now close this in two parts.

**The end event binds the next action.** The end of an investigation is a
state, not a sentence the agent writes. A threshold is met, the phase is over,
and the next call is bound whether or not the agent says so. The next call is
one of four: the implementation action the end event was about, a validation
or test action, a plan or todo write when the task asked for one, or the
report. It must not be another read, search, or browse of the same subject.
One exception per phase, and only before the budget is spent: when a named
acceptance criterion is still unanswered, one targeted read that answers it is
allowed, and that read is the last of the phase. The same rule governs a
declaration of incompleteness ("I have the implementation shape, but I need to
check the migration"): it licenses exactly one read with a named target, and a
second read is not licensed. A second request for another look is an
escalation, not a read.

**A direct task has a frozen target set and a budget.**
The target set is frozen when it is written, and it is written before the
first read. Each item is a path and the question that path answers: the
acceptance criteria and their source, the files the change touches, the
conventions to follow, and the risk that could change the approach. When every
item has a verdict, the read phase is over. A question that appears later is an
uncovered item, or one logged target-set change, which counts against the
budget. Broadening the target set after the verdict is established, beyond that
one logged change, is a reportable failure, not diligence.

The end criterion is countable in both phases. Every target item and every
acceptance criterion ends with a conclusion that names its source: a file and
a line, or a command and its output. A phase ends on its deliverable, not on a
write. A todo, a plan, or a scratch file is not a deliverable and does not end a
phase.

Three limits follow from the target set:

- A named section, category, or file is the scope. Reading the whole
  specification because a section of it was named is scope expansion.
- The second read of a path needs a reason and the third stops it. The count
  is by path, not by call, so a slice, a grep, or a search over a path already
  read in full counts as a read of that path.
- The soft default is 45 tool calls before the first edit, scaled at 5 tool
  calls per target item, with a floor of 20 and a cap of 45. The budget is set
  before the work starts and does not change while it runs. A lane does not
  raise its own budget: only a coordinator raises one, and only before it
  dispatches the work. A root with no assignment sets its own before its
  first read, from its own target set. At the budget the report is the only
  remaining action. The corpus median before the first mutation was 39 calls,
  and the default sits above it.

The tail after the last mutation is named as well. It is a verification phase,
not a research phase.

| File | What it holds |
| --- | --- |
| `config/prompt-overlay.md` | Section 2.2.3 states the end event and the calls it allows. Section 2.2.4 bounds the read phase of a direct task. |
| `config/swarm-prompt.md` | The coordinator's own read phase, and the target list, the evidence budget and the stop condition in the brief contract. |
| `config/skills/swarm-engineering/SKILL.md` | Section 2.3.3 carries the end event for a worker, section 2.3.4 the re-read rule, and section 11 the coordinator's own read phase. |

These are model-guidance rules, not runtime safeguards. Jcode's tool schemas
cannot tell an agent it read a file it already read, and the prompts cannot
hard-stop a read. What they do is make the intended transition explicit and
give the agent a number to check itself against. A tool-call cap in the
runtime would be a different mechanism and is not claimed here.

## Bounding the verification phase

The read phase got a target set, a budget, and an end event that binds the
next call. The tail after the last write got a name and nothing else, and the
tail is where the worst row of the corpus sits: 774 calls after the last file
write, with the target change unimplemented. A name is not a stopping
condition, so the defect was still reachable after the fix.

The verification phase ends at the first of four conditions.

| Condition | What it means |
| --- | --- |
| Criteria checked | Every acceptance criterion has been checked, and the evidence recorded. |
| A check that cannot fail | A check that passes whatever happens is not evidence. Repair it, run it once, move on. |
| A question that could change the result | The remaining question is worth a call only if its answer would change what is delivered. That is implementation work, not verification: make the change, then verify the criterion it affects. If it cannot, it is not a reason to keep verifying. |
| The budget reached | The budget is spent. Report what was verified, and mark the rest unverified. |

The verification phase has a target set too, and it is the acceptance criteria:
one check per criterion, the same list the read phase was bounded by, read as
checks. Re-reading the file you just wrote is not verification, because a
check that verifies a change is the check that exercises it. And the report is
the last call, not the next one.

The verification phase runs the project's own checks. A criterion those
checks cannot falsify is reported as unverifiable, not replaced by a new
oracle, a mutation test, or a side experiment. Files under scratch/ are neither
a deliverable nor evidence.

The verification phase has its own budget: 2 tool calls per acceptance
criterion, capped at 20, set before the phase starts. A criterion the phase
did not check is named in the report.

In the same corpus, the median session made 14 tool calls after its last
mutation. A report that names the criterion it did not check is more useful
than one that claims everything was checked.

| File | What it holds |
| --- | --- |
| `config/prompt-overlay.md` | Section 2.2.5 bounds the verification phase. |
| `config/swarm-prompt.md` | The coordinator's own tail, and the lane's acceptance criteria as its verification target set. |
| `config/skills/swarm-engineering/SKILL.md` | Section 2.3.5 carries the same rule for a worker, with the developer and tester exit criteria and a coordinator bullet in section 11 pointing at it. |

The same limit applies as before: these are model-guidance rules, not runtime
safeguards, and the prompts cannot hard-stop a read.

## The rules as cards

Each card names the audience it binds, what fires it, what ends it, its
exception, its enforcer, and the file and section that state it. The ten
rules, in order: threshold, budget, end event, closed set, one exception,
frozen target set, re-read rule, verification phase, lane conclusion, brief
completeness.

| Rule | Audience | Trigger | End | Exception | Enforcer | Where it is stated |
| --- | --- | --- | --- | --- | --- | --- |
| Threshold | both | One of four thresholds is met: target exhausted, verdict established, budget reached, or blocked. | The investigation ends; the next call is bound by the closed set. | none | The report names the threshold; the coordinator checks it against the target list and budget. | `config/prompt-overlay.md` section 2.2.1 and `config/skills/swarm-engineering/SKILL.md` section 2.3.1, both titled "Evidence Thresholds" |
| Budget | both | Each budget is written down when its phase starts: the direct task's read budget, 45 tool calls scaled at 5 tool calls per target item with a floor of 20 and a cap of 45, set before the first read; an investigation lane's 20 tool calls, set before the work starts; the verification budget, 2 tool calls per acceptance criterion capped at 20, set before the verification phase starts. | The budget is spent; the report is the only action left. | The one exception is licensed before the budget is spent. | The brief carries the number; only a coordinator raises one, before dispatch. The coordinator's own read phase follows the same rules. | `config/prompt-overlay.md` section 2.2.2 and `config/skills/swarm-engineering/SKILL.md` section 2.3.2, both titled "Tool-Call Budgets"; the skill's read budget is in section 11 and its verification budget in section 2.3.5; `config/swarm-prompt.md`, brief contract, evidence budget, and the coordinator's own read phase for its 45-call read budget |
| End event | both | A threshold is met. The end event does not wait for an announcement: an agent that met a threshold is bound whether or not it says so. | The phase ends; the next call is bound. | none | The report records the end event; the coordinator checks the next call. | `config/prompt-overlay.md` section 2.2.3 and `config/skills/swarm-engineering/SKILL.md` section 2.3.3, both titled "The End Event Binds the Next Action"; `config/swarm-prompt.md`, the coordinator's own read phase |
| Closed set | both | The end event has happened. | The next call is one of four: the implementation action the end event was about, a validation or test action, a plan or todo write when the task asked for one, or the report. | one targeted read that answers a named acceptance criterion | The report shows the next call; the coordinator stops a lane that reads. | `config/prompt-overlay.md` section 2.2.3 and `config/skills/swarm-engineering/SKILL.md` section 2.3.3, both titled "The End Event Binds the Next Action" |
| One exception | both | A named acceptance criterion is still unanswered when the end event happens. The same rule governs a declaration of incompleteness. | One more targeted read answers it, and that read is the last of the phase. A second request for another look is an escalation, not a read. | none | The report names the criterion and the read; the coordinator takes the escalation. | `config/prompt-overlay.md` section 2.2.3 and `config/skills/swarm-engineering/SKILL.md` section 2.3.3, both titled "The End Event Binds the Next Action"; the precondition that the budget is not yet spent is stated in section 2.2.2 and section 2.3.2, where the budget lives |
| Frozen target set | both | Before the first read the target set is written. Each item is a path and the question it answers: the acceptance criteria and their source, the files the change touches. | Every item has a verdict, or the item is listed as uncovered in the report. | one logged target-set change, which counts against the budget; broadening the target set after the verdict is established, beyond that one logged change, is a reportable failure, not diligence | The brief carries the target list; the report lists the items not covered; the coordinator stops a widened set. | `config/prompt-overlay.md` section 2.2.4 Bounding the Read Phase of a Direct Task; `config/swarm-prompt.md`, brief contract, target list; `config/skills/swarm-engineering/SKILL.md` section 2.3.1 Evidence Thresholds |
| Re-read rule | both | A path is read again. The count is by path, not by call, so a slice, a grep, or a search over a path already read in full counts as a read of that path. | The third read of the same path stops it; the second read needs a stated reason. | one second read of the same path, with a stated reason | The report records the reads; the coordinator stops the third. | `config/prompt-overlay.md` section 2.2.4 Bounding the Read Phase of a Direct Task; `config/skills/swarm-engineering/SKILL.md` section 2.3.4 No Third Read of the Same Path; `config/swarm-prompt.md`, the coordinator's own read phase |
| Verification phase | both | The deliverable is written. The target set is the acceptance criteria, one check each, run as the project's own checks. | The first of four conditions: criteria checked, a check that cannot fail, a question that could change the result, or the budget of 2 tool calls per acceptance criterion reached. | none | The report names each criterion checked and each left unverified. | `config/prompt-overlay.md` section 2.2.5 and `config/skills/swarm-engineering/SKILL.md` section 2.3.5, both titled "Bounding the Verification Phase"; `config/swarm-prompt.md`, the coordinator's own tail |
| Lane conclusion | lane | The lane ends on one of the four thresholds: target exhausted, verdict established, budget reached, or blocked, and the worker names the one that ended it. An open question becomes a coordinator task only when it affects a declared acceptance criterion. | The lane ends with a conclusion and the items it did not cover. | none | The coordinator closes the lane and records the uncovered items in the todo row. A lane ending on "budget reached" or "target exhausted" is a completed lane with a reported gap; one ending on "verdict established" is a completed lane; one ending on "blocked" is a completed lane with a reported blocker. | `config/prompt-overlay.md` section 12.6 Investigation Management and section 12.8 Enforcing a Lane's Bound; `config/swarm-prompt.md`, brief contract, stop condition; `config/skills/swarm-engineering/SKILL.md` section 11.1 Stopping a Lane That Overran Its Brief, for a lane stopped at its bound |
| Brief completeness | root | A brief is written for a lane. | The brief carries the role and objective, the scope, the evidence, the acceptance criteria, the validation, the ownership, the dependencies, the report contract, the target list, the evidence budget and the stop condition. A brief without a target list, an evidence budget, or a stop condition is not ready to dispatch. | none | The coordinator names the missing field instead of assuming it. | `config/prompt-overlay.md` section 12.5 Assignment Brief; `config/swarm-prompt.md`, brief contract |

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

This is why the overlay, the skill and `swarm-prompt.md` all tell the agent not
to assume the flag produced a review. The skill asks for the review with
`/autoreview now` or `/review`; the overlay says in its report that
independent verification is required and lets the user run `/autoreview now`;
`swarm-prompt.md` says the commands are typed by the user and names the review
in the report.

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

Every one of those is something the scripts never write and never remove.
The paths are the real ones jcode uses on v0.99.1: `~/.jcode/sessions/`,
`~/.jcode/goals/global/`, `~/.jcode/servers.json`, `~/.jcode/mcp.json`,
`~/.local/bin/jcode`, `~/AGENTS.md`, and a skill directory this repo does not
own. A suite that used to plant one artifact per category and assert that both
the install and `uninstall --full` left every one of them byte-identical is in
the file history at commit `39ce723`.

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

The repo side of that is checkable: those paths are gone from the repo, and
the git history shows the commit that removed them (`c330070`, "chore: clean
legacy docs and tools"). The machine side is historical: it describes what
happened on the machine this repo was developed on, and nothing in this repo
can verify another machine's `~/.local/bin`.

The `[hooks]` block that referenced two of those CLIs is gone too. Nothing now
gates a remote push or a commit on an `ambient/*` branch, and the
`~/.jcode/audit.log` trail those hooks maintained has been deleted. The
config still records the removal in a comment rather than dropping it
silently; in `config/config.toml` it is a comment, not a live setting.

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

## Verification

There is no automated verification in this repository. What there is:

```bash
./scripts/install --dry-run   # writes nothing, and predicts the real run
./scripts/install --check     # 6 checks against the live install, writes nothing
./scripts/install             # the real install
./scripts/uninstall --dry-run
```

The two read-only modes disagree on purpose. The dry run previews an install
and skips verification; the check runs the verification and installs nothing.
The six checks are that the installed config parses, that it is a regular file
rather than a symlink, that it matches `config/config.toml`, that every repo
skill is installed, that the installed skills match the repo, and that the two
prompt files have not drifted from live. Drift is a warning on a normal run
and a failure under `--check`, because `install` never writes the prompt
files.

A dry run that reports success is a promise the real install keeps. Preflight
checks the same things in both modes, and a refusal carries the same message
and the same exit code in both, so the preview never reports a success that
the real run is going to refuse.

### What this repository used to check

The gates are in the file history at commit `39ce723`, not in the tree:

| What it did | What it caught |
| --- | --- |
| `scripts/test`, 356 checks | the install and uninstall behaviour, the paths the scripts must not touch, the prompt content, the three size ceilings, the heading structure |
| `scripts/doc-check`, 193 checks | every claim this README makes about this repository's own behaviour |
| `scripts/prompt-contract` and `scripts/prompt-contract.json` | 126 protected strings and heading references across the three tiers: 64 in the overlay, 42 in the Skill, 20 in the swarm prompt |
| `scripts/prompt-verify` | the gate for a prompt compression: the contract, the ceilings, the headings, the rule check, and both suites |
| `scripts/inject-defect` | proof that the gates fail when they should: 7 of 7 injected defects caught, re-run at `39ce723` |
| `scripts/rule-drop`, `rule-inventory`, `rule-repair`, `measure-rule-tools` | a rule lost by a rewrite, and the measurement of how well those tools detect one |

The practical consequence is specific: **nothing in this repository can now
fail because a prompt tier lost a rule.** The rules that survived the
compression pass are held by the words on this page and by the files
themselves. When a tier is edited, these are the parts to read first:

- the four thresholds, the read budget and the verification budget, in
  `config/prompt-overlay.md` sections 2.2.1, 2.2.2 and 2.2.5, and in
  `config/skills/swarm-engineering/SKILL.md` sections 2.3.1, 2.3.2 and 2.3.5;
- the end event and the closed set of calls it allows, in overlay section 2.2.3
  and skill section 2.3.3;
- the frozen target set, in overlay section 2.2.4 and skill section 2.3.1, and
  the re-read rule, in overlay section 2.2.4 and skill section 2.3.4;
- the brief contract in `config/swarm-prompt.md`, and the heading numbers and
  titles that this README and the three prompt files point at.

`git show 39ce723:scripts/prompt-contract.json` returns the contract, and
`git show 39ce723:scripts/test` returns the suite, if either is wanted back.

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
