// Package job defines the core data type managed by the tick daemon.
//
// A Job is a delayed-wakeup intent: at FireAtMs (absolute unix-ms),
// the daemon sends the Message to the live session WakeSessionID via
// NotifySession over the jcode unix socket. If WakeSessionID is dead
// at fire time, the daemon falls back to the swarm coordinator.
package job

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"time"
)

// Job is the persistent record for one scheduled wake.
//
// Stable JSON wire shape — embedded in jobs.jsonl and in MCP tool
// responses. Do not rename fields without a migration story.
type Job struct {
	ID            string `json:"id"`
	FireAtMs      int64  `json:"fire_at_ms"`      // absolute unix-ms
	WakeSessionID string `json:"wake_session_id"`
	Message       string `json:"message"`
	CreatedAtMs   int64  `json:"created_at_ms"`
}

// New constructs a Job with a human-readable, sortable, unique ID.
// ID format: "<unix_ms>-<random 6 hex chars>" — e.g. "1754380123456-a3f9c1".
//
// fireAt is interpreted as a wall-clock instant; we store its unix-ms.
// msg may be empty (the daemon will still send an empty notification
// to the session, which jcode routes like any other message).
func New(wakeSessionID, msg string, fireAt time.Time) Job {
	now := time.Now()
	return Job{
		ID:            newID(now),
		FireAtMs:      fireAt.UnixMilli(),
		WakeSessionID: wakeSessionID,
		Message:       msg,
		CreatedAtMs:   now.UnixMilli(),
	}
}

// NewWithOffset is a convenience for CLI submit: "now + duration".
func NewWithOffset(wakeSessionID, msg string, offset time.Duration) Job {
	return New(wakeSessionID, msg, time.Now().Add(offset))
}

// newID builds "<unix_ms>-<rand6>" where rand6 is 6 lowercase hex chars
// (3 bytes encoded). Cryptographically random; collision probability
// negligible for the per-user daemon scale.
func newID(now time.Time) string {
	var b [3]byte
	if _, err := rand.Read(b[:]); err != nil {
		// crypto/rand never fails on linux; if it does, fall back to
		// a deterministic suffix so the daemon still functions.
		b = [3]byte{0xde, 0xad, 0xbe}
	}
	return fmt.Sprintf("%d-%s", now.UnixMilli(), hex.EncodeToString(b[:]))
}