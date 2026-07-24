"""Write-set / clean-tree regression suite for the Step 7.5 finalizer.

iterate-2026-07-24-finalizer-events-staging. ``update_compliance.py --phase
security`` writes up to FOUR tracked artifact groups — the compliance MDs, an
appended ``grade_snapshot`` in ``shipwright_events.jsonl`` (one per regen,
unconditional), ``shipwright_compliance_config.json`` (``phases_covered``), and
— when there is no ``origin`` remote to route to the gitignored outbox — a
direct append to the tracked ``.shipwright/triage.jsonl``. The finalizer must
stage ALL of them (mirroring iterate F6's explicit ``git add`` list); leaving
any unstaged leaves a dirty tree that aborts the next ``ensure_current``
pre-merge refresh (exit 6), and the ad-hoc recovery (``git checkout --
shipwright_events.jsonl``) discards the grade snapshot.

Shared helpers + fixtures: ``_finalize_helpers.py`` / ``conftest.py``.
"""

from __future__ import annotations

import subprocess

from _finalize_helpers import (
    committed_files,
    faithful_regen,
    load_finalize_module,
    porcelain,
)


def test_finalize_leaves_clean_tree_after_commit(pipeline_project, monkeypatch):
    """REGRESSION: the full write-set is staged — no dirty leak.

    The pre-fix finalizer staged only ``.shipwright/compliance/``, leaving the
    appended grade_snapshot (and config/triage) dirty after committing. A dirty
    events.jsonl aborts the next ``ensure_current``.
    """
    fsc = load_finalize_module()
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_NON_INTERACTIVE", raising=False)
    monkeypatch.setattr(fsc, "_run_update_compliance", faithful_regen())

    result = fsc.finalize(pipeline_project, scan_id="scan-clean-101")
    assert result["committed"] is True
    assert porcelain(pipeline_project) == "", (
        "finalizer left a dirty working tree — appended event/config not staged"
    )


def test_finalize_commit_includes_events_and_config(pipeline_project, monkeypatch):
    """The snapshot commit carries events.jsonl + config + triage, not just MDs."""
    fsc = load_finalize_module()
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_NON_INTERACTIVE", raising=False)
    monkeypatch.setattr(fsc, "_run_update_compliance", faithful_regen())

    result = fsc.finalize(pipeline_project, scan_id="scan-incl-102")
    assert result["committed"] is True
    touched = committed_files(pipeline_project)
    assert "shipwright_events.jsonl" in touched
    assert "shipwright_compliance_config.json" in touched
    assert ".shipwright/compliance/dashboard.md" in touched
    assert ".shipwright/triage.jsonl" in touched


def test_finalize_commits_when_only_event_changed(pipeline_project, monkeypatch):
    """DERIVED EDGE: MDs unchanged but a grade_snapshot was appended.

    The pre-fix dirty-check keyed on ``.shipwright/compliance/`` only, so it saw
    "no diff", early-returned "unchanged", and left events.jsonl dirty with no
    commit. The event must be committed instead.
    """
    fsc = load_finalize_module()
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_NON_INTERACTIVE", raising=False)
    monkeypatch.setattr(
        fsc, "_run_update_compliance",
        faithful_regen(change_md=False, append_event=True, touch_config=False,
                       append_triage=False),
    )

    result = fsc.finalize(pipeline_project, scan_id="scan-evt-103")
    assert result["committed"] is True
    assert porcelain(pipeline_project) == ""
    assert "shipwright_events.jsonl" in committed_files(pipeline_project)


def test_finalize_stages_direct_triage_append(pipeline_project, monkeypatch):
    """DOUBT-REVIEW REGRESSION: a direct append to the tracked triage.jsonl.

    ``update_compliance`` runs ``emit_sbom_triage`` / ``emit_test_failure_triage``
    on every regen. With no ``origin`` remote (``should_route_to_outbox`` False)
    those append DIRECT to the tracked ``.shipwright/triage.jsonl`` — a fourth
    write target the finalizer must also stage, or it leaks like events.jsonl.
    """
    fsc = load_finalize_module()
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_NON_INTERACTIVE", raising=False)

    # Pre-seed a TRACKED triage.jsonl; the fixture has no `origin`, so producer
    # appends land here directly.
    tri = pipeline_project / ".shipwright" / "triage.jsonl"
    tri.write_text('{"schema":"triage/v1"}\n', encoding="utf-8")
    subprocess.run(["git", "-C", str(pipeline_project), "add", ".shipwright/triage.jsonl"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(pipeline_project), "commit", "-m", "chore: seed triage log"],
                   check=True, capture_output=True)

    monkeypatch.setattr(fsc, "_run_update_compliance", faithful_regen())
    result = fsc.finalize(pipeline_project, scan_id="scan-triage-104")

    assert result["committed"] is True
    assert porcelain(pipeline_project) == ""
    assert ".shipwright/triage.jsonl" in committed_files(pipeline_project)


