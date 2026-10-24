"""Adopt's ``_scaffold_env_local`` goes through the stack-profile resolver (campaign S2).

It no longer hands the bundled profile directory to ``init_env_file``: a custom
project profile scaffolds too, an unknown / invalid profile comes back as an
``action: "error"`` result (stored under ``results["env_local"]``), and a reserved
sentinel stays ``skipped`` with no framework-only scaffold. The partial-write handling
around it is S3. Tagged to FR-01.06 (see shared/tests/test_profile_resolver.py).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.generate_adoption_artifacts import _scaffold_env_local

pytestmark = pytest.mark.covers("FR-01.06")


def _project(tmp_path: Path, profile) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "shipwright_run_config.json").write_text(json.dumps({"profile": profile}), encoding="utf-8")
    return root


def _profile(root: Path, name: str, **data) -> Path:
    path = root / ".shipwright" / "profiles" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": name, **data}), encoding="utf-8")
    return path


def test_custom_project_profile_is_scaffolded(tmp_path):
    root = _project(tmp_path, "my-stack")
    _profile(root, "my-stack", required_env_vars={"build": [{"name": "MY_TOKEN", "description": "t"}]})
    out = _scaffold_env_local(root)
    assert out["action"] == "created" and "MY_TOKEN" in out["vars"]
    assert "OPENROUTER_API_KEY" in out["framework_keys"]  # framework keys still merged


def test_bundled_profile_scaffold_is_unchanged(tmp_path):
    out = _scaffold_env_local(_project(tmp_path, "supabase-nextjs"))
    assert out["action"] == "created" and "NEXT_PUBLIC_SUPABASE_URL" in out["vars"]


def test_unknown_profile_returns_an_error_result_and_writes_nothing(tmp_path):
    root = _project(tmp_path, "no-such-stack")
    out = _scaffold_env_local(root)
    assert out["action"] == "error" and out["kind"] == "not_found"
    assert "no-such-stack" in out["error"] and "Searched" in out["error"]
    assert not (root / ".env.local").exists() and not (root / ".gitignore").exists()


def test_corrupt_profile_returns_an_error_result_naming_the_file(tmp_path):
    root = _project(tmp_path, "vite-hono")
    path = root / ".shipwright" / "profiles" / "vite-hono.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    out = _scaffold_env_local(root)
    assert out["action"] == "error" and out["kind"] == "invalid" and str(path) in out["error"]


@pytest.mark.parametrize("sentinel", ["generic", "detecting"])
def test_sentinel_stays_skipped_without_a_framework_only_scaffold(tmp_path, sentinel):
    root = _project(tmp_path, sentinel)
    out = _scaffold_env_local(root)
    assert out["action"] == "skipped" and not (root / ".env.local").exists()
