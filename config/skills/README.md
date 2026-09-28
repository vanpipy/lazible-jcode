# Skills (portable distribution)

jcode loads skills at startup in this order:

1. `~/.claude/plugins/.../skills/*/SKILL.md`
2. `~/.jcode/skills/*/SKILL.md`
3. `~/.agents/skills/*/SKILL.md`
4. `./.jcode/skills/*/SKILL.md` (project-level overlay, re-read each session)
5. `./.agents/skills/*/SKILL.md`
6. `./.claude/skills/*/SKILL.md`

`config/skills/` is the portable subset owned by this repo. It is bidirectionally synced
to `~/.jcode/skills/` or to a project-level overlay by `scripts/sync-skills`.

## Currently owned

| Name | Purpose | Origin |
| --- | --- | --- |
| `optimization` | Performance optimization workflow (define metric → measure → attribute → static analysis → macro-first) | Borrowed from `~/Project/patched-jcode/.jcode/skills/optimization/SKILL.md` |

## Sync commands

```bash
./scripts/sync-skills --to-home          # push to ~/.jcode/skills/
./scripts/sync-skills --from-home        # pull back from home
./scripts/sync-skills --to-project .     # push into current project's .jcode/skills/
```