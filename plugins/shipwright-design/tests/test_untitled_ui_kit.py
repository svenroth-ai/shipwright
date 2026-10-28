"""The Untitled UI kit stays consistent: tokens only, every token defined, examples current, snippets covered."""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent
DESIGN = PLUGIN / "skills" / "design"
KIT = DESIGN / "kit" / "untitled-ui"
BUILD = PLUGIN / "scripts" / "tools" / "build_kit_examples.py"
TOKEN_SETS = sorted((KIT / "tokens").glob("*.css"))


def _css() -> str:
    return (KIT / "kit.css").read_text(encoding="utf-8")


def _css_without_comments() -> str:
    return re.sub(r"/\*.*?\*/", "", _css(), flags=re.S)


def _classes(text: str) -> set[str]:
    return set(re.findall(r"\.([a-zA-Z][\w-]*)", text))


@pytest.mark.covers("FR-01.04")
def test_kit_uses_tokens_only() -> None:
    literals = re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", _css())
    assert literals == [], f"kit.css holds literal colours {literals}; use a token"


@pytest.mark.covers("FR-01.04")
@pytest.mark.parametrize("tokens", TOKEN_SETS, ids=lambda p: p.stem)
def test_every_token_the_kit_uses_is_defined_by_each_token_set(tokens: Path) -> None:
    used = set(re.findall(r"var\((--[\w-]+)", _css()))
    defined = set(re.findall(r"(--[\w-]+)\s*:", tokens.read_text(encoding="utf-8")))
    assert used - defined == set()


@pytest.mark.covers("FR-01.04")
def test_there_are_at_least_two_token_sets() -> None:
    assert len(TOKEN_SETS) >= 2


