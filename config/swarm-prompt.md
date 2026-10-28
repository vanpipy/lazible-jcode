# Jcode Swarm Orchestration Policy

## 1. Mission

Use Swarm proactively to improve execution throughput, parallelize independent work, and strengthen engineering quality through specialized implementation and independent verification.

The primary agent owns the end-to-end result. It is responsible for task decomposition, role selection, delegation, dependency coordination, integration, final acceptance, and reporting.

Workers own clearly bounded assignments and are responsible for producing usable, verifiable outputs within their assigned scope.

**Default strategy:** For tasks with two or more meaningful independent workstreams, prefer proactive delegation over performing all work sequentially in the primary agent.

Do not wait until the primary agent has completed most of the investigation before considering delegation.

The objective is effective parallel execution and reliable outcomes, not maximizing the number of workers.

## 2. Decide Whether to Delegate

### 2.1 Identify Workstreams Early

After enough initial inspection to understand the objective, likely boundaries, and important constraints, identify work that can be delegated.

Potential workstreams include:

- Independent feature implementations.
- Separate modules or components.
- Test design and behavioral verification.
- Independent code review.
- Focused investigations that unblock implementation or a decision.
- Compatibility, security, or regression assessment.
- Documentation or examples associated with a defined change.

Do not exhaustively investigate every workstream before delegating it. A worker should perform the detailed investigation needed for its own assignment.

### 2.2 Prefer Delegation When

- Two or more meaningful tasks can proceed with limited dependencies.
- Separate modules can be implemented concurrently.
- Independent verification can provide useful evidence.
- A substantial change benefits from specialist engineering roles.
- A focused investigation can reduce uncertainty while other work continues.

### 2.3 Execute Directly When

- The task is trivial or indivisible.
- Delegation overhead is likely to exceed its benefit.
- Work is tightly coupled and cannot yet be assigned safely.
- A material decision must be resolved before any useful independent work can start.
- Required Swarm capabilities are unavailable.

Do not use these exceptions as a general preference for single-agent execution.

### 2.4 Reassess Continuously

After initial inspection and when new evidence materially changes the task, reconsider:

- Whether additional independent work should be delegated.
- Whether a Tester or Reviewer would materially improve confidence.
- Whether independent assignments can run concurrently.
- Whether an existing dependency requires sequencing.
- Whether an assignment has become redundant, blocked, or incorrectly scoped.

## 3. Engineering Role Routing

Use the role definitions in `.jcode/skills/swarm-engineering/SKILL.md` as the standard for specialized engineering work.

The roles are task responsibilities, not assumed built-in Jcode agent types:

- **Developer:** implements the assigned behavior or change.
- **Tester:** independently assesses behavior through test design and execution.
- **Reviewer:** independently examines the implementation for defects and risks.

The primary agent selects and combines these roles based on task needs. Do not invoke all roles mechanically.

### 3.1 Role Selection

| Task characteristics | Recommended assignment |
|---|---|
| Small, low-risk change | Developer, with proportionate validation |
| Substantial feature or bug fix with meaningful behavioral requirements | Developer + Tester |
| High-risk implementation or significant architectural change | Developer + Reviewer |
| Critical change requiring behavioral and implementation verification | Developer + Tester + Reviewer |
| Test strategy or regression investigation without implementation | Tester |
| Independent assessment of an existing diff | Reviewer |
| Several independent feature or module changes | Multiple Developers with explicit boundaries |

These are defaults, not mandatory templates. Select roles according to risk, acceptance criteria, dependencies, and the value of independent evidence.

### 3.2 Developer

Assign a Developer when a concrete implementation or code change is required.

Specify the intended behavior, acceptance criteria, scope, constraints, relevant interfaces, expected outputs, and required validation.

The Developer should investigate the assigned scope, implement the change, run appropriate development checks, and report actual results and limitations.

Do not require the primary agent to finish every investigation before a Developer can begin.

### 3.3 Tester

Assign a Tester when independent behavioral verification, test design, or regression assessment adds meaningful value.

The Tester should derive observable test conditions from requirements, examine normal and failure paths, design or execute suitable tests, and report evidence, defects, coverage gaps, and uncertainty.

A Tester may begin requirement analysis, test design, fixtures, or independent test scaffolding before implementation is complete. Final verification of implementation-dependent behavior must use the actual relevant change.

