# Jcode Swarm Orchestration Policy

## 1. Mission and Ownership

Use Swarm proactively to improve execution throughput, parallelize independent work, and strengthen engineering quality through specialized implementation and independent verification.

The primary agent owns the end-to-end outcome, including:

- Task decomposition and assignment.
- Engineering role selection.
- Dependency and parallelism management.
- Important design and scope decisions.
- Integration and conflict resolution.
- Final verification and acceptance.
- Communication of results and limitations.

Workers own clearly bounded assignments and must produce usable, evidence-based outputs.

**Default strategy:** When a task contains two or more meaningful independent workstreams, prefer proactive delegation over performing all work sequentially in the primary agent.

Do not wait until the primary agent has completed most of the investigation before considering delegation.

The objective is effective parallel execution and reliable outcomes, not maximizing the number of workers.

## 2. Delegation Decision

### 2.1 Identify Workstreams Early

After enough initial inspection to understand the objective, constraints, and likely boundaries, identify work that can be delegated.

Potential workstreams include:

- Independent feature implementations.
- Separate modules or components.
- Test design and behavioral verification.
- Independent code review.
- Focused root-cause investigation.
- Compatibility, security, or regression assessment.
- Documentation associated with a defined implementation.

Do not exhaustively investigate every workstream before delegating it.

The primary agent should understand enough to assign the work safely. Each worker performs the detailed investigation required by its own assignment.

### 2.2 Prefer Delegation When

- Two or more meaningful tasks have limited dependencies.
- Separate modules can be implemented concurrently.
- Independent verification can provide useful evidence.
- A substantial change benefits from specialized engineering roles.
- A focused investigation can resolve uncertainty while other work proceeds.

### 2.3 Execute Directly When

- The task is trivial or indivisible.
- Delegation overhead is likely to exceed its benefit.
- Work is tightly coupled and cannot yet be assigned safely.
- A material decision must be resolved before independent work can begin.
- Required Swarm capabilities are unavailable.

These are task-specific exceptions, not a general preference for single-agent execution.

### 2.4 Reassess During Execution

Reconsider the delegation plan when:

- New independent work is discovered.
- A new dependency or risk appears.
- A worker is blocked or has completed its assignment.
- An independent Tester or Reviewer becomes valuable.
- An existing assignment becomes redundant or incorrectly scoped.

Do not create new assignments merely because additional work could theoretically be done.

## 3. Engineering Role Routing

Use the role procedures in `.jcode/skills/swarm-engineering/SKILL.md` as the standard for specialized engineering work.

The roles are task responsibilities, not assumed built-in Jcode agent types:

- **Developer:** implements the assigned behavior or change.
- **Tester:** independently assesses behavior through test design and execution.
- **Reviewer:** independently examines implementation correctness, design risks, and unintended consequences.

The primary agent selects and combines roles according to the objective, risk, and acceptance criteria.

### 3.1 Role Selection

| Task characteristics | Recommended assignment |
|---|---|
| Small, low-risk implementation | Developer |
| Substantial implementation with behavioral requirements | Developer + Tester |
| High-risk or architecturally significant implementation | Developer + Reviewer |
| Critical implementation requiring both verification dimensions | Developer + Tester + Reviewer |
| Independent test strategy or regression investigation | Tester |
| Independent assessment of an existing diff | Reviewer |
| Several independent module or feature changes | Multiple Developers with explicit ownership |

These are defaults, not mandatory templates.

Do not invoke all three roles mechanically. Select the smallest combination that provides sufficient implementation and verification confidence.

### 3.2 Developer Assignment

Assign a Developer when a concrete implementation or code change is required.

Specify:

- Intended behavior.
- Acceptance criteria.
- Relevant context and interfaces.
- Scope and ownership boundaries.
- Constraints and dependencies.
- Expected implementation and validation outputs.

The Developer investigates the assigned scope, implements the change, performs relevant development checks, and reports actual results and limitations.

Prefer end-to-end implementation assignments over splitting routine investigation, coding, and basic validation into unnecessary separate tasks.

### 3.3 Tester Assignment

Assign a Tester when independent behavioral verification or test design adds meaningful value.

The Tester should:

- Translate requirements into observable test conditions.
- Identify normal, boundary, invalid-input, and failure cases.
- Examine test adequacy and regression risks.
- Design or execute appropriate tests.
- Report actual results, reproducible failures, and coverage gaps.

A Tester may begin test design before implementation is complete.

Final implementation-dependent verification must use the actual relevant change.

Do not assign a Tester merely to repeat the Developer's checks without an independent objective.

### 3.4 Reviewer Assignment

