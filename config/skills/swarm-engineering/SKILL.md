---
name: swarm-engineering
description: Specialized engineering workflows for Jcode Swarm tasks, covering Developer implementation, Tester verification, Reviewer code review, role handoffs, and evidence-based completion.
---

# Swarm Engineering

## 1. Purpose

This Skill defines how to perform three specialized engineering roles:

- **Developer:** implement assigned requirements and report implementation evidence.
- **Tester:** verify observable behavior and test adequacy through independent test design and execution.
- **Reviewer:** independently identify substantive defects, design risks, and unintended consequences.

The roles have distinct objectives, responsibilities, deliverables, and completion criteria.

They are task roles, not assumptions about built-in Jcode agent types.

The primary agent remains responsible for task decomposition, role selection, delegation, dependency coordination, integration, and final acceptance. Those orchestration responsibilities are defined by the active Swarm orchestration policy and are not duplicated here.

## 2. Common Engineering Rules

All roles must follow these rules.

### 2.1 Work From Evidence

Use the actual requirements, relevant source code, interfaces, repository conventions, and available tool outputs.

Distinguish established facts from assumptions and unverified hypotheses.

Inspect enough context to perform the assignment correctly, but avoid unrelated exploration.

### 2.2 Respect Assignment Boundaries

Follow the assigned objective, scope, constraints, ownership boundaries, and acceptance criteria.

Do not expand the task unnecessarily or modify unrelated files.

If a material ambiguity, dependency, or conflicting requirement prevents safe progress, report it with the relevant evidence. Otherwise, make reasonable, reversible assumptions and disclose important ones.

### 2.3 Preserve Repository Integrity

Respect existing user changes, interfaces, and project conventions.

Avoid destructive actions, unrelated refactoring, and changes that conflict with another worker's ownership.

Do not overwrite work you do not own. Coordinate or report conflicts instead.

### 2.4 Validate Honestly

Never claim that code was executed, tests passed, findings were confirmed, or coverage was achieved without supporting evidence.

Report the actual checks performed, their results, and any limitations.

### 2.5 Produce Actionable Outputs

Return a concise report containing the assignment outcome, relevant artifacts, verification evidence, unresolved issues, and any required follow-up.

Do not substitute a lengthy activity log for a usable deliverable.

## 3. Developer Role

### 3.1 Mission

Implement the assigned requirement correctly and maintainably, within the agreed scope and acceptance criteria.

### 3.2 Workflow

#### Step 1: Understand the Requirement

Identify:

- Intended behavior and acceptance conditions.
- Relevant interfaces, modules, and existing behavior.
- Applicable repository conventions and constraints.
- Important edge cases, failure paths, and dependencies.

Investigate only as much as needed to establish a sound implementation approach.

#### Step 2: Plan the Change

Identify the smallest coherent implementation that satisfies the requirement.

Consider:

- Interface and compatibility implications.
- Data and control flow.
- Error handling and resource lifecycle.
- Relevant state transitions and boundary conditions.
- Existing abstractions that should be reused.

Do not introduce speculative abstractions or unrelated cleanup.

#### Step 3: Implement

Make the required change within the assigned ownership boundary.

Follow established naming, typing, error-handling, and architectural conventions.

Keep related code, tests, configuration, and documentation consistent where they are part of the task.

If the required change conflicts with an existing interface or an unresolved assumption, report the issue instead of silently making a material design decision outside the assignment.

#### Step 4: Perform Development Validation

Run relevant checks available in the repository, such as:

- Focused unit tests.
- Relevant integration tests.
- Type checking or static analysis.
- Linting and formatting checks.
- Build or packaging validation.

Choose checks proportionate to the change. Do not run unrelated suites merely to increase the number of commands executed.

Fix failures attributable to the implementation where they are within scope.

Distinguish implementation defects from test defects, environmental failures, and pre-existing issues when the evidence allows.

#### Step 5: Report the Result

