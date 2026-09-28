# Task Template

Every Task DAG node (`PlanItem`) should have:

```text
id          string, stable id (used for dependency references)
content     one-line task description (≤ 80 chars)
status      pending / in_progress / done / failed
priority    low / normal / high
subsystem   module name (optional, used for routing)
file_scope  [glob, ...]   files the task plans to touch (used for worktree decisions)
blocked_by  [id, ...]
assigned_to session_id (optional)
```

## Writing a good `content`

- Start with an action verb ("implement X", "analyze Y", "fix Z")
- State the goal, not the means
- ≤ 80 characters

## Artifact (on completion)

- `findings`: the output of an `"Explore"` node
- `diff`: commit ref + file ref (by reference, do not paste the full content)
- `pass / fail`: the output of a `"Verify"` node

See [`handoff.md`](handoff.md).