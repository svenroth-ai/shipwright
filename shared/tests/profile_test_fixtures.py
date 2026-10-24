"""Fixtures + helpers for the stack-profile resolver tests.

Fixtures ``project`` / ``user_dir`` are imported by name into each profile test
module (module-local: they are NOT registered globally, so they cannot shadow a
``project`` parameter elsewhere in ``shared/tests``); the helpers are imported directly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
import profile_resolver as pr  # noqa: E402,F401


def write_profile(directory: Path, name: str, **extra) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    data = {"name": name, "description": f"custom {name}", **extra}
    path = directory / f"{name}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def proj_dir(project: Path) -> Path:
    return project / ".shipwright" / "profiles"


@pytest.fixture(name="project")
def profile_project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    return root


@pytest.fixture(name="user_dir")
def profile_user_dir(isolate_user_profiles_dir):
    return isolate_user_profiles_dir
