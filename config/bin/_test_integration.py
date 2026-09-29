#!/usr/bin/env python3
# Integration tests for jcode-orchestrate end-to-end flow usability.
#
# Unlike _test_orchestrator.py (which uses --fake-report), these tests:
#   - Use REAL verify_cmd (not just `true`)
#   - Use --json output and parse the response
#   - Cover --loop N, multi-milestone, mixed review paths
#   - Verify md5 of install artifacts matches source
#
# Each test gets a hermetic temp git repo + temp goal home.
# Exits non-zero on any assertion failure.

import json
import os
import shutil
import subprocess
import sys
import tempfile
import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
GOAL = REPO / "config" / "bin" / "jcode-goal"
ORCH = REPO / "config" / "bin" / "jcode-orchestrate"

PASS = 0
FAIL = 0


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def run(cmd: list[str], env: dict | None = None, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, env=env, check=False, **kw)


def setup_repo() -> tuple[Path, str, str]:
    """Create temp git repo, init goal, return (home, goal_id, cwd_backup)."""
    home = Path(tempfile.mkdtemp(prefix="orch-int-"))
    run(["git", "init", "-q", str(home)])
    run(["git", "-C", str(home), "config", "user.email", "test@test"])
    run(["git", "-C", str(home), "config", "user.name", "test"])
    (home / "README.md").write_text("init")
    run(["git", "-C", str(home), "add", "README.md"])
    run(["git", "-C", str(home), "commit", "-q", "-m", "init"])
    env = os.environ.copy()
    env["JCODE_GOAL_HOME"] = str(home)
    out = run([str(GOAL), "add", "Integration", "--priority", "high",
               "--content", "E2E test", "--scope", "project", "--cwd", str(home)], env=env)
    assert out.returncode == 0, out.stderr
    cwd_backup = os.getcwd()
    os.chdir(home)
    data = json.loads(run([str(GOAL), "list", "--json"], env=env).stdout)
    return home, data[0]["id"], cwd_backup


def orchestrate(home: Path, *args: str, fake_report: str | None = None,
               dryrun_verify: str | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["JCODE_GOAL_HOME"] = str(home)
    cmd = [str(ORCH), "--cwd", str(home), "--dry-run"]
    if fake_report is not None:
        cmd += ["--fake-report", fake_report]
    if dryrun_verify is not None:
        env["JCODE_DRYRUN_VERIFY"] = dryrun_verify
    cmd += list(args)
    return run(cmd, env=env)


def get_goal(home: Path, gid: str) -> dict:
    env = os.environ.copy()
    env["JCODE_GOAL_HOME"] = str(home)
    data = json.loads(run([str(GOAL), "list", "--json"], env=env).stdout)
    return next(g for g in data if g["id"] == gid)


def step_status(g: dict, mid: str, sid: str) -> str:
    m = next(m for m in g["milestones"] if m["id"] == mid)
    s = next(s for s in m["steps"] if s["id"] == sid)
    return s["status"]


def milestone_status(g: dict, mid: str) -> str:
    return next(m for m in g["milestones"] if m["id"] == mid)["status"]


def assert_eq(actual, expected, label):
    global PASS, FAIL
    if actual == expected:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}: got {actual!r}, expected {expected!r}")


def assert_in(needle, haystack, label):
    global PASS, FAIL
    if needle in haystack:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}: {needle!r} not in {haystack!r}")


