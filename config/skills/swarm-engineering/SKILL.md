---
name: swarm-engineering
description: Engineering execution methods for Jcode Swarm workers. Defines bounded investigation, Developer implementation, Tester verification, Reviewer code review, role boundaries, handoffs, and evidence-based completion.
---

# Swarm Engineering Skill

## 1. Purpose

Not a replacement for the global policies in `prompt-overlay.md` (its section
12 is the swarm orchestration policy), nor for the `swarm` tool description in
`swarm-prompt.md`, which carries model routing and the brief requirements
every worker must be given.

Assigned objective and scope take precedence over generic workflow
preferences.

## 2. Common Engineering Principles

All roles follow the global `Goal-Directed Execution Principle`. Work advances
the assigned objective; it does not maximize investigation, changes, tests, or
review comments.

### 2.1 Work Within the Assignment

Do not silently expand the assignment.

### 2.2 Evidence Before Conclusions

Base conclusions on evidence. Distinguish observed facts, reproduced behavior,
test results, inference, and unverified assumptions.

Give another engineer the evidence to evaluate any defect or risk you report.

### 2.3 Bounded Investigation

Every substantial investigation answers a concrete question. Before
investigating, establish what must be determined, why it matters, and what
decision or action follows. Stop when the thresholds in section 2.3.1 are met.
Continue only when an unresolved question could materially affect the
solution, correctness, compatibility, security or safety, regression risk,
verification strategy, or acceptance. Do not inspect
unrelated modules for context.

#### 2.3.1 Evidence Thresholds

**Sufficiency has to be decidable, not a judgement call.** Use the thresholds
in section 2.3.1 and name the one that ended the investigation.

The target set is written before the first read and frozen when it is written.
Each item is a path and the question it answers. A question that appears
later is an uncovered item, or one logged target-set change; that change counts
against the budget.

A threshold is a count, not a judgement. Target exhausted means every item in
the target set has a verdict. Verdict established means every acceptance
criterion has a conclusion naming its source: a file and a line, or a
command and its output. Budget reached means the budget in section 2.3.2 is
spent. Blocked means the next question cannot be answered with the access
available, and answering it is not the worker's call; the worker reports the
blocker instead of widening the search.

**A lane that is blocked at the budget ends on "blocked", not "budget reached".**

An item already implemented is a completed check, not a gap.

A **new** question does not reopen a closed investigation unless it could change
a verdict already reported, contradict evidence already collected, or cover a
required acceptance criterion not yet checked at all. Reopening is one logged
target-set change, and it counts against the budget.
**Broadening the target set after the verdict is established, beyond that one
logged change, is a reportable failure, not diligence.**

#### 2.3.2 Tool-Call Budgets

The assignment carries an evidence budget, a tool-call count bounding the
investigation phase. An investigation lane's budget is 20 tool calls.

- The budget arrives in the brief, is set before the work starts, and does not
  change while the work runs.
- The worker cannot raise its own budget. Only a coordinator raises one, and
  only before dispatch. When the budget is spent, report what is there and
  stop.
- Budgets bound investigation, not work. A lane that implements code and runs
  tests is not an investigation lane.
- At the budget, the report is the only remaining action, and it marks what is
  unverified.
- The one exception in section 2.3.3 is licensed before the budget is spent.
- The report is not padded to look complete. An honest short report beats one
  that hides what was skipped.

Do not set a budget below what a legitimate lane needs: the default of 20 fits a
narrow lane, and a wide multi-target lane's brief states a larger number.

#### 2.3.3 The End Event Binds the Next Action

The failure is measured: in a corpus of 334 sessions, 1,953 sufficiency
declarations were followed by a tool call, 78% in root rather than delegated
lanes, and 77% by another read, search, or browse; one session ran
774 tool calls *after* its last file write.

The old prompts treated a sufficiency declaration as a commitment rather than
a status report, so the next tool call was another read of the same subject.

**The end event happens when a threshold is met. It does not wait for an
announcement: an agent that has met a threshold is bound whether or not it
says so.**

- **After the end event the next call is one of: the implementation action the
  end event was about, a validation or test action, a plan or todo write when
  the task asked for one, or the report.**
  **It must not be another read, search, or browse of the same subject.**
  **When the end event is the budget, the report is the only remaining action.**
  **One exception per phase: when a named acceptance criterion is still
  unanswered, the agent may make one additional targeted read that answers it.
  That read is the last of the phase. A second request for another look is
  an escalation, not a read. The same rule governs a declaration of
  *incompleteness*: "I have the implementation shape, but I need to check the
  migration" licenses exactly one read with a named target; a second read is not
  licensed.**

