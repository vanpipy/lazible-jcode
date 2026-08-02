# swarm/role-templates/ — worked sample artifacts

This directory holds **one worked sample `complete_node` artifact per role**, in
the form of `swarm/role-templates/<role>.example.json`.

## Purpose

A worked sample is a *complete, hand-written example* of the typed artifact
the worker will hand back to the root session. They exist so the root
session (or a human) can see, at a glance, what a well-formed artifact
looks like for each role. The samples are **reference material**, not
test fixtures and not auto-loaded.

These files are **NOT**:

- Test inputs. `scripts/test_role_templates.py` validates their *schema*
  (parseable JSON + six required fields + valid `confidence` value) — it
  does not check their prose.
- Worker prompts. They go in `swarm/roles/<role>.md`, not here.
- jcode-loaded content. jcode's `~/.jcode/roles/` symlink target is
  `swarm/roles/`, never `swarm/role-templates/`.

## What's in here

| File                                 | Shows a sample artifact for…                                 |
|--------------------------------------|--------------------------------------------------------------|
| `reviewer.example.json`              | Code review of a worker commit (blocker / major / minor)     |
| `investigator.example.json`          | Hypothesis-driven bug hunt with confirmed / rejected branches|
| `migrator.example.json`              | Large-scale API migration with a blocked-ids tail            |
| `test-writer.example.json`           | Test scaffold task across multiple `tests/<behaviour>.test.ts` files |
| `doc-writer.example.json`            | Doc rewrite to match current behaviour + cross-link check    |
| `implementer.example.json`           | TDD red→green→refactor feature add, feature-flagged          |

The samples deliberately use *different file paths, different
frameworks, different validation commands* — they are not interchangeable.
That variety is the point: each sample demonstrates what good looks like
for *that* role, in *that* style.

## How to use these as a template

When the root session is composing a spawn prompt for a worker, copy the
matching role's `.example.json` and replace the role-specific content
**field-by-field**:

1. `findings` — rewrite entirely. This is your prose conclusion. Keep the
   shape (`array of {severity, summary, evidence}` for `reviewer`;
   string summary for `investigator`; array-of-things-done for
   `test-writer`; etc.) but the words are yours.
2. `evidence[]` — replace every entry with a fresh `file:line` /
   `commit:hash` / command-output citation from your own task. Do not
   copy citations from a different run.
3. `validation` — write down the *actual commands you ran* and the
   *observed results*. Plausible-sounding commands you did not run
   are a fast track to `confidence: high` rejection.
4. `open_questions[]` — keep the items you genuinely do not know or
   that are out of scope. Empty is acceptable only when the task was
   truly exhaustive.
5. `confidence` — pick `low`, `medium`, or `high`. `high` requires a
   real observation in `validation`, not hand-wave.
6. `what_i_did_not_check[]` — list the gates you did *not* run. Empty
   only when truly exhaustive; otherwise reviewers will drill there.

The samples are deliberately opinionated: each one shows the *minimum*
of what a clean artifact looks like. A real worker artifact is free to
add role-specific fields (`hypotheses[]`, `blocked_ids[]`,
`red_green_refactor_log[]`, etc.) — they are *additions*, not
replacements, of the six required keys.

## How to update a sample

When you change a worker role's expected shape (e.g. add a new required
field to the Output contract), update the matching `.example.json` in
the same commit so the sample stays in sync. The schema test in
`scripts/test_role_templates.py` will catch any drift that violates
the six-key baseline.

## Related

- `swarm/roles/<role>.md` — the worker persona templates themselves.
- `swarm/swarm-prompt.md` §5 — the Output contract this directory
  enforces.
- `scripts/test_role_templates.py` — the schema test that guards
  `swarm/role-templates/`.
