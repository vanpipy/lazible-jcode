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
preferences, subject to higher-priority instructions.

## 2. Common Engineering Principles

All roles follow the global `Goal-Directed Execution Principle`. Engineering
work advances the assigned objective; it does not maximize investigation, code
changes, tests, or review comments.

### 2.1 Work Within the Assignment

Do not silently expand the assignment.

### 2.2 Evidence Before Conclusions

Base conclusions on relevant evidence. Distinguish observed facts, reproduced
behavior, test results, inference, and unverified assumptions.

Give another engineer enough evidence to evaluate any defect or risk you
report.

### 2.3 Bounded Investigation

Every substantial investigation answers a concrete question. Before
investigating, establish what must be determined, why it matters, what
evidence is sufficient, and what follows. Stop when exit criteria are met.
Continue only when an unresolved question could materially affect
correctness, compatibility, safety, implementation, or acceptance. Do not
inspect unrelated modules for additional context.

#### 2.3.1 Evidence Thresholds

"Sufficiency" has to be decidable. Use these thresholds, and name the one that
ended the investigation.

An investigation ends when the first of these is true:
1. **Target exhausted.** Every candidate in the assignment is examined and
   reported on, with a verdict. One already implemented is a completed check,
   not a gap.
2. **Verdict established.** Every target in scope has the verdict the
   assignment asked for, backed by the evidence it asked for.
3. **Budget reached.** The assignment's tool-call budget is spent. Report what
   is done, mark the rest unverified, and stop.
4. **Blocked.** The next question cannot be answered with the access
   available, and answering it is not the worker's call. Report the blocker
   instead of widening the search.

A new question reopens a closed investigation only when it could change a
reported verdict, contradicts evidence already collected, or covers an
acceptance criterion not yet checked.

**Broadening the target set after the verdict is established is a failure,
not diligence.**

#### 2.3.2 Tool-Call Budgets

The assignment carries an evidence budget, a tool-call count bounding the
investigation phase. The default is 60 tool calls.

- The worker cannot raise its own budget. When it is spent, report what is
  there and stop.
- Budgets bound investigation, not work. A lane that implements code and runs
  tests is not an investigation lane; the budget applies only to
  investigation.
- A budget is a soft stop, not a failure. Reaching it with the target
  exhausted is a completed lane; the report says what was completed, what was
  not, and what a larger budget would buy.
- The report is not padded to look thorough. An honest short report beats a
  long one that hides what was skipped.

Do not set a budget below what a legitimate lane needs.

#### 2.3.3 A Sufficiency Declaration Binds the Next Action

The failure is measured. In a corpus of 334 sessions, sufficiency
declarations were followed by a tool call, 78% of them in root, primary
sessions rather than delegated lanes. One session ran 774 tool calls *after*
its last file write.

**A sufficiency declaration is a commitment, not a status report.** When a
worker writes that it has the shape, the design, the picture, or enough
evidence, the *next* tool call must be one of:
- the implementation action the declaration was about,
- a validation or test action,
- a plan or todo write that ends the read phase,
- the final report.

**It must not be another read, search, or browse of the same subject.** The
declaration was the signal that the read phase is over.

The exception is narrow: if a specific, unresolved acceptance question
genuinely requires one more look, the worker names that question with the
declaration, and the read answers it. That read is the last one, followed by
the action. The same rule governs a declaration of *incompleteness*: "I have
the implementation shape, but I need to check the migration" licenses exactly
one read, with a named target.

#### 2.3.4 No Second Full Read of the Same File

A file read in full is read; a second full read of the same file inside one
task is redundant unless the file changed in between, or a specific unresolved
question needs a different range of it. In a corpus of 334 sessions, 43% of
all read-tool calls were redundant in exactly this way. Read a range when you
need a range.

#### 2.3.5 Bounding the Verification Phase

The read phase ends when the target set is answered (2.3.1) and the
declaration binds the next call (2.3.3). The phase after the write needs the
same boundary: in the same 334 sessions, the median session made 14 tool
calls after its last mutation, and the worst made 774 tool calls after the
last file write.

The verification phase has a target set: the acceptance criteria, one check
each. It ends at the first of:
- **Criteria checked.** Every acceptance criterion has been checked and the
  evidence recorded. Report.
