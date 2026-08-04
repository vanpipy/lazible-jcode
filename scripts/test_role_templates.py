#!/usr/bin/env python3
"""TDD-style structural tests for swarm/role-templates/*.example.json.

Validates that every worked sample artifact:
  * parses as valid JSON
  * contains all six required fields from the Output contract
  * declares confidence as exactly one of low / medium / high

This is a pure schema test — it does NOT check semantic quality of
the prose. That is the job of a human reviewer (or a downstream LLM
review worker) reading the artifact.

The samples are reference material for the root session when composing
spawn prompts; they are not auto-loaded by jcode.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "swarm" / "role-templates"

REQUIRED_KEYS = (
    "findings",
    "evidence",
    "validation",
    "open_questions",
    "confidence",
    "what_i_did_not_check",
)

ALLOWED_CONFIDENCE = ("low", "medium", "high")

# Roles for which we expect a worked sample. Adding a role here without an
# accompanying .example.json file is treated as a test failure.
EXPECTED_ROLES = (
    "reviewer",
    "investigator",
    "migrator",
    "test-writer",
    "doc-writer",
    "implementer",
)


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def _pass(msg: str) -> None:
    print(f"PASS: {msg}")


def test_template_files_exist() -> list[str]:
    """Every expected role must have a `.example.json` file."""
    errors: list[str] = []
    if not TEMPLATES_DIR.is_dir():
        errors.append(f"missing templates directory: {TEMPLATES_DIR}")
        return errors
    for role in EXPECTED_ROLES:
        path = TEMPLATES_DIR / f"{role}.example.json"
        if not path.is_file():
            errors.append(f"missing template file: {path}")
    return errors


def test_template_parses_and_has_keys() -> list[dict[str, object]]:
    """Each template must parse as JSON and contain the six required keys."""
    errors: list[dict[str, object]] = []
    if not TEMPLATES_DIR.is_dir():
        return errors
    for path in sorted(TEMPLATES_DIR.glob("*.example.json")):
        role = path.stem.removesuffix(".example")
        record: dict[str, object] = {"path": str(path), "errors": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            record["errors"].append(f"invalid JSON: {exc}")
            errors.append(record)
            continue
        if not isinstance(data, dict):
            record["errors"].append("top-level value must be an object")
            errors.append(record)
            continue
        for key in REQUIRED_KEYS:
            if key not in data:
                record["errors"].append(f"missing required key: {key!r}")
        errors.append(record)
    return errors


def test_confidence_is_allowed_value() -> list[dict[str, object]]:
    """Each template's confidence field must be one of {low, medium, high}."""
    errors: list[dict[str, object]] = []
    if not TEMPLATES_DIR.is_dir():
        return errors
    for path in sorted(TEMPLATES_DIR.glob("*.example.json")):
        role = path.stem.removesuffix(".example")
        record: dict[str, object] = {"path": str(path), "errors": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            record["errors"].append(f"invalid JSON: {exc}")
            errors.append(record)
            continue
        if not isinstance(data, dict):
            continue
        conf = data.get("confidence")
        if conf not in ALLOWED_CONFIDENCE:
            record["errors"].append(
                f"confidence must be one of {ALLOWED_CONFIDENCE}, got {conf!r}"
            )
        errors.append(record)
    return errors


def main() -> int:
    """Run all sub-tests and return a process exit code (0 = pass)."""
    found_errors = False

    existence_errors = test_template_files_exist()
    for err in existence_errors:
        _fail(err)
    if existence_errors:
        found_errors = True
    else:
        _pass(f"all {len(EXPECTED_ROLES)} expected template files exist")

    key_errors = test_template_parses_and_has_keys()
    for record in key_errors:
        for err in record["errors"]:  # type: ignore[union-attr]
            _fail(f"{record['path']}: {err}")
    if any(r["errors"] for r in key_errors):
        found_errors = True
    elif key_errors:
        _pass(f"all {len(key_errors)} templates parse and contain required keys")

    conf_errors = test_confidence_is_allowed_value()
    for record in conf_errors:
        for err in record["errors"]:  # type: ignore[union-attr]
            _fail(f"{record['path']}: {err}")
    if any(r["errors"] for r in conf_errors):
        found_errors = True
    elif conf_errors:
        _pass(f"all {len(conf_errors)} templates have valid confidence value")

    if found_errors:
        print("\nFAIL: role-templates schema tests failed", file=sys.stderr)
        return 1
    print("\nOK: all role-templates schema tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
