"""FR-01.04 #2, #3, #5, #6, #8, #9 — the six design-phase gates the ledger
walk found nowhere in code.
"""

import subprocess
from pathlib import Path

from lib.design_gate_extras import (
    chrome_nav_targets_consistent,
    flows_present_for_multi_screen_app,
    iteration_touched_flagged_screens,
    parse_feedback_round,
    standalone_html_violations,
    uploads_preserved,
    visual_tokens_present,
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


# --------------------------------------------------------------------------- #
# #2 — visual_tokens_present
# --------------------------------------------------------------------------- #

GOOD_GUIDELINES = (
    "# Visual Guidelines\n\n"
    "## Typography\n- Primary font: Inter\n\n"
    "## Colors\n| Role | Value |\n|---|---|\n| Background | #fff |\n\n"
    "## Spacing & Layout\n- Base unit: 4px\n"
)


def test_a_complete_guidelines_file_passes(tmp_path):
    p = tmp_path / "visual-guidelines.md"
    p.write_text(GOOD_GUIDELINES, encoding="utf-8")
    assert visual_tokens_present(p).ok is True


def test_a_missing_file_fails(tmp_path):
    result = visual_tokens_present(tmp_path / "visual-guidelines.md")
    assert result.ok is False
    assert "does not exist" in result.detail


def test_a_file_with_empty_colors_section_fails(tmp_path):
    p = tmp_path / "visual-guidelines.md"
    p.write_text("# Visual Guidelines\n\n## Typography\nx\n\n## Colors\n\n## Spacing\nx\n", encoding="utf-8")
    result = visual_tokens_present(p)
    assert result.ok is False
    assert "colours" in result.detail


def test_a_file_missing_a_whole_section_fails(tmp_path):
    p = tmp_path / "visual-guidelines.md"
    p.write_text("# Visual Guidelines\n\n## Typography\nx\n\n## Colors\nx\n", encoding="utf-8")
    result = visual_tokens_present(p)
    assert result.ok is False
    assert "spacing" in result.detail


# --------------------------------------------------------------------------- #
# #3 — flows_present_for_multi_screen_app
# --------------------------------------------------------------------------- #


def test_a_single_screen_app_needs_no_flow():
    assert flows_present_for_multi_screen_app(1, 0).ok is True


def test_a_multi_screen_app_with_no_flow_fails():
    result = flows_present_for_multi_screen_app(3, 0)
    assert result.ok is False
    assert "3 screens but 0 flows" in result.detail


def test_a_multi_screen_app_with_a_flow_passes():
    assert flows_present_for_multi_screen_app(3, 1).ok is True


def test_zero_screens_needs_no_flow():
    assert flows_present_for_multi_screen_app(0, 0).ok is True


# --------------------------------------------------------------------------- #
# #5 — chrome_nav_targets_consistent
# --------------------------------------------------------------------------- #

CHROME = (
    '<aside class="sidebar">'
    '<a href="02-dashboard.html" class="nav-item active">Dashboard</a>'
    '<a href="03-projects.html" class="nav-item">Projects</a>'
    "</aside>"
)


def test_a_screen_matching_the_chrome_nav_set_passes():
    screen = (
        '<aside class="sidebar">'
        '<a href="02-dashboard.html" class="nav-item">Dashboard</a>'
        '<a href="03-projects.html" class="nav-item active">Projects</a>'
        "</aside>"
    )
    assert chrome_nav_targets_consistent(CHROME, screen).ok is True


def test_a_screen_missing_a_nav_target_fails():
    screen = '<aside class="sidebar"><a href="02-dashboard.html" class="nav-item active">Dashboard</a></aside>'
    result = chrome_nav_targets_consistent(CHROME, screen)
    assert result.ok is False
    assert "02-dashboard.html" in result.detail


def test_a_screen_with_an_improvised_extra_nav_item_fails():
    screen = CHROME.replace("</aside>", '<a href="99-secret.html" class="nav-item">Secret</a></aside>')
    result = chrome_nav_targets_consistent(CHROME, screen)
    assert result.ok is False


def test_an_auth_screen_with_no_nav_markup_is_exempt():
    assert chrome_nav_targets_consistent(CHROME, "<html><body>Login</body></html>").ok is True


def test_href_before_class_attribute_order_is_also_matched():
    screen = '<a class="nav-item active" href="02-dashboard.html">D</a><a class="nav-item" href="03-projects.html">P</a>'
    assert chrome_nav_targets_consistent(CHROME, screen).ok is True


# --------------------------------------------------------------------------- #
# #6 — standalone_html_violations
# --------------------------------------------------------------------------- #


def test_a_self_contained_screen_has_no_violations():
    html = '<html><link href="https://fonts.googleapis.com/css?family=Inter"></html>'
    assert standalone_html_violations(html) == []


def test_an_external_script_is_a_violation():
    html = '<html><script src="https://cdn.example.com/lib.js"></script></html>'
    assert standalone_html_violations(html) == ["https://cdn.example.com/lib.js"]


def test_multiple_violations_are_all_reported():
    html = (
        '<img src="https://images.example.com/a.png">'
        '<link href="https://cdn.other.com/x.css">'
    )
    violations = standalone_html_violations(html)
    assert len(violations) == 2


def test_a_single_quoted_reference_is_still_caught():
    """External code review, iterate-2026-09-11-e1-checks-plan-design:
    the original pattern was double-quote-only; agent-generated HTML
    routinely uses single quotes."""
    html = "<script src='https://cdn.example.com/lib.js'></script>"
    assert standalone_html_violations(html) == ["https://cdn.example.com/lib.js"]


def test_a_protocol_relative_reference_is_caught():
    html = '<script src="//cdn.example.com/lib.js"></script>'
    assert standalone_html_violations(html) == ["//cdn.example.com/lib.js"]


def test_a_protocol_relative_allowed_font_host_passes():
    html = '<link href="//fonts.googleapis.com/css?family=Inter">'
    assert standalone_html_violations(html) == []


def test_a_hostile_url_embedding_the_allowed_host_in_its_path_still_violates():
    """A substring match on the URL text would let this through — the host
    must be compared exactly."""
    html = '<script src="https://evil.example/?x=fonts.googleapis.com"></script>'
    violations = standalone_html_violations(html)
    assert len(violations) == 1


# --------------------------------------------------------------------------- #
# #8 — uploads_preserved
# --------------------------------------------------------------------------- #


def test_an_untouched_upload_passes(tmp_path):
    repo = _init_repo(tmp_path)
    uploads = repo / ".shipwright" / "designs" / "uploads"
    uploads.mkdir(parents=True)
    (uploads / "brand.md").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add upload")
    assert uploads_preserved(repo, uploads).ok is True


def test_a_modified_upload_fails(tmp_path):
    repo = _init_repo(tmp_path)
    uploads = repo / ".shipwright" / "designs" / "uploads"
    uploads.mkdir(parents=True)
    (uploads / "brand.md").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add upload")
    (uploads / "brand.md").write_text("changed\n", encoding="utf-8")
    result = uploads_preserved(repo, uploads)
    assert result.ok is False
    assert "brand.md" in result.detail


def test_a_new_untracked_upload_is_not_a_violation(tmp_path):
    repo = _init_repo(tmp_path)
    uploads = repo / ".shipwright" / "designs" / "uploads"
    uploads.mkdir(parents=True)
    (uploads / "new.md").write_text("x\n", encoding="utf-8")
    assert uploads_preserved(repo, uploads).ok is True


def test_non_git_project_passes_trivially(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    assert uploads_preserved(tmp_path, uploads).ok is True


# --------------------------------------------------------------------------- #
# #9 — parse_feedback_round / iteration_touched_flagged_screens
# --------------------------------------------------------------------------- #

FEEDBACK_ROUND = (
    "# Design Feedback — Round 2\n\n"
    "> Exported: 2026-07-24\n\n"
    "## Summary\n\n| Status | Count |\n|--------|-------|\n\n"
    "## 01-auth\n\n"
    "### #1 Login — CHANGES\n\n"
    "**File:** screens/01-login.html  \n"
    "**FRs:** FR-01.01\n\n"
    "Move the CTA button.\n\n"
    "---\n\n"
    "### #2 Dashboard — REJECTED\n\n"
    "**File:** screens/02-dashboard.html  \n"
    "**FRs:** FR-01.02\n\n"
    "Wrong layout entirely.\n\n"
    "---\n\n"
    "### #3 Settings — APPROVED\n\n"
    "**File:** screens/03-settings.html  \n"
    "**FRs:** FR-01.03\n\n"
    "---\n\n"
)


def test_parse_feedback_round_reads_flagged_screens():
    entries = parse_feedback_round(FEEDBACK_ROUND)
    assert ("screens/01-login.html", "CHANGES") in entries
    assert ("screens/02-dashboard.html", "REJECTED") in entries
    assert ("screens/03-settings.html", "APPROVED") in entries


def test_every_flagged_screen_touched_passes():
    result = iteration_touched_flagged_screens(
        ["screens/01-login.html", "screens/02-dashboard.html"],
        ["screens/01-login.html", "screens/02-dashboard.html"],
    )
    assert result.ok is True
    assert result.warnings == ()


def test_an_untouched_flagged_screen_fails():
    result = iteration_touched_flagged_screens(
        ["screens/01-login.html", "screens/02-dashboard.html"],
        ["screens/01-login.html"],
    )
    assert result.ok is False
    assert "screens/02-dashboard.html" in result.detail


def test_a_drive_by_change_beyond_the_flagged_set_only_warns():
    result = iteration_touched_flagged_screens(
        ["screens/01-login.html"],
        ["screens/01-login.html", "screens/09-unrelated.html"],
    )
    assert result.ok is True
    assert any("09-unrelated" in w for w in result.warnings)
