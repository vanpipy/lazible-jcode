# Policies

Declarative policy descriptions. The markdown in this directory is **not loaded
at runtime**. It serves as:

- a human-readable memo of why a setting has the value it has
- semantics an agent can consult before acting
- the intent behind the numbers in `config/config.toml`

| File | Content |
| --- | --- |
| `autonomy.md` | L0 to L3 autonomy levels, and which one this repo ships |
| `git.md` | what the pre_tool gate blocks, branch naming, commits, worktree decision |
| `repair-loop.md` | where the retry budget lives and how escalation works |
| `audit.md` | the post_tool hook, log format, and what it can and cannot do |

## Relationships

- `policies/` → intent (humans and agents read)
- `config.toml` → behavior (jcode reads, no overlay)
- `templates/` → output format (agents write)
- `docs/mermaid-style.md` → documentation conventions
