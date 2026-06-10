"""Tests for `triage_cli.py list --json` — the machine-readable contract.

iterate-2026-06-10-triage-list-json. The WebUI live-view (trg-e2a0ebb3) consumes
this instead of re-parsing JSONL: it emits the SAME unioned (tracked ∪ outbox),
status==triage items the human `list` shows, as a JSON array, plus a
`pendingDelivery` boolean so the UI can badge outbox-only (not-yet-swept) items.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from triage import append_triage_item, mark_status  # noqa: E402

TRIAGE_CLI = _SHARED_SCRIPTS / "tools" / "triage_cli.py"
OUTBOX_REL = ".shipwright/triage.outbox.jsonl"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TRIAGE_CLI), *args],
        capture_output=True, text=True, check=False,
    )


def _list_json(project: Path) -> list[dict]:
    res = _run(["--project-root", str(project), "list", "--json"])
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _write_outbox(project: Path, *appends: dict) -> None:
    p = project / OUTBOX_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(a) + "\n" for a in appends), encoding="utf-8")


@pytest.fixture
def tracked_item(tmp_path: Path) -> str:
    return append_triage_item(
        tmp_path, source="github", severity="high", kind="bug",
        title="GitHub security", detail="ctx", dedup_key="gh-security:acme/foo",
        launch_payload="/shipwright-security\n\nContext: foo.",
    )


def test_list_json_emits_array_of_open_items(tmp_path: Path, tracked_item: str) -> None:
    data = _list_json(tmp_path)
    assert isinstance(data, list) and len(data) == 1
    item = data[0]
    assert item["id"] == tracked_item
    assert item["status"] == "triage"
    assert item["launchPayload"].startswith("/shipwright-security")
    assert item["pendingDelivery"] is False  # lives in the tracked log


def test_list_json_empty_is_empty_array(tmp_path: Path) -> None:
    assert _list_json(tmp_path) == []


def test_list_json_excludes_dismissed(tmp_path: Path, tracked_item: str) -> None:
    mark_status(tmp_path, tracked_item, new_status="dismissed", by="x", reason="r")
    assert _list_json(tmp_path) == []


def test_list_json_marks_outbox_only_pending_delivery(tmp_path: Path) -> None:
    """An item living ONLY in the gitignored outbox buffer (not yet swept to the
    tracked log) appears with pendingDelivery=true — the WebUI badge signal."""
    _write_outbox(tmp_path, {
        "event": "append", "id": "trg-outbox01", "ts": "2026-06-10T00:00:00Z",
        "source": "manual", "severity": "low", "kind": "improvement",
        "title": "outbox-only item", "status": "triage",
    })
    by_id = {d["id"]: d for d in _list_json(tmp_path)}
    assert "trg-outbox01" in by_id
    assert by_id["trg-outbox01"]["pendingDelivery"] is True


def test_list_json_tracked_preferred_when_in_both(tmp_path: Path, tracked_item: str) -> None:
    """TRACKED-PREFERRED: an id present in BOTH files is pendingDelivery=false
    (the tracked copy ships in the PR; the outbox copy is GC'd post-delivery)."""
    _write_outbox(tmp_path, {
        "event": "append", "id": tracked_item, "ts": "2026-06-10T00:00:00Z",
        "source": "github", "severity": "high", "kind": "bug",
        "title": "dup", "status": "triage",
    })
    [it] = [d for d in _list_json(tmp_path) if d["id"] == tracked_item]
    assert it["pendingDelivery"] is False


def test_list_default_output_is_not_json(tmp_path: Path, tracked_item: str) -> None:
    """Regression: the human-readable default (no --json) is unchanged."""
    res = _run(["--project-root", str(tmp_path), "list"])
    assert res.returncode == 0
    assert tracked_item in res.stdout
    with pytest.raises(json.JSONDecodeError):
        json.loads(res.stdout)