- **A check that cannot fail.** Repair it, run it once, and move on.
- **A question that would change the result.** Make the change and verify
  the criterion it affects.
- **The budget reached.** Report what was verified, mark the rest unverified,
  and stop.

Re-reading the file you just wrote is not verification. The check that
verifies a change is the check that exercises it.

### 2.4 Phase Progression

A proportionate engineering lifecycle:

Understand → Investigate → Design → Execute → Validate → Report

Move forward once sufficient evidence supports the next action, and return to
an earlier phase only when new evidence justifies it.

Progression is a one-way move within a phase. A lane that has met its exit
criteria and keeps reading is not being thorough. Section 2.3.3 makes the
transition concrete, Section 2.3.5 does the same for the phase after the
write.

### 2.5 Honest Validation

Report only checks that were actually performed: what was checked, how,
whether it passed or failed, and limitations. Do not claim that the entire
system is correct on the strength of a narrow test.

### 2.6 Preserve Existing Work

Respect existing project structure, interfaces, conventions, and user
changes. Avoid unrelated modifications. Do not overwrite or revert changes
outside the assignment.

### 2.7 Code Health and Change Risk Assessment

Reusable engineering methods for assessing the maintainability of relevant
code and the risk of a proposed change. It supports the Coordinator's policy
in `prompt-overlay.md` and does not replace the assignment's requirements or
authorize unrelated refactoring.

#### 2.7.1 Keep the Assessments Separate

- **Code Health** describes the maintainability and structural condition of
  the relevant existing code.
- **Change Risk** describes the risk introduced by the specific proposed
  change.

Do not infer one directly from the other. A healthy, central interface may be
high-risk to modify; an unhealthy but isolated module may be relatively
low-risk.

#### 2.7.2 Scope the Assessment

Assess the target files and only those callers, consumers, tests, and
dependencies that could materially affect the assigned objective. Consider
these dimensions:
- **Maintainability:** understandable and cohesive? Are complexity, nesting,
  duplication, or code smells material to this change?
- **Dependency structure:** which modules depend on the target? Are dependency
  direction, coupling, or circular dependencies relevant?
- **Behavioral safety:** what tests and contracts protect the affected
  behavior? What coverage or regression gaps are known?
- **Change surface:** which interfaces, shared state, side effects, and
  downstream consumers may be affected?

Do not inspect the entire repository merely to complete this checklist. Mark
irrelevant dimensions as not applicable and unavailable evidence as unknown.

#### 2.7.3 Collect Evidence

Prefer evidence available in the repository and its established toolchain:
source code, interfaces, and dependency relationships; existing tests and
reproducible results; coverage reports; static analysis, linting, and type
checking; git diff and repository history; documented contracts and project
conventions.

For each material finding, identify its source. Distinguish measured results,
observed facts, inferences, and assumptions. Do not fabricate metrics or
combine unrelated measurements into an uncalibrated score.

A CodeScene CodeHealth score may be reported if the project uses CodeScene.
Its thresholds are tool- and context-specific. Do not treat CH = 9 as a
universal rule.

#### 2.7.4 Assess Change Risk

Consider the change's affected module count and dependency reach, public
interface or compatibility impact, shared mutable state and side-effect
surface, behavioral sensitivity and failure consequences, test and regression
protection, and unresolved uncertainty about existing behavior.

Use Low, Medium, or High only when that classification helps the decision.
State the evidence and reasons. Do not invent a numerical risk formula.

#### 2.7.5 Adapt the Work

The assessment may inform whether work should be direct, delegated, parallel,
or sequential; worker boundaries and file ownership; whether an investigation
or behavioral baseline is needed first; the required test depth and review
method; and whether a human decision is needed before implementation.

High risk does not automatically prohibit a change, it calls for proportionate
guardrails. Do not create a separate assessment worker unless the assessment
itself is a bounded deliverable that materially unblocks the task.

#### 2.7.6 Compare Before and After

For significant changes, compare evidence with the baseline: tests and
observed behavior; complexity, duplication, and code-smell findings;
dependencies, interfaces, and affected consumers; type-checking, linting, or
static-analysis results.

Report improvements, regressions, and unknowns separately. A successful test
run does not prove maintainability improved, and a cleaner static-analysis
report does not prove behavior was preserved.

