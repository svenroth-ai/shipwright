"""Tests for detect_frontend_changes.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from detect_frontend_changes import _is_frontend_path, detect


# --- _is_frontend_path ---------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "webui/client/src/App.tsx",
        "app/components/Button.jsx",
        "src/styles/index.css",
        "frontend/page.svelte",
        "client/lib/foo.vue",
        "webui/client/src/index.html",
        "webui/client/src/hooks/useTheme.ts",
        "src/utils/format.js",
    ],
)
def test_frontend_paths(path: str) -> None:
    assert _is_frontend_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "server/api.py",
        "shared/scripts/dev_server.py",
        "README.md",
        "CHANGELOG.md",
        "package.json",
        "scripts/install.sh",
        "plugins/shipwright-build/scripts/tool.ts",  # .ts outside frontend root → not counted
        "docs/guide.md",
    ],
)
def test_non_frontend_paths(path: str) -> None:
    assert _is_frontend_path(path) is False


# --- detect() ------------------------------------------------------------


def _run_git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init", "-q", "-b", "main")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("# seed\n", encoding="utf-8")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-q", "-m", "seed")
    return repo


def test_empty_diff(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    result = detect(repo, since="HEAD")
    assert result["has_frontend_changes"] is False
    assert result["files"] == []


def test_backend_only_diff(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "server.py").write_text("print('hi')\n", encoding="utf-8")
    _run_git(repo, "add", "server.py")
    _run_git(repo, "commit", "-q", "-m", "backend")

    result = detect(repo, since="HEAD~1")
    assert result["has_frontend_changes"] is False
    assert result["files"] == []


def test_mixed_diff_returns_only_frontend(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "server.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / "App.tsx").write_text("export const App = () => null;\n", encoding="utf-8")
    _run_git(repo, "add", "server.py", "src/App.tsx")
    _run_git(repo, "commit", "-q", "-m", "mixed")

    result = detect(repo, since="HEAD~1")
    assert result["has_frontend_changes"] is True
    assert result["files"] == ["src/App.tsx"]


def test_ts_outside_frontend_root_ignored(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "scripts").mkdir()
    (repo / "scripts" / "build-tool.ts").write_text("// node tool\n", encoding="utf-8")
    _run_git(repo, "add", "scripts/build-tool.ts")
    _run_git(repo, "commit", "-q", "-m", "tool")

    result = detect(repo, since="HEAD~1")
    assert result["has_frontend_changes"] is False


def test_css_counts_regardless_of_location(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "theme.css").write_text("body { color: red; }\n", encoding="utf-8")
    _run_git(repo, "add", "theme.css")
    _run_git(repo, "commit", "-q", "-m", "css")

    result = detect(repo, since="HEAD~1")
    assert result["has_frontend_changes"] is True
    assert result["files"] == ["theme.css"]


def test_git_diff_failure_returns_error(tmp_path: Path) -> None:
    non_repo = tmp_path / "not-a-repo"
    non_repo.mkdir()
    result = detect(non_repo, since="HEAD")
    assert result["has_frontend_changes"] is False
    assert "error" in result
