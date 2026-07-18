"""Shared fixtures for the triage-repair regression suites.

Split out of `test_triage_repair.py` when that file crossed the 300-LOC gate
(iterate-2026-07-18-outbox-newline-corruption). Consumed by
`test_triage_repair.py` (scan + apply) and `test_triage_repair_safety.py`
(minimal-rewrite, refusals, lock ordering).

Underscore-prefixed so pytest does not collect it as a test module — same
convention as `_sweep_helpers.py`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import triage  # noqa: E402

APPEND = {"event": "append", "id": "trg-aaaaaaaa", "ts": "2026-07-18T10:00:00Z"}
STATUS = {"event": "status", "id": "trg-aaaaaaaa", "newStatus": "dismissed", "by": "webui"}


def j(obj: dict) -> str:
    """Canonical producer serialization — no spaces, matching `triage._append_line`."""
    return json.dumps(obj, separators=(",", ":"))


def project(tmp_path: Path) -> Path:
    (tmp_path / ".shipwright").mkdir(parents=True, exist_ok=True)
    return tmp_path


def corrupt_outbox(proj: Path, *, tail: str = "") -> Path:
    """The reported incident on disk: append + status on ONE physical line."""
    p = triage._outbox_path(proj)
    p.write_bytes((j(APPEND) + j(STATUS) + tail + "\n").encode())
    return p


def quarantine_path(proj: Path) -> Path:
    return proj / ".shipwright" / "triage.outbox.quarantine.jsonl"


def nonblank(path: Path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
