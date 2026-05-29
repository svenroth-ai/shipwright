"""Tests for snapshot-provenance audit (iterate-2026-05-23-compliance-md-single-producer).

Group E (E1-E5) audit no longer compares on-disk MDs to a fresh re-render;
it compares them to the last iterate-finalize snapshot. The snapshot is
identified by:

  1. The latest commit whose body contains a ``Run-ID:`` trailer
  2. AND whose tree modifications include at least one file under
     ``.shipwright/compliance/``.

If no such commit exists (greenfield, pre-adoption history), the audit
emits a single ``E0 snapshot-unavailable`` info finding and reports
``any_stale=False`` — by construction, there is no baseline to drift
against.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))


# ---------------------------------------------------------------------------
# Git fixture helpers
# ---------------------------------------------------------------------------


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init", "-b", "main", str(repo)],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e.com"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Tester"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "commit.gpgsign", "false"],
                   check=True, capture_output=True)


def _git_commit(repo: Path, files: dict[str, str], msg: str) -> str:
    """Stage ``files`` (relative paths) and commit with ``msg``. Returns SHA."""
    for rel, content in files.items():
        full = repo / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", msg],
                   check=True, capture_output=True)
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return sha


def _seed_baseline_compliance(_repo: Path | None = None) -> dict[str, str]:
    """Return the 5 canonical compliance MDs as a {rel_path: content} dict.

    The ``_repo`` arg is unused (no longer writes files itself — the
    ``_git_commit`` helper writes whatever dict it gets). Kept optional
    for callers that pass ``main`` / ``tmp_path`` for readability.
    """
    return {
        ".shipwright/compliance/traceability-matrix.md":
            "# Requirements Traceability Matrix\n\nGenerated: 2026-05-23T00:00:00Z\n\nBaseline RTM body\n",
        ".shipwright/compliance/test-evidence.md":
            "# Test Evidence\n\nGenerated: 2026-05-23T00:00:00Z\n\nBaseline test-evidence body\n",
        ".shipwright/compliance/change-history.md":
            "# Commit Change Log\n\nGenerated: 2026-05-23T00:00:00Z\n\nBaseline change-history body\n",
        ".shipwright/compliance/sbom.md":
            "# Software Bill of Materials\n\nGenerated: 2026-05-23T00:00:00Z\n\nBaseline SBOM body\n",
        ".shipwright/compliance/dashboard.md":
            "# Compliance Dashboard\n\nGenerated: 2026-05-23T00:00:00Z\n\nBaseline dashboard body\n",
    }


# ---------------------------------------------------------------------------
# find_snapshot_commit
# ---------------------------------------------------------------------------


def test_find_snapshot_commit_picks_latest_run_id_commit_touching_compliance(tmp_path):
    """When multiple commits qualify, return the most recent one."""
    from scripts.audit.audit_staleness import find_snapshot_commit

    _git_init(tmp_path)
    # Baseline non-iterate commit.
    _git_commit(tmp_path, {"README.md": "Hi\n"}, "chore: init")
    # First iterate adds compliance MDs.
    sha_old = _git_commit(
        tmp_path, _seed_baseline_compliance(tmp_path),
        "feat(iterate): first iterate\n\nRun-ID: iterate-2026-05-01-first\n",
    )
    # Non-iterate commit between iterates (no Run-ID).
    _git_commit(tmp_path, {"README.md": "edited\n"}, "fix: random")
    # Second iterate modifies compliance MDs.
    sha_new = _git_commit(
        tmp_path,
        {".shipwright/compliance/dashboard.md":
         "# Compliance Dashboard\n\nGenerated: 2026-05-24T00:00:00Z\n\nUpdated dashboard\n"},
        "feat(iterate): second iterate\n\nRun-ID: iterate-2026-05-23-second\n",
    )

    sha = find_snapshot_commit(tmp_path)
    assert sha == sha_new
    assert sha != sha_old


def test_find_snapshot_commit_skips_run_id_commits_not_touching_compliance(tmp_path):
    """Run-ID commits that DON'T touch .shipwright/compliance/ are skipped."""
    from scripts.audit.audit_staleness import find_snapshot_commit

    _git_init(tmp_path)
    # Iterate commit that updates MDs.
    sha_compliance = _git_commit(
        tmp_path, _seed_baseline_compliance(tmp_path),
        "feat(iterate): touches compliance\n\nRun-ID: iterate-A\n",
    )
    # A LATER iterate commit that does NOT touch compliance.
    _git_commit(
        tmp_path, {"src/code.py": "print('ok')\n"},
        "feat(iterate): code-only\n\nRun-ID: iterate-B\n",
    )

    # find_snapshot_commit must skip iterate-B (no compliance/ touch)
    # and return iterate-A.
    sha = find_snapshot_commit(tmp_path)
    assert sha == sha_compliance


