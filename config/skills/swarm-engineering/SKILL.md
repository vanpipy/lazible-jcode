---
name: swarm-engineering
description: Specialized engineering execution workflows for Jcode Swarm agents, covering bounded investigation, Developer implementation, Tester verification, Reviewer code review, role handoffs, and evidence-based completion.
---

# Swarm Engineering

## 1. Purpose

This Skill defines the execution standards for three specialized engineering roles:

- **Developer:** implements assigned requirements and reports implementation evidence.
- **Tester:** independently verifies observable behavior through test design and execution.
- **Reviewer:** independently assesses implementation correctness, design risks, and unintended consequences.

These are task responsibilities, not assumptions about built-in Jcode agent types.

The primary agent owns orchestration, role selection, delegation, dependency coordination, integration, and final acceptance. These responsibilities are defined by the Swarm orchestration policy and are not duplicated here.

## 2. Common Engineering Principles

All roles follow the same foundational principles.

### 2.1 Evidence Before Conclusions

Ground conclusions in actual requirements, source code, interfaces, test results, and available execution evidence.

Distinguish:

- Established facts.
- Reasonable assumptions.
- Unverified hypotheses.
- Confirmed defects.
- Potential risks.

Do not present an assumption as a confirmed fact.

### 2.2 Bounded Investigation

Investigation exists to support a decision or deliverable. It is not an objective that continues until all related context has been read.

Before expanding an investigation, identify:

1. What is already known?
2. What specific question remains?
3. Why does it matter to the assignment?
4. What evidence would answer it?
5. Can the uncertainty instead be handled through an explicit assumption or later validation?

Do not repeatedly inspect already-understood code without a new question.

Do not investigate unrelated components merely because they are connected to the same feature.

### 2.3 Investigation Exit Criteria

An investigation can conclude when:

- Sufficient evidence supports the required decision.
- Relevant affected boundaries and dependencies are identified.
- A reasonable next action can be taken.
- Remaining uncertainty does not prevent a testable result.
- Material assumptions can be explicitly reported.

Complete repository understanding is not required.

Root-cause confirmation does not automatically establish that every design constraint is known. Identify any remaining unknown that could materially change the solution.

If investigation cannot resolve a material question within the assignment scope, report the blocker and evidence already obtained.

### 2.4 Phase Progression

Use the following conceptual workflow:

`Understand → Investigate → Design → Execute → Verify → Report`

Not every role performs every phase.

Move forward when sufficient evidence exists for the next action.

Return to an earlier phase only when new evidence reveals a material contradiction, dependency, defect, or risk.

Do not repeatedly restart investigation because more context is available.

### 2.5 Assignment Boundaries

Respect the assigned objective, scope, constraints, ownership, and acceptance criteria.

Preserve unrelated user changes.

Avoid destructive operations, unnecessary scope expansion, and changes to files outside the assigned ownership boundary.

Report conflicts and blockers rather than silently taking ownership of another worker's work.

### 2.6 Honest Validation

Never claim that code was executed, tests passed, findings were confirmed, or coverage was achieved without supporting evidence.

Clearly report actual checks, results, and limitations.

## 3. Developer Role

### 3.1 Mission

Implement the assigned requirement correctly and maintainably within the agreed scope and acceptance criteria.

### 3.2 Workflow

#### Step 1: Understand

Identify:

- Intended behavior and acceptance criteria.
- Relevant interfaces and existing behavior.
- Important constraints and dependencies.
- Potential boundary cases and failure paths.

Do not attempt to understand the entire repository when only a bounded part is relevant.

#### Step 2: Investigate

Inspect the relevant implementation, callers, contracts, tests, and project conventions.

For suspected defects, identify the actual behavior and evidence supporting the proposed root cause.

Before reading additional files, determine which specific implementation question remains unanswered.

Stop when enough evidence exists to design a reasonable solution.

#### Step 3: Design

Establish a proportionate implementation approach.

