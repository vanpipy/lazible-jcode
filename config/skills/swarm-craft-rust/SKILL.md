---
name: swarm-craft-rust
description: The Rust pieces - the idioms, the version floors and the traps, one section per topic. Read in any lane that changes Rust code, before it changes it.
---

# The Rust pieces

## 0. How to use this Skill

The `swarm-engineering` skill owns the **process** — what a lane does, what it
reports — and the `swarm-craft-shared` Skill owns the **shared pieces** that hold in every
language. This Skill owns the **idioms**: the Rust rules that are not generic,
the version floors they carry, and the traps this language has shipped. Read
the piece that matches what you are changing, before you change it. Everything
here is checkable: a rule you cannot check is advice, not guidance.

## 1. The surface: layout, packaging, the version floor

* `cargo new` for a package: `src/lib.rs` or `src/main.rs`.
* A `[workspace]` groups the crates of one repository.
* Declare the floor in `Cargo.toml` as `rust-version = "1.85"`.
* Cargo 1.56 and later read it; CI runs the suite on that toolchain.
* Pin the compiler in `rust-toolchain.toml`: `channel`, `components`.
* Edition 2021 needs Rust 1.56; edition 2024 needs Rust 1.85.
* `cargo build`, `cargo test`, `cargo clippy`, `cargo fmt` are the tools.

## 2. Typing

* Absence is `Option<T>`, failure is `Result<T, E>` — Python's `None` and
  Java's `null` have no equivalent.
* No implicit numeric conversion: a `u32` does not become a `u64`.
* `as` casts never fail: `u32 as u8` drops high bytes, `i32 as u32`
  reinterprets the sign — use `TryFrom`.
* `Display` for the user, `Debug` for the programmer; `?` needs `E: Debug`.
* `impl Trait` for a parameter or return type you do not name; `dyn Trait`
  for a trait object.

## 3. Data modelling

* An `enum` for a closed set of states, a `struct` for a record; two `bool`
  flags that must not both be true become an `enum`.
* Derive what you mean: `#[derive(Clone, Debug, PartialEq, Eq, Hash)]` —
  without `Eq` a `HashMap` key breaks.
* Parse at the boundary: `UserId::parse` returns `Result<UserId, ParseError>`.
* `serde` with `derive` for wire types; `deny_unknown_fields` on input.
* Reach for a trait when the behaviour is shared, not for one caller.

## 4. Collections and the standard library

* `Vec`, `HashMap`/`BTreeMap`, `HashSet`/`BTreeSet`, `VecDeque` cover most
  needs; `BTreeMap` when you need sorted order or a range.
* Unlike JavaScript's `Map`, `HashMap` iteration order is randomised.
* `map.entry(k)` looks up and inserts in one pass: `Vacant` gives an
  `Entry` to `insert` into, `Occupied` the value already there.
* `or_insert_with(|| ...)` is lazy; `or_insert(x)` is not.
* `String` and `str` are UTF-8; `str::len()` counts bytes, not characters.

## 5. Iteration and laziness

* `Iterator` is lazy: `map` and `filter` do nothing until the chain is
  consumed by `collect`, `sum` or a `for` loop.
* `iter()` borrows, `iter_mut()` borrows mutably, `into_iter()` consumes.
* `filter_map` beats `filter(..).map(..)`: one pass, no `Option` left.
* `collect::<Result<Vec<_>, _>>()` stops at the first error.
* Borrow before you clone: a `clone()` added to satisfy the borrow checker
  means the ownership is wrong.
* `group_by` needs the input sorted by the key first — the `groupby` trap.

## 6. Errors and the Result type

* A library returns errors; it does not panic. Go returns the error as its
  last value, Java throws — Rust returns `Result`.
* `?` propagates and converts: the error type must implement `From` for the
  inner error, or `?` will not compile.
* `unwrap`/`expect` only where the invariant is written down — never on a
  file, an argument, the network or the environment.
* A custom error implements `std::error::Error` and names its cause;
  `thiserror` derives it.

## 7. Resources

* `Drop` is the cleanup: a `File`, a `MutexGuard`, a socket all release on
  scope exit, including on an early return or a panic.
* There is no `finally`; `Drop` is the equivalent, and it runs while the
  panic unwinds.
* `Drop` cannot be async — hand a future that must await back to the caller.
* `mem::forget` leaks on purpose; `ManuallyDrop` bypasses `Drop` deliberately.
* A `MutexGuard` held across an `.await` is a deadlock. See §11.

## 8. Files and paths

* `Path` and `PathBuf`, never a `String` path: `Path::join` and
  `PathBuf::push` build a path, `format!("{}/{}", dir, name)` does not.
* `Path::new` borrows, `PathBuf::from` owns; a reader takes `&Path`.
* `fs::canonicalize` resolves symlinks and fails if the path does not
  exist. A path is not normalised: `a/./b` and `a/b` differ.
* Write atomically when a reader may see a partial file: write a temporary
  file in the same directory, then `fs::rename` over it.
* Rust does not translate newlines: `writeln!` writes `\n` everywhere.

## 9. The shell and the outside world

* `Command::new("prog").arg(x)` — an argument list, never a shell string.
  `Command` does not spawn a shell.
* Unlike Python's `subprocess.run(check=True)`, a non-zero exit is not an
  error: check `status.code()` yourself.
* On Windows a `.bat` or `.cmd` target still goes through `cmd.exe`.
* `Command::output()` captures both streams; `Command::status()` inherits
  them. A child that fills the pipe buffer blocks until you read.
* `std::process::exit` skips every `Drop` — return an `ExitCode` instead.

## 10. Time and clocks

* `Instant` for a duration: it is monotonic, so a clock change cannot make
  it run backwards. `SystemTime` is for a wall-clock stamp.
