"""The ``fr_history.py`` CLI — the surface a reader actually reaches (S7).

The library is exercised in ``test_fr_change_history*.py``. These tests are
about what a person typing the command sees and what a caller gets back: an
empty history must read as an answer, an unknown id must not be confusable with
one, and neither may collide with a usage error.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._fr_history_fixtures import project, work  # noqa: E402

from lib.fr_change_history import STATUS_FOUND, STATUS_UNKNOWN_FR  # noqa: E402

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "fr_history.py"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_UNKNOWN_FR = 3
EXIT_LOG_UNREADABLE = 4


def _run(root: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_TOOL), *args, "--project-root", str(root)],
        capture_output=True, text=True, encoding="utf-8",
    )


def test_lists_changes_and_exits_zero(tmp_path):
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a",
                                   summary="did a thing")])
    proc = _run(root, "FR-01.01")
    assert proc.returncode == EXIT_OK
    assert "run-a" in proc.stdout
    assert "did a thing" in proc.stdout


def test_an_empty_history_renders_as_no_recorded_changes_and_exits_zero(tmp_path):
    """Not an error, not a blank screen, not a silent success."""
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    proc = _run(root, "FR-01.02")
    assert proc.returncode == EXIT_OK
    assert "No recorded changes." in proc.stdout
    assert proc.stderr.strip() == ""


def test_an_unknown_id_exits_3_and_says_so(tmp_path):
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    proc = _run(root, "FR-99.99")
    assert proc.returncode == EXIT_UNKNOWN_FR
    assert "names no requirement" in proc.stderr
    assert "NOT an empty history" in proc.stderr


def test_unknown_and_empty_do_not_render_or_exit_the_same_way(tmp_path):
    """The two must never be confusable — that conflation is FV-1/FV-2."""
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    empty = _run(root, "FR-01.02")
    unknown = _run(root, "FR-99.99")
    assert empty.returncode != unknown.returncode
    assert empty.stdout != unknown.stdout


def test_an_unknown_id_does_not_collide_with_a_usage_error(tmp_path):
    """argparse owns exit 2; the unknown-id code must be distinguishable."""
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    unknown = _run(root, "FR-99.99")
    bad_flag = subprocess.run(
        [sys.executable, str(_TOOL), "FR-01.01", "--no-such-flag"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert bad_flag.returncode == EXIT_USAGE
    assert unknown.returncode != bad_flag.returncode


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_id_is_a_usage_error_not_an_answer(tmp_path, blank):
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    proc = _run(root, blank)
    assert proc.returncode == EXIT_USAGE
    assert "must not be empty" in proc.stderr
    assert proc.stdout.strip() == ""


def test_coverage_is_reported_alongside_the_answer(tmp_path):
    root = project(tmp_path, [
        work(id="evt-1", adr_id="a", affected_frs=["FR-01.01"]),
        work(id="evt-2", adr_id="b", change_type="docs"),
    ])
    proc = _run(root, "FR-01.01")
    assert "1 of 2 recorded changes name any requirement" in proc.stdout


def test_an_unverified_catalog_is_flagged_in_the_output(tmp_path):
    """Silence here would read as 'the id was checked and is fine'."""
    (tmp_path / "shipwright_events.jsonl").write_text(
        json.dumps(work(affected_frs=["FR-01.01"], adr_id="run-a")) + "\n",
        encoding="utf-8",
    )
    proc = _run(tmp_path, "FR-01.01")
    assert proc.returncode == EXIT_OK
    assert "not checked for existence" in proc.stdout


def test_json_is_machine_readable_and_carries_the_status(tmp_path):
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    proc = _run(root, "FR-01.01", "--json")
    payload = json.loads(proc.stdout)
    assert payload["status"] == STATUS_FOUND
    assert payload["changes"][0]["label"] == "run-a"
    assert payload["coverage"]["work_events"] == 1


def test_json_still_exits_3_for_an_unknown_id(tmp_path):
    """The exit code is the contract; --json must not soften it."""
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    proc = _run(root, "FR-99.99", "--json")
    assert proc.returncode == EXIT_UNKNOWN_FR
    assert json.loads(proc.stdout)["status"] == STATUS_UNKNOWN_FR


def test_survives_a_non_ascii_summary_on_a_legacy_codepage(tmp_path):
    """Real event summaries carry em dashes and arrows; Windows defaults cp1252."""
    root = project(tmp_path, [
        work(affected_frs=["FR-01.01"], adr_id="run-a",
             summary="converged — five parsers → one reader"),
    ])
    proc = _run(root, "FR-01.01")
    assert proc.returncode == EXIT_OK
    assert "→" in proc.stdout


def test_a_retired_requirement_is_answered_and_labelled_as_retired(tmp_path):
    root = project(tmp_path, [work(affected_frs=["FR-01.09"], adr_id="run-retired")],
                   fr_ids=("FR-01.01", "FR-01.02"))
    proc = _run(root, "FR-01.09")
    assert proc.returncode == EXIT_OK
    assert "not a live requirement" in proc.stdout
    assert "run-retired" in proc.stdout


def test_partial_coverage_tells_the_reader_where_the_rest_is(tmp_path):
    """Documenting the gap only in a test leaves the reader with a lossy tool."""
    root = project(tmp_path, [
        work(id="evt-1", adr_id="a", affected_frs=["FR-01.01"]),
        work(id="evt-2", adr_id="b", change_type="docs"),
    ])
    proc = _run(root, "FR-01.01")
    assert "git log" in proc.stdout
    assert "commit" in proc.stdout


def test_an_unreadable_fragment_is_warned_about_in_the_output(tmp_path):
    root = project(tmp_path, [])
    good = json.dumps(work(id="evt-a", adr_id="run-a", affected_frs=["FR-01.01"]))
    (root / "shipwright_events.jsonl").write_text(
        good + "\n" + "{not json at all\n", encoding="utf-8"
    )
    proc = _run(root, "FR-01.01")
    assert proc.returncode == EXIT_OK
    assert "unreadable fragment" in proc.stdout
