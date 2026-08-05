package mcp

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/1jehuang/lazible-jcode/tick/internal/job"
	"github.com/1jehuang/lazible-jcode/tick/internal/scheduler"
	"github.com/1jehuang/lazible-jcode/tick/internal/store"
)

// fakeNotify records every fired job and returns nil (success). Tests
// can inspect .fired to verify the scheduler actually invoked notify.
//
// We model the runMCP callback shape here: on notify success, the
// production callback in tick/main.go:101-109 calls st.Remove. In
// tests, that remove is done explicitly by the test driver — this
// keeps the fake aligned with the contract and lets each test decide
// whether the store entry should survive.
type fakeNotify struct {
	mu    sync.Mutex
	fired []job.Job
}

func (f *fakeNotify) notify(j job.Job) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.fired = append(f.fired, j)
	return nil
}

// newTestServer builds a Server backed by a real scheduler + a real
// store (writing to a per-test temp file). Reader / writer are unused
// because the tests drive s.handle directly.
func newTestServer(t *testing.T) (*Server, *fakeNotify, string) {
	t.Helper()
	dir := t.TempDir()
	storePath := filepath.Join(dir, "jobs.jsonl")
	st, err := store.New(storePath)
	if err != nil {
		t.Fatalf("store.New: %v", err)
	}

	notif := &fakeNotify{}
	sched := scheduler.New(notif.notify)
	srv := New(sched, st, os.Stdin, os.Stdout)
	t.Cleanup(func() {
		// store uses lazy file open; nothing to close explicitly.
	})
	return srv, notif, storePath
}

// callListJobs synthesizes a JSON-RPC tools/call for list_jobs and
// returns the parsed listEntry slice.
func callListJobs(t *testing.T, s *Server) []listEntry {
	t.Helper()
	reqJSON := []byte(`{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_jobs","arguments":{}}}`)
	var req request
	if err := json.Unmarshal(reqJSON, &req); err != nil {
		t.Fatalf("unmarshal request: %v", err)
	}
	resp := s.handle(context.Background(), &req)
	if resp == nil {
		t.Fatalf("handle returned nil response")
	}
	if resp.Error != nil {
		t.Fatalf("list_jobs RPC error: code=%d msg=%s", resp.Error.Code, resp.Error.Message)
	}
	res, ok := resp.Result.(toolResult)
	if !ok {
		t.Fatalf("unexpected result type %T", resp.Result)
	}
	if res.IsError {
		t.Fatalf("list_jobs returned isError=true; content=%#v", res.Content)
	}
	if len(res.Content) != 1 {
		t.Fatalf("expected 1 content block, got %d", len(res.Content))
	}
	text := res.Content[0].Text
	var entries []listEntry
	if err := json.Unmarshal([]byte(text), &entries); err != nil {
		t.Fatalf("unmarshal content text: %v (text=%q)", err, text)
	}
	return entries
}

// 1. Core regression — list_jobs reads the store, not the scheduler.
//
// A job that exists ONLY in the store (never submitted to the
// scheduler) must still appear in list_jobs. Before the fix,
// toolListJobs called s.sched.List() which returns [].
func TestListJobs_ReadsFromStore_NotScheduler(t *testing.T) {
	srv, _, _ := newTestServer(t)

	j := job.New("sess_store_only", "alpha", time.Now().Add(5*time.Second))
	if err := srv.store.Append(j); err != nil {
		t.Fatalf("store.Append: %v", err)
	}

	entries := callListJobs(t, srv)
	if len(entries) != 1 {
		t.Fatalf("expected 1 entry from store-only job, got %d (%#v)", len(entries), entries)
	}
	if entries[0].JobID != j.ID {
		t.Errorf("job_id mismatch: got %q want %q", entries[0].JobID, j.ID)
	}
	if entries[0].WakeSessionID != "sess_store_only" {
		t.Errorf("wake_session_id mismatch: got %q", entries[0].WakeSessionID)
	}
	if entries[0].FireAtMs != j.FireAtMs {
		t.Errorf("fire_at_ms mismatch: got %d want %d", entries[0].FireAtMs, j.FireAtMs)
	}
	if entries[0].MessagePreview != "alpha" {
		t.Errorf("message_preview mismatch: got %q", entries[0].MessagePreview)
	}
}

