package scheduler

import (
	"testing"
	"time"

	"github.com/1jehuang/lazible-jcode/tick/internal/job"
)

// fakeNotify records each call and returns a configured error per id.
// Used to drive the scheduler without touching real sockets.
type fakeNotify struct {
	calls   []calledJob
	errByID map[string]error
}

type calledJob struct {
	WakeSessionID string
	Message       string
	ID            string
}

func (f *fakeNotify) notify(j job.Job) error {
	f.calls = append(f.calls, calledJob{
		WakeSessionID: j.WakeSessionID,
		Message:       j.Message,
		ID:            j.ID,
	})
	if f.errByID == nil {
		return nil
	}
	return f.errByID[j.ID]
}

func newSched(n func(j job.Job) error) *Scheduler {
	return New(n)
}

// 1. Three jobs at +100/+200/+300 fire in order with the right args.
func TestScheduler_FiresJobsInOrder(t *testing.T) {
	notif := &fakeNotify{}
	s := newSched(notif.notify)

	base := time.Now()
	s.Submit(job.New("sess_A", "alpha", base.Add(100*time.Millisecond)))
	s.Submit(job.New("sess_B", "beta", base.Add(300*time.Millisecond))) // intentionally inserted later
	s.Submit(job.New("sess_C", "gamma", base.Add(200*time.Millisecond)))

	// Drive by hand at three timestamps.
	firedT1 := s.Tick(base.Add(150 * time.Millisecond).UnixMilli())
	if len(firedT1) != 1 || firedT1[0].WakeSessionID != "sess_A" {
		t.Fatalf("t=150ms expected sess_A, got %#v", firedT1)
	}
	firedT2 := s.Tick(base.Add(250 * time.Millisecond).UnixMilli())
	if len(firedT2) != 1 || firedT2[0].WakeSessionID != "sess_C" {
		t.Fatalf("t=250ms expected sess_C, got %#v", firedT2)
	}
	firedT3 := s.Tick(base.Add(350 * time.Millisecond).UnixMilli())
	if len(firedT3) != 1 || firedT3[0].WakeSessionID != "sess_B" {
		t.Fatalf("t=350ms expected sess_B, got %#v", firedT3)
	}

	if got := notif.calls; len(got) != 3 {
		t.Fatalf("expected 3 notify calls, got %d (%#v)", len(got), got)
	}
	want := []string{"sess_A", "sess_C", "sess_B"}
	for i, c := range notif.calls {
		if c.WakeSessionID != want[i] {
			t.Errorf("call[%d] wake=%s want=%s", i, c.WakeSessionID, want[i])
		}
	}
}

// 2. Cancel before fire: job never reaches NotifyFunc.
func TestScheduler_CancelMidFlight(t *testing.T) {
	notif := &fakeNotify{}
	s := newSched(notif.notify)

	base := time.Now()
	jA := job.New("sess_A", "alpha", base.Add(100*time.Millisecond))
	jB := job.New("sess_B", "beta", base.Add(200*time.Millisecond))

	s.Submit(jA)
	s.Submit(jB)

	all := s.List()
	if len(all) != 2 {
		t.Fatalf("list expected 2, got %d", len(all))
	}

	// Cancel sess_B explicitly (not "all[0]", whose ordering is
	// unspecified by List).
	var cancelledID string
	for _, j := range all {
		if j.WakeSessionID == "sess_B" {
			cancelledID = j.ID
			break
		}
	}
	if !s.Cancel(cancelledID) {
		t.Fatal("cancel returned false for known id")
	}
	if s.Cancel(cancelledID) {
		t.Fatal("cancel returned true for already-cancelled id")
	}

	// At t=150ms: sess_A fires (we did not cancel it). sess_B was
	// cancelled before fire time, so it must NOT fire.
	fired := s.Tick(base.Add(150 * time.Millisecond).UnixMilli())
	if len(fired) != 1 || fired[0].WakeSessionID != "sess_A" {
		t.Fatalf("expected only sess_A to fire at 150ms; got %#v", fired)
	}
	if len(notif.calls) != 1 || notif.calls[0].WakeSessionID != "sess_A" {
		t.Fatalf("expected one notify call to sess_A; got %#v", notif.calls)
	}

	// At t=300ms: nothing left to fire; sess_B never existed past Cancel.
	fired = s.Tick(base.Add(300 * time.Millisecond).UnixMilli())
	if len(fired) != 0 {
		t.Fatalf("expected 0 fires at 300ms after Cancel; got %#v", fired)
	}
}

// 3. NotifyFunc returning an error for one job does NOT stop later jobs.
func TestScheduler_NotifyErrorDoesNotStopLaterJobs(t *testing.T) {
	notif := &fakeNotify{
		errByID: map[string]error{},
	}
	s := newSched(notif.notify)

	base := time.Now()
	j1 := job.New("sess_A", "alpha", base.Add(100*time.Millisecond))
	j2 := job.New("sess_B", "beta", base.Add(200*time.Millisecond))
	j3 := job.New("sess_C", "gamma", base.Add(300*time.Millisecond))

	s.Submit(j1)
	s.Submit(j2)
	s.Submit(j3)

	notif.errByID[j2.ID] = errNotifyFailed

	// Drain at the final timestamp — all three should be fired despite j2's error.
	fired := s.Tick(base.Add(400 * time.Millisecond).UnixMilli())
	if len(fired) != 3 {
		t.Fatalf("expected 3 fired jobs, got %d", len(fired))
	}
	if got := []string{notif.calls[0].WakeSessionID, notif.calls[1].WakeSessionID, notif.calls[2].WakeSessionID}; got[0] != "sess_A" || got[1] != "sess_B" || got[2] != "sess_C" {
		t.Errorf("fire order wrong: %#v", got)
	}
}

// 4. Tick at a time before any FireAtMs returns nothing.
func TestScheduler_TickBeforeAnyFireReturnsEmpty(t *testing.T) {
	notif := &fakeNotify{}
	s := newSched(notif.notify)
	base := time.Now()
	s.Submit(job.New("sess_A", "alpha", base.Add(10*time.Second)))

	fired := s.Tick(base.UnixMilli())
	if len(fired) != 0 {
		t.Fatalf("expected 0, got %d", len(fired))
	}
	if len(notif.calls) != 0 {
		t.Fatalf("notify should not be called yet; got %d", len(notif.calls))
	}
}

// 5. List returns all jobs regardless of fire time.
func TestScheduler_ListReturnsAll(t *testing.T) {
	notif := &fakeNotify{}
	s := newSched(notif.notify)
	base := time.Now()
	s.Submit(job.New("sess_A", "alpha", base.Add(100*time.Millisecond)))
	s.Submit(job.New("sess_B", "beta", base.Add(50*time.Millisecond)))

	all := s.List()
	if len(all) != 2 {
		t.Fatalf("list expected 2, got %d", len(all))
	}
	// Both jobs present; order is not guaranteed by List but both IDs should be there.
	seen := map[string]bool{}
	for _, j := range all {
		seen[j.WakeSessionID] = true
	}
	if !seen["sess_A"] || !seen["sess_B"] {
		t.Fatalf("list missing one of the jobs: %#v", all)
	}
}

// errNotifyFailed is the sentinel we expect from notif.notify when errByID has an entry.
var errNotifyFailed = sentinelErr("notify failed")

type sentinelErr string

func (e sentinelErr) Error() string { return string(e) }