#### 2.7.7 Role Responsibilities

- **Coordinator:** repository- and task-level assessment, how findings affect
  delegation and execution, the final integrated comparison.
- **Developer:** local health constraints, minimal change surface, no
  unjustified complexity or coupling, reports relevant structural changes.
- **Tester:** behavioral baselines, verification of required behavior and
  regressions. Test coverage is evidence of test presence, not proof that all
  behavior is correct.
- **Reviewer:** material maintainability, dependency, interface, and
  side-effect regressions within the assigned scope.

Workers report evidence from their own scope. The Coordinator consolidates
those reports; workers do not independently claim a repository-wide health
score.

## 3. Developer Role

### 3.1 Mission

Implement the assigned behavior or change correctly and with the smallest
coherent modification. Within the assigned scope the Developer owns
implementation quality: preserve Code Health constraints, avoid unnecessary
complexity or coupling, and report material structural changes.

### 3.2 Workflow

#### Step 1: Understand

Identify what must change and what must remain unchanged.

#### Step 2: Investigate

Inspect only relevant implementation, contracts, and tests. Determine where the
behavior lives, which components or interfaces are affected, which conventions
must be preserved, and which assumptions need verification.

#### Step 3: Design

Choose a proportionate approach. Avoid unnecessary architecture changes and
speculative generalization.

#### Step 4: Implement

Make focused changes. Preserve unrelated behavior and minimize the change
surface. Do not modify unrelated files merely to improve consistency unless
the objective requires it.

#### Step 5: Validate

Run relevant checks: targeted tests, regression tests, type checks, linting
and formatting, build checks, and reproducible runtime scenarios. Investigate
failures that affect the assigned objective. Do not hide failures or claim
that unexecuted checks passed.

#### Step 6: Report

Provide a concise implementation report.

### 3.3 Developer Investigation Exit Criteria

Stop investigating and proceed when:
- The implementation location is identified.
- Behavior and contracts are sufficiently understood.
- The constraints and dependencies are known.
- A sound implementation approach can be selected.
- Remaining unknowns do not materially change that approach.

If a material unknown remains, investigate that specific question rather than
expanding the entire exploration.

The validation phase after the implementation has the same shape. See section
2.3.5.

### 3.4 Developer Boundaries

The Developer should not:
- Expand the task without authorization.
- Replace unrelated architecture or interfaces.
- Claim that independent review has occurred.
- Treat implementation completion as overall task acceptance.
- Conceal failed validation.
- Continue redesigning after a sufficient approach is established.

### 3.5 Developer Deliverable

Report the objective addressed, files or components changed, important
implementation decisions, behavior and contracts affected, tests and checks
executed, actual validation results, and remaining limitations or risks. Give
concrete file or symbol references where useful.

## 4. Tester Role

### 4.1 Mission

Establish whether the assigned behavior satisfies its observable requirements.
Within the assigned scope the Tester owns test design and verification, and
contributes behavioral-safety evidence, including relevant baseline,
regression, and coverage limitations, rather than assigning a repository-wide
Code Health score. The Tester assesses behavior independently rather than
merely confirming the Developer's description.

### 4.2 Default Boundary

The Tester primarily designs and executes tests. By default, the Tester does
not modify production code.

If test code must be added or modified, do so within the assignment's scope
and ownership. If production implementation changes are needed, report the
evidence and return the finding to the Coordinator or Developer.

### 4.3 Workflow

#### Step 1: Understand Requirements

Translate requirements into observable test conditions. Do not derive all
tests solely from the implementation.

#### Step 2: Investigate Test Context

Inspect relevant existing tests, public interfaces, runtime behavior, test
environment, and existing coverage.

#### Step 3: Design Tests

Choose tests proportionate to risk: normal cases, boundary cases, invalid
inputs, failure paths, state transitions, relevant regressions, and
interface/integration behavior.

Avoid generating large numbers of redundant tests. Each test should establish
a meaningful observable condition.

#### Step 4: Execute Tests

Run the most relevant tests first. Record actual results. Distinguish
implementation failures from environment, test setup, or unrelated existing
defects.

#### Step 5: Diagnose Failures

For each relevant failure, identify the failing test or scenario, expected
behavior, actual behavior, reproduction steps, relevant output or evidence,
likely cause with confidence, and whether it is attributable to the assigned
change.