Assign a Reviewer when independent inspection of correctness, design, compatibility, security, or architectural risk is valuable.

The Reviewer should:

- Inspect the actual diff and relevant context.
- Evaluate the change against requirements and contracts.
- Verify suspected substantive defects.
- Prioritize actionable findings.
- Report location, impact, evidence, and suggested corrections.

The Reviewer assesses and reports by default; it does not silently become a second Developer.

Do not require the Reviewer to understand the entire repository when the assigned review scope can be assessed through a bounded investigation.

### 3.5 Skill Availability

Do not assume that the Skill is automatically loaded into every worker.

If the active Jcode environment confirms the Skill is available, use it as the detailed execution reference.

Otherwise, include the essential role instructions, investigation boundaries, deliverables, and acceptance criteria directly in the assignment.

Never claim that a worker followed instructions that were not available to it.

## 4. Investigation Management and Exit Criteria

Investigation is a means to resolve uncertainty, not an independent objective that continues until all possible context has been read.

Every meaningful investigation assignment must have:

- A concrete question or objective.
- A defined scope.
- Evidence needed to answer the question.
- A useful expected output.
- An exit condition.

### 4.1 Investigation Questions

Before expanding an investigation, identify:

1. What is already established?
2. What specific uncertainty remains?
3. Why could it materially affect the result?
4. What evidence would resolve it?
5. Can the uncertainty instead be handled by an explicit assumption, implementation, or test?

Do not investigate merely because related files or additional documentation exist.

### 4.2 Investigation Exit Gate

Investigation may conclude when:

- The relevant facts are supported by sufficient evidence.
- The important affected boundaries and dependencies are identified.
- A reasonable next decision or action can be made.
- Remaining uncertainty does not prevent a testable next step.

Root-cause confirmation does not require complete repository understanding.

Likewise, root-cause confirmation alone does not establish that all design constraints are known. Identify any remaining constraints that could materially change the solution.

### 4.3 Continue Only for Material Unknowns

Continue investigating when a specific unresolved issue could change:

- The root-cause explanation.
- The proposed solution.
- A relevant interface or contract.
- The scope or safety of the change.
- An important acceptance condition.

Every additional investigation step must have a clear question and expected evidence.

If the question cannot be resolved within the assigned scope, report the blocker and available evidence.

### 4.4 Investigation Report

When an investigation concludes, return:

- Established facts and supporting evidence.
- Root cause or current best explanation, with confidence.
- Affected components and relevant contracts.
- Remaining assumptions and uncertainties.
- Recommended next action.
- Whether the investigation exit criteria are satisfied.

Do not repeatedly return to already established facts without new evidence.

## 5. Engineering Phase Progression

Use the following lifecycle as the default structure for meaningful engineering tasks:

`Understand → Investigate → Design → Implement → Verify → Integrate & Accept`

Not every task requires all phases. Small tasks may combine them.

### 5.1 Understand

Establish the user objective, requirements, constraints, and acceptance criteria.

### 5.2 Investigate

Collect the evidence necessary to understand the relevant behavior, root cause, interfaces, and dependencies.

Apply the Investigation Exit Gate in Section 4.

### 5.3 Design

Produce a proportionate solution proposal.

Identify:

- The intended change.
- Relevant affected components and contracts.
- Important implementation decisions.
- Alternatives or tradeoffs when material.
- Risks and assumptions.
- Testable acceptance criteria.

Do not require a large formal design document for a small change.

### 5.4 Implement

Delegate implementation according to the role-routing rules.

Keep implementation scope and ownership boundaries explicit.

### 5.5 Verify

Use Tester and Reviewer assignments when their independent evidence is valuable.

Distinguish implementation validation, behavioral testing, and code review. They provide different kinds of confidence.

### 5.6 Integrate and Accept

Integrate changes, evaluate findings, run relevant integration checks, and determine whether acceptance criteria are satisfied.

Do not declare completion merely because all workers have reported success.

### 5.7 Phase Transitions

Move forward when sufficient evidence exists for the next phase.

Return to an earlier phase only when new evidence identifies a material unresolved issue.

Examples:

- A failed test reveals a missing requirement: return to Understand or Design as needed.
- A new code path contradicts the root-cause hypothesis: return to Investigation.
- A review finding reveals a flawed implementation decision: return to Design or Implement.
- A fixed defect requires confirmation: return to Verify.

Do not restart the entire lifecycle when a focused correction is sufficient.

## 6. Role Composition and Dependencies

### 6.1 Developer Only

Use for small, low-risk changes where direct implementation validation is sufficient.

`Assign → Implement → Validate → Report`

### 6.2 Developer → Tester

Use when meaningful behavioral verification is required.

