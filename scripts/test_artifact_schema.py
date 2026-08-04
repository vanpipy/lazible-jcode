#!/usr/bin/env python3
"""Tests for scripts/artifact_schema.py.

The validator is a pure function: takes a dict, returns a list of error
strings (empty if valid). These tests pin the contract.
"""

import sys
import unittest
from pathlib import Path

# Allow importing scripts/artifact_schema.py
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.artifact_schema import validate


def _minimal_artifact() -> dict:
    """A valid artifact with all required fields, no optional fields."""
    return {
        "type": "progress",
        "session_id": "session_abc123",
        "task_id": "task-xyz",
        "branch": "feat/foo_abc1234",
        "commit": "abc1234",
        "elapsed_min": 5,
        "step": "writing tests",
        "confidence": "high",
        "blockers": [],
    }


class TestArtifactSchema(unittest.TestCase):
    def test_valid_minimal_artifact(self):
        """All required fields, no optional fields, returns []."""
        errors = validate(_minimal_artifact())
        self.assertEqual(errors, [], f"unexpected errors: {errors}")

    def test_valid_full_artifact_with_dependencies(self):
        """All required + optional fields including dependencies, returns []."""
        art = _minimal_artifact()
        art.update({
            "type": "final",
            "next": None,
            "findings": ["finding 1", "finding 2"],
            "evidence": ["file.py:42", "test.py:10"],
            "edge_cases_considered": ["empty input", "null values"],
            "validation": "pytest: 23/23",
            "open_questions": [],
            "what_i_did_not_check": ["lint"],
            "dependencies": [
                {"branch": "feat/bar_def5678", "commit": "def5678", "why": "needs ID"},
            ],
            "artifact_branch": "feat/foo_abc1234",
        })
        errors = validate(art)
        self.assertEqual(errors, [], f"unexpected errors: {errors}")

    def test_missing_required_field(self):
        """Missing 'commit' returns an error mentioning 'commit'."""
        art = _minimal_artifact()
        del art["commit"]
        errors = validate(art)
        self.assertTrue(
            any("commit" in e for e in errors),
            f"expected error mentioning 'commit', got: {errors}",
        )

    def test_invalid_confidence(self):
        """confidence='foo' (not in low/medium/high) returns an error."""
        art = _minimal_artifact()
        art["confidence"] = "foo"
        errors = validate(art)
        self.assertTrue(
            any("confidence" in e for e in errors),
            f"expected error mentioning 'confidence', got: {errors}",
        )

    def test_invalid_dependency_shape(self):
        """A dependency entry missing 'why' returns an error."""
        art = _minimal_artifact()
        art["dependencies"] = [
            {"branch": "feat/x_aaa", "commit": "aaaaaaa"},  # missing 'why'
        ]
        errors = validate(art)
        self.assertTrue(
            any("dependencies" in e or "why" in e for e in errors),
            f"expected error mentioning dep/why, got: {errors}",
        )

    def test_blockers_must_be_list(self):
        """blockers must be a list; if it's a string, return an error."""
        art = _minimal_artifact()
        art["blockers"] = "not a list"
        errors = validate(art)
        self.assertTrue(
            any("blockers" in e for e in errors),
            f"expected error mentioning 'blockers', got: {errors}",
        )

    def test_invalid_type(self):
        """type='unknown' (not progress/final) returns an error."""
        art = _minimal_artifact()
        art["type"] = "unknown"
        errors = validate(art)
        self.assertTrue(
            any("type" in e for e in errors),
            f"expected error mentioning 'type', got: {errors}",
        )

    def test_multiple_errors(self):
        """Multiple invalid fields produce multiple errors."""
        art = _minimal_artifact()
        art["confidence"] = "bogus"
        art["blockers"] = "not a list"
        del art["commit"]
        errors = validate(art)
        self.assertGreaterEqual(
            len(errors), 3,
            f"expected at least 3 errors, got {len(errors)}: {errors}",
        )


if __name__ == "__main__":
    unittest.main()