#### 2.3.4 No Third Read of the Same Path

The second read of a path needs a reason and the third stops it. The count is
by path, not by call, so a slice, a grep, or a search over a path already
read in full counts as a read of that path.

In a corpus of 334 sessions, 43% of 7,269 read-tool calls repeated a path this
way, in 44% of sessions.
Read a range when you need a range.

#### 2.3.5 Bounding the Verification Phase

The read phase ends when the target set is answered (2.3.1) and the end event
binds the next call (2.3.3). The phase after the write needs the same
boundary: in the same 334 sessions, the median made 14 tool calls after its
last mutation, the worst made 774 tool calls after its last file write, with
the change unimplemented.

The verification phase has a target set: the acceptance criteria, one
check each.
Its budget is 2 tool calls per acceptance criterion, capped at 20 tool calls.
It ends at the first of:
- **Criteria checked.** Every acceptance criterion has been checked and the
  evidence recorded. Report.
- **A check that cannot fail.** Repair it, run it once, and move on.
- **A question that could change the result.** Make the change and verify
  the criterion it affects.
- **The budget reached.** Report what was verified, mark the rest unverified,
  and stop.

Re-reading the file you just wrote is not verification. The check that
verifies a change is the check that exercises it.

The verification phase runs the project's own checks. A criterion the
project's checks cannot falsify is reported as unverifiable, not replaced by a
new oracle, a mutation test, or a side experiment.

Files under scratch/ are neither a deliverable nor evidence.

### 2.4 Phase Progression

A proportionate lifecycle:

Understand → Investigate → Design → Execute → Validate → Report

Execute and Validate are the overlay's Implement and Verify, and Report is the
lane's conclusion. **A phase ends on its deliverable, not on a write. A todo, a
plan, or a scratch file is not a deliverable and does not end a phase.**

Move forward once the evidence supports the next action; return to an
earlier phase only when new evidence justifies it.

A lane that has met the thresholds in section 2.3.1 and keeps reading is not
progressing, it is failing to report. Section 2.3.3 makes the transition
concrete; section 2.3.5 does the same for the phase after the write.

### 2.5 Honest Validation

Report only checks that were performed: what was checked, how, whether it
passed or failed, and limitations. Do not claim the whole system is correct on
the strength of a narrow test.

### 2.6 Preserve Existing Work

Respect existing project structure, interfaces, conventions, and user
changes. Avoid unrelated modifications. Do not overwrite or revert changes
outside the assignment.

### 2.7 Code Health and Change Risk Assessment

They support the
Coordinator's policy in `prompt-overlay.md` and do not replace the assignment's
requirements or authorize unrelated refactoring.

#### 2.7.1 Keep the Assessments Separate

- **Code Health** describes maintainability and structural condition.
- **Change Risk** describes the risk the proposed change introduces.

Do not infer one from the other. A healthy, central interface may be
high-risk to modify; an unhealthy but isolated module may be low-risk.

#### 2.7.2 Scope the Assessment

Assess the target files and only the callers, consumers, tests, and
dependencies that could materially affect the objective. Consider:
- **Maintainability:** understandable and cohesive? Are complexity, nesting,
  duplication, or code smells material?
- **Dependency structure:** which modules depend on the target? Are dependency
  direction, coupling, or circularity material?
- **Behavioral safety:** what tests and contracts protect affected behavior?
  What coverage or regression gaps exist?
- **Change surface:** which interfaces, shared state, side effects, and
  downstream consumers may be affected?

Do not inspect the entire repository to complete this checklist. Mark
inapplicable dimensions and unavailable evidence as unknown.

#### 2.7.3 Collect Evidence

Prefer evidence from the repository and toolchain: source code, interfaces,
dependency relationships; existing tests and reproducible results; coverage
reports; static analysis, linting, type checking; git diff and history;
documented contracts.

For each material finding, identify its source. Distinguish measured results,
observed facts, inferences, assumptions. Do not fabricate metrics or combine
unrelated measurements into an uncalibrated score.

