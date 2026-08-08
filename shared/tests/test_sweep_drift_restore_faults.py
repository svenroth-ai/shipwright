"""Failure paths of the salvage restore — audit 2026-07-28, finding 23.

Split from ``test_sweep_drift_restore.py`` (the happy-path + classification half)
when that file crossed the 300-line guideline. These are the arms the external plan
review called out as the ones a normal integration test never reaches: a rename that
fails, a ``git checkout`` that fails with and without a file reappearing at the path,
an outbox adoption that fails, and the one outcome no replay can finish.

Every simulated writer lands in the REAL window — between the plan's last read and
the rename — by appending from inside ``_claim_salvage_path``, the call immediately
preceding ``os.replace``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parents[1]
for _p in (_SHARED / "scripts", _SHARED / "tests"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import _sweep_helpers as h  # noqa: E402
from lib import sweep_drift_restore as sdr  # noqa: E402
from lib.sweep_drift import commit_main_tracked_drift, plan_main_tracked_drift  # noqa: E402

TRIAGE = ".shipwright/triage.jsonl"



@pytest.fixture
def repo(git_origin_repo, monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    work, _origin = git_origin_repo
    h.set_identity(work)
    h.seed_tracked(work, h.item("trg-seed"))
    return work


def _log(work: Path) -> Path:
    return work / TRIAGE


def _outbox(work: Path) -> Path:
    return work / ".shipwright" / "triage.outbox.jsonl"


def _add_drift(work: Path, *lines: str) -> None:
    with _log(work).open("a", encoding="utf-8", newline="\n") as fh:
        for line in lines:
            fh.write(line + "\n")


def _salvages(work: Path) -> list[Path]:
    return sorted((work / ".shipwright").glob("triage.jsonl.salvage-*"))


def _writer_lands_in_the_window(monkeypatch, work: Path, payload: str):
    """Append ``payload`` to the tracked log between the plan's last read and the
    rename — the exact window the finding is about."""
    real = sdr._claim_salvage_path

    def claim_then_append(triage_path: Path) -> Path:
        claimed = real(triage_path)
        with triage_path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
        return claimed

    monkeypatch.setattr(sdr, "_claim_salvage_path", claim_then_append)


# --- the paths that must preserve rather than guess --------------------------


def test_unparseable_late_content_is_kept_not_adopted(repo, monkeypatch) -> None:
    """Adopting anything that merely DIFFERS would turn corruption into delivery
    input. It is preserved for a human and named in the reason."""
    _add_drift(repo, h.item("trg-drift"))
    plan = plan_main_tracked_drift(repo, _outbox(repo))
    _writer_lands_in_the_window(monkeypatch, repo, "half-written {not js")

    result = commit_main_tracked_drift(plan, repo, _outbox(repo))

    assert "main_tracked_salvage_needs_review" in result.reason
    kept = _salvages(repo)
    assert len(kept) == 1 and "half-written" in kept[0].read_text(encoding="utf-8")
    assert "half-written" not in _outbox(repo).read_text(encoding="utf-8")


def test_a_glued_late_line_is_kept_but_names_the_repair_tool(repo, monkeypatch) -> None:
    """Stage-3 doubt review, medium. A late line that GLUES two well-formed appends
    (the same shape ``plan_main_tracked_drift`` now names on the refusal path) landed
    here as unexplained corruption, on a branch that already reports the sweep as
    ``adopted`` (success) — an unnamed remedy is easier to miss on a success than on a
    refusal. It must still be preserved, not adopted (this predicate never licenses
    moving a glued line), but the reason must say why and how to fix it."""
    _add_drift(repo, h.item("trg-drift"))
    plan = plan_main_tracked_drift(repo, _outbox(repo))
    glued = h.item("trg-glued-a") + h.item("trg-glued-b")
    _writer_lands_in_the_window(monkeypatch, repo, glued + "\n")

    result = commit_main_tracked_drift(plan, repo, _outbox(repo))

    assert result.status == "adopted"
    assert "main_tracked_salvage_glued_line" in result.reason, result.reason
    assert "triage_repair.py" in result.reason, "the escape hatch is unnamed: " + result.reason
    kept = _salvages(repo)
    assert len(kept) == 1 and "trg-glued-a" in kept[0].read_text(encoding="utf-8")
    assert "trg-glued-a" not in _outbox(repo).read_text(encoding="utf-8"), "glue reached delivery"


def test_failed_adoption_keeps_the_salvage_rather_than_dropping_it(repo, monkeypatch) -> None:
    """The salvage is the ONLY copy of a late append until the outbox write lands.
    If that write fails, deleting it would destroy the very line we preserved."""
    _add_drift(repo, h.item("trg-drift"))
    plan = plan_main_tracked_drift(repo, _outbox(repo))
    _writer_lands_in_the_window(monkeypatch, repo, h.item("trg-late") + "\n")

    def refuse_adoption(late, outbox_path):
        raise OSError("simulated outbox write failure")

    monkeypatch.setattr(sdr, "_adopt_late_lines", refuse_adoption)
    result = commit_main_tracked_drift(plan, repo, _outbox(repo))

    assert "main_tracked_salvage_unadopted" in result.reason
    assert "do not delete it" in result.reason
    kept = _salvages(repo)
    assert len(kept) == 1 and "trg-late" in kept[0].read_text(encoding="utf-8")


def test_missing_log_after_a_failed_put_back_is_an_error_not_buffered(repo, monkeypatch) -> None:
    """``buffered`` promises the next sweep completes the restore. Nothing completes
    a restore of a file that is gone, so that outcome gets its own status and the
    sweep stops on it (external plan review R5)."""
    import subprocess as _sp
    _add_drift(repo, h.item("trg-drift"))
    plan = plan_main_tracked_drift(repo, _outbox(repo))

    monkeypatch.setattr(sdr, "run_git_soft",
                        lambda *a, **k: _sp.CompletedProcess(["git"], 1, "", "checkout exploded"))
    claimed: list[Path] = []
    real_claim, real_replace, fired = sdr._claim_salvage_path, sdr.os.replace, []

    def record_claim(triage_path: Path) -> Path:
        got = real_claim(triage_path)
        claimed.append(got)
        return got

    def fail_the_put_back(src, dst):
        # Only the put-back direction, keyed on the claimed path object rather than on
        # the naming scheme, so a rename of the scheme fails this loudly (code review).
        if claimed and Path(src) == claimed[-1]:
            fired.append(src)
            raise OSError("simulated put-back failure")
        return real_replace(src, dst)

    monkeypatch.setattr(sdr, "_claim_salvage_path", record_claim)
    monkeypatch.setattr(sdr.os, "replace", fail_the_put_back)
    result = commit_main_tracked_drift(plan, repo, _outbox(repo))

    assert fired, "the injected put-back failure never fired — the test would be vacuous"
    assert result.status == "error", result
    assert "MISSING" in result.reason and "Restore it by hand" in result.reason
    assert not _log(repo).exists()
    assert len(_salvages(repo)) == 1


def test_a_wholesale_rewrite_is_kept_not_adopted(repo, monkeypatch) -> None:
    """Truncation / replacement is not an append, so the prefix check refuses it."""
    _add_drift(repo, h.item("trg-drift"))
    plan = plan_main_tracked_drift(repo, _outbox(repo))
    real = sdr._claim_salvage_path

    def claim_then_clobber(triage_path: Path) -> Path:
        claimed = real(triage_path)
        triage_path.write_text(h.HEADER + "\n", encoding="utf-8", newline="\n")
        return claimed

    monkeypatch.setattr(sdr, "_claim_salvage_path", claim_then_clobber)
    result = commit_main_tracked_drift(plan, repo, _outbox(repo))

    assert "main_tracked_salvage_not_an_extension" in result.reason
    assert len(_salvages(repo)) == 1


def test_rename_failure_aborts_instead_of_overwriting(repo, monkeypatch) -> None:
    """Falling back to a bare checkout would be the very overwrite this prevents."""
    _add_drift(repo, h.item("trg-drift"))
    plan = plan_main_tracked_drift(repo, _outbox(repo))
    before = _log(repo).read_text(encoding="utf-8")

    # Discriminate on the path the claim helper actually handed out, not on a
    # hardcoded ".salvage-" substring: keying on the naming scheme meant renaming it
    # would silently turn this into a no-op that still passed green (code review).
    claimed: list[Path] = []
    real_claim, real_replace, fired = sdr._claim_salvage_path, sdr.os.replace, []

    def record_claim(triage_path: Path) -> Path:
        got = real_claim(triage_path)
        claimed.append(got)
        return got

    def boom(src, dst):
        # SELECTIVE: `sdr.os` is the process-global `os` module, so a blanket patch
        # also breaks durable_atomic_write's outbox publish and the test would pass
        # for the wrong reason (measured — it did).
        if claimed and Path(dst) == claimed[-1]:
            fired.append(dst)
            raise OSError("simulated sharing violation")
        return real_replace(src, dst)

    monkeypatch.setattr(sdr, "_claim_salvage_path", record_claim)
    monkeypatch.setattr(sdr.os, "replace", boom)
    result = commit_main_tracked_drift(plan, repo, _outbox(repo))

    assert fired, "the injected failure never fired — the test would be vacuous"
    assert result.status == "buffered"
    assert "main_tracked_salvage_rename_failed" in result.reason
    assert _log(repo).read_text(encoding="utf-8") == before   # nothing overwritten
    assert "trg-drift" in _outbox(repo).read_text(encoding="utf-8")   # safe in the outbox
    assert _salvages(repo) == []


def test_checkout_failure_puts_the_log_back(repo, monkeypatch) -> None:
    _add_drift(repo, h.item("trg-drift"))
    plan = plan_main_tracked_drift(repo, _outbox(repo))
    before = _log(repo).read_text(encoding="utf-8")
    monkeypatch.setattr(sdr, "run_git_soft",
                        lambda *a, **k: __import__("subprocess").CompletedProcess(
                            ["git"], 1, "", "checkout exploded"))

    result = commit_main_tracked_drift(plan, repo, _outbox(repo))

    assert result.status == "buffered"
    assert "main_tracked_restore_failed" in result.reason
    assert _log(repo).read_text(encoding="utf-8") == before
    assert _salvages(repo) == []


def test_checkout_failure_with_a_reappeared_file_keeps_both(repo, monkeypatch) -> None:
    """External plan review: unconditionally moving the salvage back would clobber a
    writer that recreated the path after the rename — the same loss, one step later."""
    _add_drift(repo, h.item("trg-drift"))
    plan = plan_main_tracked_drift(repo, _outbox(repo))
    import subprocess as _sp

    def fail_and_recreate(args, **kwargs):
        _log(repo).write_text(h.HEADER + "\n" + h.item("trg-other") + "\n",
                              encoding="utf-8", newline="\n")
        return _sp.CompletedProcess(["git", *args], 1, "", "checkout exploded")

    monkeypatch.setattr(sdr, "run_git_soft", fail_and_recreate)
    result = commit_main_tracked_drift(plan, repo, _outbox(repo))

    assert result.status == "buffered"
    assert "main_tracked_restore_ambiguous" in result.reason
    assert "trg-other" in _log(repo).read_text(encoding="utf-8")      # not clobbered
    kept = _salvages(repo)
    assert len(kept) == 1 and "trg-drift" in kept[0].read_text(encoding="utf-8")


def test_a_later_refusal_still_names_the_salvage(repo, monkeypatch) -> None:
    """The unrecoverable path announces the sole surviving copy ONCE, on stderr, mid
    worktree-setup. From the next iterate on, `main_tracked_diverged` is all the
    operator sees — so that refusal repeats the pointer (doubt review)."""
    _add_drift(repo, h.item("trg-drift"))
    salvage = sdr._claim_salvage_path(_log(repo))
    salvage.write_text(h.HEADER + "\n" + h.item("trg-orphan") + "\n", encoding="utf-8")

    # Control: drift alone is adoptable, so the refusal below is caused by the
    # divergence and not by the salvage file merely existing.
    assert plan_main_tracked_drift(repo, _outbox(repo)).status == "adoptable"

    # Now make the working log a NON-extension of HEAD — the state a failed restore
    # leaves behind — and confirm the refusal names the salvage sitting beside it.
    _log(repo).write_text(h.HEADER + "\n", encoding="utf-8", newline="\n")
    diverged = plan_main_tracked_drift(repo, _outbox(repo))

    assert diverged.status == "refused"
    assert "main_tracked_diverged" in diverged.reason
    assert salvage.name in diverged.reason
    assert "do not `git clean`" in diverged.reason
