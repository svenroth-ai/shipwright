"""Order service (refactor diff — BASE). DATA for the harness."""


def persist_order(order):
    rows = _serialize(order)
    return _write(rows)


def _serialize(order):
    return [order]


def _write(rows):
    return len(rows) == 1
