"""Evidence-line + suggested-command rendering for the Group-D traceability detectives.

Split from ``_group_d_traceability`` (which owns the *verdicts*) so that file stays under
its ADR-096 cap and the two concerns separate cleanly: everything here turns an already-
decided finding into human-readable text and never influences pass/fail.

Rendering rule that matters for safety: repo-controlled strings (test ids, raw markdown
rows) belong in *evidence*, never in a suggested copy-paste command — a test id carrying
a quote or shell metacharacter would break the command a user is invited to run. Only
schema-pinned ``FR-\\d{2}\\.\\d{2}`` ids are interpolated into commands.
"""

from __future__ import annotations


def suggest_orphan(fr: str | None) -> str:
    """The ``/shipwright-iterate`` command offered alongside a D-orphan failure.

    ``fr`` is schema-pinned (or None), so it is safe to interpolate; the offending test
    path deliberately stays in evidence instead.
    """
    target = f"for {fr} " if fr else ""
    return (
        f"/shipwright-iterate --type change \"retarget or retire the orphaned "
        f"test(s) {target}— see .shipwright/compliance/test-traceability.json\""
    )


def suggest_layer() -> str:
    """The command offered alongside a D-layer failure."""
    return (
        "/shipwright-iterate --type change \"add an executed-passing test at the "
        "missing layer(s) — see .shipwright/compliance/audit-report.md\""
    )


def orphan_line(o: dict, tag: str) -> str:
    """``<test> → <fr> (<reason>) [<tag>]`` for one orphan entry."""
    fr = o.get("tagged_fr")
    target = f"→ {fr}" if fr else "(no live FR)"
    return f"{o.get('test', '?')} {target} ({o.get('reason', '')}) [{tag}]"


def invalid_tag_line(iv: dict) -> str:
    """One malformed ``@FR`` tag — a typo that silently under-covers."""
    return (f"{iv.get('test', '?')}: malformed tag {iv.get('raw', '')!r} "
            f"({iv.get('reason', 'invalid')}) — silent under-coverage [invalid_tag]")


def fold_defect_line(fd: dict) -> str:
    """One ``## FR-Fold-Map`` hygiene defect, with enough locus to fix the spec.

    Carries ``spec_path:line`` because a fold defect is only actionable if the author can
    find the offending row; the bounded ``raw`` stays out of the line (it is repo-
    controlled text) unless a renderer explicitly escapes it.
    """
    where = fd.get("spec_path") or "?"
    if fd.get("line"):
        where = f"{where}:{fd['line']}"
    target = f" → {fd['survivor']}" if fd.get("survivor") else ""
    return (f"{fd.get('folded', '?')}{target} — {fd.get('kind', 'defect')} "
            f"at {where} [fold_map]")


def layer_gap_line(gap: tuple, tag: str) -> str:
    """``FR-XX.YY [layer] (Priority) — reason [tag, provenance]`` for one D-layer gap."""
    disp, layer, priority, reason, source = gap
    return f"{disp} [{layer}] ({priority}) — {reason} [{tag}, {source}]"


def invalid_layer_line(iv: dict) -> str:
    """An FR whose explicitly-headed Layers cell resolved to zero canonical layers."""
    return f"{iv.get('fr', '?')} invalid Layers cell {iv.get('raw', '')!r} [HARD, explicit]"


__all__ = [
    "fold_defect_line", "invalid_layer_line", "invalid_tag_line", "layer_gap_line",
    "orphan_line", "suggest_layer", "suggest_orphan",
]
