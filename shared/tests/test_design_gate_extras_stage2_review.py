"""Regression tests for Stage-2 code-review findings on
`shared/scripts/lib/design_gate_extras.py`, iterate-2026-09-11-e1-checks-
plan-design. Split out from `test_design_gate_extras.py` to stay under
that file's own size budget.
"""

import subprocess
from pathlib import Path

from lib.design_gate_extras import chrome_nav_targets_consistent, uploads_preserved


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@test.invalid")
    _git(repo, "config", "user.name", "Test")
    return repo


def test_single_quoted_nav_markup_is_also_matched():
    """Double-quote-only used to false-PASS single-quoted markup via the
    "no nav markup" exempt branch instead of comparing — the same gap
    `standalone_html_violations` was already hardened against."""
    chrome = "<a href='02-dashboard.html' class='nav-item active'>Dashboard</a>"
    screen = "<a href='99-secret.html' class='nav-item'>Secret</a>"
    result = chrome_nav_targets_consistent(chrome, screen)
    assert result.ok is False
    assert "99-secret.html" in result.detail


def test_a_staged_new_upload_edited_again_before_commit_is_not_a_violation(tmp_path):
    """An "AM" status (staged-add, then edited again pre-commit) is still
    a NEW, never-committed file per `uploads_preserved`'s own "never-yet-
    committed uploads are not this criterion's concern" — it was never
    "supplied" to begin with."""
    repo = _init_repo(tmp_path)
    uploads = repo / ".shipwright" / "designs" / "uploads"
    uploads.mkdir(parents=True)
    (uploads / "new.md").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    (uploads / "new.md").write_text("edited again pre-commit\n", encoding="utf-8")
    assert uploads_preserved(repo, uploads).ok is True


def test_an_absolute_uploads_path_still_catches_a_modified_upload(tmp_path):
    """External Tier-3 review, iterate-2026-09-11-e1-checks-plan-design: an
    absolute pathspec passed straight to git can be rejected on some
    platforms, and the failure was swallowed as "no evidence" (a false
    pass). The gate now converts to a repo-relative pathspec first — both
    args here are already absolute, as every real caller passes them."""
    repo = _init_repo(tmp_path)
    uploads = repo / ".shipwright" / "designs" / "uploads"
    uploads.mkdir(parents=True)
    (uploads / "brand.md").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add upload")
    (uploads / "brand.md").write_text("changed\n", encoding="utf-8")
    result = uploads_preserved(repo.resolve(), uploads.resolve())
    assert result.ok is False
    assert "brand.md" in result.detail
