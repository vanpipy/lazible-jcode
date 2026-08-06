// Package notifier sends NotifySession requests to a jcode server over
// its unix socket. It also implements the "fallback to coordinator"
// behavior: if the target session is dead, retry once with the swarm
// coordinator (looked up via coordinator.Lookup).
//
// Wire shape reference (read-only source):
//   /home/leroy/Project/jcode/crates/jcode-protocol/src/wire.rs:188
//     Request::NotifySession { id: u64, session_id: String, message: String }
//     #[serde(rename = "notify_session")]
//
// Socket path reference (read-only source):
//   /home/leroy/Project/jcode/crates/jcode-app-core/src/server/socket.rs:7
//     pub fn socket_path() -> PathBuf {
//         if let Ok(custom) = std::env::var("JCODE_SOCKET") {
//             return PathBuf::from(custom);
//         }
//         crate::storage::runtime_dir().join("jcode.sock")
//     }
//
// runtime_dir precedence: $JCODE_RUNTIME_DIR > $XDG_RUNTIME_DIR (linux)
// > $TMPDIR (macos) > temp_dir(). See
// /home/leroy/Project/jcode/crates/jcode-storage/src/lib.rs:97.
package notifier

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"time"

	"github.com/1jehuang/lazible-jcode/tick/internal/coordinator"
)

// Notifier sends one NotifySession request per call.
type Notifier struct {
	socketPath string
	nextID     atomic.Uint64
	repoPath   string // for coordinator fallback; "" means don't fallback
}

// New constructs a Notifier bound to the given socket path.
//
// repoPath is the absolute path of the repo whose swarm JSON holds the
// coordinator fallback. Pass "" to disable fallback (NotifySession will
// return any error it gets without retrying).
//
// repoPath is also sent as the Subscribe handshake's working_dir.
// jcode requires Subscribe with an absolute working_dir before any
// stateful request on a new connection; without it, notify_session is
// rejected with "Client must Subscribe with a working_dir before
// sending stateful requests" (see jcode's
// crates/jcode-app-core/src/server/client_lifecycle.rs:463-477).
// When repoPath is empty, the handshake is skipped and notify_session
// is sent directly; jcode will reject it. Callers that need a working
// notify_session MUST set repoPath to an absolute path.
func New(socketPath, repoPath string) *Notifier {
	return &Notifier{socketPath: socketPath, repoPath: repoPath}
}

// DefaultSocketPath returns the jcode unix socket path, mirroring
// the implementation in
// /home/leroy/Project/jcode/crates/jcode-app-core/src/server/socket.rs:7.
//
// Override order:
//   - $JCODE_TICK_SOCKET (test override)
//   - $JCODE_SOCKET (jcode's own override)
//   - $JCODE_RUNTIME_DIR/jcode.sock
//   - $XDG_RUNTIME_DIR/jcode.sock
//   - $TMPDIR/jcode.sock (macos)
//   - os.TempDir()/jcode-<user-discriminator>/jcode.sock (fallback)
func DefaultSocketPath() string {
	if d := os.Getenv("JCODE_TICK_SOCKET"); d != "" {
		return d
	}
	if d := os.Getenv("JCODE_SOCKET"); d != "" {
		return d
	}
	if d := os.Getenv("JCODE_RUNTIME_DIR"); d != "" {
		return filepath.Join(d, "jcode.sock")
	}
	if d := os.Getenv("XDG_RUNTIME_DIR"); d != "" {
		return filepath.Join(d, "jcode.sock")
	}
	if d := os.Getenv("TMPDIR"); d != "" {
		return filepath.Join(d, "jcode.sock")
	}
	return filepath.Join(os.TempDir(), "jcode.sock")
}

