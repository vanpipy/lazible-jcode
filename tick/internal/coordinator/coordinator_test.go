package coordinator

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

// TestRepoPathFromCwd_EnvVarOverride verifies that when
// JCODE_TICK_REPO_PATH is set, RepoPathFromCwd returns its value
// verbatim — even when the cwd is not inside a git repo (which would
// otherwise cause `git rev-parse --show-toplevel` to return "").
//
// This is the fix path for the MCP-launched daemon case: jcode's MCP
// subprocess spawns tick with CWD != repo path, so the rev-parse
// fallback would silently yield "" and disable the self-wake
// detection gate added in 719e16b.
func TestRepoPathFromCwd_EnvVarOverride(t *testing.T) {
	const want = "/explicit/override/path"

	// Use t.Setenv so the override is automatically restored at test
	// end — cleaner than os.Setenv + t.Cleanup.
	t.Setenv("JCODE_TICK_REPO_PATH", want)

	// Move cwd to a directory that is definitively NOT inside a git
	// repo, so the rev-parse branch would return "" if invoked.
	origCwd, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	t.Cleanup(func() { _ = os.Chdir(origCwd) })

	tmp := t.TempDir()
	// Resolve symlinks so the chdir is stable on systems where
	// t.TempDir returns a /tmp -> /private/tmp style path.
	resolved, err := filepath.EvalSymlinks(tmp)
	if err != nil {
		t.Fatalf("eval symlinks: %v", err)
	}
	if err := os.Chdir(resolved); err != nil {
		t.Fatalf("chdir %s: %v", resolved, err)
	}

	got := RepoPathFromCwd()
	if got != want {
		t.Fatalf("RepoPathFromCwd() = %q, want %q (env override should win over rev-parse)", got, want)
	}
}

// TestRepoPathFromCwd_FallsBackToGitRevParse verifies that without
// the env var, the function returns whatever `git rev-parse
// --show-toplevel` returns from the current cwd (or "" if cwd is
// not in a git repo). We do not pin a specific path because the
// test environment may run inside the lazible-jcode repo, an
// unrelated git repo, or no repo at all. Instead, we cross-check
// the result against an independent rev-parse invocation and
// require the two to match — this catches both "always returns
// empty" and "ignores the cwd" regressions.
func TestRepoPathFromCwd_FallsBackToGitRevParse(t *testing.T) {
	// Make sure the env var is unset for this test. t.Setenv to "" is
	// a no-op for os.Getenv (returns ""), so the override branch is
	// skipped.
	t.Setenv("JCODE_TICK_REPO_PATH", "")

	origCwd, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	t.Cleanup(func() { _ = os.Chdir(origCwd) })

	// Move to /tmp — if /tmp is inside a git repo (unusual but
	// possible in some test envs), we'll validate against it.
	if err := os.Chdir("/tmp"); err != nil {
		t.Fatalf("chdir /tmp: %v", err)
	}

	// Compute the expected value independently.
	cmd := exec.Command("git", "rev-parse", "--show-toplevel")
	cmd.Env = append(os.Environ(), "GIT_TERMINAL_PROMPT=0")
	out, err := cmd.Output()
	var want string
	if err != nil {
		// Not in a git repo — expect RepoPathFromCwd to return "" too.
		want = ""
	} else {
		want = strings.TrimSpace(string(out))
	}

	got := RepoPathFromCwd()
	if got != want {
		t.Fatalf("RepoPathFromCwd() = %q, want %q (rev-parse fallback)", got, want)
	}
}
