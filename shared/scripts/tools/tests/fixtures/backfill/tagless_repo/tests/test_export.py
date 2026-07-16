"""Tagless unit test — backfill fixture (DATA, not collected by the real suite).

Only title similarity reaches FR-05.01 ("export orders to a CSV file"), so the
engine proposes it (advisory) but must NOT auto-write it.
"""


def test_export_orders_to_csv():
    assert True
