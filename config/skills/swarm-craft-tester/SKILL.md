---
name: swarm-craft-tester
description: The tester's craft - choose the oracle, make the check discriminate, cover the boundary rather than the middle, prove the check can fail, report honestly. Read in a Tester lane before it writes or judges a check.
---
# The tester's craft

## 1. How to use this Skill

The `swarm-engineering` skill owns the **process**: what a Tester does, in what order, and what
the report has to carry. This Skill owns the **craft of the check** — how the
oracle is chosen, how a check is made to discriminate, and what makes a
result worth reporting. Nothing here repeats the process; everything here is
about the thing the process asks for.

The `swarm-craft-shared` Skill, a sibling Skill, holds the shared core: the three checks that
hold in every language, and the twelve pieces. The review smells live in
the `swarm-craft-reviewer` Skill §4, a sibling Skill. This Skill says how a Tester applies that
core. Where the two overlap, this Skill is the narrower reading of it, for the
Tester's hand.

Everything here is a rule you can be shown to have followed or broken. If a
piece cannot be checked, it is advice, not guidance — treat advice as optional
and guidance as binding.

Read the piece that matches the check you are about to write, before you write
it. A brief names this Skill and the section that applies: "read §3 of the
tester's craft before you write the assertion". A brief that names a role and
no piece leaves the lane guessing what good looks like.

The language Skill carries the idioms. The repository's own
conventions win where they disagree with any of these Skills.

## 2. Choose the oracle

The oracle is the observable behaviour the requirement names. It is the thing
a reader of the requirement would see if they ran the artifact themselves.

* The oracle is the observable behaviour the requirement names, never the
  implementation's own value.
* A test that asserts what the code returns is not a check of what the code
  should return. It restates the implementation, and passes for any
  implementation, including the wrong one.
* Name the source of the expected value: the requirement, the specification, a
  second method, or a hand count. Write that source in the test, so the next
  reader can check the value without asking.
* Derive the expected value from the requirement before you read the
  implementation, so the implementation cannot tell you what to expect.
* Re-derive a computed expected value a second way: a second tool, a
  different algorithm, a hand count. Two methods that agree are evidence; one
  is an assertion.
* The check is black-box: it runs through the public surface. A check that
  reaches into a private helper tests the implementation, and breaks on a
  rename that changed no behaviour.
* Where the wording of the output is the contract, pin the wording exactly and
  say in the test why the wording is the contract.
* A requirement with no observable oracle is reported as such. Do not invent
  one, and do not pass a check you could not define.

## 3. Make the check discriminate

A check discriminates when it can give two different answers for two different
behaviours. A check that gives the same answer either way proves nothing about
the behaviour.

* For each case, name the value that separates the two answers: a boundary, a
  type, a sign, a count, an error instead of a value.
* A case whose expected value differs from its sibling's is the case that
  discriminates. A case whose expected value matches the one before it adds
  no evidence.
* A check that compares the wrong thing — a substring where a call was meant,
  a name where a behaviour was meant — passes for the wrong reason and is
  worse than no check, because it buys confidence it cannot pay for.
* One behaviour per check. A check that asserts five things tells the reader
  which one failed only by running it five times.
* Assert on the observable result, not on the intermediate that produced it.
* Name the behaviour in the check's name, not the function under test: the
  name states what was supposed to happen.
* A check that cannot fail is not a check. Prove it — §5.

## 4. Cover the boundary, not the middle

The cases that decide the requirement sit at the edges of what it allows.

* The cases that matter: empty, one, many, the largest allowed, the smallest
  allowed, the malformed, the wrong type, the missing file, the error path.
* The middle of the range is the case that is already covered. It adds a line
  to the report and no evidence.
* Build the smallest fixture that exercises the behaviour. A fixture carrying
  more than the behaviour needs is another thing that can break the check.
* No sleeps, no network, no dependence on the wall clock. Seed the
  randomness.
* Read the clock through an argument the check controls; freeze the time the
  check depends on.
* Write into a temporary directory, never into the working tree.
* One case per requirement clause. A requirement with no case is a coverage
  gap, reported as a gap — never a silent pass.

## 5. Prove the check can fail

After you write a check, make it fail on purpose and show that it fails.

* Make it fail on purpose: invert the expectation, break the input, or revert
  the fix in a throwaway copy.
* Show the failure: quote the failing output, the command, and the case that
  failed. "It failed" is not evidence; the output is.
* Report the failing observation. It is the evidence that the check
  discriminates.
* A check never seen failing is a claim, not a check.
* Keep the evidence of the failure next to the check, so the next reader can
  repeat it.
* Break only the behaviour under test. A failure caused by a broken
  environment is not a demonstration that this check discriminates.
* Leave the tree as it was. The broken check was an experiment; restore it
  before the report.
* If the check will not fail when it should, the check is defective — fix it
  before you report the behaviour it claims to verify.

## 6. Report honestly

* Report what passed, what failed, what was blocked, and what was not tested.
  The four are different findings, and the report keeps them apart.
* A verdict without evidence is not a verdict. Name the check, the command and
  the result that support it.
* The requirement set wins over a report that disagrees with it. Where the two
  conflict, report the conflict; do not pick the one you can defend.
* A check that cannot be run in this environment is `not demonstrated`, never
  `met`. Say what blocked it and what would unblock it.
* Cite the requirement each check covers, and list the requirements with no
  check as gaps.
* Quote the evidence: the failing output, the passing run's summary, the
  command that produced it.
* Name the environment the check ran in, and where it differs from the
  environment the artifact runs in, say so in the report rather than in a
  footnote.
* Do not generalise a narrow pass. A passing check is evidence about the
  behaviour it covers, and about nothing else.
