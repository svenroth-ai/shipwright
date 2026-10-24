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


# Stack-profile test isolation (campaign stack-profile-resolver, D4): keeps the
# developer's real ~/.shipwright/profiles out of every test in this root.
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_isolation_dir = str(_Path(__file__).resolve().parents[2])
_added = _isolation_dir not in _sys.path
if _added:
    _sys.path.append(_isolation_dir)
from profile_test_isolation import isolate_user_profiles_dir  # noqa: E402,F401

if _added:  # leave sys.path as found: shared/scripts holds a `tools` package that would shadow a plugin's
    _sys.path.remove(_isolation_dir)
