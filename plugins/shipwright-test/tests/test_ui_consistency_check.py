"""Tests for ui_consistency_check.py — cross-page UI consistency detection."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from lib.ui_consistency_check import run_consistency_check


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def project_root(tmp_path):
    """Create minimal project structure with src/app and src/components."""
    (tmp_path / "src" / "app" / "dashboard").mkdir(parents=True)
    (tmp_path / "src" / "app" / "courses").mkdir(parents=True)
    (tmp_path / "src" / "app" / "admin").mkdir(parents=True)
    (tmp_path / "src" / "app" / "profile").mkdir(parents=True)
    (tmp_path / "src" / "components").mkdir(parents=True)
    return tmp_path


def _write_page(root: Path, route: str, content: str):
    """Write a page.tsx file at the given route."""
    page = root / "src" / "app" / route / "page.tsx"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Empty / no files
# ---------------------------------------------------------------------------

def test_no_src_directory(tmp_path):
    """No src/ directory → skipped."""
    result = run_consistency_check(tmp_path)
    assert result["skipped"] is True
    assert "No page/component files found" in result["skip_reason"]


def test_empty_src(tmp_path):
    """Empty src/ directory → skipped."""
    (tmp_path / "src" / "app").mkdir(parents=True)
    result = run_consistency_check(tmp_path)
    assert result["skipped"] is True


# ---------------------------------------------------------------------------
# Heading hierarchy
# ---------------------------------------------------------------------------

def test_heading_consistent(project_root):
    """All pages use text-2xl → CONSISTENT."""
    _write_page(project_root, "dashboard", '<h1 className="text-2xl font-bold">Dashboard</h1>')
    _write_page(project_root, "courses", '<h1 className="text-2xl font-bold">Courses</h1>')
    _write_page(project_root, "admin", '<h1 className="text-2xl font-bold">Admin</h1>')

    result = run_consistency_check(project_root, categories=["heading_hierarchy"])
    cat = result["categories"]["heading_hierarchy"]
    assert cat["status"] == "CONSISTENT"
    assert cat["majority_pattern"] == "text-2xl"


def test_heading_inconsistent(project_root):
    """Mixed text-2xl and text-3xl → INCONSISTENT with outliers."""
    _write_page(project_root, "dashboard", '<h1 className="text-2xl font-bold">Dashboard</h1>')
    _write_page(project_root, "courses", '<h1 className="text-3xl font-bold">Courses</h1>')
    _write_page(project_root, "admin", '<h1 className="text-2xl font-bold">Admin</h1>')

    result = run_consistency_check(project_root, categories=["heading_hierarchy"])
    cat = result["categories"]["heading_hierarchy"]
    assert cat["status"] == "INCONSISTENT"
    assert cat["majority_pattern"] == "text-2xl"
    assert len(cat["outliers"]) == 1
    assert cat["outliers"][0]["found"] == "text-3xl"
    assert "courses" in cat["outliers"][0]["file"]


# ---------------------------------------------------------------------------
# Spacing patterns
# ---------------------------------------------------------------------------

def test_spacing_consistent(project_root):
    """All pages use space-y-6 → CONSISTENT."""
    _write_page(project_root, "dashboard", '<div className="space-y-6"><section>A</section></div>')
    _write_page(project_root, "courses", '<div className="space-y-6"><section>B</section></div>')

    result = run_consistency_check(project_root, categories=["spacing_patterns"])
    cat = result["categories"]["spacing_patterns"]
    assert cat["status"] == "CONSISTENT"
    assert cat["majority_pattern"] == "space-y-6"


def test_spacing_inconsistent(project_root):
    """Mixed space-y-6 and space-y-8 → INCONSISTENT."""
    _write_page(project_root, "dashboard", '<div className="space-y-8"><section>A</section></div>')
    _write_page(project_root, "courses", '<div className="space-y-6"><section>B</section></div>')
    _write_page(project_root, "admin", '<div className="space-y-6"><section>C</section></div>')

    result = run_consistency_check(project_root, categories=["spacing_patterns"])
    cat = result["categories"]["spacing_patterns"]
    assert cat["status"] == "INCONSISTENT"
    assert cat["majority_pattern"] == "space-y-6"
    assert len(cat["outliers"]) == 1
    assert cat["outliers"][0]["found"] == "space-y-8"


# ---------------------------------------------------------------------------
# Component patterns
# ---------------------------------------------------------------------------

def test_component_patterns_consistent(project_root):
    """All use DataTable → CONSISTENT."""
    _write_page(project_root, "dashboard", '<DataTable columns={cols} data={data} />')
    _write_page(project_root, "courses", '<DataTable columns={cols} data={data} />')

    result = run_consistency_check(project_root, categories=["component_patterns"])
    cat = result["categories"]["component_patterns"]
    assert cat["status"] == "CONSISTENT"
    assert cat["majority_pattern"] == "DataTable"


def test_component_patterns_inconsistent(project_root):
    """Mixed DataTable and Table → INCONSISTENT."""
    _write_page(project_root, "dashboard", '<DataTable columns={cols} data={data} />')
    _write_page(project_root, "courses", '<DataTable columns={cols} data={data} />')
    _write_page(project_root, "admin", '<Table><TableBody>...</TableBody></Table>')

    result = run_consistency_check(project_root, categories=["component_patterns"])
    cat = result["categories"]["component_patterns"]
    assert cat["status"] == "INCONSISTENT"
    assert cat["majority_pattern"] == "DataTable"
    assert len(cat["outliers"]) == 1
    assert cat["outliers"][0]["found"] == "Table"


# ---------------------------------------------------------------------------
# Token usage
# ---------------------------------------------------------------------------

def test_token_usage_clean(project_root):
    """Only semantic tokens → CONSISTENT."""
    _write_page(project_root, "dashboard", '<div className="bg-primary text-primary-foreground">OK</div>')
    _write_page(project_root, "courses", '<div className="bg-muted text-muted-foreground">OK</div>')

    result = run_consistency_check(project_root, categories=["token_usage"])
    cat = result["categories"]["token_usage"]
    assert cat["status"] == "CONSISTENT"


def test_token_usage_hardcoded(project_root):
    """Hardcoded colors → INCONSISTENT."""
    _write_page(project_root, "dashboard", '<div className="bg-primary text-primary-foreground">OK</div>')
    _write_page(project_root, "courses", '<div className="bg-blue-500 text-gray-700">Bad</div>')

    result = run_consistency_check(project_root, categories=["token_usage"])
    cat = result["categories"]["token_usage"]
    assert cat["status"] == "INCONSISTENT"
    assert len(cat["outliers"]) >= 1
    found_values = {o["found"] for o in cat["outliers"]}
    assert "bg-blue-500" in found_values or "text-gray-700" in found_values


# ---------------------------------------------------------------------------
# Form patterns
# ---------------------------------------------------------------------------

def test_form_patterns_no_forms(project_root):
    """No form elements → SKIPPED."""
    _write_page(project_root, "dashboard", '<div>No forms here</div>')

    result = run_consistency_check(project_root, categories=["form_patterns"])
    cat = result["categories"]["form_patterns"]
    assert cat["status"] == "SKIPPED"


# ---------------------------------------------------------------------------
# Category filtering
# ---------------------------------------------------------------------------

def test_category_filter(project_root):
    """Only specified categories are checked."""
    _write_page(project_root, "dashboard", '<h1 className="text-2xl">Dashboard</h1>')

    result = run_consistency_check(project_root, categories=["heading_hierarchy"])
    assert "heading_hierarchy" in result["categories"]
    assert "spacing_patterns" not in result["categories"]


def test_all_categories_checked_by_default(project_root):
    """All 6 categories checked when none specified."""
    _write_page(project_root, "dashboard", '<h1 className="text-2xl">Dashboard</h1>')

    result = run_consistency_check(project_root)
    assert len(result["categories"]) == 6


# ---------------------------------------------------------------------------
# File filter (scoped mode for iterate)
# ---------------------------------------------------------------------------

def test_file_filter(project_root):
    """Only specified files are scanned."""
    _write_page(project_root, "dashboard", '<h1 className="text-2xl">Dashboard</h1>')
    _write_page(project_root, "courses", '<h1 className="text-3xl">Courses</h1>')

    # Only scan dashboard → no inconsistency possible
    result = run_consistency_check(
        project_root,
        categories=["heading_hierarchy"],
        file_filter=["src/app/dashboard/page.tsx"],
    )
    cat = result["categories"]["heading_hierarchy"]
    assert cat["status"] == "CONSISTENT"


# ---------------------------------------------------------------------------
# Root-cause groups
# ---------------------------------------------------------------------------

def test_root_cause_groups(project_root):
    """Root-cause groups only include inconsistent categories."""
    _write_page(project_root, "dashboard", '<h1 className="text-2xl">D</h1><div className="space-y-6">A</div>')
    _write_page(project_root, "courses", '<h1 className="text-3xl">C</h1><div className="space-y-6">B</div>')

    result = run_consistency_check(project_root, categories=["heading_hierarchy", "spacing_patterns"])
    groups = result["root_cause_groups"]
    assert "Spacing" in groups
    assert "heading_hierarchy" in groups["Spacing"]
    # spacing_patterns is consistent, so should not be in the group
    assert "spacing_patterns" not in groups.get("Spacing", [])


# ---------------------------------------------------------------------------
# Passed / total counts
# ---------------------------------------------------------------------------

def test_passed_total_counts(project_root):
    """Passed/total correctly reflect category results."""
    _write_page(project_root, "dashboard", '<h1 className="text-2xl">D</h1><DataTable />')
    _write_page(project_root, "courses", '<h1 className="text-3xl">C</h1><DataTable />')

    result = run_consistency_check(project_root, categories=["heading_hierarchy", "component_patterns"])
    assert result["total"] == 2
    assert result["passed"] == 1  # component_patterns consistent, heading_hierarchy not


# ---------------------------------------------------------------------------
# JSON output format
# ---------------------------------------------------------------------------

def test_json_serializable(project_root):
    """Result is JSON-serializable."""
    _write_page(project_root, "dashboard", '<h1 className="text-2xl">D</h1>')
    result = run_consistency_check(project_root)
    serialized = json.dumps(result)
    assert isinstance(json.loads(serialized), dict)
