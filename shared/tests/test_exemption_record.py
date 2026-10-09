"""The per-exemption record in the F5c entry: validation, writer, F11 gate, summary line."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from lib.exemption_record import (
    entry_exemptions_error, entry_summary_line, exemption_counts, exemptions_error, format_summary_line,
)
from shared.tests._iterate_entry_helpers import append_iterate_entry
from tools.append_iterate_entry import IterateAppendError
from tools.verifiers.common import Severity
from tools.verifiers.exemption_record_check import check_exemption_record

RUN_ID = "iterate-2026-10-08-exemption-record"
TOOL = str(Path(__file__).resolve().parents[1] / "scripts" / "tools" / "exemption_summary.py")


def _item(scope="tests/test_x.py::test_helper", kind="test_exemption", code="fixture-or-helper"):
    return {"kind": kind, "scope": scope, "reason_code": code}


def _block(*items):
    return {"count": len(items), "items": list(items)}


def _entry(**extra):
    return {
        "run_id": RUN_ID, "date": "2026-10-08T10:00:00Z", "type": "change",
        "complexity": "medium", "branch": "iterate/x", "spec": None,
        "tests_passed": True, "adr": RUN_ID, **extra,
    }


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True)
    return tmp_path


@pytest.mark.covers("FR-01.11")
def test_absent_key_is_legacy_and_valid_but_explicit_null_is_malformed():
    assert entry_exemptions_error({}) is None
    assert entry_summary_line({}) == "not recorded (legacy entry)"  # never "0": that reads as a recorded zero
    assert exemption_counts(None) == {}
    assert entry_exemptions_error({"exemptions": None}) is not None
    assert entry_summary_line({"exemptions": None}).startswith("INVALID - ")


@pytest.mark.covers("FR-01.11")
def test_well_formed_block_is_valid_and_counted_per_reason_code():
    block = _block(_item(), _item("tests/a.py::b"), _item("tests/c.py::d", code="mechanical-refactor"))
    assert exemptions_error(block) is None
    assert exemption_counts(block) == {"fixture-or-helper": 2, "mechanical-refactor": 1}
    assert format_summary_line(block) == "3 (fixture-or-helper: 2, mechanical-refactor: 1)"


@pytest.mark.covers("FR-01.11")
def test_empty_block_prints_zero():
    assert exemptions_error(_block()) is None
    assert format_summary_line(_block()) == "0"


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("bad", [
    "three", [], {"count": 1}, {"items": []},
    {"count": 2, "items": [_item()]},          # count disagrees with items
    {"count": True, "items": []},              # bool is not a count
    _block("not an object"),
    _block({"kind": "test_exemption", "scope": "a::b"}),                       # no reason_code
    _block({**_item(), "note": "free text"}),                                  # extra key
    _block(_item(code="because I said so")),                                   # free text reason
    _block(_item(kind="no_such_family")),                                      # unknown family
    _block(_item(kind=7)),
    _block(_item(code="unavailable")),                                         # right code, wrong family
    _block(_item(kind="review_not_run", code="unavailable")),                  # a review answer is not an exemption
    _block(_item(kind="untestable", code="covered-by-existing-test")),         # nor is an untestable behaviour
])
def test_malformed_blocks_are_refused(bad):
    assert exemptions_error(bad) is not None
    assert format_summary_line(bad).startswith("INVALID - ")


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("scope", [
    "", "   ", "/etc/passwd::t", "x.py::/../../secret", "C:\\x\\t.py::t", "c:/x::t", "../outside.py::t",
    "tests/../../x.py::t", "tests\\..\\..\\x.py::t", "a\nb::t", "a\x00b", "x" * 301,
    "x.py::/etc/passwd", "x.py::C:\\secret", "x.py::t::/abs",   # an absolute path AFTER the first `::`
])
def test_unsafe_scopes_are_refused(scope):
    assert exemptions_error(_block(_item(scope))) is not None


@pytest.mark.covers("FR-01.11")
def test_a_slash_inside_a_test_name_is_not_an_absolute_path():
    assert exemptions_error(_block(_item("tests/x.py::test_a[/not/leading]"))) is None


@pytest.mark.covers("FR-01.11")
def test_writer_refuses_a_malformed_block_and_writes_a_valid_one(project):
    with pytest.raises(IterateAppendError, match="exemptions.count"):
        append_iterate_entry(project, _entry(exemptions={"count": 5, "items": []}))
    result = append_iterate_entry(project, _entry(exemptions=_block(_item())))
    written = json.loads((project / result["entry_path"]).read_text(encoding="utf-8"))
    assert written["exemptions"]["count"] == 1


@pytest.mark.covers("FR-01.11")
def test_writer_and_f11_refuse_an_explicit_null_block(project):
    with pytest.raises(IterateAppendError, match="exemptions"):
        append_iterate_entry(project, _entry(exemptions=None))


@pytest.mark.covers("FR-01.11")
def test_writer_still_accepts_a_legacy_entry_without_the_block(project):
    result = append_iterate_entry(project, _entry())
    assert "exemptions" not in json.loads((project / result["entry_path"]).read_text(encoding="utf-8"))


@pytest.mark.covers("FR-01.11")
def test_f11_check_skips_without_the_block_passes_when_valid_and_fails_when_tampered(project):
    assert check_exemption_record(project, RUN_ID).severity == Severity.SKIPPED.value
    result = append_iterate_entry(project, _entry(exemptions=_block(_item())))
    ok = check_exemption_record(project, RUN_ID)
    assert ok.ok is True and "1 (fixture-or-helper: 1)" in ok.detail

    path = project / result["entry_path"]
    data = json.loads(path.read_text(encoding="utf-8"))
    data["exemptions"]["items"][0]["reason_code"] = "trust me"
    path.write_text(json.dumps(data), encoding="utf-8")
    red = check_exemption_record(project, RUN_ID)
    assert red.ok is False and "closed test_exemption vocabulary" in red.detail


def _summary(project, run_id=RUN_ID):
    done = subprocess.run(
        [sys.executable, TOOL, "--project-root", str(project), "--run-id", run_id],
        capture_output=True, text=True, encoding="utf-8",
    )
    return done.returncode, done.stdout.strip()


@pytest.mark.covers("FR-01.11")
def test_summary_cli_prints_the_count_for_f12_and_the_pr_body(project):
    append_iterate_entry(project, _entry(exemptions=_block(_item(), _item("tests/a.py::b"))))
    assert _summary(project) == (0, "2 (fixture-or-helper: 2)")


@pytest.mark.covers("FR-01.11")
def test_summary_cli_says_not_recorded_for_a_legacy_entry_and_fails_loudly_without_one(project):
    assert _summary(project)[0] == 1 and _summary(project)[1].startswith("INVALID - no iterate entry")
    append_iterate_entry(project, _entry())
    assert _summary(project) == (0, "not recorded (legacy entry)")
    append_iterate_entry(project, _entry(run_id="iterate-2026-10-08-zero", adr="iterate-2026-10-08-zero",
                                         exemptions=_block()))
    assert _summary(project, "iterate-2026-10-08-zero") == (0, "0")
