"""Unit tests (pytest) for the demo app — traceability fixture.

DATA for the traceability harness, NOT collected by the real suite (see the
fixtures/traceability/conftest.py collection guard). Demonstrates the
`@pytest.mark.covers` grammar form, a malformed tag, and an untagged test.
"""

import pytest


@pytest.mark.covers("FR-03.01")
def test_sign_in_rejects_bad_password():
    # unit layer, tagged FR-03.01, passes in evidence.
    assert True


@pytest.mark.covers("FR-1.3")
def test_sign_in_locale():
    # Malformed tag (single-digit segments) -> invalid_tags, never coverage.
    assert True


def test_health_endpoint():
    # No @FR tag -> untagged_tests (informational).
    assert True
