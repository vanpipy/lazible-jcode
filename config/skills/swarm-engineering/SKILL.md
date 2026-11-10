---
name: swarm-engineering
description: Engineering execution methods for Jcode Swarm workers. Defines bounded investigation, Developer implementation, Tester verification, Reviewer code review, role boundaries, handoffs, and evidence-based completion.
---

# Swarm Engineering Skill

## 1. Purpose

This Skill defines how engineering workers execute assigned responsibilities.

It provides practical workflows and deliverable standards for:
- Developer: implementation.
- Tester: test design and verification.
- Reviewer: independent code review.

It also defines common engineering principles and role handoffs.

This Skill does not replace:
- Global execution policies in `prompt-overlay.md`, including the swarm orchestration policy in its section 12.
- The `swarm` tool description in `swarm-prompt.md`, which carries model routing and the brief requirements every worker must be given.

The assigned objective and scope take precedence over generic workflow preferences, subject to higher-priority instructions and constraints.

## 2. Common Engineering Principles

All roles follow the global `Goal-Directed Execution Principle`.

The purpose of engineering work is to advance the assigned objective, not to maximize investigation, code changes, tests, or review comments.

### 2.1 Work Within the Assignment

Before starting, identify assigned role, objective, scope and out-of-scope boundaries, relevant context and established evidence, constraints, expected deliverables, acceptance criteria, dependencies, and validation expectations.

Do not silently expand the assignment.

If the objective or constraints are materially ambiguous, identify the specific ambiguity and seek clarification or report it to the Coordinator.

### 2.2 Evidence Before Conclusions

Base conclusions on relevant evidence.

Distinguish:
- Observed facts.
- Reproduced behavior.
- Test results.
- Reasonable inference.
- Unverified assumptions.

When reporting a defect or risk, provide enough evidence for another engineer to understand and evaluate it.

### 2.3 Bounded Investigation

Every substantial investigation should answer a concrete question.

Before investigating, establish:
1. What needs to be determined?
2. Why does it matter?
3. What evidence is sufficient?
4. What decision or action follows?

Stop when investigation exit criteria are met.

Continue only when an unresolved question could materially affect correctness, compatibility, safety, implementation, or acceptance.

Do not inspect unrelated modules simply because they may provide additional context.

### 2.4 Phase Progression

Use a proportionate engineering lifecycle:

Understand → Investigate → Design → Execute → Validate → Report

Not every task requires a separate document or explicit phase.

Move forward once sufficient evidence supports the next action. Return to an earlier phase only when new evidence justifies it.

### 2.5 Honest Validation

Report only checks that were actually performed.

For every validation result, identify what was checked, how it was checked, whether it passed or failed, and relevant limitations.

Do not claim that the entire system is correct based on a narrow test.

### 2.6 Preserve Existing Work

Respect existing project structure, interfaces, conventions, and user changes.

Avoid unrelated modifications. Do not overwrite or revert changes outside the assignment.

## 2.7 Code Health and Change Risk Assessment

This procedure provides reusable engineering methods for assessing the
maintainability of relevant code and the risk of a proposed change. It
supports the Coordinator's policy in `prompt-overlay.md`; it does not replace
the assignment's requirements or authorize unrelated refactoring.

### 2.7.1 Keep the Assessments Separate

- **Code Health** describes the maintainability and structural condition of
  the relevant existing code.
- **Change Risk** describes the risk introduced by the specific proposed
  change.

Do not infer one directly from the other. A healthy, central interface may
be high-risk to modify. An unhealthy but isolated module may be relatively
low-risk for a narrow change.

### 2.7.2 Scope the Assessment

Assess the target files and only those callers, consumers, tests, and
dependencies that could materially affect the assigned objective.

Consider these dimensions when relevant:

| Dimension | Questions and evidence |
| --- | --- |
| Maintainability | Is the code understandable and cohesive? Are complexity, nesting, duplication, or code smells material to this change? |
| Dependency structure | Which modules depend on the target? Are dependency direction, coupling, or circular dependencies relevant? |
| Behavioral safety | What tests and behavioral contracts protect the affected behavior? What coverage or regression gaps are known? |
| Change surface | Which interfaces, shared state, side effects, and downstream consumers may be affected? |

