"""Throwaway git repos for the baseline touched-set tests: real git, never a mocked reader."""

from __future__ import annotations

import subprocess
from pathlib import Path

SPEC = ".shipwright/planning/01-adopted/spec.md"

SPEC_TEXT = """# Spec

## Functional Requirements

| ID | Area | Name | Priority | Description | Basis | Layers |
|---|---|---|---|---|---|---|
| FR-01.09 | Adopted | /changelog | Must | Prepare a release. | code | unit (inferred) |
| FR-01.10 | Adopted | /compliance | Must | Keep evidence. | code | unit |

## Acceptance Criteria

### FR-01.09 — /changelog

- (E) [AC01] Given work, when release, then a note exists.
- (E) [AC02] Given nothing, when release, then it stops.

### FR-01.10 — /compliance

- (E) [AC01] Given a run, when audited, then evidence exists.
"""


def git(root: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "config", "commit.gpgsign", "false")
    commit(root, files, "base")
    return root


def commit(root: Path, files: dict[str, str | None], msg: str) -> str:
    for rel, text in files.items():
        path = root / rel
        if text is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", msg)
    return git(root, "rev-parse", "HEAD")
