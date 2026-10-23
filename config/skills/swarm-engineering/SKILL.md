---
name: swarm-engineering
description: A systematic engineering workflow for decomposing complex tasks into bounded parallel work units, coordinating agents, controlling shared state, reviewing evidence, recovering from failures, and integrating verified results. Use when a task benefits from multi-agent engineering collaboration.
---

# Swarm Engineering

## 1. Purpose

This Skill defines a practical engineering procedure for multi-agent collaboration.

Use it to transform a complex engineering objective into a set of bounded, independently reviewable work units, coordinate their execution, and integrate their results into a verified outcome.

This Skill does not replace the global operating policy or the Swarm orchestration policy. It provides the engineering method used to carry them out.

## 2. When to Use

Use this Skill when one or more of the following conditions hold:

- The task contains multiple independent investigations or implementation units.
- Different components can be developed against stable interfaces.
- Independent review would materially improve correctness or confidence.
- The task requires coordinated work across several subsystems.
- The task is large enough that explicit ownership, dependencies, and integration are valuable.

Do not use this Skill merely because a task contains multiple files.

Prefer direct execution when the work is small, tightly coupled, predominantly sequential, or cheaper to complete without delegation.

## 3. Inputs

Before starting, establish the available information:

- Engineering objective and desired outcome.
- Repository root and relevant project instructions.
- Current working-tree state and existing modifications.
- Known architecture, interfaces, and dependencies.
- Applicable constraints and safety requirements.
- Available agents, tools, Skills, and execution environments.
- Acceptance criteria and verification options.

Record important unknowns. Do not silently replace missing information with assumptions that could change the implementation or its safety.

## 4. Workflow Overview

Follow this lifecycle:

1. Frame the engineering objective.
2. Inspect the existing system.
3. Decompose the task.
4. Establish interfaces, dependencies, and ownership.
5. Assign bounded work units.
6. Monitor execution and manage exceptions.
7. Review contributions and collect evidence.
8. Integrate accepted results.
9. Verify the integrated outcome.
10. Report completion and remaining risks.

The workflow is iterative. New evidence may require revising the decomposition, interface contract, or execution strategy.

## 5. Step 1 — Frame the Objective

Convert the request into a testable engineering objective.

Define:

- **Goal:** What outcome must be achieved?
- **Scope:** What is included and excluded?
- **Constraints:** What must remain unchanged?
- **Acceptance criteria:** What observable conditions demonstrate success?
- **Risks:** What could break, conflict, or cause irreversible effects?
- **Deliverables:** What artifacts, code, tests, or findings are expected?

Separate requirements from proposed implementation details. Do not confuse a requested outcome with an assumed solution.

For ambiguous requirements, identify the smallest decision that must be resolved before work can proceed.

## 6. Step 2 — Inspect the Existing System

Perform enough investigation to make decomposition safe.

Inspect relevant:

- Source files and public interfaces.
- Tests and build configuration.
- Repository instructions and conventions.
- Existing modifications and uncommitted work.
- Call sites and downstream dependencies.
- Failure reports, logs, and reproducible examples.

Use evidence to distinguish actual defects from hypotheses.

For investigation-heavy tasks, a read-only discovery phase can precede implementation. Its purpose is to establish shared facts and reduce incompatible assumptions.

Do not require every Worker to repeat the same repository-wide discovery. Share validated findings with downstream assignments.

## 7. Step 3 — Decompose by Outcomes

Split the objective into meaningful work units.

A work unit should ideally have:

- One primary outcome.
- A bounded scope.
- A clear owner.
- Explicit dependencies.
- An independently reviewable deliverable.
- Observable acceptance criteria.

Prefer decomposition along stable boundaries, such as:

- Independent subsystem investigations.
- Separate components with agreed interfaces.
- Implementation and independent review.
- Test design and test execution.
- Documentation derived from verified implementation.

Avoid decomposition that creates artificial independence. Two tasks are not independent merely because they touch different files.