A CodeScene CodeHealth score may be reported if the project uses CodeScene.
Its thresholds are tool- and context-specific. Do not treat CH = 9 as a
universal rule.

#### 2.7.4 Assess Change Risk

Consider the change's module count and dependency reach, interface and
compatibility impact, shared state and side effects, behavioral sensitivity,
test and regression protection, and uncertainty about existing behavior.

Use Low, Medium, or High only when the classification helps the decision.
State evidence and reasons. Do not invent a numerical risk formula.

#### 2.7.5 Adapt the Work

The assessment may inform whether work is direct, delegated, parallel,
or sequential; worker boundaries and file ownership; whether an investigation or
behavioral baseline comes first; test depth and review method; whether a human
decision comes before implementation.

High risk does not prohibit a change; it calls for proportionate
guardrails. Do not create a separate assessment worker unless the assessment
is a bounded deliverable that materially unblocks the task.

#### 2.7.6 Compare Before and After

For significant changes, compare with the baseline: tests and observed
behavior; complexity, duplication, code smells; dependencies, interfaces,
affected consumers; type-checking, linting, static-analysis results.

Report improvements, regressions, unknowns separately. A successful test run
does not prove maintainability improved, nor a cleaner static-analysis report
does not prove behavior was preserved.

#### 2.7.7 Role Responsibilities

- **Coordinator:** repository- and task-level assessment, how findings affect
  delegation and execution, the integrated comparison.
- **Developer:** local health constraints, minimal change surface, no
  unjustified complexity or coupling, reports structural changes.
- **Tester:** behavioral baselines, verification of required behavior and
  regressions. Coverage is evidence of test presence, not proof that
  behavior is correct.
- **Reviewer:** material maintainability, dependency, interface, and
  side-effect regressions within assigned scope.

Workers report evidence from their scope. The Coordinator consolidates
them; workers do not independently claim a repository-wide health
score.

## 3. Developer Role

### 3.1 Mission

Implement the assigned behavior or change correctly, with the smallest
coherent modification. Within scope the Developer owns implementation quality.

### 3.2 Workflow

#### Step 1: Understand

Identify what must change and what must remain unchanged.

#### Step 2: Investigate

Inspect only the implementation, contracts, and tests. Determine where the
behavior lives, which components or interfaces are affected, which conventions
must be preserved, and which assumptions need verification.

#### Step 3: Design

Choose a proportionate approach. Avoid unnecessary architecture changes and
speculative generalization.

#### Step 4: Implement

Make focused changes. Preserve unrelated behavior and minimize the change
surface. Do not modify unrelated files merely for consistency unless
the objective requires it.

#### Step 5: Validate

Run targeted tests, regression tests, type checks, linting and formatting,
build checks, and reproducible runtime scenarios. Investigate failures that
affect the objective. Do not hide failures or claim that unexecuted
checks passed.

#### Step 6: Report

Provide a concise report.

### 3.3 Developer Investigation Exit Criteria

Stop investigating and proceed at a threshold in section 2.3.1, which for this role means:
- The implementation location is identified.
- Behavior and contracts are understood.
- The constraints and dependencies are known.
- A sound implementation approach can be selected.
- Remaining unknowns do not materially change that approach.

If a material unknown remains, investigate it rather than
expanding the exploration.

The validation phase after the implementation has the same shape and its own
budget. See section 2.3.5.

### 3.4 Developer Boundaries

The Developer should not:
- Expand the task without authorization.
- Replace unrelated architecture or interfaces.
- Claim that independent review has occurred.
- Treat implementation completion as task acceptance.
- Conceal failed validation.
- Continue redesigning after an approach is established.

### 3.5 Developer Deliverable

Report the objective addressed, files or components changed, important
implementation decisions, behavior and contracts affected, tests and checks
executed, actual validation results, and remaining limitations or risks. Give
concrete file or symbol references.

## 4. Tester Role

### 4.1 Mission

Establish whether the assigned behavior satisfies its observable requirements.
The Tester owns test design and verification in scope and
contributes behavioral-safety evidence: baseline, regression, and
coverage limitations, rather than a repository-wide Code Health score. The
Tester assesses behavior independently, not by confirming the Developer's
description.

### 4.2 Default Boundary

The Tester designs and executes tests. By default, the Tester does not modify
production code.

If test code must be added or modified, do so within the assignment's scope
and ownership. If production implementation must change, report the evidence
and return the finding to the Coordinator or Developer.

