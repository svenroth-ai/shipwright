"""AC-2 / AC-3 / AC-4 at the gate — "completed" is not the same claim as "happened".

`_code_review_floor` used to accept `status == "completed"` on `code` or
`external_code` with nothing else on the row. Recording a pass with `--from`
omitted defaults to the `none` adapter, `build_findings` returns `[]`, and the
row lands as `findings_count 0 / provider null / raw_excerpt null /
recorded_by "none"` — byte-indistinguishable from a line nobody earned.
"""

import json
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
from tools.verifiers.review_record_check import check_review_record  # noqa: E402

RUN = "iterate-2026-07-28-floor"
WHY = "operator declined the subagent cascade for this session, per Step 8"


def _entry(root: Path, complexity: str = "medium") -> None:
    d = root / ".shipwright" / "agent_docs" / "iterates"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{RUN}.json").write_text(json.dumps({
        "run_id": RUN, "type": "bug", "complexity": complexity,
        "branch": "iterate/x", "tests_passed": True,
        "date": "2026-07-28T00:00:00+00:00",
    }), encoding="utf-8")


def _record(root: Path, **overrides):
    """Every type closed; `overrides` replaces individual entries."""
    record = new_record(RUN)
    for review_type in REVIEW_TYPES:
        if review_type not in overrides:
            record = upsert_review(record, make_entry(
                review_type, STATUS_NOT_RUN, disposition=WHY), force=True)
    record = upsert_review(record, make_entry("spec", STATUS_COMPLETED,
                                              recorded_by="spec-reviewer"), force=True)
    for review_type, entry in overrides.items():
        record = upsert_review(record, entry, force=True)
    write_record(root, RUN, record)
    return record


# --- AC-2: the floor demands evidence ---------------------------------------

def test_an_evidence_free_completed_row_does_not_satisfy_the_floor(tmp_path):
    _entry(tmp_path)
    _record(tmp_path, external_code=make_entry(
        "external_code", STATUS_COMPLETED, recorded_by="none"))

    result = check_review_record(tmp_path, RUN)

    assert result.is_failure, "a row with no provider, no excerpt and no findings passed"
    assert "evidence" in result.detail.lower()


def test_blank_metadata_is_not_evidence(tmp_path):
    """openai #6 — whitespace must not launder a fabricated row."""
    _entry(tmp_path)
    _record(tmp_path, external_code=make_entry(
        "external_code", STATUS_COMPLETED, provider="   ", raw_excerpt="\n\t",
        recorded_by="  "))

    assert check_review_record(tmp_path, RUN).is_failure


def test_a_provider_is_evidence(tmp_path):
    _entry(tmp_path)
    _record(tmp_path, external_code=make_entry(
        "external_code", STATUS_COMPLETED, provider="openrouter",
        recorded_by="external-review"))

    assert check_review_record(tmp_path, RUN).ok is True


def test_a_clean_internal_review_with_zero_findings_still_passes(tmp_path):
    """The commonest honest case: the reviewer ran and found nothing. It carries
    no findings and no provider — the adapter name is what proves it happened."""
    _entry(tmp_path)
    _record(tmp_path, code=make_entry(
        "code", STATUS_COMPLETED, findings=[], recorded_by="code-reviewer"))

    assert check_review_record(tmp_path, RUN).ok is True


def test_findings_alone_are_evidence(tmp_path):
    _entry(tmp_path)
    _record(tmp_path, code=make_entry(
        "code", STATUS_COMPLETED, recorded_by="none",
        findings=[{"finding": "a real one", "severity": "low"}]))

    assert check_review_record(tmp_path, RUN).ok is True


def test_small_complexity_has_no_floor(tmp_path):
    _entry(tmp_path, complexity="small")
    _record(tmp_path, code=make_entry("code", STATUS_NOT_RUN, disposition=WHY))

    assert check_review_record(tmp_path, RUN).ok is True


# --- AC-4: Stage 2 cannot have run without Stage 1 --------------------------

def test_a_completed_code_row_without_a_completed_spec_row_fails(tmp_path):
    _entry(tmp_path)
    record = _record(tmp_path, code=make_entry(
        "code", STATUS_COMPLETED, recorded_by="code-reviewer"))
    record = upsert_review(record, make_entry(
        "spec", STATUS_NOT_RUN, disposition=WHY), force=True)
    write_record(tmp_path, RUN, record)

    result = check_review_record(tmp_path, RUN)

    assert result.is_failure
    assert "spec" in result.detail and "Stage 1" in result.detail


def test_external_code_is_outside_the_stage_1_invariant(tmp_path):
    """openai #4 — spec-compliance is deliberately NOT cascaded to external
    providers, so requiring `spec` there would block the documented route."""
    _entry(tmp_path)
    record = _record(tmp_path, external_code=make_entry(
        "external_code", STATUS_COMPLETED, provider="openrouter"))
    record = upsert_review(record, make_entry(
        "spec", STATUS_NOT_RUN,
        disposition="Stage 1 is not cascaded to external providers"), force=True)
    write_record(tmp_path, RUN, record)

    assert check_review_record(tmp_path, RUN).ok is True


def test_an_unanswered_spec_row_blocks_like_any_other_type(tmp_path):
    _entry(tmp_path)
    record = new_record(RUN)
    for review_type in REVIEW_TYPES:
        record = upsert_review(record, make_entry(
            review_type, STATUS_NOT_RUN, disposition=WHY), force=True)
    write_record(tmp_path, RUN, record)   # `spec` left pending

    result = check_review_record(tmp_path, RUN)

    assert result.is_failure and "spec" in result.detail


# --- AC-3: a missing F5c entry fails, it does not skip ----------------------

def test_a_missing_iterate_entry_fails_instead_of_skipping(tmp_path):
    _record(tmp_path, code=make_entry("code", STATUS_COMPLETED,
                                      recorded_by="code-reviewer"))

    result = check_review_record(tmp_path, RUN)

    assert result.is_failure, "no F5c entry must not read as 'not applicable'"
    assert "F5c" in result.detail


def test_trivial_complexity_still_skips(tmp_path):
    _entry(tmp_path, complexity="trivial")

    assert check_review_record(tmp_path, RUN).is_skipped


def test_the_stage_1_remediation_command_is_actually_executable(tmp_path):
    """A gate that blocks with a broken way forward is a trap.

    The failure message advertised `--from spec-reviewer`, which is not in
    `lib.review_payloads.ADAPTERS` — argparse would have rejected the very
    command the gate told the operator to run (external code review, openai #2).
    Parsed here rather than eyeballed, so the message and the CLI cannot drift.
    """
    import re

    from lib.review_payloads import ADAPTERS
    from tools.verifiers.review_record_floor import stage_one_precedes_stage_two

    record = new_record(RUN)
    record = upsert_review(record, make_entry(
        "code", STATUS_COMPLETED, recorded_by="code-reviewer"), force=True)
    detail = stage_one_precedes_stage_two(record).detail

    adapters = re.findall(r"--from (\S+)", detail)
    assert adapters, "the remediation must name an adapter"
    for adapter in adapters:
        assert adapter in ADAPTERS, (
            f"the gate tells the operator to run `--from {adapter}`, which "
            f"argparse rejects — choices are {sorted(ADAPTERS)}"
        )
