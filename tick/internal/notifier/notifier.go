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
// Returns the final outcome. ctx may be used for cancellation.
func (n *Notifier) NotifySession(ctx context.Context, sessionID, message string) error {
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

// send is the single-attempt helper. Returns nil on success, an error
// otherwise. The error is meant for the caller to log / fallback on.
func (n *Notifier) send(ctx context.Context, sessionID, message string) error {
	id := n.nextID.Add(1)
	payload := wireMessage{
		Type:      "notify_session",
		ID:        id,
		SessionID: sessionID,
		Message:   message,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal: %w", err)
	}
	body = append(body, '\n')

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

	if _, err := conn.Write(body); err != nil {
		return fmt.Errorf("write: %w", err)
	}

	// Read exactly one response line.
	r := bufio.NewReader(conn)
	line, err := r.ReadBytes('\n')
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