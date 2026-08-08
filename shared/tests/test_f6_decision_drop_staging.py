"""F6 decision-drop staging is run_id-glob-scoped, not directory-level.

Split out of test_write_decision_drop.py (bloat-gate crossing). doubt-reviewer
MEDIUM #4 (iterate-2026-08-08-track-decision-drops): unlike every other F6
directory-level add, decision-drops/ is a single FLAT directory shared by
every run that has touched a worktree — a campaign's sub-iterates branch-hop
inside ONE shared worktree. A bare directory add would sweep an unrelated,
never-committed sibling drop into this run's own commit, misattributing its
ADR's origin.
"""

from __future__ import annotations

from pathlib import Path

from tools.write_decision_drop import drop_dir, write_decision_drop

_F6 = "plugins/shipwright-iterate/skills/iterate/references/F6.md"


def _fields(**over):
    base = dict(
        run_id="iterate-20260515-foo",
        section="Iterate — change: foo",
        title="Foo decision",
        context="why",
        decision="what",
        consequences="impact",
    )
    base.update(over)
    return base


def _f6_decision_drop_add_line() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    for line in (repo_root / _F6).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("git add") and "decision-drops/" in stripped:
            return stripped
    raise AssertionError("F6.md no longer stages decision-drops/ at all")


def test_f6_decision_drop_add_is_glob_scoped_to_run_id():
    line = _f6_decision_drop_add_line()
    assert "decision-drops/{run_id}_*.json" in line, (
        f"F6 must scope the decision-drop add to THIS run's own files, not "
        f"the whole directory: {line!r}"
    )


def test_unrelated_sibling_drop_survives_run_id_scoped_staging(
    git_origin_repo, make_worktree
):
    """The concrete failure MEDIUM #4 describes: a leftover drop from an
    unrelated/aborted run sits uncommitted in a shared campaign worktree.
    Staging by THIS run's own `{run_id}_*.json` glob (what F6.md now
    instructs) must leave that sibling file untouched — a bare directory-level
    `git add` would have swept it into this run's commit instead."""
    work, _ = git_origin_repo
    wt = make_worktree(work, "campaign-shared")
    write_decision_drop(wt, **_fields(run_id="iterate-sub-a"))  # leftover, never committed
    write_decision_drop(wt, **_fields(run_id="iterate-sub-b"))  # this run's own drop

    safe = "iterate-sub-b"
    matched = sorted(p.name for p in drop_dir(wt).glob(f"{safe}_*.json"))
    assert matched == ["iterate-sub-b_001.json"]

    all_present = sorted(p.name for p in drop_dir(wt).glob("*.json"))
    assert "iterate-sub-a_001.json" in all_present, (
        "sanity: the sibling drop is genuinely present on disk and would "
        "have been swept by a directory-level `git add .../decision-drops/`"
    )