// wireMessage is the JSON we send. Field order matches the rust struct's
// derived Serialize impl (struct fields in declaration order).
//
// Wire reference (rust):
//   #[serde(rename = "notify_session")]
//   NotifySession { id: u64, session_id: String, message: String },
//
// We intentionally serialize with a stable struct order (no map) and
// include a trailing newline as the rust client_api does:
//   `let json = serde_json::to_string(&request)? + "\n";`
type wireMessage struct {
	Type      string `json:"type"`
	ID        uint64 `json:"id"`
	SessionID string `json:"session_id"`
	Message   string `json:"message"`
}

// subscribeWire is the JSON for the Subscribe handshake message.
// Wire reference (rust, jcode-protocol/src/wire.rs:115):
//   #[serde(rename = "subscribe")]
//   Subscribe { id: u64, working_dir: Option<String>, ... }
//
// jcode's client_lifecycle.rs:463-477 requires every stateful request
// from a new connection to be preceded by a Subscribe with an absolute
// working_dir. jcode rejects notify_session with:
//   "Client must Subscribe with a working_dir before sending
//    stateful requests"
// See docs/TICK_DAEMON_FAILURE_2026-08-05.md for the empirical
// reproduction that exposed this gap.
type subscribeWire struct {
	Type       string `json:"type"`
	ID         uint64 `json:"id"`
	WorkingDir string `json:"working_dir"`
}

// wireResponse is the subset of Response we parse. jcode's full
// Response enum has dozens of variants; we only need to distinguish
// "error" (failure → fallback) from anything else (success).
type wireResponse struct {
	Type    string `json:"type"`
	ID      uint64 `json:"id"`
	Message string `json:"message"`
}

// NotifySession sends one NotifySession to sessionID. On error response
// from jcode, OR on transport error, retry once via the swarm
// coordinator (if repoPath was configured at construction).
//
// Self-wake detection: if repoPath is configured and the target session
// matches the swarm coordinator's session id, NotifySession refuses
// with ErrSelfWake and performs no socket I/O. The jcode runtime
// silently swallows NotifySession calls targeted at the coordinator
// when the coordinator is in "waiting for user input" state — the daemon
// would otherwise ack the request, remove the job from store, and the
// message would never be delivered. See docs/TICK_SELF_WAKE_GAP.md.
//
// Detection is fail-safe: if coordinator.Lookup errors (missing swarm
// JSON, read error, etc.) the check is skipped and normal flow proceeds.
//
// Returns the final outcome. ctx may be used for cancellation.
func (n *Notifier) NotifySession(ctx context.Context, sessionID, message string) error {
	if n.repoPath != "" {
		if coordID, cerr := coordLookup(n.repoPath); cerr == nil && coordID == sessionID {
			if _, already := selfWakeLogged.LoadOrStore(sessionID, struct{}{}); !already {
				fmt.Fprintf(os.Stderr, "tick: self-wake refused for session=%s; job will remain in store as warning\n", sessionID)
			}
			return ErrSelfWake
		}
	}

	if err := n.send(ctx, sessionID, message); err != nil {
		if n.repoPath == "" {
			return err
		}
		coordID, cerr := coordinator.Lookup(n.repoPath)
		if cerr != nil || coordID == "" || coordID == sessionID {
			return err
		}
		// Fallback: send to coordinator with a "[tick-fallback]" prefix so
		// the coordinator knows this was meant for a different session.
		fallbackMsg := fmt.Sprintf("[tick-fallback] target=%s dead; original: %s", sessionID, message)
		if ferr := n.send(ctx, coordID, fallbackMsg); ferr != nil {
			return fmt.Errorf("primary notify failed: %v; fallback to coordinator failed: %w", err, ferr)
		}
		return nil
	}
	return nil
}

// dialContext is a package-level seam for tests to substitute a fake
// network dialer. Production code uses net.Dialer.DialContext.
var dialContext = func(ctx context.Context, network, addr string) (net.Conn, error) {
	var d net.Dialer
	return d.DialContext(ctx, network, addr)
}

// coordLookup is a package-level seam for tests to substitute the
// coordinator session ID lookup. Production code uses coordinator.Lookup.
var coordLookup = coordinator.Lookup

