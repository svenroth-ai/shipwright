"""``already_audited`` must not freeze a provisional SKIP forever (trg-b36fd844).

``unresolvable_run_id_skip`` (S2/S3/W2/S9/S10) SKIPs when the audited run has
no exact ``iterate_history`` entry yet. Since iterate-2026-08-06-resolve-run-id-seam
the ``(phase, run_id, session_id)`` triple is stable across a whole run, so the
FIRST Stop after B1a — before F5c ever writes that entry — used to record a
finding that every LATER Stop's ``already_audited`` treated as final, even once
the entry appeared. The fix: findings tagged
``reason_code="unresolvable_run_id"`` are re-audited once
``has_exact_iterate_entry`` turns True.

Unit-level coverage lives here for ``make_finding``/``unresolvable_run_id_skip``
tagging and ``already_audited`` staleness. The E2E coverage that drives the
real Stop hook subprocess end to end (the shape the bug actually manifested
in) lives in the sibling
``test_phase_quality_stop_hook_reachability_e2e.py`` — split out to keep
this file under the 300-LOC guideline.
"""

from __future__ import annotations

import json
from pathlib import Path

from lib import phase_quality as pq  # noqa: E402
from lib.phase_quality._findings import already_audited  # noqa: E402
from lib.phase_quality._staleness import is_stale_unresolvable_run_id_finding  # noqa: E402
from tools.verifiers._iterate_run_id import unresolvable_run_id_skip  # noqa: E402


# ---------------------------------------------------------------------------
# Unit: make_finding / unresolvable_run_id_skip tagging
# ---------------------------------------------------------------------------


def test_make_finding_embeds_reason_code_when_given():
    finding = pq.make_finding("S9", pq.STATUS_SKIP, "evidence", reason_code="unresolvable_run_id")
    assert finding["reason_code"] == "unresolvable_run_id"


def test_make_finding_omits_reason_code_by_default():
    finding = pq.make_finding("S9", pq.STATUS_PASS, "evidence")
    assert "reason_code" not in finding


def test_unresolvable_run_id_skip_tags_the_finding(tmp_path: Path):
    guard = unresolvable_run_id_skip(tmp_path, "unknown", [], "S9", "S9 name")
    assert guard is not None
    assert guard["reason_code"] == "unresolvable_run_id"
    assert guard["status"] == pq.STATUS_SKIP


def test_unresolvable_run_id_skip_no_reason_code_when_resolvable(tmp_path: Path):
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"iterate_history": [{"run_id": "run-a"}]}), encoding="utf-8")
    guard = unresolvable_run_id_skip(tmp_path, "run-a", [], "S9", "S9 name")
    assert guard is None  # caller proceeds with normal logic — nothing to tag


# ---------------------------------------------------------------------------
# Unit: already_audited staleness
# ---------------------------------------------------------------------------


def _write_iterate_finding(tmp_path: Path, run_id: str, session_id: str, *, marker: bool) -> None:
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    s2 = (
        pq.make_finding("S2", pq.STATUS_SKIP, "not resolvable", reason_code="unresolvable_run_id")
        if marker
        else pq.make_finding("S2", pq.STATUS_PASS, "spec present")
    )
    pq.write_finding_json(tmp_path, "iterate", run_id, session_id, {"spec": [s2]})


def test_already_audited_true_for_an_ordinary_finding(tmp_path: Path):
    _write_iterate_finding(tmp_path, "run-a", "sess-1", marker=False)
    assert already_audited(tmp_path, "iterate", "run-a", "sess-1") is True


def test_already_audited_still_true_while_entry_remains_absent(tmp_path: Path):
    """No needless re-audit loop: a provisional SKIP recorded while the entry
    is STILL absent must stay final — nothing has changed that would produce
    a different verdict."""
    _write_iterate_finding(tmp_path, "run-a", "sess-1", marker=True)
    assert already_audited(tmp_path, "iterate", "run-a", "sess-1") is True


def test_already_audited_false_once_the_entry_appears(tmp_path: Path):
    _write_iterate_finding(tmp_path, "run-a", "sess-1", marker=True)
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"iterate_history": [{"run_id": "run-a", "complexity": "medium"}]}),
        encoding="utf-8",
    )
    assert already_audited(tmp_path, "iterate", "run-a", "sess-1") is False


def test_already_audited_false_for_a_hook_level_error_finding(tmp_path: Path):
    """write_error_finding's empty-categories source="error" payload is the
    least-informed verdict there is — it must never freeze a phase at "the
    audit crashed" for the rest of the run."""
    pq.write_error_finding(tmp_path, "iterate", "run-a", "sess-1", RuntimeError("boom"))
    assert already_audited(tmp_path, "iterate", "run-a", "sess-1") is False


def test_already_audited_false_when_any_category_carries_the_marker(tmp_path: Path):
    """The marker can land in ANY of the six categories (S9/S10 are in
    ``spec`` too, but a future check could tag a different category) — the
    staleness scan must not be hard-coded to one."""
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    marker = pq.make_finding("W2", pq.STATUS_SKIP, "not resolvable", reason_code="unresolvable_run_id")
    pq.write_finding_json(tmp_path, "iterate", "run-a", "sess-1", {"workflow": [marker]})
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"iterate_history": [{"run_id": "run-a", "complexity": "medium"}]}),
        encoding="utf-8",
    )
    assert already_audited(tmp_path, "iterate", "run-a", "sess-1") is False


# ---------------------------------------------------------------------------
# Unit: is_stale_unresolvable_run_id_finding — direct branch coverage
# ---------------------------------------------------------------------------


def test_is_stale_unresolvable_run_id_finding_false_for_a_non_dict_payload(tmp_path: Path):
    """A malformed (non-dict) payload must short-circuit to 'not stale'
    before touching CATEGORIES — the schema guard at the top of the try."""
    assert is_stale_unresolvable_run_id_finding(["not", "a", "dict"], tmp_path, "run-a") is False
    assert is_stale_unresolvable_run_id_finding(None, tmp_path, "run-a") is False


def test_is_stale_unresolvable_run_id_finding_swallows_exception_and_warns(tmp_path: Path, capsys):
    """A malformed category value (truthy but non-iterable) raises TypeError
    while scanning for the marker. Doubt-review D4: this must fall back to
    'not stale' AND print a stderr diagnostic, not fail silently."""
    payload = {"canon": 1}  # `payload.get("canon") or []` -> 1, not iterable

    result = is_stale_unresolvable_run_id_finding(payload, tmp_path, "run-a")

    assert result is False
    err = capsys.readouterr().err
    assert "is_stale_finding fell back to 'not stale'" in err
    assert "run_id='run-a'" in err