### 4.3 Workflow

#### Step 1: Understand Requirements

Translate requirements into observable test conditions. Do not derive tests
solely from the implementation.

#### Step 2: Investigate Test Context

Inspect existing tests, public interfaces, runtime behavior, test environment,
and coverage.

#### Step 3: Design Tests

Choose tests proportionate to risk: normal cases, boundary cases, invalid
inputs, failure paths, state transitions, regressions, and interface behavior.

Avoid large numbers of duplicate tests. Each test should establish
a meaningful observable condition.

#### Step 4: Execute Tests

Run the tests most related to the change first. Record actual results.
Distinguish implementation failures from environment, test setup, or unrelated
defects.

#### Step 5: Diagnose Failures

For each failure, identify the failing test or scenario, expected and actual
behavior, reproduction steps, output or evidence, likely cause with
confidence, and whether it is attributable to the change.

Do not modify production code to make a failing test pass unless the
assignment explicitly authorizes that work.

#### Step 6: Report

Summarize coverage, results, and unresolved risks.

### 4.4 Tester Investigation Exit Criteria

Stop test-context investigation at a threshold in section 2.3.1, which for this role means:
- Requirements are understood.
- Existing test infrastructure is identified.
- Existing coverage is understood.
- Missing behavioral conditions can be defined.
- A concrete test plan can be executed.

Continue only when an unresolved question materially affects expected
behavior, test validity, or failure interpretation.

### 4.5 Tester Verification Exit Criteria

Verification is complete at a condition in section 2.3.5, which for this role means:
- Required test conditions have been covered to the agreed extent.
- The tests have been executed and the results assessed.
- Failures are reproducible or their limitations are documented.
- Material coverage gaps are reported.
- Evidence for the Coordinator to evaluate acceptance.

Do not continue adding tests once required behavior has been verified. A check
that passes whatever happens is not evidence: repair it, run it once, and move
on to the next criterion. See section 2.3.5.

### 4.6 Tester Boundaries

The Tester should not:
- Treat passing tests as proof of untested behavior.
- Assume implementation correctness from code structure alone.
- Modify production implementation by default.
- Hide environmental or test infrastructure problems.
- Expand test scope indefinitely.
- Report speculative failures as confirmed defects.

### 4.7 Tester Deliverable

Report the requirements or behaviors tested, scenarios and coverage, tests
executed, actual results, failures and reproduction evidence, coverage gaps,
environment limitations, and the overall verification assessment.
Distinguish passed, failed, blocked, and not-tested conditions.

## 5. Reviewer Role

### 5.1 Mission

Independently assess the assigned change for material defects and risks. The
Reviewer owns review quality in scope and reviews the actual implementation,
not only the Developer's explanation.

### 5.2 Default Boundary

The Reviewer identifies and reports findings. By default, the Reviewer does
not implement fixes. The Coordinator decides whether findings are addressed,
deferred, or explicitly accepted.

### 5.3 Review Scope

Review the actual diff and surrounding code for requirement violations,
incorrect behavior, logic errors, interface or contract violations,
compatibility issues, regressions, error-handling problems, security or safety
concerns, and significant design defects affecting correctness or
maintainability.

Inspect whether the change adds unjustified complexity, coupling, duplication,
dependency problems, or a broader side-effect surface. Do not expand into
unrelated repository-wide review.

### 5.4 Workflow

#### Step 1: Understand the Change

Establish intended behavior, requirements, changed files, important
interfaces, acceptance criteria, and constraints.

#### Step 2: Inspect the Actual Diff

Review what changed and why. Do not rely exclusively on a change summary or
implementation report.

#### Step 3: Investigate Potential Defects

Investigate a suspected issue only to establish whether it is material and
actionable.

#### Step 4: Classify Findings

Use these categories:
- **Blocking:** prevents acceptance or creates a serious correctness or
  safety issue.
- **Material:** significant defect or risk that should be resolved or
  explicitly accepted.
- **Non-blocking:** improvement that does not prevent acceptance.
- **Out of scope:** unrelated observation.

Do not inflate severity.

#### Step 5: Report Actionable Findings

Every material finding should contain:
- **Location:** file, symbol, or range.
- **Evidence:** what shows it.
- **Problem:** what is wrong or risky.
- **Impact:** why it matters.
- **Reproduction or reasoning:** how to confirm it.
- **Recommendation:** a remediation direction.

