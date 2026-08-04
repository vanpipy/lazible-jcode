#!/usr/bin/env python3
"""Tests for scripts/swarm-state-monitor.py."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


_MONITOR_PATH = Path(__file__).resolve().parent / "swarm-state-monitor.py"
_SPEC = importlib.util.spec_from_file_location("swarm_state_monitor", _MONITOR_PATH)
monitor = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules["swarm_state_monitor"] = monitor
_SPEC.loader.exec_module(monitor)


class TestClassify(unittest.TestCase):
    """Classification boundaries remain stable while tick filtering changes."""

    def setUp(self) -> None:
        self.thresholds = mock.patch.dict(
            monitor.THRESHOLDS,
            {"quiet_min": 5, "silent_min": 15, "dead_min": 30},
            clear=True,
        )
        self.thresholds.start()
        self.addCleanup(self.thresholds.stop)

    def _classify(self, artifact_type: str | None, age_min: int) -> str:
        state = monitor.BranchState(
            branch="feat/example_abcdef0",
            has_commits=True,
            artifact_type=artifact_type,
        )
        monitor.classify(state, age_min)
        assert state.classification is not None
        return state.classification

    def test_final_artifact_is_healthy_inside_handoff_pending_window(self) -> None:
        # A `final` commit inside the handoff-pending window (default 1 min)
        # is still `healthy`: the worker may be in the middle of calling
        # `complete_node` and we tolerate the gap.
        self.assertEqual(self._classify("final", 1), "healthy")

    def test_final_artifact_moves_from_healthy_to_quiet_to_silent(self) -> None:
        # Past the handoff-pending window, classification becomes `quiet` and
        # root must integrate from the commit (action = integrate-now).
        cases = (
            (2, "quiet"),
            (5, "quiet"),
            (15, "quiet"),
            (16, "silent"),
        )
        for age_min, expected in cases:
            with self.subTest(age_min=age_min):
                self.assertEqual(self._classify("final", age_min), expected)

    def test_progress_artifact_crosses_all_age_classes(self) -> None:
        cases = (
            (4, "progressing"),
            (5, "quiet"),
            (14, "quiet"),
            (15, "silent"),
            (29, "silent"),
            (30, "dead"),
        )
        for age_min, expected in cases:
            with self.subTest(age_min=age_min):
                self.assertEqual(self._classify("progress", age_min), expected)

    def test_missing_commits_are_dead(self) -> None:
        state = monitor.BranchState(branch="feat/empty_abcdef0")
        monitor.classify(state, None)
        self.assertEqual(state.classification, "dead")
        self.assertEqual(state.rationale, "no commits on branch")
        self.assertEqual(state.recommended_action, "recover")


class TestRecommendedAction(unittest.TestCase):
    """Regression tests for the silent-stuck failure mode.

    The failure: a worker commits a `final` artifact (which IS the durable
    half of the handoff) but never calls `complete_node` (or calls
    `report status: ready` which doesn't wake root). Without the
    `recommended_action` field, root treated the resulting `healthy`/
    `quiet` classification as "nothing to do" and missed the integrate
    window entirely.

    These tests pin the new behavior: any `final` commit past the
    handoff-pending window MUST surface `recommended_action =
    "integrate-now"`, regardless of classification. This is the contract
    root-tick.sh relies on.
    """

    def _classify(self, artifact_type, age_min):
        state = monitor.BranchState(
            branch="feat/x_abcdef0",
            has_commits=True,
            artifact_type=artifact_type,
        )
        monitor.classify(state, age_min)
        return state

    def test_final_past_handoff_window_action_is_integrate_now(self) -> None:
        """The silent-stuck repro: final commit, no handoff, age = 6m.

        Before the fix: classification="quiet", no action field, root had
        no signal to integrate. Result: branch rotted in the swarm for
        hours.
        After the fix: classification="quiet", recommended_action=
        "integrate-now" — root MUST integrate from the commit even if
        `complete_node` never arrived.
        """
        state = self._classify("final", 6)
        self.assertEqual(state.classification, "quiet")
        self.assertEqual(state.recommended_action, "integrate-now")
        # Rationale must mention the missing handoff so root understands
        # why integrate-now is required.
        self.assertIn("no handoff", state.rationale)

    def test_final_inside_handoff_pending_window_action_is_observe(self) -> None:
        """Within handoff-pending window (default 1 min), tolerate gap."""
        state = self._classify("final", 0)
        self.assertEqual(state.classification, "healthy")
        self.assertEqual(state.recommended_action, "observe")

    def test_final_past_silent_sla_action_still_integrate_now(self) -> None:
        """Even at silent SLA, action is still integrate-now.

        The commit is durable. If worker died between commit and
        complete_node, recoverer would be redundant — integrate first,
        then optionally spawn a recoverer to investigate the missing
        handoff if other branches show same pattern.
        """
        state = self._classify("final", 20)
        self.assertEqual(state.classification, "silent")
        self.assertEqual(state.recommended_action, "integrate-now")

    def test_progress_silent_sla_action_is_recover(self) -> None:
        """progress + past silent SLA = recoverer (worker may be dead)."""
        state = self._classify("progress", 20)
        self.assertEqual(state.classification, "silent")
        self.assertEqual(state.recommended_action, "recover")

    def test_progress_quiet_window_action_is_dm_heartbeat_reminder(self) -> None:
        """progress + quiet window = cheap ping (worker probably fine)."""
        state = self._classify("progress", 10)
        self.assertEqual(state.classification, "quiet")
        self.assertEqual(state.recommended_action, "dm-heartbeat-reminder")

    def test_no_commits_action_is_recover(self) -> None:
        """Empty branch = recoverer spawn (or worker never started)."""
        state = monitor.BranchState(branch="feat/empty_abcdef0")
        monitor.classify(state, None)
        self.assertEqual(state.recommended_action, "recover")

    def test_handoff_pending_window_env_override(self) -> None:
        """HANDOFF_PENDING_MIN env var widens the observe window."""
        state = self._classify("final", 5)
        # Default handoff_pending_window=1 → 5m is past it → integrate-now
        self.assertEqual(state.recommended_action, "integrate-now")

        os.environ["HANDOFF_PENDING_MIN"] = "10"
        try:
            # With override, 5m is inside the window → observe
            state2 = self._classify("final", 5)
            self.assertEqual(state2.recommended_action, "observe")
        finally:
            del os.environ["HANDOFF_PENDING_MIN"]


class TestArtifactParsing(unittest.TestCase):
    def test_no_artifact_block_returns_empty_dict(self) -> None:
        self.assertEqual(monitor._parse_artifact("ordinary commit body"), {})

    def test_malformed_json_returns_empty_dict(self) -> None:
        body = '''message\n\n```json artifact
{"type": "progress",}
```\n'''
        self.assertEqual(monitor._parse_artifact(body), {})

    def test_missing_type_field_remains_untyped(self) -> None:
        body = '''message\n\n```json artifact
{"step": "working", "confidence": "medium"}
```\n'''
        artifact = monitor._parse_artifact(body)
        self.assertEqual(artifact["step"], "working")
        self.assertNotIn("type", artifact)


class TestTickAgeFilter(unittest.TestCase):
    def _state(
        self,
        branch: str,
        age_min: int,
        artifact_type: str,
        classification: str,
    ) -> object:
        state = monitor.BranchState(
            branch=branch,
            has_commits=True,
            latest_commit="a" * 40,
            latest_age_min=age_min,
            artifact_type=artifact_type,
            artifact_confidence="high",
        )
        # Run classify() so both classification AND recommended_action are
        # populated. The tick exit-code now depends on recommended_action,
        # not just classification.
        monitor.classify(state, age_min)
        # Some tests want to override the classification (e.g. assert the
        # old text-based exit code path); allow it as a final write.
        if classification is not None:
            state.classification = classification
        state.rationale = f"{artifact_type} commit {age_min}m ago"
        return state

    def _run_tick(
        self,
        states: dict[str, object],
        *,
        since_hours: float = 24,
        include_stale: bool = False,
    ) -> tuple[int, str]:
        with mock.patch.object(
            monitor, "_list_worker_branches", return_value=list(states)
        ), mock.patch.object(
            monitor,
            "collect_state",
            side_effect=lambda branch, _cwd: states[branch],
        ):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = monitor.cmd_tick(
                    Path("."),
                    since_hours=since_hours,
                    include_stale=include_stale,
                )
        return exit_code, stdout.getvalue()

    def test_since_filters_stale_progress_and_final_branches(self) -> None:
        states = {
            "feat/recent_abcdef0": self._state(
                "feat/recent_abcdef0", 30, "progress", "progressing"
            ),
            "feat/old-progress_abcdef0": self._state(
                "feat/old-progress_abcdef0", 61, "progress", "dead"
            ),
            "feat/old-final_abcdef0": self._state(
                "feat/old-final_abcdef0", 120, "final", "silent"
            ),
        }

        exit_code, output = self._run_tick(states, since_hours=1)

        # The recent branch is at the dead SLA boundary (30m, action=recover),
        # so exit 2 — the stale ones are filtered, but the visible one still
        # needs root attention. The point of the test is the *visibility*
        # filter, not the exit code.
        self.assertEqual(exit_code, 2)
        self.assertIn("feat/recent_abcdef0", output)
        self.assertNotIn("feat/old-progress_abcdef0", output)
        self.assertNotIn("feat/old-final_abcdef0", output)
        # Case (c): some visible + some hidden — unified wording with case (b).
        self.assertIn(
            "(2 worker branch(es) hidden; pass --include-stale to show all)",
            output,
        )
        # The old "stale branches hidden" wording is no longer used.
        self.assertNotIn("stale branches hidden", output)
        self.assertIn("within --since=1h filter", output)

    def test_include_stale_bypasses_age_filter(self) -> None:
        states = {
            "feat/recent_abcdef0": self._state(
                "feat/recent_abcdef0", 30, "progress", "progressing"
            ),
            "feat/old-final_abcdef0": self._state(
                "feat/old-final_abcdef0", 120, "final", "silent"
            ),
        }

        exit_code, output = self._run_tick(
            states,
            since_hours=1,
            include_stale=True,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("feat/recent_abcdef0", output)
        self.assertIn("feat/old-final_abcdef0", output)
        self.assertNotIn("stale branches hidden", output)
        self.assertIn("--include-stale enabled", output)

    def test_all_filtered_uses_single_clean_message(self) -> None:
        """When --since hides every branch, tick must NOT print the
        misleading '(no worker branches found)' header (which would imply
        there are no branches at all). It should print a single line
        explaining all are filtered, and not print the table or json.
        """
        states = {
            "feat/old1_abcdef0": self._state(
                "feat/old1_abcdef0", 120, "progress", "dead"
            ),
            "feat/old2_abcdef0": self._state(
                "feat/old2_abcdef0", 200, "final", "silent"
            ),
            "feat/old3_abcdef0": self._state(
                "feat/old3_abcdef0", 90, "progress", "dead"
            ),
        }

        exit_code, output = self._run_tick(states, since_hours=1)

        self.assertEqual(exit_code, 0)
        # Should NOT contain the misleading header.
        self.assertNotIn("(no worker branches found)", output)
        # Should contain the all-hidden explanation.
        self.assertIn(
            "(3 worker branch(es) hidden by --since=1h filter; "
            "pass --include-stale to show all)",
            output,
        )
        # Should NOT also print the per-row "(N stale branches hidden; ...)"
        # duplicate message — cmd_tick returns early in this case.
        self.assertNotIn("(3 stale branches hidden;", output)
        # The branches themselves should not appear (they are filtered).
        self.assertNotIn("feat/old1_abcdef0", output)
        self.assertNotIn("feat/old2_abcdef0", output)
        self.assertNotIn("feat/old3_abcdef0", output)


class TestTickCLI(unittest.TestCase):
    def _run_main(self, argv: list[str]) -> mock.Mock:
        with mock.patch.object(sys, "argv", [str(_MONITOR_PATH), *argv]), mock.patch.object(
            monitor, "_ensure_git"
        ), mock.patch.object(monitor, "cmd_tick", return_value=0) as cmd_tick:
            self.assertEqual(monitor.main(), 0)
        return cmd_tick

    def test_tick_defaults_to_24_hours(self) -> None:
        cmd_tick = self._run_main(["tick"])
        cmd_tick.assert_called_once_with(
            Path(".").resolve(),
            since_hours=24,
            include_stale=False,
        )

    def test_tick_accepts_since_and_include_stale(self) -> None:
        cmd_tick = self._run_main(["tick", "--since=1", "--include-stale"])
        cmd_tick.assert_called_once_with(
            Path(".").resolve(),
            since_hours=1,
            include_stale=True,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
