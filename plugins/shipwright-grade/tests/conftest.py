"""Shared fixtures for shipwright-grade tests.

Provides a deterministic synthetic-git-repo builder and the Layer-A fixtures
(well-run / messy / no-tests) plus negative fixtures. All repos are built with a
pinned author/committer identity and date and an isolated git config, so the
grade of a fixture is byte-stable across machines.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Core library importable bare (mirrors scripts/lib/__init__.py + grade.py).
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_LIB = _PLUGIN_ROOT / "scripts" / "lib"
_TOOLS = _PLUGIN_ROOT / "scripts" / "tools"
for _p in (_LIB, _TOOLS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def require_git() -> None:
    """Skip locally / hard-fail in CI when git is unavailable."""
    if shutil.which("git") is None:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail("git is required in CI — install git on the runner")
        pytest.skip("git not available on this machine")


def _base_env() -> dict[str, str]:
    return {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "Grade Test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Grade Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
    }


def _git(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env or _base_env(), check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")


def build_repo(root: Path, commits: list[dict]) -> Path:
    """Build a git repo at ``root`` from a list of commit specs.

    Each commit spec: ``{"subject": str, "body"?: str, "files": {rel: content},
    "date"?: iso8601}``.
    """
    require_git()
    root.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], root)
    _git(["config", "commit.gpgsign", "false"], root)
    for spec in commits:
        for rel, content in spec.get("files", {}).items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        _git(["add", "-A"], root)
        date = spec.get("date", "2024-01-01T12:00:00")
        env = {**_base_env(), "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        subject = spec["subject"]
        body = spec.get("body", "")
        message = f"{subject}\n\n{body}" if body else subject
        _git(["commit", "-q", "--no-gpg-sign", "-m", message], root, env=env)
    return root


# --------------------------------------------------------------------------- #
# Layer-A fixture repos (session-scoped: built once, deterministic).
# --------------------------------------------------------------------------- #

_PYPROJECT = (
    "[project]\n"
    'name = "sample"\n'
    'requires-python = ">=3.11"\n'
    'dependencies = ["fastapi", "pytest"]\n'
)
_API_PY = (
    "from fastapi import FastAPI\n\n"
    "app = FastAPI()\n\n"
    '@app.get("/users")\n'
    "def list_users():\n"
    "    return []\n\n"
    '@app.get("/orders")\n'
    "def list_orders():\n"
    "    return []\n"
)
_TEST_API_PY = (
    "from app.api import app  # noqa\n\n"
    "def test_users_route():\n"
    '    assert "/users" in {r.path for r in app.routes}\n\n'
    "def test_orders_route():\n"
    '    assert "/orders" in {r.path for r in app.routes}\n'
)
_CI_YML = "name: ci\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n"


@pytest.fixture(scope="session")
def well_run_repo(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("well_run")
    return build_repo(root, [
        {"subject": "feat: scaffold api (#1)", "date": "2024-01-01T09:00:00",
         "files": {"pyproject.toml": _PYPROJECT, "app/api.py": _API_PY}},
        {"subject": "test: add api tests (#2)", "date": "2024-01-02T09:00:00",
         "files": {"tests/test_api.py": _TEST_API_PY}},
        {"subject": "ci: add github actions (#3)", "date": "2024-01-03T09:00:00",
         "files": {".github/workflows/ci.yml": _CI_YML}},
        {"subject": "fix: handle empty orders (#4)", "date": "2024-01-04T09:00:00",
         "files": {"app/api.py": _API_PY + "\n# fixed\n"}},
    ])


@pytest.fixture(scope="session")
def well_run_no_refs_repo(tmp_path_factory) -> Path:
    """A well-run repo — CI + tests + small files + clean Conventional Commits —
    whose subjects carry NO PR/issue ``#N`` reference (a disciplined squash-merge
    history). Byte-for-byte the ``well_run_repo`` minus the ``(#N)`` tokens.

    This is the local-mode honesty regression case: git-log ``#N`` provenance is
    0/4 here, which used to collapse change-traceability to F ("out of control")
    even though the repo is exemplary. In local-only mode change-traceability must
    render n/a (not measurable without --allow-network), so this repo grades on
    its real controls (B — the cold-repo ceiling), never F.
    """
    root = tmp_path_factory.mktemp("well_run_no_refs")
    return build_repo(root, [
        {"subject": "feat: scaffold api", "date": "2024-01-01T09:00:00",
         "files": {"pyproject.toml": _PYPROJECT, "app/api.py": _API_PY}},
        {"subject": "test: add api tests", "date": "2024-01-02T09:00:00",
         "files": {"tests/test_api.py": _TEST_API_PY}},
        {"subject": "ci: add github actions", "date": "2024-01-03T09:00:00",
         "files": {".github/workflows/ci.yml": _CI_YML}},
        {"subject": "fix: handle empty orders", "date": "2024-01-04T09:00:00",
         "files": {"app/api.py": _API_PY + "\n# fixed\n"}},
    ])


@pytest.fixture(scope="session")
def no_tests_repo(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("no_tests")
    return build_repo(root, [
        {"subject": "feat: api (#1)", "date": "2024-01-01T09:00:00",
         "files": {"pyproject.toml": _PYPROJECT, "app/api.py": _API_PY}},
        {"subject": "feat: more routes (#2)", "date": "2024-01-02T09:00:00",
         "files": {"app/api.py": _API_PY + "\n# more\n"}},
    ])


@pytest.fixture(scope="session")
def messy_repo(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("messy")
    minimal_py = _API_PY.replace("/orders", "/x").split("@app.get(\"/x\")")[0]
    return build_repo(root, [
        {"subject": "stuff", "date": "2024-01-01T09:00:00",
         "files": {"pyproject.toml": '[project]\nname = "m"\n', "app/api.py": minimal_py}},
        {"subject": "more stuff", "date": "2024-01-02T09:00:00",
         "files": {"app/api.py": minimal_py + "\n# x\n"}},
        {"subject": "wip", "date": "2024-01-03T09:00:00",
         "files": {"notes.txt": "todo\n"}},
    ])


# --------------------------------------------------------------------------- #
# Negative fixtures (graceful n/a, never a crash).
# --------------------------------------------------------------------------- #

@pytest.fixture
def non_git_dir(tmp_path: Path) -> Path:
    (tmp_path / "readme.md").write_text("not a repo\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def bare_repo(tmp_path: Path) -> Path:
    require_git()
    root = tmp_path / "bare.git"
    root.mkdir()
    _git(["init", "--bare", "-q"], root)
    return root


@pytest.fixture
def empty_git_repo(tmp_path: Path) -> Path:
    require_git()
    root = tmp_path / "empty"
    root.mkdir()
    _git(["init", "-q"], root)
    return root


@pytest.fixture
def shallow_repo(well_run_repo: Path, tmp_path: Path) -> Path:
    """A real repo carrying a `.git/shallow` marker (shallow-clone shape)."""
    require_git()
    dest = tmp_path / "shallow"
    shutil.copytree(well_run_repo, dest)
    (dest / ".git" / "shallow").write_text("", encoding="utf-8")
    return dest


@pytest.fixture
def huge_binary_repo(tmp_path: Path) -> Path:
    """A repo with a binary blob and an oversize text file (caps must hold)."""
    require_git()
    root = tmp_path / "huge"
    root.mkdir()
    _git(["init", "-q"], root)
    _git(["config", "commit.gpgsign", "false"], root)
    (root / "data.bin").write_bytes(bytes(range(256)) * 8)
    (root / "big.txt").write_text("x" * 2_000_000, encoding="utf-8")
    (root / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    _git(["add", "-A"], root)
    env = {**_base_env(), "GIT_AUTHOR_DATE": "2024-01-01T00:00:00",
           "GIT_COMMITTER_DATE": "2024-01-01T00:00:00"}
    _git(["commit", "-q", "--no-gpg-sign", "-m", "chore: data (#1)"], root, env=env)
    return root


@pytest.fixture
def hostile_repo(tmp_path: Path) -> Path:
    """A repo whose commit subject carries ANSI + a bidi override + a control char."""
    root = tmp_path / "hostile"
    # ANSI colour + BEL + a bidi override (built via chr() so no literal control
    # characters live in this test source).
    ansi_subject = (
        "feat: add \x1b[31mRED\x1b[0m\x07 " + chr(0x202E) + "evil" + chr(0x202C)
        + " thing (#9)"
    )
    return build_repo(root, [
        {"subject": ansi_subject, "date": "2024-01-01T09:00:00",
         "files": {"pyproject.toml": _PYPROJECT, "app/api.py": _API_PY}},
    ])
