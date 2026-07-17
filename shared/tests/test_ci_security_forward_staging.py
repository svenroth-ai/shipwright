"""Forward-staging parity for ``ci-security.json`` in the churn regenerate step
(iterate-2026-07-17-ci-security-forward-staging — closes #375 CR-1).

``resolve_churn_conflicts.regenerate_tracked_snapshots`` re-derives the tracked
snapshots after an ``integrate_main`` merge and stages them from its ``out`` map.
``ci-security.json`` is produced by the SAME ``_update_compliance`` call as the
five compliance MDs but is a ``.json`` — so it was absent from the ``.md``-shaped
``COMPLIANCE_MDS`` and never entered ``out``, never got staged. A fresh
``security.yml`` scan that rewrote it mid-integrate was left modified-but-unstaged
and the refresh was lost (the follow-up commit stages only the index).

The fix folds ``CI_SECURITY_SUMMARY`` into the compliance staging loop — the
forward mirror of ``integrate_main``'s ``DERIVED_MDS | {CI_SECURITY_SUMMARY}``
rollback restore set. These tests pin all three behaviors: a rewritten summary is
recorded + staged (unit), it reaches the ``integrate_main`` follow-up commit with
a clean tree (real-git integration — the ``cross_component`` ``category:"integration"``
behavior), and an UNCHANGED summary is not staged into a phantom commit.

Real-git via the ``git_origin_repo`` / ``make_worktree`` conftest fixtures + the
helpers from ``test_integrate_main`` / ``test_integrate_campaign_status``. NOT
marked ``slow`` so it gates in CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_integrate_campaign_status import _stub_derived_md_producers  # noqa: E402
from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402
from tools import finalize_iterate  # noqa: E402
from tools import integrate_main  # noqa: E402
from tools import resolve_churn_conflicts as rcc  # noqa: E402

_CI_SEC = ".shipwright/compliance/ci-security.json"
_DASH = ".shipwright/compliance/dashboard.md"  # a COMPLIANCE_MD → restricts the loop to the compliance block


def test_regenerate_stages_ci_security_when_rewritten(git_origin_repo, monkeypatch) -> None:
    """AC-1: when ``_update_compliance`` REWRITES ci-security.json (a fresh scan),
    ``regenerate_tracked_snapshots`` records it ``regenerated`` AND stages it."""
    work, _origin = git_origin_repo
    _write(work, _CI_SEC, '{"critical": 0}\n')
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed ci-security")

    fresh = '{"critical": 3, "generated_at": "fresh-scan"}\n'

    def fresh_scan(project_root):
        # update_compliance.py's refresh_ci_security rewrote the summary from a
        # fresh security.yml run; iterdir returns the whole compliance/ dir.
        (Path(project_root) / _CI_SEC).write_text(fresh, encoding="utf-8")
        return [_CI_SEC]

    monkeypatch.setattr(finalize_iterate, "_update_compliance", fresh_scan)

    out = rcc.regenerate_tracked_snapshots(work, "iterate-x", only={_DASH})

    assert out.get(_CI_SEC) == "regenerated", out
    staged = _git(work, "diff", "--cached", "--name-only").stdout.split()
    assert _CI_SEC in staged, staged
    # the STAGED content is the fresh scan, not the committed placeholder.
    assert '"critical": 3' in _git(work, "show", ":" + _CI_SEC).stdout


def test_regenerate_does_not_stage_unchanged_ci_security(git_origin_repo, monkeypatch) -> None:
    """AC-3: fail-soft common case — ``_update_compliance`` ran but left
    ci-security.json untouched (no fresh scan). ``git add`` on an unchanged file is
    a no-op, so it must NOT enter the staged diff (no phantom follow-up commit)."""
    work, _origin = git_origin_repo
    _write(work, _CI_SEC, '{"critical": 0}\n')
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed ci-security")

    # compliance ran (truthy paths) but did not touch ci-security.json.
    monkeypatch.setattr(finalize_iterate, "_update_compliance", lambda pr: ["ok"])

    out = rcc.regenerate_tracked_snapshots(work, "iterate-x", only={_DASH})

    # recorded (mirrors the MDs) but a no-op ``git add`` leaves it out of the diff.
    assert out.get(_CI_SEC) == "regenerated", out
    staged = _git(work, "diff", "--cached", "--name-only").stdout.split()
    assert _CI_SEC not in staged, staged


def test_ci_security_fresh_scan_reaches_followup_commit(git_origin_repo, make_worktree, monkeypatch) -> None:
    """AC-2 (cross_component ``category:"integration"``): a fresh ``security.yml``
    scan that rewrites ci-security.json DURING an ``integrate_main`` regen must be
    STAGED and reach the regenerate follow-up commit — with a clean working tree
    afterwards. Proves ``churn_merge`` (allowlist) ⊕ ``regenerate_tracked_snapshots``
    (forward staging) ⊕ ``integrate_main`` (follow-up commit) compose on real git.
    The forward mirror of the AC-5 rollback-parity test.
    """
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, _CI_SEC, '{"critical": 0}\n')
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed ci-security")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "cisec-fwd")
    _write(wt, _CI_SEC, '{"critical": 1}\n')     # ours
    _git(wt, "commit", "-am", "iterate edits ci-security")

    _write(work, _CI_SEC, '{"critical": 2}\n')   # theirs → both changed → conflict
    _git(work, "commit", "-am", "main advances ci-security")
    _git(work, "push", "origin", "main")

    fresh = '{"critical": 9, "generated_at": "fresh-scan"}\n'
    _stub_derived_md_producers(monkeypatch)  # heavy agent-doc producers → harmless success

    def fresh_scan(project_root):
        # a fresh security.yml run rewrote the summary DURING regen — the exact
        # CR-1 forward-staging scenario (overrides the _stub's no-op _update_compliance).
        (Path(project_root) / _CI_SEC).write_text(fresh, encoding="utf-8")
        return [_CI_SEC]

    monkeypatch.setattr(finalize_iterate, "_update_compliance", fresh_scan)

    result = integrate_main.integrate(wt, "iterate-fwd", do_fetch=True)

    assert result["status"] == "ok", result
    assert "regenerated-followup" in result["steps"], result
    # The fresh scan reached the follow-up commit (HEAD), NOT left modified-but-unstaged.
    assert '"critical": 9' in _git(wt, "show", "HEAD:" + _CI_SEC).stdout
    assert _CI_SEC in _git(wt, "show", "--name-only", "--format=", "HEAD").stdout
    # Working tree is clean — the pre-fix bug left ci-security.json dirty here.
    assert _git(wt, "status", "--porcelain", "--", _CI_SEC).stdout.strip() == ""