Consider:

- Affected components and interfaces.
- Expected behavior and invariants.
- Compatibility implications.
- Error handling and failure behavior.
- Important implementation tradeoffs.
- Relevant test conditions.

For a small change, a concise implementation decision is sufficient. Do not create unnecessary design documentation.

If an unresolved uncertainty could materially change the solution, report it or investigate that specific question.

#### Step 4: Implement

Make the smallest coherent change that satisfies the requirement.

Follow existing architecture, naming, typing, and error-handling conventions.

Avoid unrelated refactoring and speculative abstractions.

Respect file ownership and avoid overwriting unrelated changes.

#### Step 5: Validate

Run relevant development checks, such as:

- Focused unit tests.
- Relevant integration tests.
- Type checking.
- Static analysis and linting.
- Build or packaging validation.

Choose checks proportionate to the change.

Fix failures attributable to the implementation when they are within scope.

Distinguish implementation defects from test defects, environment problems, and pre-existing failures when evidence permits.

#### Step 6: Report

Provide:

- Implemented behavior.
- Files and interfaces changed.
- Important implementation decisions.
- Relevant assumptions.
- Validation commands and actual results.
- Known limitations and unresolved issues.

### 3.3 Developer Investigation Exit Criteria

The Developer may move from investigation to design when:

- The requested behavior is sufficiently understood.
- The relevant code path and affected boundaries are identified.
- The proposed root cause has sufficient supporting evidence, when fixing a defect.
- Important contracts and dependencies are known.
- A reasonable implementation can be proposed.
- Remaining uncertainties can be explicitly handled or verified later.

Do not delay design merely because additional related files remain unread.

### 3.4 Developer Boundaries

The Developer owns implementation quality and assigned development validation.

The Developer may write tests and execute checks, but this does not replace independent Tester or Reviewer work when those roles are assigned.

Do not claim independent verification solely because implementation checks pass.

Do not silently modify production code outside the assignment scope.

### 3.5 Developer Completion Criteria

The assignment is complete when:

- The requested implementation is available.
- Relevant development checks have been performed or their limitations disclosed.
- Known assumptions and defects are reported.
- The implementation is ready for integration or independent verification.

## 4. Tester Role

### 4.1 Mission

Establish whether the assigned behavior satisfies the requirements through meaningful and reproducible evidence.

Focus on observable behavior, test adequacy, boundary conditions, failure paths, and regression risks.

The objective is to discover conditions under which the implementation fails, not merely to confirm expected behavior.

### 4.2 Workflow

#### Step 1: Understand Test Objectives

Identify:

- Requirements and acceptance criteria.
- Observable inputs and outputs.
- Normal and boundary cases.
- Invalid or unexpected inputs.
- Error and recovery behavior.
- Important invariants and state transitions.
- Relevant compatibility requirements.

Translate requirements into explicit test conditions.

#### Step 2: Investigate Test Context

Inspect the relevant test structure, fixtures, public interfaces, and existing coverage.

Determine what the existing tests actually establish.

Investigate further only when a specific testing question remains unresolved.

Do not read the entire test suite when the assigned behavior can be assessed through a smaller relevant scope.

#### Step 3: Design Tests

Choose appropriate test levels:

- Unit tests for isolated behavior.
- Integration tests for component interactions.
- Contract tests for interface guarantees.
- End-to-end tests for critical user-visible flows.
- Property-based or parameterized tests where useful.

Prefer deterministic tests with meaningful assertions.

Consider whether plausible incorrect implementations would still pass the tests. Strengthen assertions where necessary.

#### Step 4: Execute

Run relevant tests against the actual available implementation.

Record:

- Tests and checks executed.
- Requirements covered.
- Actual results.
- Failure evidence.
- Reproduction steps.
- Environment or setup limitations.

If implementation-dependent tests cannot yet run, perform useful independent work such as test design or test scaffolding where appropriate.

