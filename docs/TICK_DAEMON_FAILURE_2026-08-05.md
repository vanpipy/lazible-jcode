# tick daemon failure 2026-08-05

## TL;DR

The `jcode-swarm-tick` daemon was running, but **no `NotifySession`
request ever reached a live session** for at least 24 minutes. The
underlying bug is a protocol mismatch: tick's `notifier.go` sends
`notify_session` directly, but jcode's `client_lifecycle` requires a
preceding `Subscribe` handshake with an absolute `working_dir`. jcode
rejects every fire with:

```
{"type":"error","id":1,"message":"Client must Subscribe with a working_dir before sending stateful requests"}
```

The error is silently swallowed by the scheduler. Jobs accumulate in
the persistent store but never fire. A fix landed on
`feat/tick-subscribe-handshake_3dd2402` (see Resolution below).

## Symptom

- 11 jobs in the queue, every `fire_at_ms` already past by 1–7 minutes
- `list_jobs` returned the full set, no consumption
- `mcp__tick__list_jobs` worked (it reads the persistent store, not
  the scheduler)
- `mcp__tick__submit_job` returned a `job_id` (the write succeeded)
- `mcp__tick__cancel_job` returned `{"cancelled":false}` for unknown
  ids (correct), but a known pending id also returned `false` because
  the scheduler was not running to honor the cancel
- No session ever received a wake message

## Investigation chain

### 1. tick MCP tool reachability (working)

`mcp__tick__list_jobs` / `submit_job` / `cancel_job` all responded,
suggesting jcode's MCP shim was reading the persistent store directly
(or had cached responses). No protocol error surfaced at the tool
layer.

### 2. tick daemon process (alive but idle)

```
PID 157185, PPID 3248
ELAPSED 24:17
%CPU 0.1, %MEM 0.0, RSS 6812 KB
STAT Sl (interruptible sleep, multi-threaded)
```

The process existed, parented by `jcode serve` (PID 3248), but
`%CPU` was effectively zero. A 100ms-resolution scheduler loop
should have been visibly busy even with idle work.

### 3. tick self-wake to session_root (no actual fire)

Submitted a 5s job with `wake_session_id=session_root`:

- `submit_job` returned `job_id` and `fire_at_ms` correctly
- After 5s, `list_jobs` still showed the job in the queue
- After 8s, `cancel_job` returned `{"cancelled":false}` and the job
  remained

Two hypotheses to disambiguate:
- (a) tick refused self-wake and kept the job in store as a warning
- (b) tick was attempting to fire but the underlying transport
  rejected every call

### 4. cross-session probe (decisive)

Submitted a 5s job to `session_scorpion_*` (definitely not self).
After 8s, `list_jobs` still showed the job. This rules out (a) for
this particular job — the daemon was simply not firing.

### 5. direct socket probe (smoking gun)

Used Python to dial `/run/user/1000/jcode.sock` directly and send a
`notify_session`:

```python
import socket, json
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(2)
s.connect('/run/user/1000/jcode.sock')
s.sendall(json.dumps({"type":"notify_session","id":1,
  "session_id":"session_root",
  "message":"diag"}).encode() + b"\n")
print(s.recv(4096))
# b'{"type":"error","id":1,"message":"Client must Subscribe
#   with a working_dir before sending stateful requests"}\n'
```

jcode **did** respond (transport OK, id matched), but rejected with the
Subscribe-first error. This explained every observation:

- daemon alive, scheduler running, every Tick attempting to fire
- notifier.send() erroring on every call
- scheduler silently dropping the error (`_ = notify(j)`)
- jobs piling up in the store

### 6. protocol root cause

In `/home/leroy/Project/jcode/crates/jcode-protocol/src/wire.rs:115`:

```rust
/// Subscribe to events (for TUI clients)
#[serde(rename = "subscribe")]
Subscribe {
    id: u64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    working_dir: Option<String>,
    ...
}
```

In `/home/leroy/Project/jcode/crates/jcode-app-core/src/server/client_lifecycle.rs:84-97`:

```rust
"Subscribe requires the client's working directory".to_string()
"Subscribe working_dir must be an absolute path".to_string()
...
"Client must Subscribe with a working_dir before sending stateful
 requests".to_string()
```

