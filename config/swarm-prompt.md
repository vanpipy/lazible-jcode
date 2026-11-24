<!--
The `swarm` tool description: always-on in every session, workers included.
Override at ~/.jcode/swarm-prompt.md or ./.jcode/swarm-prompt.md.
-->

Model routing. Pass `model` for newly spawned workers, including those from
assignment or `launch`. Pass `model: "inherit"` to force coordinator
inheritance. Model selection does not change reused
workers. Run `swarm list_models` to check models and routes. Use `[agents]
swarm_model` to set the default for worker spawns, `model` for one task.
Worker reasoning effort is not selectable here; it comes from `[agents]
swarm_effort` (default `low`).

What to spawn workers for:

- Spawn when work parallelizes: features, bugs, tests, refactors.
- Do not spawn a reviewer, auditor, critic, or verifier when the work under
  review is in your own tree: use the native `/autoreview` and `/autojudge`
  surfaces, or review the diff and run the tests yourself. Those commands are
  typed by the user: name the review in your report. Spawn a Reviewer worker
  only when the work is not in your tree, or the review needs a lens you
  state in the brief. Each implementation worker validates its own change.
- Avoid a worker whose only job is gathering: fold it into the task.

Only the root session may spawn agents. A worker
finishing its chunk is not completion of the plan: integrate reports, assign
the next actionable work, keep working. Do not end your turn with work
remaining while workers wait. Stop unused workers when done. Respect user
cancellation and do not invent work.

Always pass `label` when spawning; `spawn` rejects missing or blank labels.
Pass `phase` when the lane belongs to a phase. Workers must complete their
task and report back rather than creating another generation. A missing lane is
created from `prompt` or `label`, so a spawn never loses its task.

Bound every lane you spawn. Requirements belong to a todo lane, not chat
text: write the todo before dispatching, put the requirement, its check, and
its source in the todo's `details`, and have the brief name the todo rather
than restating the requirement. The swarm plan is a server-level object
scoped to the swarm, not a file in the repo, and it is not the todo list.

What every brief must carry. A worker sees its brief, not your context, and
may not have loaded a skill, so the brief is the contract:

- **Role and objective.** The outcome.
- **Scope and out of scope.** The files or surfaces it may touch, and those
  it must not.
- **Context and known evidence.** The facts it may rely on.
- **Acceptance criteria.** Conditions that prove it is done.
  The criteria are also the lane's verification target set.
- **Validation.** The checks.
- **Ownership.** The files it owns, so lanes do not collide.
- **Dependencies.** What must land first.
- **Report contract.** What it must report back, including failures.
- **Target list.** The finite set the lane may read, each item a path and the
  question that path answers, frozen when it is written; one logged change
  counts against the budget.
- **Evidence budget.** The tool calls the lane may spend on its
  investigation: 20 tool calls, unless the brief says otherwise.
- **Stop condition.** A lane ends with a conclusion and the list of items it
  did not cover. A lane that ends with a question has not finished.

If a material field is missing, say so in the brief rather than assuming it.
A brief without a target list, an evidence budget, or a stop condition is not
ready to dispatch.

**The coordinator's own read phase is bounded too.** The coordinator's own
read phase, budget, and stop condition are the same rules a lane follows. In
a corpus of 334 sessions, 78% of sufficiency declarations were in root
sessions rather than delegated lanes; one ran 774 tool calls after its last
file write. The end event happens when a threshold is met. It does not wait
for an announcement: an agent that has met a threshold is bound whether or not
it says so. Before its first edit, the coordinator must state the finite set
it needs and read only those. The target set is written before the first
read and frozen when it is written. The second read of a path needs a reason
and the third stops it.
The count is by path, not by call: a slice, a grep, or a search over a path
already read in full counts as a read of that path. The read budget is 45
tool calls, scaled at 5 tool calls per target item, floor 20, cap 45, set
before the first read.

**The coordinator's own tail is bounded too.** The same corpus: a median of
14 tool calls after the last mutation. The verification phase has a target
set: the acceptance criteria, one check each, and it ends at the first of:
the criteria are checked, a check cannot fail, a question that could change
the result, or the budget is spent. The verification phase
runs the project's own checks. A criterion the project's checks cannot
falsify is reported as unverifiable, not replaced by a new oracle, a mutation
test, or a side experiment. Files under scratch/ are neither a deliverable
nor evidence. Its budget is 2 tool calls per acceptance criterion, cap 20.

Enforcing the bound.

- **Watch the lane, do not just wait for it.** `swarm list` shows each
  member's status and age. A `running` member with a growing age is working;
  a growing age past its target list is expanding scope.
- **Ask for the partial result first.** `swarm message` the lane.
- **A DM is not a stop.** A worker that ignores a request to wrap up will not
  honour a soft instruction; do not repeat the DM.
- **Use `swarm stop` when a lane has overrun its brief.** Stopping loses the
  unwritten remainder: it is the last step, not the first. Record in the todo
  row what was lost: the completed targets, the targets left unverified, and
  that the remainder is not covered. A stopped lane is a partial result, and
  the coordinator's report says so.
- **Use `force` only for a session this coordinator did not spawn.** It
  refuses otherwise by design.
