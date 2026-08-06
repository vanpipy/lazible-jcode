package notifier

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"strings"
	"testing"
	"time"
)

// fakeConn lets us capture the bytes the notifier writes without
// touching a real socket. It implements net.Conn.
type fakeConn struct {
	written bytes.Buffer
	readBuf io.Reader
	closed  bool
}

func (c *fakeConn) Read(b []byte) (int, error)             { return c.readBuf.Read(b) }
func (c *fakeConn) Write(b []byte) (int, error)            { return c.written.Write(b) }
func (c *fakeConn) Close() error                           { c.closed = true; return nil }
func (c *fakeConn) LocalAddr() net.Addr                    { return fakeAddr("local") }
func (c *fakeConn) RemoteAddr() net.Addr                   { return fakeAddr("remote") }
func (c *fakeConn) SetDeadline(t time.Time) error          { return nil }
func (c *fakeConn) SetReadDeadline(t time.Time) error      { return nil }
func (c *fakeConn) SetWriteDeadline(t time.Time) error     { return nil }

type fakeAddr string

func (a fakeAddr) Network() string { return "unix" }
func (a fakeAddr) String() string  { return string(a) }

// dialFunc replaces net.DialContext for tests.
type dialFunc func(ctx context.Context, network, addr string) (net.Conn, error)

// withDial saves and restores net.DialContext via package var swap.
func withDial(t *testing.T, fn dialFunc) {
	t.Helper()
	orig := dialContext
	dialContext = fn
	t.Cleanup(func() { dialContext = orig })
}

// coordLookupFunc replaces coordinator.Lookup for tests.
type coordLookupFunc func(repoPath string) (string, error)

// withCoordLookup saves and restores the coordLookup package var. Use
// this to inject fakes that simulate self-wake, missing swarm state, or
// different coordinator identities without touching the on-disk JSON.
func withCoordLookup(t *testing.T, fn coordLookupFunc) {
	t.Helper()
	orig := coordLookup
	coordLookup = fn
	t.Cleanup(func() { coordLookup = orig })
}

// TestNotifier_WireShape asserts the exact JSON wire format the daemon
// sends over the unix socket, per jcode-protocol/src/wire.rs:188.
//
// We intentionally do NOT dial a real socket. The test substitutes a
// fakeConn that captures bytes and returns a synthetic ack response.
//
// When repoPath is empty (no swarm context), no Subscribe handshake is
// sent — only notify_session. When repoPath is set, Subscribe is sent
// first; see TestNotifier_HandshakeOrder for that flow.
func TestNotifier_WireShape(t *testing.T) {
	resp := []byte(`{"type":"done","id":1}` + "\n")
	conn := &fakeConn{readBuf: strings.NewReader(string(resp))}

	withDial(t, func(ctx context.Context, network, addr string) (net.Conn, error) {
		if network != "unix" {
			t.Fatalf("expected unix network, got %s", network)
		}
		return conn, nil
	})

	n := New("/tmp/fake-jcode.sock", "") // no repo → no handshake
	if err := n.NotifySession(context.Background(), "session_fox_42", "wake up"); err != nil {
		t.Fatalf("NotifySession returned err: %v", err)
	}

	got := conn.written.Bytes()
	// Must end with a single trailing newline.
	if len(got) == 0 || got[len(got)-1] != '\n' {
		t.Fatalf("wire payload must end with newline, got: %q", got)
	}
	payload := strings.TrimRight(string(got), "\n")

	// Must be valid JSON.
	var msg map[string]any
	if err := json.Unmarshal([]byte(payload), &msg); err != nil {
		t.Fatalf("payload is not JSON: %v (payload=%q)", err, payload)
	}

	// Must have exactly these four keys.
	want := map[string]any{
		"type":       "notify_session",
		"id":         float64(1), // JSON numbers decode as float64
		"session_id": "session_fox_42",
		"message":    "wake up",
	}
	for k, v := range want {
		if msg[k] != v {
			t.Errorf("field %q: got %v, want %v", k, msg[k], v)
		}
	}
	if len(msg) != len(want) {
		t.Errorf("expected exactly %d fields, got %d (%#v)", len(want), len(msg), msg)
	}
}

