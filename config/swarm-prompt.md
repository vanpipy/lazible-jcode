<!--
This file IS the swarm config. It becomes the `swarm` tool description, so it is
always-on context in every session, including worker sessions. Keep it short.
Override globally at ~/.jcode/swarm-prompt.md or per-project at
./.jcode/swarm-prompt.md.
-->

Model routing guidance for spawned swarm agents. Pass `model` to choose a model
for newly spawned workers, including workers created by assignment or `launch`.
An explicit model overrides `agents.swarm_model`. When omitted, workers use that
configured default, or inherit the coordinator's model and route when unset.
Pass `model: "inherit"` to force coordinator inheritance even with a configured
default. Model selection does not change reused workers. Run `swarm list_models`
to check available models/routes. Route-prefixed values such as
`openai-api:gpt-6-astra` pin the authentication route as well as the model.
Use `[agents] swarm_model` to set the default for future worker spawns, and
the `model` parameter for task-specific choices. Worker reasoning effort is
not selectable from this tool: workers run at the user's `[agents]
swarm_effort` (default `low`).

What to spawn workers for:

- Spawn workers to implement: build features, fix bugs, write tests, migrate
  or refactor code. Give each worker a concrete, scoped change with clear file
  ownership and an acceptance check it can run itself.
- Do not spawn a reviewer, auditor, critic, or verifier when the work under
  review is in your own tree. Use the native `/autoreview` and `/autojudge`
  surfaces, or review the diff and run the tests yourself. The native
  end-of-turn trigger does not fire in every mode, and those commands are typed
  by the user, not called by an agent, so name the review you want in your
  report and let the user run `/autoreview now`. Spawn a Reviewer worker
  only when what it must review is not in your tree, or when the review needs
  a lens you state in the brief. Each implementation worker validates its own
  change before reporting.
- Avoid a worker whose only job is to gather information with nothing to
  build on. Fold the needed investigation into the implementation task, or do
  it yourself first. A delegated investigation is worth a lane when it
  answers a bounded question that unblocks a decision, and the brief says
  which question that is.

Structure guidance for spawned swarm agents:

- Always pass `label` when spawning (e.g. `label: "auth refactor"`) so the swarm
  UI shows what each agent is for. The explicit `spawn` action rejects missing or
  blank labels. A spawned worker owns that lane in your todo list; the todo
  list is the lane and syncs only that worker. Pass `phase` when the lane
  belongs to a specific phase of the plan.
- Only the root session may spawn agents. Workers must complete their assigned
  task directly and report back rather than creating another generation.

What every brief must carry. A worker sees its brief and the tool descriptions.
It does not see your context, and it is not guaranteed to have loaded any
skill, so the brief is the contract:

- Role, and the objective to achieve.
- Scope and out of scope: the files or surfaces it may touch, and those it
  must not.
- Context and known evidence: the facts it may rely on, so it does not
  re-derive them.
- Acceptance criteria: the observable conditions that prove the work is done.
- Validation: the commands or checks to run.
- Ownership: the files it owns, so parallel lanes do not collide.
- Report contract: what it must report back, including what failed.
- Relevant health and risk context: for significant changes, include known
  Code Health findings, material dependencies, behavioral risks, and
  applicable quality constraints. Keep this scoped to the worker's lane.

If a material field is missing, say so in the brief rather than assuming it.

Requirements belong to a todo lane, not to chat text. Write the todo before
dispatching, put the requirement, its observable check, and its source in the
todo's `details`, and have the brief name the todo rather than restating the
requirement. A requirement copied into a chat message drifts; a requirement in
a todo has a stable id to cite. The swarm plan itself is a server-level object
scoped to the swarm, not a file in the repo, and it is not the todo list.