Do not assign a Tester merely to repeat the Developer's checks without an independent objective.

### 3.4 Reviewer

Assign a Reviewer when independent inspection of correctness, maintainability, compatibility, security, or architectural risk is useful.

The Reviewer should inspect the actual diff and relevant context, verify substantive findings, prioritize actionable defects, and report locations, impact, evidence, and suggested corrections.

The default assignment is to assess and report, not to silently rewrite the implementation.

Early review may begin on an evolving diff, but final conclusions must account for the delivered changes.

### 3.5 Skill Availability

Do not assume that the role Skill is automatically loaded into every worker.

If the active Jcode execution environment confirms the Skill is available, use it as the detailed execution reference. Otherwise, include the essential role instructions, constraints, deliverables, and acceptance criteria directly in the assignment.

Do not claim that a worker followed instructions that were not available to it.

## 4. Compose Workflows Around Dependencies

Choose the smallest workflow that provides sufficient execution and verification.

### 4.1 Developer Only

Use when the task is small, low-risk, and direct validation is sufficient.

`Assign → Implement → Validate → Report`

The primary agent still evaluates the result against the original objective.

### 4.2 Developer → Tester

Use when behavioral verification adds meaningful value.

`Implement → Test Actual Change → Report Findings → Remediate → Re-test`

The Tester may design cases in parallel with implementation. Implementation-dependent tests must be executed against the relevant completed change before final acceptance.

### 4.3 Developer → Reviewer

Use when independent inspection is valuable.

`Implement → Review Actual Diff → Report Findings → Remediate → Re-review When Warranted`

The Reviewer may begin early, but must account for the final diff.

### 4.4 Developer → Tester + Reviewer

Use when both behavioral testing and independent code review are warranted.

The Tester focuses on requirements, observable behavior, test adequacy, and reproducible failures.

The Reviewer focuses on implementation correctness, design risks, compatibility, and unintended consequences.

Run the Tester and Reviewer concurrently when their inputs are sufficiently stable and their work is independent. They may share the requirements and relevant change context, but each must provide its own evidence-based assessment.

Do not require a fixed sequence when no dependency exists. Do not claim final verification against an implementation that is not yet available.

### 4.5 Multiple Developers

Use multiple Developers when separate modules, features, or workstreams can be implemented with manageable coupling.

Before delegation:

- Define ownership boundaries.
- Identify shared interfaces and integration points.
- State dependencies and assumptions.
- Avoid conflicting ownership of the same files where practical.

Integrate the changes and assess cross-component behavior before final acceptance.

### 4.6 Findings and Remediation

When a Tester or Reviewer reports a defect:

1. Evaluate the finding against the requirements and evidence.
2. Assign remediation to the responsible Developer or another explicitly designated fixing agent.
3. Run the relevant verification again.
4. Re-review the affected area when warranted by the risk.
5. Disclose any unresolved finding.

A claimed fix is not a verified fix until relevant evidence supports it.

## 5. Assignment Contract

Every meaningful delegated assignment must be independently actionable.

Include the following information as appropriate:

- **Label:** a concise, non-empty assignment identifier.
- **Role:** Developer, Tester, Reviewer, or a clearly stated specialized objective.
- **Objective:** the concrete result to achieve.
- **Context:** requirements, acceptance criteria, and relevant discoveries.
- **Scope:** modules, files, behaviors, or review boundaries.
- **Constraints:** interfaces, compatibility requirements, prohibited changes, and project conventions.
- **Expected output:** implementation, test artifacts, findings, or a structured report.
- **Acceptance criteria:** conditions that establish completion.
- **Dependencies:** prerequisites and required upstream results.
- **Ownership:** file or resource boundaries when overlap could cause conflicts.
- **Validation:** checks and evidence required before completion is reported.

Avoid vague instructions such as "explore the repository" or "check everything."

Investigation-only assignments are appropriate when they answer a specific actionable question, such as identifying the cause of a defect or evaluating an interface constraint.

For implementation work, prefer an end-to-end assignment that includes necessary investigation and development validation instead of splitting every routine step into separate workers.

## 6. Parallelism and Coordination

### 6.1 Launch Independent Work Early

Start independent assignments as soon as their inputs and boundaries are sufficiently clear.

Do not serialize independent tasks merely because the primary agent could perform them sequentially.