// TestNotifier_HandshakeOrder asserts that when repoPath is set, the
// daemon sends a Subscribe handshake BEFORE the notify_session request
// on the same connection. This is required by jcode's
// client_lifecycle.rs:463-477 (rejects any stateful request before
// Subscribe with "Client must Subscribe with a working_dir before
// sending stateful requests"). See docs/TICK_DAEMON_FAILURE_2026-08-05.md.
func TestNotifier_HandshakeOrder(t *testing.T) {
	const repoPath = "/abs/path/to/repo"
	// Two responses: subscribe ack, then notify_session ack.
	resp := []byte(`{"type":"done","id":1}` + "\n" + `{"type":"done","id":2}` + "\n")
	conn := &fakeConn{readBuf: strings.NewReader(string(resp))}

	withDial(t, func(ctx context.Context, network, addr string) (net.Conn, error) {
		return conn, nil
	})

	n := New("/tmp/fake-jcode.sock", repoPath)
	if err := n.NotifySession(context.Background(), "session_target", "hello"); err != nil {
		t.Fatalf("NotifySession returned err: %v", err)
	}

	written := strings.TrimRight(conn.written.String(), "\n")
	lines := strings.Split(written, "\n")
	if len(lines) != 2 {
		t.Fatalf("expected 2 wire messages (subscribe + notify_session), got %d:\n%s", len(lines), written)
	}

	var sub, notify map[string]any
	if err := json.Unmarshal([]byte(lines[0]), &sub); err != nil {
		t.Fatalf("line 0 is not JSON: %v (line=%q)", err, lines[0])
	}
	if err := json.Unmarshal([]byte(lines[1]), &notify); err != nil {
		t.Fatalf("line 1 is not JSON: %v (line=%q)", err, lines[1])
	}

	// Line 0 must be Subscribe with the configured working_dir.
	if sub["type"] != "subscribe" {
		t.Errorf("line 0 type: got %v, want subscribe", sub["type"])
	}
	if sub["working_dir"] != repoPath {
		t.Errorf("line 0 working_dir: got %v, want %q", sub["working_dir"], repoPath)
	}
	if _, ok := sub["id"]; !ok {
		t.Errorf("line 0 missing id field: %#v", sub)
	}

	// Line 1 must be notify_session.
	if notify["type"] != "notify_session" {
		t.Errorf("line 1 type: got %v, want notify_session", notify["type"])
	}
	if notify["session_id"] != "session_target" {
		t.Errorf("line 1 session_id: got %v, want session_target", notify["session_id"])
	}
	if notify["message"] != "hello" {
		t.Errorf("line 1 message: got %v, want hello", notify["message"])
	}

	// IDs must be distinct (each request allocates a fresh id).
	if id0, id1 := sub["id"], notify["id"]; id0 == id1 {
		t.Errorf("subscribe and notify_session must have distinct ids, both got %v", id0)
	}
}

