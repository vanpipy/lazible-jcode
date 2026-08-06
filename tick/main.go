// Command tick is the jcode-swarm-tick daemon — a mechanical timer
// that fires delayed wake-up jobs to live jcode sessions via the
// unix-socket NotifySession request.
//
// Subcommands:
//
//	mcp      Run as an MCP server over stdio (long-running).
//	submit   Submit one job and exit (CLI for humans / scripts).
//	list     Print pending jobs and exit.
//	cancel   Cancel a job by id and exit.
//	start    Long-lived daemon owning the heap (PID file); same as mcp
//	         today, kept for forward compatibility.
//	--help   Print usage.
//
// See ./README.md for full docs.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/1jehuang/lazible-jcode/tick/internal/coordinator"
	"github.com/1jehuang/lazible-jcode/tick/internal/job"
	"github.com/1jehuang/lazible-jcode/tick/internal/mcp"
	"github.com/1jehuang/lazible-jcode/tick/internal/notifier"
	"github.com/1jehuang/lazible-jcode/tick/internal/scheduler"
	"github.com/1jehuang/lazible-jcode/tick/internal/store"
)

// daemonSignals lists the OS signals the MCP-mode daemon responds to.
// SIGINT and SIGTERM are the conventional shutdown signals. SIGHUP is
// added so a terminal disconnect (or `kill -SIGHUP` from a user /
// process-group tear-down) does NOT kill the daemon — well-behaved
// Unix daemons ignore SIGHUP, treating it as a config-reload hook or
// no-op. Before this, SIGHUP triggered Go's default os.Exit, taking
// the daemon down and producing the "jobs pile up, nothing fires"
// failure mode documented in
// docs/TICK_DAEMON_FAILURE_2026-08-05.md §"Other findings" #1.
//
// Test-only seam: package main is the only place this list is
// referenced (signal.NotifyContext), but main_test.go needs the var
// to assert SIGHUP is present without spawning a real process.
var daemonSignals = []os.Signal{syscall.SIGINT, syscall.SIGTERM, syscall.SIGHUP}

// commitSHA and buildTime are injected at build time via
//
//	go build -ldflags "-X main.commitSHA=$(git rev-parse HEAD) \
//	                    -X main.buildTime=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
//
// They appear in the startup banner so an operator tailing daemon
// stderr can tell whether the running binary is post-fix (has
// Subscribe handshake + ErrSelfWake) or pre-fix (silent self-wake
// loss). The defaults are non-empty so `go run` and `go test` produce
// a valid banner without the linker flags.
var (
	commitSHA = "unknown"
	buildTime = "unknown"
)

// printStartupBanner writes a single-line identity record to w. The
// line is the only persistent fingerprint of which binary is
// running, so it MUST include the commit SHA, build timestamp, and
// PID. Format is intentionally greppable:
//
//	tick: pid=12345 commit=abc1234 built=2026-08-06T16:00:00Z
//
// The w parameter is an io.Writer seam so tests can capture the
// output without touching os.Stderr (which is captured but not
// inspectable from inside the test process).
func printStartupBanner(w io.Writer, pid int) {
	fmt.Fprintf(w, "tick: pid=%d commit=%s built=%s\n", pid, commitSHA, buildTime)
}

const usage = `tick — jcode-swarm-tick daemon.

USAGE:
  tick mcp                                     # run MCP server over stdio
  tick submit <session_id> <fire_at> <msg>     # fire_at: "+5s", "+10m", or epoch_ms
  tick list                                    # print pending jobs as JSON
  tick cancel <job_id>                         # cancel a pending job
  tick start                                   # long-lived daemon (PID file written)
  tick --help

ENV:
  JCODE_TICK_SOCKET    Override jcode unix socket path.
  JCODE_TICK_STATE_DIR Override jobs.jsonl parent dir.
  JCODE_SOCKET         jcode's own socket override.
  JCODE_RUNTIME_DIR    jcode runtime dir (default).
  XDG_RUNTIME_DIR      Linux runtime dir.
`

func main() {
	if len(os.Args) < 2 || os.Args[1] == "--help" || os.Args[1] == "-h" {
		fmt.Fprint(os.Stderr, usage)
		if len(os.Args) < 2 {
			os.Exit(2)
		}
		return
	}
	cmd := os.Args[1]
	args := os.Args[2:]

	switch cmd {
	case "mcp":
		os.Exit(runMCP())
	case "submit":
		os.Exit(runSubmit(args))
	case "list":
		os.Exit(runList())
	case "cancel":
		os.Exit(runCancel(args))
	case "start":
		// Same as mcp for MVP — future: write a PID file.
		os.Exit(runMCP())
	default:
		fmt.Fprintf(os.Stderr, "tick: unknown subcommand %q\n\n%s", cmd, usage)
		os.Exit(2)
	}
}

// --- MCP server entrypoint ---

