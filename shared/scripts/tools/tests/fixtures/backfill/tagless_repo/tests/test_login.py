"""Already-tagged unit test — backfill fixture (DATA, not collected by the suite).

Carries an explicit ``@pytest.mark.covers("FR-05.01")`` tag → the engine must
honour it and NEVER re-write it (idempotency: a re-run adds no duplicate tag).
"""

import pytest


@pytest.mark.covers("FR-05.01")
def test_login_succeeds():
    assert True
