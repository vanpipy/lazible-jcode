# Autonomous Coding Framework — Bundle Mapping

> **Status:** active / current
> **Source spec:** `new.md` (jcode Autonomous Coding Framework)
> **Audience:** anyone reading the bundle to understand what it ships
> and why. Most users only need the `~/.jcode/prompt-overlay.md` +
> `~/.jcode/swarm-prompt.md` they see at runtime; this doc is for
> bundle maintainers + curious readers.

This document maps the design in `new.md` onto the bundle's actual
artifacts. It exists so:

- A bundle maintainer can see at a glance which file owns which
  concept (profile, workflow, role, safety, etc.).
- A new contributor can answer "where does X live?" without reading
  every file.
- The orchestrator and worker prompts can stay lean and point at
  this document for deep detail.

---

## 1. Goals & non-goals

**In scope (what the bundle covers):**

- A **generic orchestrator profile** that runs over jcode's native
  DAG engine — not a domain-specific (e.g. finance / investment
  research) overlay.
- A **profile system** that selects workflow + effort + autonomy
  level via prompt logic.
- A **typed-artifact contract** enforced across all worker roles
  (7 base fields + `status` enum).
- A **safety model** that classifies actions into auto-allowed vs
  requires-permission tiers and forbids `git push` to main without
  verbatim user OK.
- A **clean separation** between orchestrator-side concerns
  (`prompt-overlay.md`), worker-side concerns (`swarm-prompt.md`),
  and per-role persona (`roles/*.md`).
- **Coverage of `new.md`'s 27 sections**, mapped to the bundle's
  actual artifacts.

**Out of scope (explicitly deferred):**

- New top-level directories (`profiles/`, `workflows/`, `policies/`,
  `templates/`, `state/`, `ambient/`). jcode does not read these; the
  bundle does not invent them.
- A `[profile]` / `[workflow]` / `[autonomy]` / `[git]` config schema
  in `~/.jcode/config.toml`. jcode does not parse these keys; writing
  them would be dead config.
- Ambient-mode memory consolidation / proactive work. jcode's
  `AMBIENT_MODE.md` is design-phase (Phases 2-5 TODO); the bundle
  does not reimplement what the engine will eventually provide.
- Runtime tier enforcement. `SAFETY_SYSTEM.md` is design-phase
  (Phases 1-5 TODO); the bundle keeps safety at the prompt level
  (see §6).

**Non-goals (intentionally not pursued):**

- **Pre-baked persona**. The bundle ships a generic orchestrator, not
  an investment-researcher (or any other domain-specific) persona.
  Users who want a persona can re-attach at the user layer
  (`~/.jcode/AGENTS.md` or a project overlay).
- Domain-specific workers (finance / quant / investment-research
  pipelines). The bundle ships generic engineering roles only.
- A `jcode-autonomous` wrapper script. If needed, the profile
  detection in `prompt-overlay.md` §1 already routes users to the
  right effort rung; a wrapper is redundant until a non-prompt-layer
  feature lands.

---

## 2. The six-layer model (and what backs each layer)

`new.md` §24 collapses the design into:

```
1. Ambient / scheduler      — when should agent work?
2. Global Policy / Profile  — how autonomous should it be?
3. Orchestrator             — what needs to happen?
4. Task DAG                 — what depends on what?
5. Workers                  — actually perform the work.
6. Git + Validation + Safety — can we trust and ship the result?
```

The bundle maps each layer to a specific file + jcode mechanism.

