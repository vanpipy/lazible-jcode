---
name: swarm-craft-shared
description: "The shared craft every lane works by - the three checks that hold in every language, the pieces that shape the code, and the same piece in another stack. Read in any lane before a non-trivial edit: the core the role Skills apply."
---
# The shared craft

## 1. How to use this Skill

The `swarm-engineering` skill owns the **process**: what a Developer, Tester or
Reviewer lane does, in what order, and what its report has to carry. This
craft set owns the **craft**: how the code is shaped, what makes a check worth
running, and what a reviewer looks for in the code itself. The two do not
overlap, and nothing here repeats the skill's roles — it gives them something
to work with.

| Skill | What it is |
| --- | --- |
| the `swarm-craft-shared` Skill | this Skill: the core every lane uses |
| the `swarm-craft-developer` Skill | the developer's craft: how a Developer applies the core to an edit |
| the `swarm-craft-tester` Skill | the tester's craft: how a Tester applies the core to a check |
| the `swarm-craft-reviewer` Skill | the reviewer's craft: how a Reviewer applies the core to a change |
| the `swarm-craft-<language>` Skill | the language pieces, one Skill per language |

The language-specific pieces are separate Skills, one per language, so that a
language can be loaded on its own and grow without this Skill growing with it.
The language Skills that ship with this set are the `swarm-craft-python` Skill,
the `swarm-craft-java` Skill, the `swarm-craft-go` Skill, the
`swarm-craft-typescript` Skill and the `swarm-craft-rust` Skill; each one
carries its own nineteen numbered sections — that language's reading of the
same ground, in its own idioms — while the twelve pieces in §3 stay the shared
rules behind them. A brief names the Skill and the piece: "read §3 of the
tester's craft before you write the check". A brief that names a role and no
piece leaves the lane guessing what good looks like.

Everything here is a rule you can be shown to have followed or broken. If a
piece cannot be checked, it is advice, not guidance — treat advice as optional
and guidance as binding.

## 2. The three checks that hold in every language

These three are not in the skill, and they are the difference between a lane
that finished and a lane that knows whether it finished.

### 2.1 Make the check falsifiable

**The principle.** A check that cannot fail is not a check. A check that passes
for a reason other than the one it claims to measure is worse than no check,
because it buys confidence it cannot pay for.

**In practice.** Two failures are common and both are invisible to the author.
A check that compares the wrong thing — a substring where a call was meant, a
name where a behaviour was meant — passes for a reason that has nothing to do
with the requirement. And a check whose guarding branch can never be reached
never runs, so it reports a healthy number for a condition nobody exercises.

**How you show it.** After you write a check, make it fail on purpose and show
that it fails: invert it, break the input, or revert the fix in a throwaway
copy. Report the failing observation. A check you have never seen fail is a
claim, not a check.

### 2.2 Re-derive every number a second way

**The principle.** A measurement reported once is an assertion. The second
method is what turns it into evidence.

**In practice.** When a number matters, compute it again by a different route:
a second tool, a different algorithm, a hand count, a different granularity. If
the two methods disagree, the disagreement is the finding — it points at the
measurement, not at the code.

**How you show it.** The report gives both numbers and names the methods. When
the methods agree, the number is evidence. When they cannot be run apart, say
that instead of presenting the single number as settled.

### 2.3 Validate where the artifact runs

**The principle.** A check runs under some interpreter, some toolchain, some
runtime, some set of stubs. It proves something about that environment and
nothing else. The consumer is the environment: the artifact must be validated
where it will actually be used.

**In practice.** A unit test on a stubbed service says the call shape is right;
it does not say the real service accepts the result. A script run in a
temporary directory says something about a tree that is not the tree being
measured. A test run under a different interpreter does not speak for the
interpreter the package declares.

**How you show it.** The evidence names the environment it ran in, and where an
environment differs from the consumer's, the report says so in its boundary
section rather than in a footnote.

## 3. The pieces that hold in every language

Each piece is a set of rules with a named trap. The examples are Python because
that is the language the first language Skill covered; the rules are not
Python's, and the language Skill for the language in play has the rest.

### 3.1 Boundaries and modules

* A module has one reason to change. If you cannot name that reason in a
  sentence, the module is two modules.
