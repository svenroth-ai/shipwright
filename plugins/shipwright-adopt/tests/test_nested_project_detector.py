"""Unit tests for nested_project_detector.detect_nested_projects."""

from pathlib import Path

from lib.nested_project_detector import detect_nested_projects


def test_detects_nested_shipwright_subproject(nested_shipwright: Path) -> None:
    nested = detect_nested_projects(nested_shipwright)
    paths = [n["path"] for n in nested]
    assert "webui" in paths
    webui = next(n for n in nested if n["path"] == "webui")
    assert "shipwright_run_config.json" in webui["markers"]
    assert webui["reason"] == "separate-shipwright-project"


def test_no_nested_in_clean_repo(nextjs_repo: Path) -> None:
    nested = detect_nested_projects(nextjs_repo)
    # nextjs-repo fixture has no shipwright markers in subdirs
    shipwright_markers = [n for n in nested if "shipwright_run_config.json" in n["markers"]]
    assert shipwright_markers == []


def test_ignores_node_modules_and_dist(tmp_path: Path) -> None:
    (tmp_path / "node_modules" / "something").mkdir(parents=True)
    (tmp_path / "node_modules" / "something" / "package.json").write_text("{}")
    (tmp_path / "dist").mkdir()
    assert detect_nested_projects(tmp_path) == []
