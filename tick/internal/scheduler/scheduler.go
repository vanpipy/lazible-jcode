// Package scheduler manages a min-heap of timed wake-up jobs and fires
// each job at its FireAtMs via a caller-supplied NotifyFunc.
//
// The scheduler is purely mechanical: it does not evaluate state, does
// not subscribe to jcode's SwarmStatus stream, and does not implement
// fire_if conditions. All "smart" decisions live in the agent; the
// daemon is a 100ms-resolution timer.
package scheduler

import (
	"container/heap"
	"context"
	"sync"
	"time"

	"github.com/1jehuang/lazible-jcode/tick/internal/job"
)

// NotifyFunc is invoked for each job whose FireAtMs has been reached.
//
// The scheduler does not interpret the returned error; an error from
// NotifyFunc does not stop later jobs from firing. Errors should be
// surfaced via the daemon's stderr / logs.
type NotifyFunc func(j job.Job) error

// item is the heap entry — pointer so that heap mutations update the
// underlying slice in place.
type item struct {
	job job.Job
	idx int // heap-managed index; -1 when not in heap
}

// minHeap implements heap.Interface over []*item by FireAtMs ascending.
type minHeap []*item

func (h minHeap) Len() int           { return len(h) }
func (h minHeap) Less(i, j int) bool { return h[i].job.FireAtMs < h[j].job.FireAtMs }
func (h minHeap) Swap(i, j int) {
	h[i], h[j] = h[j], h[i]
	h[i].idx = i
	h[j].idx = j
}
func (h *minHeap) Push(x any) {
	it := x.(*item)
	it.idx = len(*h)
	*h = append(*h, it)
}
func (h *minHeap) Pop() any {
	old := *h
	n := len(old)
	it := old[n-1]
	it.idx = -1
	*h = old[:n-1]
	return it
}

// Scheduler is the central state of the tick daemon.
//
// Concurrency: Submit / Cancel / List / Tick may be called from any
// goroutine; Run is the loop that calls Tick on a timer. The mutex
// protects all heap mutations and the lookup map.
type Scheduler struct {
	mu     sync.Mutex
	heap   *minHeap
	byID   map[string]*item
	notify NotifyFunc
}

// New constructs a Scheduler bound to a NotifyFunc. The NotifyFunc must
// be safe for concurrent calls if Run is active.
func New(notify NotifyFunc) *Scheduler {
	h := &minHeap{}
	heap.Init(h)
	return &Scheduler{
		heap:   h,
		byID:   make(map[string]*item),
		notify: notify,
	}
}

// Submit inserts j. The ID is taken from j.ID; if empty, the caller is
// responsible for setting one (job.New always does).
//
// Returns an error if a job with the same ID already exists.
func (s *Scheduler) Submit(j job.Job) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.byID[j.ID]; exists {
		return errDuplicate
	}
	it := &item{job: j}
	heap.Push(s.heap, it)
	s.byID[j.ID] = it
	return nil
}

// Cancel removes the job with the given id. Returns true if a job was
// removed, false if no such job exists.
func (s *Scheduler) Cancel(id string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	it, ok := s.byID[id]
	if !ok {
		return false
	}
	heap.Remove(s.heap, it.idx)
	delete(s.byID, id)
	return true
}

// List returns a snapshot of all pending jobs. Order is unspecified.
func (s *Scheduler) List() []job.Job {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]job.Job, 0, len(s.byID))
	for _, it := range s.byID {
		out = append(out, it.job)
	}
	return out
}

// Tick drains all jobs whose FireAtMs <= nowMs and fires each via the
// configured NotifyFunc. Returns the jobs that were fired (in fire
// order, i.e. sorted by FireAtMs).
//
// Tests drive the scheduler by hand via Tick(now); Run is the
// production ticker that calls Tick once per wake.
//
// NotifyFunc errors are intentionally ignored here — the scheduler
// must keep firing later jobs even if a NotifyFunc returns an error
// (e.g. socket briefly unavailable). The daemon's notify closure
// logs to stderr.
func (s *Scheduler) Tick(nowMs int64) []job.Job {
	s.mu.Lock()
	var fired []job.Job
	for s.heap.Len() > 0 {
		peek := (*s.heap)[0]
		if peek.job.FireAtMs > nowMs {
			break
		}
		popped := heap.Pop(s.heap).(*item)
		delete(s.byID, popped.job.ID)
		fired = append(fired, popped.job)
	}
	notify := s.notify
	s.mu.Unlock()

	// Call notify OUTSIDE the lock so a slow / hanging notify does not
	// block other scheduler operations.
	for _, j := range fired {
		_ = notify(j)
	}
	return fired
}

// Run drives the scheduler in a 100ms loop until ctx is cancelled.
//
// On each wake:
//   - call Tick(now)
//   - Tick invokes NotifyFunc for each due job (see Tick doc)
//
// Stopping: ctx cancel exits the loop after the current iteration.
func (s *Scheduler) Run(ctx context.Context) {
	const interval = 100 * time.Millisecond
	t := time.NewTicker(interval)
	defer t.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case now := <-t.C:
			s.Tick(now.UnixMilli())
		}
	}
}

// errDuplicate is returned by Submit when the ID already exists.
var errDuplicate = sentinel("duplicate job id")

type sentinel string

func (e sentinel) Error() string { return string(e) }