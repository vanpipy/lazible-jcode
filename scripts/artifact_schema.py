"""Typed artifact schema + validator.

The schema is the contract every worker commit's artifact JSON block must
satisfy. Validation is non-strict (returns list of errors instead of
raising) so root can use it on partially-filled artifacts.

Required fields:
- type: 'progress' | 'final'
- session_id: str
- task_id: str
- branch: str
- commit: str (hex SHA, 7-40 chars)
- elapsed_min: int (>= 0)
- step: str
- confidence: 'low' | 'medium' | 'high'
- blockers: list[str]

Optional fields:
- next: str | null
- findings: list[str]
- evidence: list[str | dict]
- edge_cases_considered: list[str]
- validation: str
- open_questions: list[str]
- what_i_did_not_check: list[str]
- dependencies: list[dict] with {branch, commit, why} all strings
- artifact_branch: str (set by root on integration; worker may leave blank)

Returns: list of error strings (empty if valid).
"""

from __future__ import annotations

import re
from typing import Any

_REQUIRED_FIELDS = {
    "type",
    "session_id",
    "task_id",
    "branch",
    "commit",
    "elapsed_min",
    "step",
    "confidence",
    "blockers",
}

_VALID_TYPES = {"progress", "final"}
_VALID_CONFIDENCE = {"low", "medium", "high"}
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


def validate(artifact: Any) -> list[str]:
    """Validate an artifact dict. Returns a list of error strings.

    Empty list means the artifact is valid. Never raises: callers can
    pass malformed input and still get a usable list of problems.
    """
    errors: list[str] = []

    if not isinstance(artifact, dict):
        return [f"artifact must be a dict, got {type(artifact).__name__}"]

    # Required fields presence.
    for field in _REQUIRED_FIELDS:
        if field not in artifact:
            errors.append(f"missing required field: {field!r}")

    # type: progress | final
    if "type" in artifact and artifact["type"] not in _VALID_TYPES:
        errors.append(
            f"type must be one of {sorted(_VALID_TYPES)}, "
            f"got {artifact['type']!r}"
        )

    # confidence: low | medium | high
    if "confidence" in artifact and artifact["confidence"] not in _VALID_CONFIDENCE:
        errors.append(
            f"confidence must be one of {sorted(_VALID_CONFIDENCE)}, "
            f"got {artifact['confidence']!r}"
        )

    # commit: hex SHA, 7-40 chars
    if "commit" in artifact:
        c = artifact["commit"]
        if not isinstance(c, str) or not _SHA_RE.match(c):
            errors.append(
                f"commit must be a hex SHA (7-40 chars), got {c!r}"
            )

    # elapsed_min: int >= 0
    if "elapsed_min" in artifact:
        e = artifact["elapsed_min"]
        if not isinstance(e, int) or isinstance(e, bool) or e < 0:
            errors.append(
                f"elapsed_min must be a non-negative int, got {e!r}"
            )

    # blockers: list[str]
    if "blockers" in artifact:
        b = artifact["blockers"]
        if not isinstance(b, list):
            errors.append(f"blockers must be a list, got {type(b).__name__}")
        else:
            for i, item in enumerate(b):
                if not isinstance(item, str):
                    errors.append(
                        f"blockers[{i}] must be a string, got {type(item).__name__}"
                    )

    # dependencies: list[dict] with {branch, commit, why} all strings
    if "dependencies" in artifact:
        d = artifact["dependencies"]
        if not isinstance(d, list):
            errors.append(
                f"dependencies must be a list, got {type(d).__name__}"
            )
        else:
            for i, dep in enumerate(d):
                if not isinstance(dep, dict):
                    errors.append(
                        f"dependencies[{i}] must be a dict, got {type(dep).__name__}"
                    )
                    continue
                for key in ("branch", "commit", "why"):
                    if key not in dep:
                        errors.append(
                            f"dependencies[{i}] missing required key: {key!r}"
                        )
                    elif not isinstance(dep[key], str):
                        errors.append(
                            f"dependencies[{i}].{key} must be a string, "
                            f"got {type(dep[key]).__name__}"
                        )

    # Optional type checks (lighter).
    for field in ("session_id", "task_id", "branch", "step"):
        if field in artifact and not isinstance(artifact[field], str):
            errors.append(
                f"{field} must be a string, got {type(artifact[field]).__name__}"
            )

    return errors
