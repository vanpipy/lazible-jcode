OK. Going forward I will use **Mermaid** consistently to describe the architecture, state machines, DAG, Git/worktree, and agent collaboration.

Below is the previous core design rewritten in Mermaid.

> **Implementation status note** (2026-09-28): the original architecture envisioned 4 profiles (default / autonomous / conservative / research).
> In practice only the `autonomous` profile remains : the others were no-ops or referenced unimplemented hooks.
> The multi-profile architecture below is kept as the **vision**; the current actual state is at [`config/profiles/README.md`](config/profiles/README.md).

## 1. Overall architecture

```mermaid
flowchart TB
    U[Human<br/>Issue / Specification]

    A[Ambient / Scheduler<br/>When should we work?]
    P[Global Policy / Profile<br/>How autonomous should it be?]
    O[Orchestrator<br/>What needs to happen?]
    D[Task DAG<br/>What depends on what?]

    W1[Research Worker]
    W2[Implementation Worker]
    W3[Test Worker]
    W4[Review Worker]

    I[Integration]
    V[Validation]
    R[Repair]
    PR[Pull Request]
    H[Human Gate]

    U --> A
    A --> P
    P --> O
    O --> D

    D --> W1
    D --> W2
    D --> W3

    W1 --> I
    W2 --> I
    W3 --> I

    I --> W4
    W4 --> V

    V -->|PASS| PR
    V -->|FAIL| R
    R --> D

    PR --> H
```

---

## 2. Global configuration and project configuration

```mermaid
flowchart TB
    G[~/.jcode]

    C[config.toml]
    P[profiles]
    PR[prompts]
    W[workflows]
    PO[policies]
    T[templates]
    S[state]
    AM[ambient]

    G --> C
    G --> P
    G --> PR
    G --> W
    G --> PO
    G --> T
    G --> S
    G --> AM

    P --> PD[default]
    P --> PA[autonomous]
    P --> PC[conservative]
    P --> PRS[research]

    Repo[Project Repository]
    AG[AGENTS.md]

    Repo --> AG

    C --> Runtime[Agent Runtime]
    P --> Runtime
    PR --> Runtime
    W --> Runtime
    PO --> Runtime
    T --> Runtime

    AG --> Runtime
```

Configuration priority:

```mermaid
flowchart BT
    G[Global Defaults]
    P[Active Profile]
    A[Project AGENTS.md]
    T[Current Task / User Prompt]

    G --> P
    P --> A
    A --> T

    T --> E[Effective Agent Context]
```

Safety is a special layer; ordinary project configuration cannot lower the safety level:

```mermaid
flowchart TB
    S[Global Safety Policy]
    G[Global Agent Policy]
    A[Project AGENTS.md]
    T[Task]

    S --> G
    G --> A
    A --> T

    S -. "cannot be weakened" .-> A
    S -. "cannot be weakened" .-> T
```

---

# 3. The `~/.jcode` directory

```mermaid
graph TD
    J["~/.jcode/"]

    J --> C["config.toml"]

    J --> P["profiles/"]
    P --> P1["default/"]
    P --> P2["autonomous/"]
    P --> P3["conservative/"]
    P --> P4["research/"]

    J --> PR["prompts/"]
    PR --> PR1["orchestrator.md"]
    PR --> PR2["worker.md"]
    PR --> PR3["reviewer.md"]
    PR --> PR4["tester.md"]

    J --> W["workflows/"]
    W --> W1["feature.md"]
    W --> W2["bugfix.md"]
    W --> W3["refactor.md"]
    W --> W4["research.md"]

    J --> PO["policies/"]
    PO --> PO1["autonomy.md"]
    PO --> PO2["git.md"]
    PO --> PO3["safety.md"]
    PO --> PO4["validation.md"]

    J --> T["templates/"]
    T --> T1["task.md"]
    T --> T2["handoff.md"]
    T --> T3["report.md"]

    J --> S["state/"]
    S --> S1["tasks/"]
    S --> S2["runs/"]
    S --> S3["logs/"]

    J --> AM["ambient/"]
    AM --> AM1["state.json"]
    AM --> AM2["queue.json"]
    AM --> AM3["usage.json"]
    AM --> AM4["logs/"]
```

