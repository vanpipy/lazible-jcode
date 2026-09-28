# Report Template

Format for reports sent upward when a DAG task completes (read by humans / agents).

## Header

```text
Status:      pass | fail | blocked
Owner:       session_id / agent_name
Updated:     ISO timestamp
Confidence:  verified | validated | plausible | speculative
```

## Body

- **What was done**: 3-7 bullet points
- **Why this approach**: 1-3 reasons (point at handoff / commit / doc)
- **How it was verified**: build / test / e2e commands
- **Remaining risks / edges**: honestly list cases not covered
- **Next steps**: optional

## TL;DR

> A single line the reader can grasp at a glance.

The `Tldr` must convey "what was done + result" within 200 characters.

## Example

```text
Status:      pass
Owner:       session-a3f2
Updated:     2026-09-28T17:00:00Z
Confidence:  validated

What was done
- Added MAX_REQUEUE constant in jcode-plan/src/dag/ops.rs
- Added retry_max field in config-types
- Default value = 3 (does not break existing configs)

Why this approach
- new.md §12 mentions a retry < 3 guard
- jcode-task-types already has a Difficulty enum

How it was verified
- cargo check -p jcode-plan
- cargo test -p jcode-config-types

Remaining risks
- A default retry = 3 makes existing users see new reject logs, but functionality is not broken

Next steps
- Wire retry counting into ambient.rs → fire ntfy when threshold exceeded

Tldr: Added retry max = 3 as default.
```