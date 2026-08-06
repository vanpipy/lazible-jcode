package main

import (
	"bytes"
	"io"
	"os"
	"strings"
	"syscall"
	"testing"
)

// TestDaemonSignals_IncludesSIGHUP asserts that the daemon's signal
// handler includes SIGHUP. The Unix convention is that well-behaved
// daemons ignore SIGHUP (treating it as a config-reload hook or
// no-op), not exit on it — a SIGHUP-capable process survives terminal
// disconnects and background invocations. Without this, every `kill
// -SIGHUP <pid>` from a user (or from a process-group tear-down)
// terminates the daemon and triggers the "jobs pile up, nothing
// fires" failure mode documented in
// docs/TICK_DAEMON_FAILURE_2026-08-05.md §"Other findings" #1.
func TestDaemonSignals_IncludesSIGHUP(t *testing.T) {
	found := false
	for _, s := range daemonSignals {
		if s == syscall.SIGHUP {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("daemonSignals missing SIGHUP; got %v", daemonSignals)
	}
}

// TestDaemonSignals_StillIncludesSIGINTAndSIGTERM asserts the original
// signal handlers are preserved — SIGHUP must be added, not replace
// them. SIGINT (Ctrl-C) and SIGTERM (default kill) are still the
// expected shutdown signals.
func TestDaemonSignals_StillIncludesSIGINTAndSIGTERM(t *testing.T) {
	want := map[os.Signal]bool{
		syscall.SIGINT:  false,
		syscall.SIGTERM: false,
	}
	for _, s := range daemonSignals {
		if _, ok := want[s]; ok {
			want[s] = true
		}
	}
	for sig, present := range want {
		if !present {
			t.Errorf("daemonSignals missing %v; got %v", sig, daemonSignals)
		}
	}
}

// TestStartupBanner_IncludesBuildInfo asserts the startup banner
// contains the commit SHA, build timestamp, and PID. Without the
// banner, an operator tailing daemon stderr cannot tell whether the
// running binary has the post-fix behavior (Subscribe handshake +
// ErrSelfWake) or the pre-fix behavior (silent self-wake loss). The
// commit SHA is injected via -ldflags "-X main.commitSHA=<sha>" at
// build time; here we override the package vars to simulate that
// injection without invoking the linker.
//
// See docs/TICK_DAEMON_FAILURE_2026-08-05.md §"What would have caught
// this earlier" for the related "version fingerprint" gap.
func TestStartupBanner_IncludesBuildInfo(t *testing.T) {
	origCommit, origBuild := commitSHA, buildTime
	commitSHA = "abc1234"
	buildTime = "2026-08-06T16:00:00Z"
	t.Cleanup(func() {
		commitSHA = origCommit
		buildTime = origBuild
	})

	var buf bytes.Buffer
	printStartupBanner(&buf, 12345)

	got := buf.String()
	for _, want := range []string{
		"tick",
		"abc1234",
		"2026-08-06T16:00:00Z",
		"12345",
	} {
		if !strings.Contains(got, want) {
			t.Errorf("banner missing %q; got: %q", want, got)
		}
	}
}

// TestStartupBanner_HandlesUnknownCommit asserts the banner does not
// crash when commitSHA is the ldflags default "unknown" — important so
// that `go run` / `go test` invocations still produce a valid banner
// even without the production build flags.
func TestStartupBanner_HandlesUnknownCommit(t *testing.T) {
	origCommit, origBuild := commitSHA, buildTime
	commitSHA = "unknown"
	buildTime = "unknown"
	t.Cleanup(func() {
		commitSHA = origCommit
		buildTime = origBuild
	})

	var buf bytes.Buffer
	printStartupBanner(&buf, 999)

	got := buf.String()
	if !strings.Contains(got, "tick") {
		t.Errorf("banner must include program name even when build vars are unknown; got: %q", got)
	}
	if !strings.Contains(got, "999") {
		t.Errorf("banner must include PID; got: %q", got)
	}
}

// unused import guard so the test file compiles even if io is dropped
// during future edits (linters catch unused imports).
var _ = io.Discard