* Depend on the public name of a neighbour, never on its internals. A private
  helper that another module imports is a public helper with worse manners.
* No cycles. A cycle means the shared concept sits at the wrong level: move it
  down until the dependency points one way.
* The public surface is a promise. Everything outside it may change without
  notice, so everything outside it is free to be simpler.
* A module called `utils`, `helpers` or `common` is a module nobody owns.
  Name it after what it is for.

### 3.2 Types and contracts

* Model the states a thing can be in, not only the state you expect. A status
  field, a sum type, a sealed hierarchy — make the illegal state impossible
  to represent rather than defensive to handle.
* Parse at the boundary, trust inside. Validate the outside input once, convert
  it to your own type, and let the rest of the code assume validity.
* Name a type after what it is, not after its shape. `Customer`, not
  `StringList`.
* Return the smallest useful type. A function that returns a dict of four keys
  when the caller wanted one of them is a function with an accidental API.
* Say how a function fails. A signature that can raise, return an error value or
  return nothing are three different contracts, and the caller has to know which
  one it is.

### 3.3 Errors, exit codes and streams

* An error is data. Keep the message, the cause and the context; chain errors
  instead of replacing them.
* Distinguish "the caller did something wrong" from "we are broken". The first
  gets a message and a non-zero exit; the second gets a traceback. Do not
  swallow the first into the second.
* One diagnostic per failure, on stderr. Results go to stdout.
* Exit codes are a contract: zero for success, non-zero for failure, and a
  documented meaning for each code you use.
* Never catch and ignore. A handler that swallows everything is a lie told to
  the next reader of the log.
* A traceback on stdout is a bug in the program, not in the data.

### 3.4 Dependencies and the standard library

* The standard library first. A dependency is a contract you did not write and
  cannot fix; take one on when it removes a real problem, not when it saves a
  line.
* Name what a dependency replaces. If you cannot, it is not earning its place.
* Pin what you ship, declare what you develop against.
* A transitive dependency is still a dependency. Read what it pulls in before
  you take it in.
* One version of a library per process. Two is a bug waiting for a slow day.

### 3.5 State, data and its shape

* Keep one source of truth. Two copies of the same fact drift apart; one fact
  plus a derived view does not.
* Prefer immutable values. A change produces a new value, so there is no
  half-updated state to reason about.
* Copy at the boundary. Do not hand out a mutable structure you still hold.
* Put the shape of the data in the code, so a reader does not have to infer it
  from how it is used.
* Serialise at the edge. Keep the in-memory form typed and the wire form
  explicit.

### 3.6 Time, concurrency and ordering

* Read the clock once and pass the value in. A function that reads the time
  itself cannot be tested.
* Store UTC, convert at the edge.
* Never sleep to wait for something. Wait on the condition — an event, a
  future, a channel — so the wait ends when the work does.
* Name the ordering guarantee you rely on, and say plainly when there is none.
* Shared mutable state needs one owner. A lock is not an owner.
* Be idempotent: a retried operation must not write twice.

### 3.7 Input, output and the outside world

* Everything from the outside is untrusted — the file, the argument, the
  response, the environment variable.
* Validate and convert at the boundary; inside, you may assume.
* Encoding is explicit. Never rely on the platform default.
* Newlines: read and write in binary when the bytes matter; otherwise normalise
  on read and write `\n`.
* Paths are not strings. Use the path type and build paths, never concatenate
  them.
* Pass an argument list to an external command, never a shell string.

### 3.8 Performance, and how you know

* Measure before you change. The number comes from a profiler, not from a
  feeling.
* Optimise what the profile names, not what worries you.
* Complexity first. An `O(n²)` loop beats any constant-factor tuning.
* A faster version that is harder to read needs a measurement and a comment
  saying why the trade was worth it.
* State the cost in the report: bytes, milliseconds, requests.

### 3.9 Tests and test design

* One behaviour per test, and the name states the behaviour rather than the
  function under test.
* Arrange, act, assert — in that order, and the assertion says what was
  expected.
* A test that cannot fail is a liability; see §2.1.
* Cover the boundaries: empty, one, many, negative, huge, unicode, malformed.
* Assert on behaviour, not on wording — unless the wording *is* the contract,
  such as a command's output format. Then pin it and say so in the test.