Do not inspect the entire repository merely to complete this checklist. Mark
irrelevant dimensions as not applicable and unavailable evidence as unknown.

### 2.7.3 Collect Evidence

Prefer evidence available in the repository and its established toolchain:

- Actual source code, interfaces, and dependency relationships.
- Existing tests and reproducible test results.
- Coverage reports, when available and relevant.
- Static analysis, linting, type checking, and complexity tools.
- Git diff and relevant repository history.
- Documented contracts and established project conventions.

For each material finding, identify its source. Distinguish measured results,
observed facts, inferences, and assumptions. Do not fabricate metrics or
combine unrelated measurements into an uncalibrated score.

A CodeScene CodeHealth score may be reported if the project actually uses
CodeScene. Its thresholds are tool- and context-specific; do not treat CH = 9
as a universal rule.

### 2.7.4 Assess Change Risk

Consider the specific change's:

- Affected module count and dependency reach.
- Public interface or compatibility impact.
- Shared mutable state and side-effect surface.
- Behavioral sensitivity and failure consequences.
- Test and regression protection.
- Unresolved uncertainty about existing behavior.

Use Low, Medium, or High only when that classification helps the decision.
State the evidence and reasons. Do not invent a numerical risk formula.

### 2.7.5 Adapt the Work

The assessment may inform:

- Whether work should be direct, delegated, parallel, or sequential.
- Worker boundaries and file ownership.
- Whether an investigation or behavioral baseline is needed first.
- The required test depth and review method.
- Whether a human decision is needed before implementation.

High risk does not automatically prohibit a change. It calls for proportionate
guardrails. Do not create a separate assessment worker unless the assessment
itself is a bounded deliverable that materially unblocks the task.

### 2.7.6 Compare Before and After

For significant changes, compare relevant evidence with the baseline:

- Tests and observed behavior.
- Complexity, duplication, and code-smell findings.
- Dependencies, interfaces, and affected consumers.
- Shared state and side-effect surface.
- Relevant type-checking, linting, or static-analysis results.

Report improvements, regressions, and unknowns separately. A successful test
run does not prove maintainability improved; a cleaner static-analysis report
does not prove behavior was preserved.

### 2.7.7 Role Responsibilities

- **Coordinator:** Owns repository- and task-level assessment, decides how
  findings affect delegation and execution, and makes the final integrated
  comparison.
- **Developer:** Understands local health constraints, minimizes unnecessary
  change surface, avoids introducing unjustified complexity or coupling, and
  reports relevant structural changes.
- **Tester:** Establishes behavioral baselines and verifies required behavior
  and regressions. Test coverage is evidence of test presence, not proof that
  all behavior is correct.
- **Reviewer:** Inspects the actual change for material maintainability,
  dependency, interface, and side-effect regressions within the assigned
  scope.

Workers report evidence from their own scope. The Coordinator consolidates
those reports; workers do not independently claim a repository-wide health
score.

## 3. Developer Role

### 3.1 Mission

Implement the assigned behavior or change correctly and with the smallest coherent modification.

The Developer owns implementation quality within the assigned scope. The Developer should preserve relevant Code Health constraints, avoid unnecessary complexity or coupling, and report material structural changes or regressions.

### 3.2 Workflow

#### Step 1: Understand
Establish required behavior, relevant existing behavior, interfaces and dependencies, constraints, and acceptance criteria. Identify what must change and what must remain unchanged.

#### Step 2: Investigate
Inspect only relevant implementation, contracts, and tests.

Determine where the behavior is implemented, which components or interfaces are affected, which existing conventions must be preserved, and what assumptions need verification.

#### Step 3: Design
Choose a proportionate implementation approach.

Consider correctness, compatibility, error handling, existing abstractions, relevant edge cases, and testability.

Avoid unnecessary architecture changes or speculative generalization.

#### Step 4: Implement
Make focused changes. Preserve unrelated behavior and minimize the change surface.