// TestNotifier_HandshakeErrorPreventsNotify asserts that when the
// Subscribe handshake returns an error from jcode, the daemon does NOT
// send the notify_session request. This prevents jobs from being
// silently "acked" by jcode's client_lifecycle.rs error path while
// the message never reaches the target session.
//
// Repro: in the failure doc, every notify_session was rejected with
// "Client must Subscribe..." but the daemon continued anyway, making
// the failure mode invisible. With the handshake, the rejection
// surfaces immediately.
func TestNotifier_HandshakeErrorPreventsNotify(t *testing.T) {
	// Only one response (the subscribe error). If the daemon sent
	// notify_session anyway, the second read would see EOF.
	resp := []byte(`{"type":"error","id":1,"message":"Subscribe working_dir must be an absolute path"}` + "\n")
	conn := &fakeConn{readBuf: strings.NewReader(string(resp))}

	withDial(t, func(ctx context.Context, network, addr string) (net.Conn, error) {
		return conn, nil
	})

	n := New("/tmp/fake-jcode.sock", "relative/path") // not absolute → jcode rejects
	err := n.NotifySession(context.Background(), "session_target", "hello")
	if err == nil {
		t.Fatal("expected error from subscribe rejection, got nil")
	}
	if !strings.Contains(err.Error(), "subscribe handshake") {
		t.Errorf("error should mention subscribe handshake, got: %v", err)
	}
	if !strings.Contains(err.Error(), "absolute path") {
		t.Errorf("error should surface server message, got: %v", err)
	}

	// Verify only one wire message was sent (no notify_session).
	written := strings.TrimRight(conn.written.String(), "\n")
	lines := strings.Split(written, "\n")
	if len(lines) != 1 {
		t.Fatalf("expected only subscribe message after rejection, got %d:\n%s", len(lines), written)
	}
	var sub map[string]any
	if err := json.Unmarshal([]byte(lines[0]), &sub); err != nil {
		t.Fatalf("line 0 is not JSON: %v", err)
	}
	if sub["type"] != "subscribe" {
		t.Errorf("line 0 type: got %v, want subscribe", sub["type"])
	}
}

// TestNotifier_ServerErrorReturnsError asserts that a `{"type":"error"}`
// response surfaces as an error to the caller (so the daemon can decide
// to fallback to coordinator). With repoPath empty, no handshake is
// sent — only one error response is needed.
func TestNotifier_ServerErrorReturnsError(t *testing.T) {
	resp := []byte(`{"type":"error","id":1,"message":"session not found"}` + "\n")
	conn := &fakeConn{readBuf: strings.NewReader(string(resp))}

	withDial(t, func(ctx context.Context, network, addr string) (net.Conn, error) {
		return conn, nil
	})

	n := New("/tmp/fake-jcode.sock", "") // no fallback
	err := n.NotifySession(context.Background(), "session_ghost", "wake up")
	if err == nil {
		t.Fatal("expected error from server-error response, got nil")
	}
	if !strings.Contains(err.Error(), "session not found") {
		t.Errorf("error should contain server message, got: %v", err)
	}
}

// TestNotifier_DialFailureReturnsError asserts that a refused connection
// surfaces as an error (and does not panic, hang, or fallback when
// repoPath is empty).
func TestNotifier_DialFailureReturnsError(t *testing.T) {
	withDial(t, func(ctx context.Context, network, addr string) (net.Conn, error) {
		return nil, io.EOF
	})

	n := New("/tmp/fake-jcode.sock", "")
	err := n.NotifySession(context.Background(), "session_x", "hi")
	if err == nil {
		t.Fatal("expected error when dial fails, got nil")
	}
}

// TestNotifier_DetectsSelfWake asserts that NotifySession short-circuits
// with ErrSelfWake when the wake target matches the swarm coordinator's
// session id. The dial must NOT be invoked — this is the entire point of
// the check: refuse the job upfront so the daemon never sends a request
// that the jcode runtime will silently swallow.
//
// See docs/TICK_SELF_WAKE_GAP.md for the empirical reproduction.
func TestNotifier_DetectsSelfWake(t *testing.T) {
	const target = "session_fox_42"

	withCoordLookup(t, func(repoPath string) (string, error) {
		return target, nil // coordinator IS the target → self-wake
	})

	var dialCount int
	withDial(t, func(ctx context.Context, network, addr string) (net.Conn, error) {
		dialCount++
		t.Fatalf("dial must NOT be invoked on self-wake (call #%d)", dialCount)
		return nil, errors.New("unreachable: dial was called")
	})

	n := New("/tmp/fake-jcode.sock", "any-repo")
	err := n.NotifySession(context.Background(), target, "wake up")
	if !errors.Is(err, ErrSelfWake) {
		t.Fatalf("expected ErrSelfWake, got: %v", err)
	}
	if dialCount != 0 {
		t.Errorf("dial must not be invoked on self-wake, was called %d times", dialCount)
	}
}

