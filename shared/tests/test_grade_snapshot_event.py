"""record_event ``grade_snapshot`` support (M-Pre-3,
iterate-2026-07-10-grade-snapshot-events).

Lives in a NEW file because the two existing ``test_record_event.py`` modules
are baseline-capped (anti-ratchet would block appending to them — same reason
``test_record_event_lifecycle_integrity.py`` was created).

``grade_snapshot`` is the M-Pre-3 event the compliance dashboard appends once
per Control-Grade regen so the WebUI Ship's-Log can trend the grade. These
tests pin the producer side: the type is an accepted ``--type`` choice, its
``build_event`` branch serialises ``grade``/``score``/optional ``commit``, and
the event round-trips through ``append_event`` → ``read_events``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parents[1] / "scripts" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _tree_lineage_fixtures import commit, git, init_repo  # noqa: E402
from record_event import (  # noqa: E402
    append_event,
    build_event,
    main,
    parse_args,
    read_events,
)


class TestGradeSnapshotTypeAccepted:
    """The closed ``--type`` registry accepts grade_snapshot (drift protection)."""

    def test_cli_accepts_and_lands(self, tmp_path, capsys):
        rc = main([
            "--project-root", str(tmp_path),
            "--type", "grade_snapshot",
            "--grade", "A",
            "--score", "95.5",
        ])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["success"] is True
        assert out["type"] == "grade_snapshot"

        events = read_events(tmp_path)
        assert len(events) == 1
        event = events[0]
        assert event["type"] == "grade_snapshot"
        assert event["grade"] == "A"
        assert event["score"] == 95.5
        assert event["ts"]  # generic timestamp populated
        assert event["id"].startswith("evt-")
        # No --commit supplied → the optional key is omitted (clean wire shape).
        assert "commit" not in event


class TestGradeSnapshotBuildEvent:
    def test_shape_with_commit(self):
        args = parse_args([
            "--project-root", ".",
            "--type", "grade_snapshot",
            "--grade", "B",
            "--score", "82",
            "--commit", "deadbeef",
        ])
        event = build_event(args)
        assert event["type"] == "grade_snapshot"
        assert event["grade"] == "B"
        assert event["score"] == 82.0  # --score is a float
        assert event["commit"] == "deadbeef"

    def test_score_is_float(self):
        args = parse_args([
            "--project-root", ".",
            "--type", "grade_snapshot",
            "--grade", "D", "--score", "63",
        ])
        event = build_event(args)
        assert isinstance(event["score"], float)


class TestGradeSnapshotValidation:
    """grade_snapshot lands on the DURABLE log — the manual CLI must not be able
    to write a null/malformed snapshot (the auto-emitter is already safe)."""

    def test_missing_score_rejected(self):
        args = parse_args(["--project-root", ".", "--type", "grade_snapshot",
                           "--grade", "A"])
        with pytest.raises(ValueError, match="requires --grade and --score"):
            build_event(args)

    def test_missing_grade_rejected(self):
        args = parse_args(["--project-root", ".", "--type", "grade_snapshot",
                           "--score", "90"])
        with pytest.raises(ValueError, match="requires --grade and --score"):
            build_event(args)

    def test_score_out_of_range_rejected(self):
        args = parse_args(["--project-root", ".", "--type", "grade_snapshot",
                           "--grade", "A", "--score", "150"])
        with pytest.raises(ValueError, match=r"in \[0, 100\]"):
            build_event(args)

    def test_score_zero_boundary_accepted(self):
        # grade F / score 0 is a valid (worst) grade — must NOT be rejected.
        args = parse_args(["--project-root", ".", "--type", "grade_snapshot",
                           "--grade", "F", "--score", "0"])
        event = build_event(args)
        assert event["score"] == 0.0


class TestGradeSnapshotRoundTrip:
    """Producer → shipwright_events.jsonl → reader round-trip (io boundary)."""

    def test_append_then_read(self, tmp_path):
        args = parse_args([
            "--project-root", str(tmp_path),
            "--type", "grade_snapshot",
            "--grade", "C", "--score", "71.0",
        ])
        event = build_event(args)
        returned = append_event(tmp_path, event)
        assert returned == event["id"]

        back = read_events(tmp_path)
        assert [e["id"] for e in back] == [event["id"]]
        assert back[0]["type"] == "grade_snapshot"
        assert back[0]["grade"] == "C"
        assert back[0]["score"] == 71.0

    def test_attribution_survives_the_round_trip_with_declared_types(self, tmp_path):
        """The attribution fields cross the JSONL boundary intact and typed as
        the cross-repo consumer contract declares (iterate-2026-07-28-…-lineage).

        ``--project-root`` here is a bare temp dir, not a repo, so this also pins
        the honest-degradation half: an unresolvable tree says ``"unknown"`` out
        loud rather than omitting the field, because an ABSENT ``lineage`` is
        reserved to mean "written before attribution existed".
        """
        args = parse_args([
            "--project-root", str(tmp_path),
            "--type", "grade_snapshot",
            "--grade", "B", "--score", "84.0",
        ])
        event = build_event(args)
        append_event(tmp_path, event)

        back = read_events(tmp_path)[0]
        assert back["lineage"] == "unknown"
        assert isinstance(back["lineage"], str)
        # Nothing was invented for the facts that could not be resolved.
        assert "branch" not in back
        assert "base" not in back


class TestGradeSnapshotAttributionCannotBeAsserted:
    """No caller may hand-write a lineage (external plan review, approach/medium).

    A CLI able to pass ``--lineage main`` from a branch worktree could
    manufacture a false main-lineage point in the exact log the grade trend
    reads. Vocabulary validation would not catch it — ``main`` is a legal value;
    the lie is the assertion. So the flags must not exist at all, and this test
    fails if someone adds them back.
    """

    @pytest.mark.parametrize("key", ["lineage", "branch", "base"])
    def test_an_amendment_cannot_overlay_attribution(self, key):
        """The door the original producer audit missed.

        `event_amended --fields` is a generic top-level field writer, and
        `apply_amendments` overlays it onto the target with a blind merge — no
        allowlist, no target-type check. So the "cannot be asserted" property
        held on the producer path and leaked through the log's own mutator:
        reproduced end to end, a snapshot honestly emitted as
        `lineage=branch score=12` read back as `lineage=main score=99.9`.
        Refusing these keys is the same shape as the `tests` block validation
        that already sits in that branch for exactly this reason.
        """
        with pytest.raises(ValueError, match="derived from the tree, never asserted"):
            build_event(parse_args([
                "--project-root", ".", "--type", "event_amended",
                "--amends", "evt-deadbeef", "--fields", json.dumps({key: "main"}),
            ]))

    def test_an_amendment_may_still_correct_ordinary_fields(self):
        # The refusal must be surgical: amendments are the sanctioned correction
        # channel for everything else, and 27 existing ones overlay spec_impact,
        # change_type, affected_frs and description.
        event = build_event(parse_args([
            "--project-root", ".", "--type", "event_amended",
            "--amends", "evt-deadbeef",
            "--fields", json.dumps({"spec_impact": "none", "description": "fixed"}),
        ]))
        assert event["fields"]["spec_impact"] == "none"

    @pytest.mark.parametrize("flag", ["--lineage", "--branch", "--base"])
    def test_no_flag_can_assert_attribution(self, flag):
        with pytest.raises(SystemExit):
            parse_args([
                "--project-root", ".", "--type", "grade_snapshot",
                "--grade", "A", "--score", "90", flag, "main",
            ])

    def test_the_cli_degrades_honestly_outside_a_repo(self, tmp_path, capsys):
        # Derived, always: even the manual path cannot leave a snapshot
        # unattributed. Outside a repo that derivation is "unknown".
        rc = main([
            "--project-root", str(tmp_path),
            "--type", "grade_snapshot", "--grade", "A", "--score", "90",
        ])
        assert rc == 0
        capsys.readouterr()

        assert read_events(tmp_path)[0]["lineage"] == "unknown"

    def test_the_cli_resolves_a_real_tree_not_just_unknown(self, tmp_path, capsys):
        """AC7's substantive half (external code review, test/medium).

        The degradation test above passes against a CLI hardcoded to stamp
        ``"unknown"``, so on its own it proves nothing about derivation. This
        one runs the CLI against a real repository on an unmerged branch and
        demands the resolved facts.
        """
        repo = init_repo(tmp_path / "repo")
        git(repo, "checkout", "-b", "iterate/cli")
        commit(repo, "two.txt")
        branch_point = git(repo, "rev-parse", "main")

        assert main([
            "--project-root", str(repo),
            "--type", "grade_snapshot", "--grade", "C", "--score", "70",
        ]) == 0
        capsys.readouterr()

        event = read_events(repo)[0]
        assert event["lineage"] == "branch"
        assert event["branch"] == "iterate/cli"
        assert event["base"] == branch_point

    def test_the_cli_resolves_main_lineage_on_the_default_branch(self, tmp_path, capsys):
        repo = init_repo(tmp_path / "repo")

        assert main([
            "--project-root", str(repo),
            "--type", "grade_snapshot", "--grade", "A", "--score", "95",
        ]) == 0
        capsys.readouterr()

        event = read_events(repo)[0]
        assert event["lineage"] == "main"
        assert event["branch"] == "main"