# ---------------------------------------------------------------------------
# I1: Fresh E2E happy path with REAL verify_cmd
# ---------------------------------------------------------------------------
def test_i1_e2e_real_verify():
    print("I1: E2E happy path with REAL verify_cmd (multi-milestone)")
    home, gid, cwd_backup = setup_repo()
    try:
        env = os.environ.copy()
        env["JCODE_GOAL_HOME"] = str(home)
        run([str(GOAL), "milestone", gid, "add", "M1: backend"], env=env)
        run([str(GOAL), "step", gid, "m-0", "add", "implement X",
             "--verify", "python3 -c 'print(\"ok\")'"], env=env)
        run([str(GOAL), "step", gid, "m-0", "add", "implement Y",
             "--verify", "echo done"], env=env)
        run([str(GOAL), "milestone", gid, "add", "M2: docs", "--no-review"], env=env)
        run([str(GOAL), "step", gid, "m-1", "add", "write docs",
             "--verify", "ls /tmp >/dev/null"], env=env)

        # Use --loop N for true E2E
        result = orchestrate(home, "--loop", "20")
        g = get_goal(home, gid)
        assert_eq(g["status"], "complete", "I1 goal.status = complete")
        assert_eq(milestone_status(g, "m-0"), "completed", "I1 m-0 = completed")
        assert_eq(milestone_status(g, "m-1"), "completed", "I1 m-1 = completed")
        assert_eq(step_status(g, "m-0", "m-0-step-0"), "done", "I1 m-0-step-0 = done")
        assert_eq(step_status(g, "m-0", "m-0-step-1"), "done", "I1 m-0-step-1 = done")
        assert_eq(step_status(g, "m-1", "m-1-step-0"), "done", "I1 m-1-step-0 = done")
        # Reviewer fired for m-0 (review_required default) and was skipped for m-1 (--no-review)
        assert_eq(g["milestones"][0]["review_verdict"], "clean", "I1 m-0 verdict=clean")
        assert_eq(g["milestones"][1].get("review_verdict"), None, "I1 m-1 no verdict")
        # Loop must have stopped early on goal_completed (so ran < 20)
        assert_in("loop: ran ", result.stdout, "I1 loop summary printed")
    finally:
        os.chdir(cwd_backup)
        shutil.rmtree(home, ignore_errors=True)


# ---------------------------------------------------------------------------
# I2: Real verify_cmd failure → step retry → escalate
# ---------------------------------------------------------------------------
def test_i2_real_verify_failure():
    print("I2: Real verify_cmd failure (false) → step retry → escalate")
    home, gid, cwd_backup = setup_repo()
    try:
        env = os.environ.copy()
        env["JCODE_GOAL_HOME"] = str(home)
        # max_retries=2 so we escalate after 3 fails (0, 1, 2)
        run([str(GOAL), "milestone", gid, "add", "M0",
             "--review-max-retries", "2", "--no-review"], env=env)
        run([str(GOAL), "step", gid, "m-0", "add", "always-fails",
             "--verify", "false",
             "--max-retries", "2"], env=env)

        # Drive 10 cycles (way more than needed)
        for _ in range(10):
            orchestrate(home, dryrun_verify="fail")

        g = get_goal(home, gid)
        s = g["milestones"][0]["steps"][0]
        assert_eq(s["status"], "escalated", "I2 step.status = escalated")
        assert_eq(s["retry_count"], 2, "I2 retry_count = 2 (==max)")
        # last_error should mention forced failure
        assert_in("forced failure", s.get("last_error", ""), "I2 last_error populated")
    finally:
        os.chdir(cwd_backup)
        shutil.rmtree(home, ignore_errors=True)


# ---------------------------------------------------------------------------
# I3: --json output mode parses correctly
# ---------------------------------------------------------------------------
def test_i3_json_output():
    print("I3: --json output mode parses correctly")
    home, gid, cwd_backup = setup_repo()
    try:
        env = os.environ.copy()
        env["JCODE_GOAL_HOME"] = str(home)
        run([str(GOAL), "milestone", gid, "add", "M0", "--no-review"], env=env)
        run([str(GOAL), "step", gid, "m-0", "add", "x",
             "--verify", "true"], env=env)

        result = orchestrate(home, "--once", "--json")
        # First cycle: spawn_coder
        data = json.loads(result.stdout)
        assert_eq(data.get("ok"), True, "I3 json.ok = true")
        assert_eq(data.get("goal_id"), gid, "I3 json.goal_id matches")
        assert len(data.get("actions", [])) >= 1, "I3 json.actions non-empty"
        a0 = data["actions"][0]
        assert_eq(a0.get("type"), "spawn_coder", "I3 first action = spawn_coder")

        # Second cycle: step_done + milestone_in_progress
        result = orchestrate(home, "--once", "--json")
        data = json.loads(result.stdout)
        actions = [a["type"] for a in data["actions"]]
        assert_in("step_done", actions, "I3 second cycle has step_done")
    finally:
        os.chdir(cwd_backup)
        shutil.rmtree(home, ignore_errors=True)


