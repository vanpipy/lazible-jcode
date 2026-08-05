// Package store persists jobs across daemon restarts.
//
// Format: append-only JSONL at <runtime_dir>/state/tick/jobs.jsonl.
//
// Reads tolerate malformed lines (logged and skipped) so a half-written
// line from a crashed daemon does not brick startup.
package store

import (
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sync"

	"github.com/1jehuang/lazible-jcode/tick/internal/job"
)

// Store is a JSONL-backed append-only log.
type Store struct {
	mu   sync.Mutex
	path string
}

// New opens (and lazily creates) the jobs.jsonl at the given path.
// Parent directories are created with 0700 perms; the file itself with 0600.
func New(path string) (*Store, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return nil, fmt.Errorf("store: mkdir parent: %w", err)
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_RDWR|os.O_APPEND, 0o600)
	if err != nil {
		return nil, fmt.Errorf("store: open %s: %w", path, err)
	}
	f.Close()
	return &Store{path: path}, nil
}

// DefaultPath returns <runtime_dir>/state/tick/jobs.jsonl.
//
// runtime_dir precedence: $JCODE_TICK_STATE_DIR > $XDG_STATE_HOME/jcode/tick
// > $HOME/.local/state/jcode/tick. We deliberately do NOT use the
// runtime_dir that jcode itself uses (which is on $XDG_RUNTIME_DIR — a
// tmpfs) so jobs survive reboots.
func DefaultPath() string {
	if d := os.Getenv("JCODE_TICK_STATE_DIR"); d != "" {
		return filepath.Join(d, "jobs.jsonl")
	}
	if d := os.Getenv("XDG_STATE_HOME"); d != "" {
		return filepath.Join(d, "jcode", "tick", "jobs.jsonl")
	}
	if h, err := os.UserHomeDir(); err == nil {
		return filepath.Join(h, ".local", "state", "jcode", "tick", "jobs.jsonl")
	}
	return "jobs.jsonl"
}

// Append writes j as a single JSON line.
func (s *Store) Append(j job.Job) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	b, err := json.Marshal(j)
	if err != nil {
		return fmt.Errorf("store: marshal: %w", err)
	}
	f, err := os.OpenFile(s.path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		return fmt.Errorf("store: open for append: %w", err)
	}
	defer f.Close()
	w := bufio.NewWriter(f)
	if _, err := w.Write(b); err != nil {
		return fmt.Errorf("store: write: %w", err)
	}
	if err := w.WriteByte('\n'); err != nil {
		return fmt.Errorf("store: write newline: %w", err)
	}
	if err := w.Flush(); err != nil {
		return fmt.Errorf("store: flush: %w", err)
	}
	return nil
}

// LoadAll reads every line, returning valid Jobs. Malformed lines are
// silently skipped (logged by the caller if it wants visibility).
func (s *Store) LoadAll() ([]job.Job, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	f, err := os.Open(s.path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil, nil
		}
		return nil, fmt.Errorf("store: open: %w", err)
	}
	defer f.Close()
	var out []job.Job
	r := bufio.NewReader(f)
	for {
		line, err := r.ReadBytes('\n')
		if len(line) > 0 {
			var j job.Job
			if jerr := json.Unmarshal(bytesTrimNewline(line), &j); jerr == nil {
				out = append(out, j)
			}
			// else: malformed; skip silently
		}
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return out, fmt.Errorf("store: read: %w", err)
		}
	}
	return out, nil
}

// Remove rewrites the file without the job whose ID equals id.
//
// Atomic: write to jobs.jsonl.tmp, fsync, rename.
func (s *Store) Remove(id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	all, err := s.loadUnlocked()
	if err != nil {
		return err
	}
	var keep []job.Job
	for _, j := range all {
		if j.ID != id {
			keep = append(keep, j)
		}
	}
	if len(keep) == len(all) {
		// Nothing removed; not an error.
		return nil
	}
	tmp := s.path + ".tmp"
	f, err := os.OpenFile(tmp, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o600)
	if err != nil {
		return fmt.Errorf("store: open tmp: %w", err)
	}
	w := bufio.NewWriter(f)
	for _, j := range keep {
		b, err := json.Marshal(j)
		if err != nil {
			f.Close()
			os.Remove(tmp)
			return fmt.Errorf("store: marshal: %w", err)
		}
		if _, err := w.Write(b); err != nil {
			f.Close()
			os.Remove(tmp)
			return fmt.Errorf("store: write tmp: %w", err)
		}
		if err := w.WriteByte('\n'); err != nil {
			f.Close()
			os.Remove(tmp)
			return fmt.Errorf("store: write newline tmp: %w", err)
		}
	}
	if err := w.Flush(); err != nil {
		f.Close()
		os.Remove(tmp)
		return fmt.Errorf("store: flush tmp: %w", err)
	}
	if err := f.Sync(); err != nil {
		f.Close()
		os.Remove(tmp)
		return fmt.Errorf("store: fsync tmp: %w", err)
	}
	if err := f.Close(); err != nil {
		os.Remove(tmp)
		return fmt.Errorf("store: close tmp: %w", err)
	}
	if err := os.Rename(tmp, s.path); err != nil {
		return fmt.Errorf("store: rename tmp: %w", err)
	}
	return nil
}

// loadUnlocked reads the file without acquiring the lock. Caller must hold s.mu.
func (s *Store) loadUnlocked() ([]job.Job, error) {
	f, err := os.Open(s.path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil, nil
		}
		return nil, fmt.Errorf("store: open: %w", err)
	}
	defer f.Close()
	var out []job.Job
	r := bufio.NewReader(f)
	for {
		line, err := r.ReadBytes('\n')
		if len(line) > 0 {
			var j job.Job
			if jerr := json.Unmarshal(bytesTrimNewline(line), &j); jerr == nil {
				out = append(out, j)
			}
		}
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return out, fmt.Errorf("store: read: %w", err)
		}
	}
	return out, nil
}

// bytesTrimNewline returns b with trailing \n removed (one or more).
func bytesTrimNewline(b []byte) []byte {
	for len(b) > 0 && b[len(b)-1] == '\n' {
		b = b[:len(b)-1]
	}
	return b
}