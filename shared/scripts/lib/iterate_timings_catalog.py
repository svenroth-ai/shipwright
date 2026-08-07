#!/usr/bin/env python3
"""Iterate-timing spans — span-name catalog (SSoT) and name/parent validation.

Split from ``iterate_timings.py`` at ~300 lines (file-size guideline). Self-
contained leaf module — imports only :class:`IterateTimingError` from the
sibling ``iterate_timings_extra`` leaf (neither leaf depends on the parent,
which imports back from both) — enumerating every span this project records:
7 top-level lifecycle groups + the nested spans named in the card.
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from iterate_timings_extra import IterateTimingError  # noqa: E402

# ---------------------------------------------------------------------------
# Catalog (SSoT) — 7 top-level groups + 15 nested spans named in the card.
# ---------------------------------------------------------------------------

TOP_LEVEL_SPANS: tuple[str, ...] = (
    "discovery_diagnosis", "planning", "implementation", "verification",
    "review", "finalization", "delivery",
)

# F5b (finalize_iterate.py) folds the durable event BEFORE F6 commits and
# BEFORE F11 pushes/delivers — the SKILL places "end finalization" at F11
# entry and "delivery" only self-records from the real F11 CLI invocation, so
# neither can EVER be closed (or, for delivery, exist at all) when the fold
# runs, in every run, structurally — not an occasional gap (doubt review).
# Coverage/degraded is measured against this achievable subset so a genuinely
# complete pre-fold run reads as complete, not permanently "degraded";
# finalization/delivery are still shown per-run, just not penalized for an
# incompleteness the architecture guarantees. See iterate-timings.md.
FOLD_TIME_CAPTURABLE_SPANS: tuple[str, ...] = (
    "discovery_diagnosis", "planning", "implementation", "verification", "review",
)

# name -> frozenset of valid parent names. Top-level spans parent to ``None``.
SPAN_PARENTS: dict[str, frozenset] = {
    "discovery_diagnosis": frozenset({None}),
    "planning": frozenset({None}),
    "implementation": frozenset({None}),
    "verification": frozenset({None}),
    "review": frozenset({None}),
    "finalization": frozenset({None}),
    "delivery": frozenset({None}),
    "focused_tests": frozenset({"implementation"}),
    "pre_f0_validation": frozenset({"verification"}),
    "f0_queue": frozenset({"verification"}),
    "canonical_f0_active": frozenset({"verification"}),
    "f0_unit_result": frozenset({"canonical_f0_active"}),
    "self_review": frozenset({"review"}),
    "spec_review": frozenset({"review"}),
    "code_review": frozenset({"review"}),
    "doubt_review": frozenset({"review"}),
    "external_review": frozenset({"planning", "review"}),
    "reviewer_wait": frozenset({"planning", "review"}),
    "remediation": frozenset({"review"}),
    "delivery_wait": frozenset({"delivery"}),
    "ci_wait": frozenset({"delivery", "delivery_wait"}),
    "post_ci_remediation": frozenset({"delivery"}),
}
SPAN_NAMES: frozenset = frozenset(SPAN_PARENTS)

SOURCES: frozenset = frozenset({"producer", "agent", "derived"})
OUTCOMES: frozenset = frozenset({"completed", "incomplete", "cancelled", "unavailable"})


def validate_name_parent(name: str, parent: str | None) -> None:
    if name not in SPAN_NAMES:
        raise IterateTimingError(f"unknown span name {name!r}")
    if parent not in SPAN_PARENTS[name]:
        allowed = ", ".join(str(p) for p in sorted(SPAN_PARENTS[name], key=lambda p: p or ""))
        raise IterateTimingError(f"span {name!r} does not accept parent {parent!r} (allowed: {allowed})")
