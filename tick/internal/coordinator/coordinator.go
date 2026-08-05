// Package coordinator looks up the swarm coordinator session id for a
// given repo path, used as the fallback target when a wake job's
// WakeSessionID is dead at fire time.
//
// State file shape (per ~/.jcode/state/swarm/*.json):
//
//	{
//	  "swarm_id": "/abs/path/to/repo/.git",
//	  "coordinator_session_id": "session_xxx",
//	  "members": [...],
//	  ...
//	}
//
// The filename encodes the repo path with `/` replaced by `_`, plus a
// `__git` suffix. See ~/.jcode/state/swarm/_home_leroy_Project_jcode__git.json
// for a live example.
package coordinator

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// SwarmState is the subset of the swarm JSON we care about.
type SwarmState struct {
	SwarmID              string `json:"swarm_id"`
	CoordinatorSessionID string `json:"coordinator_session_id"`
}

// Lookup returns the coordinator_session_id for the given repo path
// (typically `git rev-parse --show-toplevel`).
//
// Caches per-repo for 30s to avoid rereading the JSON on every job fire.
func Lookup(repoPath string) (string, error) {
	return getCached(repoPath)
}

// ErrNotFound is returned when no swarm JSON exists for the repo.
var ErrNotFound = errors.New("coordinator: no swarm state file for repo")

// --- internal ---

var (
	cacheMu sync.Mutex
	cache   = map[string]cacheEntry{}
)

type cacheEntry struct {
	coordinatorID string
	expiresAt     time.Time
}

const cacheTTL = 30 * time.Second

func getCached(repoPath string) (string, error) {
	cacheMu.Lock()
	if e, ok := cache[repoPath]; ok && time.Now().Before(e.expiresAt) {
		cacheMu.Unlock()
		return e.coordinatorID, nil
	}
	cacheMu.Unlock()

	id, err := readFromDisk(repoPath)
	if err != nil {
		return "", err
	}

	cacheMu.Lock()
	cache[repoPath] = cacheEntry{coordinatorID: id, expiresAt: time.Now().Add(cacheTTL)}
	cacheMu.Unlock()
	return id, nil
}

// readFromDisk scans ~/.jcode/state/swarm/ for a JSON whose swarm_id
// matches "<repoPath>/.git" (jcode writes repoPath with .git appended).
func readFromDisk(repoPath string) (string, error) {
	stateDir, err := stateDir()
	if err != nil {
		return "", err
	}
	entries, err := os.ReadDir(stateDir)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return "", ErrNotFound
		}
		return "", fmt.Errorf("coordinator: read %s: %w", stateDir, err)
	}
	want := repoPath + "/.git"
	for _, ent := range entries {
		if ent.IsDir() || !strings.HasSuffix(ent.Name(), ".json") {
			continue
		}
		full := filepath.Join(stateDir, ent.Name())
		data, err := os.ReadFile(full)
		if err != nil {
			continue
		}
		var st SwarmState
		if err := json.Unmarshal(data, &st); err != nil {
			continue
		}
		if st.SwarmID == want && st.CoordinatorSessionID != "" {
			return st.CoordinatorSessionID, nil
		}
	}
	return "", ErrNotFound
}

// stateDir returns the directory containing swarm JSON state files.
func stateDir() (string, error) {
	if d := os.Getenv("JCODE_STATE_DIR"); d != "" {
		return filepath.Join(d, "swarm"), nil
	}
	if d := os.Getenv("XDG_STATE_HOME"); d != "" {
		return filepath.Join(d, "jcode", "swarm"), nil
	}
	h, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(h, ".jcode", "state", "swarm"), nil
}

// RepoPathFromCwd returns the absolute repo path (without trailing
// .git) for the current working directory, via `git rev-parse
// --show-toplevel`. If the cwd is not inside a git repo, returns "".
func RepoPathFromCwd() string {
	cmd := exec.Command("git", "rev-parse", "--show-toplevel")
	cmd.Env = append(os.Environ(), "GIT_TERMINAL_PROMPT=0")
	out, err := cmd.Output()
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(out))
}