def test_find_snapshot_commit_skips_compliance_commits_without_run_id(tmp_path):
    """Compliance-touching commits WITHOUT Run-ID: are skipped."""
    from scripts.audit.audit_staleness import find_snapshot_commit

    _git_init(tmp_path)
    # Iterate commit (qualifies).
    sha_iter = _git_commit(
        tmp_path, _seed_baseline_compliance(tmp_path),
        "feat(iterate): real iterate\n\nRun-ID: iterate-X\n",
    )
    # Manual compliance regen — NO Run-ID:.
    _git_commit(
        tmp_path,
        {".shipwright/compliance/dashboard.md":
         "# Compliance Dashboard\n\nGenerated: 2026-05-24T00:00:00Z\n\nManual regen\n"},
        "chore(compliance): manual regen",
    )

    # Must return the iterate, not the manual regen.
    sha = find_snapshot_commit(tmp_path)
    assert sha == sha_iter


def test_find_snapshot_commit_returns_none_when_no_match(tmp_path):
    """Greenfield repo with no qualifying commits returns None."""
    from scripts.audit.audit_staleness import find_snapshot_commit

    _git_init(tmp_path)
    _git_commit(tmp_path, {"README.md": "Hi\n"}, "chore: init")
    _git_commit(tmp_path, {"src/x.py": "x\n"}, "feat: code")

    sha = find_snapshot_commit(tmp_path)
    assert sha is None


def test_find_snapshot_commit_returns_none_when_not_a_git_repo(tmp_path):
    """Non-git directory returns None (greenfield-safe)."""
    from scripts.audit.audit_staleness import find_snapshot_commit

    sha = find_snapshot_commit(tmp_path)
    assert sha is None


# ---------------------------------------------------------------------------
# check_staleness against snapshot
# ---------------------------------------------------------------------------


def test_check_staleness_green_when_on_disk_matches_snapshot(tmp_path):
    """Right after iterate-finalize commit, all 5 docs match snapshot."""
    from scripts.audit.audit_staleness import check_staleness

    _git_init(tmp_path)
    _git_commit(
        tmp_path, _seed_baseline_compliance(tmp_path),
        "feat(iterate): seed compliance\n\nRun-ID: iterate-2026-05-23-seed\n",
    )

    report = check_staleness(tmp_path)
    assert report.snapshot_unavailable is False
    assert report.any_stale is False
    # iterate-2026-05-27 added 3 agent-doc MDs to the registry. The
    # baseline fixture only seeds the 5 compliance MDs — the 3 agent-doc
    # entries are absent on both sides (test fixture didn't seed them,
    # snapshot didn't contain them), so compare_doc returns
    # ``stale=False, error="not-in-snapshot"`` for those.
    assert len(report.docs) == 8
    assert all(d.stale is False for d in report.docs)


def test_check_staleness_green_after_non_compliance_commits_layered(tmp_path):
    """After non-iterate commits that DON'T touch compliance, audit stays green.

    This is the core anti-false-positive guarantee: security work, manual
    fixes, doc edits — none of these can produce E1-E5 findings because
    the snapshot baseline is stable.
    """
    from scripts.audit.audit_staleness import check_staleness

    _git_init(tmp_path)
    _git_commit(
        tmp_path, _seed_baseline_compliance(tmp_path),
        "feat(iterate): seed\n\nRun-ID: iterate-2026-05-23-seed\n",
    )
    # Layer N non-compliance commits on top.
    _git_commit(tmp_path, {"src/a.py": "a\n"}, "feat(security): patch 1")
    _git_commit(tmp_path, {"src/b.py": "b\n"}, "fix(security): patch 2")
    _git_commit(tmp_path, {"src/c.py": "c\n"}, "chore: bump dep")

    report = check_staleness(tmp_path)
    assert report.snapshot_unavailable is False
    assert report.any_stale is False
    assert all(d.stale is False for d in report.docs)


def test_check_staleness_flags_hand_edited_md(tmp_path):
    """Hand-editing an on-disk MD post-snapshot → stale finding for that doc."""
    from scripts.audit.audit_staleness import check_staleness

    _git_init(tmp_path)
    _git_commit(
        tmp_path, _seed_baseline_compliance(tmp_path),
        "feat(iterate): seed\n\nRun-ID: iterate-2026-05-23-seed\n",
    )
    # Hand-edit the dashboard AFTER the snapshot was created.
    (tmp_path / ".shipwright" / "compliance" / "dashboard.md").write_text(
        "# Compliance Dashboard\n\nGenerated: 2026-05-23T00:00:00Z\n\nHand-edited body — drift!\n",
        encoding="utf-8",
    )

    report = check_staleness(tmp_path)
    assert report.any_stale is True
    stale = [d for d in report.docs if d.stale]
    assert len(stale) == 1
    assert stale[0].doc == "dashboard"
    # Snapshot SHA must be present in evidence for the operator hint.
    assert stale[0].snapshot_sha == report.snapshot_sha


