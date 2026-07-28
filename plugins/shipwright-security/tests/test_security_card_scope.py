"""Scope-option rendering for the security scan card (``security_card``).

AC-6: the operator is offered concrete, countable choices ("everything (22),
or critical and above (2)") rather than an abstract "how far do you want to
go?". Split out of test_security_card.py to keep both files small.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from security_card import scope_options, severity_counts  # noqa: E402


def _counts(**by_sev: int) -> dict[str, int]:
    base = {s: 0 for s in ("critical", "high", "medium", "low", "info")}
    base.update(by_sev)
    return base


@pytest.mark.covers("FR-01.07")
class TestScopeOptions:
    def test_offers_a_cumulative_option_per_populated_tier(self) -> None:
        rendered = scope_options(_counts(critical=2, high=3, low=17))
        assert "everything (22)" in rendered
        assert "critical and above (2)" in rendered
        assert "high and above (5)" in rendered

    def test_empty_tiers_are_not_offered(self) -> None:
        """An option that would select zero findings is not a choice."""
        rendered = scope_options(_counts(critical=2, low=20))
        assert "high and above" not in rendered
        assert "medium and above" not in rendered

    def test_single_tier_collapses_to_everything(self) -> None:
        """With one severity present, "critical and above" IS "everything" —
        offering both would be a fake choice."""
        rendered = scope_options(_counts(critical=3))
        assert rendered == "everything (3)"

    def test_the_widest_tier_never_duplicates_everything(self) -> None:
        rendered = scope_options(_counts(critical=1, low=2))
        assert rendered.count("(3)") == 1

    def test_options_are_ordered_most_severe_first(self) -> None:
        rendered = scope_options(_counts(critical=1, high=1, medium=1))
        assert rendered.index("critical and above") < rendered.index("high and above")

    def test_pairs_with_severity_counts(self) -> None:
        findings = [{"severity": "critical"}, {"severity": "low"}, {"severity": "low"}]
        assert scope_options(severity_counts(findings)) == (
            "everything (3), or critical and above (1)"
        )
