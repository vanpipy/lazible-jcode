# Policies

Declarative policy descriptions. The markdown in this directory **is not loaded at runtime**. It serves as:

- A human-readable memo (rationale for autonomy choices)
- Semantics that agents can consult in pre_tool gates
- An intent layer for future profile automation

| File | Content |
| --- | --- |
| `autonomy.md` | L0–L3 autonomy level definitions and switching discipline |
| `git.md` | worktree / branch / commit conventions |
| `repair-loop.md` | retry / escalation strategy |

## Relationships

- `policies/` → intent (humans read)
- `profiles/` → behavior (jcode reads)
- `templates/` → output format (agents write)
- `notes/` → design process (developers read)