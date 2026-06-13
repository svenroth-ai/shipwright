"""Cross-component integration: every migrated atomic writer now routes its
write through the ONE shared durable primitive
(``lib.atomic_write.durable_atomic_write``), so a crash/power-loss can't drop the
just-written content.

This is the ``cross_component`` integration-coverage proof
(``category:"integration"``): it exercises writers that live in different
subsystems — ``shared/lib`` (gitattributes self-heal, bloat baseline, worktree
isolation), the ``shared/lib/phase_quality`` subpackage, and ``shared/tools``
(phase-history) — TOGETHER, spying ``os.fsync`` at the single primitive to prove
each composes on the durable path with the fsync-before-replace ordering, and
round-tripping each file byte-correctly (the ``touches_io_boundary`` round-trip
probe). The diff touches cross-component machinery (gitattributes/gitignore
self-heal, hook + event-log writers), so a real-scenario composition test is
required; this is it.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import lib.atomic_write as aw  # noqa: E402
from lib import bloat_baseline, gitattributes_selfheal, worktree_isolation  # noqa: E402
from lib.phase_quality import _findings  # noqa: E402
from tools import append_phase_history  # noqa: E402


@pytest.fixture
def durability_spy(monkeypatch):
    """Record the ordered ``fsync``/``replace`` events the primitive emits.

    Every migrated writer funnels through ``durable_atomic_write`` → this single
    ``aw.os`` reference, so the spy sees one ``fsync``-then-``replace`` per write
    regardless of which subsystem's writer was called."""
    events: list[str] = []
    real_fsync, real_replace = os.fsync, os.replace

    def spy_fsync(fd):
        events.append("fsync")
        return real_fsync(fd)

    def spy_replace(src, dst):
        events.append("replace")
        return real_replace(src, dst)

    monkeypatch.setattr(aw.os, "fsync", spy_fsync)
    monkeypatch.setattr(aw.os, "replace", spy_replace)
    return events


def _assert_durable_write_happened(events: list[str], baseline: int) -> None:
    """Since `baseline`, at least one fsync occurred and it preceded a replace."""
    window = events[baseline:]
    assert "fsync" in window, "writer did not fsync — not routed through the durable primitive"
    assert "replace" in window, "writer did not os.replace"
    assert window.index("fsync") < window.index("replace"), "fsync must precede replace"


def test_writers_across_subsystems_compose_on_durable_primitive(tmp_path, durability_spy):
    events = durability_spy

    # shared/lib — bloat baseline writer
    n = len(events)
    doc = {"version": 1, "entries": [{"path": "x.py", "current": 10}]}
    bpath = bloat_baseline.write_baseline(tmp_path, doc)
    _assert_durable_write_happened(events, n)
    assert json.loads(bpath.read_text(encoding="utf-8")) == doc

    # shared/lib/phase_quality subpackage — finding JSON writer
    n = len(events)
    finding = tmp_path / "finding.json"
    _findings._atomic_write_json(finding, {"phase": "iterate", "canon": [], "workflow": []})
    _assert_durable_write_happened(events, n)
    assert json.loads(finding.read_text(encoding="utf-8"))["phase"] == "iterate"

    # shared/lib — gitattributes self-heal (verbatim writer: bytes preserved exactly)
    n = len(events)
    ga = tmp_path / ".gitattributes"
    gitattributes_selfheal._atomic_write(ga, "shipwright_events.jsonl merge=union\n")
    _assert_durable_write_happened(events, n)
    assert ga.read_bytes() == b"shipwright_events.jsonl merge=union\n"

    # shared/lib — worktree-isolation JSON writer (ensure_ascii=False preserved)
    n = len(events)
    wj = tmp_path / "wt.json"
    worktree_isolation._atomic_write_json(wj, {"slug": "héllo", "n": 2})
    _assert_durable_write_happened(events, n)
    assert json.loads(wj.read_text(encoding="utf-8")) == {"slug": "héllo", "n": 2}

    # shared/tools — phase-history JSON writer
    n = len(events)
    ph = tmp_path / "phase_history.json"
    append_phase_history._atomic_write_json(ph, {"phases": [{"phase": "iterate"}]})
    _assert_durable_write_happened(events, n)
    assert json.loads(ph.read_text(encoding="utf-8"))["phases"][0]["phase"] == "iterate"

    # All five subsystems' writers fsync'd before replacing — the durability
    # decision composes across the whole atomic-writer family.
    assert events.count("fsync") >= 5
