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
CHECK = PLUGIN / "scripts" / "tools" / "check_brand_tokens.py"
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


@pytest.mark.covers("FR-01.04")
@pytest.mark.parametrize("tokens", TOKEN_SETS, ids=lambda p: p.stem)
def test_token_sets_meet_wcag_aa_contrast(tokens: Path) -> None:
    css = tokens.read_text(encoding="utf-8")
    assert _checker().check_css(css) == []


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


def _checker():
    spec = importlib.util.spec_from_file_location("check_brand_tokens", CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


# A brand taken from a claude.ai Design System: its raw colours are laid over a shipped set, then checked and corrected.
RAW_BRAND = ":root { --color-primary: #128a76; --color-muted: #6c6a64; --color-border-strong: #cdc7ba; }"


@pytest.mark.covers("FR-01.04")
def test_brand_checker_flags_weak_brand_colours_and_the_suggestions_bring_it_to_green() -> None:
    mod = _checker()
    css = (KIT / "tokens" / "warm.css").read_text(encoding="utf-8") + RAW_BRAND
    failures = mod.check_css(css)
    assert any(f.startswith("muted ") for f in failures) and any(f.startswith("border-strong ") for f in failures)
    best: dict[str, str] = {}
    for token, value in re.findall(r"try --color-([\w-]+): (#[0-9a-f]{6})", " ".join(failures)):
        if token not in best or mod.luminance(value) < mod.luminance(best[token]):
            best[token] = value  # the doc's rule on a light theme: the most contrasting (darkest) suggestion
    assert mod.check({**mod.parse_colours(css), **best}) == []


@pytest.mark.covers("FR-01.04")
def test_brand_checker_cli_exit_codes(tmp_path: Path) -> None:
    brand = tmp_path / "brand.css"
    brand.write_text(RAW_BRAND, encoding="utf-8")
    run = lambda *a: subprocess.run([sys.executable, str(CHECK), *a], capture_output=True, text=True, check=False)  # noqa: E731
    assert run("--base", "warm").returncode == 0
    weak = run("--base", "warm", "--overrides", str(brand))
    assert weak.returncode == 1 and "try --color-" in weak.stdout
    assert run("--base", "warm", "--overrides", str(tmp_path / "absent.css")).returncode == 2


@pytest.mark.covers("FR-01.04")
def test_brand_checker_reports_a_token_the_brand_set_leaves_out() -> None:
    mod = _checker()
    colours = mod.parse_colours((KIT / "tokens" / "clean.css").read_text(encoding="utf-8"))
    del colours["focus"]
    assert mod.check(colours) == ["missing --color-focus"]


@pytest.mark.covers("FR-01.04")
def test_brand_from_design_system_is_offered_where_the_look_is_chosen() -> None:
    """The claude.ai Design System route is reachable from Step 2.5, the Step 3 question and the kit doc, and its checker exists."""
    refs = DESIGN / "references"
    for doc in (DESIGN / "SKILL.md", refs / "step-2-5-brand-extraction.md", refs / "step-3-design-interview.md", refs / "untitled-ui-components.md"):
        assert "brand-from-design-system.md" in doc.read_text(encoding="utf-8"), doc.name
    text = (refs / "brand-from-design-system.md").read_text(encoding="utf-8")
    assert "check_brand_tokens.py" in text and CHECK.is_file()


@pytest.mark.covers("FR-01.04")
def test_brand_checker_main_in_process_covers_base_overrides_and_full_set(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI entry runs in-process too, so diff coverage sees it (a subprocess run is invisible to it)."""
    mod = _checker()
    brand = tmp_path / "brand.css"
    brand.write_text(RAW_BRAND, encoding="utf-8")
    assert mod.main(["--base", "clean"]) == 0
    assert "OK" in capsys.readouterr().out
    assert mod.main(["--tokens", str(KIT / "tokens" / "bold.css")]) == 0
    assert mod.main(["--base", "warm", "--overrides", str(brand)]) == 1
    assert "try --color-" in capsys.readouterr().out
    assert mod.main(["--base", "warm", "--overrides", str(tmp_path / "absent.css")]) == 2
    with pytest.raises(SystemExit):
        mod.main([])


@pytest.mark.covers("FR-01.04")
def test_brand_checker_flags_font_sizes_below_the_minimum() -> None:
    mod = _checker()
    css = (KIT / "tokens" / "clean.css").read_text(encoding="utf-8") + ":root { --font-size-base: 14px; }"
    failures = mod.check(mod.parse_colours(css), mod.parse_sizes(css))
    assert len(failures) == 1 and "font sizes below the minimum" in failures[0]


@pytest.mark.covers("FR-01.04")
def test_brand_checker_reports_values_it_cannot_read_instead_of_passing_on_the_base() -> None:
    """An override the checker skipped would leave the base value in force and report green for a colour nobody checked."""
    mod = _checker()
    base = (KIT / "tokens" / "warm.css").read_text(encoding="utf-8")
    failures = mod.check_css(base + ":root { --color-muted: rgb(150, 150, 150); --font-size-base: 1rem; }")
    assert any("--color-muted" in f and "not a solid hex" in f for f in failures)
    assert any("--font-size-base" in f and "not a px size" in f for f in failures)
    shorthand = mod.check_css(base + ":root { --color-muted: #999; }")
    assert any(f.startswith("muted #999999") for f in shorthand), "a 3-digit hex is read as the colour it means"


@pytest.mark.covers("FR-01.04")
def test_brand_checker_requires_primary_hover_darker_and_font_sizes_present() -> None:
    mod = _checker()
    colours = mod.parse_colours((KIT / "tokens" / "clean.css").read_text(encoding="utf-8"))
    for hover in (colours["primary"], "#93c5fd"):  # the same colour, and a lighter one: neither is a darker hover
        assert any(f.startswith("primary-hover") and "darker" in f for f in mod.check({**colours, "primary-hover": hover}))
    assert mod.check(mod.parse_colours((KIT / "tokens" / "clean.css").read_text(encoding="utf-8")), {}) == ["missing --font-size-base", "missing --font-size-sm"]
