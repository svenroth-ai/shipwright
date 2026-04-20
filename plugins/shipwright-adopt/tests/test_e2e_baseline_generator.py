"""Unit tests for e2e_baseline_generator."""

from pathlib import Path

from lib.e2e_baseline_generator import render_baseline_spec, write_baseline_spec


SAMPLE_ROUTES = [
    {
        "url": "/dashboard",
        "title": "Dashboard",
        "h1": "Active Projects",
        "buttons": ["+ New", "Filter", "Export"],
    },
    {"url": "/settings", "title": "Settings", "h1": "Account", "buttons": []},
]


def test_render_produces_valid_ts() -> None:
    out = render_baseline_spec(SAMPLE_ROUTES)
    assert "import { test, expect }" in out
    assert "FR-01.01" in out
    assert "FR-01.02" in out
    assert "/dashboard" in out
    assert "/settings" in out
    assert "Active Projects" in out


def test_render_empty_routes() -> None:
    out = render_baseline_spec([])
    assert "No routes crawled" in out


def test_write_to_filesystem(tmp_path: Path) -> None:
    path = write_baseline_spec(tmp_path, SAMPLE_ROUTES)
    assert path.exists()
    assert path.name == "adopted-baseline.spec.ts"
    assert path.parent.name == "flows"
    assert path.parent.parent.name == "e2e"


def test_escape_safe() -> None:
    routes = [{"url": "/test", "title": "O'Reilly's guide", "h1": "Don't break", "buttons": []}]
    out = render_baseline_spec(routes)
    # h1 must be correctly escaped inside the TS string literal
    assert "Don\\'t break" in out
    # test title stripped of special chars (becomes "ORellys guide" or similar)
    # -> confirm no raw unescaped apostrophe survives in the JS string arg
    assert "'Don't" not in out  # would be a TS syntax error
