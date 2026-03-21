"""Tests for screen registry."""

from pathlib import Path

from screen_registry import generate_manifest, scan_designs_dir, write_manifest


def test_scan_empty_dir(tmp_path):
    designs = tmp_path / "designs"
    designs.mkdir()
    result = scan_designs_dir(designs)
    assert result["screens"] == []
    assert result["flows"] == []
    assert result["uploads"] == []
    assert result["has_visual_guidelines"] is False


def test_scan_with_screens(tmp_project_with_designs):
    designs = tmp_project_with_designs / "designs"
    result = scan_designs_dir(designs)
    assert len(result["screens"]) == 2
    assert result["screens"][0]["name"] == "login"
    assert result["screens"][0]["number"] == 1
    assert result["screens"][1]["name"] == "dashboard"


def test_scan_with_flows(tmp_project_with_designs):
    designs = tmp_project_with_designs / "designs"
    result = scan_designs_dir(designs)
    assert len(result["flows"]) == 1
    assert result["flows"][0]["name"] == "auth-flow"


def test_scan_with_uploads(tmp_project_with_designs):
    uploads = tmp_project_with_designs / "designs" / "uploads"
    (uploads / "mockup.png").write_text("fake png")
    (uploads / "header.html").write_text("<html>header</html>")

    result = scan_designs_dir(tmp_project_with_designs / "designs")
    assert len(result["uploads"]) == 2


def test_generate_manifest(tmp_project_with_designs):
    designs = tmp_project_with_designs / "designs"
    content = generate_manifest(designs, "My App", "supabase-nextjs")
    assert "# Design Manifest" in content
    assert "login" in content
    assert "dashboard" in content
    assert "auth-flow" in content
    assert "supabase-nextjs" in content


def test_write_manifest(tmp_project_with_designs):
    designs = tmp_project_with_designs / "designs"
    path = write_manifest(designs, "My App", "supabase-nextjs")
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "Design Manifest" in content


def test_scan_ignores_non_html(tmp_path):
    designs = tmp_path / "designs"
    (designs / "screens").mkdir(parents=True)
    (designs / "screens" / "notes.txt").write_text("not a screen")
    (designs / "screens" / "01-login.html").write_text("<html></html>")

    result = scan_designs_dir(designs)
    assert len(result["screens"]) == 1