def test_check_staleness_emits_e0_when_no_snapshot_available(tmp_path):
    """No iterate-finalize commit yet → E0 info + any_stale=False."""
    from scripts.audit.audit_staleness import check_staleness

    _git_init(tmp_path)
    _git_commit(tmp_path, {"README.md": "Hi\n"}, "chore: init")

    report = check_staleness(tmp_path)
    assert report.snapshot_unavailable is True
    assert report.snapshot_sha is None
    # No false positives — there's no baseline to drift against.
    assert report.any_stale is False


def test_check_staleness_handles_file_missing_at_snapshot(tmp_path):
    """If a doc was added AFTER the snapshot (e.g. new compliance file),
    compare returns ``stale=False, error="not-in-snapshot"`` rather than
    flagging it stale.

    iterate-2026-05-27 (code-reviewer HIGH #1) changed the semantics: a
    doc whose snapshot side is missing is a "registry expansion ahead of
    the snapshot baseline" — not a drift. The next iterate-finalize
    commit introduces the doc into the snapshot; subsequent audits then
    compare normally. Treating this as stale produced 3 false-positive
    Group E entries per audit until the next finalize.
    """
    from scripts.audit.audit_staleness import check_staleness

    _git_init(tmp_path)
    # Snapshot contains only dashboard; the other 4 don't exist yet.
    _git_commit(
        tmp_path,
        {".shipwright/compliance/dashboard.md":
         "# Compliance Dashboard\n\nGenerated: 2026-05-23T00:00:00Z\n\nDashboard only\n"},
        "feat(iterate): partial seed\n\nRun-ID: iterate-partial\n",
    )
    # Operator manually creates the missing 4 files on-disk post-snapshot.
    for rel, content in _seed_baseline_compliance(tmp_path).items():
        if rel == ".shipwright/compliance/dashboard.md":
            continue
        (tmp_path / rel).write_text(content, encoding="utf-8")

    report = check_staleness(tmp_path)
    # Dashboard is consistent with snapshot.
    by_doc = {d.doc: d for d in report.docs}
    assert by_doc["dashboard"].stale is False
    # The 4 missing-at-snapshot docs are now benign per the
    # iterate-2026-05-27 semantics fix.
    for key in ("rtm", "test_evidence", "change_history", "sbom"):
        d = by_doc[key]
        assert d.stale is False, (
            f"{key} flagged stale; iterate-2026-05-27 'not-in-snapshot' "
            f"semantic regressed (error={d.error!r})"
        )
        assert d.error == "not-in-snapshot"


# ---------------------------------------------------------------------------
# Worktree-awareness
# ---------------------------------------------------------------------------


def test_find_snapshot_commit_sees_branch_lineage_from_worktree(tmp_path):
    """Audit invoked from inside a worktree walks the worktree's branch
    lineage — which inherits main's history through branching, so a
    main-branch iterate-finalize commit IS visible.

    More importantly (the case the dogfood revealed): the worktree's
    OWN HEAD commit is also visible, so an iterate audit can find the
    F6 commit it just made. Routing through the main repo would miss
    this because main's HEAD doesn't track the iterate branch.
    """
    from scripts.audit.audit_staleness import find_snapshot_commit

    main = tmp_path / "main"
    main.mkdir()
    _git_init(main)
    main_sha = _git_commit(
        main, _seed_baseline_compliance(),
        "feat(iterate): seed\n\nRun-ID: iterate-from-main\n",
    )

    # Create a linked worktree.
    wt = tmp_path / "wt"
    subprocess.run(
        ["git", "-C", str(main), "worktree", "add", str(wt), "-b", "iterate/x"],
        check=True, capture_output=True,
    )

    # Through inherited lineage, the worktree sees main's commit.
    assert find_snapshot_commit(wt) == main_sha

    # Now simulate an iterate-finalize commit ON the worktree's branch
    # — that commit MUST become the new snapshot (the dogfood case).
    wt_sha = _git_commit(
        wt,
        {".shipwright/compliance/dashboard.md":
         "# Dashboard\n\nGenerated: 2026-05-24T00:00:00Z\n\nWT update\n"},
        "feat(iterate): wt update\n\nRun-ID: iterate-from-wt\n",
    )
    assert find_snapshot_commit(wt) == wt_sha
    # Main repo's view is untouched — still its own latest snapshot.
    assert find_snapshot_commit(main) == main_sha


