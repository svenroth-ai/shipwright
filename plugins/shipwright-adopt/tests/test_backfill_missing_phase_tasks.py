"""Unit tests for ``lib.adopted_phase_tasks.backfill_missing_phase_tasks``.

Campaign p4-04-retire-write-once-steps, sub-iterate s2b: s2's seeding
(``build_adopted_phase_task`` via ``write_run_config``) only fires at adopt
time, so a repo adopted BEFORE s2 landed has ``completed_steps`` and no
``phase_tasks[]`` on disk at all. This module gives that gap an owner --
these tests pin the pure backfill function that computes what to add to an
EXISTING config, independent of the CLI wrapper (tested separately in
``test_backfill_phase_tasks_cli.py``).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from lib.adopted_phase_tasks import backfill_missing_phase_tasks, build_adopted_phase_task

_NOW = "2026-09-09T00:00:00+00:00"


def _adopted_config(**overrides) -> dict:
    """The pre-s2 shape: completed_steps + adoption, no phase_tasks[] key at
    all -- exactly what leadwright's real on-disk config looks like (see the
    fixture-based boundary probe below)."""
    base = {
        "pipeline": ["project", "design", "plan", "build", "test", "changelog", "deploy"],
        "status": "complete",
        "current_step": None,
        "completed_steps": ["project", "plan", "build", "test"],
        "standalone": False,
        "adoption": {
            "adopted_at": _NOW,
            "commit_at_adoption": "deadbeef",
            "features_inferred": 0,
            "nested_excluded": [],
            "plugin_version": "0.1.0",
        },
        "updated_at": _NOW,
    }
    base.update(overrides)
    return base


def test_adds_a_phase_tasks_entry_per_completed_step() -> None:
    cfg = _adopted_config()
    updated, added, skipped = backfill_missing_phase_tasks(cfg, now=_NOW)

    assert added == ["project", "plan", "build", "test"]
    assert skipped == []
    phases = {t["phase"] for t in updated["phase_tasks"]}
    assert phases == {"project", "plan", "build", "test"}
    assert all(t["establishedAtAdoption"] is True for t in updated["phase_tasks"])


def test_the_test_phase_backfills_as_skipped_matching_phase_history() -> None:
    """External code review, s2b: leadwright's own real config records
    ``phase_history.test.outcome == "adopted-skipped"``. The backfilled
    ``test`` entry must read ``skipped``, not ``done`` -- pinned here
    directly rather than left to the shared name-keyed rule's say-so."""
    cfg = _adopted_config()

    updated, _added, _skipped = backfill_missing_phase_tasks(cfg, now=_NOW)

    by_phase = {t["phase"]: t for t in updated["phase_tasks"]}
    assert by_phase["test"]["status"] == "skipped"
    assert by_phase["project"]["status"] == "done"
    assert by_phase["plan"]["status"] == "done"
    assert by_phase["build"]["status"] == "done"


def test_original_config_is_not_mutated_in_place() -> None:
    """The pure function must return a NEW dict -- a caller reading the
    original after the call must still see the pre-backfill shape, so a
    partial failure downstream (e.g. the CLI write fails) cannot leave the
    caller's in-memory copy silently changed."""
    cfg = _adopted_config()
    updated, _added, _skipped = backfill_missing_phase_tasks(cfg, now=_NOW)

    assert "phase_tasks" not in cfg
    assert updated is not cfg
    assert "phase_tasks" in updated


def test_is_idempotent_a_second_call_adds_nothing() -> None:
    cfg = _adopted_config()
    once, added_1, _ = backfill_missing_phase_tasks(cfg, now=_NOW)
    twice, added_2, _ = backfill_missing_phase_tasks(once, now=_NOW)

    assert added_1 != []
    assert added_2 == []
    assert twice["phase_tasks"] == once["phase_tasks"]


def test_a_non_adopted_config_is_left_untouched() -> None:
    """Scope guard: this function is the owner of the ADOPTED-config gap
    only. A config with completed_steps but no ``adoption`` key was never
    written by shipwright-adopt, and inventing phase_tasks[] entries for a
    run this code never observed would misrepresent it."""
    cfg = _adopted_config()
    del cfg["adoption"]

    updated, added, skipped = backfill_missing_phase_tasks(cfg, now=_NOW)

    assert added == []
    assert skipped == []
    assert updated == cfg
    assert "phase_tasks" not in updated


def test_a_malformed_adoption_value_is_treated_as_not_adopted() -> None:
    """External code review, s2b: a hand-edited or corrupted config could
    carry ``"adoption": null`` -- present but not a JSON object. A bare
    ``.get()`` on that would crash the caller; this function must treat it
    the same as an absent ``adoption`` key, not guess."""
    cfg = _adopted_config(adoption=None)

    updated, added, skipped = backfill_missing_phase_tasks(cfg, now=_NOW)

    assert added == []
    assert skipped == []
    assert updated == cfg


