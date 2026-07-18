"""Forward-staging parity for ``test-traceability.json`` in the churn regenerate
step (iterate-2026-07-18-churn-allowlist-test-traceability — closes the
CHURN_ALLOWLIST gap iterate #391 hit).

``test-traceability.json`` (the ``test_links`` collector output) is produced by the
SAME ``_update_compliance --phase iterate`` call as the compliance MDs but is a
``.json``, so it was absent from the ``.md``-shaped ``COMPLIANCE_MDS`` — it was
neither in ``CHURN_ALLOWLIST`` (so ``complete_merge`` ABORTED on a conflict) nor in
the regenerate staging loop (so a re-derive would be left modified-but-unstaged).
This mirrors the ``ci-security.json`` CR-1 fix exactly.

These tests pin: it is an allowlisted (resolvable, not blocking) churn artifact; a
rewritten snapshot is recorded + staged (unit); it reaches the ``integrate_main``
follow-up commit with a clean tree (real-git — the ``cross_component``
``category:"integration"`` behavior); and an UNCHANGED snapshot is not staged into
a phantom commit. NOT marked ``slow`` so it gates in CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.churn_merge import CHURN_ALLOWLIST, classify  # noqa: E402
from test_integrate_campaign_status import _stub_derived_md_producers  # noqa: E402
from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402
from tools import finalize_iterate  # noqa: E402
from tools import integrate_main  # noqa: E402
from tools import resolve_churn_conflicts as rcc  # noqa: E402

_TT = ".shipwright/compliance/test-traceability.json"
_DASH = ".shipwright/compliance/dashboard.md"  # a COMPLIANCE_MD → restricts the loop to the compliance block


def test_test_traceability_in_allowlist_not_blocking() -> None:
    """AC-1: a conflicted test-traceability.json is RESOLVABLE (not blocking), so
    ``complete_merge``'s preflight no longer aborts the whole merge on it."""
    assert _TT in CHURN_ALLOWLIST
    resolvable, blocking = classify([_TT])
    assert _TT in resolvable and blocking == []


def test_regenerate_stages_test_traceability_when_rewritten(git_origin_repo, monkeypatch) -> None:
    """AC-2: when ``_update_compliance`` REWRITES test-traceability.json,
    ``regenerate_tracked_snapshots`` records it ``regenerated`` AND stages it."""
    work, _origin = git_origin_repo
    _write(work, _TT, '{"schema_version": 2, "links": []}\n')
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed test-traceability")

    fresh = '{"schema_version": 2, "links": [], "generated_at": "fresh"}\n'

    def fresh_scan(project_root):
        (Path(project_root) / _TT).write_text(fresh, encoding="utf-8")
        return [_TT]

    monkeypatch.setattr(finalize_iterate, "_update_compliance", fresh_scan)

    out = rcc.regenerate_tracked_snapshots(work, "iterate-x", only={_DASH})

    assert out.get(_TT) == "regenerated", out
    staged = _git(work, "diff", "--cached", "--name-only").stdout.split()
    assert _TT in staged, staged
    assert '"generated_at": "fresh"' in _git(work, "show", ":" + _TT).stdout


def test_regenerate_does_not_stage_unchanged_test_traceability(git_origin_repo, monkeypatch) -> None:
    """AC-2: fail-soft common case — ``_update_compliance`` ran but left
    test-traceability.json untouched. A no-op ``git add`` must NOT enter the staged
    diff (no phantom follow-up commit)."""
    work, _origin = git_origin_repo
    _write(work, _TT, '{"schema_version": 2, "links": []}\n')
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed test-traceability")

    monkeypatch.setattr(finalize_iterate, "_update_compliance", lambda pr: ["ok"])

    out = rcc.regenerate_tracked_snapshots(work, "iterate-x", only={_DASH})

    assert out.get(_TT) == "regenerated", out
    staged = _git(work, "diff", "--cached", "--name-only").stdout.split()
    assert _TT not in staged, staged


def test_test_traceability_fresh_scan_reaches_followup_commit(git_origin_repo, make_worktree, monkeypatch) -> None:
    """AC-3 (cross_component ``category:"integration"``): a fresh test-links regen
    that rewrites test-traceability.json DURING an ``integrate_main`` merge must be
    STAGED and reach the regenerate follow-up commit — with a clean working tree
    afterwards. Proves ``churn_merge`` (allowlist) ⊕ ``regenerate_tracked_snapshots``
    (forward staging) ⊕ ``integrate_main`` (follow-up commit) compose on real git —
    i.e. a two-sided conflict on test-traceability.json RESOLVES instead of aborting.
    """
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, _TT, '{"schema_version": 2, "links": [0]}\n')
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed test-traceability")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "tt-fwd")
    _write(wt, _TT, '{"schema_version": 2, "links": [1]}\n')   # ours
    _git(wt, "commit", "-am", "iterate edits test-traceability")

    _write(work, _TT, '{"schema_version": 2, "links": [2]}\n')  # theirs → both changed → conflict
    _git(work, "commit", "-am", "main advances test-traceability")
    _git(work, "push", "origin", "main")

    fresh = '{"schema_version": 2, "links": [9], "generated_at": "fresh"}\n'
    _stub_derived_md_producers(monkeypatch)

    def fresh_scan(project_root):
        (Path(project_root) / _TT).write_text(fresh, encoding="utf-8")
        return [_TT]

    monkeypatch.setattr(finalize_iterate, "_update_compliance", fresh_scan)

    result = integrate_main.integrate(wt, "iterate-fwd", do_fetch=True)

    assert result["status"] == "ok", result
    assert "regenerated-followup" in result["steps"], result
    assert '"links": [9]' in _git(wt, "show", "HEAD:" + _TT).stdout
    assert _TT in _git(wt, "show", "--name-only", "--format=", "HEAD").stdout
    assert _git(wt, "status", "--porcelain", "--", _TT).stdout.strip() == ""
