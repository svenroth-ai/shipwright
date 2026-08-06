"""Boundary Probe — producer -> file -> consumer, through the real CLI.

``touches_io_boundary`` is declared by hand for
iterate-2026-08-06-p2-19c-corruption-absence: the change alters a record decoder,
a file-read encoding path and a machine-readable output contract. The path-based
detector does not fire on any of these files, so the flag — and this probe — are a
deliberate choice rather than a derived one.

What a round-trip buys that the unit tests do not: the units call
``build_listing`` and ``undelivered_status_ids`` directly with hand-built inputs.
This drives the **real writers** (``triage.append_triage_item`` / ``mark_status``)
into **real files**, then runs ``triage_cli.py`` as a **subprocess** and parses its
stdout. Nothing is stubbed, so a wiring mistake between the three — the exact
failure a unit test cannot see — shows up here.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[1]
_SCRIPTS = _SHARED / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import triage  # noqa: E402

_CLI = _SCRIPTS / "tools" / "triage_cli.py"


def _run_cli(project: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SCRIPTS)
    return subprocess.run(
        [sys.executable, str(_CLI), "--project-root", str(project), "list", *args],
        capture_output=True, text=True, timeout=120, env=env,
    )


def _project(tmp_path: Path) -> Path:
    (tmp_path / ".shipwright").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _add(project: Path, *, title: str, to_outbox: bool) -> str:
    return triage.append_triage_item(
        project, source="manual", severity="low", kind="bug",
        title=title, detail="d", to_outbox=to_outbox,
    )


def test_buffered_decision_round_trips_to_the_json_contract(tmp_path: Path, monkeypatch) -> None:
    """A dismiss written only to the outbox must read back as NOT yet committed.

    This is the whole of finding 28 end to end: the writer puts the status event in
    the gitignored buffer, and the consumer has to be able to say so.
    """
    project = _project(tmp_path)
    item_id = _add(project, title="will be dismissed", to_outbox=False)
    # Force the flip into the outbox the way idle main does.
    monkeypatch.setattr(triage, "should_route_to_outbox", lambda root: True)
    triage.mark_status(project, item_id, new_status="dismissed", by="webui",
                       reason="done")

    result = _run_cli(project, "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    # The dismiss resolved, so the item is in NEITHER section. That is exactly why
    # a per-row flag cannot carry this case — the ENVELOPE has to.
    assert payload["contractVersion"] == 2
    assert all(r["id"] != item_id for r in payload["open"])
    assert all(r["id"] != item_id for r in payload["deferred"])

    # The assertion that matters, made THROUGH the CLI's own stdout. An earlier
    # version of this test abandoned the subprocess here and called the library
    # in-process, so it confirmed the gap its name claimed to disprove (Stage-3
    # doubt): the JSON consumer saw "everything delivered" on a buffered store.
    assert payload["undeliveredDecisions"]["count"] == 1
    assert payload["undeliveredDecisions"]["ids"] == [item_id]
    assert payload["undeliveredDecisions"]["truncated"] is False


def test_open_item_with_a_buffered_flip_carries_the_field(tmp_path: Path, monkeypatch) -> None:
    """A row that IS listed carries the boolean, and a clean one carries False."""
    project = _project(tmp_path)
    parked = _add(project, title="parked", to_outbox=False)
    clean = _add(project, title="clean", to_outbox=False)
    monkeypatch.setattr(triage, "should_route_to_outbox", lambda root: True)
    triage.mark_status(project, parked, new_status="snoozed", by="webui",
                       reason="later", revisit_at="2099-01-01")

    payload = json.loads(_run_cli(project, "--json").stdout)
    rows = {r["id"]: r for r in payload["open"] + payload["deferred"]}

    assert rows[parked]["pendingStatusDelivery"] is True
    assert rows[clean]["pendingStatusDelivery"] is False
    # The pre-existing field keeps its own, different meaning.
    assert rows[clean]["pendingDelivery"] is False


def test_human_listing_names_the_uncommitted_decisions(tmp_path: Path, monkeypatch) -> None:
    """The operator surface that finding 28 says did not exist anywhere."""
    project = _project(tmp_path)
    item_id = _add(project, title="dismissed in the buffer", to_outbox=False)
    monkeypatch.setattr(triage, "should_route_to_outbox", lambda root: True)
    triage.mark_status(project, item_id, new_status="dismissed", by="webui",
                       reason="done")

    result = _run_cli(project)
    assert result.returncode == 0, result.stderr
    assert "not committed to any branch yet" in result.stdout
    assert item_id in result.stdout
    # It must not claim more than it can prove.
    assert "reached origin" not in result.stdout


def test_a_fully_delivered_store_says_nothing(tmp_path: Path, monkeypatch) -> None:
    """No false alarm: a decision in the tracked store is not reported pending."""
    project = _project(tmp_path)
    item_id = _add(project, title="tracked", to_outbox=False)
    monkeypatch.setattr(triage, "should_route_to_outbox", lambda root: False)
    triage.mark_status(project, item_id, new_status="dismissed", by="cli",
                       reason="done")

    result = _run_cli(project)
    assert result.returncode == 0, result.stderr
    assert "not committed to any branch" not in result.stdout


def test_repair_does_not_delete_the_record_the_reader_recovers(tmp_path: Path) -> None:
    """The loss path this change created, and closed. Found by Stage-1 spec review.

    ``_iter_raw_lines_at`` recovers a record sitting behind a damaged prefix, and
    the corruption notice tells the operator to run ``triage_repair.py``. That tool
    read the same line with NO predicate, so it recovered nothing, quarantined the
    whole line and republished the file **without** the record — turning a reader
    improvement into a writer that destroys what the reader just saved. Measured
    before the fix: the survivor was absent from the rewritten content.
    """
    from tools.triage_repair import scan_path

    project = _project(tmp_path)
    store = triage._outbox_path(project)
    truncated = '{"event":"append","id":"trg-aaaa","ts":"1'
    survivor = {"event": "append", "id": "trg-survivor", "ts": "2026-01-01T00:00:00Z",
                "source": "manual", "severity": "low", "kind": "bug",
                "title": "t", "detail": "d", "status": "triage"}
    store.write_bytes((truncated + json.dumps(survivor, separators=(",", ":"))
                       + "\n").encode())

    # The reader sees it...
    assert [r["id"] for r in triage._iter_raw_lines_at(store)] == ["trg-survivor"]
    # ...and the repair tool must keep it.
    report = scan_path(store)
    assert any("trg-survivor" in line for line in report.lines), report.lines
    # The damaged prefix is still quarantined — recovery, not tolerance.
    assert any(truncated in span for span in report.unrecoverable)


def test_json_stays_parseable_when_a_store_is_corrupt(tmp_path: Path) -> None:
    """The corruption notice goes to stderr; stdout must remain valid JSON.

    A reporting path that contaminated stdout would turn "corruption is now
    observable" into "the machine contract broke" (external plan review round 2).
    """
    project = _project(tmp_path)
    _add(project, title="ok", to_outbox=False)
    outbox = triage._outbox_path(project)
    outbox.write_bytes(b'}{unrecoverable\n')

    result = _run_cli(project, "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)          # the assertion that matters
    assert payload["contractVersion"] == 2
    assert "unrecoverable" in result.stderr or "outbox" in result.stderr
    # And the damage is reported as DATA, not only as a stderr line a pipe drops.
    assert payload["corruption"]["count"] == 1
    assert payload["corruption"]["spans"][0]["path"] == "triage.outbox.jsonl"


def test_a_clean_store_reports_no_undelivered_decisions(tmp_path: Path, monkeypatch) -> None:
    """No false alarm on the envelope block either."""
    project = _project(tmp_path)
    item_id = _add(project, title="tracked", to_outbox=False)
    monkeypatch.setattr(triage, "should_route_to_outbox", lambda root: False)
    triage.mark_status(project, item_id, new_status="dismissed", by="cli", reason="done")

    payload = json.loads(_run_cli(project, "--json").stdout)
    assert payload["undeliveredDecisions"] == {
        "count": 0, "truncated": False, "ids": []}
