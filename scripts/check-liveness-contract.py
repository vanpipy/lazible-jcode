#!/usr/bin/env python3
"""
check-liveness-contract.py

Validates the structural and semantic completeness of the swarm's
liveness contract across role files, the swarm-prompt, the
prompt-overlay, and the HEARTBEAT doc.

Exits 0 on PASS, 1 on FAIL.

What it checks:

  1. Every role file has a "## Liveness contract (worker-driven)"
     section.
  2. Every role's Liveness section contains the required rule markers
     (heartbeat / stuck / exit right / reminder-loop / completion /
     cross-swarm). This catches silent regressions where a future
     edit drops a rule.
  3. swarm/swarm-prompt.md §12 root obligations carries the
     "mandatory passive inspection" rule with the "decision point"
     keyword — the rule added to plug the silent-stuck gap.
  4. swarm/prompt-overlay.md §1 promotes passive inspection from
     "recommended" to "mandatory" — the L1 doc edit.
  5. docs/HEARTBEAT.md has the "Cross-swarm handoff gap" section and
     the "Completion = commit AND `complete_node`" subsection — the
     L1 docs that codify the 2026-08 silent-stuck incident.

This is a pure structural / keyword test. It does not evaluate
semantic correctness of the prose. That is the job of a human reviewer
or downstream LLM review worker.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROLES_DIR = ROOT / "swarm" / "roles"
SWARM_PROMPT = ROOT / "swarm" / "swarm-prompt.md"
PROMPT_OVERLAY = ROOT / "swarm" / "prompt-overlay.md"
HEARTBEAT = ROOT / "docs" / "HEARTBEAT.md"

# Section header for the worker liveness contract.
LIVENESS_SECTION = "## Liveness contract (worker-driven)"

# Required keyword markers that MUST appear in every role's Liveness
# section. Each is a regex; the section is searched for any line
# matching at least one pattern per marker.
REQUIRED_RULES = {
    "heartbeat": [
        r"Heartbeat.*5 min",
        r"heartbeat.*5[\s\-]min",
    ],
    "stuck": [
        r"Stuck.*self.?escalation",
        r"stuck.*self.?escalation",
    ],
    "exit_right": [
        r"Exit right",
        r"exit right",
    ],
    "reminder_loop": [
        r"Reminder.?loop",
        r"reminder.?loop",
    ],
    # L2 additions:
    "completion": [
        r"Completion\s*=\s*\S+\s+AND\s+`?complete_node`?",
    ],
    "cross_swarm": [
        r"Cross.?swarm",
        r"cross.?swarm",
    ],
}

# Roles that are expected to carry the Liveness contract.
EXPECTED_ROLES = (
    "implementer",
    "reviewer",
    "investigator",
    "migrator",
    "test-writer",
    "doc-writer",
    "recoverer",
)


# ---------------------------------------------------------------------------
# Smart Postman L1 / L2 markers (added 2026-08 after silent-stuck incident)
# ---------------------------------------------------------------------------


#: Mandatory keyword markers in swarm-prompt.md §13 "Smart Postman".
SMART_POSTMAN_REQUIRED_MARKERS = (
    "Smart Postman",
    "swarm-state-monitor.py",
    "tick",
    "recoverer",
    "inspection-confirmation",
    "silent",
    "dead",
)

#: Mandatory keyword markers in prompt-overlay.md §1 Smart Postman section.
PROMPT_OVERLAY_SMART_POSTMAN_MARKERS = (
    "Smart Postman",
    "swarm-state-monitor.py",
    "tick",
    "recoverer",
    "ambient",
    "silent",
    "dead",
)


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def _pass(msg: str) -> None:
    print(f"PASS: {msg}")


def extract_section(content: str, header: str, end_re: str = r"^## ") -> str | None:
    """Extract the text between `header` and the next `## ` heading."""
    lines = content.splitlines()
    start = None
    end = None
    for i, line in enumerate(lines):
        if line.strip() == header:
            start = i + 1
        elif start is not None and re.match(end_re, line.strip()):
            end = i
            break
    if start is None:
        return None
    if end is None:
        end = len(lines)
    return "\n".join(lines[start:end])


def check_rule(section: str, rule: str, patterns: list[str]) -> bool:
    """Return True iff at least one pattern matches in section."""
    for pat in patterns:
        if re.search(pat, section, flags=re.IGNORECASE | re.MULTILINE):
            return True
    return False


def check_roles(errors: list[str]) -> None:
    if not ROLES_DIR.is_dir():
        errors.append(f"roles directory not found: {ROLES_DIR}")
        return
    role_files = sorted(p for p in ROLES_DIR.iterdir() if p.suffix == ".md")
    found_roles = {p.stem for p in role_files}

    for expected in EXPECTED_ROLES:
        if expected not in found_roles:
            errors.append(f"missing role file: {expected}.md")

    for role_path in role_files:
        role = role_path.stem
        content = role_path.read_text()
        section = extract_section(content, LIVENESS_SECTION)
        if section is None:
            errors.append(f"{role}: missing '{LIVENESS_SECTION}' section")
            continue
        for rule_name, patterns in REQUIRED_RULES.items():
            if not check_rule(section, rule_name, patterns):
                errors.append(
                    f"{role}: Liveness section missing required rule "
                    f"'{rule_name}' (no pattern matched: {patterns})"
                )


def check_complete_node_mandatory(errors: list[str]) -> None:
    """implementer.md must mandate `complete_node` (NOT `report`) for final handoff.

    2026-08 silent-stuck incident: worker called `report` instead of
    `complete_node`, root never received a wake. The lenient "or report"
    wording in implementer.md must be replaced with mandatory complete_node.
    """
    implementer = ROLES_DIR / "implementer.md"
    if not implementer.is_file():
        return
    content = implementer.read_text()
    section = extract_section(content, LIVENESS_SECTION)
    if section is None:
        return  # already reported by check_roles

    # MUST have explicit mandatory/ONLY framing for complete_node.
    if not re.search(
        r"complete_node.{0,120}\b(mandatory|only handoff|exclusively)\b|"
        r"\b(mandatory|only handoff|exclusively)\b.{0,120}complete_node",
        section,
        re.IGNORECASE | re.DOTALL,
    ):
        errors.append(
            "implementer.md: Liveness section missing mandatory "
            "'complete_node' framing — must contain 'complete_node ONLY' "
            "or 'complete_node mandatory' (L2 hardening after 2026-08 "
            "silent-stuck)"
        )

    # MUST NOT contain the lenient "complete_node ... or report" wording.
    if re.search(
        r"\bcomplete_node\b.{0,200}\bor\s+`?report`?|"
        r"`?report`?[^.\n]{0,60}\bcomplete_node\b[^.\n]{0,40}\b(wake|handoff)\b",
        section,
        re.IGNORECASE | re.DOTALL,
    ):
        errors.append(
            "implementer.md: Liveness section still allows 'report' as "
            "alternative to 'complete_node' — must be complete_node ONLY "
            "for final handoff (L2 hardening after 2026-08 silent-stuck)"
        )


def check_swarm_prompt(errors: list[str]) -> None:
    if not SWARM_PROMPT.is_file():
        errors.append(f"swarm-prompt.md not found: {SWARM_PROMPT}")
        return
    content = SWARM_PROMPT.read_text()

    # §12 root obligations MUST carry the mandatory passive inspection
    # rule. We look for a paragraph that contains both "passive
    # inspection" and "decision point" inside the root obligations
    # region.
    root_obligations = extract_section(
        content,
        "### Root obligations (responsiveness, soft)",
    )
    if root_obligations is None:
        errors.append(
            "swarm-prompt.md: '### Root obligations (responsiveness, "
            "soft)' section missing — §12 contract cannot be enforced"
        )
        return

    # Mandatory passive inspection rule must be present.
    if not re.search(r"passive inspection", root_obligations, re.IGNORECASE):
        errors.append(
            "swarm-prompt.md §12 root obligations: missing "
            "'passive inspection' rule (L1 hardening)"
        )
    if not re.search(r"decision point", root_obligations, re.IGNORECASE):
        errors.append(
            "swarm-prompt.md §12 root obligations: missing "
            "'decision point' keyword (defines WHEN to inspect)"
        )
    # The rule must be framed as mandatory, not "recommended".
    # Look for explicit mandatory language; reject permissive frames.
    if not re.search(
        r"Mandatory passive inspection|must inspect|MUST inspect",
        root_obligations,
        re.IGNORECASE,
    ):
        errors.append(
            "swarm-prompt.md §12 root obligations: passive inspection "
            "rule not framed as mandatory (must contain 'Mandatory' / "
            "'MUST inspect' — the L1 hardening)"
        )


def check_prompt_overlay(errors: list[str]) -> None:
    if not PROMPT_OVERLAY.is_file():
        errors.append(f"prompt-overlay.md not found: {PROMPT_OVERLAY}")
        return
    content = PROMPT_OVERLAY.read_text()

    # §1 must mention passive inspection at least once.
    if not re.search(r"[Pp]assive worktree inspection", content):
        errors.append(
            "prompt-overlay.md: missing 'Passive worktree inspection' "
            "callout (L1 hardening requires the root overlay to "
            "reference the rule)"
        )
        return

    # Locate the passive-inspection callout and ensure it is framed as
    # mandatory, not "recommended".
    # The callout looks like:
    #   **Passive worktree inspection (mandatory at every decision point).**
    m = re.search(
        r"\*\*Passive worktree inspection\s*\(([^)]+)\)\.\*\*",
        content,
    )
    if not m:
        errors.append(
            "prompt-overlay.md: 'Passive worktree inspection' callout "
            "not found in bold form (cannot verify framing)"
        )
        return
    framing = m.group(1).strip().lower()
    if "recommended" in framing and "mandatory" not in framing:
        errors.append(
            f"prompt-overlay.md: passive inspection framed as "
            f"'{m.group(1).strip()}' — must be promoted to 'mandatory "
            f"at every decision point' (L1 hardening)"
        )
    elif "mandatory" not in framing:
        errors.append(
            f"prompt-overlay.md: passive inspection framed as "
            f"'{m.group(1).strip()}' — must contain 'mandatory' "
            f"(L1 hardening)"
        )


def check_heartbeat(errors: list[str]) -> None:
    if not HEARTBEAT.is_file():
        errors.append(f"HEARTBEAT.md not found: {HEARTBEAT}")
        return
    content = HEARTBEAT.read_text()

    # Must have the "Cross-swarm handoff gap" section.
    if "## Cross-swarm handoff gap" not in content:
        errors.append(
            "HEARTBEAT.md: missing '## Cross-swarm handoff gap' "
            "section (L1 hardening codifies the silent-stuck gap)"
        )

    # Must have the "Completion = commit AND `complete_node`"
    # subsection.
    if not re.search(
        r"### Completion\s*=\s*commit AND `complete_node`",
        content,
    ):
        errors.append(
            "HEARTBEAT.md: missing '### Completion = commit AND "
            "`complete_node`' subsection (L1 hardening)"
        )


def check_smart_postman_swarm_prompt(errors: list[str]) -> None:
    """swarm-prompt.md §13 must declare the Smart Postman tick protocol.

    Added in the L2 hardening (2026-08). Each marker is searched for
    anywhere in the file (the §13 anchor is loose in case the section
    header moves).
    """
    if not SWARM_PROMPT.is_file():
        errors.append(f"swarm-prompt.md not found: {SWARM_PROMPT}")
        return
    content = SWARM_PROMPT.read_text()
    missing = [
        m for m in SMART_POSTMAN_REQUIRED_MARKERS
        if not re.search(re.escape(m), content, re.IGNORECASE)
    ]
    if missing:
        errors.append(
            "swarm-prompt.md: §13 Smart Postman missing required "
            f"markers: {missing}"
        )

    # §13 must contain the inline cadence — at minimum, the words
    # "decision point" and "5 minutes" must co-occur to bind the tick
    # to the existing decision-point framework.
    if not re.search(
        r"decision point",
        content,
        re.IGNORECASE,
    ) or not re.search(
        r"5\s*min",
        content,
        re.IGNORECASE,
    ):
        errors.append(
            "swarm-prompt.md: §13 Smart Postman must reference both "
            "'decision point' and '5 min' to bind tick cadence to the "
            "existing decision-point framework"
        )


def check_smart_postman_prompt_overlay(errors: list[str]) -> None:
    """prompt-overlay.md §1 Smart Postman section must reference the
    tick protocol, the recoverer role, and the inline-not-background
    rationale (ambient wake hint)."""
    if not PROMPT_OVERLAY.is_file():
        errors.append(f"prompt-overlay.md not found: {PROMPT_OVERLAY}")
        return
    content = PROMPT_OVERLAY.read_text()
    missing = [
        m for m in PROMPT_OVERLAY_SMART_POSTMAN_MARKERS
        if not re.search(re.escape(m), content, re.IGNORECASE)
    ]
    if missing:
        errors.append(
            "prompt-overlay.md: Smart Postman section missing required "
            f"markers: {missing}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.parse_args()

    errors: list[str] = []
    check_roles(errors)
    check_complete_node_mandatory(errors)
    check_swarm_prompt(errors)
    check_prompt_overlay(errors)
    check_heartbeat(errors)
    check_smart_postman_swarm_prompt(errors)
    check_smart_postman_prompt_overlay(errors)

    if errors:
        for e in errors:
            _fail(e)
        print(
            f"\nFAIL: {len(errors)} liveness-contract violation(s) — "
            "see errors above",
            file=sys.stderr,
        )
        return 1

    n_roles = sum(1 for p in ROLES_DIR.iterdir() if p.suffix == ".md")
    _pass(
        f"all {n_roles} roles carry the 6 required liveness rules "
        f"(heartbeat / stuck / exit-right / reminder-loop / "
        f"completion / cross-swarm)"
    )
    _pass(
        "swarm-prompt.md §12 root obligations carries the mandatory "
        "passive inspection rule with 'decision point' framing"
    )
    _pass(
        "swarm-prompt.md §13 Smart Postman tick protocol declared "
        "(inline cadence, recoverer spawn, decision-point binding)"
    )
    _pass(
        "prompt-overlay.md §1 passive inspection is mandatory (not "
        "recommended)"
    )
    _pass(
        "prompt-overlay.md §1 Smart Postman section references "
        "tick / recoverer / ambient wake hint"
    )
    _pass(
        "HEARTBEAT.md has 'Cross-swarm handoff gap' and 'Completion "
        "= commit AND complete_node' sections"
    )
    _pass(
        "implementer.md mandates complete_node for final handoff "
        "(report forbidden for final)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())