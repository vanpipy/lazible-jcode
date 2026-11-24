---
name: swarm-craft-go
description: The Go pieces - the idioms, the version floors and the traps, one section per topic. Read in any lane that changes Go code, before it changes it.
---

# The Go pieces

## 0. How to use this Skill

The `swarm-engineering` skill owns the **process** — what a lane does, what it
reports — and the `swarm-craft-shared` Skill owns the **shared pieces** that hold in every
language. This Skill owns the **idioms**: the Go rules that are not generic, the
version floors they carry, and the traps this language has shipped.

Read the piece that matches what you are changing, before you change it. A
brief names the piece: "read section 6 of the Go craft before you touch the
error handling". Everything here is checkable — if a rule cannot be checked,
treat it as advice rather than guidance.

Go differs from the other languages in this craft set in ways that change the
code, not the style: there is no exception, no null in the type system, no lazy
sequence, and no runtime that tracks a goroutine for you.

## 1. The surface: layout, packaging, the version floor

* One module, one `go.mod` at the root; the module path is the import prefix.
* The `go` directive is the language version; since Go 1.21 also the toolchain.
* A `go 1.22` directive turns on the per-iteration loop variable (section 5).
* `go build ./...`, `go vet ./...`, `gofmt -l .` and `go test ./...` are the checks.
* `gofmt -l` must print nothing; `//go:build` picks files by tag (Go 1.17).

## 2. Typing

* `nil` is a value of every pointer, slice, map, channel and interface type.
* The type system, unlike Java's or TypeScript's, cannot stop a nil deref.
* The zero value of every type is usable: `var b bytes.Buffer` needs no setup.
* An interface is satisfied implicitly; keep it in the package that uses it.
* Accept interfaces, return concrete types; `any` (Go 1.18) over `interface{}`.
* Generics (Go 1.18) for a container or an algorithm; a constraint is a type set.
* A type assertion `v := i.(T)` panics; use `v, ok := i.(T)` unless guaranteed.

## 3. Data modelling

* A struct, not `map[string]any`: a map field has no shape a reader can see.
* A named type for a closed set (`Status`) and for an identity (`UserID`).
* Validate once at the boundary and convert; inside, assume validity.
* A struct copies by value, and a copy of a slice field shares its array.
* A struct is comparable only when every field is; a slice field breaks `==`.
* Either the zero value is right, or the doc says how to build a valid one.

## 4. Collections and the standard library

* `slices` and `maps` are standard since Go 1.21: `slices.Sort`, `maps.Clone`.
* `slices.Sort` is not stable; `slices.SortStableFunc` when equal order matters.
* `maps.Keys` returns a slice in Go 1.21 and an iterator in Go 1.23.
* A nil map reads fine, a write to it panics: "assignment to entry in nil map".
* `append` may write into another slice's spare capacity over the same array.
* `bytes.Buffer` over `+=` in a loop; `sync.Map` only for what it is tuned for.

## 5. Iteration and the loop variable

* No lazy sequence, unlike a Python generator: `range` walks the slice first.
* The loop variable is per iteration since Go 1.22; below that floor copy it.
* Map iteration order is randomised; sort the keys when the order matters.
* `for i, v := range s` copies the element; assign to `s[i]` to change it.
* A `range` over a channel ends when it is closed; `v, ok := <-ch` tells a close.
* A `range` over a nil channel blocks forever: the goroutine waits for ever.
* A `defer` inside a loop runs at the end of the function, not the iteration.

## 6. Errors

* The error is the last return value: handle it, or say why it is safe to ignore.
* `fmt.Errorf("read %s: %w", name, err)` keeps the chain (Go 1.13).
* `errors.Is` and `errors.As` walk that chain; `==` does not.
* Compare with the sentinel (`errors.Is(err, fs.ErrNotExist)`), never the text.
* `errors.Join` (Go 1.20) combines errors without losing either.
* `panic` belongs in `main` and in tests; `recover` works only in a defer.
* `os.Exit` and `log.Fatal` skip the deferred functions, so a file stays open.
* `go vet`'s lostcancel check flags a `context.WithCancel` whose cancel is lost.

