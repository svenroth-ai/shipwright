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


#: Tree-derived keys ``apply_grade_snapshot`` stamps ITSELF, outside the
#: ``lineage_fields`` projection. ``dirty`` is captured before the producer writes
#: and handed in (trg-f5ae5371) rather than resolved by the lineage resolver, but it
#: is derived from the tree just the same — so it is refused just the same. Adding a
#: name here must be a deliberate act, which is why the set is written out rather
#: than computed.
_SELF_STAMPED_ATTRIBUTION = {"dirty"}


def test_attribution_keys_cover_everything_derived_from_the_tree():
    """The refusal list must not drift behind what actually reaches the log.

    ``ATTRIBUTION_KEYS`` is what `event_amended --fields` refuses. What reaches the
    log is the `lineage_fields` projection PLUS the fields this module stamps on its
    own. They are maintained by hand across three modules, and each iterate has had
    to *remember* to keep them aligned — a future field added to one and not the
    other would be assertable again, which is the exact hole the refusal exists to
    close (internal code review, medium).
    """
    from tree_lineage import TreeLineage, lineage_fields

    projected = set(lineage_fields(TreeLineage("branch", "b", "abcdef1")))
    assert projected | _SELF_STAMPED_ATTRIBUTION == ATTRIBUTION_KEYS
    assert not projected & _SELF_STAMPED_ATTRIBUTION, (
        "a key is now emitted by BOTH routes — decide which one owns it")


class TestDirtyIsSuppliedNotMeasured:
    """``dirty`` says whether the tree held uncommitted work when the grade was
    measured. It is handed in, because by the time this module runs the producer has
    already rewritten tracked documents and a measurement here would read ``true`` on
    a pristine tree (trg-f5ae5371)."""

    @pytest.mark.parametrize("value", [True, False])
    def test_stamps_the_supplied_value(self, repo: Path, value: bool):
        event: dict = {}
        apply_grade_snapshot(event, grade="A", score=90, project_root=repo,
                             dirty=value)
        assert event["dirty"] is value

    def test_omits_the_key_when_unknown(self, repo: Path):
        """Absent must stay absent: a snapshot that cannot say whether its tree was
        clean must not claim it was."""
        event = {"dirty": True}
        apply_grade_snapshot(event, grade="A", score=90, project_root=repo)
        assert "dirty" not in event

    def test_explicit_unknown_removes_a_stale_value(self, repo: Path):
        """Re-shaping a reused event cannot retain an earlier capture."""
        event = {"dirty": False}
        apply_grade_snapshot(event, grade="A", score=90, project_root=repo,
                             dirty=None)
        assert "dirty" not in event

    @pytest.mark.parametrize("bad", ["true", 1, 0, "", [], {}])
    def test_a_non_bool_never_reaches_the_durable_log(self, repo: Path, bad):
        """The log is read cross-repo; a truthy non-bool would serialise as itself
        and read back as something no consumer has a rule for."""
        event = {"dirty": True}
        apply_grade_snapshot(event, grade="A", score=90, project_root=repo,
                             dirty=bad)
        assert "dirty" not in event

    def test_dirty_is_refused_as_an_amendment(self):
        """AC6 — an amendment able to set ``dirty: false`` could launder a
        work-in-progress measurement into one claiming a committed state."""
        from grade_snapshot_shape import reject_asserted_attribution

        with pytest.raises(ValueError, match="dirty"):
            reject_asserted_attribution({"dirty": False})


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
