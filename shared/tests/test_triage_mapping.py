"""Pure-function mapping tests for the triage inbox API.

AC-8: drift-protection for `suggest_priority_from_severity` and
`suggest_domain_from_source`. Constants asserted against the imported
SSoT (no duplicated literals).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from triage import (  # noqa: E402
    DEFAULT_DOMAIN,
    DOMAIN_FROM_SOURCE,
    KINDS,
    PRIORITY_FROM_SEVERITY,
    SEVERITIES,
    STATUSES,
    suggest_domain_from_source,
    suggest_priority_from_severity,
)


# --- suggest_priority_from_severity --------------------------------------

@pytest.mark.parametrize(
    ("severity", "expected"),
    [
        ("critical", "P0"),
        ("high", "P1"),
        ("medium", "P2"),
        ("low", "P3"),
        ("info", "P3"),
    ],
)
def test_suggest_priority_from_severity_table(severity: str, expected: str) -> None:
    assert suggest_priority_from_severity(severity) == expected


def test_suggest_priority_invalid_severity_raises() -> None:
    with pytest.raises(ValueError):
        suggest_priority_from_severity("catastrophic")


def test_priority_table_covers_all_known_severities() -> None:
    """Every severity in the SSoT enum has a priority mapping."""
    for sev in SEVERITIES:
        assert sev in PRIORITY_FROM_SEVERITY, f"missing priority for severity={sev}"


# --- suggest_domain_from_source ------------------------------------------

@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("compliance", "compliance"),
        ("phaseQuality", "engineering"),
        ("security", "engineering"),
        ("performance", "engineering"),
        ("ci", "engineering"),
        ("iterate", "engineering"),
        ("manual", "engineering"),
        ("unknown-source-xyz", "engineering"),  # default fallback
    ],
)
def test_suggest_domain_from_source_table(source: str, expected: str) -> None:
    assert suggest_domain_from_source(source) == expected


def test_default_domain_constant() -> None:
    assert DEFAULT_DOMAIN == "engineering"


def test_domain_table_only_overrides_for_compliance() -> None:
    """`compliance` is the only non-default mapping; the rest fall back to
    `engineering`. Tighten this when more domains are added."""
    assert DOMAIN_FROM_SOURCE.get("compliance") == "compliance"
    # No other source short-circuits the fallback today.
    for src in ("phaseQuality", "security", "performance", "ci", "iterate"):
        # If a source is explicitly mapped, it must be a known domain;
        # otherwise it must fall through to DEFAULT_DOMAIN.
        if src in DOMAIN_FROM_SOURCE:
            assert DOMAIN_FROM_SOURCE[src] == DEFAULT_DOMAIN, (
                f"unexpected explicit domain mapping for {src}"
            )


# --- enum SSoT smoke -----------------------------------------------------

def test_status_enum_values() -> None:
    assert set(STATUSES) == {"triage", "promoted", "dismissed", "snoozed"}


def test_severity_enum_values() -> None:
    assert set(SEVERITIES) == {"critical", "high", "medium", "low", "info"}


def test_kind_enum_values() -> None:
    assert set(KINDS) == {
        "bug",
        "feature",
        "improvement",
        "compliance",
        "maintenance",
    }