## 7. Resources

* `defer f.Close()` right after the open, `defer mu.Unlock()` after `mu.Lock()`.
* `defer` runs at function exit, last in first out — not at the end of a block.
* To see the close error: `defer func() { err = errors.Join(err, f.Close()) }()`.
* `sync.Once` for a one-time init, `sync.OnceValue` (Go 1.21) for a return value.
* `runtime.SetFinalizer` is not a destructor: close what you opened.
* Reuse one `http.Client`; a client per request loses the connection pool.

## 8. Files and paths

* `os.ReadFile`, `os.WriteFile` and `os.MkdirTemp` (Go 1.16); `ioutil` is old.
* `filepath.Join` and `filepath.Clean`; never join a path with `"/"`.
* A path from outside must stay under its root: `filepath.Abs` plus `filepath.Rel`.
* `os.Root` (Go 1.24) confines the access itself, below the check.
* `os.Create` truncates; an append-only file wants `os.O_APPEND|os.O_CREATE`.
* Write atomically: a temp file in the same directory, then `os.Rename`.
* `bufio.Scanner` stops at 64 KiB per token and returns `bufio.ErrTooLong`.

## 9. The shell and the outside world

* `exec.Command` and `exec.CommandContext` take an argument list, not a shell.
* Never `sh -c` with input you did not write.
* `cmd.Run()` returns an `*exec.ExitError`: check the exit code and the stderr.
* `cmd.CombinedOutput()` gives a short command's output as one string.
* A command inherits no streams: set `cmd.Stdin`, `cmd.Stdout`, `cmd.Stderr`.
* `http.NewRequestWithContext`, and `defer resp.Body.Close()` on every response.
* Give an `http.Client` a `Timeout`; the default is none at all.

## 10. Time and clocks

* `time.Now()` carries a monotonic reading and `time.Since(start)` uses it.
* `time.Now().UTC()` for a stamp that leaves the process.
* Compare instants with `t.Equal(u)`, never `==`: the internal parts differ.
* Store UTC, convert at the edge.
* `time.Duration` is int64 nanoseconds: `30 * time.Second`, never a bare `30`.
* Take "now" as an argument, so the code can be tested at a fixed moment.
* `time.After` in a loop leaves a timer running; use `time.NewTimer` and stop it.

## 11. Concurrency

* Every goroutine needs a way to stop: a context it watches, a channel closed.
* A goroutine blocked on a channel nobody closes is a leak.
* `context.Context` is the first parameter of anything that can block.
* It is never a struct field, and a library must not call `context.Background()`.
* The sender closes a channel, the receiver never does; closing twice panics.
* One owner for shared mutable state; a mutex is not the owner.
* `sync.WaitGroup` for a fixed set of goroutines, `errgroup` to cancel on error.
* `atomic.Int64` (Go 1.19) over `atomic.AddInt64` on a raw field.
* `go test -race ./...` reports only the races it actually executes.

## 12. Testing

* `testing` from the standard library, in a `_test.go` file beside the code.
* Table-driven: a slice of cases, one `t.Run` per case.
* `t.Helper()` in a helper, so the failure points at the caller.
* `t.TempDir()` (Go 1.15) for files, `t.Setenv` (Go 1.17) for the environment.
* A test that writes into the repository fails in somebody else's checkout.
* `httptest.NewServer` for a server, `httptest.NewRecorder` for a handler.
* `go test ./... -count=1` defeats the cached result; `-run` selects the cases.
* `t.Parallel()` only when the test touches no shared global state.
* Fuzzing: `FuzzX(f *testing.F)` with a seed corpus, run with `-fuzz` (1.18).

## 13. The command line

