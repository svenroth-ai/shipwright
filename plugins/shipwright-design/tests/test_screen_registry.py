"""Tests for screen registry."""

from pathlib import Path

from screen_registry import (
    generate_manifest,
    parse_screen_linked_frs,
    scan_designs_dir,
    write_manifest,
)

STEP_4_PATH = (
    Path(__file__).resolve().parent.parent
    / "skills" / "design" / "references" / "step-4-generate-screens.md"
)


def test_step_4_instructs_the_requirements_comment_producer():
    """Stage-1 spec review, iterate-2026-09-11-e1-checks-plan-design:
    `parse_screen_linked_frs` reads the `<!-- Requirements: ... -->` comment,
    but nothing ever instructed a screen's author to write it — a
    consumer with no producer. Pin the instruction, not just its existence,
    so a rewrite of the Save step can't silently drop it again."""
    body = STEP_4_PATH.read_text(encoding="utf-8")
    assert "<!-- Requirements:" in body, (
        "Step 4's Save instruction must tell the agent to write the "
        "Requirements comment `parse_screen_linked_frs` reads — without a "
        "producer, every screen's linked_frs stays empty"
    )


def test_scan_empty_dir(tmp_path):
    designs = tmp_path / ".shipwright" / "designs"
    designs.mkdir(parents=True)
    result = scan_designs_dir(designs)
    assert result["screens"] == []
    assert result["flows"] == []
    assert result["uploads"] == []
    assert result["has_visual_guidelines"] is False


def test_scan_with_screens(tmp_project_with_designs):
    designs = tmp_project_with_designs / ".shipwright" / "designs"
    result = scan_designs_dir(designs)
    assert len(result["screens"]) == 2
    assert result["screens"][0]["name"] == "login"
    assert result["screens"][0]["number"] == 1
    assert result["screens"][1]["name"] == "dashboard"


def test_scan_with_flows(tmp_project_with_designs):
    designs = tmp_project_with_designs / ".shipwright" / "designs"
    result = scan_designs_dir(designs)
    assert len(result["flows"]) == 1
    assert result["flows"][0]["name"] == "auth-flow"


def test_scan_with_uploads(tmp_project_with_designs):
    uploads = tmp_project_with_designs / ".shipwright" / "designs" / "uploads"
    (uploads / "mockup.png").write_text("fake png")
    (uploads / "header.html").write_text("<html>header</html>")

    result = scan_designs_dir(tmp_project_with_designs / ".shipwright" / "designs")
    assert len(result["uploads"]) == 2


def test_generate_manifest(tmp_project_with_designs):
    designs = tmp_project_with_designs / ".shipwright" / "designs"
    content = generate_manifest(designs, "My App", "supabase-nextjs")
    assert "# Design Manifest" in content
    assert "login" in content
    assert "dashboard" in content
    assert "auth-flow" in content
    assert "supabase-nextjs" in content


def test_write_manifest(tmp_project_with_designs):
    designs = tmp_project_with_designs / ".shipwright" / "designs"
    path = write_manifest(designs, "My App", "supabase-nextjs")
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "Design Manifest" in content


def test_generate_manifest_no_prior_file_omits_non_ui_frs_section(tmp_project_with_designs):
    designs = tmp_project_with_designs / ".shipwright" / "designs"
    content = generate_manifest(designs, "My App", "supabase-nextjs")
    assert "## Non-UI FRs" not in content


def test_write_manifest_preserves_hand_added_non_ui_frs_section(tmp_project_with_designs):
    designs = tmp_project_with_designs / ".shipwright" / "designs"
    path = write_manifest(designs, "My App", "supabase-nextjs")

    non_ui_section = (
        "## Non-UI FRs\n\n"
        "- FR-03.01 — ADR-004 (background job, no screen)\n"
    )
    original = path.read_text(encoding="utf-8")
    # Simulate a hand-added section, inserted right after ## Screens per the
    # Step 6 template.
    screens_end = original.index("## User Flows")
    edited = original[:screens_end] + non_ui_section + "\n" + original[screens_end:]
    path.write_text(edited, encoding="utf-8")

    # Regenerating (e.g. after adding another screen) must round-trip the
    # hand-added section rather than dropping it — trg-44f49504.
    write_manifest(designs, "My App", "supabase-nextjs")
    regenerated = path.read_text(encoding="utf-8")

    assert "## Non-UI FRs" in regenerated
    assert "FR-03.01 — ADR-004 (background job, no screen)" in regenerated

    # And it survives a second regeneration too (not a one-shot carry-over).
    write_manifest(designs, "My App", "supabase-nextjs")
    assert "FR-03.01 — ADR-004 (background job, no screen)" in path.read_text(encoding="utf-8")