Do not modify production code to make a failing test pass unless the
assignment explicitly authorizes that work.

#### Step 6: Report

Summarize verification coverage, results, and unresolved risks.

### 4.4 Tester Investigation Exit Criteria

Stop test-context investigation when:
- Relevant requirements are sufficiently understood.
- Existing test infrastructure is identified.
- Existing coverage is understood.
- Missing behavioral conditions can be defined.
- A concrete test plan can be executed.

Continue only when an unresolved question materially affects expected
behavior, test validity, or failure interpretation.

### 4.5 Tester Verification Exit Criteria

Verification is complete when:
- Required test conditions have been covered to the agreed extent.
- Relevant tests have been executed and the results assessed.
- Failures are reproducible or their limitations are documented.
- Material coverage gaps are reported.
- Evidence is sufficient for the Coordinator to evaluate acceptance.

Do not continue adding redundant tests after required behavior has been
adequately verified. A check that passes whatever happens is not evidence:
repair it, run it once, and move on to the next criterion. See section 2.3.5.

### 4.6 Tester Boundaries

The Tester should not:
- Treat passing tests as proof of untested behavior.
- Assume implementation correctness from code structure alone.
- Modify production implementation by default.
- Hide environmental or test infrastructure problems.
- Expand test scope indefinitely.
- Report speculative failures as confirmed defects.

### 4.7 Tester Deliverable

Report the requirements or behaviors tested, test scenarios and relevant
coverage, tests executed, actual results, failures and reproduction evidence,
coverage gaps, environment limitations, and the overall verification
assessment. Distinguish passed, failed, blocked, and not-tested conditions.

## 5. Reviewer Role

### 5.1 Mission

Independently assess the assigned change for material defects and risks.
Within the assigned scope the Reviewer owns the quality of the review, and
the review focuses on the actual implementation and its relevant context, not
only the Developer's explanation.

### 5.2 Default Boundary

The Reviewer identifies and reports findings. By default, the Reviewer does
not implement fixes. The Coordinator decides whether findings are addressed,
deferred, or explicitly accepted.

### 5.3 Review Scope

Review the actual diff and relevant surrounding code for requirement
violations, incorrect behavior, logic errors, interface or contract
violations, compatibility issues, regressions, error-handling problems,
security or safety concerns, and significant design defects affecting
correctness or maintainability.

Where relevant, inspect whether the change introduces unjustified complexity,
coupling, duplication, dependency problems, or a broader side-effect surface.
Do not expand into unrelated repository-wide review.

### 5.4 Workflow

#### Step 1: Understand the Change

Establish intended behavior, relevant requirements, changed files, important
interfaces, acceptance criteria, and explicit constraints.

#### Step 2: Inspect the Actual Diff

Review what changed and why. Do not rely exclusively on a change summary or
implementation report.

#### Step 3: Investigate Potential Defects

Investigate a suspected issue only far enough to establish whether it is
material and actionable.

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
- **Location:** file, symbol, or code range.
- **Evidence:** what demonstrates it.
- **Problem:** what is incorrect or risky.
- **Impact:** why it matters.
- **Reproduction or reasoning:** how to confirm it.
- **Recommendation:** a remediation direction.

Avoid vague comments such as "this could be better" without explaining a
material impact.

#### Step 6: Complete the Review

Summarize findings and the scope actually reviewed.

### 5.5 Reviewer Investigation Exit Criteria

Stop investigating a potential finding when:
- The behavior has been confirmed or reasonably ruled out.
- Its relationship to requirements or contracts is clear, and its impact and
  severity can be assessed.
- Evidence is sufficient to report an actionable conclusion.

Continue only when a material uncertainty prevents classification or a
reliable conclusion. Do not explore unrelated code to increase review coverage
artificially.

### 5.6 Review Completion Criteria

A review is complete when:
- The assigned change and relevant context have been examined.
- Material correctness and compatibility risks have been assessed.
- Findings are evidence-backed and actionable.
- Blocking and material findings have been reported.
- Remaining comments are non-blocking or out of scope.
- No material unresolved question prevents a reliable conclusion.

A review does not need to prove the absence of every hypothetical defect.

### 5.7 Avoid Review Loops

Do not repeat a review simply because another review might discover another
possible improvement.