Do not modify unrelated files merely to improve consistency unless required by the objective.

#### Step 5: Validate
Run relevant checks, such as targeted tests, relevant regression tests, type checks, linting and formatting, build checks, and reproducible runtime scenarios.

Investigate failures that affect the assigned objective. Do not hide failures or claim that unexecuted checks passed.

#### Step 6: Report
Provide a concise implementation report.

### 3.3 Developer Investigation Exit Criteria

Stop investigating and proceed when:
- The relevant implementation location is identified.
- The behavior and relevant contracts are sufficiently understood.
- The constraints and dependencies are known.
- A sound implementation approach can be selected.
- Remaining unknowns do not materially change that approach.

If a material unknown remains, investigate that specific question rather than expanding the entire exploration.

### 3.4 Developer Boundaries

The Developer should not:
- Expand the task without authorization.
- Replace unrelated architecture or interfaces.
- Claim that independent review has occurred.
- Treat implementation completion as overall task acceptance.
- Conceal failed validation.
- Continue redesigning after a sufficient implementation approach has been established.

### 3.5 Developer Deliverable

Report:
1. Objective addressed.
2. Files or components changed.
3. Important implementation decisions.
4. Relevant behavior and contracts affected.
5. Tests and checks executed.
6. Actual validation results.
7. Remaining limitations or risks.

Provide concrete file or symbol references where useful.

## 4. Tester Role

### 4.1 Mission

Establish whether the assigned behavior satisfies its observable requirements.

The Tester owns test design and verification within the assigned scope. The Tester contributes behavioral-safety evidence, including relevant baseline, regression, and coverage limitations, rather than assigning a repository-wide Code Health score.

The Tester should independently assess behavior rather than merely confirm the Developer's description.

### 4.2 Default Boundary

The Tester primarily designs and executes tests.

By default, the Tester does not modify production code.

If test code must be added or modified, do so within the assignment's scope and ownership.

If production implementation changes are needed, report the evidence and return the finding to the Coordinator or Developer.

### 4.3 Workflow

#### Step 1: Understand Requirements

Identify expected behavior, relevant acceptance criteria, inputs and outputs, preconditions and postconditions, error behavior, relevant edge cases, and regression-sensitive behavior.

Translate requirements into observable test conditions.

Do not derive all tests solely from the implementation. Requirements and expected behavior should remain the basis of verification.

#### Step 2: Investigate Test Context

Inspect relevant existing tests, test framework and fixtures, public interfaces, runtime behavior, test environment, and existing coverage.

Determine which tests already establish required behavior and which gaps remain.

#### Step 3: Design Tests

Choose tests proportionate to risk.

Consider normal cases, boundary cases, invalid inputs, failure paths, state transitions, relevant regressions, and interface/integration behavior.

Avoid generating large numbers of redundant tests. Each test should establish a meaningful observable condition.

#### Step 4: Execute Tests

Run the most relevant tests first. Expand to broader regression or integration checks when scope and risk justify them.

Record actual results.

Distinguish test failures caused by implementation from failures caused by environment, test setup, or unrelated existing defects.

#### Step 5: Diagnose Failures

For each relevant failure, identify the failing test or scenario, expected behavior, actual behavior, reproduction steps, relevant output or evidence, likely cause with confidence, and whether the failure is attributable to the assigned change.

Do not modify production code to make a failing test pass unless the assignment explicitly authorizes that work.

#### Step 6: Report

Summarize verification coverage, results, and unresolved risks.

### 4.4 Tester Investigation Exit Criteria

Stop test-context investigation when:
- Relevant requirements are sufficiently understood.
- Existing test infrastructure is identified.
- Relevant existing coverage is understood.
- Missing behavioral conditions can be defined.
- A concrete test plan can be executed.

Continue only when an unresolved question materially affects expected behavior, test validity, or failure interpretation.

### 4.5 Tester Verification Exit Criteria

Verification is complete when:
- Required test conditions have been covered to the agreed extent.
- Relevant tests have been executed.
- Results have been assessed.
- Failures are reproducible or their limitations are documented.
- Material coverage gaps are reported.
- Evidence is sufficient for the Coordinator to evaluate acceptance.

