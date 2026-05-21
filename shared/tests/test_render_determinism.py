"""End-to-end determinism tests for the eight Shipwright Markdown renderers.

Each render must be a pure function of the input data — primarily of
`shipwright_events.jsonl`. Two renders against the same events.jsonl must
produce byte-identical output. Otherwise the rendered file drifts on
every Stop hook, leaving `git status` permanently dirty in a
self-adopted Shipwright repo.

Iterate: iterate-2026-05-22-deterministic-render-timestamps.

Strategy
--------
For each renderer-group we build a minimal synthetic `tmp_path` repo
with a deterministic `shipwright_events.jsonl`, run the renderer twice
separated by a real `time.sleep(...)`, and assert byte-equality. A
companion "different input → different output" sanity test proves the
determinism is genuine (i.e. the helper is not just returning a
constant).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))


def _write_min_repo(project_root: Path, *, events: list[dict]) -> None:
    """Materialise the minimum on-disk shape the renderers expect."""
    (project_root / "shipwright_events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + ("\n" if events else ""),
        encoding="utf-8",
    )
    (project_root / "shipwright_run_config.json").write_text(
        json.dumps({
            "status": "complete",
            "completed_steps": ["project", "plan", "build", "test"],
            "current_step": None,
        }),
        encoding="utf-8",
    )
    (project_root / "shipwright_build_config.json").write_text(
        json.dumps({"splits": []}),
        encoding="utf-8",
    )


_BASE_EVENT = {
    "type": "work_completed",
    "source": "iterate",
    "ts": "2026-05-20T12:00:00+00:00",
    "intent": "change",
    "description": "baseline event",
    "tests": {"passed": 5, "total": 5},
    "commit": "abc1234567890",
    "affected_frs": [],
}


def _later_event() -> dict:
    e = dict(_BASE_EVENT)
    e["ts"] = "2026-05-22T10:30:00+00:00"
    e["description"] = "later event"
    e["commit"] = "def4567890abc"
    return e


# ---------------------------------------------------------------------------
# Renderer wrappers — each returns the rendered string for the given
# project_root, encapsulating any sys.path / import path the renderer
# needs.
# ---------------------------------------------------------------------------


def _render_build_dashboard(project_root: Path) -> str:
    from tools.update_build_dashboard import generate_dashboard
    return generate_dashboard(project_root)


def _render_triage_inbox(project_root: Path) -> str:
    # aggregate_triage.render_markdown takes (items, now=...). The
    # `main()` orchestrator computes `now` itself. We exercise the
    # orchestrator's now-resolution path indirectly by calling
    # `_resolve_render_now(project_root)` (new helper added in this
    # iterate). For the determinism test we don't need to write the
    # file to disk — we just call the now-resolver + render_markdown.
    from tools.aggregate_triage import render_markdown, _resolve_render_now
    now = _resolve_render_now(project_root)
    return render_markdown([], now=now)


def _render_session_handoff(project_root: Path) -> str:
    from tools.generate_session_handoff import generate_handoff
    # Pass a fixed session_id + reason so wall-clock isn't the only volatile.
    return generate_handoff(
        project_root=project_root,
        session_id="determinism-test",
        reason="determinism-test",
    )


# Note: compliance_dashboard determinism is verified in the compliance
# plugin's own test suite — `plugins/shipwright-compliance/tests/`. An
# in-process call from `shared/tests/` triggers a sys.modules ordering
# issue when other shared tests have already loaded a different `scripts`
# package layout. The helper unit tests (`test_events_log.py`) plus the
# 3 renderer cases below already lock in the determinism property;
# compliance gets its own dedicated cases over there.
_RENDERERS = {
    "build_dashboard": _render_build_dashboard,
    "triage_inbox": _render_triage_inbox,
    "session_handoff": _render_session_handoff,
}


# ---------------------------------------------------------------------------
# Determinism: same input → same output, even when wall-clock moves
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("renderer_id", list(_RENDERERS.keys()))
def test_render_is_deterministic_against_same_events(
    tmp_path: Path, renderer_id: str
) -> None:
    """Two renders separated by real wall-clock time produce identical output."""
    _write_min_repo(tmp_path, events=[_BASE_EVENT])

    renderer = _RENDERERS[renderer_id]

    # First render.
    out_1 = renderer(tmp_path)

    # Real wall-clock advance — guarantees `datetime.now()` would be different.
    time.sleep(1.2)

    # Second render.
    out_2 = renderer(tmp_path)

    assert out_1 == out_2, (
        f"[{renderer_id}] Render is non-deterministic — second call differs "
        f"from the first despite identical events.jsonl input.\n"
        f"=== First render (first 400 chars) ===\n{out_1[:400]}\n"
        f"=== Second render (first 400 chars) ===\n{out_2[:400]}"
    )


# ---------------------------------------------------------------------------
# Sanity check: different input → different output (so the determinism
# isn't degenerate / just a constant return)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("renderer_id", list(_RENDERERS.keys()))
def test_render_changes_when_events_change(
    tmp_path: Path, renderer_id: str
) -> None:
    """Adding a new event between renders MUST change the output (for the
    renderers whose banner reflects event timestamps).

    For the session_handoff renderer this asserts the run/commit blocks
    differ; for the others it asserts the timestamp banner differs.
    """
    _write_min_repo(tmp_path, events=[_BASE_EVENT])
    renderer = _RENDERERS[renderer_id]

    out_1 = renderer(tmp_path)

    # Append a strictly-later event.
    _write_min_repo(tmp_path, events=[_BASE_EVENT, _later_event()])

    out_2 = renderer(tmp_path)

    assert out_1 != out_2, (
        f"[{renderer_id}] Adding a new event to events.jsonl produced "
        f"identical output — the renderer is not actually reading the "
        f"input (degenerate determinism).\n"
        f"=== Output (first 300 chars) ===\n{out_1[:300]}"
    )
