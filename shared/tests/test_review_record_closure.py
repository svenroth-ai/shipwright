"""U3: the review record is enforced at EVERY complexity, trivial included.

Before this change a record could close every type ``not_run`` with free-text
dispositions and the gate went green at small, and it never looked at trivial at
all. Now ``self`` must be completed with evidence at every complexity, and every
skipped pass names a closed-vocabulary ``reason_code`` — the one default
``trivial-auto`` at trivial, a per-type code from ``small`` up.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.review_record import (  # noqa: E402
    REVIEW_TYPES,
    make_entry,
    new_record,
    upsert_review,
    write_record,
)
from tools.verifiers.common import Severity  # noqa: E402
from tools.verifiers.review_record_check import check_review_record  # noqa: E402

RUN = "iterate-2026-10-08-closure"
WHY = "the phase matrix does not run this pass at this complexity"


def _entry(root: Path, complexity: str) -> None:
    d = root / ".shipwright" / "agent_docs" / "iterates"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{RUN}.json").write_text(json.dumps({
        "run_id": RUN, "type": "change", "complexity": complexity,
        "branch": "iterate/x", "tests_passed": True,
        "date": "2026-10-08T00:00:00+00:00",
    }), encoding="utf-8")


def _record(root: Path, code: str | None, *, self_entry: dict | None = None,
            overrides: dict[str, dict] | None = None) -> dict:
    """`self` completed (evidenced) unless replaced; every other type not_run with `code`."""
    record = new_record(RUN)
    for review_type in REVIEW_TYPES:
        if review_type == "self":
            entry = self_entry or make_entry("self", "completed", recorded_by="self-review")
        else:
            entry = make_entry(review_type, "not_applicable", disposition=WHY)
            if code is not None:
                entry["reason_code"] = code
        record = upsert_review(record, entry, force=True)
    for entry in (overrides or {}).values():
        record = upsert_review(record, entry, force=True)
    write_record(root, RUN, record)
    return record


@pytest.mark.covers("FR-01.11")
def test_trivial_self_plus_the_default_code_passes_and_is_not_a_skip(tmp_path):
    _entry(tmp_path, "trivial")
    _record(tmp_path, "trivial-auto")

    result = check_review_record(tmp_path, RUN)

    assert result.ok, result.detail
    assert result.severity != Severity.SKIPPED.value


@pytest.mark.covers("FR-01.11")
def test_trivial_accepts_any_closed_code_not_only_the_default(tmp_path):
    _entry(tmp_path, "trivial")
    _record(tmp_path, "missing-keys")

    assert check_review_record(tmp_path, RUN).ok


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("complexity", ["trivial", "small", "medium"])
def test_self_not_run_fails_at_every_complexity(tmp_path, complexity):
    _entry(tmp_path, complexity)
    code = "trivial-auto" if complexity == "trivial" else "diff-below-threshold"
    _record(tmp_path, code, self_entry={
        **make_entry("self", "not_run", disposition=WHY), "reason_code": code})

    result = check_review_record(tmp_path, RUN)

    assert result.is_failure
    assert "`self` is 'not_run'" in result.detail
    assert "--force" in result.detail, "a closed row is immutable; the repair must say --force"


@pytest.mark.covers("FR-01.11")
def test_an_evidence_free_self_row_fails(tmp_path):
    """`--status completed` with `--from` omitted is the shape nobody earned."""
    _entry(tmp_path, "trivial")
    _record(tmp_path, "trivial-auto",
            self_entry=make_entry("self", "completed", recorded_by="none"))

    result = check_review_record(tmp_path, RUN)

    assert result.is_failure and "no evidence" in result.detail


@pytest.mark.covers("FR-01.11")
def test_small_names_the_type_that_lacks_a_code(tmp_path):
    _entry(tmp_path, "small")
    _record(tmp_path, "complexity-below-threshold", overrides={
        "doubt": make_entry("doubt", "not_run", disposition=WHY)})

    result = check_review_record(tmp_path, RUN)

    assert result.is_failure
    assert "without a reason_code: doubt" in result.detail


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("complexity", ["small", "medium", "large"])
def test_the_trivial_default_is_refused_above_trivial(tmp_path, complexity):
    _entry(tmp_path, complexity)
    _record(tmp_path, "complexity-below-threshold", overrides={
        "doubt": {**make_entry("doubt", "not_run", disposition=WHY), "reason_code": "trivial-auto"}})

    result = check_review_record(tmp_path, RUN)

    assert result.is_failure
    assert f"'trivial-auto' at {complexity}: doubt" in result.detail


@pytest.mark.covers("FR-01.11")
def test_trivial_free_text_closure_names_the_one_command(tmp_path):
    _entry(tmp_path, "trivial")
    _record(tmp_path, None)

    result = check_review_record(tmp_path, RUN)

    assert result.is_failure
    assert "close-missing" in result.detail and "--reason-code trivial-auto" in result.detail


@pytest.mark.covers("FR-01.11")
def test_a_legacy_gates_spec_row_is_held_to_the_same_rule(tmp_path):
    """A row read from the retired `gates` seam is still a row this run closed."""
    _entry(tmp_path, "small")
    record = _record(tmp_path, "complexity-below-threshold")
    del record["reviews"]["spec"]
    record["gates"] = {"spec": make_entry("spec", "not_run", disposition=WHY)}
    write_record(tmp_path, RUN, record)

    result = check_review_record(tmp_path, RUN)

    assert result.is_failure and "without a reason_code: spec" in result.detail


@pytest.mark.covers("FR-01.11")
def test_a_code_outside_the_vocabulary_is_an_integrity_fault(tmp_path):
    _entry(tmp_path, "small")
    _record(tmp_path, "complexity-below-threshold")
    path = tmp_path / ".shipwright" / "planning" / "iterate" / RUN / "reviews.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["reviews"]["doubt"]["reason_code"] = "because"
    path.write_text(json.dumps(data), encoding="utf-8")

    result = check_review_record(tmp_path, RUN)

    assert result.is_failure and "unreadable or schema-invalid" in result.detail