def test_write_manifest_without_non_ui_frs_section_stays_absent(tmp_project_with_designs):
    designs = tmp_project_with_designs / ".shipwright" / "designs"
    path = write_manifest(designs, "My App", "supabase-nextjs")
    assert "## Non-UI FRs" not in path.read_text(encoding="utf-8")

    write_manifest(designs, "My App", "supabase-nextjs")
    assert "## Non-UI FRs" not in path.read_text(encoding="utf-8")


def test_generate_manifest_preserves_non_ui_frs_section_at_end_of_file(tmp_project_with_designs):
    """The section boundary is `\\n## ` OR end-of-string — verify the
    end-of-file case (no following section) round-trips too."""
    designs = tmp_project_with_designs / ".shipwright" / "designs"
    manifest_path = designs / "design-manifest.md"
    manifest_path.write_text(
        "# Design Manifest\n\n## Screens\n\nNo screens generated yet.\n\n"
        "## Non-UI FRs\n\n- FR-09.01 — ADR-010 (webhook, no screen)\n",
        encoding="utf-8",
    )

    content = generate_manifest(designs, "My App", "supabase-nextjs")
    assert "FR-09.01 — ADR-010 (webhook, no screen)" in content


# ---------------------------------------------------------------------------
# parse_screen_linked_frs / linked_frs wiring — FR-01.04 #1 / #4
# ---------------------------------------------------------------------------


def test_a_screen_declaring_requirements_is_parsed(tmp_path):
    f = tmp_path / "01-login.html"
    f.write_text(
        "<!-- Requirements: FR-01.02, FR-01.05 -->\n<html><body>Login</body></html>",
        encoding="utf-8",
    )
    assert parse_screen_linked_frs(f) == ["FR-01.02", "FR-01.05"]


def test_a_screen_with_no_comment_links_nothing(tmp_path):
    f = tmp_path / "01-login.html"
    f.write_text("<html><body>Login</body></html>", encoding="utf-8")
    assert parse_screen_linked_frs(f) == []


def test_a_malformed_token_in_the_comment_is_dropped_not_mined(tmp_path):
    f = tmp_path / "01-login.html"
    f.write_text("<!-- Requirements: FR-01.02x, FR-01.05 -->\n<html></html>", encoding="utf-8")
    assert parse_screen_linked_frs(f) == ["FR-01.05"]


def test_a_missing_file_yields_no_links_rather_than_raising(tmp_path):
    assert parse_screen_linked_frs(tmp_path / "nope.html") == []


def test_scan_populates_linked_frs_from_the_screen_comment(tmp_project_with_designs):
    designs = tmp_project_with_designs / ".shipwright" / "designs"
    (designs / "screens" / "01-login.html").write_text(
        "<!-- Requirements: FR-01.02 -->\n<html><body>Login</body></html>", encoding="utf-8"
    )
    result = scan_designs_dir(designs)
    login = next(s for s in result["screens"] if s["name"] == "login")
    assert login["linked_frs"] == ["FR-01.02"]


def test_generate_manifest_renders_linked_frs_in_the_table(tmp_project_with_designs):
    designs = tmp_project_with_designs / ".shipwright" / "designs"
    (designs / "screens" / "01-login.html").write_text(
        "<!-- Requirements: FR-01.02, FR-01.05 -->\n<html></html>", encoding="utf-8"
    )
    content = generate_manifest(designs, "My App", "supabase-nextjs")
    login_row = next(line for line in content.splitlines() if "| login |" in line)
    assert "FR-01.02, FR-01.05" in login_row


def test_generate_manifest_renders_none_for_an_unlinked_screen(tmp_project_with_designs):
    designs = tmp_project_with_designs / ".shipwright" / "designs"
    content = generate_manifest(designs, "My App", "supabase-nextjs")
    login_row = next(line for line in content.splitlines() if "| login |" in line)
    assert "| none |" in login_row


def test_scan_ignores_non_html(tmp_path):
    designs = tmp_path / ".shipwright" / "designs"
    (designs / "screens").mkdir(parents=True)
    (designs / "screens" / "notes.txt").write_text("not a screen")
    (designs / "screens" / "01-login.html").write_text("<html></html>")

    result = scan_designs_dir(designs)
    assert len(result["screens"]) == 1
