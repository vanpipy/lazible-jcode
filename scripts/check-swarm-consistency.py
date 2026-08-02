#!/usr/bin/env python3
"""
check-swarm-consistency.py

Reads all 6 role files under swarm/roles/, extracts the ## Output contract
(mandatory) section from each, and compares field count, names, and ordering.
Exits 0 on PASS, 1 on FAIL.
"""

import argparse
import os
import re
import sys


SECTION_HEADER = "## Output contract (mandatory)"
# Pattern: - `field_name` or - `field_name: value` at the start of a line
FIELD_PATTERN = re.compile(r"^- `([^`]+)`")


def extract_contract(content):
    """Extract the Output contract section from a role file.

    Returns the text between SECTION_HEADER and the next ##  heading (not
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
    """Extract ordered list of field names from a contract section.

    Returns a list of field name strings (the backtick-quoted identifier at
    the start of each bullet line), preserving order.
    """
    if not section_text:
        return []
    fields = []
    for line in section_text.splitlines():
        stripped = line.strip()
        m = FIELD_PATTERN.match(stripped)
        if m:
            # Strip trailing `: value` part if present (e.g. `field: type`)
            raw = m.group(1)
            field_name = raw.split(":")[0].strip()
            fields.append(field_name)
    return fields


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
            return 1, f"FAIL: {role}: '## Output contract (mandatory)' section not found"

        fields = parse_fields(section)
        if not fields:
            return 1, f"FAIL: {role}: no fields extracted from Output contract section"

        contracts[role] = fields

    # Use the first role as the canonical reference
    role_names = sorted(contracts.keys())
    reference_role = role_names[0]
    reference_fields = contracts[reference_role]

    for role in role_names[1:]:
        role_fields = contracts[role]

        # Check field count
        if len(role_fields) != len(reference_fields):
            return 1, (
                f"FAIL: {role}: field count mismatch "
                f"(has {len(role_fields)}, expected {len(reference_fields)}): "
                f"{role_fields}"
            )

        # Check field names and ordering
        if role_fields != reference_fields:
            # Find first differing index for a helpful message
            for i, (ref_f, cur_f) in enumerate(zip(reference_fields, role_fields)):
                if ref_f != cur_f:
                    return 1, (
                        f"FAIL: {role}: field ordering mismatch at position {i} "
                        f"(has '{cur_f}', expected '{ref_f}')"
                    )
            # If we get here, counts differ (already handled above) but
            # technically different sets
            return 1, (
                f"FAIL: {role}: field names mismatch "
                f"(has {role_fields}, expected {reference_fields})"
            )

    n = len(role_names)
    return 0, f"PASS: all {n} roles carry identical Output contract"


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