| # | Layer | Bundle artifact | jcode mechanism | Status |
|---|---|---|---|---|
| 1 | Ambient / scheduler | (none — engine-owned) | `[ambient]` config + `schedule_ambient` tool | **Engine-side; design-phase for memory garden / proactive work. Bundle does not implement.** |
| 2 | Profile / autonomy | `swarm/prompt-overlay.md` §1 | (prompt-level) — orchestrator reads user intent + sets `effort = "swarm" \| "swarm-deep"` | **Live** (the bundle's contribution: 4 profiles → 2 effort rungs) |
| 3 | Orchestrator | `swarm/prompt-overlay.md` | base system prompt + `AGENTS.md` + overlay; `swarm task_graph` for DAG | **Live** |
| 4 | Task DAG | (orchestrator-side API call) | `swarm task_graph`, `expand_node`, `complete_node`, `inject_gap` | **Live** (jcode-native, see `docs/SWARM_TASK_GRAPH.md`) |
| 5 | Workers | `swarm/roles/*.md` (6 files) + `swarm/swarm-prompt.md` | `swarm spawn` (orchestrator inlines role body into spawn prompt) | **Live** (typed-artifact contract enforced per role) |
| 6 | Git + Validation + Safety | `swarm/prompt-overlay.md` §6 + `swarm/swarm-prompt.md` §8 | git worktrees (worktree-backing workspaces) + slice-scoped gates + prompt-level safety | **Live at prompt level**; runtime tier enforcement is engine-side design-phase |

Cross-cutting: `AGENTS.md` (project + global, loaded by jcode native)
provides repo-specific context for layers 3-5 only. It does **not**
pick profile or workflow — those are bundle concerns.

---

## 3. Profile system (4 profiles → 2 effort rungs)

`new.md` §6 specifies 4 profiles. The bundle implements them in
`prompt-overlay.md` §1.

| Profile | `effort` value | Default workflow | When to use |
|---|---|---|---|
| `default` | (model default) | none — answer directly | trivial / Q&A / small fix |
| `research` | `swarm` | `research` | explore before deciding |
| `conservative` | (model default) | `bugfix` or `refactor` | tight scope, no parallel fan-out |
| `autonomous` | `swarm-deep` | `feature` | multi-stage work with critique/verify gates |

**Why two rungs, not four.** jcode natively recognizes two swarm
effort sentinels: `swarm` (light fan-out) and `swarm-deep` (DAG-first
with gates). The four profiles collapse onto two rungs because that's
what the engine offers. The `default` and `conservative` profiles
both use the model's default effort — they differ in workflow only
(answer vs bugfix vs refactor).

**Why this matters.** Setting `effort = "swarm-deep"` on the first
dispatch of an `autonomous` session makes jcode inject
`SWARM_DEEP_EFFORT_DIRECTIVE` (in `crates/jcode-base/src/prompt.rs`)
which contains the full DAG-first + typed-handoff + gate-discipline
prose. The orchestrator does **not** need to repeat that prose — the
engine supplies it. This is the central trick of the design.

---

## 4. Workflow system (4 workflows)

`new.md` §8 specifies 4 workflows. The bundle implements them in
`prompt-overlay.md` §2.

| Workflow | Stages | Default role mapping |
|---|---|---|
| `feature` | understand → explore → plan → implement → verify → review → integrate → PR | `implementer`, `reviewer`, `test-writer` |
| `bugfix` | reproduce → diagnose → fix → regression-test → review | `implementer`, `test-writer`, `reviewer` |
| `refactor` | understand → dependency-analysis → plan → incremental-refactor → test → api-compat → review | `migrator`, `test-writer`, `reviewer` |
| `research` | explore (composite) → critique → synthesize | `investigator` + `reviewer` |

Composing workflows: a feature that contains a refactor slice runs
`refactor` on the slice first (as a composite DAG node), then
`feature` on the rest. Native DAG semantics.

**Picking.** The orchestrator picks by user intent. Trivial
clarifications and Q&A do not pick a workflow — they answer in the
default profile.

---

## 5. Role model (4 prompts, 6 in the bundle)

`new.md` §9-12 names 4 roles: orchestrator, worker, reviewer, tester.
The bundle ships **6 engineering roles** (4 generic + 2 extras):

| Bundle role | `new.md` equivalent | When |
|---|---|---|
| `implementer` | worker | feature / bugfix implementation |
| `reviewer` | reviewer | adversarial review |
| `test-writer` | tester | test scaffolding / coverage |
| `migrator` | worker (specialized) | cross-module refactor |
| `investigator` | (not in new.md; research profile worker) | read-only research / hypothesis |
| `doc-writer` | (not in new.md; supplementary) | docs / comments / README |

**Why the two extras:**

- `investigator` powers the `research` profile — it is the role the
  orchestrator dispatches for the `explore → critique → synthesize`
  shape.
- `doc-writer` is a thin specialization of `implementer` for changes
  that are pure markdown. Some projects want clean review history for
  doc changes; others are happy folding them into `implementer`. The
  bundle ships it as a separate role for clarity, not necessity.

Every role's typed artifact carries the **same 7 base fields** plus
`status`. The 8-field contract is invariant.

---

## 6. Typed artifact contract (the spine)

The contract — defined per role in `roles/*.md` `## Output schema`
sections and enforced by the engine in `swarm-deep` mode — is layered:

- **Engine's `HandoffArtifact`** (the typed handoff payload attached
  to a node on completion; `crates/jcode-plan/src/dag/mod.rs:262`).
  7 fields, `findings` + `confidence` + non-empty `what_i_did_not_check`
  are hard-required in deep mode; the rest are optional.
