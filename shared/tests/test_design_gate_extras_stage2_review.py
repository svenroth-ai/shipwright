"""Regression tests for Stage-2 code-review findings on
`shared/scripts/lib/design_gate_extras.py`, iterate-2026-09-11-e1-checks-
plan-design. Split out from `test_design_gate_extras.py` to stay under
that file's own size budget.
"""

import subprocess
from pathlib import Path

from lib.design_gate_extras import (
    chrome_nav_targets_consistent,
    standalone_html_violations,
    uploads_preserved,
)


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


def test_the_git_pathspec_is_repo_relative_not_absolute(tmp_path, monkeypatch):
    """External Tier-3 review, iterate-2026-09-11-e1-checks-plan-design: an
    absolute pathspec passed straight to git can be rejected on some
    platforms, and the failure was swallowed as "no evidence" (a false
    pass). Captures the actual argv git would receive — a same-tmp_path
    (absolute-vs-absolute) comparison would pass on the old code too."""
    import subprocess as subprocess_module

    from lib import design_gate_extras

    repo = tmp_path / "repo"
    repo.mkdir()
    captured = {}

    def _fake_run(argv, **kwargs):
        captured["argv"] = argv
        return subprocess_module.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(design_gate_extras.subprocess, "run", _fake_run)
    design_gate_extras.uploads_preserved(repo, repo / ".shipwright" / "designs" / "uploads")
    pathspec = captured["argv"][-1]
    assert pathspec == ".shipwright/designs/uploads"


def test_nav_item_not_first_in_the_class_attribute_is_still_matched():
    """External Tier-3 review, PR #726 round 8: anchoring the class value to
    START with `nav-item`/`topnav-link` false-PASSed `class="active nav-item"`
    as having no nav markup at all."""
    chrome = '<a href="02-dashboard.html" class="nav-item active">Dashboard</a>'
    screen = '<a href="99-secret.html" class="active nav-item">Secret</a>'
    result = chrome_nav_targets_consistent(chrome, screen)
    assert result.ok is False
    assert "99-secret.html" in result.detail


def test_an_unquoted_external_reference_is_still_caught():
    """External Tier-3 review, PR #726 round 8: a quote-only pattern let
    valid unquoted HTML (`<script src=https://cdn.example.com/lib.js>`)
    bypass the standalone gate entirely."""
    html = "<script src=https://cdn.example.com/lib.js></script>"
    assert standalone_html_violations(html) == ["https://cdn.example.com/lib.js"]


def test_a_greater_than_inside_a_quoted_attribute_does_not_truncate_the_tag():
    """Round-8 code review: a hand-rolled `<[^>]+>` tag regex is not
    quote-aware, so a `>` inside an EARLIER quoted attribute (e.g. an inline
    arrow-function handler) truncated the "tag" and silently dropped every
    attribute after it — including the very `src`/`class` this gate exists
    to check."""
    standalone = (
        '<a onclick="items.map(i => i)" href="99-secret.html" class="nav-item">Secret</a>'
    )
    chrome = '<a href="02-dashboard.html" class="nav-item active">Dashboard</a>'
    result = chrome_nav_targets_consistent(chrome, standalone)
    assert result.ok is False
    assert "99-secret.html" in result.detail

    html = '<script onclick="i => i" src="https://cdn.example.com/lib.js"></script>'
    assert standalone_html_violations(html) == ["https://cdn.example.com/lib.js"]


def test_a_duplicated_attribute_resolves_first_wins():
    """Round-8 code review: a dict built by iterating (name, value) pairs
    collapses to LAST-wins on a duplicate attribute; the HTML spec (and
    every browser) is FIRST-wins — a browser loading the first `src` while
    the gate checks the second is a false pass in exactly the direction six
    prior rounds were blocked on."""
    html = '<script src="https://evil.example/x.js" src="local.js"></script>'
    assert standalone_html_violations(html) == ["https://evil.example/x.js"]


def test_a_leading_space_or_backslash_authority_reference_is_still_caught():
    """Round-8b code review: the whitespace-strip and backslash-normalize
    hardening had no regression test — reverting either left the suite
    green. The RAW (unnormalized) value is what gets reported."""
    spaced = '<script src=" https://cdn.example.com/x.js"></script>'
    assert standalone_html_violations(spaced) == [" https://cdn.example.com/x.js"]

    backslashed = '<script src="https:\\\\cdn.example.com\\x.js"></script>'
    assert standalone_html_violations(backslashed) == ["https:\\\\cdn.example.com\\x.js"]


def test_a_scheme_relative_reference_with_no_slashes_is_still_caught():
    """Round-8b code review: deciding "external" by leading-slash count
    missed the WHATWG special-scheme forms a real browser also resolves
    externally — `https:evil.example` (zero slashes) and
    `https:/evil.example` (one) both load from `evil.example`."""
    assert standalone_html_violations(
        '<script src="https:evil.example/x.js"></script>'
    ) == ["https:evil.example/x.js"]
    assert standalone_html_violations(
        '<script src="https:/evil.example/x.js"></script>'
    ) == ["https:/evil.example/x.js"]