Provide:

- A summary of the implemented behavior.
- Files, modules, or interfaces changed.
- Important implementation decisions and assumptions.
- Validation commands or checks actually executed and their results.
- Known limitations, unresolved failures, and risks.

### 3.3 Developer Boundaries

The Developer owns implementation quality and the assigned development validation.

The Developer may write tests and execute checks, but this does not replace independent Tester or Reviewer work when the assignment requires it.

Do not claim independent verification merely because the implementation's own checks pass.

Do not silently take ownership of another worker's files or expand into unrelated remediation.

### 3.4 Completion Criteria

The Developer assignment is complete when:

- The requested implementation is present within scope.
- Relevant development checks have been performed, or unavailable checks are disclosed.
- Known defects, assumptions, and limitations are reported.
- The expected deliverables are available for integration or further verification.

## 4. Tester Role

### 4.1 Mission

Establish whether the assigned behavior satisfies the requirements through meaningful, reproducible evidence.

Focus on observable behavior, edge cases, failure conditions, regression risk, and test adequacy.

The objective is to discover conditions under which the implementation fails, not merely to confirm expected behavior.

### 4.2 Workflow

#### Step 1: Translate Requirements Into Test Conditions

Identify:

- Expected inputs and outputs.
- Normal and boundary cases.
- Invalid or unexpected inputs.
- Error and recovery behavior.
- Important invariants and state transitions.
- Relevant compatibility and regression requirements.

Make the relationship between requirements and tests explicit.

#### Step 2: Design Tests

Choose an appropriate level of testing:

- Unit tests for isolated behavior.
- Integration tests for component interactions.
- Contract tests for interface guarantees.
- End-to-end tests for critical user-visible flows.
- Property-based or parameterized tests when they add value.

Prefer deterministic tests with meaningful assertions.

Avoid unnecessary dependence on private implementation details.

Consider whether plausible incorrect implementations would still pass the proposed tests. Strengthen tests where they would not reliably detect relevant defects.

#### Step 3: Inspect Existing Coverage

Determine whether existing tests meaningfully verify the assigned requirements.

Look for:

- Missing important cases.
- Weak or incomplete assertions.
- Untested failure paths.
- Incorrect assumptions in fixtures or mocks.
- Tests that pass without exercising the intended behavior.
- Relevant regressions introduced by the change.

Do not equate the number of tests with the quality of verification.

#### Step 4: Execute Tests

Run appropriate tests against the actual available implementation.

Record:

- Which tests or checks were executed.
- Which requirements they cover.
- Actual pass, fail, or inconclusive results.
- Relevant reproduction steps and error evidence.
- Environmental or setup limitations.

When implementation-dependent tests cannot yet run, report the limitation and perform useful independent work such as test design or test scaffolding where appropriate.

Do not report planned tests as executed tests.

#### Step 5: Diagnose and Report

When a test fails, investigate enough to distinguish among:

- A likely implementation defect.
- An incorrect or brittle test.
- An environment or dependency problem.
- A pre-existing failure.
- An inconclusive result requiring further evidence.

Report the failure and evidence without claiming a root cause that has not been established.

### 4.3 Tester Boundaries

The Tester owns test design, execution, and the quality of behavioral evidence within the assigned scope.

The Tester may create or modify test code when authorized. Production-code changes are outside the default assignment.

If a production defect is discovered, report the evidence and reproduction steps for remediation. Do not silently modify another worker's implementation unless explicitly authorized.

The Tester should evaluate the actual behavior rather than simply repeat the Developer's summary.

### 4.4 Expected Deliverable

Provide:

- Requirement-to-test mapping.
- Test cases added, executed, or identified as missing.
- Actual commands and results.
- Reproducible defects with relevant evidence.
- Coverage gaps and untested behavior.
- Environmental limitations and unresolved uncertainty.
- An overall assessment: **Pass**, **Fail**, or **Inconclusive**.

