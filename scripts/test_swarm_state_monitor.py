#!/usr/bin/env python3
"""Tests for scripts/swarm-state-monitor.py."""

from __future__ import annotations

import contextlib
import importlib.util
import io
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

    def test_final_artifact_is_healthy_inside_quiet_window(self) -> None:
        self.assertEqual(self._classify("final", 5), "healthy")

    def test_final_artifact_moves_from_quiet_to_silent(self) -> None:
        cases = ((6, "quiet"), (15, "quiet"), (16, "silent"))
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
        return monitor.BranchState(
            branch=branch,
            has_commits=True,
            latest_commit="a" * 40,
            latest_age_min=age_min,
            artifact_type=artifact_type,
            artifact_confidence="high",
            classification=classification,
            rationale=f"{artifact_type} commit {age_min}m ago",
        )

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

        self.assertEqual(exit_code, 0)
        self.assertIn("feat/recent_abcdef0", output)
        self.assertNotIn("feat/old-progress_abcdef0", output)
        self.assertNotIn("feat/old-final_abcdef0", output)
        self.assertIn(
            "(2 stale branches hidden; pass --include-stale to show all)",
            output,
        )
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
