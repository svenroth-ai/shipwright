"""An `append` with a missing / null / unknown `status` reads as `triage`.

trg-87a3da4a (first half). It must be warned about but must NOT become
corruption: `corruption` is the WebUI contract for undecodable bytes, and a
new validator class would block the sweep via `has_non_orphan_error`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from triage import append_triage_item, read_all_items  # noqa: E402
from lib import triage_integrity, triage_status_normalize  # noqa: E402

TRIAGE_CLI = _SHARED_SCRIPTS / "tools" / "triage_cli.py"

pytestmark = pytest.mark.covers("FR-01.14/AC01")



def _record(item_id: str, **overrides) -> dict:
    rec = {"event": "append", "id": item_id, "ts": "2026-11-12T00:00:00Z",
           "source": "hand", "severity": "low", "kind": "bug",
           "title": f"title {item_id}", "detail": "d", "status": "triage"}
    rec.update(overrides)
    return {k: v for k, v in rec.items() if v is not ...}


def _seed(project: Path, *records: dict) -> None:
    append_triage_item(project, source="seed", severity="low", kind="bug",
                       title="seed", detail="d")
    path = project / ".shipwright" / "triage.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


@pytest.fixture(autouse=True)
def _fresh_warning_state():
    triage_status_normalize._WARNED.clear()
    yield
    triage_status_normalize._WARNED.clear()


CASES = {
    "missing": _record("trg-00000001", status=...),
    "null": _record("trg-00000002", status=None),
    "unknown": _record("trg-00000003", status="open"),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_malformed_status_reads_as_triage(tmp_path: Path, name: str, capsys) -> None:
    rec = CASES[name]
    _seed(tmp_path, rec)
    item = next(i for i in read_all_items(tmp_path) if i["id"] == rec["id"])
    assert item["status"] == "triage"
    err = capsys.readouterr().err
    assert "integrity warning" in err and rec["id"] in err


@pytest.mark.parametrize("name", sorted(CASES))
def test_malformed_status_is_not_corruption(tmp_path: Path, name: str) -> None:
    _seed(tmp_path, CASES[name])
    assert triage_integrity.store_corruption(tmp_path / ".shipwright" / "triage.jsonl") == []


def test_warns_once_per_id(tmp_path: Path, capsys) -> None:
    _seed(tmp_path, CASES["missing"])
    read_all_items(tmp_path)
    read_all_items(tmp_path)
    assert capsys.readouterr().err.count("integrity warning") == 1


def test_valid_status_is_untouched_and_silent(tmp_path: Path, capsys) -> None:
    _seed(tmp_path, _record("trg-00000004", status="dismissed"))
    item = next(i for i in read_all_items(tmp_path) if i["id"] == "trg-00000004")
    assert item["status"] == "dismissed"
    assert "integrity warning" not in capsys.readouterr().err


def test_a_later_status_event_still_wins(tmp_path: Path) -> None:
    status = {"event": "status", "id": "trg-00000001", "ts": "2026-11-12T01:00:00Z",
              "newStatus": "dismissed", "by": "t", "reason": "r"}
    _seed(tmp_path, CASES["missing"], status)
    item = next(i for i in read_all_items(tmp_path) if i["id"] == "trg-00000001")
    assert item["status"] == "dismissed"


def test_cli_list_shows_all_three_as_open_with_warning(tmp_path: Path) -> None:
    _seed(tmp_path, *CASES.values())
    res = subprocess.run(
        [sys.executable, str(TRIAGE_CLI), "--project-root", str(tmp_path), "list", "--json"],
        capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stderr
    open_ids = {i["id"] for i in json.loads(res.stdout)["open"]}
    assert {r["id"] for r in CASES.values()} <= open_ids
    assert res.stderr.count("integrity warning") == 3
    assert "unrecoverable" not in res.stderr


def test_gc_resolver_agrees_with_the_reader(tmp_path: Path) -> None:
    from lib import triage_gc_resolve  # noqa: PLC0415
    _seed(tmp_path, *CASES.values())
    reader = {i["id"]: i["status"] for i in read_all_items(tmp_path)}
    gc = {i["id"]: i["status"] for i in triage_gc_resolve.resolve_tracked_only(tmp_path)}
    for rec in CASES.values():
        assert reader[rec["id"]] == gc[rec["id"]] == "triage"
