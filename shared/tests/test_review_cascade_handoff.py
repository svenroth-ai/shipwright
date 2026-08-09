"""Review-cascade section of the in-flight iterate handoff
(iterate-2026-08-09-compaction-state-audit).

Split out of ``test_generate_session_handoff.py`` rather than appended there:
that file already carries a grandfathered bloat-baseline entry, so growing it
further would ratchet past its `current` ceiling. See that file for the
sibling `render_iterate_progress()` tests (external-review marker, run_id/
complexity parsing) this file assumes as background.
"""

from __future__ import annotations

import json

from lib.handoff_iterate import render_iterate_progress


def _write_iterate_spec(project_root, *, run_id: str, complexity: str, branch_tail: str) -> None:
    """Minimal iterate spec file matching a branch tail (mirrors the helper
    of the same name in test_generate_session_handoff.py)."""
    iterate_dir = project_root / ".shipwright" / "planning" / "iterate"
    iterate_dir.mkdir(parents=True, exist_ok=True)
    spec = iterate_dir / f"2026-04-17-{branch_tail}.md"
    spec.write_text(
        "\n".join([
            f"# Iterate Spec: {branch_tail}",
            "",
            f"- **Run ID:** {run_id}",
            "- **Type:** feature",
            f"- **Complexity:** {complexity}",
            "- **Status:** draft",
        ]),
        encoding="utf-8",
    )


def _write_reviews_json(project_root, *, run_id: str, statuses: dict) -> None:
    """Write a minimal reviews.json. ``statuses`` maps review_type -> status;
    any type from REVIEW_TYPES not given defaults to 'pending'."""
    from lib.review_record_schema import REVIEW_TYPES

    record_dir = project_root / ".shipwright" / "planning" / "iterate" / run_id
    record_dir.mkdir(parents=True, exist_ok=True)
    reviews = {
        t: {
            "review_type": t,
            "status": statuses.get(t, "pending"),
            "findings_count": 0,
            "findings": [],
            "provider": None,
            "completed_at": None,
            "disposition": None,
            "recorded_by": None,
            "parse_status": None,
            "raw_excerpt": None,
        }
        for t in REVIEW_TYPES
    }
    (record_dir / "reviews.json").write_text(
        json.dumps({"schema_version": 1, "run_id": run_id, "reviews": reviews}),
        encoding="utf-8",
    )


def test_review_cascade_not_started_when_reviews_json_absent(tmp_project):
    """No reviews.json yet (before Step 7/self-review) — must not crash and
    must not falsely claim an interruption."""
    _write_iterate_spec(
        tmp_project, run_id="iterate-2026-08-09-notstarted",
        complexity="medium", branch_tail="notstarted",
    )

    lines = render_iterate_progress(tmp_project, {"branch": "iterate/notstarted"})
    text = "\n".join(lines)

    assert "Review Cascade" in text and "not started" in text
    assert "Review cascade interrupted" not in text


def test_review_cascade_not_due_yet_when_self_pending(tmp_project):
    """A freshly-init'd record has every type pending — must read as 'not
    due yet', never as an interrupted cascade (external plan review, openai
    HIGH finding this fix exists to close)."""
    _write_iterate_spec(
        tmp_project, run_id="iterate-2026-08-09-allpending",
        complexity="medium", branch_tail="allpending",
    )
    _write_reviews_json(tmp_project, run_id="iterate-2026-08-09-allpending", statuses={})

    lines = render_iterate_progress(tmp_project, {"branch": "iterate/allpending"})
    text = "\n".join(lines)

    assert "Review Cascade" in text and "not due yet" in text
    # The cascade itself must not add a replay entry — any replay present
    # here would come from the (unrelated) missing external-review marker.
    assert "Review cascade interrupted" not in text
    assert "reviews.json is unreadable" not in text


def test_review_cascade_interrupted_when_self_terminal_and_others_pending(tmp_project):
    """self completed but code/doubt still pending — the cascade started and
    was interrupted; B1 must be able to see this from the rendered handoff."""
    _write_iterate_spec(
        tmp_project, run_id="iterate-2026-08-09-interrupted",
        complexity="medium", branch_tail="interrupted",
    )
    _write_reviews_json(
        tmp_project, run_id="iterate-2026-08-09-interrupted",
        statuses={"self": "completed", "spec": "completed"},
    )

    lines = render_iterate_progress(tmp_project, {"branch": "iterate/interrupted"})
    text = "\n".join(lines)

    assert "Review Cascade" in text and "interrupted" in text
    assert "code" in text and "doubt" in text
    assert "Mandatory replay on Resume" in text
    assert "Review cascade interrupted" in text