### Decomposition test

For each proposed work unit, ask:

1. Can it make progress without an unresolved upstream decision?
2. Can its scope and ownership be stated clearly?
3. Can its result be reviewed independently?
4. Does parallel execution offer a meaningful benefit?
5. Is the expected coordination cost acceptable?

If these questions cannot be answered satisfactorily, revise the decomposition or execute the work sequentially.

## 8. Step 4 — Define Contracts and Dependencies

Before parallel implementation, stabilize the contracts that allow work units to interoperate.

A contract may define:

- Public function or type signatures.
- Data models and serialization rules.
- File formats and directory conventions.
- Error handling and failure semantics.
- Configuration and environment assumptions.
- Test expectations.
- Compatibility requirements.

Record dependencies explicitly. Do not allow separate Workers to independently invent incompatible interfaces.

When the contract is uncertain, assign a focused design or investigation task before implementation begins.

## 9. Step 5 — Establish Ownership

Classify resources before issuing overlapping assignments.

Use the following ownership model:

- **Read-only:** Workers may inspect but must not modify.
- **Exclusive:** One Worker is authorized to modify the resource.
- **Coordinated:** Multiple contributors may participate under an explicit contract and sequence.
- **Integration-owned:** Contributions are reviewed and combined by the Coordinator.

Prefer exclusive ownership for mutable files.

Do not assume that different sessions have separate worktrees or isolated filesystems. Confirm actual runtime behavior.

If isolation is uncertain, use read-only investigations, independent patch proposals, or sequential implementation.

Preserve pre-existing user changes. Never discard unrelated modifications as part of integration cleanup.

## 10. Step 6 — Issue the Assignment

Every engineering assignment must communicate:

### Objective
The specific result expected from the Worker.

### Context
Relevant source paths, architectural decisions, prior findings, and constraints.

### Scope
Files or components to inspect or modify, and work explicitly excluded.

### Ownership
Permitted write targets and shared-resource restrictions.

### Procedure
The expected approach and any applicable Skills or project conventions.

### Deliverables
The artifact or evidence the Worker must return.

### Acceptance criteria
The observable conditions required for acceptance.

### Escalation conditions
When the Worker should stop and report a blocker, ambiguity, unexpected conflict, or unavailable capability.

For read-only investigation, explicitly prohibit modifications.

For implementation work, specify whether the Worker should edit the shared working tree or return a patch or recommendation. Use only modes supported by the runtime.

## 11. Step 7 — Monitor Execution

Monitor meaningful state transitions rather than requesting constant updates.

Track each work unit as one of:

- Pending.
- Running.
- Blocked.
- Failed.
- Completed, awaiting review.
- Accepted.
- Rejected or cancelled.

Use the actual lifecycle states exposed by the runtime; the labels above are a conceptual tracking model, not a claim about Jcode's exact status API.

When a Worker reports a material discovery:

1. Evaluate whether it changes the current plan.
2. Identify downstream assignments affected by the discovery.
3. Communicate updated constraints or contracts.
4. Reassign or stop obsolete work when necessary.

Avoid unnecessary duplicate assignments. Before creating a replacement Worker, determine whether the original Worker is still running or has already modified shared state.

## 12. Step 8 — Review Deliverables

Review the actual deliverable, not just its summary.

### Investigation deliverables

Verify that:

- Findings answer the assigned question.
- Source locations or other evidence support important claims.
- Observed behavior is distinguished from inferred behavior.
- Recommendations account for material constraints.
- No unauthorized changes were made.

### Implementation deliverables

Verify that:

- The diff is within the assigned scope.
- Existing interfaces and conventions are respected.
- The implementation matches the agreed contract.
- Error handling and edge cases are addressed.
- Relevant tests or checks were performed.
- Unrelated changes have not been introduced.

### Test deliverables

Verify that:

- Tests correspond to the acceptance criteria.
- Important success and failure paths are covered.
- The test environment and command are identified.
- Failures and skipped checks are reported accurately.
- Test results are not overstated.