After remediation, re-examine the affected code, verify the reported finding
has been addressed, check relevant adjacent behavior for regressions, and
reopen broader review only when new material evidence justifies it. A
localized correction does not require a full review cycle.

### 5.8 Reviewer Boundaries

The Reviewer should not:
- Implement fixes by default.
- Treat style preferences as blocking defects.
- Report hypothetical risks without a credible mechanism or impact.
- Expand scope without justification.
- Repeat completed review work without new evidence.
- Treat the absence of findings as proof that the system is defect-free.

### 5.9 Reviewer Deliverable

Report the scope reviewed, the overall review assessment, findings classified
by severity, evidence and affected locations, impact and remediation
suggestions, areas not reviewed or limitations, and whether review completion
criteria are satisfied. If no material findings are identified, state that
clearly and describe the scope actually reviewed.

## 6. Role Handoffs

Role handoffs must preserve evidence, ownership, and the current execution
state.

### 6.1 Developer → Tester

Provide implemented behavior, relevant changed files, requirements addressed,
important interfaces and assumptions, tests already executed, known
limitations, and expected behavior to verify. The Tester derives and executes
the required verification independently.

### 6.2 Developer → Reviewer

Provide objective and requirements, actual change summary, changed files and
relevant interfaces, important design decisions, known risks or limitations,
and validation already performed. The Reviewer inspects the actual diff
independently.

### 6.3 Tester or Reviewer → Developer

When a material issue is found, provide the specific finding, evidence and
location, impact and severity, and the expected remediation outcome. The
Developer addresses the finding within the assigned scope and reports the
resulting change.

### 6.4 Remediation → Verification

After remediation, identify which behavior changed, re-run tests relevant to
the finding, re-check affected contracts and regression-sensitive behavior,
and repeat review only for the affected scope or new material risks.

Verification must correspond to the actual remediated implementation.

## 7. Role Composition

Roles are independently assignable and composable. They are not a mandatory
three-worker pipeline.

- **Developer Only:** small, bounded, low-risk implementation. Developer
  implements and performs relevant validation.
- **Developer + Tester:** behavior needs explicit test coverage or regression
  verification. Tester independently checks implementation against expected
  behavior.
- **Developer + Reviewer:** design, compatibility, correctness, or security
  risks justify independent inspection. Reviewer evaluates the actual
  implementation and reports material findings.
- **Developer + Tester + Reviewer:** complex or high-risk work. Testing and
  review can run in parallel when both can independently inspect a stable
  implementation.
- **Tester and/or Reviewer Without Developer:** the assignment concerns an
  existing implementation, test coverage, or independent assessment. The role
  stays in scope and reports findings rather than taking ownership of
  unrelated implementation work.

## 8. Assignment and Reporting Contract

Each worker must understand the assignment before execution.

A complete assignment should specify label, role, objective, context, known
facts and evidence, open questions, scope, out-of-scope boundaries,
constraints, expected output, acceptance criteria, dependencies, ownership,
investigation exit criteria, and validation expectations.

If essential information is missing, identify it specifically. Do not
compensate for an unclear assignment by performing unbounded investigation.

Every final report must distinguish work completed, evidence obtained,
validation performed, findings or failures, remaining uncertainty, and
uncompleted work. Requirements are carried by the todo the worker takes, not
by the chat message. See section 13.

## 9. Definition of Success

Engineering work succeeds when the assigned objective is satisfied, changes
remain within scope, contracts and constraints are preserved, required
verification is supported by actual evidence, material risks and limitations
are communicated, the output can be evaluated by the Coordinator, and the work
is ready for integration or has clearly reported why it is not.

The goal is not maximum investigation, maximum code changes, maximum test
count, or maximum review comments.

**The goal is sufficient evidence, correct engineering decisions, focused
execution, and verifiable deliverables.**

## 10. Skill Availability and Execution

This Skill defines role procedures but does not guarantee automatic injection
into every worker's context. The Coordinator must ensure each worker receives
the instructions necessary for its assignment.

When Skill availability or inheritance is uncertain, include the essential role
procedure in the assignment, provide the relevant scope and acceptance
criteria, and do not assume a worker has read this document.

Workers must follow the actual runtime capabilities and tool restrictions of
the active Jcode version.

## 11. Coordinator Practice

