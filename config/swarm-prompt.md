<!--
The `swarm` tool description: always-on in every session, workers included.
Override at ~/.jcode/swarm-prompt.md or ./.jcode/swarm-prompt.md.
-->

Model routing. Pass `model` to choose a model for newly spawned workers,
including workers created by assignment or `launch`. It overrides
`agents.swarm_model`; omitted, workers use that default, else the
coordinator's model. Pass `model: "inherit"` to force coordinator inheritance
even with a configured default. Model selection does not change reused
workers. Run `swarm list_models` to check available models and routes. Use
`[agents] swarm_model` to set the default for future worker spawns, and
`model` for task-specific choices. Worker reasoning effort is not selectable
here: workers run at the user's `[agents] swarm_effort` (default `low`).

What to spawn workers for:

- Spawn when work parallelizes, and to implement: build features, fix bugs,
  write tests, migrate, refactor.
- Do not spawn a reviewer, auditor, critic, or verifier when the work under
  review is in your own tree: use the native `/autoreview` and `/autojudge`
  surfaces, or review the diff and run the tests yourself. Those commands are
  typed by the user, so name the review in your report. Spawn a Reviewer
  worker only when the work is not in your tree, or the review needs a lens
  you state in the brief. Each implementation worker validates its own change
  before reporting.
- Avoid a worker whose only job is gathering information: fold the
  investigation into the implementation task, or do it.

Only the root session may spawn agents, and it owns coordination until the
outcome is complete. A worker finishing its chunk is not completion of the
plan: integrate reports, assign the next actionable work, keep working. Do
not end your turn with actionable work remaining while workers wait. Stop
unused workers when done. Respect user cancellation and do not invent work.

Always pass `label` when spawning (e.g. `label: "auth"`); `spawn` rejects
missing or blank labels. Pass `phase` when the lane belongs to a phase of the
plan. Workers must complete their task directly and report back rather than
creating another generation. A missing lane is created from `prompt` or
`label`, so a spawn never silently loses its task.

Bound every lane you spawn. Requirements belong to a todo lane, not chat text:
write the todo before dispatching, put the requirement, its observable check,
and its source in the todo's `details`, and have the brief name the todo
rather than restating the requirement. The swarm plan is a server-level
object scoped to the swarm, not a file in the repo, and it is not the todo
list.

What every brief must carry. A worker sees its brief, not your context, and
may not have loaded a skill, so the brief is the contract:

- **Role and objective.** The role, and the outcome to achieve.
- **Scope and out of scope.** The files or surfaces it may touch, and those
  it must not. A worker that does not know the boundary searches the whole
  repository to be sure.
- **Context and known evidence.** The facts it may rely on, so it does not
  re-derive them.
- **Acceptance criteria.** The observable conditions that prove it is done.
  The criteria are also the lane's verification target set.
- **Validation.** The commands or checks to run.
- **Ownership.** The files it owns, so parallel lanes do not collide.
- **Dependencies.** What must land first.
- **Report contract.** What it must report back, including what failed.
- **Target list.** The finite set of candidates, files, or requirements to
  check.
- **Evidence budget.** The tool-call count that bounds the investigation; the
  default is 60 tool calls.
- **Stop condition.** What the lane does when the target list is done or the
  budget is spent: report what it has and mark the rest unverified.

If a material field is missing, say so in the brief rather than assuming it.

**The coordinator's own read phase is bounded too.** In a corpus of
334 sessions, 78% of sufficiency declarations were in root sessions rather
than delegated lanes, and one ran 774 tool calls after its last file write
without implementing the change. A sufficiency declaration binds the next
call: implementation, validation, the plan, or the report. Before its first
edit, a coordinator states the finite set of things it needs to know and
reads only those. A file already read in full is not read in full again. The
soft default is 60 tool calls before the first edit.

**The coordinator's own tail is bounded too.** After the last write, the
remaining calls check the acceptance criteria and then report. The same corpus
produced a median of 14 tool calls after the last mutation. The verification
phase has a target set: the acceptance criteria, one check each, and it ends
at the first of: the criteria are checked, a check cannot fail, the remaining
question would change what is delivered, or the budget is spent.

Enforcing the bound.

- **Watch the lane, do not just wait for it.** `swarm list` shows each
  member's status and last activity age. A member that is `running` with a
  growing activity age is working; one whose age keeps growing while its
  target list is covered is expanding scope.
- **Ask for the partial result first.** `swarm message` the lane: "report
  what you have, mark the rest unverified".
- **A DM is not a stop.** A worker that ignores a request to wrap up will not
  honour a soft instruction. Do not repeat the DM.
- **Use `swarm stop` when a lane has overrun its brief.** Stopping loses the
  unwritten remainder: it is the last step, not the first. Record in the todo
  row what was lost: the lane's completed targets, the targets it left
  unverified, and that the remainder is not covered. A stopped lane is a
  partial result, and the coordinator's own report has to say so.
- **Use `force` only for a session this coordinator did not spawn.** It
  refuses otherwise by design.