---

# 4. Autonomous Coding Control Loop

This is the core state machine of the whole system:

```mermaid
stateDiagram-v2
    [*] --> Receive

    Receive --> Understand
    Understand --> Plan
    Plan --> Decompose
    Decompose --> Schedule

    Schedule --> Execute
    Execute --> Observe
    Observe --> Verify

    Verify --> Review: PASS
    Verify --> Diagnose: FAIL

    Diagnose --> Repair
    Repair --> Execute

    Review --> FinalValidation: PASS
    Review --> Repair: FINDINGS

    FinalValidation --> PR: PASS
    FinalValidation --> Diagnose: FAIL

    PR --> HumanGate
    HumanGate --> [*]
```

The most critical part is:

```text
FAIL
 ↓
Diagnose
 ↓
Repair
 ↓
Execute
 ↓
Verify
```

Rather than:

```text
FAIL → "try again"
```

---

# 5. Feature Workflow

```mermaid
flowchart TD
    Start([Feature Request])

    Analyze[Analyze Repository]
    Context[Read AGENTS.md<br/>+ Global Policy]
    Plan[Create Implementation Plan]
    DAG[Build Task DAG]

    Research[Research]
    Backend[Backend Implementation]
    Frontend[Frontend Implementation]
    Tests[Test Implementation]

    Integrate[Integration]
    Review[Adversarial Review]
    Validate[Full Validation]
    E2E[E2E / Browser Test]

    Diagnose[Diagnose Failure]
    Repair[Create Repair Task]

    PR[Create PR]
    Human[Human Approval]

    Start --> Analyze
    Analyze --> Context
    Context --> Plan
    Plan --> DAG

    DAG --> Research
    DAG --> Backend
    DAG --> Frontend
    DAG --> Tests

    Research --> Integrate
    Backend --> Integrate
    Frontend --> Integrate
    Tests --> Integrate

    Integrate --> Review
    Review -->|Findings| Repair
    Repair --> DAG

    Review -->|Clean| Validate
    Validate -->|Fail| Diagnose
    Diagnose --> Repair

    Validate -->|Pass| E2E
    E2E -->|Fail| Diagnose
    E2E -->|Pass| PR

    PR --> Human
```

---

# 6. Swarm / DAG

The recommended DAG for a medium feature:

```mermaid
flowchart TD
    T0["T0: Understand Repository"]

    T1["T1: Architecture / Research"]
    T2["T2: Backend Implementation"]
    T3["T3: Frontend Implementation"]
    T4["T4: Test Design"]

    T5["T5: Backend Tests"]
    T6["T6: Frontend Tests"]

    T7["T7: Integration"]
    T8["T8: Adversarial Review"]
    T9["T9: Full Validation"]
    T10["T10: E2E"]

    T0 --> T1
    T0 --> T2
    T0 --> T3
    T0 --> T4

    T2 --> T5
    T3 --> T6
    T4 --> T5
    T4 --> T6

    T1 --> T7
    T5 --> T7
    T6 --> T7

    T7 --> T8
    T8 --> T9
    T9 --> T10
```

This is **not** "always exactly 6 agents".

The real logic is:

```mermaid
flowchart LR
    Task[Task]

    Analyze[Analyze]
    Split{Composite?}

    Single[Single Worker]
    DAG[Build DAG]

    Task --> Analyze
    Analyze --> Split

    Split -->|No| Single
    Split -->|Yes| DAG
```

---

# 7. Workers and Handoff

```mermaid
flowchart LR
    O[Orchestrator]

    T[Task Node]
    W[Worker]
    A[Handoff Artifact]
    N[Next Task]

    O --> T
    T --> W
    W --> A
    A --> N

    A -. "findings" .-> N
    A -. "evidence" .-> N
    A -. "validation" .-> N
    A -. "edge cases" .-> N
    A -. "open questions" .-> N
    A -. "confidence" .-> N
    A -. "what I did not check" .-> N
```

