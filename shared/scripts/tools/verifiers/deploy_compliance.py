"""Deploy-phase workflow compliance checks (Phase-Quality PR 2).

Implements W7 — smoke test status. Evidence sources (in priority
order):

1. ``shipwright_deploy_config.json.smoke_test_status`` (plan § 3)
2. ``shipwright_test_results.json.smoke.status`` (populated by
   ``record_event.py --type test_run --smoke-status …``)
3. Latest ``test_run`` event in ``shipwright_events.jsonl`` with a
   ``layers.smoke.status`` field.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.phase_quality import (  # noqa: E402
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    make_finding,
)
from tools.verifiers.common import read_events_jsonl  # noqa: E402


W7_NAME = "W7 smoke test passed"
W7_REMEDIATION = (
    "Re-run the deploy smoke test and record --smoke-status pass via "
    "record_event.py, or write smoke_test_status=pass into "
    "shipwright_deploy_config.json."
)


def _smoke_from_deploy_config(project_root: Path) -> str | None:
    path = project_root / "shipwright_deploy_config.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    raw = data.get("smoke_test_status")
    return str(raw) if isinstance(raw, str) else None


def _smoke_from_test_results(project_root: Path) -> str | None:
    path = project_root / "shipwright_test_results.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    smoke = data.get("smoke") or {}
    if isinstance(smoke, dict):
        raw = smoke.get("status")
        if isinstance(raw, str):
            return raw
    return None


def _smoke_from_events(project_root: Path) -> str | None:
    events = read_events_jsonl(project_root)
    latest: tuple[str, str] | None = None  # (ts, status)
    for e in events:
        if e.get("type") != "test_run":
            continue
        layers = e.get("layers") or {}
        smoke = layers.get("smoke") if isinstance(layers, dict) else None
        if not isinstance(smoke, dict):
            continue
        status = smoke.get("status")
        if not isinstance(status, str):
            continue
        ts = str(e.get("ts", ""))
        if latest is None or ts > latest[0]:
            latest = (ts, status)
    return latest[1] if latest else None


def check_w7_smoke_status(project_root: Path) -> dict[str, Any]:
    for source_fn, source_name in (
        (_smoke_from_deploy_config, "shipwright_deploy_config.json"),
        (_smoke_from_test_results, "shipwright_test_results.json"),
        (_smoke_from_events, "events.jsonl"),
    ):
        status = source_fn(project_root)
        if status is None:
            continue
        if status.lower() == "pass":
            return make_finding(
                "W7", STATUS_PASS,
                f"smoke_status=pass (source: {source_name})",
                name=W7_NAME,
            )
        return make_finding(
            "W7", STATUS_FAIL,
            f"smoke_status={status!r} (source: {source_name})",
            name=W7_NAME,
            remediation=W7_REMEDIATION,
        )
    return make_finding(
        "W7", STATUS_SKIP,
        "no smoke test evidence in deploy_config / test_results / events.jsonl",
        name=W7_NAME,
        remediation=W7_REMEDIATION,
    )


def run(project_root: Path, run_id: str) -> list[dict[str, Any]]:
    del run_id
    return [check_w7_smoke_status(project_root)]


__all__ = ["check_w7_smoke_status", "run"]
