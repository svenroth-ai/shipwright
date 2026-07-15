"""Integration test (pytest) — traceability fixture.

DATA for the harness, not collected by the real suite. Demonstrates a tagged
test at the integration layer (path-based layer detection lives in the
production collector; the golden manifest pins the layer here).
"""

import pytest


@pytest.mark.covers("FR-03.03")
def test_order_persists_to_database():
    # integration layer, tagged FR-03.03, passes in evidence.
    assert True