// ErrSelfWake is returned when NotifySession is called with a
// wake_session_id that matches the swarm coordinator. Self-wake is
// silently swallowed by the jcode runtime in "waiting for user input"
// sessions; the daemon refuses the job to make the failure visible.
// See docs/TICK_SELF_WAKE_GAP.md for the empirical reproduction
// (2026-08-05).
var ErrSelfWake = errors.New("tick: self-wake refused; NotifySession on the coordinator session is silently swallowed by the jcode runtime; use a different scheduler or target another session")

// selfWakeLogged deduplicates the stderr warning per session ID so a
// burst of self-wakes does not flood the daemon log.
var selfWakeLogged sync.Map // map[string]struct{}

// send is the single-attempt helper. Opens one connection to jcode's
// unix socket, sends Subscribe first (when repoPath is configured),
// then sends notify_session. Both requests and both responses flow
// over the same connection. Returns nil on success, an error
// otherwise. The error is meant for the caller to log / fallback on.
//
// The Subscribe handshake is mandatory. Skipping it causes jcode to
// reject notify_session with "Client must Subscribe..." and the
// scheduler silently swallows the error (scheduler.go:151: `_ =
// notify(j)`), producing the "jobs pile up, nothing fires" failure
// mode documented in docs/TICK_DAEMON_FAILURE_2026-08-05.md.
//
// A single *bufio.Reader is created on top of the connection and
// reused across both requests. The bufio buffer absorbs excess bytes
// from the underlying conn on each ReadBytes call, which is required
// for the second read to see the second response — creating a fresh
// bufio.Reader per request would buffer ahead past the first response
// boundary on the first request and starve the second read.
func (n *Notifier) send(ctx context.Context, sessionID, message string) error {
	conn, err := dialContext(ctx, "unix", n.socketPath)
	if err != nil {
		return fmt.Errorf("dial %s: %w", n.socketPath, err)
	}
	defer conn.Close()

	// Apply a 2-second deadline for the whole request, so a wedged
	// jcode server cannot block the scheduler.
	if dl, ok := ctx.Deadline(); ok {
		conn.SetDeadline(dl)
	} else {
		conn.SetDeadline(time.Now().Add(2 * time.Second))
	}

	br := bufio.NewReader(conn)

	if n.repoPath != "" {
		if err := writeRequest(conn, br, subscribeWire{
			Type:       "subscribe",
			ID:         n.nextID.Add(1),
			WorkingDir: n.repoPath,
		}); err != nil {
			return fmt.Errorf("subscribe handshake: %w", err)
		}
	}

	return writeRequest(conn, br, wireMessage{
		Type:      "notify_session",
		ID:        n.nextID.Add(1),
		SessionID: sessionID,
		Message:   message,
	})
}

// writeRequest marshals payload to JSON, writes it with a trailing
// newline to w, reads exactly one response line from br, and returns
// nil on success or an error if the response is "error" or any
// transport/parse step fails. payload must serialize with a `type`
// field that jcode can route on. br MUST be a *bufio.Reader that
// wraps the same conn w writes to; the bufio buffer absorbs excess
// bytes between successive writeRequest calls on the same conn.
func writeRequest(w io.Writer, br *bufio.Reader, payload any) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal: %w", err)
	}
	body = append(body, '\n')
	if _, err := w.Write(body); err != nil {
		return fmt.Errorf("write: %w", err)
	}

	line, err := br.ReadBytes('\n')
	if err != nil && !errors.Is(err, io.EOF) {
		return fmt.Errorf("read response: %w", err)
	}
	if len(line) == 0 {
		return errors.New("empty response from server")
	}
	var resp wireResponse
	if err := json.Unmarshal(line, &resp); err != nil {
		return fmt.Errorf("parse response: %w (line=%q)", err, line)
	}
	if resp.Type == "error" {
		if resp.Message != "" {
			return fmt.Errorf("server error: %s", resp.Message)
		}
		return errors.New("server error")
	}
	return nil
}