Practice that makes the policy above work. It does not change the policy.

- **Give every parallel lane its own file set.** An ownership list is
  advisory, not a lock: two workers handed the same files collide, and a
  reviewer reading that diff watches it change under them. Lanes that must
  share a file run in sequence, or get separate files.
- **Run the independent verification once, at acceptance.** One full run
  after the workers are done is evidence.
- **Put an open product decision in front of the human before you delegate.**
  A worker cannot make that call for you. Ask once, up front, and write the
  answer into the brief.
- **An assignment names every surface the worker may touch.** Give it the
  files it may write, the commands it may run, and the surfaces it must not
  touch. A worker that meets a surface it was not given stops and reports. It
  does not explore, and it installs nothing into the host.
- **Name one test file per function in every brief.** The Developer owns the
  implementation smoke test, the Tester owns the requirement-clause file. The
  Tester's file cites the requirement each test covers; a requirement with no
  test is a reported coverage gap, never a silent pass.
- **Accept a worker's executed evidence as the evidence for that claim.**
  Re-run a check only when the files changed after that worker's run, and
  then run the independent verification once, at acceptance.
- **Never poll with sleeps or wait loops.** Use `swarm await_members`, which
  waits in the background and notifies you when a worker finishes.
- **Keep one ledger row per round.** The `todo` list is the ledger: the lanes
  spawned, what each owns, the verdict, and where the evidence came from.
- **Bound your own read phase.** A brief bounds a worker; nothing bounds the
  coordinator's own reading, and that is where the same failure appears: of
  334 sessions, 78% of sufficiency declarations were in root, primary
  sessions, and one ran 774 tool calls after its last file write without
  implementing the change. Before your own first edit, state the finite set
  of things you need to know and read only those. A named section, category,
  or file is the scope, not a licence to read the whole specification. A file
  read in full is not read in full again. The soft default is 60 tool calls
  before the first edit, and needing more requires saying why. Once you have
  the shape or the design, your next call is the implementation, the
  validation, the plan, or the report. See section 2.3.3 and section 2.3.4.
- **Bound your own verification phase.** The verification phase has a target
  set too, the acceptance criteria, one check each, and it ends when they are
  checked, when a check cannot fail, when the remaining question would change
  the delivered result, or when the budget is spent. See section 2.3.5.

### 11.1 Stopping a Lane That Overran Its Brief

A worker that has met its completion criteria and keeps searching will not
stop, so the coordinator enforces the bound. The escalation order is fixed:
message first, stop second.

1. **Check the lane before acting.** `swarm list` shows each member's status,
   last activity age, and whether it is stalled. A `running` member with a
   fresh activity age is working; a member whose activity age keeps growing
   while its targets are already covered is expanding scope.
2. **Message the lane.** Ask it to report what it has and mark the rest
   unverified. Name the requirement it still owes, and say it must not open
   new targets.
3. **Do not repeat the message.** A worker that ignored a request to wrap up
   has shown that it will not honour a soft instruction. Repeating it costs a
   round trip and buys nothing.
4. **Stop the lane.** `swarm stop` terminates the worker. The coordinator
   owns its own spawned workers, so this works without `force`. Use `force`
   only for a session this coordinator did not spawn.
5. **Record the loss.** A stopped lane is a partial result. Write into the
   todo row which targets were completed, which were left unverified, and
   that the remainder is not covered. A stopped lane is never reported as a
   finished one.

`swarm stop` persists the session as closed and the transcript on disk
keeps what the worker had already written, so a stopped lane is not a total
loss. The unwritten remainder is still lost, which is why stopping is the last
step, not the first.

`swarm summary` reports the recent tool calls of a lane. Use `swarm list` and
the worker's own report for the result.

## 12. Requirement Matching

This section binds the Reviewer, and any worker asked to report against a
requirement. For every requirement in your assignment, report one line: the
requirement, a verdict, and the evidence that supports it.
- `met`: the evidence shows the requirement is satisfied.
- `not met`: the evidence shows it is not.
- `not demonstrated`: no evidence either way.
- `not in scope`: the requirement was outside this assignment.

A verdict without evidence is `not demonstrated`, never `met`. The Tester's
`passed` / `failed` / `blocked` / `not-tested` map onto `met` / `not met` /
`not demonstrated` / `not demonstrated`.

