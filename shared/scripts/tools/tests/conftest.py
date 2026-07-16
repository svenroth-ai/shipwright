"""Test-collection guard for ``shared/scripts/tools/tests``.

Keeps the backfill-engine fixture mini-repo out of the real pytest session.
The tagless sample tests under ``fixtures/backfill/`` (``test_*.py``,
``*.spec.ts``, ``*.test.ts``) are DATA for the TT6 harness — the engine points
at them explicitly (copied to a tmp dir first, since it writes tags). The real
suite must never collect them: they would run as no-op tests and pollute counts.
Mirrors the shipwright-compliance plugin's own fixture-collection guard.
"""

from __future__ import annotations

from pathlib import Path

_BACKFILL_FIXTURES = Path(__file__).parent / "fixtures" / "backfill"


def pytest_ignore_collect(collection_path: Path, config) -> bool:
    p = Path(collection_path)
    return p == _BACKFILL_FIXTURES or _BACKFILL_FIXTURES in p.parents