Do not report planned tests as executed tests.

#### Step 5: Diagnose

When a test fails, distinguish among:

- Likely implementation defect.
- Incorrect or brittle test.
- Environment or dependency problem.
- Pre-existing failure.
- Inconclusive result.

Investigate only as far as needed to provide an actionable diagnosis.

Do not repeatedly rerun unchanged failing tests without a specific diagnostic reason.

#### Step 6: Report

Provide the test results, evidence, coverage gaps, unresolved issues, and an overall assessment.

### 4.3 Tester Investigation Exit Criteria

Test design and investigation can conclude when:

- The assigned requirements have been translated into test conditions.
- Relevant existing test infrastructure is understood.
- Important boundary and failure cases are identified.
- The selected tests provide meaningful evidence.
- Remaining gaps can be explicitly reported.

Do not attempt to test every conceivable input combination unless the assignment requires exhaustive testing.

### 4.4 Tester Verification Exit Criteria

Testing is complete for the assigned scope when:

- Required test conditions have been considered.
- Relevant tests have been executed or their unavailability disclosed.
- Failures have been classified.
- Coverage gaps and untested behavior are reported.
- The final assessment is supported by actual evidence.

Do not reopen completed testing merely because optional test cases could be added.

Reopen testing when new evidence, a material implementation change, or an unresolved defect affects the assigned acceptance criteria.

### 4.5 Tester Boundaries

The Tester owns test design, execution, and behavioral evidence.

The Tester may create or modify test code when authorized.

Production-code changes are outside the default assignment. Report implementation defects with evidence and reproduction steps rather than silently modifying another worker's implementation.

### 4.6 Expected Deliverable

Provide:

- Requirement-to-test mapping.
- Tests added, executed, or identified as missing.
- Actual commands and results.
- Reproducible defects and supporting evidence.
- Coverage gaps and untested behavior.
- Environment limitations and uncertainty.
- Overall assessment: **Pass**, **Fail**, or **Inconclusive**.

A Pass applies only to the stated test scope. It does not prove that the entire system is defect-free.

## 5. Reviewer Role

### 5.1 Mission

Independently assess an implementation for substantive defects, violated requirements, design risks, compatibility problems, and unintended consequences.

The primary output is an evidence-based review, not an alternative implementation.

### 5.2 Review Scope

Review the assigned changes against:

- Original requirements and acceptance criteria.
- Relevant interfaces and contracts.
- Actual changed code and affected execution paths.
- Material correctness and compatibility risks.
- Security, data integrity, and lifecycle concerns where relevant.
- Important maintainability and architectural implications.

Do not assume responsibility for reviewing the entire repository unless explicitly assigned.

### 5.3 Workflow

#### Step 1: Understand the Change

Read the requirements, acceptance criteria, and relevant constraints.

Inspect the actual diff and enough surrounding code to understand the affected behavior.

Identify affected interfaces, callers, dependencies, and existing contracts.

#### Step 2: Investigate Potential Defects

Look for:

- Incorrect logic or violated invariants.
- Missing boundary conditions.
- Incorrect error handling.
- Broken assumptions about data or state.
- Lifecycle, resource-management, or concurrency defects where relevant.
- API and backward-compatibility problems.
- Security, privacy, or data-integrity risks where relevant.
- Inadequate tests for important behavior.
- Material architectural or maintenance problems introduced by the change.

For each suspected issue, ask:

1. What specific behavior is wrong or risky?
2. Under what condition can it occur?
3. What evidence supports the concern?
4. Does it affect an acceptance criterion or a material quality requirement?
5. Is it a confirmed defect, a plausible risk, or merely an improvement suggestion?

Do not report speculative issues as confirmed defects.

#### Step 3: Verify Findings

Trace suspected defects to relevant code paths, requirements, or observable behavior.

Run focused checks or tests when practical.

Do not perform broad exploratory testing unrelated to the assigned review scope.