- **Bundle extension** (this section). The bundle requires one extra
  field on every artifact: `status ∈ {completed, partial, needs-info,
  blocked}`. The engine does not read it. The bundle's orchestrator
  uses it to pick accept / reject / re-spawn decisions.

### 6.1 Engine schema (`crates/jcode-plan/src/dag/mod.rs:262`)

```rust
pub struct HandoffArtifact {
    pub findings: String,
    pub evidence: Vec<String>,           // file:line, commit refs, paths
    pub edge_cases_considered: Vec<String>,
    pub validation: Option<String>,
    pub open_questions: Vec<String>,
    pub confidence: Option<String>,      // parses to Low|Medium|High
    pub what_i_did_not_check: Vec<String>,
}
```

`evidence` is `Vec<String>` (free-form refs like `"path:line"` or a
commit SHA), NOT `{commit, files_changed}` objects. Other optional
fields use `skip_serializing_if = "Vec::is_empty"` so they are omitted
when empty.

### 6.2 Engine-enforced (deep mode)

`complete_node` calls `validate_artifact` in
`crates/jcode-plan/src/dag/ops.rs:703`. In deep mode, non-gate
artifacts MUST:

- Have non-empty `findings` (string, after trim).
- Have non-empty `what_i_did_not_check` (the only acceptable "empty"
  is an explicit `"nothing, fully covered"` entry on truly exhaustive
  work — the field is mandatory because gates read it).
- Have parseable `confidence ∈ {low, medium, high}`. Honest `low` is
  welcome; missing / unparseable values are rejected the same way as
  thin findings.

Failing any of these returns `DagError::ThinArtifact` and the
artifact is rejected. Light mode accepts any artifact.

### 6.3 Bundle contract (what to emit)

```json
{
  "status": "completed" | "partial" | "needs-info" | "blocked",
  "findings": "<string>",
  "evidence": ["<file:line>", "<commit-sha>", "<path>", ...],
  "edge_cases_considered": ["..."],
  "validation": "...",
  "open_questions": ["..."],
  "confidence": "low" | "medium" | "high",
  "what_i_did_not_check": ["..."]
}
```

Plus role-specific fields (e.g., `findings[]` with `severity` for
`reviewer`, `tests_added[]` for `test-writer`).

**Invariants:**