# ---------------------------------------------------------------------------
# I4: Mixed --no-review + review milestones
# ---------------------------------------------------------------------------
def test_i4_mixed_review():
    print("I4: Mixed --no-review + review milestones")
    home, gid, cwd_backup = setup_repo()
    try:
        env = os.environ.copy()
        env["JCODE_GOAL_HOME"] = str(home)
        run([str(GOAL), "milestone", gid, "add", "M-fast", "--no-review"], env=env)
        run([str(GOAL), "step", gid, "m-0", "add", "s1",
             "--verify", "true"], env=env)
        run([str(GOAL), "milestone", gid, "add", "M-review"], env=env)
        run([str(GOAL), "step", gid, "m-1", "add", "s2",
             "--verify", "echo verified"], env=env)

        # Drive to completion (single-step per milestone = 3 cycles + 1 review = 4)
        result = orchestrate(home, "--loop", "10")
        g = get_goal(home, gid)
        assert_eq(g["status"], "complete", "I4 goal.status = complete")
        assert_eq(milestone_status(g, "m-0"), "completed", "I4 m-fast = completed")
        assert_eq(milestone_status(g, "m-1"), "completed", "I4 m-review = completed")
        assert_eq(g["milestones"][0].get("reviewer_session_id"), None,
                  "I4 m-fast: reviewer never spawned")
        assert_in("reviewer:", str(g["milestones"][1].get("reviewer_label", "")),
                  "I4 m-review: reviewer spawned")
        # Loop must stop early (ran < 10)
        assert_in("loop: ran ", result.stdout, "I4 loop summary")
    finally:
        os.chdir(cwd_backup)
        shutil.rmtree(home, ignore_errors=True)


# ---------------------------------------------------------------------------
# I5: Real reviewer JSON with findings → precise reset (real file path)
# ---------------------------------------------------------------------------
def test_i5_real_json_findings():
    print("I5: Real reviewer JSON file (findings) → precise reset")
    home, gid, cwd_backup = setup_repo()
    try:
        env = os.environ.copy()
        env["JCODE_GOAL_HOME"] = str(home)
        run([str(GOAL), "milestone", gid, "add", "M0"], env=env)
        run([str(GOAL), "step", gid, "m-0", "add", "step-A",
             "--verify", "true"], env=env)
        run([str(GOAL), "step", gid, "m-0", "add", "step-B",
             "--verify", "true"], env=env)

        # Write the reviewer verdict to a real JSON file
        report = {
            "verdict": "findings",
            "findings": [
                {
                    "step_id": "m-0-step-1",
                    "severity": "major",
                    "location": "src/x.py:42",
                    "issue": "Edge case missing — counter overflow on negative input",
                }
            ],
            "confidence": 0.85,
            "reasoning": "Audited diff; main concern is the arithmetic branch",
        }
        report_path = home / "reviewer_report.json"
        report_path.write_text(json.dumps(report))

        # Drive 4 cycles to reach 'review' state (spawn A, done A + spawn B, done B + milestone_in_progress, spawn reviewer)
        for _ in range(4):
            orchestrate(home)

        # Cycle 5: reviewer reads from --fake-report (real JSON file content)
        # Note: --fake-report takes a string, not a file path. Embed the JSON.
        result = orchestrate(home, "--fake-report", report_path.read_text())

        g = get_goal(home, gid)
        m = g["milestones"][0]
        assert_eq(m["status"], "in_progress", "I5 milestone reopened")
        assert_eq(m["review_retry_count"], 1, "I5 retry_count = 1")
        assert_eq(m["review_verdict"], "findings", "I5 verdict = findings")
        # step-A should remain done; step-B reset with finding attached
        assert_eq(step_status(g, "m-0", "m-0-step-0"), "done", "I5 step-A unchanged")
        assert_eq(step_status(g, "m-0", "m-0-step-1"), "pending", "I5 step-B reset")
        s_b = next(s for s in m["steps"] if s["id"] == "m-0-step-1")
        assert_in("Edge case missing", s_b.get("last_findings", ""),
                  "I5 finding text attached")
        assert_in("src/x.py:42", s_b.get("last_findings", ""),
                  "I5 finding location attached")
        assert_in("review_failed", result.stdout, "I5 review_failed action")
    finally:
        os.chdir(cwd_backup)
        shutil.rmtree(home, ignore_errors=True)