# ---------------------------------------------------------------------------
# group_e integration — ensure E0 info + per-doc findings are translated
# ---------------------------------------------------------------------------


def test_group_e_emits_e0_info_when_no_snapshot(tmp_path):
    """When no snapshot, Group E emits a single E0 info finding (not 5 fails)."""
    from scripts.audit import group_e

    _git_init(tmp_path)
    _git_commit(tmp_path, {"README.md": "Hi\n"}, "chore: init")

    findings = group_e.run(tmp_path, config=None, data=None)
    # Exactly one E0 info finding (status="skip" or "info" — implementation-defined,
    # but MUST NOT be 5 stale fails).
    e0 = [f for f in findings if f.check_id == "E0"]
    assert len(e0) == 1
    assert e0[0].status != "fail"
    # No per-doc stale fails.
    per_doc_fails = [f for f in findings if f.check_id in ("E1", "E2", "E3", "E4", "E5") and f.status == "fail"]
    assert per_doc_fails == []


# ---------------------------------------------------------------------------
# iterate-2026-05-23-security-adopt-compliance-snapshots:
# Snapshot detection accepts Run-ID from any producer (iterate / adopt /
# security pipeline finalize).
# ---------------------------------------------------------------------------


def test_find_snapshot_commit_accepts_adopt_run_id(tmp_path):
    """``Run-ID: adopt-...`` trailer qualifies the commit as a snapshot."""
    from scripts.audit.audit_staleness import find_snapshot_commit

    _git_init(tmp_path)
    sha = _git_commit(
        tmp_path, _seed_baseline_compliance(tmp_path),
        "chore(shipwright): adopt repository into Shipwright SDLC\n\n"
        "Adopted via /shipwright-adopt using profile=python-cli, scope=full_app.\n\n"
        "Run-ID: adopt-2026-05-23-myrepo\n",
    )
    assert find_snapshot_commit(tmp_path) == sha


def test_find_snapshot_commit_accepts_security_run_id(tmp_path):
    """``Run-ID: security-...`` trailer qualifies the commit as a snapshot."""
    from scripts.audit.audit_staleness import find_snapshot_commit

    _git_init(tmp_path)
    sha = _git_commit(
        tmp_path, _seed_baseline_compliance(tmp_path),
        "chore(compliance): refresh after security scan\n\n"
        "Updated dashboard/test-evidence/change-history/sbom to reflect post-scan state.\n"
        "No FR coverage change (RTM unaffected).\n\n"
        "Run-ID: security-scan-20260523-001\n",
    )
    assert find_snapshot_commit(tmp_path) == sha


def test_find_snapshot_commit_picks_most_recent_across_mixed_producers(tmp_path):
    """iterate + adopt + security commits in mixed order — most recent wins."""
    from scripts.audit.audit_staleness import find_snapshot_commit

    _git_init(tmp_path)
    # Adopt is the first producer (sets baseline).
    _git_commit(
        tmp_path, _seed_baseline_compliance(tmp_path),
        "chore(shipwright): adopt\n\nRun-ID: adopt-2026-05-23-repo\n",
    )
    # Then a security pipeline finalize.
    _git_commit(
        tmp_path,
        {".shipwright/compliance/dashboard.md":
         "# Dashboard\n\nGenerated: 2026-05-24T00:00:00Z\n\nPost-security update\n"},
        "chore(compliance): refresh after security scan\n\nRun-ID: security-001\n",
    )
    # Then an iterate.
    sha_iterate = _git_commit(
        tmp_path,
        {".shipwright/compliance/dashboard.md":
         "# Dashboard\n\nGenerated: 2026-05-25T00:00:00Z\n\nPost-iterate update\n"},
        "feat(iterate): some feature\n\nRun-ID: iterate-2026-05-25-feat\n",
    )

    # Most recent wins — regardless of producer type.
    assert find_snapshot_commit(tmp_path) == sha_iterate


def test_group_e_emits_per_doc_findings_when_snapshot_exists(tmp_path):
    """When snapshot exists and on-disk matches, Group E emits 5 pass findings."""
    from scripts.audit import group_e

    _git_init(tmp_path)
    _git_commit(
        tmp_path, _seed_baseline_compliance(tmp_path),
        "feat(iterate): seed\n\nRun-ID: iterate-2026-05-23\n",
    )

    findings = group_e.run(tmp_path, config=None, data=None)
    per_doc = [f for f in findings if f.check_id in ("E1", "E2", "E3", "E4", "E5")]
    assert len(per_doc) == 5
    assert all(f.status == "pass" for f in per_doc)
