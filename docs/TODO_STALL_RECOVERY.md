# TODO stall recovery

When the todo store enters a state where it rejects every write to
close an in-progress item, the agent is in a **reminder loop**:
system messages every ~2–3 seconds saying "1 incomplete todo" with
no way to dismiss them. This document captures how to recognize it
and what to do.

## Symptoms

- `todo` tool returns the same error every time:
  > "Your end-to-end ownership is not high enough to complete this
  >  goal. ... setting a higher end_to_end_ownership on the goal
  >  for this group; until that field is raised the write is
  >  rejected and the stored todo list is left unchanged."
- The stored todo list always shows the same locked item, regardless
  of what is sent.
- `completion_confidence`, `status: completed`, `priority`, ID renames,
  goal groups with `end_to_end_ownership` from 95 → 100 → 200 → 255
  all fail.
- Creating + closing an `initiative` does not unstick it.
- Focus on the initiative does not unstick it.

## Probable cause

A session-level persistent goal has a stored `end_to_end_ownership`
threshold that the tool cannot match (likely set higher than the
schema allows in a prior session, or set externally). Every write
that targets the locked item is rejected until that goal is updated
externally.

## Detection (worker-side, recommended contract)

Per the worker-driven liveness contract (`docs/HEARTBEAT.md`),
treat a reminder loop as **stuck state**. The worker should:

1. Count consecutive identical system reminders. If count ≥ 5 with
   no successful tool action in between, the worker is in a stall
   loop.
2. Emit `dm --delivery=interrupt {"type":"stuck","reason":"todo store
   is in reminder loop, no progress possible","since":"<ts>"}` to root.
3. If still no progress after the standard 5-min exit-right window,
   report `status: abandoned` and exit cleanly.

The same heartbeat / stuck / exit-right machinery that handles tool
stalls and external blocker stalls handles reminder stalls — they are
the same failure mode with a different symptom.

## Detection (root-side)

If the root session is itself in a reminder loop:

1. Do not waste tokens sending additional `todo` writes. The lock
   will not lift from this side.
2. Output a single explicit "stalled" acknowledgment to the user
   explaining the loop and pointing to this doc.
3. Continue with whatever end-to-end work is still possible outside
   the todo store (commit, push, deploy, document).
4. The lock will clear when the session ends or when an external
   tool resets the persistent goal store.

## Workaround (when lock is identified before work is complete)

This is exactly the situation that motivated
`docs/MANUAL_BINARY_SWAP.md` — environmental locks that block normal
flow. The mitigation is the same: identify the environmental
limitation, document the workaround, push what you can to origin,
and let the next session pick up.

## Cannot-fix from inside the session

- The persistent goal's `end_to_end_ownership` threshold.
- The session-reminder trigger loop itself.
- Anything requiring a runtime configuration reset.

## See also

- `docs/HEARTBEAT.md` — worker-driven liveness contract (the
  reminder loop is just another form of "stuck").
- `docs/MANUAL_BINARY_SWAP.md` — sibling environmental-lock
  workaround.
- `docs/LIVENESS_VALIDATION.md` — Turn 5 worker-death recovery
  uses the same passive-detection pattern this recovery shares.