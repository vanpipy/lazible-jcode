# Handoff Artifact Template

A DAG edge = communication channel. `handoff` is what a node injects downstream when it completes.

## Required fields (see `SWARM_TASK_GRAPH.md §6.3`)

```text
summary              one-line summary (≤ 200 chars)
evidence             [paths / references / commit / log line numbers]
findings             non-trivial conclusions (explore nodes only)
validation           how it was verified (implement / verify nodes only)
edge_cases           boundary cases encountered
open_questions       questions still open, but downstream may proceed
confidence           speculative / plausible / validated / verified
what_i_did_not_check explicit statement of what was NOT checked (**mandatory**)
```

## Writing discipline

- **by-reference preferred**: `crates/foo/api.rs:120-145` is better than pasting 30 lines of code
- **by-value for decisions / design / analysis**: things not in the repo
- **`confidence` should match the strength of `evidence`**:
  - `verified` + no `what_i_did_not_check` → not trustworthy
  - `plausible` + strong evidence → trustworthy
  - `validated` typically means "I ran the tests"

## Length

- summary ≤ 200 chars
- evidence ≤ 20 lines
- `what_i_did_not_check` has no length limit but should be **exhaustive**

See [`../design.md` §3.4](../design.md).