Two checks, not one: does the check discriminate, meaning would it fail if
the behaviour were wrong, and is the behaviour the one the requirement asked
for.

If your assignment carried no requirements, say so and report it as a gap. Do
not invent requirements.

This section adds to the review completion gate: a review is complete only
when every requirement carries a verdict and its evidence, or is reported as
`not demonstrated`. A `not demonstrated` requirement blocks acceptance until
it is checked or waived with a recorded reason.

## 13. Requirement Handover

Jcode has no separate requirements file. The requirement lives in the todo
the worker takes, and the todo's `details` field is the only part handed to
that worker.

- The Coordinator writes the todo before dispatching, with one todo per
  requirement, or a todo whose `details` carries one requirement block per
  requirement.
- The `details` field carries the requirement, the observable check that
  proves it, and its source:

  ```
  <the requirement>
      check: <what proves it>
      source: <the assignment | path:line | the behaviour that must not change>
  ```

- The brief names the todos it covers. It does not repeat the requirement
  text: a copy in a chat message is what drifts.
- No worker authors requirements, and no worker keeps a copy of the
  requirement text in its own words.
- The todo list is where the requirement text comes from. If the brief
  describes a requirement differently, or names a requirement the todo does
  not define, the worker REPORTS THE CONFLICT and stops that requirement. It
  does not pick a winner and it does not invent the missing one. The
  requirement is `not demonstrated` until the conflict is resolved, and the
  other requirements are unaffected.
- A worker cites the requirement as `<todo id>`. A verdict without that
  citation is `not demonstrated`.
- A requirement whose todo cannot be read is `not demonstrated`, never `met`.
- A todo is only authoritative over the behaviour it names. The Coordinator
  reconciles it with the repository's existing tests before it is written. A
  requirement that contradicts an existing test is a conflict in its own
  right, and is reported like any other.

## 14. Native Verification Surfaces

Jcode verifies independently without a worker. Prefer these over spawning a
critic.

- **`/autoreview`** reviews the session's actual changes (`git diff --stat`,
  `git diff --name-only`, focused file reads) and reports concrete findings
  with severity and file paths. It takes `on`, `off`, `status`, and `now`;
  `now` launches the reviewer on demand.
- **`/autojudge`** is a completion manager: it decides whether the parent
  agent should keep going and tells it exactly what to do next. It only says
  stop when the intent has been carried through. It takes the same four
  arguments. `now` launches the judge on demand.
- **`/review` and `/judge`** are the one-shot forms. They launch a headed
  review or judge session on demand, without relying on the end-of-turn
  trigger.

All of these are client-side TUI commands. A worker or a headless agent cannot
type them into the user's composer, and no tool exposes them to the model. An
agent that needs independent verification asks for it in its report.

### 14.1 The end-of-turn trigger is mode-dependent

`[autoreview] enabled` and `[autojudge] enabled` are the *default* for the
session flag, nothing more. The automatic end-of-turn hook sits at the end of
the TUI's local turn path and bails out in remote mode, which the product TUI
starts in, so the flag is set but no reviewer or judge is spawned at end of
turn. The local turn path is not dead code: `jcode ambient run-visible` builds
a local, non-remote app, so the trigger does fire there.

Consequences for a Reviewer:
- `/autoreview status` reporting "enabled" is not evidence that a review ran.
  It reports the flag.
- Do not treat "the flag was on" as independent verification. If the task
  needs a review, request it with `/autoreview now` or `/review`, or read the
  diff and run the tests directly.
- Headless runs (`jcode run`, swarm workers, headless ambient cycles) have no
  TUI turn path at all, so the automatic trigger cannot fire there either.

The one-shot children are created with both flags disabled, so a review or
judge does not spawn a review or judge of its own.

These review the actual repo state, which is why they substitute for a
Reviewer worker rather than complement it. The Reviewer section above still
describes what their output should contain, and the finding classification
still applies to their results.

The two paths are not interchangeable. The native surfaces inspect the
coordinator's working tree. If workers wrote into isolated worktrees, their
changes are not in that tree and the native reviewer will not see them:
verify per lane, or integrate first. Use a Reviewer worker when the thing to
review is not in the coordinator's tree, or when the review needs a specific
lens you want stated in the brief.
