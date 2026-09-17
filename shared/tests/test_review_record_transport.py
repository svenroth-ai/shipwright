"""``transport``/``transport_note`` on a review-record entry.

Marks which harness actually answered a review-role pass (`agent`, the
default same-session Agent-tool spawn, vs `codex`, `review_via_codex.py`) so
the model-tier floor verifier can exempt a row with no legal Claude
`model_tier` value instead of flagging it as an operator mistake.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.review_record import (  # noqa: E402
    REVIEW_TYPES,
    STATUS_COMPLETED,
    STATUS_NOT_RUN,
    make_entry,
    new_record,
    upsert_review,
    write_record,
)
from lib.review_record_schema import validate_entry  # noqa: E402
from tools.verifiers.review_record_check import check_review_record  # noqa: E402
from tools.verifiers.review_record_model_tier import model_tier_note  # noqa: E402

RUN = "iterate-2026-09-13-codex-internal-review-transport-transporttest"
WHY = "not needed for this test's transport scenario"


def test_transport_absent_by_default() -> None:
    entry = make_entry("code", STATUS_COMPLETED, recorded_by="code-reviewer")
    assert "transport" not in entry


def test_transport_codex_recorded() -> None:
    entry = make_entry("code", STATUS_COMPLETED, recorded_by="code-reviewer", transport="codex")
    assert entry["transport"] == "codex"
    assert validate_entry("code", entry) is None


def test_transport_note_recorded() -> None:
    entry = make_entry(
        "code", STATUS_COMPLETED, recorded_by="code-reviewer",
        transport="codex", transport_note="mid-run timeout, fell back to inherit",
    )
    assert entry["transport_note"] == "mid-run timeout, fell back to inherit"


def test_invalid_transport_value_rejected() -> None:
    entry = make_entry("code", STATUS_COMPLETED, recorded_by="code-reviewer")
    entry["transport"] = "carrier-pigeon"
    err = validate_entry("code", entry)
    assert err is not None
    assert "transport" in err


def _record_with_transport(root: Path, transport: str | None) -> None:
    record = new_record(RUN)
    for review_type in REVIEW_TYPES:
        if review_type not in ("code", "spec"):
            record = upsert_review(record, make_entry(
                review_type, STATUS_NOT_RUN, disposition=WHY), force=True)
    record = upsert_review(record, make_entry(
        "spec", STATUS_COMPLETED, recorded_by="spec-reviewer", model_tier="opus"))
    code_kwargs = {"recorded_by": "code-reviewer"}
    if transport is not None:
        code_kwargs["transport"] = transport
    record = upsert_review(record, make_entry("code", STATUS_COMPLETED, **code_kwargs))
    write_record(root, RUN, record)


def _entry(root: Path) -> None:
    import json
    d = root / ".shipwright" / "agent_docs" / "iterates"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{RUN}.json").write_text(json.dumps({
        "run_id": RUN, "type": "bug", "complexity": "medium",
        "branch": "iterate/x", "tests_passed": True,
        "date": "2026-09-13T00:00:00+00:00",
    }), encoding="utf-8")


def _configure_floor(root: Path, tier: str) -> None:
    import json
    (root / "shipwright_model_config.json").write_text(
        json.dumps({"floors": {"review": tier}}), encoding="utf-8",
    )


def test_codex_transport_row_exempt_from_missing_tier_floor_note(tmp_path: Path) -> None:
    """A `codex`-transport row has no legal Claude `model_tier` — the floor
    verifier must not flag it as an operator-forgot-the-flag gap."""
    _entry(tmp_path)
    _configure_floor(tmp_path, "opus")
    _record_with_transport(tmp_path, transport="codex")

    result = check_review_record(tmp_path, RUN)

    assert result.ok is True
    assert "no recorded tier" not in result.detail


def test_agent_transport_row_still_flagged_for_missing_tier(tmp_path: Path) -> None:
    """The exemption is transport-specific — an ordinary agent-spawn row with
    no recorded tier is still flagged exactly as before."""
    _entry(tmp_path)
    _configure_floor(tmp_path, "opus")
    _record_with_transport(tmp_path, transport=None)

    result = check_review_record(tmp_path, RUN)

    assert result.ok is True
    assert "no recorded tier" in result.detail


def test_model_tier_note_direct_exemption_for_codex_transport(tmp_path: Path) -> None:
    _configure_floor(tmp_path, "opus")
    record = {
        "reviews": {
            "spec": {"status": STATUS_COMPLETED, "recorded_by": "spec-reviewer",
                     "model_tier": "opus"},
            "code": {"status": STATUS_COMPLETED, "recorded_by": "code-reviewer",
                     "transport": "codex"},
        },
    }
    note = model_tier_note(record, tmp_path)
    assert note == ""
