"""Playwright reports key specs relative to ``config.rootDir`` (the ``testDir``), not to the
project root. With the config in a sub-folder (``client/playwright.config.ts``,
``testDir: './e2e'``) the report says ``flows/board.spec.ts`` while the manifest knows
``client/e2e/flows/board.spec.ts`` -- the ids never joined and every passing E2E test read
as missing (GitHub issue #969). ``read_playwright`` now derives the base from the report's
own ``config.rootDir`` when the caller supplies none.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts.lib.collectors.execution_evidence import build_index, read_playwright  # noqa: E402

_TITLE = "moves a card @FR-01.01"


def _report(root_dir: str, file: str = "flows/board.spec.ts") -> dict:
    return {
        "config": {"rootDir": root_dir},
        "suites": [{
            "title": file, "file": file,
            "specs": [{
                "title": _TITLE,
                "tests": [{"status": "expected", "results": [{"status": "passed"}]}],
            }],
        }],
    }


@pytest.mark.covers("FR-01.10/AC01")
def test_rootdir_inside_project_rebases_spec_file(tmp_path):
    data = _report((tmp_path / "client" / "e2e").as_posix())
    out = read_playwright(data, root=tmp_path)
    assert f"client/e2e/flows/board.spec.ts::{_TITLE}" in out
    assert out[f"client/e2e/flows/board.spec.ts::{_TITLE}"]["executed"] == "pass"


@pytest.mark.covers("FR-01.10/AC01")
def test_rootdir_is_applied_through_build_index(tmp_path):
    data = _report((tmp_path / "client" / "e2e").as_posix())
    index = build_index(playwright=data, root=tmp_path)
    assert f"client/e2e/flows/board.spec.ts::{_TITLE}" in index["results"]


@pytest.mark.covers("FR-01.10/AC01")
def test_rootdir_equal_to_project_root_adds_no_prefix(tmp_path):
    out = read_playwright(_report(tmp_path.as_posix(), "e2e/a.spec.ts"), root=tmp_path)
    assert f"e2e/a.spec.ts::{_TITLE}" in out


@pytest.mark.covers("FR-01.10/AC01")
def test_explicit_base_wins_over_rootdir(tmp_path):
    data = _report((tmp_path / "client" / "e2e").as_posix())
    out = read_playwright(data, root=tmp_path, base="other")
    assert f"other/flows/board.spec.ts::{_TITLE}" in out


@pytest.mark.covers("FR-01.10/AC01")
def test_rootdir_outside_project_is_ignored_fail_closed(tmp_path):
    outside = tmp_path.parent / "elsewhere"
    out = read_playwright(_report(outside.as_posix()), root=tmp_path)
    assert f"flows/board.spec.ts::{_TITLE}" in out  # unchanged: won't join, never a false pass


@pytest.mark.covers("FR-01.10/AC01")
@pytest.mark.parametrize("config", [None, {}, {"rootDir": ""}, {"rootDir": 7}, "x"])
def test_missing_or_malformed_config_keeps_prior_behaviour(tmp_path, config):
    data = _report("ignored")
    data.pop("config")
    if config is not None:
        data["config"] = config
    out = read_playwright(data, root=tmp_path)
    assert f"flows/board.spec.ts::{_TITLE}" in out


@pytest.mark.covers("FR-01.10/AC01")
def test_absolute_spec_file_outside_rootdir_gets_no_derived_prefix(tmp_path):
    # Absolute, under root but NOT under rootDir: norm_path already makes it root-relative, so
    # the derived base must not be added (fails without the is_absolute guard).
    abs_file = (tmp_path / "other" / "x.spec.ts").as_posix()
    data = _report((tmp_path / "client" / "e2e").as_posix(), abs_file)
    out = read_playwright(data, root=tmp_path)
    assert set(out) == {f"other/x.spec.ts::{_TITLE}"}


@pytest.mark.covers("FR-01.10/AC01")
def test_derived_base_is_joined_even_when_the_file_repeats_the_dir_name(tmp_path):
    # rootDir=<root>/e2e and a spec at <root>/e2e/e2e/x.spec.ts is reported as "e2e/x.spec.ts".
    # The derived base is certain, so it must NOT be skipped as "already prefixed" -- else the
    # id would key <root>/e2e/x.spec.ts, a different file (a false-pass path).
    out = read_playwright(_report((tmp_path / "e2e").as_posix(), "e2e/x.spec.ts"), root=tmp_path)
    assert set(out) == {f"e2e/e2e/x.spec.ts::{_TITLE}"}


@pytest.mark.covers("FR-01.10/AC01")
def test_dotdot_file_is_collapsed_and_a_project_escape_never_joins(tmp_path):
    root_dir = (tmp_path / "client" / "e2e").as_posix()
    collapsed = read_playwright(_report(root_dir, "../smoke/a.spec.ts"), root=tmp_path)
    assert set(collapsed) == {f"client/smoke/a.spec.ts::{_TITLE}"}
    escaped = read_playwright(_report(root_dir, "../../../x.spec.ts"), root=tmp_path)
    assert all(k.startswith("..") for k in {k.split("::")[0] for k in escaped})  # cannot join


@pytest.mark.covers("FR-01.10/AC01")
def test_native_separator_rootdir_and_nested_suite(tmp_path):
    data = _report(str(tmp_path / "client" / "e2e"))  # backslashes on Windows
    spec = data["suites"][0]["specs"]
    data["suites"][0] = {"title": "f", "file": "flows/board.spec.ts", "specs": [],
                         "suites": [{"title": "describe", "specs": spec}]}
    out = read_playwright(data, root=tmp_path)
    assert set(out) == {f"client/e2e/flows/board.spec.ts::{_TITLE}"}


@pytest.mark.covers("FR-01.10/AC01")
def test_without_root_the_rootdir_is_not_used():
    out = read_playwright(_report("/abs/client/e2e"))
    assert f"flows/board.spec.ts::{_TITLE}" in out