Do not continue adding redundant tests after required behavior has been adequately verified.

### 4.6 Tester Boundaries

The Tester should not:
- Treat passing tests as proof of untested behavior.
- Assume implementation correctness from code structure alone.
- Modify production implementation by default.
- Hide environmental or test infrastructure problems.
- Expand test scope indefinitely.
- Report speculative failures as confirmed defects.

### 4.7 Tester Deliverable

Report:
1. Requirements or behaviors tested.
2. Test scenarios and relevant coverage.
3. Tests executed.
4. Actual results.
5. Failures and reproduction evidence.
6. Coverage gaps.
7. Environment limitations.
8. Overall verification assessment.

Clearly distinguish passed, failed, blocked, and not-tested conditions.

## 5. Reviewer Role

### 5.1 Mission

Independently assess the assigned change for material defects and risks.

The Reviewer owns the quality of the review within the assigned scope.

The review must focus on the actual implementation and its relevant context, not only the Developer's explanation.

### 5.2 Default Boundary

The Reviewer identifies and reports findings.

By default, the Reviewer does not implement fixes.

The Coordinator decides whether findings should be addressed, deferred, or explicitly accepted.

### 5.3 Review Scope

Focus on the actual diff and relevant surrounding code.

Review for requirement violations, incorrect behavior, logic errors, interface or contract violations, compatibility issues, regressions, error-handling problems, security or safety concerns, and significant design defects affecting correctness or maintainability. Where relevant to the assignment, inspect whether the change introduces unjustified complexity, coupling, duplication, dependency problems, or a broader side-effect surface.

Do not expand into unrelated repository-wide review.

### 5.4 Workflow

#### Step 1: Understand the Change
Establish intended behavior, relevant requirements, changed files and components, important interfaces, acceptance criteria, and explicit constraints.

#### Step 2: Inspect the Actual Diff
Review what changed and why. Identify relevant interactions with existing code.

Do not rely exclusively on a change summary or implementation report.

#### Step 3: Investigate Potential Defects
For each plausible issue, determine:
- Is the behavior actually possible?
- Is there evidence in the implementation or execution path?
- Does it violate a requirement or contract?
- What is the impact?
- Is it within the assigned scope?

Investigate a suspected issue only far enough to establish whether it is material and actionable.

#### Step 4: Classify Findings

Use these categories:
- **Blocking:** Prevents acceptance or creates a serious correctness or safety issue.
- **Material:** Significant defect or risk that should be resolved or explicitly accepted.
- **Non-blocking:** Improvement that does not prevent acceptance.
- **Out of scope:** Unrelated observation.

Do not inflate severity.

#### Step 5: Report Actionable Findings

Every material finding should contain:
- **Location:** Relevant file, symbol, or code range.
- **Evidence:** What demonstrates the issue.
- **Problem:** What is incorrect or risky.
- **Impact:** Why it matters.
- **Reproduction or reasoning:** How the issue can be confirmed.
- **Recommendation:** A practical remediation direction.

Avoid vague comments such as "this could be better" without explaining a material impact.

#### Step 6: Complete the Review
Summarize findings and the scope actually reviewed.

### 5.5 Reviewer Investigation Exit Criteria

Stop investigating a potential finding when:
- The behavior has been confirmed or reasonably ruled out.
- Its relationship to requirements or contracts is clear.
- Its impact and severity can be assessed.
- Evidence is sufficient to report an actionable conclusion.

Continue only when a material uncertainty prevents classification or a reliable conclusion.

Do not explore unrelated code to increase review coverage artificially.

### 5.6 Review Completion Criteria

A review is complete when:
- The assigned change and relevant context have been examined.
- Material correctness and compatibility risks have been assessed.
- Findings are evidence-backed and actionable.
- Blocking and material findings have been reported.
- Remaining comments are non-blocking or out of scope.
- No material unresolved question prevents a reliable review conclusion.

A review does not need to prove the absence of every hypothetical defect.

### 5.7 Avoid Review Loops