def test_a_malformed_existing_phase_tasks_value_is_left_untouched() -> None:
    """External code review, s2b: a present-but-non-list ``phase_tasks``
    must never be silently discarded and overwritten with a fresh array --
    that would destroy whatever malformed data was actually there."""
    cfg = _adopted_config(phase_tasks={"not": "a list"})

    updated, added, skipped = backfill_missing_phase_tasks(cfg, now=_NOW)

    assert added == []
    assert skipped == []
    assert updated == cfg
    assert updated["phase_tasks"] == {"not": "a list"}


def test_duplicate_completed_steps_produce_only_one_entry_per_phase() -> None:
    """External code review, s2b: ``have_phases``/``seen`` must be updated
    AS entries are accepted, not only from what already existed on disk --
    otherwise a repeated phase in the source list mints two entries for it
    on the very first backfill, breaking the 'one entry per phase'
    contract this function documents."""
    cfg = _adopted_config(completed_steps=["project", "plan", "project"])

    updated, added, _skipped = backfill_missing_phase_tasks(cfg, now=_NOW)

    assert added == ["project", "plan"]
    phases = [t["phase"] for t in updated["phase_tasks"]]
    assert phases.count("project") == 1


def test_only_the_gap_is_filled_when_phase_tasks_already_partially_present() -> None:
    """A config that mixes a seeded-at-adoption gap with a REAL entry (e.g.
    the repo was adopted, then later driven by /shipwright-run for a new
    feature covering 'build' again) must never touch the real entry."""
    real_build_task = build_adopted_phase_task("build", now=_NOW)
    real_build_task["establishedAtAdoption"] = False
    real_build_task["result"] = {"ok": True}
    cfg = _adopted_config(phase_tasks=[real_build_task])

    updated, added, _skipped = backfill_missing_phase_tasks(cfg, now=_NOW)

    assert added == ["project", "plan", "test"]
    tasks_by_phase = {t["phase"]: t for t in updated["phase_tasks"]}
    assert tasks_by_phase["build"] is real_build_task
    assert tasks_by_phase["build"]["establishedAtAdoption"] is False


def test_an_out_of_vocabulary_completed_step_is_skipped_not_fatal() -> None:
    """completed_steps is a free-form list on old configs (write_run_config
    did not validate it against the Phase enum before s2). One bad entry
    must not block backfilling the valid ones alongside it."""
    cfg = _adopted_config(completed_steps=["project", "not-a-real-phase"])

    updated, added, skipped = backfill_missing_phase_tasks(cfg, now=_NOW)

    assert added == ["project"]
    assert skipped == ["not-a-real-phase"]
    assert {t["phase"] for t in updated["phase_tasks"]} == {"project"}


def test_a_config_with_no_completed_steps_list_is_left_untouched() -> None:
    cfg = _adopted_config()
    cfg["completed_steps"] = None

    updated, added, skipped = backfill_missing_phase_tasks(cfg, now=_NOW)

    assert added == []
    assert skipped == []
    assert updated == cfg


# ---------------------------------------------------------------------------
# Boundary Probe (producer -> file on disk -> consumer): the same real
# consumer test_config_writer_phase_tasks.py pins for a FRESH adoption --
# here for a BACKFILLED pre-existing one, mirroring its cross-plugin file-
# path load (ADR-045).
# ---------------------------------------------------------------------------


def _load_mermaid():
    repo_root = Path(__file__).resolve().parents[3]
    mod_path = (
        repo_root / "plugins" / "shipwright-compliance" / "scripts" / "lib" / "mermaid.py"
    )
    spec = importlib.util.spec_from_file_location("mermaid_backfill_probe", mod_path)
    assert spec is not None and spec.loader is not None
    mermaid = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mermaid)
    return mermaid


def test_backfilled_phases_read_as_complete_by_dashboard_phase_strip() -> None:
    """AC1: an adopted config written before this campaign reads correctly
    after the backfill. Probed with a non-'complete' pipeline_status, the
    branch that actually consults phase_tasks[] (a driven-run-in-progress
    config feeding an adoption's already-done phases through the SAME
    reader test_config_writer_phase_tasks.py pins for a fresh write)."""
    cfg = _adopted_config()
    updated, _added, _skipped = backfill_missing_phase_tasks(cfg, now=_NOW)

    mermaid = _load_mermaid()
    for phase in ("project", "plan", "build", "test"):
        status = mermaid._get_phase_status(phase, "in_progress", {"run": updated})
        assert status == "complete", (
            f"phase {phase!r} read as {status!r} after backfill -- an adopted "
            "repo predating the campaign must not render as having skipped it"
        )
