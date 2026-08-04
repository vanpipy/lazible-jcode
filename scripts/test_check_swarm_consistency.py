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

    def test_missing_core_field_fails(self):
        """A role missing one of the 6 core fields should FAIL."""
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

    def test_missing_roles_dir_exits_one(self):
        """Missing roles directory should exit with code 1."""
        fake_dir = os.path.join(self.temp_dir, "nonexistent_roles")
        exit_code, stdout, stderr = self._run_checker(roles_dir=fake_dir)
        self.assertEqual(exit_code, 1)

    # --- TDD red/green tests for the core-fields-vs-extras split ---
    # The recoverer legitimately has 14 fields (6 core + classification,
    # suggested_action, plus indented sub-bullets under each). The old
    # checker treated this as a count mismatch; the new model accepts
    # role-specific extras and only enforces the 6 core fields.

    def test_recoverer_with_role_specific_extras_passes(self):
        """The real recoverer.md has 6 core fields plus classification and
        suggested_action role-specific extras. The new model must PASS."""
        # Use the real repo's roles directory to exercise the recoverer
        # contract verbatim (no mocking needed; the real file is the spec).
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        )
        real_roles_dir = os.path.join(repo_root, "swarm", "roles")

        exit_code, stdout, stderr = self._run_checker(roles_dir=real_roles_dir)
        self.assertEqual(
            exit_code,
            0,
            f"Expected PASS against real roles dir, got {exit_code}.\n"
            f"stdout: {stdout}\nstderr: {stderr}",
        )
        self.assertIn("PASS", stdout)

    def test_implementer_missing_core_field_fails(self):
        """A mock implementer missing one of the 6 core fields must FAIL."""
        core_except_what = """## Output contract (mandatory)

- `findings` — short prose summary.
- `evidence[]` — citations.
- `validation` — gate results.
- `open_questions[]` — gaps.
- `confidence: low | medium | high` — observation.
# NOTE: what_i_did_not_check[] deliberately omitted

## Scope
"""
        full_core = """## Output contract (mandatory)

- `findings` — short prose summary.
- `evidence[]` — citations.
- `validation` — gate results.
- `open_questions[]` — gaps.
- `confidence: low | medium | high` — observation.
- `what_i_did_not_check[]` — unchecked gates.

## Scope
"""
        self._write_role("implementer", f"# Role: implementer\n\n{core_except_what}")
        self._write_role("reviewer", f"# Role: reviewer\n\n{full_core}")

        exit_code, stdout, stderr = self._run_checker()
        self.assertEqual(
            exit_code,
            1,
            f"Expected FAIL when implementer omits a core field, got {exit_code}."
            f"\nstdout: {stdout}",
        )
        self.assertIn("implementer", stdout)

    def test_all_seven_roles_consistent_core_fields(self):
        """All 7 real roles (doc-writer, implementer, investigator, migrator,
        recoverer, reviewer, test-writer) carry the 6 core fields."""
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        )
        real_roles_dir = os.path.join(repo_root, "swarm", "roles")
        # Sanity: confirm there are exactly 7 .md files there.
        md_files = [f for f in os.listdir(real_roles_dir) if f.endswith(".md")]
        self.assertEqual(
            len(md_files),
            7,
            f"Expected 7 role files, found {len(md_files)}: {md_files}",
        )

        exit_code, stdout, stderr = self._run_checker(roles_dir=real_roles_dir)
        self.assertEqual(
            exit_code,
            0,
            f"Expected PASS for all 7 real roles, got {exit_code}."
            f"\nstdout: {stdout}\nstderr: {stderr}",
        )
        self.assertIn("7", stdout)  # confirm message mentions role count

    def test_recoverer_requires_classification_and_suggested_action(self):
        """A mock recoverer missing classification or suggested_action
        must FAIL (these are the recoverer-specific required extras)."""
        recoverer_no_extras = """## Output contract (mandatory)

- `findings` — short prose summary.
- `evidence[]` — citations.
- `validation` — gate results.
- `open_questions[]` — gaps.
- `confidence: low | medium | high` — observation.
- `what_i_did_not_check[]` — unchecked gates.

## Scope
"""
        full_core = """## Output contract (mandatory)

- `findings` — short prose summary.
- `evidence[]` — citations.
- `validation` — gate results.
- `open_questions[]` — gaps.
- `confidence: low | medium | high` — observation.
- `what_i_did_not_check[]` — unchecked gates.

## Scope
"""
        self._write_role("recoverer", f"# Role: recoverer\n\n{recoverer_no_extras}")
        self._write_role("implementer", f"# Role: implementer\n\n{full_core}")

        exit_code, stdout, stderr = self._run_checker()
        self.assertEqual(
            exit_code,
            1,
            f"Expected FAIL for recoverer without classification/suggested_action, "
            f"got {exit_code}.\nstdout: {stdout}",
        )
        self.assertIn("recoverer", stdout)

    def test_reordered_core_fields_passes(self):
        """Reordering the 6 core fields across roles must PASS
        (the new model checks set membership, not order)."""
        canonical = """## Output contract (mandatory)

- `findings` — short prose summary.
- `evidence[]` — citations.
- `validation` — gate results.
- `open_questions[]` — gaps.
- `confidence: low | medium | high` — observation.
- `what_i_did_not_check[]` — unchecked gates.

## Scope
"""
        reordered = """## Output contract (mandatory)

- `what_i_did_not_check[]` — unchecked gates.
- `confidence: low | medium | high` — observation.
- `open_questions[]` — gaps.
- `validation` — gate results.
- `evidence[]` — citations.
- `findings` — short prose summary.

## Scope
"""
        self._write_role("role_a", f"# Role: role_a\n\n{canonical}")
        self._write_role("role_b", f"# Role: role_b\n\n{reordered}")

        exit_code, stdout, stderr = self._run_checker()
        self.assertEqual(
            exit_code,
            0,
            f"Expected PASS for reordered core fields, got {exit_code}."
            f"\nstdout: {stdout}",
        )
        self.assertIn("PASS", stdout)

    def test_role_specific_extras_allowed(self):
        """A role with extra fields beyond the 6 core fields must PASS
        (extras are allowed; the only requirement is the core set is present)."""
        core_only = """## Output contract (mandatory)

- `findings` — short prose summary.
- `evidence[]` — citations.
- `validation` — gate results.
- `open_questions[]` — gaps.
- `confidence: low | medium | high` — observation.
- `what_i_did_not_check[]` — unchecked gates.

## Scope
"""
        core_plus_extra = """## Output contract (mandatory)

- `findings` — short prose summary.
- `evidence[]` — citations.
- `validation` — gate results.
- `open_questions[]` — gaps.
- `confidence: low | medium | high` — observation.
- `what_i_did_not_check[]` — unchecked gates.
- `classification` — recoverer-specific extra (allowed).

## Scope
"""
        self._write_role("implementer", f"# Role: implementer\n\n{core_only}")
        self._write_role("reviewer", f"# Role: reviewer\n\n{core_plus_extra}")

        exit_code, stdout, stderr = self._run_checker()
        self.assertEqual(
            exit_code,
            0,
            f"Expected PASS when extras are present (extras are allowed), "
            f"got {exit_code}.\nstdout: {stdout}",
        )


if __name__ == "__main__":
    unittest.main()
