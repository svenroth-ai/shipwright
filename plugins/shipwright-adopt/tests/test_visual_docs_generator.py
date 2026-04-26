"""End-to-end test for visual_docs_generator (Tier 5).

Given a fixture repo with components + tailwind config + crawl screenshots,
generate agent_docs/{design_tokens.md, guideline.md} and persist
screenshots into agent_docs/visual/screenshots/.
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
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "globals.css").write_text(
        ":root { --background: 0 0% 100%; --foreground: 0 0% 0%; }\n",
        encoding="utf-8",
    )
    crawl_screens = tmp_path / ".shipwright" / "adopt" / "screenshots"
    crawl_screens.mkdir(parents=True)
    (crawl_screens / "_root.png").write_bytes(b"fake-png-bytes")
    (crawl_screens / "_dashboard.png").write_bytes(b"fake-png-bytes")


def test_generate_writes_design_tokens_md(tmp_path: Path) -> None:
    _setup_fixture(tmp_path)
    result = generate_visual_docs(tmp_path)
    tokens_path = tmp_path / "agent_docs" / "design_tokens.md"
    assert tokens_path.exists()
    body = tokens_path.read_text(encoding="utf-8")
    assert "primary" in body and "#0066cc" in body
    assert "accent" in body and "#ff5500" in body
    assert "background" in body  # CSS var
    assert "display" in body and "4rem" in body
    assert tokens_path == result["design_tokens"]


def test_generate_writes_guideline_md_with_components_section(tmp_path: Path) -> None:
    _setup_fixture(tmp_path)
    result = generate_visual_docs(tmp_path)
    guideline_path = tmp_path / "agent_docs" / "guideline.md"
    assert guideline_path.exists()
    body = guideline_path.read_text(encoding="utf-8")
    assert "Button" in body
    assert "Card" in body
    # Should reference colors + components in cohesive sections
    assert "Colors" in body or "colors" in body
    assert "Components" in body or "components" in body


def test_generate_persists_crawl_screenshots(tmp_path: Path) -> None:
    _setup_fixture(tmp_path)
    result = generate_visual_docs(tmp_path)
    persist_dir = tmp_path / "agent_docs" / "visual" / "screenshots"
    assert persist_dir.is_dir()
    persisted = sorted(p.name for p in persist_dir.iterdir())
    assert "_root.png" in persisted
    assert "_dashboard.png" in persisted
    assert result["screenshots_persisted"] == 2


def test_generate_skips_when_no_frontend(tmp_path: Path) -> None:
    """Backend-only project: no components, no tailwind, no CSS vars.
    The generator should no-op (or generate trivial empty docs) and report so."""
    result = generate_visual_docs(tmp_path)
    # If the result reports zero detected, that's success — no docs needed.
    assert result["component_count"] == 0
    assert result["screenshots_persisted"] == 0
    # The function may either skip writing files or write minimal placeholders.
    # Document either: the `wrote_docs` field tells the caller.
    assert "wrote_docs" in result


def test_generate_with_explicit_frontend_root(tmp_path: Path) -> None:
    """Multi-service: the helper accepts a `frontend_root` to scan instead of
    the project root. Components in client/ should be found, components at
    project root should not duplicate."""
    (tmp_path / "client" / "src" / "components").mkdir(parents=True)
    (tmp_path / "client" / "src" / "components" / "Header.tsx").write_text(
        "export const Header = () => null;\n", encoding="utf-8",
    )
    (tmp_path / "client" / "tailwind.config.ts").write_text(
        "export default { theme: { extend: { colors: { brand: '#abc' } } } };\n",
        encoding="utf-8",
    )
    result = generate_visual_docs(tmp_path, frontend_root=tmp_path / "client")
    body = (tmp_path / "agent_docs" / "guideline.md").read_text(encoding="utf-8")
    assert "Header" in body
    tokens = (tmp_path / "agent_docs" / "design_tokens.md").read_text(encoding="utf-8")
    assert "brand" in tokens