The recommended principle here:

> **DAG edges are the normal communication channel; agent-to-agent chat is the exception channel.**

```mermaid
flowchart LR
    A[Agent A]
    Artifact[Typed Handoff]
    B[Agent B]

    A --> Artifact --> B

    A -. "exception only" .-> B
```

---

# 8. Git / Worktree

Default:

```mermaid
gitGraph
    commit id: "main"
    branch agent/task-123
    checkout agent/task-123
    commit id: "implementation"
    commit id: "tests"
    commit id: "review-fixes"
```

End state:

```mermaid
flowchart LR
    Main[main]

    Task["agent/task-123"]

    Worker[Workers]
    Validate[Validation]
    PR[Pull Request]
    Human[Human Merge]

    Main --> Task
    Task --> Worker
    Worker --> Validate
    Validate --> PR
    PR --> Human
    Human --> Main
```

---

# 9. Worktree auto-strategy

```mermaid
flowchart TD
    Task[Task]

    Analyze[Analyze File Ownership]
    Conflict{High File Conflict?}
    Risk{High Risk / Large Refactor?}

    Shared[Shared Workspace]
    WT[Dedicated Worktree]

    Task --> Analyze
    Analyze --> Conflict

    Conflict -->|No| Risk
    Conflict -->|Yes| WT

    Risk -->|No| Shared
    Risk -->|Yes| WT
```

So:

```text
worktree ≠ agent

worktree = isolation boundary
```

---

# 10. Validation Pipeline

```mermaid
flowchart TD
    Code[Implementation]

    W[Worker Validation]
    I[Integration Validation]
    R[Review]
    E[E2E]
    F[Final Validation]

    Code --> W
    W -->|PASS| I
    W -->|FAIL| Fix1[Repair]

    Fix1 --> W

    I -->|PASS| R
    I -->|FAIL| Fix2[Repair]

    Fix2 --> I

    R -->|PASS| E
    R -->|FINDINGS| Fix3[Repair]

    Fix3 --> R

    E -->|PASS| F
    E -->|FAIL| Fix4[Repair]

    Fix4 --> E

    F --> Done([Verified])
```

---

# 11. Review Gate

```mermaid
flowchart TD
    Implementation[Implementation]

    Reviewer[Independent Reviewer]

    Reviewer --> Requirements[Requirements]
    Reviewer --> Diff[Git Diff]
    Reviewer --> Architecture[Architecture]
    Reviewer --> Tests[Tests]
    Reviewer --> Security[Security]
    Reviewer --> Edge[Edge Cases]

    Requirements --> Decision{Findings?}
    Diff --> Decision
    Architecture --> Decision
    Tests --> Decision
    Security --> Decision
    Edge --> Decision

    Decision -->|No| Verify[Validation]
    Decision -->|Yes| Repair[Repair Tasks]

    Repair --> Implementation
```

Reviewer principle:

```text
Coder != Reviewer
```

---

# 12. Repair Loop

```mermaid
stateDiagram-v2
    [*] --> Implementation

    Implementation --> Validation

    Validation --> Success: PASS
    Validation --> Failure: FAIL

    Failure --> Diagnosis
    Diagnosis --> RepairTask
    RepairTask --> Implementation

    Success --> [*]
```

For stricter control, you can:

```mermaid
flowchart LR
    V[Validation]
    F[Failure]
    D[Diagnosis]
    R[Repair]
    C{Retry Count < 3?}
    Human[Human Escalation]

    V -->|FAIL| F
    F --> D
    D --> R
    R --> C

    C -->|Yes| V
    C -->|No| Human
```

This prevents an agent from looping on repair indefinitely.

---

# 13. Safety Boundary

