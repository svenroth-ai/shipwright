"""`check_spec_impact_recorded` — the infrastructure fail-closed paths.

Sibling of ``test_check_ci_supplychain_infra.py`` and deliberately the same shape:
this F11 ERROR gate was one of ``git_helpers._git_available``'s five (then seven)
remaining callers, green-SKIPping ("skipped (git unavailable — cannot inspect the
branch)") on a git subprocess fault inside a real repository — the exact
conflation ``git_context`` exists to remove, closed here in trg-4183acd3.

The two ways the gate can be unable to see, and only ONE of them is a green skip:

* **not a git work tree** → SKIP. Inapplicable, not a dodge.
* **git subprocess failure / timeout / unparseable refusal** → ERROR.

Monkeypatching is by MODULE OBJECT throughout (ADR-045).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402
from tools.verifiers import iterate_checks as ic  # noqa: E402

_RUN = "iterate-spec-impact-infra"
_FAKE_SHA = "deadbeef" * 5


def _seed_run(root: Path) -> None:
    (root / "shipwright_run_config.json").write_text(
        json.dumps({"iterate_history": [
            {"run_id": _RUN, "complexity": "medium", "type": "change"},
        ]}),
        encoding="utf-8",
    )
    evt = {
        "type": "work_completed", "source": "iterate", "commit": "",
        "adr_id": _RUN, "spec_impact": "modify",
    }
    _write(root, "shipwright_events.jsonl", json.dumps(evt) + "\n")


# --- git context: exactly one of the states is a green skip -------------------


def test_outside_a_git_repo_skips(tmp_path):
    _seed_run(tmp_path)
    res = ic.check_spec_impact_recorded(tmp_path, _RUN, "")
    assert res.is_skipped, res


def test_a_git_fault_inside_a_repo_errors(tmp_path, monkeypatch):
    """The fail-open class this migration removes."""
    _seed_run(tmp_path)
    monkeypatch.setattr(ic, "git_context", lambda root: "git_error")
    res = ic.check_spec_impact_recorded(tmp_path, _RUN, _FAKE_SHA)
    assert res.ok is False and not res.is_skipped, res


def test_an_unrecognised_git_context_fails_closed(tmp_path, monkeypatch):
    """Proceed only on an EXPLICIT ``work_tree`` — any other value must refuse,
    not fall through to the fail-OPEN path."""
    _seed_run(tmp_path)
    monkeypatch.setattr(ic, "git_context", lambda root: "something_new")
    res = ic.check_spec_impact_recorded(tmp_path, _RUN, _FAKE_SHA)
    assert res.ok is False and not res.is_skipped, res


def test_a_definitive_non_repo_answer_is_not_a_git_error(tmp_path, monkeypatch):
    from tools.verifiers import git_helpers as gh  # noqa: PLC0415

    _seed_run(tmp_path)
    monkeypatch.setattr(
        gh, "_run_git",
        lambda *a, **k: (128, "", "fatal: not a git repository (or any of the parent directories)"),
    )
    assert gh.git_context(tmp_path) == "not_git"
    assert ic.check_spec_impact_recorded(tmp_path, _RUN, _FAKE_SHA).is_skipped


def test_a_localized_non_repo_answer_is_still_not_a_git_error(tmp_path, monkeypatch):
    """git uses gettext; a localized 'fatal:' for a genuine non-git dir must not
    read as a git_error and turn the documented SKIP into a hard block."""
    from tools.verifiers import git_helpers as gh  # noqa: PLC0415

    _seed_run(tmp_path)
    monkeypatch.setattr(
        gh, "_run_git",
        lambda *a, **k: (128, "", "fatal: Kein Git-Repository (oder eines der Elternverzeichnisse)"),
    )
    assert gh.git_context(tmp_path) == "not_git"
    assert ic.check_spec_impact_recorded(tmp_path, _RUN, _FAKE_SHA).is_skipped


def test_a_localized_failure_INSIDE_a_repo_is_a_git_error(
        git_origin_repo, make_worktree, monkeypatch):
    """Inside a real work tree with a real ``.git``, an unparseable failure stays
    fail-CLOSED — the gate must refuse with it, not fall back to SKIP."""
    from tools.verifiers import git_helpers as gh  # noqa: PLC0415

    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "spec-impact-localized-inside")
    _seed_run(wt)
    real = gh._run_git

    def _fail_first(root, *args, **kw):
        if args[:2] == ("rev-parse", "--is-inside-work-tree"):
            return 128, "", "fatal: etwas ist schiefgelaufen"
        return real(root, *args, **kw)

    monkeypatch.setattr(gh, "_run_git", _fail_first)
    assert gh.git_context(wt) == "git_error"
    res = ic.check_spec_impact_recorded(wt, _RUN, _FAKE_SHA)
    assert res.ok is False and not res.is_skipped, res


def test_the_refusal_does_not_claim_git_is_unavailable(tmp_path, monkeypatch):
    """The message is half the defect: the old probe SKIPped with "git unavailable
    — cannot inspect the branch" about a directory that answered with a real
    fault, not a missing repository."""
    _seed_run(tmp_path)
    monkeypatch.setattr(ic, "git_context", lambda root: "git_error")
    detail = ic.check_spec_impact_recorded(tmp_path, _RUN, _FAKE_SHA).detail.lower()
    assert "git unavailable" not in detail, detail
    assert "git" in detail


# --- the SKIP that must survive: a real work tree still enforces ---------------


def test_a_real_work_tree_still_reaches_enforcement(git_origin_repo, make_worktree):
    """The migration must not turn every run into an ERROR: a genuine work tree
    with no spec.md touch still fails for the SPEC reason, not a git one."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "spec-impact-realtree")
    _seed_run(wt)
    _write(wt, "app.py", "only a source change\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "feat: no spec touch")
    commit = _git(wt, "rev-parse", "HEAD").stdout.strip()

    res = ic.check_spec_impact_recorded(wt, _RUN, commit)
    assert res.ok is False and not res.is_skipped, res
    assert "touched no" in res.detail, res.detail


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