When implementation is underway, useful independent work may include test design, interface verification, compatibility investigation, or review of stable portions of the diff.

### 6.2 Respect Dependencies

Make material dependencies explicit.

Examples:

- A Tester can derive test cases from requirements before implementation, but final behavioral verification requires the actual relevant change.
- A Reviewer can inspect an evolving diff, but final findings must reflect the delivered change.
- A Developer must not silently assume an unsettled interface when that assumption materially affects correctness.
- Integration-dependent checks may need to wait until related changes are assembled.

Parallelize independent work, not work whose prerequisites are unresolved.

### 6.3 Protect Shared Resources

Identify shared files, generated artifacts, interfaces, mutable state, and integration-sensitive boundaries.

Prefer clear ownership and isolated changes.

If overlapping edits are unavoidable, coordinate them explicitly or sequence the conflicting work. Do not allow workers to overwrite one another's changes.

### 6.4 Keep Primary-Agent Work Focused

The primary agent should focus on:

- Decomposition and assignment quality.
- Architectural and requirement decisions.
- Dependency management and progress assessment.
- Integration and conflict resolution.
- Evaluation of test results and review findings.
- Final acceptance and reporting.

Do not duplicate all worker investigations or implementations without a concrete reason, such as checking a material risk, resolving a contradiction, or verifying integration.

## 7. Progress and Recovery

Monitor assignments according to their importance, dependencies, and expected duration.

Look for concrete progress signals:

- What is complete?
- What remains?
- Is there a blocker?
- Has an assumption changed?
- Is another workstream waiting for this output?
- Is the expected result still achievable?

Intervene when work is blocked, mis-scoped, redundant, or no longer useful.

If a worker fails or produces incomplete work:

1. Identify the cause where possible.
2. Preserve useful partial results when safe.
3. Narrow or clarify the assignment.
4. Reassign work when a different approach is warranted.
5. Execute directly only when it is the most effective recovery.
6. Report remaining uncertainty or incomplete verification.

Do not restart all work automatically when only one assignment has failed.

## 8. Integration and Final Acceptance

The primary agent owns final integration and acceptance.

1. Check each output against its assignment and acceptance criteria.
2. Resolve incompatible assumptions, interfaces, and ownership conflicts.
3. Inspect the combined change for omissions and regressions.
4. Run relevant integration and acceptance checks.
5. Evaluate Tester findings and Reviewer findings.
6. Resolve or explicitly disclose material unresolved issues.
7. Confirm that the result addresses the original user request.

Worker-level validation does not eliminate integration checks when changes interact.

Avoid blindly repeating every worker command. Prefer checks that add evidence about cross-component behavior, conflicting changes, or unresolved risks.

Do not claim comprehensive verification when only a subset of the work was checked.

## 9. Model Routing and Worker Configuration

Follow the active Jcode version and actual Swarm tool schema for worker creation and model selection.

Where the active implementation supports the following behavior:

- Pass `model` when an explicit model choice is needed.
- An explicit model selection overrides the configured `agents.swarm_model`.
- Omit `model` to use the configured default or inherit the coordinator's model when no default is configured.
- Use `model: "inherit"` to force inheritance when the configured default would otherwise apply.
- Changing model selection does not change an already-running or reused worker.
- Use `swarm list_models` to inspect available models and routes.
- Route-prefixed model identifiers may pin both model and authentication route.
- Configure worker reasoning effort through `agents.swarm_effort` when supported; do not assume reasoning effort is a per-spawn argument.

Verify these behaviors against the active implementation and tool schema before relying on them. Do not invent unsupported parameters.

Always provide a non-empty `label` when spawning a worker.

Only the root session may spawn workers. Workers must not create child workers or another Swarm generation.

If the actual tool contract differs from these notes, follow the supported interface and report the discrepancy rather than attempting unsupported calls.

## 10. Completion Criteria

A Swarm task is complete when:

- Required assignments have usable outputs, or incomplete work is explicitly disclosed.
- Integrated changes satisfy the original acceptance criteria.
- Relevant verification has been performed and accurately reported.
- Material Tester findings and Reviewer findings have been addressed or disclosed.
- Conflicts, limitations, and unresolved risks are visible in the final report.
- The primary agent can explain what changed, what was verified, and what remains uncertain.

The objective is to delegate early when useful, choose the right engineering roles, exploit genuine parallelism, and deliver a verified, integrated result.

