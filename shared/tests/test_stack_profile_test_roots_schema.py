"""The stack-profile schema accepts ``traceability.test_roots`` and types it (GitHub issue #972)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import profile_model as pm  # noqa: E402
import profile_resolver as pr  # noqa: E402


def _data(**extra) -> dict:
    return {"name": "x", **extra}


@pytest.mark.covers("FR-01.10/AC16")
def test_a_string_list_is_accepted():
    pm.validate_profile_data(_data(traceability={"test_roots": ["server/tests", "client/*/e2e"]}), "x.json")


@pytest.mark.covers("FR-01.10/AC16")
def test_null_traceability_is_accepted_like_its_sibling_keys():
    pm.validate_profile_data(_data(traceability=None), "x.json")


@pytest.mark.covers("FR-01.10/AC16")
@pytest.mark.parametrize("bad",["server/tests", {"a": 1}, [1, 2], 5])
def test_a_wrong_type_is_rejected(bad):
    with pytest.raises(ValueError):
        pm.validate_profile_data(_data(traceability={"test_roots": bad}), "x.json")


@pytest.mark.covers("FR-01.10/AC16")
def test_every_bundled_profile_still_validates():
    checked = 0
    for name in pm.bundled_names():
        try:
            pr.resolve_profile(name, None, search_dirs=[("bundled", pm.bundled_dir())])
        except pm.ProfileNotFound:  # a non-profile json that shares the folder
            continue
        checked += 1
    assert checked >= 5


@pytest.mark.covers("FR-01.10/AC16")
def test_vite_hono_declares_the_nested_layout():
    res = pr.resolve_profile("vite-hono", None, search_dirs=[("bundled", pm.bundled_dir())])
    roots = res.data["traceability"]["test_roots"]
    assert {"server/tests", "client/src", "client/e2e"} <= set(roots)