```mermaid
flowchart TB
    Agent[Autonomous Agent]

    Local[Local / Reversible]
    External[External Side Effect]

    Agent --> Local
    Agent --> External

    Local --> L1[Read Files]
    Local --> L2[Edit Files]
    Local --> L3[Run Tests]
    Local --> L4[Create Branch]
    Local --> L5[Create Worktree]
    Local --> L6[Local Commit]

    External --> E1[git push]
    External --> E2[Create PR]
    External --> E3[Merge]
    External --> E4[Deploy]
    External --> E5[External API]
```

Recommendation:

```mermaid
flowchart LR
    Action[Agent Action]

    Auto[Auto Execute]
    Gate[Permission Gate]

    Action --> Decision{External Side Effect?}

    Decision -->|No| Auto
    Decision -->|Yes| Gate
```

---

# 14. Ambient + Autonomous Coding

Adding the 24/7 mode:

```mermaid
flowchart TB
    Ambient[Ambient Scheduler]

    Queue[Task Queue]
    Orchestrator[Orchestrator]

    DAG[Task DAG]
    Workers[Worker Pool]
    Validation[Validation]
    PR[PR]

    Ambient --> Queue
    Queue --> Orchestrator
    Orchestrator --> DAG
    DAG --> Workers
    Workers --> Validation
    Validation --> PR
```

The four concepts, then:

```mermaid
flowchart LR
    Ambient["Ambient<br/>When?"]
    Orchestrator["Orchestrator<br/>What?"]
    DAG["DAG<br/>Dependencies?"]
    Worker["Workers<br/>How?"]

    Ambient --> Orchestrator
    Orchestrator --> DAG
    DAG --> Worker
```

I recommend keeping this layering.

---

# 15. Final six-layer architecture

One diagram to summarize the whole design:

```mermaid
flowchart TB
    subgraph L1["Layer 1 : Scheduling"]
        Ambient["Ambient / Scheduler<br/>When should we work?"]
    end

    subgraph L2["Layer 2 : Policy"]
        Global["Global Config / Profile"]
        Safety["Safety Policy"]
    end

    subgraph L3["Layer 3 : Intelligence"]
        Orch["Orchestrator<br/>What should happen?"]
    end

    subgraph L4["Layer 4 : State"]
        DAG["Task DAG<br/>Dependencies / Handoff"]
    end

    subgraph L5["Layer 5 : Execution"]
        Workers["Worker Pool"]
        Worktree["Git / Worktree"]
    end

    subgraph L6["Layer 6 : Trust"]
        Review["Review"]
        Test["Validation"]
        E2E["E2E"]
        Gate["Human Gate"]
    end

    Ambient --> Global
    Global --> Orch
    Safety --> Orch
    Orch --> DAG
    DAG --> Workers
    Workers --> Worktree
    Worktree --> Review
    Review --> Test
    Test --> E2E
    E2E --> Gate
```

### Mapping

| Layer | Core question | Components |
| - | ------------- | -------------------------------- |
| 1 | **When should we work?** | Ambient |
| 2 | **How are we allowed to work?** | Global Config / Profile / Safety |
| 3 | **What should we do?** | Orchestrator |
| 4 | **How do tasks relate?** | DAG |
| 5 | **Who actually executes?** | Workers / Git / Worktree |
| 6 | **How do we prove completion?** | Review / Test / E2E / Human |

The project's own `AGENTS.md` can be thought of as a **Repository Context Layer** spanning the middle tiers:

```mermaid
flowchart LR
    Global[Global jcode]
    Profile[Profile]
    AGENTS["Project AGENTS.md"]
    Task[Current Task]
    Runtime[Effective Runtime Context]

    Global --> Profile
    Profile --> AGENTS
    AGENTS --> Task
    Task --> Runtime
```

**This is the v1 architecture I recommend we lock in.**

When implementation begins, the most sensible next step is: **first define the 4 core schemas : `config.toml`, Task/DAG node, Handoff Artifact, Validation Result.** Once those four are fixed, the `orchestrator.md`, worker/reviewer prompts, workflows, and the Git/worktree controller can all be built around them without ending up as a tangle of cross-coupled prompts.