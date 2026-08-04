#!/usr/bin/env python3
"""Tests for the executable-bit CI gate.

Verifies that every shell script under ``scripts/`` and ``skills/`` has the
executable bit set. Catches ``chmod`` regressions where a fresh checkout
lands with non-executable scripts and the `bash scripts/...` invocations
in the "Verification before push" block silently fail to load.

The gate is the *minimum* invariant — the wrapper scripts (install.sh,
root-tick.sh, etc.) already self-check on invocation, but those checks
only cover the seven scripts the wrapper knows about. This walks the
filesystem and catches the long tail (lib/, dryrun, idempotency test,
worktree-swarm, build-jcode-canary, sync-jcode-source, etc.).

Three tests:

* ``test_all_sh_scripts_are_executable`` — every ``*.sh`` file under
  ``scripts/`` and ``skills/`` must be executable. Lists every offender
  on failure so the diagnostic is one shot, not "fix one then rerun".
* ``test_no_stray_non_executable_sh_files`` — the inverse check; this
  is structurally the same assertion, but the test name encodes intent
  ("no stray non-executable sh files in the repo") so a future reader
  understands why two tests cover the same ground.
* ``test_install_sh_step0_preflight_actually_runs`` — end-to-end smoke:
  invoke ``bash scripts/install.sh --help`` as a subprocess. Confirms
  the script is executable, syntactically valid (``bash -n`` is the
  install.sh step-0 pre-flight), and that the wrapper prints the
  expected step descriptions. This is the integration test; the two
  unit tests above only assert filesystem metadata.
"""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _collect_sh_files() -> list[Path]:
    """Walk ``scripts/`` and ``skills/`` and return every ``*.sh`` file.

    Relative to repo root. Sorted for stable diagnostics — diff between
    two failure runs should be zero on the file list, only the assertion
    message should change.
    """
    found: list[Path] = []
    for top in (REPO_ROOT / "scripts", REPO_ROOT / "skills"):
        if not top.is_dir():
            continue
        for path in sorted(top.rglob("*.sh")):
            if path.is_file():
                found.append(path)
    return found


class TestExecBits(unittest.TestCase):
    """CI gate: every ``*.sh`` under ``scripts/`` and ``skills/`` is +x."""

    def test_all_sh_scripts_are_executable(self) -> None:
        sh_files = _collect_sh_files()
        self.assertTrue(sh_files, "no .sh files found under scripts/ or skills/ — discovery is broken")
        offenders = [p for p in sh_files if not os.access(p, os.X_OK)]
        self.assertEqual(
            offenders,
            [],
            f"{len(offenders)} shell script(s) are not executable:\n"
            + "\n".join(f"  - {p.relative_to(REPO_ROOT)}" for p in offenders),
        )

    def test_no_stray_non_executable_sh_files(self) -> None:
        # Inverse of the test above. Same fixture, same assertion, different
        # name to encode intent: "the repo's .sh file inventory contains
        # zero non-executable entries". If a new .sh file lands without
        # +x, this test fails by name rather than by accident of being
        # the same code path.
        sh_files = _collect_sh_files()
        non_executable = [p for p in sh_files if not os.access(p, os.X_OK)]
        self.assertEqual(
            non_executable,
            [],
            f"stray non-executable .sh files in repo: {[str(p.relative_to(REPO_ROOT)) for p in non_executable]}",
        )

    def test_install_sh_step0_preflight_actually_runs(self) -> None:
        # End-to-end smoke. The pre-flight in install.sh runs `bash -n`
        # on the seven scripts the wrapper knows about. If any of them
        # is missing, not executable, or has a syntax error, this test
        # surfaces the failure mode the metadata tests above cannot.
        install_sh = REPO_ROOT / "scripts" / "install.sh"
        self.assertTrue(install_sh.is_file(), f"missing {install_sh}")
        self.assertTrue(os.access(install_sh, os.X_OK), f"{install_sh} is not executable")
        result = subprocess.run(
            ["bash", str(install_sh), "--help"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"bash scripts/install.sh --help exited {result.returncode}\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}",
        )
        # The --help output should describe the linear install steps and
        # the only --canary-version flag. Pin both so a future refactor
        # that drops the description gets caught here, not in review.
        # The help text uses numbered bullets ("  1.", "  2.", ...) rather
        # than "Step N" — match the actual output, not the AGENTS.md prose.
        self.assertIn("Runs 5 steps", result.stdout, "--help output should advertise the linear step structure")
        for step_label in (
            "  1.",  # Install jcode binary
            "  2.",  # Symlink swarm/...
            "  3.",  # Symlink skills/...
            "  4.",  # Symlink AGENTS.md
            "  5.",  # Symlink scripts/ + PATH
        ):
            self.assertIn(step_label, result.stdout, f"--help output should describe {step_label.strip()} step")
        self.assertIn("--canary-version", result.stdout, "--help output should mention --canary-version")


if __name__ == "__main__":
    unittest.main()