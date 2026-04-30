"""Visual-docs schema alignment (Fix 1).

After /shipwright-adopt, /shipwright-design must be able to consume the
generated design-system artifact without manual fix-up. That means:

- `.shipwright/designs/visual-guidelines.md` exists at the canonical
  path /shipwright-design reads, in the canonical schema (typography,
  colors, spacing, radius, shadows, component patterns).
- `.shipwright/agent_docs/design_tokens.md` is preserved as the raw
  audit trail (parsed token values from tailwind / CSS vars).
- `.shipwright/agent_docs/component_inventory.md` carries the component
  table + screenshot links — that content is architecture-shaped, not
  design-system-shaped, and should not collide with the design-system
  artifact's name. Old `guideline.md` is replaced.
"""

from __future__ import annotations

from pathlib import Path

from lib.visual_docs_generator import generate_visual_docs


def _setup_fixture(tmp_path: Path) -> None:
    (tmp_path / "src" / "components").mkdir(parents=True)
    (tmp_path / "src" / "components" / "Button.tsx").write_text(
        "export interface ButtonProps { label: string; onClick: () => void }\n"
        "export function Button(p: ButtonProps) { return null; }\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "components" / "Card.tsx").write_text(
        "export const Card = () => null;\n",
        encoding="utf-8",
    )
    (tmp_path / "tailwind.config.ts").write_text(
        "export default { theme: { extend: { "
        "colors: { primary: '#0066cc', accent: '#ff5500' }, "
        "spacing: { '18': '4.5rem' }, "
        "fontSize: { 'display': '4rem' } } } };\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "globals.css").write_text(
        ":root { --background: 0 0% 100%; --foreground: 0 0% 0%; "
        "--radius: 0.5rem; }\n",
        encoding="utf-8",
    )
    crawl_screens = tmp_path / ".shipwright" / "adopt" / "screenshots"
    crawl_screens.mkdir(parents=True)
    (crawl_screens / "_root.png").write_bytes(b"fake-png-bytes")


def test_writes_visual_guidelines_at_canonical_path(tmp_path: Path) -> None:
    """The design-system artifact lands at the path /shipwright-design reads."""
    _setup_fixture(tmp_path)
    generate_visual_docs(tmp_path)

    canonical = tmp_path / ".shipwright" / "designs" / "visual-guidelines.md"
    assert canonical.exists(), (
        "visual-guidelines.md must be written at .shipwright/designs/ — "
        "/shipwright-design reads from this path."
    )


def test_visual_guidelines_uses_canonical_schema(tmp_path: Path) -> None:
    """Sections match plugins/shipwright-design/.../visual-guidelines-template.md."""
    _setup_fixture(tmp_path)
    generate_visual_docs(tmp_path)

    body = (tmp_path / ".shipwright" / "designs" / "visual-guidelines.md").read_text(
        encoding="utf-8"
    )
    assert "# Visual Guidelines" in body
    assert "## Typography" in body
    assert "## Colors" in body
    assert "## Spacing" in body or "## Spacing & Layout" in body
    assert "## Border Radius" in body
    assert "## Shadows" in body
    assert "## Component Patterns" in body


def test_visual_guidelines_pulls_extracted_tokens_into_schema(tmp_path: Path) -> None:
    """Schema slots are filled from extracted tokens, not left as `{hex}`."""
    _setup_fixture(tmp_path)
    generate_visual_docs(tmp_path)

    body = (tmp_path / ".shipwright" / "designs" / "visual-guidelines.md").read_text(
        encoding="utf-8"
    )
    # Tailwind colors should surface as values, not literal placeholders.
    assert "#0066cc" in body or "primary" in body
    # No raw {hex} / {value} template placeholders should leak through.
    assert "{hex}" not in body
    assert "{value}" not in body


def test_design_tokens_md_preserved_as_audit_trail(tmp_path: Path) -> None:
    """design_tokens.md still exists with raw extracted values."""
    _setup_fixture(tmp_path)
    generate_visual_docs(tmp_path)

    tokens = tmp_path / ".shipwright" / "agent_docs" / "design_tokens.md"
    assert tokens.exists()
    body = tokens.read_text(encoding="utf-8")
    assert "primary" in body
    assert "#0066cc" in body
    # CSS vars from globals.css
    assert "background" in body


def test_old_guideline_md_replaced_by_component_inventory(tmp_path: Path) -> None:
    """`.shipwright/agent_docs/guideline.md` is gone; component table now lives
    in `component_inventory.md` (architecture-shaped doc)."""
    _setup_fixture(tmp_path)
    generate_visual_docs(tmp_path)

    old = tmp_path / ".shipwright" / "agent_docs" / "guideline.md"
    new = tmp_path / ".shipwright" / "agent_docs" / "component_inventory.md"
    assert not old.exists(), (
        "guideline.md is the legacy name — its content moved to "
        "component_inventory.md and the design-system content moved to "
        ".shipwright/designs/visual-guidelines.md."
    )
    assert new.exists()
    body = new.read_text(encoding="utf-8")
    assert "Button" in body
    assert "Card" in body


def test_result_dict_carries_canonical_paths(tmp_path: Path) -> None:
    """Returned dict surfaces the canonical paths so the caller can append
    them to results['written'] for the gitignore-awareness check."""
    _setup_fixture(tmp_path)
    result = generate_visual_docs(tmp_path)

    assert result["wrote_docs"] is True
    assert "visual_guidelines" in result
    assert "component_inventory" in result
    assert result["visual_guidelines"].name == "visual-guidelines.md"
    assert (
        result["visual_guidelines"].parent.name == "designs"
    )
    assert result["component_inventory"].name == "component_inventory.md"


def test_skipped_when_no_visual_signal(tmp_path: Path) -> None:
    """Backend-only project: no canonical artifact written, no error."""
    result = generate_visual_docs(tmp_path)

    assert result["wrote_docs"] is False
    canonical = tmp_path / ".shipwright" / "designs" / "visual-guidelines.md"
    assert not canonical.exists()
