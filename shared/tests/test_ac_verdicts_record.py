"""Q2 phase 1: the spec-reviewer's per-AC verdicts survive ``record_review_pass.py`` onto the ``spec`` row (and nowhere else)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _review_cli_harness import RUN_ID, make_project, payload, run_tool  # noqa: E402

_SHARED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SHARED / "scripts"))

from lib import ac_verdicts as av  # noqa: E402
from lib.review_payloads import CANONICAL_PAYLOAD_BASENAMES  # noqa: E402
from lib.review_record import read_record, validate_record  # noqa: E402

_GOOD = {"ac": "FR-01.03.AC06", "verdict": "diverges", "diff_location": "src/a.py:12", "reason": "saved twice overwrites the first copy"}
_REPLY = {"stage": "spec-compliance", "verdict": "PASS", "spec_citations": [], "summary": "ok",
          "ac_verdicts": [_GOOD, {"ac": "item-1", "verdict": "matches"}]}


def _record_spec(project, tmp_path, reply: dict, status: str = "completed", review_type: str = "spec"):
    adapter = {"spec": "spec-reviewer", "code": "code-reviewer"}[review_type]
    run_tool(project, "init")
    args = ["record", "--review-type", review_type, "--status", status, "--from", adapter,
            "--payload-file", payload(tmp_path, CANONICAL_PAYLOAD_BASENAMES[review_type], json.dumps(reply)), "--model-tier", "opus"]
    return run_tool(project, *args)


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path)


@pytest.mark.covers("FR-01.11/AC50")
def test_the_per_ac_verdicts_land_on_the_completed_spec_row_and_the_record_stays_valid(project, tmp_path):
    code, out = _record_spec(project, tmp_path, _REPLY)
    assert code == 0, out
    record = read_record(project, RUN_ID)
    assert record["reviews"]["spec"]["ac_verdicts"] == [{**_GOOD, "weakens": None}, {"ac": "item-1", "verdict": "matches", "diff_location": None, "reason": "", "weakens": None}]
    assert validate_record(record) == (True, None)


@pytest.mark.covers("FR-01.11/AC50")
def test_a_reply_without_ac_verdicts_records_exactly_as_before(project, tmp_path):
    code, out = _record_spec(project, tmp_path, {k: v for k, v in _REPLY.items() if k != "ac_verdicts"})
    assert code == 0, out
    assert "ac_verdicts" not in read_record(project, RUN_ID)["reviews"]["spec"]


@pytest.mark.covers("FR-01.11/AC50")
def test_other_review_types_never_carry_ac_verdicts(project, tmp_path):
    code, out = _record_spec(project, tmp_path, {"stage": "code-review", "review": [], "ac_verdicts": [_GOOD]}, review_type="code")
    assert code == 0, out
    assert "ac_verdicts" not in read_record(project, RUN_ID)["reviews"]["code"]


@pytest.mark.covers("FR-01.11/AC50")
def test_clean_keeps_only_well_formed_entries_and_caps_text():
    raw = [_GOOD, "junk", {"ac": "", "verdict": "matches"}, {"ac": "x", "verdict": "maybe"}, {"ac": "y", "verdict": "diverges", "reason": "r" * 900, "weakens": True}]
    out = av.clean(raw)
    assert [v["ac"] for v in out] == ["FR-01.03.AC06", "y"]
    assert len(out[1]["reason"]) <= av.MAX_REASON and out[1]["weakens"] is True


@pytest.mark.covers("FR-01.11/AC50")
def test_clean_bounds_the_number_of_entries_and_ignores_a_non_list():
    assert len(av.clean([{"ac": f"a{i}", "verdict": "matches"} for i in range(500)])) == av.MAX_ENTRIES
    assert av.clean({"ac": "x"}) == [] and av.clean(None) == []


@pytest.mark.covers("FR-01.11/AC50")
def test_an_unreadable_payload_yields_no_fields_instead_of_failing_the_record(tmp_path):
    assert av.verdict_fields("spec", "completed", str(tmp_path / "missing.json")) == {}
    bad = tmp_path / "bad.json"
    bad.write_text("not json at all", encoding="utf-8")
    assert av.verdict_fields("spec", "completed", str(bad)) == {}
    assert av.verdict_fields("spec", "not_run", str(bad)) == {} and av.verdict_fields("spec", "completed", None) == {}