Do not repeat a review simply because another review might discover another possible improvement.

After remediation:
- Re-examine the affected code.
- Verify the reported finding has been addressed.
- Check relevant adjacent behavior for regressions.
- Reopen broader review only when new material evidence justifies it.

Do not require a full review cycle for every localized correction.

### 5.8 Reviewer Boundaries

The Reviewer should not:
- Implement fixes by default.
- Treat style preferences as blocking defects.
- Report hypothetical risks without a credible mechanism or impact.
- Expand scope without justification.
- Repeat completed review work without new evidence.
- Treat the absence of findings as proof that the entire system is defect-free.

### 5.9 Reviewer Deliverable

Report:
1. Scope reviewed.
2. Overall review assessment.
3. Findings, classified by severity.
4. Evidence and affected locations.
5. Impact and remediation suggestions.
6. Areas not reviewed or limitations.
7. Whether review completion criteria are satisfied.

If no material findings are identified, state that clearly and describe the scope actually reviewed.

## 6. Role Handoffs

Role handoffs must preserve evidence, ownership, and the current execution state.

### 6.1 Developer → Tester

Provide implemented behavior, relevant changed files, requirements addressed, important interfaces and assumptions, tests already executed, known limitations, and expected behavior to verify.

The Tester should independently derive and execute required verification.

### 6.2 Developer → Reviewer

Provide objective and requirements, actual change summary, changed files and relevant interfaces, important design decisions, known risks or limitations, and validation already performed.

The Reviewer must inspect the actual diff independently.

### 6.3 Tester or Reviewer → Developer

When a material issue is found, provide the specific finding, evidence and location, expected versus actual behavior where applicable, impact and severity, reproduction or reasoning, and expected remediation outcome.

The Developer should address the finding within the assigned scope and report the resulting change.

### 6.4 Remediation → Verification

After remediation, identify which behavior changed, re-run tests relevant to the finding, re-check affected contracts and regression-sensitive behavior, and repeat review only for the affected scope or new material risks.

Verification must correspond to the actual remediated implementation.

## 7. Role Composition

Roles are independently assignable and composable. They are not a mandatory three-worker pipeline.

- **Developer Only:** Appropriate when implementation is small, bounded, and low-risk. Developer implements and performs relevant validation.
- **Developer + Tester:** Appropriate when behavior needs explicit test coverage or regression verification. Tester independently checks implementation against expected behavior.
- **Developer + Reviewer:** Appropriate when design, compatibility, correctness, or security risks justify independent inspection. Reviewer evaluates actual implementation and reports material findings.
- **Developer + Tester + Reviewer:** Appropriate for complex or high-risk work. Testing and review can run in parallel when both can independently inspect a stable implementation.
- **Tester and/or Reviewer Without Developer:** Appropriate when the assignment concerns an existing implementation, test coverage, or independent assessment. The role remains within scope and reports findings rather than silently taking ownership of unrelated implementation work.

## 8. Assignment and Reporting Contract

Each worker must understand the assignment before execution.

A complete assignment should specify label, role, objective, context, known facts and evidence, open questions, scope, out-of-scope boundaries, constraints, expected output, acceptance criteria, dependencies, ownership, investigation exit criteria, and validation expectations.

If essential information is missing, identify it specifically. Do not compensate for an unclear assignment by performing unbounded investigation.

Every final report must distinguish work completed, evidence obtained, validation performed, findings or failures, remaining uncertainty, and uncompleted work.

Requirements are carried by the todo the worker takes, not by the chat message. See section 13.

## 9. Definition of Success

Engineering work succeeds when:
- The assigned objective is satisfied.
- Changes remain within scope.
- Relevant contracts and constraints are preserved.
- Required verification is supported by actual evidence.
- Material risks and limitations are communicated.
- The output can be evaluated by the Coordinator.
- The work is ready for integration or has clearly reported why it is not.

The goal is not maximum investigation, maximum code changes, maximum test count, or maximum review comments.

**The goal is sufficient evidence, correct engineering decisions, focused execution, and verifiable deliverables.**

## 10. Skill Availability and Execution

