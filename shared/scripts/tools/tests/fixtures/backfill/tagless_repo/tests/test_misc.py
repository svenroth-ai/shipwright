"""Tagless unit test — backfill fixture (DATA, not collected by the real suite).

Matches no FR at any signal → the engine must leave it ``unmapped`` (never
branded a stale test).
"""


def test_unrelated_helper_returns_value():
    assert True