func runMCP() int {
	ctx, cancel := signal.NotifyContext(context.Background(), daemonSignals...)
	defer cancel()

	// Banner identifies which binary is running so an operator tailing
	// stderr can detect a stale pre-fix binary (commit < 2e2f700)
	// without rebuilding.
	printStartupBanner(os.Stderr, os.Getpid())

	// Build the dependency stack: store + scheduler + notifier + MCP server.
	storePath := store.DefaultPath()
	st, err := store.New(storePath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "tick: store init: %v\n", err)
		return 1
	}
	notif := notifier.New(notifier.DefaultSocketPath(), coordinator.RepoPathFromCwd())

	// The notifier implements the NotifyFunc contract (job.Job → error).
	sched := scheduler.New(func(j job.Job) error {
		if err := notif.NotifySession(ctx, j.WakeSessionID, j.Message); err != nil {
			fmt.Fprintf(os.Stderr, "tick: fire %s failed: %v\n", j.ID, err)
			return err
		}
		// Persist: remove from store on successful fire.
		_ = st.Remove(j.ID)
		return nil
	})

	// Re-hydrate scheduler from store on startup.
	jobs, err := st.LoadAll()
	if err != nil {
		fmt.Fprintf(os.Stderr, "tick: store load: %v\n", err)
	} else {
		for _, j := range jobs {
			if j.FireAtMs <= time.Now().UnixMilli() {
				// Skip already-overdue jobs from a previous run; the
				// daemon was down for too long. Drop them from store.
				_ = st.Remove(j.ID)
				continue
			}
			if err := sched.Submit(j); err != nil {
				fmt.Fprintf(os.Stderr, "tick: re-submit %s: %v\n", j.ID, err)
			}
		}
	}

	// Background scheduler loop.
	go sched.Run(ctx)

	srv := mcp.New(sched, st, os.Stdin, os.Stdout)
	if err := srv.Run(ctx); err != nil && !errors.Is(err, context.Canceled) {
		fmt.Fprintf(os.Stderr, "tick: mcp: %v\n", err)
		return 1
	}
	return 0
}

// --- CLI helpers ---

// runSubmit parses <session_id> <fire_at> <message>, persists, and exits.
// fire_at accepts "+5s", "+10m", "+1h", or absolute unix-ms.
func runSubmit(args []string) int {
	if len(args) < 3 {
		fmt.Fprintln(os.Stderr, "tick submit: need <session_id> <fire_at> <message>")
		return 2
	}
	sessionID := args[0]
	fireAtSpec := args[1]
	message := strings.Join(args[2:], " ") // allow spaces in message

	fireAt, err := parseFireAt(fireAtSpec)
	if err != nil {
		fmt.Fprintf(os.Stderr, "tick submit: bad fire_at %q: %v\n", fireAtSpec, err)
		return 2
	}

	storePath := store.DefaultPath()
	st, err := store.New(storePath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "tick submit: store: %v\n", err)
		return 1
	}
	notif := notifier.New(notifier.DefaultSocketPath(), coordinator.RepoPathFromCwd())

	var fired []job.Job
	sched := scheduler.New(func(j job.Job) error {
		if err := notif.NotifySession(context.Background(), j.WakeSessionID, j.Message); err != nil {
			fmt.Fprintf(os.Stderr, "tick submit: fire failed: %v\n", err)
			return err
		}
		_ = st.Remove(j.ID)
		fired = append(fired, j)
		return nil
	})

	j := job.New(sessionID, message, fireAt)
	if err := sched.Submit(j); err != nil {
		fmt.Fprintf(os.Stderr, "tick submit: sched: %v\n", err)
		return 1
	}
	if err := st.Append(j); err != nil {
		fmt.Fprintf(os.Stderr, "tick submit: persist: %v\n", err)
		_ = sched.Cancel(j.ID)
		return 1
	}

	// CLI submit: try to fire immediately if fire_at is past or near.
	// Useful for testing without an MCP loop.
	go sched.Run(context.Background())
	// Brief wait so a "+0s" / past fire_at actually fires before exit.
	if j.FireAtMs <= time.Now().UnixMilli()+int64(200*time.Millisecond/time.Millisecond) {
		time.Sleep(500 * time.Millisecond)
	}

	out, _ := json.Marshal(map[string]any{
		"job_id":     j.ID,
		"fire_at_ms": j.FireAtMs,
		"fired":      len(fired) > 0,
	})
	fmt.Println(string(out))
	return 0
}

func runList() int {
	storePath := store.DefaultPath()
	st, err := store.New(storePath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "tick list: store: %v\n", err)
		return 1
	}
	all, err := st.LoadAll()
	if err != nil {
		fmt.Fprintf(os.Stderr, "tick list: load: %v\n", err)
		return 1
	}
	out, _ := json.Marshal(all)
	fmt.Println(string(out))
	return 0
}

func runCancel(args []string) int {
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "tick cancel: need <job_id>")
		return 2
	}
	id := args[0]
	storePath := store.DefaultPath()
	st, err := store.New(storePath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "tick cancel: store: %v\n", err)
		return 1
	}
	all, err := st.LoadAll()
	if err != nil {
		fmt.Fprintf(os.Stderr, "tick cancel: load: %v\n", err)
		return 1
	}
	found := false
	for _, j := range all {
		if j.ID == id {
			found = true
			break
		}
	}
	if !found {
		out, _ := json.Marshal(map[string]any{"cancelled": false, "reason": "not_found"})
		fmt.Println(string(out))
		return 0
	}
	if err := st.Remove(id); err != nil {
		fmt.Fprintf(os.Stderr, "tick cancel: remove: %v\n", err)
		return 1
	}
	out, _ := json.Marshal(map[string]any{"cancelled": true})
	fmt.Println(string(out))
	return 0
}

// parseFireAt accepts "+5s", "+10m", "+1h", or absolute unix-ms.
func parseFireAt(spec string) (time.Time, error) {
	if strings.HasPrefix(spec, "+") {
		d, err := time.ParseDuration(spec[1:])
		if err != nil {
			return time.Time{}, fmt.Errorf("offset: %w", err)
		}
		if d <= 0 {
			return time.Time{}, fmt.Errorf("offset must be positive")
		}
		return time.Now().Add(d), nil
	}
	// absolute unix-ms
	ms, err := strconv.ParseInt(spec, 10, 64)
	if err != nil {
		return time.Time{}, fmt.Errorf("not an offset and not an integer: %w", err)
	}
	return time.UnixMilli(ms), nil
}