"""Tests for visual_compare.py --screen filtering."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from lib.visual_compare import run_visual_comparison


@pytest.fixture
def project_with_routes(tmp_path):
    """Create a minimal project with screen-routes.json and mockup files."""
    designs = tmp_path / "designs"
    screens = designs / "screens"
    screens.mkdir(parents=True)

    routes = {
        "01-login.html": "/login",
        "02-register.html": "/register",
        "03-dashboard.html": {"route": "/dashboard", "auth": "member"},
    }
    (designs / "screen-routes.json").write_text(json.dumps(routes), encoding="utf-8")

    # Create mockup HTML files
    for name in routes:
        (screens / name).write_text("<html><body>mockup</body></html>", encoding="utf-8")

    return tmp_path


def test_no_screen_filter_processes_all(project_with_routes):
    """Without --screen, all screens from screen-routes.json are compared."""
    with patch("lib.visual_compare._screenshot_page", return_value=True):
        result = run_visual_comparison(project_with_routes)

    assert result["skipped"] is False
    assert result["total"] == 3
    assert len(result["comparisons"]) == 3


def test_screen_filter_subset(project_with_routes):
    """With screens=["01-login.html"], only that screen is compared."""
    with patch("lib.visual_compare._screenshot_page", return_value=True):
        result = run_visual_comparison(project_with_routes, screens=["01-login.html"])

    assert result["total"] == 1
    assert len(result["comparisons"]) == 1
    assert result["comparisons"][0]["mockup"] == "01-login.html"


def test_screen_filter_multiple(project_with_routes):
    """With multiple screens, only those are compared."""
    with patch("lib.visual_compare._screenshot_page", return_value=True):
        result = run_visual_comparison(
            project_with_routes, screens=["01-login.html", "03-dashboard.html"]
        )

    assert result["total"] == 2
    mockups = {c["mockup"] for c in result["comparisons"]}
    assert mockups == {"01-login.html", "03-dashboard.html"}


def test_screen_filter_nonexistent_returns_error(project_with_routes):
    """Requesting a screen not in screen-routes.json returns an error."""
    result = run_visual_comparison(project_with_routes, screens=["99-nonexistent.html"])

    assert "error" in result
    assert "99-nonexistent.html" in result["error"]
    assert result["comparisons"] == []


def test_screen_filter_partial_nonexistent(project_with_routes):
    """If any requested screen is missing, all fail with error listing."""
    result = run_visual_comparison(
        project_with_routes, screens=["01-login.html", "99-missing.html"]
    )

    assert "error" in result
    assert "99-missing.html" in result["error"]


def test_no_routes_file(tmp_path):
    """No screen-routes.json → skipped result."""
    result = run_visual_comparison(tmp_path)
    assert result["skipped"] is True
    assert "No designs/screen-routes.json found" in result["skip_reason"]


def test_empty_routes(tmp_path):
    """Empty screen-routes.json → skipped result."""
    designs = tmp_path / "designs"
    designs.mkdir()
    (designs / "screen-routes.json").write_text("{}", encoding="utf-8")

    result = run_visual_comparison(tmp_path)
    assert result["skipped"] is True


def test_screens_none_same_as_omitted(project_with_routes):
    """screens=None behaves same as no filter (backward compatible)."""
    with patch("lib.visual_compare._screenshot_page", return_value=True):
        result = run_visual_comparison(project_with_routes, screens=None)

    assert result["total"] == 3
