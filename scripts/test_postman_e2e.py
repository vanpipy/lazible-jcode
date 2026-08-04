#!/usr/bin/env python3
"""Postman E2E test: synthetic branches at known ages, classified by tick.

This script creates a temporary git repo, populates it with 5 worker
branches whose commit ages are backdated via GIT_AUTHOR_DATE/GIT_COMMITTER_DATE,
embeds an artifact JSON in each commit body, runs `swarm-state-monitor.py
tick` against the temp repo, and asserts the classification table matches
expectations.

After verification it cleans up the temp repo (git branches + tempdir).

This is the P2 audit follow-up: an executable end-to-end test for the
Smart Postman classification logic, complementing LIVENESS_VALIDATION.md
which is a static trace.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path("/home/leroy/Project/lazible-jcode").resolve()
MONITOR = REPO_ROOT / "scripts" / "swarm-state-monitor.py"

# Each scenario: (branch_name, artifact_type, age_minutes_at_creation)
# age_minutes_at_creation is the age we want the commit to appear as
# at the moment tick runs.
SCENARIOS = [
    ("feat/postman-e2e-healthy",      "final",    2),
    ("feat/postman-e2e-progressing",  "progress", 3),
    ("feat/postman-e2e-quiet",        "progress", 8),
    ("feat/postman-e2e-silent",       "progress", 20),
    ("feat/postman-e2e-dead",         "progress", 45),
    # Beyond 24h — should be hidden by default --since=24h, shown with --include-stale.
    ("feat/postman-e2e-ancient",      "progress", 25 * 60),
]


def artifact_block(atype: str) -> str:
    return (
        "```json artifact\n"
        + json.dumps(
            {
                "type": atype,
                "session_id": "postman-e2e-test",
                "task_id": "test",
                "branch": "placeholder",
                "commit": "placeholder",
                "elapsed_min": 1,
                "step": f"synthetic {atype} commit for postman E2E test",
                "next": "n/a",
                "confidence": "high",
                "blockers": [],
            },
            indent=2,
        )
        + "\n```"
    )


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def setup_temp_repo() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="postman-e2e-"))
    run(["git", "init", "-q", "-b", "main", str(tmp)])
    run(["git", "-C", str(tmp), "config", "user.email", "test@local"])
    run(["git", "-C", str(tmp), "config", "user.name", "PostmanE2E"])
    # Initial commit on main so we can branch off.
    (tmp / "README.md").write_text("synthetic postman e2e repo\n")
    run(["git", "-C", str(tmp), "add", "README.md"])
    run(["git", "-C", str(tmp), "commit", "-q", "-m", "initial commit"])
    return tmp


def create_branch_with_artifact(tmp: Path, name: str, atype: str, age_min: int):
    """Create a branch with a single commit whose body has the artifact
    JSON, and whose author/committer date is backdated by `age_min` minutes.

    Note: git interprets GIT_AUTHOR_DATE / GIT_COMMITTER_DATE in *local* time
    when no timezone suffix is present. We use localtime so the resulting
    commit timestamp matches the requested age in the system's timezone.
    Using gmtime would mis-anchor commits by the UTC offset (e.g. 8h drift
    on a UTC+8 system)."""
    target_ts = int(time.time()) - age_min * 60
    iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(target_ts))
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": iso,
        "GIT_COMMITTER_DATE": iso,
    }
    body = f"synthetic {atype} commit (backdated {age_min}m)\n\n{artifact_block(atype)}"
    # Branch off main HEAD, write a unique file so the commit is real.
    branch_file = tmp / f"file-{name.replace('/', '_')}.txt"
    branch_file.write_text(f"content for {name}\n")
    run(["git", "-C", str(tmp), "checkout", "-q", "-b", name, "main"])
    run(["git", "-C", str(tmp), "add", str(branch_file.relative_to(tmp))])
    p = subprocess.run(
        ["git", "-C", str(tmp), "commit", "-q", "-m", body],
        env=env,
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(f"commit failed on {name}: {p.stderr}")
    run(["git", "-C", str(tmp), "checkout", "-q", "main"])


def tick(cwd: Path) -> str:
    """Run swarm-state-monitor.py tick and return its stdout."""
    p = subprocess.run(
        [sys.executable, str(MONITOR), "tick", "--include-stale"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=15,
    )
    return p.stdout


# Expected classification per scenario, given the classifier rules:
#   final    + age ≤ 5  → healthy
#   final    + age ≤ 15 → quiet
#   final    + age > 15 → silent
#   progress + age < 5  → progressing
#   progress + age ≥ 5, < 15 → quiet
#   progress + age ≥ 15, < 30 → silent
#   progress + age ≥ 30 → dead
EXPECTED = {
    "feat/postman-e2e-healthy":     "healthy",
    "feat/postman-e2e-progressing": "progressing",
    "feat/postman-e2e-quiet":       "quiet",
    "feat/postman-e2e-silent":      "silent",
    "feat/postman-e2e-dead":        "dead",
    # ancient is > 24h old, so classified as 'dead' (past all SLAs) but
    # hidden by default --since=24h filter.
    "feat/postman-e2e-ancient":     "dead",
}


def main():
    if not MONITOR.exists():
        print(f"FAIL: monitor not found at {MONITOR}", file=sys.stderr)
        return 1

    tmp = setup_temp_repo()
    print(f"[setup] temp repo at {tmp}")

    try:
        for name, atype, age in SCENARIOS:
            create_branch_with_artifact(tmp, name, atype, age)
            print(f"[setup] created {name} ({atype}, age={age}m)")

        # 1. Default tick (--since=24h): ancient branch must be hidden,
        #    all others visible.
        print("\n[tick default --since=24h]")
        out_default = subprocess.run(
            [sys.executable, str(MONITOR), "tick"],
            cwd=str(tmp),
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
        print(out_default)
        ancient_in_default = "feat/postman-e2e-ancient" in out_default
        healthy_in_default = "feat/postman-e2e-healthy" in out_default
        default_ok = (not ancient_in_default) and healthy_in_default
        mark = "OK" if default_ok else "FAIL"
        print(f"\n[assert] [{mark}] default --since=24h: ancient HIDDEN, healthy VISIBLE")
        if not default_ok:
            print(f"  ancient_in_default={ancient_in_default}, healthy_in_default={healthy_in_default}")

        # 2. tick --include-stale: all 6 visible, all classified correctly.
        print("\n[tick --include-stale]")
        out = tick(tmp)
        # Print only the table (skip the JSON block at the end)
        for line in out.splitlines():
            if line.startswith("feat/postman-e2e-"):
                print(f"  {line}")

        # Parse classifications from the --include-stale output.
        classified = {}
        for line in out.splitlines():
            for name in EXPECTED:
                if line.startswith(name):
                    parts = line.split()
                    for cls in ("healthy", "progressing", "quiet", "silent", "dead"):
                        if cls in parts:
                            classified[name] = cls
                            break
                    break

        print("\n[assert] classification table (--include-stale):")
        all_pass = True
        for name, expected in EXPECTED.items():
            actual = classified.get(name, "MISSING")
            ok = actual == expected
            mark = "OK" if ok else "FAIL"
            print(f"  [{mark}] {name}: expected={expected}, actual={actual}")
            if not ok:
                all_pass = False

        if all_pass and default_ok:
            print("\n[E2E] all 6 synthetic branches classified + filtered as expected")
            return 0
        print("\n[E2E] classification or filter mismatch — see above", file=sys.stderr)
        return 1
    finally:
        # Cleanup.
        for name, _, _ in SCENARIOS:
            run(["git", "-C", str(tmp), "branch", "-D", name])
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"\n[cleanup] removed {tmp}")


if __name__ == "__main__":
    sys.exit(main())