jcode added a Subscribe-first requirement at some point. tick's
`internal/notifier/notifier.go` predates that change and sends
`notify_session` directly. The wire shape comment on line 7-23 of
notifier.go cites `wire.rs:188` as the spec for `notify_session`, but
that spec has moved (Subscribe is required first).

## Resolution

A fix branch was spawned:

- branch: `feat/tick-subscribe-handshake_3dd2402`
- base: `3dd2402` (current main at incident time)
- scope: add `subscribe()` helper in notifier.go that sends
  `{"type":"subscribe","id":N,"working_dir":"<abs repoPath>"}`
  before the existing `notify_session` write; update tests that
  previously expected 1 message to expect 2 messages + 2 responses
- validation: `go vet ./...` and `go test -race ./...` in `tick/`

Post-merge, root session is expected to:

1. Build the new binary: `cd tick && go build -o tick .`
2. Install: `cp tick/tick ~/.local/bin/jcode-swarm-tick`
3. Restart the jcode session (jcode's MCP child manager does not
   auto-respawn dead children — see Other findings §3)
4. Verify with a 5s cross-session probe that the new daemon
   actually delivers a wake

## Other findings (not addressed in this fix)

### 1. tick's signal handling leaves SIGHUP as a kill

`tick/main.go:88` registers only `SIGINT` and `SIGTERM`:

```go
ctx, cancel := signal.NotifyContext(context.Background(),
  syscall.SIGINT, syscall.SIGTERM)
```

`SIGHUP` is not handled. Go's default is `os.Exit` on unhandled
signals. During this investigation, sending `kill -SIGHUP` to the
daemon immediately terminated it. Most well-behaved Unix daemons
ignore SIGHUP (or use it to reload config). Tracked separately.

### 2. tick `start` is currently an alias for `mcp`

`tick/main.go:77-78`:

```go
case "start":
    // Same as mcp for MVP — future: write a PID file.
    os.Exit(runMCP())
```

The README advertises a separate `tick start` mode that "writes a
PID file", but the implementation is identical to `tick mcp`. The
"persistent daemon" mode documented in `config/mcp.json.example`
does not exist yet.

### 3. jcode MCP child manager does not auto-respawn dead children

From `crates/jcode-base/src/mcp/manager.rs:121-200` and
`pool.rs:341-390`:

- `McpManager::connect_all` is called at session start
- `McpManager::call_tool` has a "connect-on-first-call" path for
  not-yet-connected servers (manager.rs:327-393)
- But after a server connects, gets a handle, and that handle's
  child dies, the dead handle stays in `pool_handles`
- `ensure_connected` only triggers re-spawn via `connect_all` or
  `connect_server`, never on a dead-handle detection
- `McpClient::is_running()` exists (client.rs:327) but is never
  called from a watchdog

Result: a dead MCP child is not detected until the next
disconnect+reconnect (e.g. session end + new session start, or an
explicit `disconnect_server` followed by `connect_server`).

### 4. tick state location is `~/.local/state/`, not `/run/user/1000/`

`tick/internal/notifier/notifier.go:65-66` and `README.md` state the
store lives at `$XDG_STATE_HOME/jcode/tick/` or
`~/.local/state/jcode/tick/`. jcode's socket is at
`$XDG_RUNTIME_DIR/jcode.sock`. The two are different directories
and were sometimes confused in early triage.

### 5. Self-wake refusal is coordinator-based, not submitter-based

`tick/README.md:85` says:

> Self-wake detection: when `notify_session` targets the swarm
> coordinator's own session_id, the daemon refuses with `ErrSelfWake`.

Detection compares the wake target against
`coordinator.Lookup(repoPath).session_id`. It is **not** "is the
submitter the target?" — the swarm coordinator's session id is the
criterion. Early triage incorrectly assumed submitter==target was
the rule, which led to some wrong conclusions.

### 6. Per-connection notifier design is fine for the fix

The current `notifier.send` dials a fresh connection per
`NotifySession`. The Subscribe handshake adds one round-trip per
fire, which is acceptable on a local unix socket (< 1ms each).
A persistent-connection refactor would be a future optimization,
not required for correctness.