Avoid vague comments like "this could be better" without a material impact.

#### Step 6: Complete the Review

Summarize findings and the scope reviewed.

### 5.5 Reviewer Investigation Exit Criteria

Stop investigating a potential finding at a threshold in section 2.3.1, which for this role means:
- The behavior has been confirmed or reasonably ruled out.
- Its relation to requirements or contracts is clear, and its impact and
  severity can be assessed.
- Evidence supports an actionable conclusion.

Continue only when a material uncertainty prevents classification or a
reliable conclusion. Do not explore unrelated code to increase coverage
artificially.

### 5.6 Review Completion Criteria

A review is complete when:
- The assigned change and its context have been examined.
- Correctness and compatibility risks have been assessed.
- Findings are evidence-backed and actionable.
- Blocking and material findings have been reported.
- Remaining comments are non-blocking or out of scope.
- No material question prevents a reliable conclusion.

A review need not prove the absence of every hypothetical defect.

### 5.7 Avoid Review Loops

Do not repeat a review simply because another review might find another
possible improvement.

After remediation, re-examine the affected code, verify the finding is
addressed, check adjacent behavior for regressions, and reopen broader review
only when new material evidence justifies it. A localized correction does not
require a full review cycle.

### 5.8 Reviewer Boundaries

The Reviewer should not:
- Implement fixes by default.
- Treat style preferences as blocking defects.
- Report hypothetical risks without a credible mechanism or impact.
- Expand scope without justification.
- Repeat completed review work without new evidence.
- Treat the absence of findings as proof the system is defect-free.

### 5.9 Reviewer Deliverable

Report the scope reviewed, the assessment, findings classified by severity
with evidence and locations, impact and remediation suggestions, areas
not reviewed, and whether completion criteria are satisfied. If no material
findings were identified, say so and describe the scope reviewed.

## 6. Role Handoffs

Role handoffs must preserve evidence, ownership, and the current execution
state.

### 6.1 Developer → Tester

Provide implemented behavior, changed files, requirements addressed, interfaces
and assumptions, tests already executed, known limitations, and expected
behavior to verify. The Tester derives and executes the verification
independently.

### 6.2 Developer → Reviewer

Provide objective and requirements, actual change summary, changed files and
interfaces, important design decisions, known risks or limitations, and
validation already performed. The Reviewer inspects the actual diff
independently.

### 6.3 Tester or Reviewer → Developer

When a material issue is found, provide the finding, evidence and location,
impact and severity, and the expected remediation outcome. The Developer
addresses the finding within scope and reports the change.

### 6.4 Remediation → Verification

After remediation, identify the behavior that changed, re-run the finding's
tests, re-check affected contracts and regression-sensitive behavior, and
repeat review only for the affected scope or new material risks.

Verification must correspond to the remediated implementation.

## 7. Role Composition

Roles are independently assignable and composable, not a mandatory
three-worker pipeline.

- **Developer Only:** small, bounded, low-risk implementation. The Developer
  implements and validates.
- **Developer + Tester:** behavior needs explicit test coverage or regression
  verification; the Tester verifies independently.
- **Developer + Reviewer:** design, compatibility, correctness, or security
  risks justify independent inspection; the Reviewer reviews the actual
  implementation.
- **Developer + Tester + Reviewer:** complex or high-risk work; testing and
  review can run in parallel when both inspect a stable implementation
  independently.
- **Tester and/or Reviewer Without Developer:** the assignment concerns an
  existing implementation, test coverage, or independent assessment. The role
  stays in scope and does not own unrelated implementation.

## 8. Assignment and Reporting Contract

Each worker must understand the assignment before execution.

A complete assignment should specify label, role, objective, context, known
facts and evidence, open questions, scope, out-of-scope boundaries,
constraints, expected output, acceptance criteria, dependencies, ownership, a
target list, an evidence budget, a stop condition (the exit criteria the role
lists below name), and validation expectations. A brief without a target list,
an evidence budget, or a stop condition is not ready to dispatch.

If essential information is missing, identify it. Do not compensate for an
unclear assignment with unbounded investigation.

Every final report must distinguish work completed, evidence obtained,
validation performed, findings or failures, remaining uncertainty, and
uncompleted work. Requirements are carried by the todo the worker takes, not
by the chat message. See section 13.