* No sleeps, no network, no dependence on the wall clock. Seed the randomness.
* Test the public surface. A test that breaks on a private rename is a test of
  the implementation, not of the behaviour.
* Build the smallest fixture that exercises the behaviour.

### 3.10 Security and secrets

* Secrets come from the environment or a secret store. Never from source, and
  never as a default value that hides a missing configuration.
* Never build a command line by concatenating input.
* Never evaluate data as code. Parse it.
* Normalise a path that came from outside and check that the result stays under
  the root.
* Do not log secrets, tokens or whole payloads.
* Validate what you did not produce. Everything else is your own output and
  already consistent.

### 3.11 Diagnostics and logging

* Log at the boundary of an operation, with the identifiers needed to correlate
  two log lines.
* Levels mean something: error — someone must act; warn — a tolerated
  surprise; info — the milestones; debug — the noise.
* A library logs; a program prints. A library that prints takes over the
  caller's terminal.
* Structured fields beat formatted sentences whenever a machine reads it.
* Never swallow an exception to keep a log clean.

### 3.12 Naming, comments and documentation

* Names carry intent: `total_tokens`, not `n2`.
* A comment explains why; the code says what.
* A docstring says what the caller must know: the contract, the arguments, the
  return value, the failure modes.
* Delete commented-out code. It is a bug with a comment attached.
* Keep the docstring true. A stale docstring is worse than a missing one.

## 4. The same piece in another stack

The craft is the same in every language; the idiom is not. When the repository
is not Python, these are the pieces to read. A language that deserves its own
Skill gets one.

**TypeScript and JavaScript.** `strict` on, and no escape hatch without a
reason. `unknown` at a boundary, narrowed immediately; `any` is a hole. `===`,
never `==`. A truthiness test treats `0` and `""` as absent — test explicitly.
An `await` inside a `try` catches rejection; a promise that is never awaited
does not. `Promise.allSettled` when partial failure is acceptable. The event
loop blocks on synchronous work, so keep it off the hot path. `structuredClone`
for a deep copy. `node:test` plus `node:assert` keeps the test surface free of
dependencies. A formatter and a linter are the record, not a reviewer's taste.

**Go.** The error is the last return value; handle it or say why it is ignored.
`fmt.Errorf("...: %w", err)` keeps the chain; `errors.Is` and `errors.As` test
it. `context.Context` is the first parameter. A goroutine needs a way to stop.
`defer` the unlock. `panic` belongs in `main` and in tests, nowhere else.
`go test -race` in the pipeline. Table-driven tests.

**Rust.** The borrow checker is a design tool: restructure before you clone.
`Result` and `Option` instead of panics; `?` to propagate. `unwrap` and
`expect` only where the invariant is stated in the message. No `unwrap` in a
library. `clippy` and `rustfmt` are the check of record. Errors implement
`std::error::Error`. `&str` until you need to own the value.

**Java and Kotlin.** Nullability is the design tool: put it in the type.
try-with-resources for every resource. No mutable static state. `equals` and
`hashCode` travel together. Immutable value objects. JUnit 5, with assertions
readable enough to name a failure.

**C#.** Nullable reference types on. `async` all the way down — never
`.Result` or `.Wait()`. `using` for disposal. LINQ only where it stays
readable. `record` for a value object. `ArgumentNullException.ThrowIfNull` at
the boundary. xUnit for the tests.

**Ruby.** Small objects with clear interfaces. Guard clauses instead of nested
conditionals. `freeze` the constants. `rescue` with a class, never bare.
`nil` checked at the boundary, not everywhere. `each` over `map` when the
result is unused. Minitest or RSpec.

**Shell.** Quote every expansion. `set -euo pipefail`, and check the exit code
of every command in a pipeline. Anything with branching belongs in a real
language. `printf` over `echo` for data. Never `rm -rf` a variable.

## 5. What this craft set does not cover

* The **process** — how a lane works, what it reports, who decides. That is the
  `swarm-engineering` skill.
* The **host** — which surfaces exist here, which tools are live. That is the
  host note the prompt carries.
* The **repository** — its conventions, its layout, its own documentation. Read
  those before this Skill; they win where they disagree.
* The **language** — the idioms of the language you are writing in. That is the
  language Skill.
* The **role** — how a Developer, a Tester and a Reviewer each apply the core.
  That is the Skill named after the role.
