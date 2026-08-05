"""`check_test_results_evidence` / `check_test_results_backfill` — infra fail-closed
paths.

Sibling of ``test_check_ci_supplychain_infra.py``: both F11 ERROR gates were, until
trg-4183acd3, two of ``git_helpers._git_available``'s undocumented extra callers
(added by #540 on 2026-08-03, after the finding that named the other five was
written) — folding a git subprocess FAULT into the SAME green SKIP as "no --commit
supplied". This pins the split: no-commit still SKIPs unchanged, but a fault WITH a
commit supplied now fails CLOSED.

Reuses the sibling test modules' fixture builders rather than re-deriving valid
manifest/evidence shapes (ADR-045: monkeypatch by MODULE OBJECT throughout).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from test_test_results_evidence_check import (  # noqa: E402
    RUN_ID as _EVIDENCE_RUN,
    _target as _evidence_target,
)
from test_test_results_backfill_check import (  # noqa: E402
    CURRENT_RUN as _BACKFILL_RUN,
    _commit as _git_commit,
    _manifest,
    _write_artifact_and_summary,
    _write_manifest,
)
from tools.verifiers import test_results_backfill_check as backfill_mod  # noqa: E402
from tools.verifiers import test_results_evidence_check as evidence_mod  # noqa: E402

_FAKE_SHA = "deadbeef" * 5


def _seed_valid_evidence(root: Path) -> None:
    _evidence_target(root).write_bytes(
        __import__("json").dumps({"iterate_latest": {"run_id": _EVIDENCE_RUN}}).encode()
    )


def _seed_valid_backfill(root: Path, monkeypatch) -> None:
    """Stubs ``_validate_source``: full commit/worktree provenance verification is
    already covered by ``test_test_results_backfill_check.py``; these tests only
    need to reach the git-context branch past it."""
    raw = _write_artifact_and_summary(root)
    _write_manifest(root, _manifest(raw, "test:seed"))
    monkeypatch.setattr(backfill_mod, "_validate_source", lambda *a, **k: None)


# --- check_test_results_evidence ------------------------------------------------


def test_evidence_no_commit_still_skips_unchanged(tmp_path, monkeypatch):
    """The pre-existing, legitimate SKIP — untouched by this migration.

    Pins AC-4's ordering, not just its outcome: ``git_context`` must never be
    called when no commit was supplied (a regression to ``if not commit_hash or
    git_context(root) != ...`` would still return a skip here, since a plain
    ``tmp_path`` is itself ``not_git`` — external code review caught that this
    outcome-only assertion could not detect the ordering regressing)."""
    def _must_not_be_called(root):
        raise AssertionError("git_context must not be called when commit_hash is absent")

    monkeypatch.setattr(evidence_mod, "git_context", _must_not_be_called)
    _seed_valid_evidence(tmp_path)
    res = evidence_mod.check_test_results_evidence(tmp_path, _EVIDENCE_RUN)
    assert res.is_skipped, res


def test_evidence_not_a_git_repo_with_a_commit_supplied_skips(tmp_path):
    _seed_valid_evidence(tmp_path)
    res = evidence_mod.check_test_results_evidence(tmp_path, _EVIDENCE_RUN, _FAKE_SHA)
    assert res.is_skipped, res


def test_evidence_git_fault_with_a_commit_supplied_errors(tmp_path, monkeypatch):
    """The fail-open class this migration removes."""
    _seed_valid_evidence(tmp_path)
    monkeypatch.setattr(evidence_mod, "git_context", lambda root: "git_error")
    res = evidence_mod.check_test_results_evidence(tmp_path, _EVIDENCE_RUN, _FAKE_SHA)
    assert res.ok is False and not res.is_skipped, res


def test_evidence_refusal_does_not_claim_unconditional_unavailability(tmp_path, monkeypatch):
    _seed_valid_evidence(tmp_path)
    monkeypatch.setattr(evidence_mod, "git_context", lambda root: "git_error")
    detail = evidence_mod.check_test_results_evidence(
        tmp_path, _EVIDENCE_RUN, _FAKE_SHA,
    ).detail.lower()
    assert "git" in detail


def test_evidence_unrecognised_git_context_fails_closed(tmp_path, monkeypatch):
    """Proceed only on an EXPLICIT ``work_tree`` — any other value must refuse,
    not fall through to the fail-OPEN path."""
    _seed_valid_evidence(tmp_path)
    monkeypatch.setattr(evidence_mod, "git_context", lambda root: "something_new")
    res = evidence_mod.check_test_results_evidence(tmp_path, _EVIDENCE_RUN, _FAKE_SHA)
    assert res.ok is False and not res.is_skipped, res


def test_evidence_localized_non_repo_message_still_skips(tmp_path, monkeypatch):
    """git uses gettext; a localized 'fatal:' for a genuine non-git dir must not
    read as a git_error and turn the documented SKIP into a hard block."""
    from tools.verifiers import git_helpers as gh  # noqa: PLC0415

    _seed_valid_evidence(tmp_path)
    monkeypatch.setattr(
        gh, "_run_git",
        lambda *a, **k: (128, "", "fatal: Kein Git-Repository (oder eines der Elternverzeichnisse)"),
    )
    assert gh.git_context(tmp_path) == "not_git"
    assert evidence_mod.check_test_results_evidence(tmp_path, _EVIDENCE_RUN, _FAKE_SHA).is_skipped


def test_evidence_real_work_tree_still_reaches_commit_enforcement(git_origin_repo):
    """The migration must not turn a healthy repo into an ERROR — an uncommitted
    working file still fails for the COMMIT reason, not a git one."""
    root, _o = git_origin_repo
    _seed_valid_evidence(root)
    (root / "unrelated.txt").write_text("x", encoding="utf-8")
    commit = _git_commit(root, "unrelated.txt")
    # The evidence file itself was never staged/committed above.
    res = evidence_mod.check_test_results_evidence(root, _EVIDENCE_RUN, commit)
    assert res.ok is False and not res.is_skipped, res
    assert "absent from" in res.detail, res.detail


# --- check_test_results_backfill -------------------------------------------------


def test_backfill_no_commit_still_skips_unchanged(tmp_path, monkeypatch):
    """Pins AC-4's ordering, not just its outcome — see the evidence-side sibling
    test for why an outcome-only assertion here would not catch a regression."""
    _seed_valid_backfill(tmp_path, monkeypatch)

    def _must_not_be_called(root):
        raise AssertionError("git_context must not be called when commit_hash is absent")

    monkeypatch.setattr(backfill_mod, "git_context", _must_not_be_called)
    res = backfill_mod.check_test_results_backfill(tmp_path, _BACKFILL_RUN)
    assert res.is_skipped, res


def test_backfill_not_a_git_repo_with_a_commit_supplied_skips(tmp_path, monkeypatch):
    _seed_valid_backfill(tmp_path, monkeypatch)
    res = backfill_mod.check_test_results_backfill(tmp_path, _BACKFILL_RUN, _FAKE_SHA)
    assert res.is_skipped, res


def test_backfill_git_fault_with_a_commit_supplied_errors(tmp_path, monkeypatch):
    """The fail-open class this migration removes."""
    _seed_valid_backfill(tmp_path, monkeypatch)
    monkeypatch.setattr(backfill_mod, "git_context", lambda root: "git_error")
    res = backfill_mod.check_test_results_backfill(tmp_path, _BACKFILL_RUN, _FAKE_SHA)
    assert res.ok is False and not res.is_skipped, res


def test_backfill_an_unrecognised_git_context_fails_closed(tmp_path, monkeypatch):
    _seed_valid_backfill(tmp_path, monkeypatch)
    monkeypatch.setattr(backfill_mod, "git_context", lambda root: "something_new")
    res = backfill_mod.check_test_results_backfill(tmp_path, _BACKFILL_RUN, _FAKE_SHA)
    assert res.ok is False and not res.is_skipped, res


def test_backfill_localized_non_repo_message_still_skips(tmp_path, monkeypatch):
    """git uses gettext; a localized 'fatal:' for a genuine non-git dir must not
    read as a git_error and turn the documented SKIP into a hard block."""
    from tools.verifiers import git_helpers as gh  # noqa: PLC0415

    _seed_valid_backfill(tmp_path, monkeypatch)
    monkeypatch.setattr(
        gh, "_run_git",
        lambda *a, **k: (128, "", "fatal: Kein Git-Repository (oder eines der Elternverzeichnisse)"),
    )
    assert gh.git_context(tmp_path) == "not_git"
    assert backfill_mod.check_test_results_backfill(tmp_path, _BACKFILL_RUN, _FAKE_SHA).is_skipped


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
