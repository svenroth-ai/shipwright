"""``lib.phase_history.latest_completion`` — reading a phase's completion record.

Split from ``test_phase_history.py`` at the 300-LOC limit; that file keeps the
timekeeping (``RecordedTime``, ``entry_anchor``, ``entry_wall_time``).

Two records, because the pipeline keeps two: seven phases append to
``shipwright_run_config.json::phase_history``, ``iterate`` writes the
file-per-run ledger. Reading the wrong one for a phase is how ``iterate`` came
to be checked against a bucket nothing has ever written for it.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.phase_history import latest_completion, parse_iso_utc  # noqa: E402


def _at(text: str) -> datetime:
    moment = parse_iso_utc(text)
    assert moment is not None
    return moment


def _cfg(root: Path, history) -> Path:
    (root / "shipwright_run_config.json").write_text(
        json.dumps({"phase_history": history}), encoding="utf-8"
    )
    return root


def test_the_last_appended_entry_wins(tmp_path):
    """File order is completion order — append_phase_history appends. Sorting by
    timestamp instead would reorder the date-only changelog entries, several of
    which share a day."""
    root = _cfg(tmp_path, {"build": [
        {"run_id": "first", "at": "2026-07-27T10:00:00+00:00"},
        {"run_id": "second", "at": "2026-07-27T09:00:00+00:00"},
    ]})

    completion = latest_completion(root, "build")

    assert completion is not None
    assert completion.run_id == "second"
    assert completion.known_run_ids == ("first", "second")


def test_repeated_run_ids_are_kept_not_deduped(tmp_path):
    """C3 counts them: one run recording SEVERAL completions is the sticky-id
    case (`build` splits), and the only case where the run id alone cannot say
    which completion the note belongs to."""
    root = _cfg(tmp_path, {"build": [
        {"run_id": "sticky", "event_at": "2026-07-27T10:00:00+00:00"},
        {"run_id": "sticky", "event_at": "2026-07-27T12:00:00+00:00"},
    ]})

    completion = latest_completion(root, "build")

    assert completion is not None
    assert completion.known_run_ids.count("sticky") == 2
    assert completion.anchor is not None
    assert completion.anchor.earliest == _at("2026-07-27T12:00:00+00:00")


def test_entries_without_a_run_id_are_skipped(tmp_path):
    root = _cfg(tmp_path, {"build": [
        {"run_id": "real", "at": "2026-07-27T10:00:00+00:00"},
        {"outcome": "completed"},
    ]})

    completion = latest_completion(root, "build")

    assert completion is not None and completion.run_id == "real"


def test_a_phase_with_no_entries_is_none(tmp_path):
    assert latest_completion(_cfg(tmp_path, {"build": []}), "build") is None


def test_an_absent_phase_is_none(tmp_path):
    assert latest_completion(_cfg(tmp_path, {"build": []}), "test") is None


def test_a_run_config_saved_with_a_bom_is_still_read(tmp_path):
    """Notepad writes UTF-8 WITH BOM, and `json.loads` rejects it at char 0.
    Read as plain utf-8 the config vanishes, and C3 announces "no completion
    recorded" for every pipeline phase — permanently, with a remediation the
    operator can follow and that will not help. The sibling config readers were
    BOM-hardened for exactly this; this one is now too."""
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"phase_history": {"build": [
            {"run_id": "r-1", "event_at": "2026-07-27T10:00:00+00:00"}]}}),
        encoding="utf-8-sig",
    )

    completion = latest_completion(tmp_path, "build")

    assert completion is not None and completion.run_id == "r-1"


def test_a_completion_can_be_narrowed_to_one_run(tmp_path):
    """C3 needs the owner's completion for the run the NOTE names, not the
    owner's latest: those differ exactly when the owner completed again without
    re-writing the note, and taking the latest excused a phase that had skipped
    its step. `known_run_ids` still spans everything, so membership is unchanged."""
    root = _cfg(tmp_path, {"deploy": [
        {"run_id": "d-1", "at": "2026-07-27T09:00:00+00:00"},
        {"run_id": "d-2", "at": "2026-07-27T12:00:00+00:00"},
    ]})

    narrowed = latest_completion(root, "deploy", run_id="d-1")

    assert narrowed is not None and narrowed.run_id == "d-1"
    assert narrowed.wall is not None
    assert narrowed.wall.earliest == _at("2026-07-27T09:00:00+00:00")
    assert narrowed.known_run_ids == ("d-1", "d-2"), "membership must span all runs"
    assert latest_completion(root, "deploy", run_id="never-ran") is None


def test_a_malformed_run_config_is_none(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text("{not json", encoding="utf-8")

    assert latest_completion(tmp_path, "build") is None


def test_a_missing_run_config_is_none(tmp_path):
    assert latest_completion(tmp_path, "build") is None


def test_a_non_list_bucket_is_none(tmp_path):
    assert latest_completion(_cfg(tmp_path, {"build": "nope"}), "build") is None


def test_an_entry_with_an_unusable_time_still_yields_the_run_id(tmp_path):
    """`when` and `run_id` fail independently: C3 must be able to say 'the run
    matches but I cannot order the two events'."""
    root = _cfg(tmp_path, {"build": [{"run_id": "r", "at": "nonsense"}]})

    completion = latest_completion(root, "build")

    assert completion is not None
    assert completion.run_id == "r"
    assert completion.wall is None


def test_it_reads_the_shapes_the_live_repo_actually_carries(tmp_path):
    """Compatibility with writer-produced JSON, not just hand-built fixtures
    (external plan review, openai R2).

    Snapshotted from this repo's own `shipwright_run_config.json` rather than
    read from it live: asserting against a tracked, mutable file makes an
    unrelated edit turn this suite red with a message pointing at the wrong
    thing. `test_completion_writers.py` covers the live writers.
    """
    root = _cfg(tmp_path, {
        # adopt, which has always stamped `at`
        "build": [{"outcome": "adopted", "run_id": "adopt-2026-05-02T183757",
                   "at": "2026-05-02T18:37:57.870696+00:00"}],
        # changelog, which stamped a bare `date` until this iterate
        "changelog": [{"run_id": "changelog-v0.26.0-20260613", "date": "2026-06-13",
                       "version": "v0.26.0", "outcome": "tagged"}],
    })

    adopted = latest_completion(root, "build")
    tagged = latest_completion(root, "changelog")

    assert adopted is not None and adopted.wall is not None
    assert adopted.wall.earliest == adopted.wall.latest, "`at` pins an instant"
    assert tagged is not None and tagged.wall is not None
    assert tagged.wall.earliest < tagged.wall.latest, "a bare `date` pins a day"