// 2. The refused self-wake scenario.
//
// A job is in BOTH the scheduler and the store. The scheduler Tick
// drains it (notify returns nil) but the production runMCP callback
// only calls st.Remove on success — and we simulate the post-fire
// state where the store was NOT touched. The job must remain visible
// in list_jobs because the store is the durable source of truth.
//
// Before the fix, toolListJobs called s.sched.List() which was empty
// after Tick removed the job from byID (scheduler.go:142).
func TestListJobs_ShowsRefusedSelfWake(t *testing.T) {
	srv, notif, _ := newTestServer(t)

	base := time.Now()
	j := job.New("sess_self_wake", "tick self-wake test", base.Add(100*time.Millisecond))
	if err := srv.sched.Submit(j); err != nil {
		t.Fatalf("sched.Submit: %v", err)
	}
	if err := srv.store.Append(j); err != nil {
		t.Fatalf("store.Append: %v", err)
	}

	// Drain the scheduler at the fire timestamp. notify returns nil but
	// the store is intentionally NOT touched — mirroring the refused
	// self-wake case where runMCP sees an error and skips st.Remove.
	fired := srv.sched.Tick(base.Add(200 * time.Millisecond).UnixMilli())
	if len(fired) != 1 || fired[0].ID != j.ID {
		t.Fatalf("expected 1 fired job, got %#v", fired)
	}
	if len(notif.fired) != 1 {
		t.Fatalf("expected 1 notify call, got %d", len(notif.fired))
	}
	if got := srv.sched.List(); len(got) != 0 {
		t.Fatalf("scheduler should be empty post-Tick, got %d", len(got))
	}

	// The store retains the refused self-wake. list_jobs must show it.
	entries := callListJobs(t, srv)
	if len(entries) != 1 {
		t.Fatalf("expected 1 entry from refused self-wake, got %d (%#v)", len(entries), entries)
	}
	if entries[0].JobID != j.ID {
		t.Errorf("job_id mismatch: got %q want %q", entries[0].JobID, j.ID)
	}
}

// 3. After a SUCCESSFUL fire the job is gone everywhere — including
// from list_jobs. The scheduler Tick drains the heap and the runMCP
// callback removes from the store. list_jobs must return [].
//
// This test guards against a "fix" that over-corrects and keeps jobs
// visible after successful fire (e.g. reading store but ignoring the
// scheduler's fired-and-removed signal).
func TestListJobs_EmptyAfterSuccessfulFire(t *testing.T) {
	srv, notif, _ := newTestServer(t)

	base := time.Now()
	j := job.New("sess_ok", "ok fire", base.Add(100*time.Millisecond))
	if err := srv.sched.Submit(j); err != nil {
		t.Fatalf("sched.Submit: %v", err)
	}
	if err := srv.store.Append(j); err != nil {
		t.Fatalf("store.Append: %v", err)
	}

	// Successful fire: Tick drains the scheduler, notify returns nil,
	// and we manually invoke st.Remove to mirror the production
	// runMCP success path (tick/main.go:101-109).
	fired := srv.sched.Tick(base.Add(200 * time.Millisecond).UnixMilli())
	if len(fired) != 1 || fired[0].ID != j.ID {
		t.Fatalf("expected 1 fired job, got %#v", fired)
	}
	if len(notif.fired) != 1 {
		t.Fatalf("expected 1 notify call, got %d", len(notif.fired))
	}
	if err := srv.store.Remove(j.ID); err != nil {
		t.Fatalf("store.Remove: %v", err)
	}

	entries := callListJobs(t, srv)
	if len(entries) != 0 {
		t.Fatalf("expected empty list after successful fire+remove, got %d (%#v)", len(entries), entries)
	}
}