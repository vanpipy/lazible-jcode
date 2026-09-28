# Mermaid Rendering Conventions

Reference: `~/Project/patched-jcode/docs/MERMAID_RENDERING_REDESIGN.md` and the
`features.mermaid = true` field (`jcode-config-types/src/lib.rs:1084`).

## Rules followed by design docs in this repo (`new.md`, `design.md`)

- All diagrams use ``` `mermaid` ``` fenced code blocks
- Diagram choice:
  - **Architecture / DAG / worktree**: use `flowchart TB` or `graph TD`
  - **State machine**: use `stateDiagram-v2`
  - **Git history**: use `gitGraph`
  - **Class / sequence diagrams**: only use `classDiagram` / `sequenceDiagram` when truly necessary
- Node labels use `\n` for line breaks; use `<br/>` for TUI readability
- Cross-doc references: ``` `~/Project/patched-jcode/docs/X.md` ```
- Do not embed emoji inside Mermaid : keep it plain text for better search indexability

## When mermaid is disabled

- When `[features].mermaid = false` is set, the TUI does not render the mermaid widget, but the inline image is still visible in the transcript
- See `jcode-config-types/src/lib.rs:1082-1084` for the exact behavior