"""Tests for design_fidelity_check.py — structural mockup vs implementation comparison."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from lib.design_fidelity_check import (
    _extract_implementation_structure,
    _extract_mockup_structure,
    _resolve_route_to_files,
    _run_auto_checks,
    run_design_fidelity_check,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCKUP_HTML = """\
<!DOCTYPE html>
<html>
<head><title>Login</title></head>
<body>
<main>
  <div class="flex items-center justify-center min-h-svh">
    <div class="card">
      <h1 class="text-2xl font-bold">Welcome</h1>
      <form class="form-field">
        <input type="email" />
        <input type="password" />
        <button>Login</button>
      </form>
    </div>
  </div>
</main>
</body>
</html>
"""

IMPL_TSX = """\
"use client";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

export default function LoginPage() {
  return (
    <main className="flex items-center justify-center min-h-svh bg-background">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>
            <h1 className="text-2xl font-bold">Welcome</h1>
          </CardTitle>
        </CardHeader>
        <CardContent className="gap-4">
          <form className="gap-4">
            <Label>Email</Label>
            <Input type="email" />
            <Label>Password</Label>
            <Input type="password" />
            <Button>Login</Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
"""


@pytest.fixture
def project_with_routes(tmp_path):
    """Create a minimal project with screen-routes.json, mockup, and implementation."""
    designs = tmp_path / "designs"
    screens = designs / "screens"
    screens.mkdir(parents=True)

    routes = {
        "screens/01-login.html": "/login",
        "screens/02-register.html": "/register",
        "screens/03-dashboard.html": {"route": "/dashboard", "auth": "member"},
    }
    (designs / "screen-routes.json").write_text(json.dumps(routes), encoding="utf-8")

    # Create mockup files
    for name in ["01-login.html", "02-register.html", "03-dashboard.html"]:
        (screens / name).write_text(MOCKUP_HTML, encoding="utf-8")

    # Create implementation files
    src_app = tmp_path / "src" / "app"
    for route_dir in ["login", "register", "dashboard"]:
        page_dir = src_app / route_dir
        page_dir.mkdir(parents=True)
        (page_dir / "page.tsx").write_text(IMPL_TSX, encoding="utf-8")

    return tmp_path


@pytest.fixture
def project_with_nested_routes(tmp_path):
    """Create a project with nested screen-routes.json format."""
    designs = tmp_path / "designs"
    screens_dir = designs / "screens"
    screens_dir.mkdir(parents=True)

    data = {
        "base_url": "http://localhost:5173",
        "screens": [
            {"mockup": "screens/10-kanban.html", "route": "/", "name": "Kanban"},
            {"mockup": "screens/11-inbox.html", "route": "/inbox", "name": "Inbox"},
        ],
    }
    (designs / "screen-routes.json").write_text(json.dumps(data), encoding="utf-8")

    for screen in data["screens"]:
        mockup_name = Path(screen["mockup"]).name
        (screens_dir / mockup_name).write_text(MOCKUP_HTML, encoding="utf-8")

    # Implementation
    src_app = tmp_path / "src" / "app"
    src_app.mkdir(parents=True)
    (src_app / "page.tsx").write_text(IMPL_TSX, encoding="utf-8")
    inbox = src_app / "inbox"
    inbox.mkdir()
    (inbox / "page.tsx").write_text(IMPL_TSX, encoding="utf-8")

    return tmp_path


# ---------------------------------------------------------------------------
# Mockup extraction tests
# ---------------------------------------------------------------------------

class TestMockupExtraction:
    def test_extracts_heading_levels(self):
        result = _extract_mockup_structure(MOCKUP_HTML)
        assert "h1" in result["heading_levels"]

    def test_extracts_layout_classes(self):
        result = _extract_mockup_structure(MOCKUP_HTML)
        assert any("flex" in lc for lc in result["layout_classes"])

    def test_extracts_component_classes(self):
        result = _extract_mockup_structure(MOCKUP_HTML)
        assert "card" in result["component_classes"]
        assert "form-field" in result["component_classes"]

    def test_extracts_semantic_sections(self):
        result = _extract_mockup_structure(MOCKUP_HTML)
        assert "main" in result["semantic_sections"]

    def test_empty_html_returns_empty(self):
        result = _extract_mockup_structure("")
        assert result["heading_levels"] == []
        assert result["layout_classes"] == []


# ---------------------------------------------------------------------------
# Implementation extraction tests
# ---------------------------------------------------------------------------

class TestImplementationExtraction:
    def test_extracts_shadcn_imports(self):
        result = _extract_implementation_structure(IMPL_TSX)
        assert "Card" in result["shadcn_imports"]
        assert "Input" in result["shadcn_imports"]
        assert "Button" in result["shadcn_imports"]

    def test_extracts_jsx_components(self):
        result = _extract_implementation_structure(IMPL_TSX)
        assert "Card" in result["jsx_components"]
        assert "CardHeader" in result["jsx_components"]
        assert "CardContent" in result["jsx_components"]

    def test_extracts_heading_levels(self):
        result = _extract_implementation_structure(IMPL_TSX)
        assert "h1" in result["heading_levels"]

    def test_detects_gap_usage(self):
        result = _extract_implementation_structure(IMPL_TSX)
        assert result["uses_gap"] is True

    def test_detects_semantic_colors(self):
        result = _extract_implementation_structure(IMPL_TSX)
        assert "bg-background" in result["semantic_colors"]

    def test_no_hardcoded_colors_in_clean_impl(self):
        result = _extract_implementation_structure(IMPL_TSX)
        assert result["hardcoded_colors"] == []

    def test_detects_hardcoded_colors(self):
        tsx = '<div className="bg-gray-500 text-blue-700">test</div>'
        result = _extract_implementation_structure(tsx)
        assert len(result["hardcoded_colors"]) > 0

    def test_detects_space_y(self):
        tsx = '<div className="space-y-4">test</div>'
        result = _extract_implementation_structure(tsx)
        assert result["uses_space_y"] is True


# ---------------------------------------------------------------------------
# Auto-checks tests
# ---------------------------------------------------------------------------

class TestAutoChecks:
    def test_matching_structures_all_pass(self):
        mockup = _extract_mockup_structure(MOCKUP_HTML)
        impl = _extract_implementation_structure(IMPL_TSX)
        checks = _run_auto_checks(mockup, impl)
        assert all(checks.values())

    def test_heading_mismatch_detected(self):
        mockup = {"heading_levels": ["h1"], "layout_classes": [], "component_classes": []}
        impl = {
            "heading_levels": ["h2"], "layout_classes": [], "jsx_components": [],
            "hardcoded_colors": [], "semantic_colors": [],
            "uses_gap": True, "uses_space_y": False,
        }
        checks = _run_auto_checks(mockup, impl)
        assert checks["heading_hierarchy_match"] is False

    def test_space_y_without_gap_fails(self):
        mockup = {"heading_levels": [], "layout_classes": [], "component_classes": []}
        impl = {
            "heading_levels": [], "layout_classes": [], "jsx_components": [],
            "hardcoded_colors": [], "semantic_colors": [],
            "uses_gap": False, "uses_space_y": True,
        }
        checks = _run_auto_checks(mockup, impl)
        assert checks["gap_not_space_y"] is False

    def test_hardcoded_colors_with_no_semantic_fails(self):
        mockup = {"heading_levels": [], "layout_classes": [], "component_classes": []}
        impl = {
            "heading_levels": [], "layout_classes": [], "jsx_components": [],
            "hardcoded_colors": ["bg-gray-500"], "semantic_colors": [],
            "uses_gap": True, "uses_space_y": False,
        }
        checks = _run_auto_checks(mockup, impl)
        assert checks["has_semantic_colors"] is False


# ---------------------------------------------------------------------------
# Route resolution tests
# ---------------------------------------------------------------------------

class TestRouteResolution:
    def test_direct_route(self, project_with_routes):
        files = _resolve_route_to_files(project_with_routes, "/login")
        assert len(files) == 1
        assert files[0].replace("\\", "/").endswith("login/page.tsx")

    def test_root_route(self, project_with_nested_routes):
        files = _resolve_route_to_files(project_with_nested_routes, "/")
        assert len(files) == 1
        assert files[0].replace("\\", "/").endswith("page.tsx")

    def test_route_group(self, tmp_path):
        """Routes with Next.js route groups like (auth)/login."""
        page = tmp_path / "src" / "app" / "(auth)" / "login" / "page.tsx"
        page.parent.mkdir(parents=True)
        page.write_text("export default function Login() {}", encoding="utf-8")

        files = _resolve_route_to_files(tmp_path, "/login")
        assert len(files) == 1
        assert files[0].replace("\\", "/").endswith("login/page.tsx")

    def test_nonexistent_route_returns_empty(self, tmp_path):
        (tmp_path / "src" / "app").mkdir(parents=True)
        files = _resolve_route_to_files(tmp_path, "/nonexistent")
        assert files == []

    def test_no_src_app_returns_empty(self, tmp_path):
        files = _resolve_route_to_files(tmp_path, "/login")
        assert files == []


# ---------------------------------------------------------------------------
# Integration tests — run_design_fidelity_check
# ---------------------------------------------------------------------------

class TestRunDesignFidelityCheck:
    def test_processes_all_screens(self, project_with_routes):
        result = run_design_fidelity_check(project_with_routes)
        assert result["skipped"] is False
        assert result["total"] == 3
        assert len(result["screens"]) == 3

    def test_screen_filter_subset(self, project_with_routes):
        result = run_design_fidelity_check(
            project_with_routes, screens=["screens/01-login.html"]
        )
        assert result["total"] == 1
        assert result["screens"][0]["mockup"] == "screens/01-login.html"

    def test_screen_filter_nonexistent_returns_error(self, project_with_routes):
        result = run_design_fidelity_check(
            project_with_routes, screens=["screens/99-missing.html"]
        )
        assert "error" in result
        assert "99-missing.html" in result["error"]

    def test_no_routes_file_skipped(self, tmp_path):
        result = run_design_fidelity_check(tmp_path)
        assert result["skipped"] is True
        assert "No designs/screen-routes.json" in result["skip_reason"]

    def test_empty_routes_skipped(self, tmp_path):
        designs = tmp_path / "designs"
        designs.mkdir()
        (designs / "screen-routes.json").write_text("{}", encoding="utf-8")
        result = run_design_fidelity_check(tmp_path)
        assert result["skipped"] is True

    def test_nested_format(self, project_with_nested_routes):
        result = run_design_fidelity_check(project_with_nested_routes)
        assert result["skipped"] is False
        assert result["total"] == 2
        routes = {s["route"] for s in result["screens"]}
        assert routes == {"/", "/inbox"}

    def test_auto_checks_in_output(self, project_with_routes):
        result = run_design_fidelity_check(project_with_routes)
        for screen in result["screens"]:
            if screen.get("status") != "error":
                assert "auto_checks" in screen

    def test_summary_counts(self, project_with_routes):
        result = run_design_fidelity_check(project_with_routes)
        summary = result["summary"]
        assert summary["total"] == 3
        assert summary["auto_pass"] + summary["needs_agent_review"] == summary["total"]

    def test_missing_mockup_file(self, tmp_path):
        """Mockup referenced in screen-routes.json but file doesn't exist."""
        designs = tmp_path / "designs"
        designs.mkdir()
        (designs / "screen-routes.json").write_text(
            json.dumps({"missing.html": "/missing"}), encoding="utf-8"
        )
        result = run_design_fidelity_check(tmp_path)
        assert result["screens"][0]["status"] == "error"

    def test_missing_implementation(self, tmp_path):
        """Mockup exists but no implementation file found."""
        designs = tmp_path / "designs"
        designs.mkdir()
        (designs / "screen-routes.json").write_text(
            json.dumps({"test.html": "/nowhere"}), encoding="utf-8"
        )
        (designs / "test.html").write_text("<h1>Test</h1>", encoding="utf-8")
        (tmp_path / "src" / "app").mkdir(parents=True)

        result = run_design_fidelity_check(tmp_path)
        assert result["screens"][0]["status"] == "needs_review"
        assert "No implementation file" in result["screens"][0]["note"]