## Empirical evidence (raw)

- `mcp__tick__list_jobs` snapshot at 15:24:53Z returned 9 jobs;
  15:30:50Z (after SIGHUP) returned `[]` (shim still works,
  daemon dead)
- Python socket probe at 15:42:59Z returned the Subscribe-first
  error
- `mcp__tick__list_jobs` at 15:40:11Z timed out at 30s (matches
  the 30s request timeout in `client.rs:46`), confirming the
  tick child was not responding

## What would have caught this earlier

- A tick-side health check: after each `notifier.send` error,
  increment a counter; if the counter exceeds N within M seconds,
  log a single ERROR-level "tick notifier failing" so it surfaces
  in monitoring. Today the only signal is `tick: fire %s failed: %v`
  on stderr, which the user does not see.
- A liveness test in the tick repo that dials a fake jcode socket
  requiring Subscribe, and asserts the notifier sends Subscribe
  first. This would have caught the regression at the same commit
  that added jcode's Subscribe requirement.
- A cross-machine smoke test: when an agent submits a wake job,
  verify the target session actually receives a message within 1
  second. This is the user-visible contract; the current tests
  only assert the notifier's local view (which says "success"
  because the error path returns).

## Action items (post-fix)

- [ ] Build + install the new tick binary (root session)
- [ ] Restart jcode session (user)
- [ ] Verify with a cross-session 5s probe (root)
- [ ] File upstream issue against jcode: protocol requirements
      (Subscribe-first, working_dir absolute) should be documented
      in the wire.rs comment that other clients cite
- [ ] File upstream issue against jcode: MCP child manager should
      auto-respawn dead children (or at minimum, fail loudly
      instead of returning 30s timeouts on every tool call)
- [ ] File upstream issue against tick: SIGHUP should be ignored
      (or trigger a config reload), not terminate
- [ ] File upstream issue against tick: `tick start` should be a
      real daemon mode (fork + PID file + detaches from stdio)
- [ ] Add an integration smoke test in the tick repo: dial a fake
      jcode server that requires Subscribe, verify notifier sends
      it; second fake server that returns error, verify error
      surfaces

## Reference: what we read in the jcode source

- `crates/jcode-protocol/src/wire.rs:115-136` — Subscribe request
  shape
- `crates/jcode-protocol/src/wire.rs:730-733` — ServerEvent::Ack
- `crates/jcode-app-core/src/server/client_lifecycle.rs:84-97` —
  Subscribe working_dir requirement (absolute path)
- `crates/jcode-app-core/src/server/client_api.rs:67-95` — Rust
  client API for subscribe
- `crates/jcode-base/src/mcp/manager.rs:121-200, 327-393` — MCP
  manager connect / call_tool flows
- `crates/jcode-base/src/mcp/pool.rs:341-390` — ensure_connected
  with 30s cooldown on repeated failures
- `crates/jcode-base/src/mcp/client.rs:135-281` — McpClient
  connect (tokio Command::spawn over stdio)
- `crates/jcode-base/src/mcp/client.rs:327-346` —
  is_running / shutdown (no auto-respawn wiring)
- `crates/jcode-storage/src/lib.rs:97-118` — runtime_dir resolution

## Reference: what we read in the tick source

- `main.go:38-138` — runMCP: scheduler + notifier + re-hydrate
  on startup, MCP server over stdio
- `main.go:88` — signal handler (SIGINT, SIGTERM only)
- `internal/scheduler/scheduler.go:133-154` — Tick: pop from
  heap, delete from byID, then call notify (errors silently
  dropped, not retried, not refilled into heap)
- `internal/notifier/notifier.go:69-86` — DefaultSocketPath
  resolution (overrides via JCODE_TICK_SOCKET, JCODE_SOCKET,
  JCODE_RUNTIME_DIR, XDG_RUNTIME_DIR, TMPDIR, TempDir)
- `internal/notifier/notifier.go:130-157` — NotifySession: self-
  wake check, primary send, fallback to coordinator once
- `internal/notifier/notifier.go:184-236` — send: dial, write
  notify_session, read response — **missing Subscribe handshake**