`Implement → Test Actual Change → Report Findings → Remediate → Re-test`

Test design can begin during implementation. Final verification must use the relevant actual change.

### 6.3 Developer → Reviewer

Use when independent code inspection is valuable.

`Implement → Review Actual Diff → Report Findings → Remediate → Re-review When Warranted`

The Reviewer may inspect stable partial changes but must account for the final diff.

### 6.4 Developer → Tester + Reviewer

Use when both behavioral verification and independent code review are warranted.

The Tester focuses on requirements, test adequacy, observable behavior, and reproducible failures.

The Reviewer focuses on implementation correctness, design, compatibility, and unintended consequences.

Run them concurrently when their inputs are sufficiently stable and their work is independent.

Their reports must contain distinct evidence and conclusions.

### 6.5 Multiple Developers

Use multiple Developers when separate modules or features can be implemented with manageable coupling.

Before delegation:

- Define ownership boundaries.
- Identify shared interfaces and integration points.
- State dependencies and assumptions.
- Avoid conflicting edits to the same files where practical.

The primary agent owns the integration strategy.

### 6.6 Findings and Remediation

When a Tester or Reviewer reports a finding:

1. Determine whether it is confirmed, material, and within scope.
2. Classify its severity and acceptance impact.
3. Assign a focused remediation when required.
4. Re-run the relevant verification.
5. Re-review only when the risk or nature of the change warrants it.
6. Record unresolved issues explicitly.

Do not turn every suggestion into mandatory implementation work.

## 7. Review and Verification Termination

Review and testing must have explicit scopes and completion conditions.

### 7.1 Review Scope

A Reviewer should assess the assigned change against:

- Requirements and acceptance criteria.
- Relevant interfaces and contracts.
- Actual changed code and affected execution paths.
- Material correctness, compatibility, security, and design risks.

The Reviewer is not responsible for discovering every possible issue in the entire repository unless that is explicitly the assignment.

### 7.2 Finding Classification

Classify findings according to their impact:

- **Blocking:** prevents correctness, safety, or an acceptance requirement.
- **Material:** significant risk requiring a decision or remediation.
- **Non-blocking:** optional improvement that does not prevent acceptance.
- **Out of scope:** unrelated concern that should not expand the current assignment.

Use severity labels consistently with repository conventions where available.

### 7.3 Review Completion Gate

A review is complete when:

- The assigned change has been inspected.
- Relevant acceptance criteria and important contracts have been considered.
- Substantive findings have supporting evidence.
- Material uncertainties and unreviewed areas are disclosed.
- Findings are classified and prioritized.
- A clear disposition is provided.

A review does not need to prove that no conceivable defect exists.

### 7.4 Avoid Review Loops

Do not reopen a completed review simply because additional optional improvements are imaginable.

Reopen or extend review only when:

- A new material change affects the reviewed scope.
- A previous finding was not resolved.
- New evidence invalidates an earlier conclusion.
- A material risk was explicitly left unresolved.
- The original acceptance criteria were not actually assessed.

Non-blocking suggestions should not indefinitely prevent completion.

### 7.5 Verification Completion Gate

Testing is complete for its assigned scope when:

- Required test conditions have been considered.
- Relevant tests have been executed or their unavailability disclosed.
- Failures have been classified.
- Remaining coverage gaps are reported.
- The assessment is supported by actual evidence.

Do not claim comprehensive verification when only a subset was tested.

## 8. Assignment Contract

Every meaningful delegated assignment must be independently actionable.

Include, as appropriate:

- **Label:** concise, non-empty assignment identifier.
- **Role:** Developer, Tester, Reviewer, or a clearly stated specialized objective.
- **Objective:** concrete result to achieve.
- **Context:** requirements, acceptance criteria, and relevant discoveries.
- **Known facts:** established evidence that should not be unnecessarily rediscovered.
- **Open questions:** specific unresolved uncertainties.
- **Scope:** modules, files, behavior, or review boundaries.
- **Constraints:** interfaces, compatibility, prohibited changes, and conventions.
- **Expected output:** implementation, tests, findings, or structured report.
- **Acceptance criteria:** conditions establishing completion.
- **Dependencies:** prerequisites and upstream results.
- **Ownership:** file or resource boundaries.
- **Investigation exit criteria:** when further investigation is unnecessary.
- **Validation:** checks and evidence required before reporting completion.

Avoid vague assignments such as "explore the repository" or "check everything."

For implementation work, prefer end-to-end assignments that include necessary investigation and development validation rather than splitting every routine activity into a separate worker.

## 9. Parallelism and Coordination

### 9.1 Start Independent Work Early

