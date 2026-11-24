---
name: swarm-craft-typescript
description: The TypeScript pieces - the idioms, the version floors and the traps, one section per topic. Read in any lane that changes TypeScript code, before it changes it.
---

# The TypeScript pieces

## 0. How to use this Skill

The `swarm-engineering` skill owns the **process** — what a lane does, what it
reports — and the `swarm-craft-shared` Skill owns the **shared pieces** that hold in every
language. This Skill owns the **idioms**: the TypeScript rules that are not
generic, the version floors they carry, and the traps this language has shipped.

Read the piece that matches what you are changing, before you change it: "read
§6 of the TypeScript craft before you touch the error handling". Everything here
is checkable — a rule that cannot be checked is advice, not guidance.

Two facts shape the rest: TypeScript types are **erased** at runtime, so a typed
API still has to validate what comes in; and the type system is **structural**,
so two unrelated classes with the same members are interchangeable.

## 1. The surface: layout, packaging, the version floor

* `tsconfig.json` is the contract; `tsc --noEmit` is the check of record, `tsc -p` the build.
* Put `strict: true` in the base config; every package extends it.
* Floors: TypeScript 5.x, Node 18, Node 20 for `import.meta.dirname`.
* Declare the floors in `engines` and in `devDependencies`.
* One module system per package: `"type": "module"` or CommonJS.
* Generate the `.d.ts`; a hand-written declaration drifts from the source.

## 2. Typing and the compiler options

* `unknown` at a boundary, `any` nowhere.
* One `any` erases the types of the whole call.
* Narrow with a guard `function isFoo(v: unknown): v is Foo`.
* `satisfies` (TypeScript 4.9+) checks a literal; `as` only silences.
* Enable `exactOptionalPropertyTypes` (4.4+): a missing key is not an `undefined` value.
* `interface` merges, `type` does not; `type` takes unions and mapped types.
* Structural typing: two classes with the same members are interchangeable.
* A `private` brand breaks that; `readonly` is compile-time only.

## 3. Data modelling

* Model the states: a discriminated union on a literal `kind`.
* `Result<T> = { ok: true; value: T } | { ok: false; error: Error }` beats null fields.
* A `never`-returning default branch makes a missing case fail to compile.
* That union is the substitute for a Rust enum; TypeScript has no sum type.
* `JSON.parse` returns `any`; validate into your own type at the boundary.
* `enum` compiles to a runtime object; `const enum` breaks under `isolatedModules`.

## 4. Collections and the standard library

* `Map` and `Set` for keyed lookup and membership.
* `Object.create(null)` for a map whose keys come from outside.
* `Object.hasOwn` (Node 16.9+); `key in obj` also hits inherited keys.
* `structuredClone` (Node 17+) copies deeply; a JSON round-trip drops `Date` and `Map`.
* `sort` mutates the array it is given, and is stable (ES2019).
* `reduce` without a seed infers the accumulator as the element type.

## 5. Iteration and laziness

* `for...of` for arrays, a `Map` and generators.
* `for...in` walks inherited enumerable keys; use `Object.keys` for own keys.
* A generator (`function*`) is lazy; an array is eager.
* `forEach` cannot `break`; use `for...of` to stop early.
* `find` returns `T | undefined`; unchecked it is `undefined` at runtime.
* `noUncheckedIndexedAccess` makes `arr[i]` a `T | undefined`.

## 6. Errors

* `throw new Error(...)`; a thrown non-Error is a runtime trap.
* `catch (e: unknown)` is what `strict` gives you; narrow it.
* Chain with `cause`: `new Error('read failed', { cause: err })` (Node 16.9+).
* A custom error extends `Error` and sets `this.name`; compare `name`, not `instanceof`.
* An empty `catch {}` swallows the failure: log it and rethrow.
* An `await` inside a `try` catches the rejection; an unawaited promise does not throw.
* Java and Rust put the failure in the signature; TypeScript does not — write it in the doc.

## 7. Resources

* `using` and `await using` (TypeScript 5.2); `Symbol.dispose` is Node 18.18+/20.5+.
* `try`/`finally` for a resource that is not disposable-shaped.
* `fs/promises.open` returns a `FileHandle`; `using` closes it on the error path.
* `pipeline` from `node:stream/promises` closes both ends and forwards the error.
* The synchronous `fs` functions block the event loop; use `fs/promises`.

## 8. Files and paths

* `node:path` — `join`, `resolve`, `basename`; never concatenate with `"/"`.
* `path.resolve(root, input)`, then check it stays under `root + path.sep`.
* Read and write with an explicit encoding; the platform default is not a contract.
* Write atomically: a temporary name in the same directory, then `rename`.
* `__dirname` and `require` do not exist in ESM: use `import.meta.dirname` (Node 20.11+).

## 9. The shell and the outside world

* `execFile` or `spawn` with an argument array; `exec` takes a shell string.
* `execFile` rejects on a non-zero exit, `spawn` does not — read the `close` event.
* `stdio: 'ignore'` or `'inherit'`, not a pipe that buffers without bound.
* `fetch` (Node 18+): check `res.ok` before the body, and pass an `AbortSignal`.
* A response body is untrusted: `JSON.parse` returns `any`.

## 10. Time and clocks