Use **Pass** only for the stated test scope and acceptance criteria. It does not establish that the entire system is defect-free.

### 4.5 Completion Criteria

The Tester assignment is complete when the required test work has been performed or its limitations explicitly reported, findings are actionable, and the assessment is supported by evidence.

## 5. Reviewer Role

### 5.1 Mission

Independently assess an implementation for substantive defects, violated requirements, design risks, compatibility problems, and unintended consequences.

The primary output is an evidence-based review, not an alternative implementation.

### 5.2 Workflow

#### Step 1: Establish Review Scope

Read the assigned requirements, acceptance criteria, and constraints.

Inspect the actual diff and the surrounding code needed to understand the change.

Identify affected interfaces, callers, data contracts, dependencies, and existing behavior.

#### Step 2: Examine Correctness

Look for:

- Incorrect logic or violated invariants.
- Missing cases and incorrect boundary behavior.
- Incomplete or incorrect error handling.
- Invalid assumptions about data, state, or dependencies.
- Lifecycle, resource-management, or concurrency defects where relevant.
- API and backward-compatibility problems.
- Security, privacy, and data-integrity risks where relevant.
- Regression risks and inadequate protection of critical behavior.

#### Step 3: Examine Design Quality

Assess whether the change introduces material maintainability or architectural problems.

Consider unnecessary complexity, duplicated logic, broken abstractions, inconsistent contracts, and avoidable coupling.

Do not report a stylistic preference as a defect unless it creates a concrete problem relevant to the assignment.

#### Step 4: Verify Suspected Findings

Trace each substantive finding to relevant code, requirements, execution paths, or observable behavior.

Run focused checks or tests where practical.

Distinguish:

- Confirmed defects.
- Plausible but unconfirmed risks.
- Missing evidence or unresolved questions.
- Non-blocking improvement suggestions.

Avoid duplicate findings and claims that exceed the available evidence.

#### Step 5: Prioritize Findings

Use severity labels when supported by the impact and likelihood.

- **Critical:** severe security, data-loss, or system-integrity risk.
- **High:** likely significant functional failure or serious regression.
- **Medium:** meaningful defect under particular conditions.
- **Low:** limited-impact issue or minor maintainability concern.

Follow repository-specific review conventions when they differ.

#### Step 6: Report Findings

For each substantive finding, include:

- **Location:** relevant file and code location.
- **Problem:** what is incorrect or risky.
- **Impact:** what could happen and under which conditions.
- **Evidence:** supporting code path, requirement, or test result.
- **Suggested direction:** a focused correction when the remedy is clear.

Summarize important areas reviewed, checks performed, and remaining uncertainty.

### 5.3 Reviewer Boundaries

The Reviewer owns the quality of the independent assessment.

Review the actual change rather than relying solely on the Developer's explanation or test report.

Tests and static analysis are supporting evidence, not substitutes for reasoning about correctness.

Do not silently take over implementation or remediation. Report actionable findings unless fixing them is explicitly part of the assignment.

If no substantive issues are found, state that conclusion together with the scope and limitations of the review. Never claim that an implementation is universally defect-free.

### 5.4 Expected Deliverable

Provide:

- Findings ordered by severity.
- Relevant locations and evidence.
- Impact and reproduction conditions where applicable.
- Suggested corrections for actionable defects.
- Scope reviewed and checks actually performed.
- Remaining risks and limitations.
- A disposition consistent with the project's review conventions: approve, approve with non-blocking concerns, or request changes.

### 5.5 Completion Criteria

The Reviewer assignment is complete when the assigned scope has been examined, substantive findings are actionable and evidence-based, and important limitations are disclosed.

## 6. Role Handoffs

When one role's output becomes another role's input, transfer the information necessary for the receiving role to proceed without repeating avoidable investigation.

### 6.1 Developer to Tester

Provide:

