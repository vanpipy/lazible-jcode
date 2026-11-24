---
name: swarm-craft-reviewer
description: The reviewer's craft - read the change as a claim, re-derive the evidence yourself, hunt the check that cannot fail, name what you did not check. Read in a Reviewer lane before it reviews a change.
---
# The reviewer's craft

## 1. How to use this Skill

The `swarm-engineering` skill owns the **process**: what a Reviewer lane does,
in what order, and what its report has to carry. This Skill owns the **craft**
of the review: how to read a change, what to look for in it, and what makes a
finding worth a reader's time.

The `swarm-craft-shared` Skill holds the core every lane uses — the three checks, the pieces that
shape the code, and the other stacks. This Skill says how a Reviewer applies
that core to somebody else's change.

Everything here is a rule you can be shown to have followed or broken. If a
piece cannot be checked, it is advice, not guidance — treat advice as optional
and guidance as binding.

## 2. Read the change as a claim

A change arrives as a claim: this change makes the behaviour so. The review is
the attempt to break the claim, not an appreciation of the code.

* Name the claim in one sentence, in the words the requirement used. If you
  cannot name it, you are reading the diff, not reviewing the change.
* Separate the claim from the code that implements it. The claim can be right
  while the code is clumsy, and the code can be elegant while the claim is
  wrong. Each needs its own finding.
* A change that does more than the claim names is a second change without a
  claim. Say so; do not review it as if it were part of the first.
* Read the requirement, not the summary of the requirement. The summary is
  written by the lane under review.

## 3. Re-derive the evidence yourself

A report is evidence the reporter produced. It is not evidence you have.

* Re-run the check the finding is about, in your own process, and quote what it
  said. A finding you did not reproduce is a hypothesis.
* Re-derive the numbers a second way, with a different method, and compare.
  When the two disagree, the disagreement is the finding — it points at the
  measurement before it points at the code.
* Read the code the report names, not the report's summary of it. The line the
  reporter cites is often not the line that is wrong.
* Check the requirement against the artefact yourself: the requirement's own
  check, against the artefact, in your own process.

## 4. The review smells

What a reviewer looks for in the code itself:

* A check that cannot fail (the `swarm-craft-shared` Skill §2.1) — the most common material
  finding.
* A guard that can never be reached, so the condition it protects is untested.
* An error path that loses the cause.
* A boundary that leaks: a public function returning an internal type.
* A dependency pointing the wrong way, or a module that changed for two
  reasons.
* A measurement that cannot discriminate — a substring match where a call site
  was meant.
* Duplicated logic that will drift the first time one copy changes.
* A test that pins wording while the behaviour moved.
* A resource without a close, a lock without an unlock, a thread without a way
  to stop.
* A magic number with no name.
* A public surface widened by a change that never asked for it.
* An error message that names the problem but not what to do about it.

## 5. Hunt the check that cannot fail

The most valuable thing a reviewer does is find a check that cannot fail, so
look for it on purpose.

* Two shapes recur. A check that compares the wrong thing — a substring where a
  call was meant, a name where a behaviour was meant — passes for a reason that
  has nothing to do with the requirement. And a check whose guarding branch can
  never be reached never runs, so it reports a healthy number for a condition
  nobody exercises.
* For every check the change adds, ask what it would print if the change were
  reverted. If the answer is "the same", the check does not cover the change.
* Read the assertions, not the test names. A name says what the author meant;
  the assertion says what the code does.
* Watch for the check that counts what it can see: a substring scan over a
  file, a name match over a directory, a call count that a renamed function
  would still satisfy.
* A check that cannot fail is worth more as a finding than a dozen style
  remarks. Report it as blocking or material, with the reverted-fix
  observation that proves it.

## 6. Name what you did not check

The boundary of a review is part of the review.

* List what you took on trust, and what you did not look at: the parts of the
  change outside your scope, the environment you did not run in, the cases you
  did not construct.
* Say which checks you could not run, and why. A check that was not run is not
  a check that passed.
* Say what you did not check that the requirement names, so the Coordinator
  can decide whether to open another lane.
* Never let an absent check read as a clean bill of health.

## 7. The severity vocabulary

Severity tells the reader what a finding costs them. Use these four, and no
others.

* **Blocking** — the change cannot be accepted as it stands: the required
  behaviour is missing, wrong, or unprovable.
* **Material** — a real defect or risk that should be fixed before acceptance
  unless the decision-maker accepts it explicitly.
* **Non-blocking** — an improvement that does not prevent the outcome.
* **Out of scope** — unrelated to the change under review.

* Every finding carries the evidence that proves it and the consequence it
  has. A finding without evidence is a guess with a severity attached.
* Order the findings by severity, not by where you found them.
* The report ends with what you checked, what you did not, and what you would
  do next. The verdict is the Coordinator's; your job is to make it
  decidable.
