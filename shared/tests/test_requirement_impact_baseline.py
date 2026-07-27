"""Tests for the per-round requirement baseline.

The design half's evidence problem, and the fix. A design round has no commit, so
an earlier draft used `git diff HEAD` plus `ls-files --others`. In the standard
pipeline nothing commits before the build phase, so every spec.md the project
phase wrote was *untracked* and therefore listed — and **any** `--impact modify`
passed on a spec nobody had edited. The check was decorative exactly where it
needed to bite.

The baseline restores the boundary a commit gives a build section: snapshot the
requirement specs before the round revises anything, compare afterwards.

Origin: trg-e9e5188e (FR-01.04).
"""

from __future__ import annotations

from pathlib import Path

from lib.requirement_impact_baseline import (
    BASELINE_SUBDIR,
    changed_specs_since,
    discover_baseline_scopes,
    read_baseline,
    snapshot_specs,
    write_baseline,
)

SPEC_A = ".shipwright/planning/01-checkout/spec.md"
SPEC_B = ".shipwright/planning/02-billing/spec.md"


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _decl_dir(root: Path) -> Path:
    return root / ".shipwright" / "planning" / "requirement-impact"


# --------------------------------------------------------------------------
# snapshot_specs
# --------------------------------------------------------------------------

def test_snapshot_covers_every_requirement_spec(tmp_path):
    _write(tmp_path, SPEC_A, "one")
    _write(tmp_path, SPEC_B, "two")
    assert sorted(snapshot_specs(tmp_path)) == [SPEC_A, SPEC_B]


def test_snapshot_excludes_iterate_scratch_and_non_specs(tmp_path):
    _write(tmp_path, SPEC_A, "one")
    _write(tmp_path, ".shipwright/planning/iterate/2026-07-27-x/spec.md", "scratch")
    _write(tmp_path, ".shipwright/planning/01-checkout/notes.md", "notes")
    assert list(snapshot_specs(tmp_path)) == [SPEC_A]


def test_snapshot_of_a_project_without_planning_is_empty(tmp_path):
    assert snapshot_specs(tmp_path) == {}


# --------------------------------------------------------------------------
# changed_specs_since — the actual predicate
# --------------------------------------------------------------------------

def test_an_untouched_spec_is_not_a_change(tmp_path):
    """The bug this exists to kill: an untracked, unedited spec counted as a touch."""
    _write(tmp_path, SPEC_A, "unchanged")
    baseline = write_baseline(_decl_dir(tmp_path), run_id="r", phase="design",
                              scope="round-1", project_root=tmp_path)
    assert changed_specs_since(baseline, tmp_path) == []


def test_an_edited_spec_is_a_change(tmp_path):
    _write(tmp_path, SPEC_A, "before")
    baseline = write_baseline(_decl_dir(tmp_path), run_id="r", phase="design",
                              scope="round-1", project_root=tmp_path)
    _write(tmp_path, SPEC_A, "after")
    assert changed_specs_since(baseline, tmp_path) == [SPEC_A]


def test_a_newly_created_spec_is_a_change(tmp_path):
    _write(tmp_path, SPEC_A, "one")
    baseline = write_baseline(_decl_dir(tmp_path), run_id="r", phase="design",
                              scope="round-1", project_root=tmp_path)
    _write(tmp_path, SPEC_B, "brand new split")
    assert changed_specs_since(baseline, tmp_path) == [SPEC_B]


def test_a_removed_spec_is_a_change(tmp_path):
    _write(tmp_path, SPEC_A, "one")
    _write(tmp_path, SPEC_B, "two")
    baseline = write_baseline(_decl_dir(tmp_path), run_id="r", phase="design",
                              scope="round-1", project_root=tmp_path)
    (tmp_path / SPEC_B).unlink()
    assert changed_specs_since(baseline, tmp_path) == [SPEC_B]


def test_only_the_edited_spec_is_reported(tmp_path):
    _write(tmp_path, SPEC_A, "a")
    _write(tmp_path, SPEC_B, "b")
    baseline = write_baseline(_decl_dir(tmp_path), run_id="r", phase="design",
                              scope="round-1", project_root=tmp_path)
    _write(tmp_path, SPEC_B, "b changed")
    assert changed_specs_since(baseline, tmp_path) == [SPEC_B]


def test_a_malformed_baseline_reports_no_changes(tmp_path):
    """Fail-closed: the recorder treats 'no changes' as a refusal for modify."""
    assert changed_specs_since({"specs": "not a dict"}, tmp_path) == []
    assert changed_specs_since({}, tmp_path) == []


# --------------------------------------------------------------------------
# Storage + round registry
# --------------------------------------------------------------------------

def test_baseline_round_trips(tmp_path):
    _write(tmp_path, SPEC_A, "one")
    write_baseline(_decl_dir(tmp_path), run_id="r", phase="design",
                   scope="round-1", project_root=tmp_path)
    stored = read_baseline(_decl_dir(tmp_path), run_id="r", phase="design",
                           scope="round-1")
    assert stored["scope"] == "round-1"
    assert list(stored["specs"]) == [SPEC_A]


def test_a_missing_baseline_reads_as_none(tmp_path):
    assert read_baseline(_decl_dir(tmp_path), run_id="r", phase="design",
                         scope="round-9") is None


def test_a_damaged_baseline_reads_as_none_so_the_declaration_fails_closed(tmp_path):
    directory = _decl_dir(tmp_path) / BASELINE_SUBDIR
    directory.mkdir(parents=True)
    from lib.requirement_impact_store import declaration_filename
    (directory / declaration_filename("r", "design", "round-1")).write_text(
        "{broken", encoding="utf-8")
    assert read_baseline(_decl_dir(tmp_path), run_id="r", phase="design",
                         scope="round-1") is None


def test_baselines_do_not_pollute_the_declaration_reader(tmp_path):
    """They live in a subdirectory, so the declarations' *.json glob misses them."""
    from lib.requirement_impact_store import read_declarations
    _write(tmp_path, SPEC_A, "one")
    write_baseline(_decl_dir(tmp_path), run_id="r", phase="design",
                   scope="round-1", project_root=tmp_path)
    records, problems = read_declarations(_decl_dir(tmp_path))
    assert records == [] and problems == []


def test_round_registry_lists_this_run_and_phase_only(tmp_path):
    _write(tmp_path, SPEC_A, "one")
    for run_id, phase, scope in (("r", "design", "round-2"),
                                 ("r", "design", "round-1"),
                                 ("r", "build", "01-auth"),
                                 ("other", "design", "round-9")):
        write_baseline(_decl_dir(tmp_path), run_id=run_id, phase=phase,
                       scope=scope, project_root=tmp_path)

    assert discover_baseline_scopes(_decl_dir(tmp_path), run_id="r",
                                    phase="design") == ["round-1", "round-2"]


def test_round_registry_is_empty_when_nothing_snapshotted(tmp_path):
    assert discover_baseline_scopes(_decl_dir(tmp_path), run_id="r",
                                    phase="design") == []