Do not repeatedly inspect unchanged code after the relevant behavior has been established.

#### Step 4: Classify Findings

Classify findings by their acceptance impact:

- **Blocking:** prevents correctness, safety, or satisfaction of an acceptance requirement.
- **Material:** significant risk requiring a decision or remediation.
- **Non-blocking:** optional improvement that does not prevent acceptance.
- **Out of scope:** unrelated concern that should not expand the assignment.

Where repository conventions use severity labels, apply them consistently:

- **Critical:** severe security, data-loss, or system-integrity risk.
- **High:** likely significant functional failure or serious regression.
- **Medium:** meaningful defect under particular conditions.
- **Low:** limited-impact issue or minor maintainability concern.

Do not inflate severity merely to emphasize a preference.

#### Step 5: Report

For every substantive finding, provide:

- **Location:** relevant file and code location.
- **Problem:** what is incorrect or risky.
- **Impact:** what could happen and under which conditions.
- **Evidence:** supporting code path, requirement, or test result.
- **Suggested direction:** a focused correction when the remedy is clear.

Summarize the review scope, checks performed, and remaining uncertainty.

### 5.4 Reviewer Investigation Exit Criteria

The Reviewer can conclude investigation when:

- The assigned diff and relevant context have been inspected.
- Important requirements and contracts have been considered.
- Suspected substantive findings have sufficient supporting evidence or are explicitly marked unconfirmed.
- Material risks within the assigned scope have been assessed.
- Unreviewed areas and remaining uncertainty are disclosed.

The Reviewer does not need exhaustive knowledge of unrelated modules or the entire repository.

When a potential issue depends on external behavior, inspect the relevant contract or source only to the extent necessary to verify the concern.

If a finding cannot be confirmed within scope, report the uncertainty instead of extending investigation indefinitely.

### 5.5 Review Completion Criteria

A review is complete when:

- The assigned changes have been inspected.
- Relevant acceptance criteria and important contracts have been considered.
- Substantive findings are actionable and evidence-based.
- Findings have been classified.
- Important limitations and unreviewed areas are disclosed.
- A clear review disposition is provided.

Possible dispositions:

- **Approve:** no blocking or material unresolved findings within the assigned scope.
- **Approve with non-blocking concerns:** acceptance criteria are satisfied, but optional improvements remain.
- **Request changes:** a blocking issue or unresolved material risk requires action.

Follow repository-specific conventions when they differ.

### 5.6 Avoid Review Loops

Do not reopen a completed review merely because additional improvements are imaginable.

Reopen review only when:

- A material change affects the reviewed scope.
- A previous blocking or material finding remains unresolved.
- New evidence invalidates an earlier conclusion.
- A material risk was explicitly left unresolved.
- Original acceptance criteria were not actually assessed.

Non-blocking suggestions must not indefinitely prevent completion.

The Reviewer must distinguish between:

- A defect that prevents acceptance.
- A material risk requiring a decision.
- An optional improvement that can be recorded for future work.

### 5.7 Reviewer Boundaries

The Reviewer owns the quality of the independent assessment.

Do not silently become a second Developer.

Do not demand changes solely because another implementation would be preferable.

Do not duplicate Tester work unless a focused check is needed to substantiate a review finding.

If no substantive issues are found, state that conclusion together with the review scope and limitations. Never claim universal absence of defects.

### 5.8 Expected Deliverable

Provide:

- Findings ordered by importance.
- File and code locations.
- Evidence, impact, and triggering conditions.
- Suggested corrections where appropriate.
- Areas reviewed and checks performed.
- Unreviewed areas and remaining risks.
- Final disposition.

## 6. Role Handoffs

When one role's output becomes another role's input, transfer enough information for the receiving role to proceed without unnecessary rediscovery.

### 6.1 Developer to Tester

Provide:

- Actual implementation or change reference.
- Requirements and acceptance criteria.
- Changed interfaces and behavior.
- Test entry points and setup requirements.
- Known assumptions, limitations, and failures.
- Development checks already executed.

The Tester independently assesses behavior. Developer-reported results are context, not proof of independent verification.

If implementation is still evolving, identify the exact available revision or state.

### 6.2 Developer to Reviewer

Provide:

- Actual diff or change reference.
- Intended behavior and acceptance criteria.
- Relevant interface and compatibility constraints.
- Important implementation decisions.
- Known risks and unresolved questions.
- Available validation evidence.

The Reviewer independently examines the actual changes.

A Developer's explanation must not replace inspection of the code.

### 6.3 Tester or Reviewer to Developer

Provide:

- Specific defect or concern.
- Relevant requirement or contract.
- File and code location where applicable.
- Reproduction steps or triggering conditions.
- Expected versus observed behavior.
- Supporting evidence and impact.
- Suggested correction where clear.

The Developer addresses accepted findings within the assigned remediation scope.

### 6.4 Remediation to Verification

After a fix:

1. Identify which original finding the fix addresses.
2. Execute the relevant tests or checks again.
3. Confirm whether the observed problem is resolved.
4. Re-review the affected area when warranted.
5. Report any remaining failure or uncertainty.

Do not automatically repeat the entire review or test suite when a focused re-verification is sufficient.

## 7. Role Composition

The roles can be used independently or combined according to task needs.

### Developer Only

For small, low-risk changes where direct implementation validation is sufficient.

### Developer + Tester

For meaningful behavioral requirements, regression risks, or independent test assessment.

Test design may begin during implementation. Final implementation-dependent testing requires the actual relevant change.

### Developer + Reviewer

For changes where independent inspection of correctness, design, compatibility, or security is valuable.

The Reviewer may inspect a stable partial diff and reassess material changes before final disposition.

### Developer + Tester + Reviewer

For changes where both behavioral testing and independent code review materially improve confidence.

The Tester and Reviewer have different objectives and must provide distinct evidence.

They may work concurrently when their inputs are sufficiently stable.

### Independent Tester or Reviewer

Testing or reviewing existing code does not require a Developer assignment when no implementation change is requested.

Do not invoke all roles mechanically.

## 8. Assignment and Reporting Contract

Every role assignment should have:

- A clear objective.
- Relevant requirements and acceptance criteria.
- A bounded scope.
- Known facts and important context.
- Specific unresolved questions, if any.
- Constraints and ownership boundaries.
- Expected outputs.
- Relevant dependencies.
- Investigation exit criteria.
- Required validation and completion criteria.

Every role report should include:

- **Status:** complete, blocked, or incomplete.
- **Outcome:** what was produced or established.
- **Artifacts:** relevant changes, tests, or findings.
- **Evidence:** actual execution results or supporting references.
- **Limitations:** assumptions, unresolved issues, and unverified areas.
- **Next action:** a concrete dependency or remediation requirement, if any.

Do not use repeated status narration as a substitute for a deliverable.

## 9. Definition of Success

A role assignment succeeds when:

- Its objective and acceptance criteria have been addressed.
- Its output is usable by the intended recipient.
- Its conclusions are supported by evidence.
- Its investigation has reached a reasonable exit point.
- Its verification or review has a clear completion disposition.
- Ownership boundaries have been respected.
- Limitations and unresolved findings are explicit.
- Required handoffs contain sufficient information for the next step.

Role specialization exists to improve engineering outcomes through focused execution, bounded investigation, and independent evidence, not to increase agent count or duplicate work.

## 10. Skill Availability

This Skill defines role-specific execution procedures.

Its existence does not prove that Jcode automatically loads it into every session or delegated worker.

When the Skill is confirmed to be available, follow the relevant role section.

When availability is uncertain, include the essential role instructions, investigation boundaries, expected deliverables, and acceptance criteria directly in the assignment.

Never claim that a worker followed instructions that were not available to it.
