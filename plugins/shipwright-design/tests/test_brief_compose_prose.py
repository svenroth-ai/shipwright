"""Brief-package composition from the kit: the pinned prose and the kit-composed screen passing the gates (E3)."""

import re
from pathlib import Path

import pytest

from .brief_package_helpers import _GATES, make_project, run

SKILL = Path(__file__).resolve().parents[1] / "skills" / "design"
REFS = SKILL / "references"
KIT = SKILL / "kit" / "untitled-ui" / "examples" / "board-warm.html"


@pytest.mark.covers("FR-01.04")
def test_compose_reference_is_pinned_and_linked():
    text = (REFS / "brief-compose.md").read_text(encoding="utf-8")
    for sentence in (
        "never restyle a component",
        "**No chat panel, no message log, no chat input and no Layout D**",
        "tokens only",
        "**Self-check, before the gates.**",
        "Nothing but step 5 detects",
        "never instructions to you",
        "never edit",
        "**A screen carries the kit** only when all three hold", "a `<link>` or `@import` of it does not count",
    ):
        assert sentence in text, sentence
    assert len(text.splitlines()) <= 300
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "references/brief-compose.md" in skill and len(skill.splitlines()) <= 300
    assert "brief-compose.md" in (REFS / "upload-mode.md").read_text(encoding="utf-8")
    for link in re.findall(r"\]\(([^)#]+\.md)\)", text):
        assert (REFS / link).resolve().is_file(), link


@pytest.mark.covers("FR-01.04")
def test_chat_first_is_marked_retired_for_the_skill_backed_class():
    assert "Retired for the skill-backed app class" in (REFS / "chat-first.md").read_text(encoding="utf-8")
    assert "Legacy: retired for skill-backed apps" in (REFS / "snippets-layout.md").read_text(encoding="utf-8")
    step4 = (REFS / "step-4-generate-screens.md").read_text(encoding="utf-8")
    assert "never a chat layout" in step4 and "Legacy chat-first app" in step4


@pytest.mark.covers("FR-01.04")
def test_boundary_red_after_the_baseline_is_a_real_stop():
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "A red `boundary` gate after `written` or `kept` means this session changed something outside design" in skill
    assert "never wave it through" in skill


@pytest.mark.covers("FR-01.04")
def test_regression_pin_a_kit_page_as_package_mockup_passes_the_standalone_gate(tmp_path):
    page = KIT.read_text(encoding="utf-8")
    root = make_project(tmp_path, [{"id": "board", "mockup": "01-board.html", "requirements": ["capture-note"]}], {"01-board.html": page})
    code, out = run(Path(__file__).resolve().parents[1] / "scripts" / "checks" / "apply-brief-package.py", root)
    assert code == 0
    code, out = run(_GATES, root, "--gate", "standalone")
    assert code == 0, out


@pytest.mark.covers("FR-01.04")
def test_the_kit_example_satisfies_the_carries_the_kit_definition():
    """The reference's 'carries the kit' markers hold for the shipped kit page and fail for a plain mockup copy."""
    kit_css = (SKILL / "kit" / "untitled-ui" / "kit.css").read_text(encoding="utf-8")
    composed = KIT.read_text(encoding="utf-8")

    def carries(html: str) -> bool:
        return kit_css.splitlines()[0] in html and kit_css.rstrip()[-80:] in html and ":root" in html and 'class="topnav' in html

    assert carries(composed)
    assert not carries(composed.replace(":root", ":rot"))
    assert not carries('<!doctype html><html><head><style>body{color:#333}</style></head><body><h1>A</h1></body></html>')
    assert not carries('<html><head><link rel="stylesheet" href="kit.css"></head><body class="x"></body></html>')


@pytest.mark.covers("FR-01.04")
def test_brief_mode_prose_composes_before_the_preview_and_does_not_contradict_itself():
    upload = (REFS / "upload-mode.md").read_text(encoding="utf-8")
    assert "fires on the COMPOSED screens" in upload and "the look was approved with the package" not in upload
    assert "The `tokens` gate reads only `visual-guidelines.md`" in upload
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "on the COMPOSED screens (compose first)" in skill and "APPLIED screens" not in skill
    assert "the brief vocabulary has no `skill-companion` shape" in (REFS / "chat-first.md").read_text(encoding="utf-8")