1. The artifact MUST end with a parseable ```` ```json ```` fenced
   block. The engine's prompt needs the JSON to hydrate downstream
   nodes; prose-only summaries fail the dataflow.
2. `evidence[]` items are free-form strings (`"path:line"`, commit
   SHA, URL). Objects are not the wire format.
3. `validation` MUST list actual gate commands run (not "looks good").
4. `what_i_did_not_check[]` MUST be non-empty in deep mode (engine
   hard requirement) and SHOULD list genuinely-unrun items on
   non-trivial work (bundle honesty rule).
5. `confidence` MUST parse to `low | medium | high`. Honest `low` is
   welcomed by the gate machinery.
6. `status` is bundle-side (engine reads `NodeStatus { Queued,
   Running, Done, Failed }` separately on the TaskNode; "blocked" is
   computed from dependency state). The orchestrator parses `status`
   mechanically to decide accept / reject / re-spawn / re-scope.

Engine enforcement (deep mode only): a worker turn that ends with
its node still running gets re-queued to a fresh worker once and
fails on repeat. The only ways a deep node closes are `expand_node`
(decompose) or `complete_node` (validated artifact). A passing gate
artifact must account for EVERY node it audited by id; rubber stamps
are structurally rejected.

---

## 7. Safety model (Tier 1 / Tier 2 — prompt-level today)

`new.md` §21 specifies a 2-tier action classifier. The bundle
implements it at the **prompt level only**, because jcode's runtime
tier system (`docs/SAFETY_SYSTEM.md`) is design-phase (Phases 1-5
TODO, last updated 2026-02-08).

**Tier 1 — auto-allowed (no permission needed):**

- Read files, `git status`, `git diff`.
- Create local branch / git worktree.
- Run tests, build, lint.
- Local commit.

**Tier 2 — requires permission:**

- `git push` to **any** remote.
- `git push` to `main` / `master` / `<repo>-main` — **NEVER** without
  verbatim user "yes" in this chat. Earlier "and push" instructions
  do not satisfy this for `main` / `master` / `<repo>-main`.
- Create / merge a PR.
- Modify CI/CD / deploy / change auth / secrets.
- Anything that leaves a trace outside the local sandbox.

Implementation: `swarm/prompt-overlay.md` §6.

**Honest gap:** until jcode's runtime tier system lands (Phases 1-5
of SAFETY_SYSTEM.md), this is a **prompt-level gate, not a
runtime-level gate**. A misbehaving agent that ignores the overlay's
prompt-level instruction CAN push to a non-main branch (or attempt
other Tier 2 actions). The overlay reduces the risk to "the agent
would have to actively choose to violate its own instructions"; it
does not eliminate it.

**Mitigations until runtime enforcement ships:**

- Local commits are cheap; remote writes are not. Treat the local
  branch as the only safe surface until push.
- Workers (`migrator`, `implementer`, etc.) must not push — only the
  orchestrator may, and only after verbatim user OK. This is
  enforced by prompt-level discipline, not by the engine.
- For high-stakes repos, set up branch protection rules on `main` so
  even a misbehaving agent cannot push directly.

---

## 8. Configuration key reference (what the engine actually reads)

The bundle intentionally does NOT add `[profile]` / `[workflow]` /
`[autonomy]` / `[git]` keys to `~/.jcode/config.toml`. jcode does not
read them; doing so would create dead config that lies about its own
behavior.

What jcode DOES read (verified by grep across `crates/`):

| Section | Purpose | Bundle usage |
|---|---|---|
| `[ambient]` | Ambient scheduler knobs (enabled, intervals, work branch prefix, etc.) | engine-side; bundle uses default |
| `[safety]` | Notification channels (ntfy, email, telegram, discord, jade_relay) | engine-side; bundle uses default |
| `[agents]` | Swarm spawn mode, max concurrent agents, memory sidecar | bundle sets `swarm_max_concurrent_agents` |
| `[provider]` / `[providers]` | Model defaults, auth, retry, failover | bundle sets `default_model`, auth keys |
| `[features]` | Feature toggles (memory, swarm, mermaid, etc.) | bundle defaults |
| `[websearch]` | Engine + fallback + market | bundle defaults |
| `[autoreview]` / `[autojudge]` | Per-feature booleans | bundle defaults |

**Implicit (not config-driven) knobs:**

- Profile → `effort` mapping happens at spawn time, in the
  orchestrator's prompt. The orchestrator sets `effort =
  "swarm-deep"` when it detects `autonomous` profile.
- Workflow selection happens in the orchestrator's planning phase.
- Per-profile allow/deny lists for Tier 2 actions are handled in the
  orchestrator's prompt, not in `[safety].rules` (which does not
  exist in the live config schema).

If a future jcode version adds `[profile]` / `[autonomy]` / `[git]`
config support, the bundle can wire those keys; for now, prompt-level
is the only path.

---

## 9. Patterns the bundle does not implement

The bundle ships a generic orchestrator. Some patterns that other
agent systems use are deliberately excluded here, with the rationale
per pattern. None of these are load-bearing; the bundle behaves the
same whether the pattern exists in some other system or not.

| Excluded pattern | Why it is excluded |
|---|---|
| Pre-baked persona (e.g. investment-researcher, finance analyst) | Domain-specific; users attach their own via project overlay or `~/.jcode/AGENTS.md` |
| Domain-specific 5-agent pipeline (e.g. risk-officer / market-analyst / strategy-designer / execution-optimizer / research-driver) | Domain-specific; out of scope; the bundle ships 6 generic engineering roles instead |
| Star-topology framing with workspace-as-coordination-layer | jcode is moving to DAG-first (`docs/SWARM_TASK_GRAPH.md`); the bundle aligns |
| `channel` as a coordination primitive | jcode is deprecating channels (SWARM_TASK_GRAPH.md §8a migration steps 3-4 pending); the bundle uses typed-artifact edges |
| `share` / `read` of shared-context key/value as a coordination primitive | Redundant with the repo + typed artifacts |
| Mixed 12-role taxonomy (3 + 5 + 6 split) | Collapsed to exactly 6 generic engineering roles |
| Tick-era coordination language (e.g. `root-tick.sh` references) | Replaced by the engine's scheduler and DAG model |
| Persona-as-ruleset framing (e.g. "8 critical rules") | Replaced by the 6-layer model |

All of these are kept out of the overlay and swarm-prompt. The 6
engineering roles are unchanged because they implement the
bundle's contract directly.

---

## 10. Mapping `new.md` sections → bundle artifacts

| `new.md` section | Topic | Bundle artifact | Notes |
|---|---|---|---|
| §1 final goal | DAG-first autonomous coding | this doc | the spine |
| §2 directory structure | (proposed dirs) | this doc §8 | bundle rejects the proposed dirs |
| §3 repo simplicity | no per-repo `.jcode/` | (project-level install is opt-in) | unchanged |
| §4 priority chain | AGENTS.md > global config | jcode native + `AGENTS.md` content | unchanged |
| §5 `config.toml` schema | (proposed schema) | this doc §8 | bundle rejects most keys |
| §6 profiles | 4 profiles | `prompt-overlay.md` §1 | implemented as 4 profiles |
| §7 deep = autonomous | rationale | `prompt-overlay.md` §1 + `swarm-prompt.md` §1 | mapped to `effort = "swarm-deep"` |
| §8 workflows | 4 workflows | `prompt-overlay.md` §2 | implemented |
| §9 orchestrator | 15-point rules | `prompt-overlay.md` §1-§6 | generic + selective |
| §10 worker | rules + handoff artifact | `swarm-prompt.md` §3-§9 + `roles/*.md` | implemented |
| §11 reviewer | adversarial review | `roles/reviewer.md` | unchanged |
| §12 tester | behavior proof | `roles/test-writer.md` | unchanged |
| §13 swarm split | dependency + ownership + risk | `prompt-overlay.md` §3 + `swarm-prompt.md` §3 | implemented |
| §14 worktree strategy | shared vs isolated | `swarm-prompt.md` §13 + extension.sh `workspace` | engine-side + bundle extension |
| §15 git strategy | branch + never push main | `prompt-overlay.md` §6 | implemented |
| §16 commit strategy | small + focused | `swarm-prompt.md` §11 | implemented |
| §17 validation pipeline | worker / integration / review / E2E | `swarm-prompt.md` §8 + `prompt-overlay.md` §6 | implemented at prompt level |
| §18 repair loop | fail → diagnose → fix → verify (DAG node) | `swarm-prompt.md` §9 | matches jcode `inject_gap` model |
| §19 handoff as message bus | typed artifact on edge | `swarm-prompt.md` §4 + §5 | implemented |
| §20 exception channel | DM only when | `swarm-prompt.md` §4 + `prompt-overlay.md` §7 | implemented |
| §21 safety tier | Tier 1 / Tier 2 | `prompt-overlay.md` §6 | prompt-level only |
| §22 autonomous definition | control loop in safety boundary | `prompt-overlay.md` §0-§7 | implemented |
| §23 ambient positioning | ambient = scheduler | this doc §2 (layer 1) | bundle does not implement ambient; engine-side |
| §24 6-layer architecture | final model | `prompt-overlay.md` §0 + this doc §2 | implemented |
| §25 final dir layout | (proposed) | this doc §8 | bundle rejects |
| §26 complete run | walkthrough | (not encoded) | flows through orchestrator's planning |
| §27 last design tradeoff | intelligence in LLM, discipline in runtime | (whole overlay) | reflected in the split: orchestrator is "intelligence", engine enforces typed-handoff + DAG gates = "discipline" |

---

## 11. References

jcode source + design docs that back this implementation:

- `crates/jcode-base/src/prompt.rs` — system prompt + overlay +
  swarm-prompt loaders, plus `SWARM_DEEP_EFFORT_DIRECTIVE` (the
  deep-mode prose).
- `crates/jcode-config-types/src/lib.rs` — full config schema
  (`[ambient]`, `[safety]`, `[agents]`, etc.). Source of truth for
  what the engine actually accepts.
- `docs/SWARM_TASK_GRAPH.md` — DAG-first design, two modes (deep /
  light), migration to drop channels/shared-context.
- `docs/AMBIENT_MODE.md` — ambient scheduler design. Bundle does
  not implement ambient; design-phase on the engine side.
- `docs/SAFETY_SYSTEM.md` — Tier 1/2 safety design. Bundle
  implements at prompt level only; runtime tier enforcement is
  design-phase.
- `docs/SYSTEM_PROMPT_CONFIG.md` — overlay + swarm-prompt loader
  precedence (project overrides global).

Bundle artifacts:

- `swarm/prompt-overlay.md` — orchestrator overlay.
- `swarm/swarm-prompt.md` — worker dispatch policy.
- `swarm/roles/{implementer,reviewer,test-writer,migrator,investigator,doc-writer}.md`
  — 6 engineering role templates, all enforcing the 8-field typed
  artifact contract.
- `scripts/install.sh` + `scripts/extension.sh` — installer + bundle
  CLI (unchanged).

This document lives at `docs/AUTONOMOUS_FRAMEWORK.md`. It is **not
installed** into `~/.jcode/`; it is bundle-maintainer reference.
