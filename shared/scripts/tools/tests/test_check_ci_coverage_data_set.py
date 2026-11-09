"""`check_ci_coverage_data_set.py` (iterate-2026-11-06-ci-parallel-jobs).

The shared test tier is measured in a parallel CI job and its `.cov-data/` reaches the
gather job by artifact. Nothing else notices a lost coverage file: combine_coverage reports
ok on whatever arrived and the diff-coverage gate is skipped when no coverage.xml exists.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.check_ci_coverage_data_set as mod  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _repo(tmp_path: Path, *, plugins: dict[str, tuple[bool, bool, bool]], integration: bool = True) -> Path:
    """plugins: name -> (has pyproject, has tests/, has scripts/)."""
    root = tmp_path / "repo"
    (root / "plugins").mkdir(parents=True)
    if integration:
        (root / "integration-tests").mkdir()
    for name, (pyproject, tests, scripts) in plugins.items():
        d = root / "plugins" / name
        d.mkdir()
        if pyproject:
            (d / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        if tests:
            (d / "tests").mkdir()
        if scripts:
            (d / "scripts").mkdir()
    return root


def _fill(root: Path, names: list[str]) -> Path:
    data = root / ".cov-data"
    data.mkdir(exist_ok=True)
    for n in names:
        (data / n).write_bytes(b"SQLite format 3\x00")
    return data


@pytest.mark.covers("FR-01.17/AC02")
def test_expected_set_follows_the_ci_test_loop_not_a_hand_list(tmp_path):
    root = _repo(tmp_path, plugins={
        "a": (True, True, True),     # measured
        "b": (True, True, False),    # tests run, but no scripts/ -> not measured (as in the CI loop)
        "c": (True, False, True),    # no tests/
        "d": (False, True, True),    # no pyproject
    })
    assert mod.expected_files(root) == [".coverage.shared", ".coverage.integration", ".coverage.a"]


@pytest.mark.covers("FR-01.17/AC02")
def test_complete_set_passes(tmp_path):
    root = _repo(tmp_path, plugins={"a": (True, True, True)})
    _fill(root, [".coverage.shared", ".coverage.integration", ".coverage.a"])
    assert mod.main(["--project-root", str(root)]) == 0


@pytest.mark.covers("FR-01.17/AC02")
@pytest.mark.parametrize("lost", [".coverage.shared", ".coverage.integration", ".coverage.a"])
def test_any_lost_file_fails_closed(tmp_path, lost, capsys):
    root = _repo(tmp_path, plugins={"a": (True, True, True)})
    present = [n for n in (".coverage.shared", ".coverage.integration", ".coverage.a") if n != lost]
    _fill(root, present)
    assert mod.main(["--project-root", str(root)]) == 1
    assert lost in capsys.readouterr().err


@pytest.mark.covers("FR-01.17/AC02")
def test_an_empty_file_counts_as_lost(tmp_path):
    root = _repo(tmp_path, plugins={})
    data = _fill(root, [".coverage.shared", ".coverage.integration"])
    (data / ".coverage.shared").write_bytes(b"")
    assert mod.main(["--project-root", str(root)]) == 1


@pytest.mark.covers("FR-01.17/AC02")
def test_a_missing_data_dir_fails_instead_of_passing_vacuously(tmp_path):
    root = _repo(tmp_path, plugins={})
    assert mod.main(["--project-root", str(root)]) == 1


@pytest.mark.covers("FR-01.17/AC02")
def test_this_repos_expected_set_names_shared_integration_and_every_measured_plugin():
    names = mod.expected_files(_REPO_ROOT)
    assert names[:2] == [".coverage.shared", ".coverage.integration"]
    assert any(n.startswith(".coverage.shipwright-") for n in names[2:])