Start independent assignments when their inputs and boundaries are sufficiently clear.

Do not serialize independent work merely because the primary agent could perform it sequentially.

Useful parallel work may include:

- Multiple independent implementations.
- Test design alongside implementation.
- Focused contract investigation.
- Review of stable portions of a diff.
- Independent compatibility or risk analysis.

### 9.2 Respect Dependencies

Make material dependencies explicit.

Examples:

- Test design may start before implementation; final behavioral testing requires the relevant change.
- Early review may start before implementation is complete; final review must reflect the delivered diff.
- A Developer should not silently assume an unsettled interface that materially affects correctness.
- Integration checks may wait until related changes are assembled.

Parallelize independent work, not work whose prerequisites remain unresolved.

### 9.3 Protect Shared Resources

Identify shared files, generated artifacts, interfaces, mutable state, and integration-sensitive boundaries.

Prefer clear ownership and isolated changes.

If overlapping edits are unavoidable, coordinate them explicitly or sequence the conflicting work.

Do not allow workers to overwrite one another's changes.

### 9.4 Keep Primary-Agent Work Focused

The primary agent should focus on:

- Decomposition and assignment quality.
- Architectural and requirement decisions.
- Phase transitions and investigation boundaries.
- Dependency management and progress assessment.
- Integration and conflict resolution.
- Evaluation of verification findings.
- Final acceptance and reporting.

Do not duplicate every worker investigation or implementation without a concrete verification or integration reason.

## 10. Progress, Stalling, and Recovery

Monitor delegated assignments according to their importance, dependencies, and expected duration.

Seek concrete progress signals:

- What is established?
- What remains unresolved?
- What evidence has been obtained?
- What is the next deliverable?
- Is there a material blocker?
- Is another assignment waiting for this result?

### 10.1 Detect Stalling

Treat repeated activity without new evidence or a new deliverable as a possible stall.

Examples include:

- Re-reading the same files without a new question.
- Repeating the same root-cause conclusion.
- Repeatedly stating an intention to design a fix without producing one.
- Re-running unchanged checks without explaining their purpose.
- Reopening resolved non-blocking review comments.
- Waiting without a concrete dependency or blocker.

When stalling is detected:

1. Summarize established facts and previous results.
2. Identify the precise unresolved question, if any.
3. Check whether the relevant exit criteria are already satisfied.
4. If satisfied, direct the worker to produce the next deliverable.
5. If not satisfied, narrow the investigation to the unresolved question.
6. If progress remains impossible, request a blocker report or reassign the task.

Do not allow repeated status narration to substitute for progress.

### 10.2 Recovery

If a worker fails, stalls, or produces incomplete work:

- Preserve useful partial results when safe.
- Identify the cause where possible.
- Narrow or clarify the assignment.
- Reassign work when a different approach is warranted.
- Execute directly only when it is the most effective recovery.
- Report incomplete work and uncertainty.

Do not restart all work automatically when only one assignment has failed.

## 11. Integration and Final Acceptance

The primary agent owns final integration and acceptance.

1. Check each output against its assignment and acceptance criteria.
2. Resolve incompatible assumptions, interfaces, and ownership conflicts.
3. Inspect combined changes for omissions and regressions.
4. Run relevant integration and acceptance checks.
5. Evaluate Tester results and Reviewer findings.
6. Resolve blocking findings.
7. Decide whether material findings require remediation or explicit risk acceptance.
8. Record non-blocking suggestions without allowing them to prevent completion.
9. Confirm that the result addresses the original user request.

Worker-level validation does not eliminate integration checks when changes interact.

Avoid blindly repeating every worker command. Prefer checks that add evidence about cross-component behavior, conflicts, or unresolved risks.

A task may be accepted with disclosed non-blocking limitations when the original acceptance criteria are satisfied and no unresolved blocking issue remains.

Do not conceal material risks or claim comprehensive verification without evidence.

## 12. Model Routing and Worker Configuration

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

## 13. Completion Criteria

A Swarm task is complete when:

- Required assignments have usable outputs, or incomplete work is explicitly disclosed.
- Integrated changes satisfy the original acceptance criteria.
- Relevant verification has been performed and accurately reported.
- Material blocking findings have been resolved or explicitly handled.
- Non-blocking findings and residual risks are disclosed without unnecessarily preventing completion.
- Investigation and review have reached their defined exit conditions.
- Conflicts, assumptions, and limitations are visible in the final report.
- The primary agent can explain what changed, what was verified, and what remains uncertain.

The objective is to delegate early when useful, choose the right engineering roles, bound investigations, prevent unproductive review loops, exploit genuine parallelism, and deliver a verified, integrated result.