* `Instant::now()` and `SystemTime::now()` are the only places that read
  the clock. Take "now" as an argument to make the code testable.
* `Instant + Duration` panics on overflow; `checked_add` returns `None`.
* `Duration::from_secs` and `as_millis` are integers — no float rounding.
* `chrono` or `time` for calendars; the standard library has no calendar.

## 11. Concurrency

* `Send` moves a value to another thread, `Sync` shares `&T`; `Rc` is neither.
* `Arc<Mutex<T>>` across threads, `Rc<RefCell<T>>` in one thread: a
  `RefCell` panics at runtime on a double borrow, `&mut` would not.
* `Mutex::lock` returns a `Result` because of poisoning.
* A `tokio::spawn`ed future must be `Send + 'static`; clone the data it needs.
* Never hold a `std::sync::MutexGuard` across an `.await`: the task that
  needs the lock can never run, and the program deadlocks.
* `cargo clippy -- -W clippy::await_holding_lock` reports that guard.
* A blocking call inside an async task stalls the whole executor: use
  `tokio::fs`/`tokio::net` or `spawn_blocking`.

## 12. Testing

* `cargo test` runs the unit tests, the integration tests and the doctests.
* Unit tests live in `#[cfg(test)] mod tests`; integration tests in `tests/`.
* A shared helper goes in `tests/common/mod.rs`, not `tests/common.rs` — a
  `.rs` file directly in `tests/` is compiled as its own test binary.
* `#[should_panic(expected = "...")]` pins the panic message.
* Compare floats with an explicit epsilon; `a == b` on `f64` is a flaky assert.
* `tempfile::tempdir()` for a temporary directory, never the repository.
* `cargo test --release` when timing matters; the debug profile is slow.

## 13. The command line

* `clap` with the `derive` feature for a real CLI; `std::env::args` for a
  script with one flag.
* `std::env::args()` panics if an argument is not valid Unicode; `args_os()`
  does not. Use `args_os` when the arguments may be paths.
* `main` returns `ExitCode` (Rust 1.61 and later) or `Result<(), Box<dyn
  Error>>`; `std::process::exit` skips the destructors.
* Results go to stdout, diagnostics to stderr, one diagnostic per failure.

## 14. Performance

* `cargo build --release` before you measure: the debug profile keeps
  `debug_assertions` and `overflow-checks` on.
* `cargo bench` with `criterion` for a number you can compare; a benchmark
  with no baseline is an anecdote.
* Profile before you change: `cargo flamegraph` (third-party), `perf`, or
  `samply`. Optimise what the profile names.
* `sort_unstable_by_key` allocates no buffer, but it is not a stable sort.
* A `clone()` in a loop is the usual cost — borrow instead, or use `Cow`.

## 15. Style, naming and docstrings

* `snake_case` for functions and variables, `CamelCase` for types and traits,
  `SCREAMING_SNAKE_CASE` for `const` and `static`.
* `rustfmt` is the format of record (`cargo fmt --check` to verify) and
  `clippy` the lint of record (`cargo clippy --all-targets -- -D warnings`).
* `///` is the doc comment and the published documentation; `//!` is the
  module documentation. `#![warn(missing_docs)]` for a library.
* A doc comment says what the caller must know: the contract, the failure
  modes, the panics.

## 16. Dependencies and environments

* `Cargo.toml` holds `[dependencies]`, `[dev-dependencies]` and
  `[build-dependencies]`; `Cargo.lock` holds the resolved versions.
* Commit `Cargo.lock` for a binary, not for a library; CI runs
  `cargo build --locked` so the lock file is honoured.
* `rust-version` is the floor you promise; a dependency with a higher floor
  raises yours — check the dependency's own metadata.
* Features are additive: a dependent cannot switch one off. `cargo tree -e
  features` shows what is enabled.

## 17. Logging and diagnostics

* `tracing` for structured events and spans, `tracing-subscriber` for the
  subscriber; `log` only to interop with a crate that uses it.
* `tracing::info!(user_id = %id, "loaded user")` — the fields are
  structured, so a machine can read them as well as a human.
* A library logs; a binary prints. `println!` in a library takes over the
  caller's terminal.
* Levels mean something: `error` — someone must act; `warn` — a tolerated
  surprise; `info` — the milestones; `debug` — the noise.

## 18. Security

* `unsafe` needs a `// SAFETY:` comment saying why the operation is sound;
  `#![forbid(unsafe_code)]` where it is not needed (Rust 1.52).
* `cargo +nightly miri test` checks `unsafe` code for undefined behaviour.
* Integer overflow wraps in release: use `checked_*`, or set
  `overflow-checks = true` in the release profile.
* Secrets come from the environment, never a default value; `OsRng` for a token.
* Normalise an outside path, then check `canonicalize` and `starts_with`.

## 19. The common traps

A checklist, not a style guide — each line is a bug that has shipped:

* `unwrap()` or `expect()` on a value from outside the program.
* `panic!`, `todo!()` or `unimplemented!()` left in a library.
* `Rc`/`RefCell` shared across threads — the fix is `Arc`/`Mutex`.
* A lock guard held across an `.await`.
* A blocking call inside an async task, stalling the executor.
* A `clone()` added to escape the borrow checker — use `mem::take`.
* `unwrap_or(expensive())` — the default runs on the hit path too.
* `str::len()` counts bytes; it was read as characters.
* `HashMap` iteration order assumed to be stable.
* An `as` cast that truncates a value that did not fit.
* `std::process::exit()` skipping every `Drop`.
* `std::env::args()` panicking on a non-UTF-8 argument.
* `println!` in library code; `unsafe` with no `// SAFETY:` comment.
* `Cargo.lock` committed for a library, or missing for a binary.