* `flag` for a simple binary, a dispatcher of your own for subcommands.
* Parse in `main`, never in `init()`; `flag.Args()` for the positional arguments.
* `flag` writes the usage to stderr and exits 2 on a parse error.
* Exit 0 on success, a documented non-zero on failure; the message on stderr.
* `os.Exit` skips the deferred functions, so close and flush before you exit.
* Offer `--json` for a machine consumer and keep the human output stable.

## 14. Performance

* Measure first: `go test -bench=. -benchmem`; `-benchmem` counts allocations.
* `pprof` for a profile; `go build -gcflags='-m'` shows the escape analysis.
* Preallocate with `make([]T, 0, n)` when the size is known.
* Use `strconv` where `fmt.Sprintf` would do.
* `sync.Pool` for buffers that churn; one buffer per goroutine, not per call.
* Complexity first: an O(n^2) loop beats any constant-factor tuning.
* `go build -trimpath` for a reproducible build path.

## 15. Style, naming and docstrings

* `CamelCase` exported, `camelCase` unexported; initialisms all caps: `UserID`.
* A package name is one short lowercase word, no underscore, no `util`.
* A doc comment starts with the name it documents: "ParseConfig reads the file.".
* A comment says why, the code says what; delete commented-out code.
* The receiver name is the same on every method of a type, pointer or value.
* Named fields over embedding: an embedded struct hides where fields came from.
* `gofmt` is the style of record — its output beats a reviewer's taste.

## 16. Dependencies and environments

* The standard library first: a dependency is a contract you did not write.
* `go.mod` declares the direct requirements, `go.sum` pins the content.
* `go mod tidy` keeps them; read the `go.sum` diff when it changes.
* `go mod verify` checks the module cache against `go.sum`.
* One version of a module: minimal version selection takes the highest.
* `go.work` for local work across modules; a `replace` is a local override.

## 17. Logging and diagnostics

* `log/slog` (Go 1.21) for structured logs: `slog.NewJSONHandler`.
* A library logs and a program prints; `fmt.Println` takes over the terminal.
* Log at the boundary of an operation, with the identifiers to correlate lines.
* Levels mean something: error is someone must act, warn a tolerated surprise.
* One diagnostic per failure, on stderr; results go to stdout.
* `log.Fatal` exits and skips the deferred functions — so does `os.Exit`.
* Never log a secret, a token or a whole payload.

## 18. Security

* `crypto/rand` for keys, tokens and nonces; `math/rand` is not secret.
* `subtle.ConstantTimeCompare` when the timing of a comparison matters.
* `html/template` for HTML — it escapes for the context; `text/template` does not.
* Parameterised queries, never a query built by concatenation.
* Normalise a path from outside; `os.Root` (Go 1.24) confines the access itself.
* A secret comes from the environment, never a default that hides a missing config.
* `exec.Command` with an argument list, never a shell string.
* `tls.Config` with `MinVersion: tls.VersionTLS12`.

## 19. The common traps

A checklist, not a style guide — each line is a bug that has shipped:

* A nil interface holding a typed nil pointer: `i != nil` is true.
* A goroutine blocked on a channel nobody closes.
* An ignored `err`: `_ = f()` with no comment.
* A write to a nil map: "assignment to entry in nil map".
* A `defer` inside a loop, which runs at the end of the function.
* `os.Exit` or `log.Fatal` skipping the deferred close.
* Two slices over one backing array, `append` into the other's spare capacity.
* `==` on two `time.Time` values that are the same instant.
* A map iteration whose order the result depends on.
* A loop variable captured by a goroutine in a module below `go 1.22`.
* `strings.Split(s, ",")` on an empty string: one empty element.
* `strconv.Atoi` with the error dropped, `fmt.Sscanf` with a partial parse.
* A type assertion without the `ok` form.
* `json.Unmarshal` ignoring an unknown field; `map[string]any` makes ints float64.
* `bufio.Scanner` stopping at 64 KiB.