* `Date.now()` is epoch milliseconds; `new Date()` is a wall clock in the host zone.
* Store UTC; `toISOString()` for exchange, `toLocaleString()` for display.
* A duration is `end - start` in milliseconds; `Date` arithmetic is not calendar arithmetic.
* `performance.now()` for a duration (monotonic); `Date.now()` for a wall-clock stamp.
* Take "now" as an argument, so the code can be tested at a fixed moment.

## 11. Concurrency

* `Promise.all` fails fast; `allSettled` for partial failure; `any` for the first success.
* An `async` function returns a promise; calling it without `await` floats it.
* `no-floating-promises` is the check; an unawaited rejection surfaces elsewhere.
* `await` inside a `try` catches the rejection; move it out to let it escape.
* `Promise.all(items.map(fn))` runs everything at once and unbounded.
* One event loop per process, unlike Go's goroutines: a CPU loop blocks every promise.
* Shared mutable state needs one owner; the standard library has no mutex.

## 12. Testing

* `node:test` and `node:assert`; `node --test` runs the files (Node 18+).
* `mock` is Node 18.13+; `t.mock.method(obj, 'name', fn)` replaces a method.
* `t.mock.restore()` in `afterEach` puts the original back.
* `assert.deepStrictEqual` for a value, `assert.throws` for a throw.
* `assert.rejects` for a rejection; an `async` test must await it.
* Deterministic: pass the clock in, seed the randomness, mock the network.
* `mkdtemp` under `os.tmpdir()`; a test that writes into the repository fails elsewhere.

## 13. The command line

* `parseArgs` from `node:util` (Node 18.3+), not `process.argv[2]` slicing.
* Exit 0 on success, a documented non-zero on failure, the message on stderr.
* `process.exitCode = 1` over `process.exit(1)`: `exit` truncates buffered stdout.
* Offer `--json` for machine consumers; keep the human output stable.
* `--help` prints the usage and exits 0; the usage line names the real syntax.
* `#!/usr/bin/env node` plus a `bin` entry in `package.json` for a published tool.

## 14. Performance

* Measure first: `performance.now()` around the operation, or a profiler.
* Types are erased: annotations, generics and `as const` cost nothing at runtime.
* `Object.freeze` is the runtime half of `readonly`, and it does cost.
* The wins are algorithmic: an `O(n²)` scan a `Map` lookup turns into `O(n)`.
* Do not allocate in a hot loop; build the lookup structure once, outside it.

## 15. Style, naming and docstrings

* `camelCase` for values and functions, `PascalCase` for types and classes.
* `UPPER_SNAKE_CASE` for module constants; `T`, `U`, `V` for type parameters.
* A doc comment says what the caller must know: the contract, the arguments, the return value.
* The types already carry the shape; the doc comment carries the failure modes.
* A comment explains why; the code says what. Delete commented-out code.
* The formatter and the type-aware linter are the record: `prettier --check` runs in CI.

## 16. Dependencies and environments

* `dependencies` for runtime, `devDependencies` for types and tools.
* Commit the lock file and read its diff when it changes.
* `engines.node` pins the floor; `node --env-file` (Node 20.6+) loads the local env.
* `@types/<name>` is a dev dependency, even when the package ships its own types.
* One version of a library per process; two copies in the tree is a latent bug.
* `skipLibCheck: true` for the dependency tree, not to hide your own errors.

## 17. Logging and diagnostics

* A library takes a logger as an argument; it never logs into the caller's terminal.
* Levels mean something: error — someone must act; warn — a tolerated surprise.
* Structured fields beat sentences: `logger.info({ requestId, ms }, 'done')`.
* Include the identifiers needed to correlate two lines — a request id, a path, a key.
* Never swallow an exception to keep a log clean.
* `console.error` for a diagnostic; `process.exitCode` over `process.exit()`.

## 18. Security

* Secrets come from `process.env` or a secret store, never from source; never log them.
* `crypto.randomUUID()` and `crypto.randomBytes()` for tokens.
* `crypto.timingSafeEqual` for a constant-time comparison.
* Never build a command line by concatenating input; `execFile` with an array.
* Parse, never evaluate: `JSON.parse` instead of `eval` or `new Function`.
* Prototype pollution: `Object.create(null)` or a `Map` for untrusted keys; reject `__proto__`.

## 19. The common traps

A checklist, not a style guide — each line is a bug that has shipped:

* A cast that hides a shape change: `x as Foo` compiles for any `x`.
* `any` at one seam, erased types for the whole call chain.
* A floating promise: the rejection is unhandled and surfaces elsewhere.
* `arr[i]` typed `T` but `undefined` at runtime — `noUncheckedIndexedAccess` catches it.
* An `enum` compiling to a runtime object; `const enum` breaks under `isolatedModules`.
* A type imported as a value: write `import type { Foo }`.
* `__dirname` and `require` in an ESM module: not defined.
* `==` where `===` was meant; `null == undefined` is true.
* A truthiness test that treats `0`, `""` and `NaN` as absent.
* `for...in` over an object, inherited enumerable keys included.
* A `catch` that logs and returns `undefined` — failure looks like an empty result.
* A `setTimeout` as a sleep in a test: it can pass for the wrong reason.
* A subclass field shadowing the base field: the base constructor sees `undefined`.
