"""Fixture repositories for the adopt snapshot contract gate.

Two repos, because a contract taken from one of them would lie:

* ``rich_repo`` exercises every ARM of the snapshot — **every list non-empty**. An empty
  list pins nothing about its elements, so a fixture that left one empty would ship a
  weak pin dressed up as a strong one (``test_the_pin_has_no_unpinned_arrays`` is what
  keeps this honest).
* ``bare_repo`` is the NULL arm: almost nothing is detectable, so every optional field
  comes back null. Merged with the rich repo, an optional field pins as ``string|null``
  rather than as whichever arm one fixture happened to show.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


def require_git() -> None:
    """Skip locally, HARD-FAIL in CI — a silently skipped gate is a false green."""
    if shutil.which("git") is None:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail("git is required in CI — install git on the runner")
        pytest.skip("git not available on this machine")


def git(repo: Path, *args: str) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_SYSTEM": os.devnull, "GIT_AUTHOR_NAME": "T",
           "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "T",
           "GIT_COMMITTER_EMAIL": "t@example.invalid",
           "GIT_AUTHOR_DATE": "2024-01-01T12:00:00",
           "GIT_COMMITTER_DATE": "2024-01-01T12:00:00"}
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, check=False, env=env)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr}")


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def rich_repo(root: Path) -> Path:
    """A repo in which every detector fires and every snapshot list is non-empty."""
    require_git()
    write(root, "package.json", json.dumps({
        "name": "rich", "scripts": {"dev": "vite", "build": "vite build",
                                    "test": "vitest", "lint": "eslint ."},
        "dependencies": {"react": "^18.0.0"},
        # @playwright/test -> test_frameworks.e2e; @vitest/coverage-v8 -> coverage_tool.
        # Without these the leaves pin as bare "null" and the published contract would
        # tell the consumer they are ALWAYS null, when in production they are objects.
        "devDependencies": {"vitest": "^1.0.0", "@playwright/test": "^1.44.0",
                            "@vitest/coverage-v8": "^1.0.0"}}))
    # Sibling client/ + server/ package.jsons carrying real frameworks →
    # stack.multi_service.{services,evidence}. The detector looks for exactly these
    # layout pairs (client/server, frontend/backend, web/api).
    write(root, "client/package.json", json.dumps({
        "name": "client", "scripts": {"dev": "vite"},  # -> services[].dev_command
        "dependencies": {"react": "^18.0.0", "vite": "^5.0.0"}}))
    write(root, "server/package.json", json.dumps({
        "name": "server", "scripts": {"dev": "node index.js"},
        "dependencies": {"express": "^4.18.0"}}))
    # A vite proxy -> services[].proxy_target (the detector probes for it explicitly).
    write(root, "client/vite.config.ts",
          "export default {\n"
          "  server: { proxy: { '/api': 'http://localhost:3001' } },\n"
          "}\n")
    # A subdirectory carrying its OWN .git → nested_projects (a vendored clone). A bare
    # package.json is deliberately NOT enough for the detector — that would flag every
    # ordinary monorepo workspace as a nested project.
    (root / "legacy-app" / ".git").mkdir(parents=True)
    write(root, "legacy-app/package.json", json.dumps({"name": "legacy"}))
    # [tool.ruff] -> conventions.python_style; [tool.pytest] -> test_frameworks.integration
    # (pytest lands there once a JS framework already claimed `unit`); coverage -> the
    # coverage_tool leaf. Without these they pin as bare "null", and the published
    # contract would tell the consumer they are ALWAYS null when in production they are
    # objects/strings.
    write(root, "pyproject.toml",
          '[project]\nname = "rich"\nrequires-python = ">=3.11"\n'
          'dependencies = ["fastapi"]\n\n'
          '[tool.ruff]\nline-length = 100\n\n'
          '[tool.pytest.ini_options]\naddopts = "-q"\n\n'
          '[tool.coverage.run]\nsource = ["app"]\n')
    write(root, "app/main.py",  # FastAPI routes → features
          "from fastapi import FastAPI\n\napp = FastAPI()\n\n"
          '@app.get("/users")\ndef users():\n    return []\n\n'
          '@app.get("/orders")\ndef orders():\n    return []\n')
    write(root, "src/app.tsx", "export default function App() { return null }\n")
    write(root, "tests/test_api.py", "def test_users():\n    assert True\n")
    # A pgTAP suite -> test_frameworks.db.
    write(root, "supabase/tests/database/rls.test.sql", "select plan(1);\n")
    write(root, ".github/workflows/ci.yml",
          "name: ci\non: [push]\njobs:\n  t:\n    runs-on: ubuntu-latest\n")
    # A bare `root = true` yields NO editorconfig data: the detector only records
    # indent_style / indent_size / end_of_line, so the leaf would pin as null.
    write(root, ".editorconfig",
          "root = true\n\n[*]\nindent_style = space\nindent_size = 2\nend_of_line = lf\n")
    write(root, ".prettierrc", "{}\n")
    write(root, ".eslintrc.json", "{}\n")
    write(root, "tsconfig.json", json.dumps({"compilerOptions": {"strict": True}}))
    git(root, "init", "-q")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "add", "-A")
    git(root, "commit", "-q", "--no-gpg-sign", "-m", "feat: initial import (#1)")
    # A refactor-keyworded subject touching >= 5 files → git.major_refactor_commits.
    for i in range(6):
        write(root, f"src/mod_{i}.ts", f"export const v{i} = {i}\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "--no-gpg-sign", "-m", "refactor: restructure modules (#2)")
    return root


def bare_repo(root: Path) -> Path:
    """A repo with almost nothing — the NULL arm of every optional field."""
    require_git()
    write(root, "README.md", "# bare\n")
    git(root, "init", "-q")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "add", "-A")
    git(root, "commit", "-q", "--no-gpg-sign", "-m", "docs: readme")
    return root
