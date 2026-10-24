"""The design-gate modules split out of ``design_gate_extras`` (campaign A2).

``check-design-gates.py`` loads them as TOP-LEVEL modules (it puts ``shared/scripts/lib``
on ``sys.path``), which takes the bare-import fallback. The existing tests load them as
``lib.*``; these load each by file path so the fallback branch runs in-process.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from lib.design_gate_html import (
    _external_host,
    chrome_nav_targets_consistent,
    screen_declares_nav,
    standalone_html_violations,
)
from lib.design_gate_result import GateResult
from lib.gate_catalog_render import _cell, render_catalog_doc

_LIB = Path(__file__).resolve().parents[1] / "scripts" / "lib"
_BARE = ("design_gate_result", "design_gate_html", "design_gate_feedback", "design_gate_extras")


@pytest.fixture(autouse=True)
def _no_bare_module_leak():
    """Drop any bare-named module a test imported, so other tests see only ``lib.*``."""
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        if name in _BARE:
            del sys.modules[name]


def _load_bare(monkeypatch, name: str):
    """Import ``name`` the way check-design-gates.py does: bare, lib dir on sys.path."""
    monkeypatch.syspath_prepend(str(_LIB))
    for mod in _BARE:  # force a fresh bare import
        monkeypatch.delitem(sys.modules, mod, raising=False)
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", _LIB / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", ["design_gate_html", "design_gate_feedback", "design_gate_extras"])
def test_modules_load_bare_via_fallback_imports(monkeypatch, name):
    module = _load_bare(monkeypatch, name)
    assert module.GateResult.__module__ == "design_gate_result"


def test_bare_extras_reexports_the_split_gates(monkeypatch):
    extras = _load_bare(monkeypatch, "design_gate_extras")
    for exported in ("GateResult", "chrome_nav_targets_consistent", "screen_declares_nav",
                     "standalone_html_violations", "iteration_touched_flagged_screens",
                     "parse_feedback_round"):
        assert exported in extras.__all__ and hasattr(extras, exported)


def test_screen_declares_nav():
    assert screen_declares_nav('<a class="nav-item" href="/a">A</a>')
    assert not screen_declares_nav("<p>no nav</p>")


def test_chrome_without_targets_and_screen_without_nav_is_ok():
    result = chrome_nav_targets_consistent("<div></div>", "<p>x</p>")
    assert isinstance(result, GateResult) and result.ok
    assert "declares no nav targets" in result.detail


def test_chrome_with_targets_and_screen_without_nav_is_exempt():
    result = chrome_nav_targets_consistent('<a class="nav-item" href="/a">A</a>', "<p>x</p>")
    assert result.ok and "exempt" in result.detail


def test_external_host_edge_cases():
    assert _external_host("") is None
    assert _external_host("  \t\n") is None
    assert _external_host("local.css") is None
    assert _external_host("mailto:a@b.example") is None
    assert _external_host("//cdn.example/x.js") == "cdn.example"
    assert _external_host("https:evil.example/x") == ""  # external scheme, no host
    assert standalone_html_violations('<img src="https:evil.example/x">') == ["https:evil.example/x"]


def test_standalone_flags_only_external_non_font_hosts():
    html = ('<link href="https://fonts.googleapis.com/css"><script src="//cdn.example/x.js"></script>'
            '<img src="local.png">')
    assert standalone_html_violations(html) == ["//cdn.example/x.js"]


def test_gate_catalog_cell_helper():
    assert _cell(None) == "-"
    assert _cell("") == "-"
    assert _cell("a | b\nc ") == "a \\| b c"


def test_render_catalog_doc_handles_missing_description_and_pending_note():
    catalog = {"gates": {}, "policies": {}, "pending_phases": {"phases": ["x"], "note": "later"}}
    doc = render_catalog_doc(
        catalog, policies_order=("p",), covered_phases=("project",), auto_default="auto-default",
    )
    assert "**Pending (follow-up):** x - later" in doc
    assert doc.isascii() and doc.endswith("\n")
