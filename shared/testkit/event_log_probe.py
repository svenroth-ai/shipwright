"""Layout-independent probes of an event log for tests (campaign events-drop-files, S4).

Stdlib only, no ``lib`` imports: usable from every pytest root (``sys.path.insert`` of
``shared/testkit``). A test that asserts "the event landed" must not care whether the
layout wrote ``shipwright_events.jsonl`` or a file in ``.shipwright/events/drops/`` -- the
standing replay gate runs the same tests under both. Tests that pin LEGACY BYTES keep
reading the legacy file directly and pin the layout (``pin_legacy``).
"""

from __future__ import annotations

import json
from pathlib import Path

LEGACY = "shipwright_events.jsonl"
FOLDERS = (".shipwright/events/archive", ".shipwright/events/drops")


def event_files(root: Path | str) -> list[Path]:
    """The existing event files of a tree: the legacy log, then archive and drop files by name."""
    base = Path(root)
    files = [base / LEGACY] if (base / LEGACY).exists() else []
    for folder in FOLDERS:
        files += sorted((base / folder).glob("*.jsonl")) if (base / folder).is_dir() else []
    return files


def event_log_exists(root: Path | str) -> bool:
    return bool(event_files(root))


def event_text(root: Path | str) -> str:
    return "".join(p.read_text(encoding="utf-8") for p in event_files(root))


def event_lines(root: Path | str) -> list[str]:
    return [ln for ln in event_text(root).splitlines() if ln.strip()]


def _parse(path: Path) -> list[dict]:
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def event_records(root: Path | str) -> list[dict]:
    """Parsed records in READER order: the legacy file in file order, then archive and drops by ``ts``
    (ISO strings of one format sort as instants; ties keep file order)."""
    files = event_files(root)
    legacy = [r for p in files if p.name == LEGACY for r in _parse(p)]
    extra = [r for p in files if p.name != LEGACY for r in _parse(p)]
    return legacy + sorted(extra, key=lambda r: str(r.get("ts", "")))


def pin_legacy(monkeypatch) -> None:
    """Pin the legacy layout for a test about legacy BYTES (it wins over the replay gate's override)."""
    monkeypatch.setenv("SHIPWRIGHT_EVENTS_LAYOUT_TEST", "1")
    monkeypatch.setenv("SHIPWRIGHT_EVENTS_LAYOUT", "legacy")


def effective_records(root: Path | str) -> list[dict]:
    """Records with ``event_amended`` folded onto their targets (as the product readers do)."""
    recs = event_records(root)
    amend = {r.get("amends"): r.get("fields", {}) for r in recs if r.get("type") == "event_amended"}
    return [{**r, **amend.get(r.get("id"), {})} for r in recs if r.get("type") != "event_amended"]