This Skill defines role procedures but does not guarantee automatic injection into every worker's context.

The Coordinator must ensure each worker receives the instructions necessary for its assignment.

When Skill availability or inheritance is uncertain:
- Include the essential role procedure in the assignment.
- Provide the relevant scope and acceptance criteria.
- Do not assume that a worker has read this document.

Workers must follow the actual runtime capabilities and tool restrictions of the active Jcode version.

## 11. Coordinator Practice

Practice that makes the policy above work. It does not change the policy.

- **Give every parallel lane its own file set.** A lane's ownership list is advisory, not a lock. Two workers handed the same files collide, and a reviewer reading that diff watches it change under them. Lanes that must share a file run one after the other, or they get separate files.
- **Run the independent verification once, at acceptance.** One full run after the workers are done is evidence. Three overlapping runs are cost without evidence. Let each worker's own report carry its own narrow checks.
- **Put an open product decision in front of the human before you delegate.** If the requirement leaves a choice open — what exit code a command returns, what counts as failure, which of two behaviours is correct — a worker cannot make that call for you. Ask once, up front, and write the answer into the brief so no round is spent on it later.
- **An assignment names every surface the worker may touch.** Give it the files it may write, the commands it may run, and the surfaces it must not touch. A worker that meets a surface it was not given stops and reports. It does not explore, and it does not install anything into the host.
- **Name one test file per function in every brief.** The Developer owns the implementation smoke test. The Tester owns the requirement-clause file. Two workers never author tests for the same clause, because that duplication is the defect the Tester is supposed to find in the implementation, not in another test file. The Tester's requirement-clause file cites the requirement each test covers, and a requirement with no test is a reported coverage gap, never a silent pass.
- **Accept a worker's executed evidence as the evidence for that claim.** Re-run a check yourself only when the files changed after that worker's run, or when two reports disagree — and then run the independent verification once, at acceptance.
- **Never poll with sleeps or wait loops.** Use `swarm await_members`, which waits in the background and notifies you when a worker finishes. Do other work, or wait for the completion notice.
- **Keep one ledger row per round.** The `todo` list is the ledger: the lanes spawned, what each owns, the verdict, and where the evidence came from. Write it once, in order.

## 12. Requirement Matching

This section binds the Reviewer, and any worker asked to report against a requirement.

For every requirement in your assignment, report one line: the requirement, a verdict, and the evidence that supports it.

- `met` — the evidence shows the requirement is satisfied.
- `not met` — the evidence shows it is not.
- `not demonstrated` — no evidence either way.
- `not in scope` — the requirement was outside this assignment.

A verdict without evidence is `not demonstrated`, never `met`. The Tester's `passed` / `failed` / `blocked` / `not-tested` map onto `met` / `not met` / `not demonstrated` / `not demonstrated`.

Two checks, not one: does the check discriminate — would it fail if the behaviour were wrong — and is the behaviour the one the requirement asked for. A review that runs only one of them has not matched the requirement.

If your assignment carried no requirements, say so and report it as a gap. Do not invent requirements.

This section adds to the review completion gate: a review is complete only when every requirement in the assignment carries a verdict and its evidence, or is reported as `not demonstrated`. A `not demonstrated` requirement blocks acceptance until it is checked, or until the Coordinator records an explicit waiver with a reason in the todo row.

## 13. Requirement Handover

Jcode has no separate requirements file. The requirement lives in the todo the worker takes, and the todo's `details` field is the only part handed to that worker.

- The Coordinator writes the todo before dispatching, with one todo per requirement, or a todo whose `details` carries one requirement block per requirement.
- The `details` field of a todo carries the requirement, the observable check that proves it, and its source:

  ```
  <the requirement>
      check: <what proves it>
      source: <the assignment | path:line | the behaviour that must not change>
  ```