A contribution may be accepted, conditionally accepted, returned for revision, or rejected. Record material reasons for the decision.

## 13. Step 9 — Handle Failures and Conflicts

Classify failures before responding.

Typical categories include:

- Missing context or unclear assignment.
- Missing tool, Skill, permission, or runtime capability.
- Dependency or environment failure.
- Incorrect implementation or failed verification.
- Conflicting changes or interface assumptions.
- Timeout or interrupted execution.
- Invalid or insufficient deliverable.

Choose the smallest effective recovery action.

Examples:

- Clarify a requirement.
- Supply missing evidence or interface information.
- Narrow the scope.
- Revise a contract.
- Retry with a materially different approach.
- Reassign the remaining work.
- Perform the remaining work directly.
- Stop and report the blocker.

Before retrying a write task, inspect the repository state and the previous attempt's modifications.

Do not conceal partial progress or erase useful failure evidence. Stop when additional attempts would be unsafe or unlikely to improve the outcome.

## 14. Step 10 — Integrate Contributions

The Coordinator owns final integration.

Use this sequence:

1. Confirm the required upstream work has been accepted.
2. Inspect actual changes and working-tree state.
3. Compare contributions against shared contracts.
4. Resolve overlapping changes and incompatible assumptions.
5. Integrate in dependency order.
6. Inspect the combined diff.
7. Run verification against the integrated result.

Do not blindly apply multiple patches that modify the same logic. Do not accept a Worker implementation solely because its isolated tests passed.

If an upstream design assumption proves incorrect, revise the contract and reassess dependent work instead of accumulating workarounds.

## 15. Step 11 — Verify the Result

Build a verification matrix from the acceptance criteria.

For each criterion, record:

- Required behavior.
- Evidence source.
- Verification method.
- Actual result.
- Remaining uncertainty.

Choose checks appropriate to the task, including focused tests, integration tests, linting, type checking, builds, reproduction steps, or independent review.

Prioritize checks that are most likely to reveal serious defects.

Distinguish among:

- Not attempted.
- Attempted but failed.
- Passed.
- Skipped or unavailable.
- Inconclusive.

A check that could not run is not a passing check.

When a test fails, investigate whether the failure is related to the change, pre-existing, or unresolved. Do not label it pre-existing without supporting evidence.

Re-run checks materially affected by integration, even if a Worker ran them earlier.

## 16. Step 12 — Produce the Final Report

Use this report structure for substantial engineering tasks:

### Outcome
Completed, partially completed, blocked, or failed.

### Scope
What was investigated or changed.

### Findings and decisions
Important discoveries and architectural decisions.

### Changes
Modified files, interfaces, or artifacts.

### Verification
Commands or checks actually performed and their results.

### Limitations and risks
Unverified behavior, failed checks, assumptions, and remaining concerns.

### Follow-up
Outstanding work or recommended next steps.

Keep the report proportional to the task. Do not include unnecessary transcripts or duplicate every intermediate Worker update.

## 17. Quality Checklist

Before declaring the engineering task complete, verify:

- [ ] The result addresses the original objective.
- [ ] Decomposition and dependencies were handled correctly.
- [ ] Worker ownership boundaries were respected.
- [ ] Material findings have supporting evidence.
- [ ] Contributions were reviewed before acceptance.
- [ ] Conflicts and partial failures were resolved or disclosed.
- [ ] The integrated result was inspected.
- [ ] Appropriate verification was performed.
- [ ] Remaining risks and limitations are explicit.
- [ ] The final report distinguishes facts from assumptions.

If any applicable item remains unsatisfied, either complete the missing work or disclose why the task remains incomplete.

## 18. Core Principle

Parallelism is a means, not an objective.

A successful Swarm is not one that spawns the most agents or completes the most assignments. It is one that produces a coherent, verifiable result with clear ownership, controlled coordination costs, and honest reporting.

