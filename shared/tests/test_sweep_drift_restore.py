"""The restore no longer overwrites a late append — audit 2026-07-28, finding 23.

``commit_main_tracked_drift`` re-reads HEAD and the tracked log, then spawns
``git checkout -- <log>``. An append landing in between was overwritten, unobserved,
and the sweep reported success; the code called that unavoidable. It is not: the log
is now renamed aside atomically first, so whatever it held is preserved and a
well-formed late append is recovered into the outbox instead of destroyed.

Each simulated writer lands in the REAL window — between the plan's last read and
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
from lib.git_base import run_git_soft  # noqa: E402
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


# --- the hazard is real ------------------------------------------------------

def test_a_bare_checkout_destroys_a_late_append(repo) -> None:
    """Negative control: what the old restore did. Without this the tests below
    could pass against a mechanism that was never needed."""
    _add_drift(repo, h.item("trg-late"))
    assert "trg-late" in _log(repo).read_text(encoding="utf-8")
    assert run_git_soft(["checkout", "--", TRIAGE], cwd=repo).returncode == 0
    assert "trg-late" not in _log(repo).read_text(encoding="utf-8")


# --- the happy paths ---------------------------------------------------------

def test_clean_restore_leaves_no_salvage_behind(repo) -> None:
    _add_drift(repo, h.item("trg-drift"))
    plan = plan_main_tracked_drift(repo, _outbox(repo))
    assert plan.status == "adoptable"

    result = commit_main_tracked_drift(plan, repo, _outbox(repo))

    assert result.status == "adopted" and result.reason == ""
    assert "trg-drift" not in _log(repo).read_text(encoding="utf-8")   # restored to HEAD
    assert "trg-drift" in _outbox(repo).read_text(encoding="utf-8")    # and buffered
    assert _salvages(repo) == []


def test_late_append_is_recovered_instead_of_destroyed(repo, monkeypatch) -> None:
    """AC-7. The line lands inside the residual window and survives."""
    _add_drift(repo, h.item("trg-drift"))
    plan = plan_main_tracked_drift(repo, _outbox(repo))
    _writer_lands_in_the_window(monkeypatch, repo, h.item("trg-late") + "\n")

    result = commit_main_tracked_drift(plan, repo, _outbox(repo))

    assert result.status == "adopted"
    assert "main_tracked_late_append_salvaged" in result.reason
    assert result.adopted == 2                       # the drift line plus the late one
    outbox = _outbox(repo).read_text(encoding="utf-8")
    assert "trg-late" in outbox and "trg-drift" in outbox
    assert _salvages(repo) == []                     # dropped only after the outbox write


def test_late_append_adoption_is_idempotent(repo, monkeypatch) -> None:
    """A replay must not double-buffer a line already in the outbox."""
    _add_drift(repo, h.item("trg-drift"))
    h.write_outbox(repo, h.item("trg-late"))
    plan = plan_main_tracked_drift(repo, _outbox(repo))
    _writer_lands_in_the_window(monkeypatch, repo, h.item("trg-late") + "\n")

    result = commit_main_tracked_drift(plan, repo, _outbox(repo))

    assert result.status == "adopted"
    body = _outbox(repo).read_text(encoding="utf-8")
    assert body.count("trg-late") == 1


# --- salvage naming + placement contracts ------------------------------------

def test_salvage_names_are_exclusive(repo) -> None:
    """Two claims must never hand out the same path — one would silently clobber the
    other's preserved bytes."""
    log = _log(repo)
    first = sdr._claim_salvage_path(log)
    second = sdr._claim_salvage_path(log)
    assert first != second and first.exists() and second.exists()


def test_salvage_path_is_gitignored_by_the_shipped_template(tmp_path: Path) -> None:
    """A salvage file must never become tracked drift of its own — in EVERY project,
    not just this one.

    Asserted against ``shared/templates/shipwright-gitignore.template``, the SSoT
    every adopter's ``.gitignore`` is generated from, rather than against the sweep
    fixture (whose ``.gitignore`` covers only the outbox, so it proved nothing) or
    against this repo's own file (which would make the test inherit its state). The
    rule relied on is ``/.shipwright/*`` plus EXACT negations: ``!/.shipwright/
    triage.jsonl`` re-includes that one name, never ``triage.jsonl.salvage-…`` —
    the same reason the template's own comment gives for ``.lock`` and ``.bak``.
    """
    template = (_SHARED / "templates" / "shipwright-gitignore.template").read_text(encoding="utf-8")
    scratch = tmp_path / "adopter"
    (scratch / ".shipwright").mkdir(parents=True)
    h.git(tmp_path, "init", "adopter")
    (scratch / ".gitignore").write_text(template, encoding="utf-8", newline="\n")

    claimed = sdr._claim_salvage_path(scratch / TRIAGE)
    rel = claimed.relative_to(scratch).as_posix()

    assert h.git(scratch, "check-ignore", "-q", rel, check=False).returncode == 0, rel
    # Control: the tracked log itself is NOT ignored, so the assertion above cannot
    # be passing merely because everything under .shipwright/ is.
    assert h.git(scratch, "check-ignore", "-q", TRIAGE, check=False).returncode != 0