- The brief names the todos it covers. It does not repeat the requirement text: a copy in a chat message is what drifts.
- No worker authors requirements, and no worker keeps a copy of the requirement text in its own words.
- The todo list is where the requirement text comes from. If the brief describes a requirement differently, or names a requirement the todo does not define, the worker REPORTS THE CONFLICT and stops that requirement. It does not pick a winner and it does not invent the missing one. The requirement is `not demonstrated` until the conflict is resolved; the other requirements are unaffected.
- A worker cites the requirement as `<todo id>`. A verdict without that citation is `not demonstrated`.
- A requirement whose todo cannot be read is `not demonstrated`, never `met`.
- A todo is only authoritative over the behaviour it names. Before it is written, the Coordinator reconciles it with the repository's existing tests; a requirement that contradicts an existing test is a conflict in its own right, and it is reported like any other.

## 14. Native Verification Surfaces

Jcode verifies independently without a worker. Prefer these over spawning a
critic.

- **`/autoreview`** reviews the session's actual changes. It inspects the repo
  with `git diff --stat`, `git diff --name-only`, and focused file reads, and
  reports concrete findings with severity and file paths. It takes `on`, `off`,
  `status`, and `now`. `now` launches the reviewer on demand. Enabled per
  session with `/autoreview on`, or globally with
  `[autoreview] enabled = true` in `config.toml`. Its model is
  `[autoreview] model`. It is a TUI command, so it is typed by the user in
  the composer, not called by an agent.
- **`/autojudge`** is a completion manager. It decides whether the parent agent
  should keep going and tells it exactly what to do next. It only says stop
  when the intent has been carried through. It takes the same four arguments.
  `now` launches the judge on demand. Enabled with `/autojudge on` or
  `[autojudge] enabled = true`. Its model is `[autojudge] model`.
- **`/review` and `/judge`** are the one-shot forms. They launch a headed
  review or judge session on demand, without relying on the end-of-turn trigger.

All of these are client-side TUI commands. A worker or a headless agent cannot
type them into the user's composer, and no tool exposes them to the model. An
agent that needs independent verification asks for it in its report, and the
user runs the command.

### 14.1 The end-of-turn trigger is mode-dependent

`[autoreview] enabled` and `[autojudge] enabled` are the *default* for the
session flag, nothing more. On v0.99.1 the automatic end-of-turn hook sits at
the end of the TUI's local turn path, and that hook bails out when the app is
in remote mode. The product TUI starts in remote mode, so in normal use the
flag is set and reported but no reviewer or judge is spawned at end of turn.

The local turn path is not dead code, though. `jcode ambient run-visible`
builds a local, non-remote app, so the end-of-turn trigger does fire there. The
ambient runner spawns that command when `[ambient] visible = true`. The repo
config sets `visible = false`, so ambient cycles run headless and stay outside
it.

Consequences for a Reviewer:

- `/autoreview status` reporting "enabled" is not evidence that a review ran.
  It reports the flag.
- Do not treat "the flag was on" as independent verification. If the task
  needs a review, request it with `/autoreview now` or `/review`, or read the
  diff and run the tests directly.
- Headless runs (`jcode run`, swarm workers, headless ambient cycles) have no
  TUI turn path at all, so the automatic trigger cannot fire there either.
- `/autoreview now` and `/autojudge now` work in the TUI, in both remote and
  local mode. They are the reliable way to get a review, and they are typed by
  the user, not by an agent.

The one-shot children are created with both flags disabled, so a review or
judge does not spawn a review or judge of its own.

These review the actual repo state, which is why they substitute for a Reviewer
worker rather than complement it. The Reviewer section above still describes
what their output should contain, and the finding classification still applies
to their results.

The two paths are not interchangeable. The native surfaces inspect the
coordinator's working tree. If workers wrote into isolated worktrees, their
changes are not in that tree and the native reviewer will not see them: verify
per lane, or integrate first. A Reviewer worker, by contrast, receives the
shared plan and its scoped instructions, and can be given a worktree scope or a
different working directory. Use a Reviewer worker when the thing to review is
not in the coordinator's tree, or when the review needs a specific lens you
want stated in the brief.

A worker whose only job is to critique is a poor use of a worker when the
changes are in the coordinator's tree. It has the same tool description and the
same skill, but it costs a lane, a slot, and a round trip for output the host
can produce faster and against the real diff.
