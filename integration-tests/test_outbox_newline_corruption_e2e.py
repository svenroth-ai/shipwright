"""E2E: the reported incident, end to end, across writer + reader + repair CLI.

Reproduces the real-world failure exactly as observed
(iterate-2026-07-18-outbox-newline-corruption): a record written without a trailing
newline, the next writer appending onto that same physical line, and the dismissal
on it silently failing to propagate.

This is the F0.5 behavior surface (cli): it drives the actual public API and the
actual CLI entry point, not the internals.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import triage  # noqa: E402

_REPAIR_CLI = _SHARED_SCRIPTS / "tools" / "triage_repair.py"


def _project(tmp_path: Path) -> Path:
    (tmp_path / ".shipwright").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_the_reported_incident_end_to_end(tmp_path: Path) -> None:
    """A WebUI dismissal concatenated onto an append must still close the item."""
    project = _project(tmp_path)

    # 1. A background producer files a finding into the gitignored outbox.
    item_id = triage.append_triage_item(
        project, source="compliance", severity="medium", kind="bug",
        title="something to fix", detail="d", to_outbox=True,
    )
    assert {i["id"]: i["status"] for i in triage.read_all_items(project)}[item_id] == "triage"

    # 2. Reproduce the corruption: a writer left no trailing newline, so the WebUI's
    #    status record landed on the SAME physical line as the append.
    outbox = triage._outbox_path(project)
    unterminated = outbox.read_text(encoding="utf-8").rstrip("\n")
    status = {
        "event": "status", "id": item_id, "ts": "2026-07-18T10:05:00Z",
        "newStatus": "dismissed", "by": "webui", "reason": "Implemented",
    }
    outbox.write_bytes(
        (unterminated + json.dumps(status, separators=(",", ":")) + "\n").encode()
    )
    assert len([ln for ln in outbox.read_text(encoding="utf-8").splitlines() if ln.strip()]) == 1

    # 3. THE BUG: before the fix the reader dropped both records and the item still
    #    read as open. It must now read as dismissed.
    items = {i["id"]: i for i in triage.read_all_items(project)}
    assert items[item_id]["status"] == "dismissed", "the dismissal must propagate"

    # 4. The corruption is still on disk, where the sweep would fold it verbatim into
    #    the tracked log. The repair CLI reports it (exit 1) without mutating.
    before = outbox.read_bytes()
    report = subprocess.run(
        [sys.executable, str(_REPAIR_CLI), "--project-root", str(project)],
        capture_output=True, text=True,
    )
    assert report.returncode == 1, report.stdout + report.stderr
    assert "NEEDS REPAIR" in report.stdout
    assert outbox.read_bytes() == before, "report mode must not mutate"

    # 5. --apply without the quiesce acknowledgement is refused (inode-swap safety).
    refused = subprocess.run(
        [sys.executable, str(_REPAIR_CLI), "--project-root", str(project), "--apply"],
        capture_output=True, text=True,
    )
    assert refused.returncode == 2
    assert outbox.read_bytes() == before

    # 6. With the acknowledgement it repairs, splitting the line and keeping BOTH
    #    records.
    applied = subprocess.run(
        [sys.executable, str(_REPAIR_CLI), "--project-root", str(project),
         "--apply", "--writers-quiesced"],
        capture_output=True, text=True,
    )
    assert applied.returncode == 0, applied.stdout + applied.stderr

    lines = [ln for ln in outbox.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2, lines
    events = [json.loads(ln)["event"] for ln in lines]
    assert events == ["append", "status"]

    # 7. The repaired file still resolves to the same user-visible state.
    after = {i["id"]: i for i in triage.read_all_items(project)}
    assert after[item_id]["status"] == "dismissed"


def test_next_append_after_the_fix_cannot_concatenate(tmp_path: Path) -> None:
    """The prevention half: the writer terminates, so this cannot recur."""
    project = _project(tmp_path)
    outbox = triage._outbox_path(project)
    outbox.write_bytes(b'{"event":"append","id":"trg-deadbeef","ts":"2026-07-18T09:00:00Z"}')

    triage.append_triage_item(
        project, source="compliance", severity="low", kind="improvement",
        title="next writer", detail="d", to_outbox=True,
    )

    lines = [ln for ln in outbox.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    for ln in lines:
        json.loads(ln)
