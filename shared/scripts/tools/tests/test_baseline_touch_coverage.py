"""BP unit BL0 - T-code from per-test coverage contexts (S6, S7, S17) and the fan-out measure.

The context database is written with coverage's own API, the same format a ``--cov-context=test``
run leaves behind, so the reader is tested against the real file layout.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools
sys.path.insert(0, str(Path(__file__).resolve().parent))

coverage = pytest.importorskip("coverage")

from _baseline_repo import SPEC, SPEC_TEXT, commit, make_repo  # noqa: E402
from verifiers._baseline_touch_core import touched_set  # noqa: E402
from verifiers._baseline_touch_coverage import context_to_test, load_contexts  # noqa: E402
from verifiers._baseline_touch_git import GitRev  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")

PROD = "def price(x):\n    y = x * 2\n    return y\n\n\ndef unused():\n    return 0\n"
TESTS = (
    'import pytest\n\n\n@pytest.mark.covers("FR-01.09")\ndef test_a():\n    assert 1\n\n\n'
    '@pytest.mark.covers("FR-01.10")\ndef test_b():\n    assert 1\n'
)
BASE = {SPEC: SPEC_TEXT, "src/mod.py": PROD, "pkg/tests/test_a.py": TESTS}


def _db(tmp_path: Path, root: Path, runs: dict[str, list[int]]) -> Path:
    db = tmp_path / ".coverage"
    data = coverage.CoverageData(basename=str(db))
    for ctx, lines in runs.items():
        data.set_context(ctx)
        data.add_lines({str((root / "src/mod.py").resolve()): lines})
    data.write()
    return db


def _run(tmp_path, head_files, runs):
    root = make_repo(tmp_path, BASE)
    base = commit(root, {"README.md": "x"}, "pad")
    head = commit(root, head_files, "change")
    ctx = load_contexts(_db(tmp_path, root, runs), root)
    return touched_set(GitRev(root, base, head), ctx)


def test_context_names_normalise_to_test_ids():
    assert context_to_test("tests/test_x.py::TestC::test_y[p1]|run", "plugins/p/") == "plugins/p/tests/test_x.py::TestC.test_y"
    assert context_to_test("", "") is None


def test_changed_line_reaches_the_frs_of_the_tests_that_ran_it(tmp_path):  # S6
    runs = {"pkg/tests/test_a.py::test_a|run": [1, 2, 3], "pkg/tests/test_a.py::test_b|run": [1, 2, 3]}
    t = _run(tmp_path, {"src/mod.py": PROD.replace("x * 2", "x * 3")}, runs)
    assert set(t.code) == {"FR-01.09", "FR-01.10"} and t.fan_out["src/mod.py::price"] == set(t.code)
    assert t.sources()["FR-01.09"] == {"code"}


def test_code_executed_by_no_bound_test_is_unattributed(tmp_path):  # S7
    t = _run(tmp_path, {"src/mod.py": PROD.replace("return 0", "return 1")}, {"pkg/tests/test_a.py::test_a|run": [1, 2, 3]})
    assert not t.code and any("unused" in u for u in t.unattributed)


def test_pure_deletion_is_attributed_through_the_enclosing_function(tmp_path):  # S17
    t = _run(tmp_path, {"src/mod.py": PROD.replace("    y = x * 2\n    return y\n", "    return x\n")},
             {"pkg/tests/test_a.py::test_a|run": [1, 2, 3]})
    assert set(t.code) == {"FR-01.09"}


def test_line_added_inside_a_function_is_attributed_to_the_function(tmp_path):
    t = _run(tmp_path, {"src/mod.py": PROD.replace("    return y\n", "    y += 1\n    return y\n")},
             {"pkg/tests/test_a.py::test_b|run": [1, 2, 3]})
    assert set(t.code) == {"FR-01.10"}


def test_new_module_level_line_has_no_context_and_is_reported(tmp_path):
    t = _run(tmp_path, {"src/mod.py": "import os\n" + PROD}, {"pkg/tests/test_a.py::test_a|run": [1, 2, 3]})
    assert not t.code and t.unattributed