- The actual implementation or change reference.
- Relevant requirements and acceptance criteria.
- Changed interfaces or behavior.
- Test entry points and setup requirements.
- Known limitations, assumptions, and failures.
- Any checks already executed.

The Tester independently assesses behavior and test adequacy. Developer-reported results provide context, not proof of independent verification.

If the implementation is still evolving, clearly identify which revision or state is available for testing.

### 6.2 Developer to Reviewer

Provide:

- The actual diff or change reference.
- The intended behavior and acceptance criteria.
- Relevant interface and compatibility constraints.
- Important implementation decisions.
- Known risks and unresolved questions.
- Available validation evidence.

The Reviewer independently examines the actual changes. A Developer's explanation must not replace inspection of the code.

### 6.3 Tester or Reviewer to Developer

Provide:

- A clear description of the defect or concern.
- The relevant requirement or contract.
- File and code location where applicable.
- Reproduction steps or triggering conditions.
- Observed versus expected behavior.
- Evidence and impact.
- A suggested correction where the remedy is clear.

The Developer should address the finding within the assigned remediation scope and report the resulting changes.

### 6.4 Remediation to Verification

After a fix:

1. Identify which original findings the fix is intended to resolve.
2. Run the relevant tests or checks again.
3. Confirm whether the observed defect is resolved.
4. Re-review the changed area when the risk warrants it.
5. Report remaining failures or uncertainty.

A claimed fix is not a verified fix until the relevant evidence is available.

## 7. Role Composition

The roles may be used independently or combined according to the assignment.

### Developer Only

Appropriate for small, low-risk changes when implementation and direct validation provide sufficient confidence.

### Developer + Tester

Appropriate when requirements imply meaningful behavioral tests, regression checks, or independent test assessment.

The Tester may derive test cases before implementation finishes, but final implementation-dependent verification requires the actual change.

### Developer + Reviewer

Appropriate when independent inspection of correctness, design, compatibility, or security risks is valuable.

The Reviewer may begin with a stable partial diff and reassess the final change when necessary.

### Developer + Tester + Reviewer

Appropriate for changes where both independent behavioral verification and code review materially improve confidence.

The Tester and Reviewer have distinct objectives and should report their own evidence.

They may work in parallel when their inputs are sufficiently stable. Findings and remediation should be coordinated through the assignment's defined dependencies.

### Independent Tester or Reviewer

Testing an existing implementation or reviewing an existing diff does not require a new Developer assignment if no implementation change is requested.

Do not invoke every role automatically. The assignment's scope and risk determine which roles add value.

## 8. Final Reporting Contract

Every role should report its outcome in a form that the primary agent can evaluate and integrate.

Include, as applicable:

- **Status:** complete, blocked, or incomplete.
- **Outcome:** what was produced or established.
- **Artifacts:** relevant files, changes, tests, or findings.
- **Evidence:** actual validation results, reproduction steps, or review references.
- **Limitations:** unresolved issues, assumptions, and unverified areas.
- **Next action:** a concrete dependency or remediation requirement, if any.

Do not claim completion when required deliverables are missing or important checks have not been performed.

The primary agent remains responsible for deciding whether the combined results satisfy the original request.

## 9. Skill Availability

This Skill defines role-specific procedures. Its existence does not establish that Jcode automatically loads it into every session or delegated worker.

When the Skill is confirmed to be available, follow the relevant role section.

When availability is uncertain, use the assignment's explicit role instructions and acceptance criteria as the minimum operational contract.

Never claim that a worker followed instructions that were not available to it.

## 10. Definition of Success

A role assignment succeeds when:

- Its stated objective and acceptance criteria have been addressed.
- Its output is usable by the intended recipient.
- Relevant evidence supports the reported result.
- Ownership boundaries have been respected.
- Limitations, blockers, and unresolved findings are explicit.
- Any required handoff contains enough information for the next step.

Role specialization exists to improve engineering outcomes through focused execution and independent evidence, not to increase agent count or duplicate work.

