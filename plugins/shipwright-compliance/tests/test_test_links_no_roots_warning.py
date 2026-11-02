"""When the collector resolves NO test folder it must say so (GitHub issue #972).

A project laid out like the ``vite-hono`` profile (``server/`` + ``client/``, tests nested below
them) has none of the conventional TOP-LEVEL folders, so ``configured_test_roots`` returned ``[]``
in silence: zero test files scanned, and the coverage gate then asked for tests that already
existed. The collector now writes one stderr line naming ``traceability.test_roots`` -- the
setting that fixes it. Resolution itself is unchanged (still ``[]``): the warning is purely
diagnostic, so no project's manifest moves.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts.lib.collectors import _test_links_io as io  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_warning_state():
    io._WARNED_NO_ROOTS.clear()
    yield
    io._WARNED_NO_ROOTS.clear()


def _vite_hono_layout(root: Path) -> None:
    (root / "server" / "tests").mkdir(parents=True)
    (root / "client" / "src").mkdir(parents=True)
    (root / "client" / "e2e").mkdir(parents=True)


def _config(root: Path, test_roots) -> None:
    (root / "shipwright_compliance_config.json").write_text(
        json.dumps({"traceability": {"test_roots": test_roots}}), encoding="utf-8",
    )


@pytest.mark.covers("FR-01.10/AC01")
def test_nested_layout_without_config_warns_and_names_the_setting(tmp_path, capsys):
    _vite_hono_layout(tmp_path)
    assert io.configured_test_roots(tmp_path) == []  # resolution unchanged
    err = capsys.readouterr().err
    assert "traceability.test_roots" in err
    assert "no test file will be scanned" in err
    assert "shipwright_compliance_config.json" in err


@pytest.mark.covers("FR-01.10/AC01")
def test_warning_is_emitted_once_per_project_root(tmp_path, capsys):
    _vite_hono_layout(tmp_path)
    io.configured_test_roots(tmp_path)
    capsys.readouterr()
    io.configured_test_roots(tmp_path)
    assert capsys.readouterr().err == ""


@pytest.mark.covers("FR-01.10/AC01")
def test_conventional_folder_present_stays_silent(tmp_path, capsys):
    (tmp_path / "tests").mkdir()
    assert io.configured_test_roots(tmp_path) == [tmp_path / "tests"]
    assert capsys.readouterr().err == ""


@pytest.mark.covers("FR-01.10/AC01")
def test_configured_roots_that_resolve_stay_silent(tmp_path, capsys):
    _vite_hono_layout(tmp_path)
    _config(tmp_path, ["server/tests", "client/src", "client/e2e"])
    roots = io.configured_test_roots(tmp_path)
    assert [r.relative_to(tmp_path).as_posix() for r in roots] == [
        "server/tests", "client/src", "client/e2e",
    ]
    assert capsys.readouterr().err == ""


@pytest.mark.covers("FR-01.10/AC01")
def test_configured_roots_matching_nothing_warn_with_a_different_message(tmp_path, capsys):
    _config(tmp_path, ["does/not/exist"])
    assert io.configured_test_roots(tmp_path) == []
    err = capsys.readouterr().err
    assert "traceability.test_roots" in err
    assert "matched no directory" in err
    assert "does/not/exist" not in err  # the entries are config content: never echoed back


@pytest.mark.covers("FR-01.10/AC01")
def test_an_empty_project_warns_for_its_own_root_only(tmp_path, capsys):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    io.configured_test_roots(a)
    io.configured_test_roots(b)
    err = capsys.readouterr().err
    assert err.count("traceability.test_roots") == 2  # exactly one line per root
    assert err.count(str(a.resolve())) == 1 and err.count(str(b.resolve())) == 1


@pytest.mark.covers("FR-01.10/AC01")
def test_an_explicit_empty_list_still_warns_and_says_scanning_is_off(tmp_path, capsys):
    # The issue asks for a warning whenever the resolved roots are empty -- no opt-out exception.
    _config(tmp_path, [])
    assert io.configured_test_roots(tmp_path) == []
    err = capsys.readouterr().err
    assert "traceability.test_roots is an empty list" in err
    assert "turns test scanning off" in err


@pytest.mark.covers("FR-01.10/AC01")
def test_warn_false_stays_silent_for_throwaway_trees(tmp_path, capsys):
    _vite_hono_layout(tmp_path)
    assert io.configured_test_roots(tmp_path, warn=False) == []
    assert capsys.readouterr().err == ""
    assert io.configured_test_roots(tmp_path) == []  # warn=False must not use up the real warning
    assert "traceability.test_roots" in capsys.readouterr().err


@pytest.mark.covers("FR-01.10/AC01")
def test_an_unreadable_config_reports_itself_once_not_twice(tmp_path, capsys):
    (tmp_path / "shipwright_compliance_config.json").write_text("{ not json", encoding="utf-8")
    io.configured_test_roots(tmp_path)
    err = capsys.readouterr().err
    assert err.count("config.json unreadable (") == 1  # not "unreadable": tmp_path carries the test name
    assert err.count("traceability.test_roots") == 1