def test_review_cascade_complete_when_self_terminal_and_nothing_pending(tmp_project):
    """Every type terminal — no replay needed for the cascade."""
    _write_iterate_spec(
        tmp_project, run_id="iterate-2026-08-09-done",
        complexity="medium", branch_tail="done",
    )
    _write_reviews_json(
        tmp_project, run_id="iterate-2026-08-09-done",
        statuses={t: "completed" for t in
                  ("self", "plan", "plan_internal", "code", "doubt", "external_code", "spec")},
    )

    lines = render_iterate_progress(tmp_project, {"branch": "iterate/done"})
    text = "\n".join(lines)

    assert "Review Cascade" in text and "complete" in text
    assert "Review cascade interrupted" not in text


def test_review_cascade_unreadable_reviews_json_flags_replay(tmp_project):
    """A malformed reviews.json is a data-integrity fault, not an absence —
    it must surface as 'unreadable' and force a replay entry, never be
    silently treated as 'not started'."""
    _write_iterate_spec(
        tmp_project, run_id="iterate-2026-08-09-broken",
        complexity="medium", branch_tail="broken",
    )
    record_dir = (
        tmp_project / ".shipwright" / "planning" / "iterate" / "iterate-2026-08-09-broken"
    )
    record_dir.mkdir(parents=True, exist_ok=True)
    (record_dir / "reviews.json").write_text("{not valid json", encoding="utf-8")

    lines = render_iterate_progress(tmp_project, {"branch": "iterate/broken"})
    text = "\n".join(lines)

    assert "Review Cascade" in text and "unreadable" in text
    assert "Mandatory replay on Resume" in text
    assert "reviews.json is unreadable" in text


def test_review_cascade_silent_when_complexity_unresolvable(tmp_project):
    """No reviews.json AND no resolvable complexity (no spec, no complexity
    line in the mini-plan) — the 'not started' notice would be noise here,
    since there is no evidence a review cascade is even due yet. Must stay
    silent, matching the prior degraded behavior, rather than announcing
    absence for every run this section cannot fully identify (external
    code-review cascade, openai medium finding)."""
    iterate_dir = tmp_project / ".shipwright" / "planning" / "iterate"
    iterate_dir.mkdir(parents=True, exist_ok=True)
    (iterate_dir / "2026-08-09-nocx-miniplan.md").write_text(
        "\n".join([
            "# Mini-Plan: nocx",
            "",
            "- **Run ID:** iterate-2026-08-09-nocx",
        ]),
        encoding="utf-8",
    )

    lines = render_iterate_progress(tmp_project, {"branch": "iterate/nocx"})
    text = "\n".join(lines)

    assert "iterate-2026-08-09-nocx" in text
    assert "Review Cascade" not in text


def test_review_cascade_resolves_run_id_from_miniplan_when_no_spec(tmp_project):
    """A small-tier run with no iterate spec (medium+ only) still has a
    mini-plan at every tier (iterate-2026-08-09-compaction-state-audit) — the
    run_id fallback must find it so the cascade check still works."""
    iterate_dir = tmp_project / ".shipwright" / "planning" / "iterate"
    iterate_dir.mkdir(parents=True, exist_ok=True)
    (iterate_dir / "2026-08-09-nospec-miniplan.md").write_text(
        "\n".join([
            "# Mini-Plan: nospec",
            "",
            "- **Run ID:** iterate-2026-08-09-nospec",
            "- **Complexity:** small",
        ]),
        encoding="utf-8",
    )
    _write_reviews_json(
        tmp_project, run_id="iterate-2026-08-09-nospec",
        statuses={"self": "completed"},
    )

    lines = render_iterate_progress(tmp_project, {"branch": "iterate/nospec"})
    text = "\n".join(lines)

    assert "iterate-2026-08-09-nospec" in text
    assert "Review Cascade" in text and "interrupted" in text
