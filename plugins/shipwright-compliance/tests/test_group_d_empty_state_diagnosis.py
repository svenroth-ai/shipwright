"""WHICH empty-requirement state D2 names — the diagnosis, not the verdict.

Split from ``test_group_d_empty_set_verdicts.py`` (requirements-catalog S6, review
round) when that module crossed its size guideline. The seam is the same one the
review found: the sibling asks *does D2 fail or skip*, this one asks *and does it
name the right cause*. They failed independently — the verdict was right from the
first cut and the diagnosis was wrong twice — so they are worth reading apart.

Every message asserted here comes from ``group_i_scan.SpecScan``, which owns the
six-state classification. Nothing in ``_group_d_empty_state`` decides a state; the
one time it tried, it reported a fully-retired spec as an empty table.

@FR-01.10
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_d  # noqa: E402


def _events(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8",
    )


def _d2(tmp_path: Path):
    findings = group_d.run(tmp_path, None, None)
    return next(f for f in findings if f.check_id == "D2")


def _spec(tmp_path: Path, body: str, split: str = "01-adopted") -> None:
    d = tmp_path / ".shipwright" / "planning" / split
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.md").write_text(body, encoding="utf-8")


#: A spec that EXISTS and holds real requirements, but whose table the shared
#: reader declines wholesale — no governing header naming a Priority column.
_UNREADABLE = """\
## Functional Requirements

| ID | Name | Notes |
|----|------|-------|
| FR-01.01 | Task board | shows every task |
| FR-01.02 | Health check | reports liveness |
"""

#: The same requirements in a table the reader DOES accept.
_READABLE = """\
## Functional Requirements

| ID | Name | Priority | Description |
|----|------|----------|-------------|
| FR-01.01 | Task board | Must | Shows every task on one board. |
| FR-01.02 | Health check | Must | Reports whether the service is live. |
"""


def test_an_unreadable_table_is_not_reported_as_stale_references(tmp_path):
    """The failure D2 gained must not misdiagnose a table-shape defect.

    The old `if not spec_frs: skip` incidentally absorbed EVERY reason the
    requirement set is empty. Now that the empty set can FAIL, the two reasons
    have to be told apart: with no spec on disk the event references really are
    dangling, but with a spec whose rows were all DECLINED the requirements
    exist and the message must not accuse the operator of stale references
    while naming the very FRs the project has.

    Verdict is unchanged -- still a fail, because nothing resolved. Only the
    diagnosis moves, from the symptom to the cause.
    """
    _spec(tmp_path, _UNREADABLE)
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "affected_frs": ["FR-01.01"]},
    ])
    d2 = _d2(tmp_path)
    assert d2.status == "fail"
    assert "not in current spec" not in d2.detail, (
        "the requirements ARE in the spec -- the table shape is the defect")
    # Wording comes from group_i_scan's `no_governing_header` state, not from a
    # sentence written here: this module classifies nothing of its own.
    assert "no table header naming a Priority column" in d2.detail
    assert "fix the table header" in d2.detail
    assert "FR-01.01" in d2.detail, "the unresolvable refs are still named"


#: Rows that parse cleanly and are all RETIRED. `read_active_fr_rows` yields
#: nothing, so the requirement set is empty — but the table is not defective.
_ALL_RETIRED = """\
## Functional Requirements

| ID | Name | Priority | Description |
|----|------|----------|-------------|

### Removed Requirements

| ID | Name | Priority | Description |
|----|------|----------|-------------|
| FR-01.01 | Task board | Must | Shows every task on one board. |
| FR-01.02 | Health check | Must | Reports whether the service is live. |
"""


def test_an_all_retired_spec_is_not_reported_as_an_empty_or_broken_table(tmp_path):
    """The case the FIRST cut of the empty-state module got wrong.

    A spec whose FR rows all sit under ``### Removed Requirements`` reads as zero
    LIVE requirements. The original version branched on raw ``any_spec`` /
    ``rejects``, saw a spec with no rejects, and fell through to *"spec.md
    present but its requirements table holds no rows"* — about a file that
    plainly holds rows, which had been read successfully, delivered as a
    non-zero exit and `FAIL — drift found`.

    Group I had classified this correctly as ``all_rows_retired`` the whole
    time. The module now READS that state instead of deriving a second answer to
    a question that already had one, which is what its own docstring said to do.
    """
    _spec(tmp_path, _ALL_RETIRED)
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "affected_frs": ["FR-01.01"]},
    ])
    d2 = _d2(tmp_path)
    assert "holds no rows" not in d2.detail, (
        "the table holds rows and they were read — they are retired")
    assert "no FR-shaped rows" not in d2.detail
    assert "Removed Requirements" in d2.detail
    assert "nothing is broken" in d2.detail


def test_the_fail_soft_fallback_degrades_to_the_historical_wording(monkeypatch,
                                                                   tmp_path):
    """Pin the degradation, so it cannot become the silent default.

    ``describe_empty_requirements`` swallows any error from the classifier and
    answers with the pre-S6 generic sentence, on the grounds that a worse message
    is not worth a red audit group. That is the right trade — but untested it is
    also the perfect hiding place: a future ``scan_specs`` signature change would
    downgrade EVERY D2 message back to generic wording, permanently, with a fully
    green suite and no one the wiser.

    So the fallback is exercised on purpose, and asserted to be a loss of
    PRECISION rather than a change of meaning: it must be exactly the historical
    literal that D1 and D4 still answer with.
    """
    from scripts.audit import _group_d_empty_state as mod
    import scripts.audit.group_i as group_i

    def _boom(*_a, **_k):
        raise TypeError("scan_specs() got an unexpected keyword argument")

    monkeypatch.setattr(group_i, "scan_specs", _boom)
    _spec(tmp_path, _UNREADABLE)
    assert mod.describe_empty_requirements(tmp_path) == mod.GENERIC

    # …and the audit still runs rather than reddening on the classifier's fault.
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "affected_frs": ["FR-01.01"]},
    ])
    d2 = _d2(tmp_path)
    assert d2.status == "fail"
    assert mod.GENERIC in d2.detail


def test_no_spec_at_all_says_so_rather_than_blaming_the_table(tmp_path):
    """Control: the OTHER empty state keeps its own, different diagnosis.

    Without this, `describe_empty_requirements` could return the table-shape
    wording unconditionally and the assertion above would still pass.
    """
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "affected_frs": ["FR-99.99"]},
    ])
    d2 = _d2(tmp_path)
    assert d2.status == "fail"
    assert "no spec.md" in d2.detail
    assert "declined" not in d2.detail


def test_a_readable_spec_keeps_the_historical_stale_reference_wording(tmp_path):
    """Control: with requirements present, an unresolvable ref IS stale.

    The historical wording is correct there and must not be replaced by the
    could-not-read phrasing, which would assert something about a spec that
    was in fact read successfully.
    """
    _spec(tmp_path, _READABLE)
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "affected_frs": ["FR-99.99"]},
    ])
    d2 = _d2(tmp_path)
    assert d2.status == "fail"
    assert "events reference FR-IDs not in current spec" in d2.detail
    assert "FR-99.99" in d2.detail


