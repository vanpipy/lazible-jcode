#!/usr/bin/env python3
"""Tests for check-swarm-consistency.py"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest


class TestCheckSwarmConsistency(unittest.TestCase):
    """TDD tests for the swarm consistency checker."""

    def setUp(self):
        """Create a temp directory for mock role files."""
        self.temp_dir = tempfile.mkdtemp()
        self.roles_dir = os.path.join(self.temp_dir, "roles")
        os.makedirs(self.roles_dir)

    def tearDown(self):
        """Remove temp directory."""
        shutil.rmtree(self.temp_dir)

    def _write_role(self, name, content):
        """Write a mock role file."""
        path = os.path.join(self.roles_dir, f"{name}.md")
        with open(path, "w") as f:
            f.write(content)
        return path

    def _run_checker(self, roles_dir=None):
        """Run check-swarm-consistency.py and return (exit_code, stdout, stderr)."""
        if roles_dir is None:
            roles_dir = self.roles_dir
        script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "check-swarm-consistency.py",
        )
        result = subprocess.run(
            [sys.executable, script, "--roles-dir", roles_dir],
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout, result.stderr

    def test_identical_contracts_pass(self):
        """Two roles with identical Output contract sections should PASS."""
        contract = """## Output contract (mandatory)

- `findings` — short prose summary of what you actually concluded.
- `evidence[]` — concrete citations: file paths, commit hashes, line numbers.
- `validation` — explicit gate results.
- `open_questions[]` — things you decided not to decide.
- `confidence: low | medium | high` — high requires a real observation.
- `what_i_did_not_check[]` — gates you did not run.

## Scope

Some scope content here.
"""
        self._write_role("role_a", f"# Role: role_a\n\n{contract}")
        self._write_role("role_b", f"# Role: role_b\n\n{contract}")

        exit_code, stdout, stderr = self._run_checker()
        self.assertEqual(exit_code, 0, f"Expected PASS (exit 0), got {exit_code}.\nstderr: {stderr}")
        self.assertIn("PASS", stdout)

    def test_missing_field_fails(self):
        """A role missing a field should FAIL."""
        contract_a = """## Output contract (mandatory)

- `findings` — short prose summary of what you actually concluded.
- `evidence[]` — concrete citations: file paths, commit hashes, line numbers.
- `validation` — explicit gate results.
- `open_questions[]` — things you decided not to decide.
- `confidence: low | medium | high` — high requires a real observation.
- `what_i_did_not_check[]` — gates you did not run.

## Scope
"""
        contract_b = """## Output contract (mandatory)

- `findings` — short prose summary of what you actually concluded.
- `evidence[]` — concrete citations: file paths, commit hashes, line numbers.
- `validation` — explicit gate results.
- `open_questions[]` — things you decided not to decide.
- `confidence: low | medium | high` — high requires a real observation.
# NOTE: what_i_did_not_check[] is intentionally missing here

## Scope
"""
        self._write_role("role_a", f"# Role: role_a\n\n{contract_a}")
        self._write_role("role_b", f"# Role: role_b\n\n{contract_b}")

        exit_code, stdout, stderr = self._run_checker()
        self.assertEqual(exit_code, 1, f"Expected FAIL (exit 1), got {exit_code}.\nstdout: {stdout}")
        self.assertIn("FAIL", stdout)
        self.assertIn("role_b", stdout)

    def test_reordered_fields_fails(self):
        """A role with reordered fields should FAIL."""
        contract_a = """## Output contract (mandatory)

- `findings` — short prose summary of what you actually concluded.
- `evidence[]` — concrete citations: file paths, commit hashes, line numbers.
- `validation` — explicit gate results.
- `open_questions[]` — things you decided not to decide.
- `confidence: low | medium | high` — high requires a real observation.
- `what_i_did_not_check[]` — gates you did not run.

## Scope
"""
        contract_b = """## Output contract (mandatory)

- `findings` — short prose summary of what you actually concluded.
- `validation` — explicit gate results.
- `evidence[]` — concrete citations: file paths, commit hashes, line numbers.
- `open_questions[]` — things you decided not to decide.
- `confidence: low | medium | high` — high requires a real observation.
- `what_i_did_not_check[]` — gates you did not run.

## Scope
"""
        self._write_role("role_a", f"# Role: role_a\n\n{contract_a}")
        self._write_role("role_b", f"# Role: role_b\n\n{contract_b}")

        exit_code, stdout, stderr = self._run_checker()
        self.assertEqual(exit_code, 1, f"Expected FAIL (exit 1), got {exit_code}.\nstdout: {stdout}")
        self.assertIn("FAIL", stdout)

    def test_wrong_field_count_fails(self):
        """A role with wrong number of fields should FAIL."""
        contract_a = """## Output contract (mandatory)

- `findings` — short prose summary of what you actually concluded.
- `evidence[]` — concrete citations: file paths, commit hashes, line numbers.
- `validation` — explicit gate results.
- `open_questions[]` — things you decided not to decide.
- `confidence: low | medium | high` — high requires a real observation.
- `what_i_did_not_check[]` — gates you did not run.

## Scope
"""
        contract_b = """## Output contract (mandatory)

- `findings` — short prose summary of what you actually concluded.
- `evidence[]` — concrete citations: file paths, commit hashes, line numbers.
- `validation` — explicit gate results.
- `open_questions[]` — things you decided not to decide.

## Scope
"""
        self._write_role("role_a", f"# Role: role_a\n\n{contract_a}")
        self._write_role("role_b", f"# Role: role_b\n\n{contract_b}")

        exit_code, stdout, stderr = self._run_checker()
        self.assertEqual(exit_code, 1, f"Expected FAIL (exit 1), got {exit_code}.\nstdout: {stdout}")
        self.assertIn("FAIL", stdout)

    def test_stdout_contains_role_name_on_fail(self):
        """FAIL output must name the offending role."""
        # good_role has 6 fields (canonical reference), bad_role has extra fields
        # Sorted: bad_role (reference, 8 fields) vs good_role (6 fields) → good_role flagged
        contract_good = """## Output contract (mandatory)

- `findings` — short prose summary.
- `evidence[]` — citations.
- `validation` — gate results.
- `open_questions[]` — gaps.
- `confidence: low | medium | high` — observation.
- `what_i_did_not_check[]` — unchecked gates.

## Scope
"""
        contract_bad = """## Output contract (mandatory)

- `findings` — short prose summary.
- `evidence[]` — citations.
- `validation` — gate results.
- `open_questions[]` — gaps.
- `confidence: low | medium | high` — observation.
- `what_i_did_not_check[]` — unchecked gates.
- `extra_field` — this field should not be here.
- `another_extra` — also not here.

## Scope
"""
        self._write_role("good_role", f"# Role: good_role\n\n{contract_good}")
        self._write_role("bad_role", f"# Role: bad_role\n\n{contract_bad}")

        exit_code, stdout, stderr = self._run_checker()
        self.assertEqual(exit_code, 1)
        self.assertIn("good_role", stdout)

    def test_missing_roles_dir_exits_one(self):
        """Missing roles directory should exit with code 1."""
        fake_dir = os.path.join(self.temp_dir, "nonexistent_roles")
        exit_code, stdout, stderr = self._run_checker(roles_dir=fake_dir)
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