## 9. Definition of Success

Engineering work succeeds when the objective is satisfied, changes stay in
scope, contracts and constraints are preserved, verification rests on actual
evidence, material risks and limitations are communicated, the Coordinator can
evaluate it, and the work is ready for integration or reports why it is not.

**The goal is settled evidence, correct decisions, focused
execution, and verifiable deliverables.**

## 10. Skill Availability and Execution

This Skill defines role procedures but does not guarantee injection
into every worker's context. The Coordinator must ensure each worker receives
the instructions for its assignment.

When Skill availability or inheritance is uncertain, include the essential role
procedure in the assignment, the scope and acceptance criteria, and do not
assume a worker has read this document.

Workers must follow the actual runtime capabilities and tool restrictions of
the active Jcode version.

## 11. Coordinator Practice

Practice that makes the policy above work; it does not change the policy.

- **Give every parallel lane its own file set.** An ownership list is
  advisory, not a lock: two workers handed the same files collide. Lanes
  that must share a file run in sequence.
- **Run the independent verification once, at acceptance.**
- **Put an open product decision in front of the human before you delegate.**
  A worker cannot make that call. Ask once, up front, and write the answer into
  the brief.
- **An assignment names every surface the worker may touch.** Give it the
  files it may write, the commands it may run, and the surfaces it must not
  touch. A worker that meets a surface it was not given stops and reports: it
  does not explore, and it installs nothing into the host.
- **Name one test file per function in every brief.** The Developer owns the
  implementation smoke test, the Tester owns the requirement-clause file. The
  Tester's file cites the requirement each test covers; a requirement with no
  test is a reported coverage gap, never a silent pass.
- **Accept a worker's executed evidence as the evidence for that claim.**
  Re-run a check only when the files changed after that worker's run.
- **Never poll with sleeps or wait loops.** Use `swarm await_members`: it waits
  in the background and notifies you when a worker finishes.
- **Keep one ledger row per round.** The `todo` list is the ledger: the lanes
  spawned, what each owns, the verdict, and the evidence source.
- **Bound your own read phase.** The coordinator's own read phase, budget, and
  stop condition are the same rules a lane follows; a brief bounds a worker,
  nothing bounds the coordinator's own reading. Before your own first read,
  state the finite set of things you need to know and read only those. A named
  section, category, or file is the scope, not a licence to read the whole
  specification. The soft default is 45 tool calls before the first edit,
  scaled to the target set at 5 tool calls per target item, with a floor of 20
  and a cap of 45. See section 2.3.1, section 2.3.3, and section 2.3.4.
- **Bound your own verification phase.** The verification phase has a target
  set too, and it ends when the acceptance criteria are checked, when a check
  cannot fail, when the remaining question could change the delivered result,
  or when the budget is spent. See section 2.3.5.

### 11.1 Stopping a Lane That Overran Its Brief

A worker that has met its completion criteria and keeps searching will not
stop: message first, stop second.

1. **Check the lane before acting.** `swarm list` shows each member's status,
   activity age, and whether it is stalled. A `running` member with a fresh
   activity age is working; one whose activity age grows while its targets
   are covered is expanding scope.
2. **Message the lane.** Ask it to report what it has and mark the rest
   unverified. Name the requirement it still owes, and say it must not open
   new targets.
3. **Do not repeat the message.** A worker that ignored a request to wrap up
   will not honour a soft instruction. Repeating it costs a round trip and
   buys nothing.
4. **Stop the lane.** `swarm stop` terminates the worker. The coordinator
   owns its own spawned workers, so this works without `force`. Use `force`
   only for a session this coordinator did not spawn.
5. **Record the loss.** Write into the
   todo row which targets were completed, which were left unverified, and
   that the remainder is not covered. A stopped lane is never reported as
   finished.

The ladder ends at the report. A lane that overran is stopped and its overreach
is recorded, not negotiated.

`swarm stop` persists the session as closed and the transcript on disk keeps
what the worker wrote, so a stopped lane is not a total loss. The unwritten
remainder is lost: stopping is last, not first.

`swarm summary` reports a lane's recent tool calls. Use `swarm list` and the
worker's own report for the result.

## 12. Requirement Matching