def test_finalize_tolerates_gitignored_events_log(pipeline_project, monkeypatch):
    """A downstream project may .gitignore events.jsonl — must not error.

    A gitignored+untracked path never appears in ``git status --porcelain``, so
    it is neither staged nor treated as a dirty leak; the MD + config still
    commit cleanly (F6's "skip a path only if gitignored" convention).
    """
    fsc = load_finalize_module()
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_NON_INTERACTIVE", raising=False)

    subprocess.run(["git", "-C", str(pipeline_project), "rm", "--cached",
                    "shipwright_events.jsonl"], check=True, capture_output=True)
    gi = pipeline_project / ".gitignore"
    gi.write_text(gi.read_text(encoding="utf-8") + "shipwright_events.jsonl\n",
                  encoding="utf-8")
    subprocess.run(["git", "-C", str(pipeline_project), "add", ".gitignore"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(pipeline_project), "commit", "-m",
                    "chore: ignore events log"], check=True, capture_output=True)

    monkeypatch.setattr(fsc, "_run_update_compliance", faithful_regen())
    result = fsc.finalize(pipeline_project, scan_id="scan-ign-105")

    assert result["committed"] is True  # MD + config still commit
    assert porcelain(pipeline_project) == ""  # ignored event is not "dirty"
    assert "shipwright_events.jsonl" not in committed_files(pipeline_project)


def test_finalize_tolerates_absent_events_log(pipeline_project, monkeypatch):
    """events.jsonl absent entirely (fake writes only an MD) → no error."""
    fsc = load_finalize_module()
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_NON_INTERACTIVE", raising=False)

    (pipeline_project / "shipwright_events.jsonl").unlink()
    subprocess.run(["git", "-C", str(pipeline_project), "rm", "--cached",
                    "shipwright_events.jsonl"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(pipeline_project), "commit", "-m",
                    "chore: drop events log"], check=True, capture_output=True)

    monkeypatch.setattr(
        fsc, "_run_update_compliance",
        faithful_regen(change_md=True, append_event=False, touch_config=False,
                       append_triage=False),
    )
    result = fsc.finalize(pipeline_project, scan_id="scan-absent-106")
    assert result["committed"] is True
    assert porcelain(pipeline_project) == ""


def test_finalize_reruns_safely_without_dirty_leak(pipeline_project, monkeypatch):
    """Re-run contract: each run commits its own snapshot; tree always clean.

    Replaces the old ``test_finalize_idempotent_across_two_runs``, whose
    "second run = no commit" premise was FALSE — the grade_snapshot append is
    unconditional per regen, so a re-run is not a no-op. What MUST hold is that
    it never leaves the tree dirty.
    """
    fsc = load_finalize_module()
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_NON_INTERACTIVE", raising=False)
    monkeypatch.setattr(fsc, "_run_update_compliance", faithful_regen())

    first = fsc.finalize(pipeline_project, scan_id="scan-rerun-a-107")
    assert first["committed"] is True
    assert porcelain(pipeline_project) == ""

    second = fsc.finalize(pipeline_project, scan_id="scan-rerun-b-107")
    assert second["committed"] is True
    assert porcelain(pipeline_project) == ""
    assert first["commit_sha"] != second["commit_sha"]


def test_finalize_real_update_compliance_leaves_clean_tree(
    pipeline_project, monkeypatch,
):
    """DRIFT GUARD: run the REAL update_compliance, assert no dirty leak.

    The faithful fake models today's write-set. This invokes the actual
    ``update_compliance.py --phase security`` subprocess (no monkeypatch) so
    that if the producer ever grows a write target the finalizer does not stage,
    the invariant "finalize leaves a clean tree" fails here — the hardcoded
    artifact list cannot silently fall behind the producer.
    """
    fsc = load_finalize_module()
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_NON_INTERACTIVE", raising=False)

    result = fsc.finalize(pipeline_project, scan_id="scan-real-108")

    assert porcelain(pipeline_project) == "", (
        "real update_compliance wrote a path the finalizer did not stage — "
        f"finalize result: {result}"
    )
    if result["committed"]:
        assert result.get("commit_sha")
