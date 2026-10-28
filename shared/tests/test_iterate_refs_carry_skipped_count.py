"""The iterate references must tell the agent to record the skipped-test count.

The WebUI ratchet requires ``tests.passed + tests.skipped == tests.total`` on
events recorded after 2026-08-08. ``record_event.py`` already supports
``--tests-skipped`` and ``lib.iterate_tests_block.fold_into_event`` already sums
``iterate_latest.<layer>.skipped``; the F7 template and the F5 layer shape just
never asked for it, so a run with skipped tests produced a red consumer check.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REFS = (Path(__file__).resolve().parents[2]
        / "plugins" / "shipwright-iterate" / "skills" / "iterate" / "references")


@pytest.mark.covers("FR-01.11")
def test_f7_record_event_template_passes_tests_skipped():
    text = (REFS / "F7.md").read_text(encoding="utf-8")
    cmd = re.search(r"record_event\.py\"[^`]*?--tests-total", text, re.S)
    assert cmd and "--tests-skipped" in cmd.group(0)


@pytest.mark.covers("FR-01.11")
def test_f5_layer_shape_documents_skipped():
    text = (REFS / "F5.md").read_text(encoding="utf-8")
    for layer in ("unit", "integration", "pgtap", "e2e"):
        line = next((ln for ln in text.splitlines() if f'"{layer}": {{' in ln), None)
        assert line is not None, f"{layer} row missing from F5.md"
        assert '"skipped"' in line, layer
