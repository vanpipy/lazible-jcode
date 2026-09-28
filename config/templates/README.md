# Templates

Markdown templates for handoff / task / report. Agents consult them when producing
the corresponding content:

| File | Usage |
| --- | --- |
| `task.md` | Task DAG node description (PlanItem) |
| `handoff.md` | Downstream artifact when a node completes |
| `report.md` | Upward report on completion

Mapping to jcode:

- `task.md` ↔ `jcode-plan/src/lib.rs:PlanItem`
- `handoff.md` ↔ typed artifact schema in `SWARM_TASK_GRAPH.md §6.3`
- `report.md` ↔ jcode's `completion_report` (`SwarmMemberRecord.latest_completion_report`)

These markdown files are **readable schema descriptions**, for humans and agents
to consult. The real runtime schema is owned by the Rust types.