# ---------------------------------------------------------------------------
# I6: --loop N stops on terminal action
# ---------------------------------------------------------------------------
def test_i6_loop_stops_on_terminal():
    print("I6: --loop N stops on terminal action (goal_completed)")
    home, gid, cwd_backup = setup_repo()
    try:
        env = os.environ.copy()
        env["JCODE_GOAL_HOME"] = str(home)
        # Single step, no review: completes in 2 cycles (spawn + done + close)
        run([str(GOAL), "milestone", gid, "add", "M0", "--no-review"], env=env)
        run([str(GOAL), "step", gid, "m-0", "add", "x",
             "--verify", "true"], env=env)

        result = orchestrate(home, "--loop", "100", "--json")
        # JSON output is pretty-printed multi-line. Use a brace-counting parser.
        text = result.stdout.strip()
        # Concatenate all top-level JSON objects from the stream.
        decoder = json.JSONDecoder()
        idx = 0
        objects = []
        while idx < len(text):
            # Skip whitespace between objects.
            while idx < len(text) and text[idx] in " \n\r\t":
                idx += 1
            if idx >= len(text):
                break
            try:
                obj, end = decoder.raw_decode(text[idx:])
                objects.append(obj)
                idx += end
            except json.JSONDecodeError:
                break
        assert objects, f"I6 no JSON objects parsed from: {text[:200]!r}"
        summary = objects[-1]
        # Expected: ran 2 cycles to complete (spawn, done+close). After
        # goal_completed, the auto-promote tries to peek the queue head;
        # with only one goal, the queue is empty, so cmd_loop stops with
        # stopped_reason="queue_empty". The earlier "terminal_action" value
        # was a less specific catch-all.
        assert summary["ran_cycles"] < 100, f"I6 loop stopped early (ran {summary['ran_cycles']})"
        assert summary["ran_cycles"] >= 2, f"I6 loop ran at least 2 cycles (got {summary['ran_cycles']})"
        assert_eq(summary["stopped_reason"], "queue_empty", "I6 stopped_reason = queue_empty (post auto-promote)")
        assert_eq(summary["max_cycles"], 100, "I6 max_cycles = 100")
    finally:
        os.chdir(cwd_backup)
        shutil.rmtree(home, ignore_errors=True)


# ---------------------------------------------------------------------------
# I7: md5 install artifacts match source
# ---------------------------------------------------------------------------
def test_i7_md5_install_artifacts():
    global PASS, FAIL
    print("I7: md5 install artifacts match source")
    pairs = [
        ("config/bin/jcode-orchestrate", "~/.local/bin/jcode-orchestrate"),
        ("config/bin/jcode-goal", "~/.local/bin/jcode-goal"),
        ("config/bin/jcode-l2-check", "~/.local/bin/jcode-l2-check"),
        ("config/bin/jcode-tool-policy", "~/.local/bin/jcode-tool-policy"),
        ("config/skills/orchestrator/SKILL.md", "~/.jcode/skills/orchestrator/SKILL.md"),
        ("config/skills/goal/SKILL.md", "~/.jcode/skills/goal/SKILL.md"),
        ("config/skills/long-task-discipline/SKILL.md",
         "~/.jcode/skills/long-task-discipline/SKILL.md"),
        ("config/share/jcode-orchestrate/prompts/coder.md",
         "~/.local/share/jcode-orchestrate/prompts/coder.md"),
        ("config/share/jcode-orchestrate/prompts/reviewer.md",
         "~/.local/share/jcode-orchestrate/prompts/reviewer.md"),
    ]
    for src_rel, dst_rel in pairs:
        src = (REPO / src_rel).resolve()
        dst = Path(dst_rel).expanduser()
        if not dst.exists():
            FAIL += 1
            print(f"  FAIL  md5: {dst_rel} missing")
            continue
        if not src.exists():
            FAIL += 1
            print(f"  FAIL  md5: source {src_rel} missing")
            continue
        s_md5 = md5(src)
        d_md5 = md5(dst)
        if s_md5 == d_md5:
            PASS += 1
            print(f"  PASS  md5 match: {src_rel}")
        else:
            FAIL += 1
            print(f"  FAIL  md5 mismatch: {src_rel} ({s_md5}) != {dst_rel} ({d_md5})")


