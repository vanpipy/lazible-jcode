<!--
This file IS the swarm config. It becomes the `swarm` tool description, so it
is always-on in every session, workers included. Override at
~/.jcode/swarm-prompt.md or ./.jcode/swarm-prompt.md.
-->

Model routing. Pass `model` to choose a model for newly spawned workers,
including workers created by assignment or `launch`. An explicit model
overrides `agents.swarm_model`; omitted, workers use that configured default,
else inherit the coordinator's model and route. Pass `model: "inherit"` to
force coordinator inheritance even with a configured default. Model selection
does not change reused workers. Run `swarm list_models` to check available
models and routes. Route-prefixed values like `openai-api:gpt-6-astra` pin
the authentication route as well. Use `[agents] swarm_model` to set the
default for future worker spawns, and the `model` parameter for task-specific
choices. Worker reasoning effort is not selectable from this tool: workers
run at the user's `[agents] swarm_effort` (default `low`).

What to spawn workers for:

- Spawn when work can be parallelized, and to implement: build features, fix
  bugs, write tests, migrate, refactor. Give each a concrete, scoped change
  with clear file ownership and an acceptance check it runs itself.
- Do not spawn a reviewer, auditor, critic, or verifier when the work under
  review is in your own tree. Use the native `/autoreview` and `/autojudge`
  surfaces, or review the diff and run the tests yourself. The native
  end-of-turn trigger does not fire in every mode, and those commands are
  typed by the user, not called by an agent, so name the review you want in
  your report and let the user run `/autoreview now`. Spawn a Reviewer worker
  only when what it must review is not in your tree, or when the review needs
  a lens you state in the brief. Each implementation worker validates its own
  change before reporting.
- Avoid a worker whose only job is gathering information with nothing to
  build on. Fold the investigation into the implementation task, or do it
  yourself first. A delegated investigation is worth a lane when it answers a
  bounded question that unblocks a decision, and the brief says which
  question that is.

The root owns coordination until the outcome is complete or genuinely blocked.
A worker finishing its chunk is not completion of the plan. Integrate reports,
assign workers the next actionable work, keep working yourself. If workers are
still running, use `await_members` with wake delivery before yielding. Do not
end your turn with actionable work remaining while workers wait. Stop unused
workers when done. Respect user cancellation and do not invent work.

Always pass `label` when spawning (e.g. `label: "auth refactor"`) so the swarm
UI shows what each agent is for; `spawn` rejects missing or blank labels. Pass
`phase` when the lane belongs to a specific phase of the plan. Only the root
session may spawn agents. Workers must complete their assigned task directly
and report back rather than creating another generation. The todo lane is the
source of truth: the spawned worker owns it, its tasks are prepopulated into
the worker, and updates sync only to that lane. `prompt` adds context, not
duplicate tasks. A missing lane is created from `prompt` or `label`, so a
spawn never silently loses its task.

Bound every lane you spawn. An unbounded brief produces an unbounded lane.
Requirements belong to a todo lane, not chat text: write the todo before
dispatching, put the requirement, its observable check, and its source in the
todo's `details`, and have the brief name the todo rather than restating the
requirement. A requirement copied into a chat message drifts; a requirement in
a todo has a stable id to cite. The swarm plan itself is a server-level
object scoped to the swarm, not a file in the repo, and it is not the todo
list.

What every brief must carry. A worker sees its brief and the tool
descriptions. It does not see your context, and it is not guaranteed to have
loaded any skill, so the brief is the contract:

- **Label.** The lane name. It keys the todo list and the swarm UI.
- **Role and objective.** The role, and the specific outcome to achieve.
- **Scope and out of scope.** The files or surfaces it may touch, and those
  it must not. A worker that knows the boundary stops at it. A worker that
  does not will search the whole repository to be sure.
- **Context and known evidence.** The facts it may rely on, so it does not
  re-derive them.
- **Acceptance criteria.** The observable conditions that prove the work is
  done. The criteria are also the lane's verification target set: once they
  are checked, the lane reports. A lane that keeps reading after its criteria
  are checked has overrun its brief.
- **Validation.** The commands or checks to run.
- **Ownership.** The files it owns, so parallel lanes do not collide.
- **Dependencies.** What must land first.
- **Report contract.** What it must report back, including what failed.
- **Health and risk context.** For significant changes, include known Code
  Health findings, material dependencies, behavioral risks, and applicable
  quality constraints.
- **Target list.** The finite set of candidates, files, or requirements to
  check, with its count. "Check whether the save path is covered" is
  unbounded. "Check these 7 save-path functions and report a verdict for
  each" is a lane.
- **Evidence budget.** The tool-call count that bounds the investigation
  phase. The default is 60. A lane without a stated budget uses the default.
- **Stop condition.** What the lane does when the target list is done or the
  budget is spent: report what it has and mark the rest unverified.

If a material field is missing, say so in the brief rather than assuming it.

**The coordinator's own read phase is bounded too.** A brief bounds a worker.
Nothing bounds the coordinator's own reading, and that is where the same
failure appears. In a corpus of 334 sessions, 78% of sufficiency declarations
were in root, primary sessions rather than delegated lanes, and one session
ran 774 tool calls after its last file write without ever implementing the
target change. Before its own first edit, a coordinator states the finite set
of things it needs to know, and reads only those. A named section, category,
or file is the scope, not a licence to read the whole specification. A file
already read in full is not read in full again. The soft default is 60 tool
calls before the first edit; a coordinator that needs more says why. When the
coordinator declares that it has the shape or the design, its next call is
the implementation, the validation, the plan, or the report.

**The coordinator's own tail is bounded too.** After the last write, the
remaining calls check the acceptance criteria and then report. The same corpus
that produced 774 tool calls after a last file write also produced a median
of 14 tool calls after the last mutation. The verification phase has a target
set: the acceptance criteria, one check each, and it ends at the first of: the
criteria are checked, a check cannot fail, the remaining question would change
what is delivered (which is implementation work, so make the change and check
the criterion it affects), or the budget is spent. Then the report follows.

Enforcing the bound. A brief is a request, not a stop. A worker that has
already met its completion criteria and keeps searching will not stop because
the brief asked it to, so the coordinator enforces it.

- **Watch the lane, do not just wait for it.** `swarm list` shows each
  member's status, its last activity age, and whether it is stalled. A member
  that is `running` with a growing activity age is working. A member whose
  activity age keeps growing while its target list is already covered is
  expanding scope.
- **Ask for the partial result first.** `swarm message` to the lane with the
  exact words "report now with what you have, mark the rest unverified". A DM
  is cheap and often enough on its own.
- **A DM is not a stop.** A worker that ignores a request to wrap up has
  demonstrated that it will not honour a soft instruction. Do not repeat the
  DM.
- **Use `swarm stop` when a lane has overrun its brief.** The coordinator
  owns its own spawned workers, so `stop` works without `force`. It terminates
  the worker and persists the session as closed. Stopping loses the unwritten
  remainder, so it is the last step, not the first. Record in the todo row
  what was lost: the lane's completed targets, the targets it left unverified,
  and the fact that the remainder is not covered. A stopped lane is a partial
  result, and the coordinator's own report has to say so.
- **Use `force` only for a session this coordinator did not spawn.** It
  refuses otherwise by design.
