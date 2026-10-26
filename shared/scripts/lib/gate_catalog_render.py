"""Renderer for ``shared/config/gate_catalog.md`` (extracted from ``gate_policy``).

``gate_catalog.md`` is GENERATED from ``gate_catalog.json``. The pure rendering
lives here so ``gate_policy`` stays the policy mechanism; it takes the policy
constants as arguments (importing them back would be a cycle) and
``gate_policy.render_catalog_markdown`` remains the public entry point.
"""
from __future__ import annotations

from typing import Any, Optional

# Unicode punctuation the JSON summaries use, transliterated to ASCII so the
# rendered doc is pure ASCII. That makes the committed file encoding-agnostic:
# it round-trips byte-for-byte through ANY shell redirect (bash, cmd, and even
# PowerShell's UTF-16 default) or the --output writer, and the drift-guard reads
# it back identically. (Belt: the CLI still writes UTF-8/LF explicitly.)
_ASCII_XLATE = {
    "—": "-", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "→": "->", "…": "...",
}


def _ascii(text: str) -> str:
    for uni, asc in _ASCII_XLATE.items():
        text = text.replace(uni, asc)
    return text


def _cell(text: Optional[str]) -> str:
    """Markdown-table-safe cell: no pipes, no newlines (em-dash for empty)."""
    if not text:
        return "-"
    return text.replace("|", "\\|").replace("\n", " ").strip()


def render_catalog_doc(
    cat: dict[str, Any],
    *,
    policies_order: tuple[str, ...],
    covered_phases: tuple[str, ...],
    auto_default: str,
) -> str:
    """Render the full human-readable catalog doc from a loaded catalog
    (deterministic, pure ASCII). ``gate_policy.render_catalog_markdown`` is the
    public entry: it loads the catalog and passes the authoritative constants."""
    gates = cat["gates"]
    policies = cat.get("policies", {})
    pending = cat.get("pending_phases", {})

    lines: list[str] = [
        "# Single-Session Phase-Gate Catalog",
        "",
        "> **GENERATED** from `shared/config/gate_catalog.json` by",
        "> `gate_policy.render_catalog_markdown` (Campaign 2026-07-07, SS2). Do NOT",
        "> edit by hand — edit the JSON and regenerate (shell-agnostic writer):",
        "> `uv run shared/scripts/tools/resolve_gate_policy.py --render-doc --output shared/config/gate_catalog.md`",
        "",
        _cell(cat.get("description")),
        "",
        "## Policies",
        "",
    ]
    for name in policies_order:
        lines.append(f"- **`{name}`** — {_cell(policies.get(name))}")
    lines += [
        "",
        f"**Covered phases:** {', '.join(covered_phases)}.",
    ]
    if pending.get("phases"):
        lines.append(
            f"**Pending (follow-up):** {', '.join(pending['phases'])} — {_cell(pending.get('note'))}"
        )
    lines.append("")

    for phase in covered_phases:
        phase_gates = [g for g in gates.values() if g["phase"] == phase]
        lines += [
            f"## `{phase}`",
            "",
            "| Gate | Policy | Fires | Constitution | Summary / default |",
            "|---|---|---|---|---|",
        ]
        for g in phase_gates:
            note = g["summary"]
            if g["policy"] == auto_default and g.get("default_answer"):
                note = f"{note} **Default:** {g['default_answer']}"
            if g.get("unattended_answer"):
                note = f"{note} **Unattended:** {g['unattended_answer']}"
            const = "yes (locked)" if g["constitution"] else "no"
            lines.append(
                f"| `{g['id']}` | {g['policy']} | {g['fires']} | {const} | {_cell(note)} |"
            )
        lines.append("")

    return _ascii("\n".join(lines) + "\n")
