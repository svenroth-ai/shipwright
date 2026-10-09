"""Run records for ``test_finalization_claims_scenario``: the F5c entry and the review record.

Written untracked into the scenario repo, as they are at F11. ``reason_code=None``
leaves the closed rows without a code (the free-text closure U3 refuses).
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.review_record import REVIEW_TYPES, make_entry, new_record, upsert_review, write_record

RUN = "iterate-2026-10-08-claims-scenario"
F5C_DIR = Path(".shipwright") / "agent_docs" / "iterates"
_WHY = "the phase matrix does not run this pass at this complexity"
_DEFAULT = object()


def write_entry(root: Path, complexity: str, surface: dict) -> None:
    """The run's F5c entry, carrying the complexity and its F0.5 block."""
    (root / F5C_DIR).mkdir(parents=True, exist_ok=True)
    entry = {"run_id": RUN, "type": "change", "complexity": complexity, "branch": "iterate/probe",
             "tests_passed": True, "date": "2026-10-08T00:00:00+00:00", "surface_verification": surface,
             "risk_flags": []}  # F5c.md: the durable copy ([] = recorded none)
    (root / F5C_DIR / f"{RUN}.json").write_text(json.dumps(entry), encoding="utf-8")


def write_review_record(root: Path, complexity: str, *, code_row: dict | None = None,
                        external_row: dict | None = None, self_status: str = "completed", reason_code=_DEFAULT) -> None:
    """``self`` per ``self_status``; every other type closed (``code_row`` overrides ``code``)."""
    if reason_code is _DEFAULT:
        reason_code = "trivial-auto" if complexity == "trivial" else "diff-below-threshold"
    record = new_record(RUN)
    for review_type in REVIEW_TYPES:
        if review_type == "self":
            entry = make_entry("self", self_status, recorded_by="self-review" if self_status == "completed" else None,
                               disposition=None if self_status == "completed" else _WHY)
            if self_status != "completed" and reason_code is not None:  # break ONLY the `self` rule
                entry["reason_code"] = reason_code
        elif (row := {"code": code_row, "external_code": external_row}.get(review_type)) is not None:
            entry = make_entry(review_type, row["status"], disposition=_WHY, recorded_by=row.get("recorded_by"))
            if row.get("provider"):
                entry["provider"] = row["provider"]
            if row.get("reason_code"):
                entry["reason_code"] = row["reason_code"]
        else:
            entry = make_entry(review_type, "not_applicable", disposition=_WHY)
            if reason_code is not None:
                entry["reason_code"] = reason_code
        record = upsert_review(record, entry, force=True)
    write_record(root, RUN, record)


def event(**fields) -> dict:
    """A compliant U6-shaped ``work_completed`` event (``spec_impact: none`` with a closed code)."""
    return {"type": "work_completed", "source": "iterate", "intent": "change",
            "affected_frs": ["FR-02.01"], "spec_impact": "none",
            "spec_impact_justification": "restores the documented login redirect",
            "spec_impact_reason_code": "restores-specified-behavior", **fields}
