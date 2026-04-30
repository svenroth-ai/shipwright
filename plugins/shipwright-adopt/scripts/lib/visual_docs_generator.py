"""Generate adopt's visual frontend documentation (Tier 5).

Three outputs (paths chosen so downstream skills consume them without fix-up):

- `.shipwright/designs/visual-guidelines.md` — the **design-system**
  artifact, in the schema /shipwright-design reads
  (typography / colors / spacing / radius / shadows / component patterns,
  see `plugins/shipwright-design/skills/design/references/visual-guidelines-template.md`).
- `.shipwright/agent_docs/design_tokens.md` — raw audit trail of every
  token value extracted from `tailwind.config.*` and `:root` CSS vars.
- `.shipwright/agent_docs/component_inventory.md` — component table
  (name / path / props / usages) plus screenshot links. Architecture-
  shaped, intentionally separate from the design-system artifact.
- `.shipwright/agent_docs/visual/screenshots/*` — copies of the crawl
  screenshots from `.shipwright/adopt/screenshots/` (gitignored adopt
  workdir) so adopt's docs reference a stable, committed location.

Backend-only projects yield `wrote_docs: false` and write nothing.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

AGENT_DOCS_DIR = ".shipwright/agent_docs"
DESIGNS_DIR = ".shipwright/designs"
LEGACY_AGENT_DOCS_DIRNAME = "agent_docs"

# Importable both as `lib.visual_docs_generator` (test path: lib/__init__.py)
# AND as `visual_docs_generator` (production path via `_load_lib()` which
# adds scripts/lib to sys.path and uses absolute names).
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from .component_inventory import build_component_inventory  # type: ignore
    from .design_tokens import extract_design_tokens  # type: ignore
except ImportError:
    from component_inventory import build_component_inventory  # type: ignore
    from design_tokens import extract_design_tokens  # type: ignore


def _render_design_tokens_md(tokens: dict[str, Any]) -> str:
    def _table(title: str, items: dict[str, str]) -> str:
        if not items:
            return f"### {title}\n\n_None detected._\n\n"
        rows = "\n".join(f"| `{k}` | `{v}` |" for k, v in sorted(items.items()))
        return f"### {title}\n\n| Token | Value |\n|-------|-------|\n{rows}\n\n"

    return (
        "# Design Tokens\n\n"
        "_Extracted by /shipwright-adopt from tailwind.config.* and `:root` CSS variables._\n\n"
        "_Audit trail. The curated design-system view lives in "
        "`.shipwright/designs/visual-guidelines.md`._\n\n"
        + _table("Colors", tokens["colors"])
        + _table("Spacing", tokens["spacing"])
        + _table("Typography", tokens["typography"])
        + _table("CSS Variables", tokens["css_vars"])
    )


# Map common CSS-var / Tailwind names onto the canonical schema's roles.
# Adopt does not invent values — when a slot has no signal, it stays "TBD".
# The aliases cover the shadcn / Tailwind / DaisyUI vocabularies most
# brownfield projects actually use; rare custom names still surface in
# the design_tokens.md audit trail.
_COLOR_ROLE_KEYS: dict[str, tuple[str, ...]] = {
    "Background": (
        "background", "bg", "background-color", "page-bg", "surface", "base-100",
    ),
    "Foreground": (
        "foreground", "fg", "text", "text-color", "body-color", "on-surface",
        "base-content",
    ),
    "Primary": (
        "primary", "brand", "accent-primary", "accent",
        "primary-color", "main",
    ),
    "Secondary": (
        "secondary", "accent-secondary", "secondary-color", "alt",
    ),
    "Muted": (
        "muted", "subtle", "neutral", "muted-foreground", "muted-bg",
        "base-200",
    ),
    "Destructive": (
        "destructive", "danger", "error", "warn", "warning", "critical",
        "alert",
    ),
    "Border": ("border", "divider", "outline", "ring", "stroke"),
}

_RADIUS_KEYS = {
    "Cards": ("radius", "card-radius", "rounded", "border-radius",
              "radius-card", "radius-lg"),
    "Buttons": ("radius", "button-radius", "btn-radius",
                "radius-button", "radius-md"),
    "Inputs": ("radius", "input-radius", "field-radius",
               "radius-input", "radius-sm"),
}


def _resolve_color(role_keys: tuple[str, ...], pools: list[dict[str, str]]) -> str | None:
    for pool in pools:
        for k in role_keys:
            if k in pool:
                return pool[k]
    return None


def _color_table(tokens: dict[str, Any]) -> str:
    """Pull semantic color roles from extracted tokens. If no match, the row
    notes "TBD — refine via /shipwright-design". The intent is not to invent
    a palette, just to surface what we found mapped onto canonical roles."""
    pools = [tokens.get("css_vars", {}), tokens.get("colors", {})]
    rows = []
    for role, keys in _COLOR_ROLE_KEYS.items():
        value = _resolve_color(keys, pools)
        if value is None:
            rows.append(f"| {role} | _TBD_ | refine via /shipwright-design |")
        else:
            rows.append(f"| {role} | `{value}` | extracted from tokens |")
    return (
        "| Role | Value | Source |\n"
        "|------|-------|--------|\n" + "\n".join(rows) + "\n"
    )


def _typography_summary(tokens: dict[str, Any]) -> str:
    sizes = tokens.get("typography", {})
    if not sizes:
        return (
            "- **Primary font:** _TBD — none detected_\n"
            "- **Headings/body:** _TBD — refine via /shipwright-design_\n"
        )
    pairs = ", ".join(f"`{k}` = `{v}`" for k, v in list(sizes.items())[:8])
    return (
        "- **Detected font sizes:** " + pairs + "\n"
        "- **Primary font:** _TBD — extract from project's font-family setup_\n"
    )


def _spacing_summary(tokens: dict[str, Any]) -> str:
    spacing = tokens.get("spacing", {})
    css_vars = tokens.get("css_vars", {})
    if spacing:
        pairs = ", ".join(f"`{k}` = `{v}`" for k, v in list(spacing.items())[:8])
        return f"- **Detected spacing scale:** {pairs}\n"
    if any(k.startswith("space") or k == "gap" for k in css_vars):
        return "- **Detected spacing variables in CSS.** See `design_tokens.md`.\n"
    return "- **Base unit:** _TBD — no spacing tokens detected_\n"


def _radius_table(tokens: dict[str, Any]) -> str:
    pools = [tokens.get("css_vars", {}), tokens.get("colors", {})]
    rows = []
    for label, keys in _RADIUS_KEYS.items():
        value = _resolve_color(keys, pools)  # same lookup logic
        rows.append(f"| {label} | `{value}` |" if value else f"| {label} | _TBD_ |")
    rows.append("| Avatars | full |")
    return (
        "| Element | Radius |\n"
        "|---------|--------|\n" + "\n".join(rows) + "\n"
    )


def _component_patterns(inventory: dict[str, Any]) -> str:
    if inventory["total"] == 0:
        return (
            "- **Buttons / Cards / Forms / Tables:** _TBD — no components detected_\n"
            "- Refine via /shipwright-design after the first iterate.\n"
        )
    common = sorted(inventory["components"], key=lambda c: -c["usage_count"])[:5]
    bullets = "\n".join(
        f"- **{c['name']}** (`{c['path']}`, {c['usage_count']} usage(s)) — see "
        "component_inventory.md for the full table."
        for c in common
    )
    return (
        bullets
        + "\n\n"
        + "_Pattern descriptions (variants, hover states, validation styles) "
        "are TBD — refine via /shipwright-design._\n"
    )


def _render_visual_guidelines_md(
    tokens: dict[str, Any],
    inventory: dict[str, Any],
) -> str:
    """Canonical schema, slot-filled from extracted tokens.

    Schema mirrors `plugins/shipwright-design/.../visual-guidelines-template.md`
    so /shipwright-design can consume the artifact verbatim.
    """
    return (
        "# Visual Guidelines\n\n"
        "> Generated by /shipwright-adopt from extracted design tokens.\n"
        "> Refine via /shipwright-design or /shipwright-iterate.\n"
        f"> Raw audit trail: `{AGENT_DOCS_DIR}/design_tokens.md`.\n\n"
        "## Typography\n\n"
        + _typography_summary(tokens)
        + "\n## Colors\n\n"
        "### Light Mode\n\n"
        + _color_table(tokens)
        + "\n## Spacing & Layout\n\n"
        + _spacing_summary(tokens)
        + "\n## Border Radius\n\n"
        + _radius_table(tokens)
        + "\n## Shadows\n\n"
        "| Level | Usage |\n"
        "|-------|-------|\n"
        "| xs | Inputs, subtle elements |\n"
        "| md | Cards (default) |\n"
        "| lg | Dropdowns, popovers |\n"
        "| xl | Modals |\n\n"
        "_Shadow tokens are TBD — refine if the project defines a custom scale._\n"
        "\n## Component Patterns\n\n"
        + _component_patterns(inventory)
    )


def _render_component_inventory_md(
    tokens: dict[str, Any],
    inventory: dict[str, Any],
    screenshots_count: int,
) -> str:
    """Component table + screenshot links. Architecture-shaped — kept separate
    from the design-system artifact so /shipwright-design isn't fed a wall of
    file paths."""
    if inventory["total"] == 0:
        components_block = "_No components detected under src/components, src/ui, or src/app._\n"
    else:
        rows = "\n".join(
            f"| `{c['name']}` | `{c['path']}` | {c['props_count']} | {c['usage_count']} |"
            for c in sorted(inventory["components"], key=lambda x: -x["usage_count"])[:50]
        )
        components_block = (
            f"Detected **{inventory['total']}** component(s):\n\n"
            "| Name | Path | Props | Usages |\n"
            "|------|------|-------|--------|\n"
            f"{rows}\n"
        )
    screenshot_block = (
        f"{screenshots_count} screenshot(s) persisted to `{AGENT_DOCS_DIR}/visual/screenshots/`."
        if screenshots_count > 0
        else "_No crawl screenshots available — run /shipwright-adopt with the dev server up to populate._"
    )
    color_summary = (
        ", ".join(f"`{name}` = `{val}`" for name, val in list(tokens["colors"].items())[:10])
        or "_no Tailwind colors detected — see `design_tokens.md`_"
    )
    return (
        "# Component Inventory\n\n"
        "_Auto-generated by /shipwright-adopt. Architecture documentation; the "
        "curated design-system view lives in `.shipwright/designs/visual-guidelines.md`._\n\n"
        "## Components\n\n"
        f"{components_block}\n"
        "## Token Snapshot\n\n"
        f"Top extracted colors: {color_summary}\n\n"
        f"_Full token list: `{AGENT_DOCS_DIR}/design_tokens.md`._\n\n"
        "## Screenshots\n\n"
        f"{screenshot_block}\n"
    )


def _persist_screenshots(project_root: Path) -> int:
    src_dir = project_root / ".shipwright" / "adopt" / "screenshots"
    dst_dir = project_root / AGENT_DOCS_DIR / "visual" / "screenshots"
    if not src_dir.is_dir():
        return 0
    dst_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in src_dir.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        shutil.copy2(f, dst_dir / f.name)
        count += 1
    return count


def generate_visual_docs(
    project_root: Path,
    frontend_root: Path | None = None,
) -> dict[str, Any]:
    """Generate visual docs for the project. Returns a result dict the
    caller can surface in the handoff.

    `frontend_root` defaults to `project_root` for single-service repos.
    For multi-service repos pass the primary frontend service dir
    (e.g. `<project_root>/client`) so component scan + tailwind parse
    look in the right place.
    """
    fe_root = frontend_root or project_root
    inventory = build_component_inventory(fe_root)
    tokens = extract_design_tokens(fe_root)
    screenshots_count = _persist_screenshots(project_root)

    has_visual_signal = (
        inventory["total"] > 0
        or any(tokens[k] for k in ("colors", "spacing", "typography", "css_vars"))
        or screenshots_count > 0
    )

    if not has_visual_signal:
        return {
            "wrote_docs": False,
            "component_count": 0,
            "screenshots_persisted": 0,
            "design_tokens": None,
            "visual_guidelines": None,
            "component_inventory": None,
        }

    agent_docs = project_root / AGENT_DOCS_DIR
    agent_docs.mkdir(parents=True, exist_ok=True)
    designs_dir = project_root / DESIGNS_DIR
    designs_dir.mkdir(parents=True, exist_ok=True)

    design_tokens_path = agent_docs / "design_tokens.md"
    component_inventory_path = agent_docs / "component_inventory.md"
    visual_guidelines_path = designs_dir / "visual-guidelines.md"

    # Preserve hand-edited copies before regenerating. The visual docs ARE
    # auto-generated, but operators may add notes between adopt runs — losing
    # those silently is the same anti-pattern fixed for CLAUDE.md / decision_log.
    try:
        from preserve_existing import preserve_if_exists, record_preservation_action  # type: ignore
    except ImportError:
        from .preserve_existing import preserve_if_exists, record_preservation_action  # type: ignore

    preservation_targets = (
        f"{AGENT_DOCS_DIR}/design_tokens.md",
        f"{AGENT_DOCS_DIR}/component_inventory.md",
        f"{DESIGNS_DIR}/visual-guidelines.md",
        # Legacy file from pre-Fix-1 adopt runs. Back it up so operators can
        # recover hand-edits, then leave the path empty (we never write it
        # again under the new schema).
        f"{AGENT_DOCS_DIR}/guideline.md",
    )
    for rel in preservation_targets:
        backup = preserve_if_exists(project_root, rel)
        if backup is not None:
            record_preservation_action(
                project_root,
                file=rel,
                action="overwritten_with_backup",
                backup_path=backup,
                note="visual docs regenerated by adopt (Tier 5)",
            )

    # The legacy guideline.md is replaced by component_inventory.md — once
    # backed up, remove the original so operators do not see two stale docs.
    legacy_guideline = agent_docs / "guideline.md"
    if legacy_guideline.exists():
        legacy_guideline.unlink()

    design_tokens_path.write_text(_render_design_tokens_md(tokens), encoding="utf-8")
    component_inventory_path.write_text(
        _render_component_inventory_md(tokens, inventory, screenshots_count),
        encoding="utf-8",
    )
    visual_guidelines_path.write_text(
        _render_visual_guidelines_md(tokens, inventory),
        encoding="utf-8",
    )

    return {
        "wrote_docs": True,
        "component_count": inventory["total"],
        "screenshots_persisted": screenshots_count,
        "design_tokens": design_tokens_path,
        "component_inventory": component_inventory_path,
        "visual_guidelines": visual_guidelines_path,
    }