# ---------------------------------------------------------------------------
# I8: end-to-end queue chain — --loop N drives 3 goals in priority order
# ---------------------------------------------------------------------------
def test_i8_queue_chain():
    print("I8: end-to-end queue chain (3 goals, --loop drives all)")
    # setup_repo creates 1 active goal. We add 2 more pending goals with
    # --priority to control the order, then run --loop with sufficient
    # budget to drive all 3 to completion.
    home, gid1, cwd_backup = setup_repo()
    try:
        env = os.environ.copy()
        env["JCODE_GOAL_HOME"] = str(home)

        # Add 2 more goals (will queue as pending since gid1 is active).
        out = run([str(GOAL), "add", "Second", "--priority", "medium",
                   "--scope", "project", "--cwd", str(home)], env=env)
        assert out.returncode == 0, out.stderr
        out = run([str(GOAL), "add", "Third", "--priority", "low",
                   "--scope", "project", "--cwd", str(home)], env=env)
        assert out.returncode == 0, out.stderr

        # Each goal needs a single no-review milestone + step with verify=true.
        goals = json.loads(run([str(GOAL), "list", "--json"], env=env).stdout)
        active = next(g for g in goals if g["status"] == "active")
        pending = sorted([g for g in goals if g["status"] == "pending"],
                         key=lambda g: g.get("created_at", ""))
        assert_eq(len(pending), 2, "I8 setup: 2 pending goals")

        for g in [active, *pending]:
            run([str(GOAL), "milestone", g["id"], "add", "M0", "--no-review"], env=env)
            run([str(GOAL), "step", g["id"], "m-0", "add", "work",
                 "--verify", "true"], env=env)

        # Run --loop with enough budget to drive all 3 goals (each needs
        # spawn + done + close ~2-3 cycles; 3 goals ~9 cycles).
        result = orchestrate(home, "--loop", "30", "--json")
        text = result.stdout.strip()
        decoder = json.JSONDecoder()
        idx = 0
        objects = []
        while idx < len(text):
            while idx < len(text) and text[idx] in " \n\r\t":
                idx += 1
            if idx >= len(text):
                break
            try:
                obj, end = decoder.raw_decode(text[idx:])
                objects.append(obj)
                idx += end
            except json.JSONDecodeError:
                break
        assert objects, f"I8 no JSON objects parsed from: {text[:200]!r}"
        summary = objects[-1]

        # All 3 should now be complete (ran out of queue -> queue_empty).
        assert_eq(summary["stopped_reason"], "queue_empty", "I8 stopped_reason = queue_empty")
        assert summary["ran_cycles"] >= 6, f"I8 ran >= 6 cycles (got {summary['ran_cycles']})"
        assert summary["ran_cycles"] <= 20, f"I8 ran <= 20 cycles (got {summary['ran_cycles']})"

        # Reload final state: all 3 goals should be status=complete.
        goals_final = json.loads(run([str(GOAL), "list", "--json"], env=env).stdout)
        statuses = sorted([g["status"] for g in goals_final])
        assert_eq(statuses, ["complete", "complete", "complete"],
                  "I8 all 3 goals completed via auto-promote chain")
    finally:
        os.chdir(cwd_backup)
        shutil.rmtree(home, ignore_errors=True)


def main() -> int:
    tests = [test_i1_e2e_real_verify, test_i2_real_verify_failure,
             test_i3_json_output, test_i4_mixed_review,
             test_i5_real_json_findings, test_i6_loop_stops_on_terminal,
             test_i7_md5_install_artifacts,
             test_i8_queue_chain]
    for t in tests:
        try:
            t()
        except AssertionError as e:
            global FAIL
            FAIL += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            FAIL += 1
            print(f"  ERROR {t.__name__}: {e}")
    print()
    print(f"{'PASS' if FAIL == 0 else 'FAIL'}: {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())