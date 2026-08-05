# tick — jcode-swarm-tick daemon

A mechanical 100ms-tick timer that fires delayed wake-ups to live jcode
sessions via the unix-socket `NotifySession` request. The daemon is dumb:
it holds a min-heap of `{fire_at_ms, session_id, message}` jobs and
sends them at the right time. All "smart" decisions (state evaluation,
fallback policy, conditional firing) live in the agent, not the daemon.

See `swarm/roles/tick-user.md` for the agent-side usage contract.

## Build

```sh
cd tick
go build -o tick .
# or build the module: go build ./...
```

Output: a single static-ish binary at `./tick`.

## CLI

```sh
# Run as an MCP server over stdio (long-running).
./tick mcp

# Submit a job and exit.
./tick submit <session_id> <fire_at> <message>
#   fire_at: "+5s", "+10m", "+1h", or absolute unix-ms

# Print pending jobs.
./tick list

# Cancel a pending job.
./tick cancel <job_id>

# Long-lived daemon (PID file written in a future release).
./tick start

# Usage.
./tick --help
```

## MCP tool contract

jcode spawns `tick` as an MCP subprocess on first use and registers its
tools. The tool surface is exactly three calls:

| Tool | Arguments | Returns |
| --- | --- | --- |
| `submit_job` | `wake_session_id: string`, `fire_in_seconds: number` (1..86400), `message: string` | `{job_id: string, fire_at_ms: number}` |
| `cancel_job` | `job_id: string` | `{cancelled: bool}` |
| `list_jobs` | — | `[{job_id, fire_at_ms, wake_session_id, message_preview}]` |

Wire format is JSON-RPC 2.0 over stdio, one object per line.

## Configuration (env vars)

| Var | Effect |
| --- | --- |
| `JCODE_TICK_SOCKET` | Override the jcode unix socket path (test escape hatch). |
| `JCODE_TICK_STATE_DIR` | Override the parent of `jobs.jsonl`. Default: `$XDG_STATE_HOME/jcode/tick/` or `~/.local/state/jcode/tick/`. |
| `JCODE_SOCKET` | jcode's own socket override (read by tick too). |
| `JCODE_RUNTIME_DIR` | jcode runtime dir (read by tick too). |
| `XDG_RUNTIME_DIR` | Linux runtime dir (read by tick too). |

## State

Pending jobs are persisted to `<state_dir>/jobs.jsonl` as JSONL.
On startup, `tick mcp` reloads this file and re-submits every job whose
`fire_at_ms` is still in the future. Jobs whose `fire_at_ms` is past
are dropped (the daemon was down too long for them to be meaningful).

## Behavior

- **Fire resolution**: 100ms (the tick interval).
- **Target dead → coordinator fallback**: if the wake session returns
  a server error or the socket is unreachable, the daemon retries once
  with the swarm coordinator (read from `~/.jcode/state/swarm/*.json`),
  prefixing the message with `[tick-fallback] target=X dead`.
- **Transport errors**: logged to stderr; the job is not retried by the
  daemon (caller is responsible for re-submitting if critical).

## What's intentionally NOT here

- `fire_if` conditions. The daemon always fires. The agent evaluates
  state on receipt.
- SwarmStatus subscriptions. The daemon does not maintain an alive
  table; it asks jcode on each fire and falls back once on error.
- Persistent PID file. `start` is currently an alias for `mcp`.

## Testing

```sh
cd tick
go test ./...
```

Tests cover:

- `internal/scheduler`: heap ordering, cancel, error-doesn't-stop-later.
- `internal/notifier`: wire shape against
  `jcode-protocol/src/wire.rs:188`, server-error response handling,
  dial-failure error path.