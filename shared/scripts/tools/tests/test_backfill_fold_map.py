"""Backfill engine + ``## FR-Fold-Map``: a tag on a folded id is already-good coverage.

Before this, a spec taxonomy fold made the retrofit engine do two wrong things at once:
brand every folded-id tag a ``confirmed_orphan``, and offer to re-tag a test that was in
fact correctly labelled. The last case here is the cross-consumer guard — the backfill
engine and the compliance collector must agree about what a folded tag means, since a
disagreement would let the retrofit "fix" tags the collector was already resolving.

@FR-01.10
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _backfill_support import run, tt1_manifest  # noqa: E402

_SPEC = """# Spec

## Functional Requirements

| FR | Description | Priority | Layers |
|----|-------------|----------|--------|
| FR-01.28 | Embedded terminal | Must | unit |

{fold}
"""

_FOLD = """## FR-Fold-Map

| Folded ID | → Survivor | Reason | Was |
|-----------|-----------|--------|-----|
{rows}
"""

_TEST_SRC = '''import pytest


@pytest.mark.covers("FR-01.44")
def test_terminal_look():
    assert True
'''


def _repo(tmp_path: Path, *, rows: str | None) -> Path:
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    fold = _FOLD.format(rows=rows) if rows else ""
    (root / "spec.md").write_text(_SPEC.format(fold=fold), encoding="utf-8")
    (root / "tests" / "test_terminal.py").write_text(_TEST_SRC, encoding="utf-8")
    return root


def _report(root: Path) -> dict:
    return run(root, commit_frs={}, apply=False)


def test_folded_tag_is_honoured_as_coverage_of_the_survivor(tmp_path):
    report = _report(_repo(tmp_path, rows="| `FR-01.44` | `FR-01.28` | delta | look |"))
    assert report["summary"]["confirmed_orphan"] == 0
    assert report["summary"]["auto_written"] == 0        # nothing re-tagged in source...
    assert report["summary"]["proposals"] == 0           # ...and nothing even proposed
    assert report["already_tagged"] == [
        {"test": "tests/test_terminal.py::test_terminal_look",
         "frs": ["FR-01.28"], "layer": "unit"}
    ]


def test_an_UNBACKTICKED_fold_table_is_not_read_as_live_requirements(tmp_path):
    """AC4 on the backfill side, non-vacuously.

    A backticked fold row is skipped by `CANONICAL_FR_RE` anyway, so a backticked fixture
    passes identically with the fold-skip removed and proves nothing. Unbackticked is the
    dangerous shape: without the skip, `FR-01.44` would parse as a live FR, the tag would
    bind to it directly, and `already_tagged` would read `FR-01.44` instead of the survivor.
    """
    report = _report(_repo(tmp_path, rows="| FR-01.44 | FR-01.28 | delta | look |"))
    assert report["summary"]["confirmed_orphan"] == 0
    assert report["already_tagged"][0]["frs"] == ["FR-01.28"]


def test_a_removed_folded_id_is_not_rescued_by_the_backfill_engine(tmp_path):
    """Retirement beats folding here too — the two consumers must not diverge."""
    root = _repo(tmp_path, rows="| `FR-01.44` | `FR-01.28` | delta | look |")
    spec = (root / "spec.md").read_text(encoding="utf-8")
    (root / "spec.md").write_text(
        spec + "\n## Removed Requirements\n\n"
        "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
        "| FR-01.44 | Retired | Must | unit |\n", encoding="utf-8")
    report = _report(root)
    assert report["summary"]["confirmed_orphan"] == 1
    assert report["orphans"]["confirmed_orphan"][0]["reason"] == "fr_removed"


def test_without_a_fold_map_the_same_tag_is_a_confirmed_orphan(tmp_path):
    """Control — the rescue comes from the fold-map, not a relaxed rule."""
    report = _report(_repo(tmp_path, rows=None))
    assert report["summary"]["confirmed_orphan"] == 1
    assert report["orphans"]["confirmed_orphan"][0]["tagged_fr"] == "FR-01.44"


@pytest.mark.parametrize("rows", [
    "| `FR-01.44` | `FR-01.45` | d | a |\n| `FR-01.45` | `FR-01.44` | d | b |",  # cycle
    "| `FR-01.44` | `FR-01.77` | d | a |",                                       # dangling
    "| `FR-01.44` | `FR-01.28` | d | a |\n| `FR-01.44` | `FR-01.30` | d | b |",  # conflict
])
def test_an_unsafe_edge_still_yields_a_confirmed_orphan(tmp_path, rows):
    report = _report(_repo(tmp_path, rows=rows))
    assert report["summary"]["confirmed_orphan"] == 1
    assert report["already_tagged"] == []


def test_a_live_tag_is_not_redirected_by_a_fold_map(tmp_path):
    """Fallback, never override — mirrors the collector-side guarantee."""
    root = _repo(tmp_path, rows="| `FR-01.28` | `FR-01.44` | d | inverted |")
    (root / "tests" / "test_terminal.py").write_text(
        _TEST_SRC.replace("FR-01.44", "FR-01.28"), encoding="utf-8")
    report = _report(root)
    assert report["summary"]["confirmed_orphan"] == 0
    assert report["already_tagged"][0]["frs"] == ["FR-01.28"]


@pytest.mark.slow
@pytest.mark.parametrize("rows,expect_orphan", [
    ("| `FR-01.44` | `FR-01.28` | delta | look |", False),
    ("| `FR-01.44` | `FR-01.77` | delta | dangling |", True),
])
def test_backfill_and_collector_agree_on_the_same_fold(tmp_path, rows, expect_orphan):
    """The two consumers of ``fr_fold_map`` must classify a fold identically.

    Runs the real TT1 collector in a clean subprocess (the ADR-045 ``lib``-collision
    boundary) over the SAME repo the backfill engine just read, and asserts both reached
    the same verdict — orphan or coverage-of-the-survivor.
    """
    root = _repo(tmp_path, rows=rows)
    report = _report(root)
    manifest = tt1_manifest(root)

    backfill_orphaned = report["summary"]["confirmed_orphan"] > 0
    collector_orphaned = bool(manifest["orphans"])
    assert backfill_orphaned == collector_orphaned == expect_orphan

    if not expect_orphan:
        assert report["already_tagged"][0]["frs"] == ["FR-01.28"]
        survivor = next(n for n in manifest["requirements"].values()
                        if n["id"] == "FR-01.28")
        links = [l for ls in survivor["tests"].values() for l in ls]
        assert [l["resolved_from"] for l in links] == ["FR-01.44"]
