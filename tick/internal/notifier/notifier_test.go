package notifier

import (
	"bytes"
	"context"
	"encoding/json"
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

// TestNotifier_WireShape asserts the exact JSON wire format the daemon
// sends over the unix socket, per jcode-protocol/src/wire.rs:188.
//
// We intentionally do NOT dial a real socket. The test substitutes a
// fakeConn that captures bytes and returns a synthetic ack response.
func TestNotifier_WireShape(t *testing.T) {
	resp := []byte(`{"type":"done","id":1}` + "\n")
	conn := &fakeConn{readBuf: strings.NewReader(string(resp))}

	withDial(t, func(ctx context.Context, network, addr string) (net.Conn, error) {
		if network != "unix" {
			t.Fatalf("expected unix network, got %s", network)
		}
		return conn, nil
	})

	n := New("/tmp/fake-jcode.sock", "") // no repo → no fallback
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

// TestNotifier_ServerErrorReturnsError asserts that a `{"type":"error"}`
// response surfaces as an error to the caller (so the daemon can decide
// to fallback to coordinator).
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