// TestNotifier_SelfWake_BypassesFallback asserts that the typed sentinel
// ErrSelfWake is returned even if the dial would have succeeded. The
// fallback retry path that runs after a primary failure must NOT mask
// the self-wake error — the daemon needs to see ErrSelfWake specifically
// so it can keep the job in store as a post-mortem record.
func TestNotifier_SelfWake_BypassesFallback(t *testing.T) {
	const target = "session_fox_42"

	withCoordLookup(t, func(repoPath string) (string, error) {
		return target, nil
	})

	// Even if dial succeeds (jcode would ack the self-wake), we must
	// refuse upfront. The dial mock returning success is the dangerous
	// case the daemon fix is meant to intercept.
	withDial(t, func(ctx context.Context, network, addr string) (net.Conn, error) {
		return &fakeConn{readBuf: strings.NewReader(`{"type":"done","id":1}` + "\n")}, nil
	})

	n := New("/tmp/fake-jcode.sock", "any-repo")
	err := n.NotifySession(context.Background(), target, "wake up")
	if err == nil {
		t.Fatal("expected ErrSelfWake, got nil")
	}
	if !errors.Is(err, ErrSelfWake) {
		t.Fatalf("expected ErrSelfWake sentinel, got: %v", err)
	}
}

// TestNotifier_NoSelfWake_WhenCoordinatorDifferent asserts that the
// self-wake check does NOT fire when the coordinator is a different
// session than the wake target. This is the normal path — most wake
// jobs target non-coordinator sessions.
//
// With repoPath set, the daemon sends Subscribe + notify_session, so
// the fake must provide two responses.
func TestNotifier_NoSelfWake_WhenCoordinatorDifferent(t *testing.T) {
	const target = "session_fox_42"
	const coord = "session_other"

	withCoordLookup(t, func(repoPath string) (string, error) {
		return coord, nil
	})

	resp := []byte(`{"type":"done","id":1}` + "\n" + `{"type":"done","id":2}` + "\n")
	conn := &fakeConn{readBuf: strings.NewReader(string(resp))}
	withDial(t, func(ctx context.Context, network, addr string) (net.Conn, error) {
		return conn, nil
	})

	n := New("/tmp/fake-jcode.sock", "any-repo")
	if err := n.NotifySession(context.Background(), target, "wake up"); err != nil {
		t.Fatalf("expected nil error when coordinator differs, got: %v", err)
	}

	// Wire payload must still be sent (existing behavior preserved).
	if conn.written.Len() == 0 {
		t.Fatal("expected wire payload to be written, got empty buffer")
	}
}

// TestNotifier_CoordinatorLookupError_DoesNotFalsePositive asserts that
// when coordinator.Lookup fails (no swarm JSON, read error, etc.), the
// self-wake check is skipped and normal flow proceeds. The daemon must
// never refuse a wake job just because it couldn't read its own state
// file — that would be a self-inflicted outage on every machine that
// runs the daemon outside an active swarm.
//
// With repoPath set, the fake must provide two responses (subscribe
// ack + notify_session ack).
func TestNotifier_CoordinatorLookupError_DoesNotFalsePositive(t *testing.T) {
	withCoordLookup(t, func(repoPath string) (string, error) {
		return "", errors.New("no swarm state")
	})

	resp := []byte(`{"type":"done","id":1}` + "\n" + `{"type":"done","id":2}` + "\n")
	conn := &fakeConn{readBuf: strings.NewReader(string(resp))}
	withDial(t, func(ctx context.Context, network, addr string) (net.Conn, error) {
		return conn, nil
	})

	n := New("/tmp/fake-jcode.sock", "any-repo")
	err := n.NotifySession(context.Background(), "session_fox_42", "wake up")
	if err != nil {
		t.Fatalf("expected nil error when coordinator lookup fails (fail-safe), got: %v", err)
	}
}
