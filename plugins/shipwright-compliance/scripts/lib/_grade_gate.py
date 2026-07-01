"""Control-Grade honesty layer — the Goodhart-resistant verdict gate.

``control_grade.compute_grade`` produces an OpenSSF-Scorecard-style weighted
average. That number is *rich* but, on its own, can average or N/A-exclude away a
single dark or broken control pillar — so a headline can read "A / full control"
while the very signal that *is* control over AI changes (is the security gate
even running; is the test suite passing) has decayed. This module is the
structural counterweight:

:func:`apply_verdict_gate` — the headline (score *and* letter, kept in lock-step)
cannot read "A — full control" when a *load-bearing* control pillar is (a) a dark
**expected** control (configured but unmeasured — e.g. the security gate isn't
running) or (b) outright broken (F-band). The per-dimension table still shows the
full rich detail; only the headline is gated so it can't lie.

**Composition is deliberately grade-neutral.** The *mix* of work — features vs.
maintenance/hardening/refactor — does NOT affect the grade. Control is "is every
requirement's state known and current, and is every change honestly attributed",
not "what fraction of recent work happened to be features". A repo doing a
correct, honest maintenance sprint (few new FR-tags) is fully in control; the
strict FR-tag *rate* and its trend measure workload composition, not control, so
they no longer cap or penalise the grade. Honest attribution is already enforced
structurally at write time (the FR-gate hard-blocks a behavior-affecting change
that omits its FR); requirement coverage and reconciliation currency carry the
traceability control signal, and both are composition-independent.

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
# poor coverage already lowers the weighted average, but it is never a
# verifiability/security *collapse*, so it must not hard-cap into F. Supporting
# dims (reconciliation, size, dependency hygiene) shape the number but never
# hard-cap.
_COLLAPSE_PILLARS = ("test_health", "change_traceability", "security")

# A dark expected control can't read "A — full control": cap one point below the
# A threshold (90), so the headline lands at the top of B with an honest why.
NON_A_CEILING = 89.0

# A broken load-bearing pillar (F-band) caps the headline into F (49 floors to F),
# so a near-half-failing suite can never be a B by averaging.
BROKEN_PILLAR_CEILING = 49.0

# Below this dimension score a load-bearing pillar is "broken" (F-band), not a gap.
_BROKEN_BELOW = 0.5


def apply_verdict_gate(
    inp: GradeInputs, dims: list[DimensionResult], raw_score: float,
) -> tuple[float, list[str]]:
    """Weakest-link cap on the headline; returns ``(ceiling_score, reasons)``.

    The number stays the weighted average unless a load-bearing control pillar is
    dark-but-expected or broken — each lowers the ceiling and adds a
    plain-language reason. The score and letter always move together (no
    "B (95/100)" contradiction) because the caller takes ``min(raw, ceiling)``.
    Workload composition (feature vs. maintenance mix) is grade-neutral and never
    appears here.
    """
    by_key = {d.key: d for d in dims}
    ceiling = raw_score
    reasons: list[str] = []

    # (a) A control this repo is configured to measure is dark (n/a) — e.g. the
    # security gate isn't running. Incomplete verification can't read full control.
    dark = [
        by_key[k] for k in inp.expected_dimensions
        if k in by_key and by_key[k].score is None
    ]
    if dark:
        ceiling = min(ceiling, NON_A_CEILING)
        labels = ", ".join(d.label.lower() for d in dark)
        reasons.append(f"verification incomplete — {labels} not measured")

    # (b) A verifiability/security control has collapsed (F-band) — weakest-link
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