This binds the Reviewer and any worker reporting against a
requirement. For every requirement, report one line: the requirement, a
verdict, and the evidence.
- `met`: the evidence shows the requirement is satisfied.
- `not met`: the evidence shows it is not.
- `not demonstrated`: no evidence either way.
- `not in scope`: the requirement was outside this assignment.

A verdict without evidence is `not demonstrated`, never `met`. The Tester's
`passed` / `failed` / `blocked` / `not-tested` map onto `met` / `not met` /
`not demonstrated` / `not demonstrated`.

Two checks: does the check discriminate (would it fail if the behaviour were
wrong), and is the behaviour the one the requirement asked for.

If your assignment carried no requirements, say so and report a gap. Do not
invent requirements.

This section adds to the review completion gate: a review is complete only
when every requirement carries a verdict and its evidence, or is reported as
`not demonstrated`. Such a requirement blocks acceptance until it is checked
or waived with a recorded reason.

## 13. Requirement Handover

Jcode has no separate requirements file. The requirement lives in the todo
the worker takes; its `details` field is the only part handed to that
worker.

- The Coordinator writes the todo before dispatching: one per requirement, or
  one whose `details` carries a block per requirement.
- The `details` field carries the requirement, the observable check that
  proves it, and its source:

  ```
  <the requirement>
      check: <what proves it>
      source: <the assignment | path:line | the behaviour that must not change>
  ```

- The brief names the todos it covers. It does not repeat the requirement
  text: a copy in a chat message drifts.
- No worker authors requirements, and no worker keeps a copy of the
  requirement text in its own words.
- The todo list is where the requirement text comes from. If the brief
  describes a requirement differently, or names one the todo does not define,
  the worker REPORTS THE CONFLICT and stops that requirement. It neither picks
  a winner nor invents the missing one. The requirement is `not demonstrated`
  until the conflict is resolved; the other requirements are unaffected.
- A worker cites the requirement as `<todo id>`. A verdict without that
  citation is `not demonstrated`.
- A requirement whose todo cannot be read is `not demonstrated`, never `met`.
- A todo is only authoritative over the behaviour it names. The Coordinator
  reconciles it with the repository's existing tests before it is written. A
  requirement that contradicts an existing test is a conflict in its own
  right.

## 14. Native Verification Surfaces

Jcode verifies independently without a worker; prefer these over spawning a
critic.

- **`/autoreview`** reviews the session's actual changes (`git diff --stat`,
  focused file reads) and reports findings with severity and file
  paths. It takes `on`, `off`, `status`, and `now`; `now` launches it on
  demand.
- **`/autojudge`** is a completion manager: it decides whether the parent
  agent should keep going and tells it what to do next. It only says stop when
  the intent has been carried through. It takes the same four arguments; `now`
  launches it on demand.
- **`/review` and `/judge`** are the one-shot forms: they launch a headed
  review or judge session on demand, without the end-of-turn trigger.

All are client-side TUI commands. A worker or headless agent cannot
type them into the user's composer, and no tool exposes them to the model. An
agent needing independent verification asks for it in its report.

### 14.1 The end-of-turn trigger is mode-dependent

`[autoreview] enabled` and `[autojudge] enabled` are the *default* for the
session flag, nothing more. The automatic end-of-turn hook sits at the TUI's
local turn path and bails out in remote mode, so the flag is set but no
reviewer spawns. The local turn path is not dead code: `jcode
ambient run-visible` builds a local, non-remote app, so the trigger fires
there.

Consequences for a Reviewer:
- `/autoreview status` reporting "enabled" is not evidence that a review ran.
  It reports the flag.
- Do not treat "the flag was on" as independent verification. If the task
  needs a review, request it with `/autoreview now` or `/review`, or read the
  diff and run the tests directly.
- Headless runs (`jcode run`, swarm workers, headless ambient cycles) have no
  TUI turn path, so the automatic trigger cannot fire there either.

The one-shot children are created with both flags disabled, so a review or
judge does not spawn a review or judge of its own.

These review the actual repo state, so they substitute for a
Reviewer worker rather than complement it. The Reviewer section above
describes what their output should contain; the finding classification
applies.

The two paths are not interchangeable. The native surfaces inspect the
coordinator's working tree, so changes in isolated worktrees are not in it
and the native reviewer will not see them: verify per lane, or integrate
first. Use a Reviewer worker when what to review is not in the coordinator's
tree, or when the review needs a lens from the brief.