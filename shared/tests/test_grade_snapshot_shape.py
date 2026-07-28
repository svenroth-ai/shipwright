"""One owner for the ``grade_snapshot`` wire shape
(iterate-2026-07-28-grade-snapshot-lineage).

Two producers write this event onto the durable log — the compliance emitter
(``_grade_snapshot.emit_grade_snapshot``) and the manual CLI
(``record_event.py --type grade_snapshot``). They used to build it
independently, so the CLI validated a score the emitter did not, and attribution
added to one would silently not exist on the other. This module is the single
place the shape is decided; these tests pin it, including the invariant that
matters most: **there is no way to produce an unattributed snapshot.**
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from grade_snapshot_shape import ATTRIBUTION_KEYS, apply_grade_snapshot  # noqa: E402


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for args in (
        ("init", "-b", "main"),
        ("config", "user.email", "fixture@example.invalid"),
        ("config", "user.name", "fixture"),
        ("config", "commit.gpgsign", "false"),
    ):
        subprocess.run(["git", "-C", str(root), *args],
                       capture_output=True, text=True, check=True)
    (root / "f.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "f.txt"], check=True,
                   capture_output=True, text=True)
    subprocess.run(["git", "-C", str(root), "commit", "-m", "init"], check=True,
                   capture_output=True, text=True)
    return root


class TestGradeAndScore:
    def test_sets_grade_and_score(self, repo: Path):
        event: dict = {"type": "grade_snapshot"}
        apply_grade_snapshot(event, grade="A", score=95.5, project_root=repo)

        assert event["grade"] == "A"
        assert event["score"] == 95.5

    def test_score_is_coerced_to_float(self, repo: Path):
        event: dict = {}
        apply_grade_snapshot(event, grade="B", score=82, project_root=repo)
        assert isinstance(event["score"], float)

    def test_zero_is_a_valid_worst_score(self, repo: Path):
        event: dict = {}
        apply_grade_snapshot(event, grade="F", score=0, project_root=repo)
        assert event["score"] == 0.0

    def test_missing_grade_rejected(self, repo: Path):
        with pytest.raises(ValueError, match="requires --grade and --score"):
            apply_grade_snapshot({}, grade=None, score=90, project_root=repo)

    def test_missing_score_rejected(self, repo: Path):
        with pytest.raises(ValueError, match="requires --grade and --score"):
            apply_grade_snapshot({}, grade="A", score=None, project_root=repo)

    def test_out_of_range_score_rejected(self, repo: Path):
        with pytest.raises(ValueError, match=r"in \[0, 100\]"):
            apply_grade_snapshot({}, grade="A", score=150, project_root=repo)

    def test_commit_is_included_only_when_supplied(self, repo: Path):
        # Omitted by default because the finalize-time regen runs BEFORE the F6
        # commit, so HEAD would name the PREVIOUS commit.
        without: dict = {}
        apply_grade_snapshot(without, grade="A", score=90, project_root=repo)
        assert "commit" not in without

        with_commit: dict = {}
        apply_grade_snapshot(with_commit, grade="A", score=90,
                             project_root=repo, commit="deadbeef")
        assert with_commit["commit"] == "deadbeef"


def test_attribution_keys_cover_everything_the_resolver_emits():
    """The refusal list must not drift behind the projection.

    ``ATTRIBUTION_KEYS`` is what `event_amended --fields` refuses; `lineage_fields`
    is what actually reaches the log. They are maintained by hand in two modules,
    and this iterate had to *remember* to keep them aligned — a future field added
    to one and not the other would be assertable again, which is the exact hole
    the refusal exists to close (internal code review, medium).
    """
    from tree_lineage import TreeLineage, lineage_fields

    assert set(lineage_fields(TreeLineage("branch", "b", "abcdef1"))) == ATTRIBUTION_KEYS


class TestAttributionIsUnavoidable:
    def test_every_snapshot_is_attributed(self, repo: Path):
        event: dict = {}
        apply_grade_snapshot(event, grade="A", score=90, project_root=repo)

        assert event["lineage"] == "main"
        assert event["branch"] == "main"
        assert 7 <= len(event["base"]) <= 64

    def test_branch_tree_is_attributed_as_such(self, repo: Path):
        subprocess.run(["git", "-C", str(repo), "checkout", "-b", "iterate/x"],
                       capture_output=True, text=True, check=True)
        (repo / "g.txt").write_text("y", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "g.txt"], check=True,
                       capture_output=True, text=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-m", "two"], check=True,
                       capture_output=True, text=True)

        event: dict = {}
        apply_grade_snapshot(event, grade="C", score=70, project_root=repo)

        assert event["lineage"] == "branch"
        assert event["branch"] == "iterate/x"

    def test_non_repo_is_attributed_unknown_not_left_bare(self, tmp_path: Path):
        # The distinction the consumer contract rests on: an ABSENT `lineage`
        # means the event predates attribution, so a producer that merely could
        # not tell must say "unknown" out loud rather than omitting the field.
        event: dict = {}
        apply_grade_snapshot(event, grade="A", score=90, project_root=tmp_path)

        assert event["lineage"] == "unknown"
        assert "branch" not in event
        assert "base" not in event

    def test_a_raising_resolver_still_yields_an_attributed_event(self, repo: Path, monkeypatch):
        # Attribution is metadata on a producer that must never fail because of
        # it: a compliance regen is not abandoned because git misbehaved.
        import grade_snapshot_shape

        def _boom(_root):
            raise RuntimeError("git exploded")

        monkeypatch.setattr(grade_snapshot_shape, "resolve_tree_lineage", _boom)

        event: dict = {}
        apply_grade_snapshot(event, grade="A", score=90, project_root=repo)

        assert event["lineage"] == "unknown"
        assert event["grade"] == "A"

    def test_validation_runs_before_attribution(self, repo: Path):
        # A malformed snapshot must be rejected outright, never written with a
        # tidy lineage stamp on top of an invalid score.
        event: dict = {}
        with pytest.raises(ValueError):
            apply_grade_snapshot(event, grade="A", score=150, project_root=repo)
        assert event == {}
