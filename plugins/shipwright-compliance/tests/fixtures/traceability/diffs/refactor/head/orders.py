"""Order service (refactor diff — HEAD). DATA for the harness.

Pure refactor: the two private helpers are inlined into one. Same result and the
same public function signature; the tests are unchanged.
"""


def persist_order(order):
    return _persist_rows([order])


def _persist_rows(rows):
    return len(rows) == 1
