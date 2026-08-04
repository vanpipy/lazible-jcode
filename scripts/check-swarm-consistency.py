#!/usr/bin/env python3
"""
check-swarm-consistency.py

Reads all role files under swarm/roles/, extracts the ## Output contract
(mandatory) section from each, and verifies that every role carries the
canonical set of 6 CORE_FIELDS plus any role-specific required extras.

The contract split is by design: most roles share a uniform 6-field
schema, but the recoverer legitimately extends that schema with
`classification` and `suggested_action` (its domain-specific output
contract for handling dead/silent worker branches). This checker
distinguishes the **core** fields that every role MUST carry from
**role-specific** extras that only some roles carry, instead of treating
a count difference as a failure.

Rules per role:
  1. All 6 CORE_FIELDS must be present (set membership, not order).
  2. Any extras required for that specific role (e.g. recoverer must
     carry `classification` and `suggested_action`) must be present.
  3. Extras beyond the required set are allowed.

Exits 0 on PASS, 1 on FAIL.
"""

import argparse
import os
import re
import sys


SECTION_HEADER = "## Output contract (mandatory)"

# Core fields that EVERY role MUST carry. This set is the source of
# truth for "what does a complete worker artifact look like?" — the
# fields listed in §5 of swarm-prompt.md and reused in every role's
# Output contract section. Order is irrelevant; only set membership
# matters.
CORE_FIELDS = frozenset({
    "findings",
    "evidence[]",
    "validation",
    "open_questions[]",
    "confidence",
    "what_i_did_not_check[]",
})

# Role-specific required extras. A role's contract MUST carry every
# field listed here (in addition to the 6 CORE_FIELDS). Roles not
# listed here have no required extras beyond CORE_FIELDS.
ROLE_REQUIRED_EXTRAS = {
    "recoverer": frozenset({"classification", "suggested_action"}),
}

# Pattern: top-level (column 0) bullet `- `field`` with NO leading
# whitespace. This deliberately rejects indented sub-bullets (e.g. the
# `finishable` / `salvageable` / `dead` enum values inside recoverer's
# `classification` and `suggested_action` blocks).
FIELD_PATTERN = re.compile(r"^- `([^`]+)`")


def extract_contract(content):
    """Extract the Output contract section from a role file.

    Returns the text between SECTION_HEADER and the next ## heading (not
    including either boundary), or None if the section is not found.
    """
    lines = content.splitlines()
    start = None
    end = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == SECTION_HEADER:
            start = i + 1
        elif start is not None and stripped.startswith("## "):
            end = i
            break

    if start is None:
        return None
    if end is None:
        end = len(lines)

    return "\n".join(lines[start:end])


def parse_fields(section_text):
    """Extract ordered list of TOP-LEVEL field names from a contract.

    Returns a list of field name strings (the backtick-quoted identifier
    at the start of each bullet line), preserving order. Indented
    sub-bullets are intentionally skipped — they are enum values or
    explanatory sub-items, not contract fields.

    Trailing `: value` parts (e.g. `field: low | medium | high`) are
    stripped, so the parsed name is always the bare field identifier.
    """
    if not section_text:
        return []
    fields = []
    for line in section_text.splitlines():
        # IMPORTANT: match the line as-is (no strip), so that indented
        # bullets (`  - ...`) do not match the `^- ` anchor.
        m = FIELD_PATTERN.match(line)
        if m:
            raw = m.group(1)
            field_name = raw.split(":")[0].strip()
            fields.append(field_name)
    return fields


def required_extras_for(role):
    """Return the set of role-specific required extras for this role.

    Roles not in ROLE_REQUIRED_EXTRAS have no required extras beyond
    CORE_FIELDS.
    """
    return ROLE_REQUIRED_EXTRAS.get(role, frozenset())


def check_consistency(roles_dir):
    """Check all role files in roles_dir for Output contract consistency.

    Returns (exit_code, message).
    exit_code: 0 = PASS, 1 = FAIL
    """
    if not os.path.isdir(roles_dir):
        return 1, f"FAIL: roles directory not found: {roles_dir}"

    # Discover all .md role files in the directory
    role_files = sorted(f for f in os.listdir(roles_dir) if f.endswith(".md"))
    if not role_files:
        return 1, f"FAIL: no .md role files found in {roles_dir}"

    contracts = {}
    for filename in role_files:
        role = filename[:-3]  # strip .md
        path = os.path.join(roles_dir, filename)

        with open(path) as f:
            content = f.read()

        section = extract_contract(content)
        if section is None:
            return 1, (
                f"FAIL: {role}: '## Output contract (mandatory)' section not found"
            )

        fields = parse_fields(section)
        if not fields:
            return 1, f"FAIL: {role}: no fields extracted from Output contract section"

        contracts[role] = fields

    # Validate each role against CORE_FIELDS + role-specific required extras.
    role_names = sorted(contracts.keys())
    for role in role_names:
        role_fields = set(contracts[role])
        missing_core = CORE_FIELDS - role_fields
        if missing_core:
            missing_list = ", ".join(sorted(missing_core))
            return 1, (
                f"FAIL: {role}: missing core field(s): {missing_list}. "
                f"All roles MUST carry these 6 core fields: "
                f"{sorted(CORE_FIELDS)}"
            )

        required_extras = required_extras_for(role)
        missing_extras = required_extras - role_fields
        if missing_extras:
            missing_list = ", ".join(sorted(missing_extras))
            return 1, (
                f"FAIL: {role}: missing role-specific required field(s): "
                f"{missing_list}. The {role} contract MUST carry these extras: "
                f"{sorted(required_extras)}"
            )

    n = len(role_names)
    # Note: do not name role-specific extras in PASS message — they vary
    # by role and listing them in a per-role table would be busywork.
    # The FAIL messages above already name them precisely.
    extras_summary = ", ".join(
        f"{role}={len(ROLE_REQUIRED_EXTRAS.get(role, []))} extra(s)"
        for role in role_names
        if ROLE_REQUIRED_EXTRAS.get(role)
    )
    if extras_summary:
        return 0, (
            f"PASS: all {n} roles carry the 6 core Output-contract fields "
            f"(role-specific extras allowed: {extras_summary})"
        )
    return 0, f"PASS: all {n} roles carry the 6 core Output-contract fields"


def main():
    parser = argparse.ArgumentParser(
        description="Check swarm role files for Output contract consistency."
    )
    parser.add_argument(
        "--roles-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "swarm", "roles"),
        help="Path to the roles directory (default: swarm/roles/ relative to script).",
    )
    args = parser.parse_args()

    # Resolve relative path
    roles_dir = os.path.abspath(args.roles_dir)

    exit_code, message = check_consistency(roles_dir)
    print(message)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()