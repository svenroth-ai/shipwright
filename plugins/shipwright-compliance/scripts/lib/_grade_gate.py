"""Control-Grade honesty layer — the Goodhart-resistant verdict gate.

``control_grade.compute_grade`` produces an OpenSSF-Scorecard-style weighted
average. That number is *rich* but, on its own, can average or N/A-exclude away a
single dark or declining control pillar — so a headline can read "A / full
control" while the very signal that *is* control over AI changes (who/why a
change happened; is the security gate even running) has decayed. This module is
the structural counterweight, applied symmetrically across pillars:

1. :func:`apply_traceability_penalty` — a *self-relative* FR-tagging decline
   (recent genuine-tag rate below the repo's own all-time rate; a full freeze is
   the maximum) reduces the requirement-traceability dimension by a **capped**
   amount, so the number itself moves. Self-relative ⇒ a stably-low infra repo is
   never punished; only erosion of the repo's own discipline is.
2. :func:`apply_verdict_gate` — the headline (score *and* letter, kept in
   lock-step) cannot read "A — full control" when a *load-bearing* control pillar
   is (a) declining, (b) a dark **expected** control (configured but unmeasured —
   e.g. the security gate isn't running), or (c) outright broken (F-band). The
   per-dimension table still shows the full rich detail; only the headline is
   gated so it can't lie.

Pure and repo-agnostic (no Shipwright collectors), so the kernel stays reusable
by the future generic repo-grader. Type-only imports avoid a runtime cycle with
``control_grade``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type hints only, no runtime import cycle
    from scripts.lib.control_grade import DimensionResult, GradeInputs

# Controls whose sub-0.5 score is a verifiability/security COLLAPSE — a failing
# test suite, missing change provenance, or unaddressed high/critical vulns —
# which caps the headline to F. requirement_traceability is deliberately ABSENT:
# its erosion is a *decline* (capped to B above by the decline branch), never a
# collapse, so the decline penalty is never double-counted into an F; its low
# coverage/tagging is already carried by the weighted average. Supporting dims
# (reconciliation, size, dependency hygiene) shape the number but never hard-cap.
_COLLAPSE_PILLARS = ("test_health", "change_traceability", "security")

# A full FR-tag freeze removes at most this share of the requirement-traceability
# dimension (capped, so a freeze depresses but never zeroes the dimension).
TRACE_DECLINE_MAX_PENALTY = 0.35

# A declining or dark control can't read "A — full control": cap one point below
# the A threshold (90), so the headline lands at the top of B with an honest why.
NON_A_CEILING = 89.0

# A broken load-bearing pillar (F-band) caps the headline into F (49 floors to F),
# so a near-half-failing suite can never be a B by averaging.
BROKEN_PILLAR_CEILING = 49.0

# Below this dimension score a load-bearing pillar is "broken" (F-band), not a gap.
_BROKEN_BELOW = 0.5


def _pct(x: float | None) -> str:
    """Format a [0,1] rate as a whole-percent string (``"3%"``)."""
    return f"{(x or 0.0):.0%}"


def trace_decline_severity(inp: GradeInputs) -> float:
    """[0,1] severity of an FR-tagging decline vs the repo's own all-time rate.

    0 when there is no trend signal, no baseline, or no decline; 1 on a total
    freeze. Self-relative against the all-time rate, so a stably-low-but-steady
    repo is never penalised — only erosion of the repo's own traceability is.
    """
    recent, base = inp.fr_tag_recent_pct, inp.fr_tag_all_pct
    if recent is None or base is None or base <= 0.0:
        return 0.0
    if recent <= 0.0:
        return 1.0
    if recent >= base:
        return 0.0
    return max(0.0, min(1.0, (base - recent) / base))


def apply_traceability_penalty(
    req_score: float, inp: GradeInputs,
) -> tuple[float, str]:
    """Apply the capped traceability-decline penalty to a dimension score.

    Returns ``(possibly_lower_score, detail_suffix)`` — the suffix is appended to
    the dimension's detail so the decline is transparent in the dashboard."""
    severity = trace_decline_severity(inp)
    if severity <= 0.0:
        return req_score, ""
    penalized = req_score * (1.0 - TRACE_DECLINE_MAX_PENALTY * severity)
    suffix = (
        f"; FR-tag rate {_pct(inp.fr_tag_recent_pct)} vs "
        f"{_pct(inp.fr_tag_all_pct)} all-time — declining"
    )
    return penalized, suffix


def apply_verdict_gate(
    inp: GradeInputs, dims: list[DimensionResult], raw_score: float,
) -> tuple[float, list[str]]:
    """Weakest-link cap on the headline; returns ``(ceiling_score, reasons)``.

    The number stays the weighted average unless a load-bearing control pillar is
    declining, dark-but-expected, or broken — each lowers the ceiling and adds a
    plain-language reason. The score and letter always move together (no
    "B (95/100)" contradiction) because the caller takes ``min(raw, ceiling)``.
    """
    by_key = {d.key: d for d in dims}
    ceiling = raw_score
    reasons: list[str] = []

    # (a) Traceability in decline/freeze — the BP-1 Goodhart guard.
    if trace_decline_severity(inp) > 0.0:
        ceiling = min(ceiling, NON_A_CEILING)
        window = f", last {inp.fr_tag_window}" if inp.fr_tag_window else ""
        reasons.append(
            "traceability declining "
            f"(FR-tag {_pct(inp.fr_tag_recent_pct)} vs "
            f"{_pct(inp.fr_tag_all_pct)} all-time{window})"
        )

    # (b) A control this repo is configured to measure is dark (n/a) — e.g. the
    # security gate isn't running. Incomplete verification can't read full control.
    dark = [
        by_key[k] for k in inp.expected_dimensions
        if k in by_key and by_key[k].score is None
    ]
    if dark:
        ceiling = min(ceiling, NON_A_CEILING)
        labels = ", ".join(d.label.lower() for d in dark)
        reasons.append(f"verification incomplete — {labels} not measured")

    # (c) A verifiability/security control has collapsed (F-band) — weakest-link
    # cap to F, so it can't be averaged up into "minor gaps".
    broken = [
        by_key[k] for k in _COLLAPSE_PILLARS
        if k in by_key and by_key[k].score is not None
        and by_key[k].score < _BROKEN_BELOW
    ]
    if broken:
        worst = min(broken, key=lambda d: d.score)
        ceiling = min(ceiling, BROKEN_PILLAR_CEILING)
        reasons.append(f"{worst.label.lower()} failing ({worst.detail})")

    return ceiling, reasons