@pytest.mark.covers("FR-01.04")
def test_committed_examples_match_what_the_kit_builds() -> None:
    result = subprocess.run([sys.executable, str(BUILD), "--check"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.covers("FR-01.04")
def test_fragments_use_only_classes_the_kit_defines() -> None:
    defined = _classes(_css_without_comments())
    for fragment in (KIT / "fragments").glob("*.html"):
        used: set[str] = set()
        for value in re.findall(r'class="([^"]+)"', fragment.read_text(encoding="utf-8")):
            used |= set(value.split())
        assert used - defined == set(), f"{fragment.name}: classes not in kit.css"


@pytest.mark.covers("FR-01.04")
def test_kit_covers_every_class_of_the_component_snippets() -> None:
    text = (DESIGN / "references" / "snippets-components.md").read_text(encoding="utf-8")
    snippet_css = "\n".join(re.findall(r"```css\n(.*?)```", text, re.S))
    assert _classes(snippet_css) - _classes(_css()) == set()


def _luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    channels = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# (foreground, background, minimum): 7.0 for secondary text (readable, WCAG AAA), 4.5 for other text (AA), 3.0 for controls and focus
CONTRAST_PAIRS = [
    ("text", "bg", 4.5), ("text", "surface", 4.5), ("muted", "bg", 7.0), ("muted", "surface", 7.0),
    ("muted", "table-header", 7.0), ("on-primary", "primary", 4.5), ("on-primary", "primary-hover", 4.5),
    ("primary", "surface", 4.5), ("primary", "bg", 4.5), ("on-primary", "error", 4.5),
    ("success", "success-bg", 4.5), ("warning", "warning-bg", 4.5), ("error", "error-bg", 4.5), ("info", "info-bg", 4.5),
    ("success", "surface", 4.5), ("warning", "surface", 4.5), ("error", "surface", 4.5),
    ("muted", "hover", 7.0), ("text", "hover", 4.5), ("muted", "primary-soft", 7.0), ("text", "primary-soft", 4.5), ("muted", "border", 7.0), ("text", "border", 4.5), ("border-strong", "surface", 3.0), ("border-strong", "bg", 3.0), ("focus", "surface", 3.0), ("focus", "bg", 3.0), ("info", "surface", 4.5), ("primary", "primary-soft", 3.0), ("text", "table-header", 4.5),
]


@pytest.mark.covers("FR-01.04")
@pytest.mark.parametrize("tokens", TOKEN_SETS, ids=lambda p: p.stem)
def test_token_sets_meet_wcag_aa_contrast(tokens: Path) -> None:
    colours = dict(re.findall(r"--color-([\w-]+):\s*(#[0-9a-fA-F]{6})\b", tokens.read_text(encoding="utf-8")))
    failures = [
        f"{fg} {colours[fg]} on {bg} {colours[bg]}: {_contrast(colours[fg], colours[bg]):.2f} < {need}"
        for fg, bg, need in CONTRAST_PAIRS
        if _contrast(colours[fg], colours[bg]) < need
    ]
    assert failures == []


@pytest.mark.covers("FR-01.04")
@pytest.mark.parametrize("tokens", TOKEN_SETS, ids=lambda p: p.stem)
def test_colour_tokens_are_solid_hex_so_the_look_stays_under_control(tokens: Path) -> None:
    """Hover, selected and ring colours are chosen colours, never a transparent tint of another one."""
    text = tokens.read_text(encoding="utf-8")
    not_solid = [
        name for name, value in re.findall(r"--color-([\w-]+):\s*([^;]+);", text)
        if name != "overlay" and not re.fullmatch(r"#[0-9a-fA-F]{6}", value.strip())
    ]
    assert not_solid == []


@pytest.mark.covers("FR-01.04")
def test_kit_has_no_literal_font_sizes() -> None:
    assert re.findall(r"font-size:\s*\d", _css()) == []


@pytest.mark.covers("FR-01.04")
@pytest.mark.parametrize("tokens", TOKEN_SETS, ids=lambda p: p.stem)
def test_type_sizes_are_readable(tokens: Path) -> None:
    sizes = {k: int(v) for k, v in re.findall(r"--font-size-(base|sm):\s*(\d+)px", tokens.read_text(encoding="utf-8"))}
    assert sizes["base"] >= 16 and sizes["sm"] >= 14


@pytest.mark.covers("FR-01.04")
def test_token_contract_names_every_token_the_kit_uses() -> None:
    contract = (KIT / "tokens-contract.md").read_text(encoding="utf-8")
    used = set(re.findall(r"var\((--[\w-]+)", _css()))
    named = set(re.findall(r"`(--[\w-]+)`", contract))
    missing = used - named
    # spacing is listed as a range, status colours as a family
    missing -= {t for t in missing if re.fullmatch(r"--space-\d", t) or re.fullmatch(r"--color-(info|success|warning|error)-bg", t)}
    assert missing == set(), f"tokens-contract.md does not mention {sorted(missing)}"


@pytest.mark.covers("FR-01.04")
@pytest.mark.parametrize("tokens", TOKEN_SETS, ids=lambda p: p.stem)
def test_every_token_named_in_the_contract_is_defined_by_each_token_set(tokens: Path) -> None:
    contract = (KIT / "tokens-contract.md").read_text(encoding="utf-8")
    named = set(re.findall(r"`(--[\w-]+)`", contract))
    defined = set(re.findall(r"(--[\w-]+)\s*:", tokens.read_text(encoding="utf-8")))
    assert named - defined == set()


# Page-level layouts (shown by the board example and the snippets), fixed overlays that would cover the gallery,
# and state modifiers: the only kit classes the gallery may leave out.
NOT_IN_GALLERY = {
    "app-layout", "main-area", "content", "sidebar", "sidebar-footer", "sidebar-logo", "sidebar-nav", "sidebar-toggle",
    "nav-divider", "nav-icon", "nav-item", "nav-section-label", "topbar", "topbar-actions", "topbar-search",
    "user-info", "user-name", "user-role", "search-input",
    "auth-card", "auth-footer", "auth-form", "auth-layout", "auth-logo", "auth-subtitle", "auth-title",
    "modal-overlay", "drawer-overlay", "open", "unread", "required", "scroll", "popover-right",
}


@pytest.mark.covers("FR-01.04")
def test_gallery_shows_every_component_class_of_the_kit() -> None:
    css = re.sub(r"/\*.*?\*/", "", _css(), flags=re.S)
    used: set[str] = set()
    for value in re.findall(r'class="([^"]+)"', (KIT / "fragments" / "gallery.html").read_text(encoding="utf-8")):
        used |= set(value.split())
    board: set[str] = set()
    for value in re.findall(r'class="([^"]+)"', (KIT / "fragments" / "board.html").read_text(encoding="utf-8")):
        board |= set(value.split())
    missing = _classes(css) - used - board - NOT_IN_GALLERY
    assert missing == set(), f"classes in kit.css that no example shows: {sorted(missing)}"


@pytest.mark.covers("FR-01.04")
@pytest.mark.parametrize("tokens", TOKEN_SETS, ids=lambda p: p.stem)
def test_heading_sizes_do_not_shrink_as_the_level_rises(tokens: Path) -> None:
    sizes = {k: int(v) for k, v in re.findall(r"--font-size-(h1|h2|h3):\s*(\d+)px", tokens.read_text(encoding="utf-8"))}
    assert sizes["h3"] <= sizes["h2"] <= sizes["h1"]


def _builder():
    spec = importlib.util.spec_from_file_location("build_kit_examples", BUILD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _kit_copy(tmp_path: Path) -> Path:
    kit = tmp_path / "kit"
    # a plugin hook may drop a runtime .shipwright/ lock dir into a kit folder it was started in; it is not kit content
    shutil.copytree(KIT, kit, ignore=shutil.ignore_patterns(".shipwright"))
    return kit


@pytest.mark.covers("FR-01.04")
def test_builder_check_passes_on_the_committed_tree_and_fails_on_a_changed_example(tmp_path: Path) -> None:
    builder = _builder()
    assert builder.main(["--check"]) == 0
    kit = _kit_copy(tmp_path)
    assert builder.main(["--check"], kit=kit) == 0
    example = next((kit / "examples").glob("board-*.html"))
    example.write_text("changed", encoding="utf-8")
    assert builder.main(["--check"], kit=kit) == 1


@pytest.mark.covers("FR-01.04")
def test_builder_write_mode_restores_examples_and_check_reports_orphans(tmp_path: Path) -> None:
    builder = _builder()
    kit = _kit_copy(tmp_path)
    shutil.rmtree(kit / "examples")
    assert builder.main([], kit=kit) == 0
    assert builder.main(["--check"], kit=kit) == 0
    (kit / "examples" / "gone-warm.html").write_text("orphan", encoding="utf-8")
    assert builder.main(["--check"], kit=kit) == 1


@pytest.mark.covers("FR-01.04")
def test_builder_refuses_a_token_set_without_a_font_entry(tmp_path: Path) -> None:
    builder = _builder()
    kit = _kit_copy(tmp_path)
    (kit / "tokens" / "new.css").write_text(":root {}", encoding="utf-8")
    with pytest.raises(KeyError, match="new"):
        builder.targets(kit)
