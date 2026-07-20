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


#: `invalid_layers` reasons that are ADVISORY. **The single definition** — the
#: D-layer verdict imports this rather than restating it, because two literals
#: are exactly what let severity drift: this module and `check_layer` each kept
#: their own idea of which reasons block, and the renderer then tagged a row
#: `advisory` on a line the verdict had already failed the audit for.
#:
#: Closed set, and the closure is the point: anything NOT listed is HARD, so a
#: typo'd or newly-added reason blocks rather than silently ceasing to. Both
#: listed reasons ride on `inferred_legacy` rows.
ADVISORY_LAYER_REASONS = frozenset({"marker_glued", "unknown_layer_token"})

#: How each `invalid_layers` reason renders: (provenance, what happened). The
#: TAG is not stored — it is derived from `ADVISORY_LAYER_REASONS`, so a line
#: cannot say `advisory` about a reason the verdict treats as hard. Hardcoding
#: `[HARD, explicit]` was true only while `no_canonical_layer` was the single
#: reason; a `marker_glued` row is `inferred_legacy` and advisory, so the
#: hardcoded pair stated the wrong severity AND the wrong provenance.
_INVALID_LAYER_KINDS: dict[str, tuple[str, str]] = {
    "no_canonical_layer": ("explicit", "no canonical layer in cell"),
    "marker_glued": ("inferred_legacy", "(inferred) marker glued to a layer"),
    "unknown_layer_token": ("inferred_legacy", "not a known test layer"),
}


def invalid_layer_line(iv: dict) -> str:
    """One malformed ``Layers`` cell, tagged by what actually went wrong.

    ``lost`` is rendered when present: for a glued marker it is the ONLY new
    information the diagnostic carries. "invalid Layers cell" tells an operator
    something is wrong; "e2e was swallowed" tells them what to fix.

    The severity tag is DERIVED, never stored beside the text: an unrecognised
    reason renders `HARD` because that is what the verdict does with it.
    """
    reason = str(iv.get("reason") or "no_canonical_layer")
    source, what = _INVALID_LAYER_KINDS.get(reason, ("unknown", reason))
    tag = "advisory" if reason in ADVISORY_LAYER_REASONS else "HARD"
    lost = iv.get("lost") or []
    lost_note = f" — lost: {', '.join(lost)}" if lost else ""
    return (f"{iv.get('fr', '?')} invalid Layers cell {iv.get('raw', '')!r} "
            f"— {what}{lost_note} [{tag}, {source}]")


__all__ = [
    "fold_defect_line", "invalid_layer_line", "invalid_tag_line", "layer_gap_line",
    "orphan_line", "suggest_layer", "suggest_orphan",
]
