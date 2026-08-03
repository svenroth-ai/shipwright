"""The lock discipline `expected_status` depends on — and the hazards in it.

Split out of `test_triage_expected_status.py` (which crossed 300 lines). Three
properties, all of which fail SILENTLY or by HANGING rather than by erroring,
which is why each gets an explicit observable:

1. the precondition is evaluated while the canonical lock is HELD — AC-1's
   whole point, and the thing that distinguishes this fix from the
   read-then-write the operator CLI already had;
2. `mark_status` acquires that lock exactly once;
3. `read_all_items` acquires it not at all — because `FileLock` is
   non-reentrant with no timeout, so a read side that took it would not raise,
   it would hang forever.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import triage  # noqa: E402
from triage import append_triage_item, mark_status, read_all_items  # noqa: E402


def _seed(root: Path) -> str:
    return append_triage_item(
        root, source="iterate", severity="low", kind="bug",
        title="t", detail="d",
    )



def test_mark_status_acquires_the_canonical_lock_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins the prerequisite that makes the in-lock `read_all_items` legal.

    `FileLock` is NOT reentrant — Windows spins on `msvcrt.locking` forever,
    POSIX blocks in `flock`. A refactor that made the read side take the lock
    would not fail this suite, it would HANG it; counting acquisitions turns
    that hang into a red test. Patched on the module object, not by dotted
    string (ADR-045).
    """
    real_cls = triage._load_file_lock_cls()
    acquisitions = []

    class CountingLock(real_cls):  # type: ignore[misc,valid-type]
        def __enter__(self):
            acquisitions.append(1)
            return super().__enter__()

    item_id = _seed(tmp_path)
    monkeypatch.setattr(triage, "_load_file_lock_cls", lambda: CountingLock)
    mark_status(tmp_path, item_id, new_status="dismissed", by="a",
                expected_status="triage")
    assert sum(acquisitions) == 1


def test_the_precondition_is_evaluated_while_the_lock_is_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-1's whole point, and the one property nothing else here pins.

    Hoisting the residence probe and the precondition ABOVE the `with` — the
    natural "don't take the lock just to find out it is a no-op" optimisation —
    keeps every other test in this run green: the byte-identity probe still
    sees no write, the KeyError still precedes, the acquisition count is still
    1, and the AST pins are source-level. It also fully reopens the race,
    leaving exactly the read-then-write the operator CLI already had and which
    this run describes as protecting "by luck, not by construction".

    So assert the property directly: the union read that feeds the comparison
    must happen while the lock is HELD. `read_all_items` is wrapped, not
    stubbed — the production call still runs.
    """
    real_lock_cls = triage._load_file_lock_cls()
    depth: list[int] = []

    class TracingLock(real_lock_cls):  # type: ignore[misc,valid-type]
        def __enter__(self):
            result = super().__enter__()
            depth.append(1)
            return result

        def __exit__(self, *exc):
            depth.pop()
            return super().__exit__(*exc)

    real_read = triage.read_all_items
    held_when_read: list[bool] = []

    def tracing_read(project_root, **kwargs):
        held_when_read.append(bool(depth))
        return real_read(project_root)

    item_id = _seed(tmp_path)
    monkeypatch.setattr(triage, "_load_file_lock_cls", lambda: TracingLock)
    monkeypatch.setattr(triage, "read_all_items", tracing_read)

    mark_status(tmp_path, item_id, new_status="dismissed", by="a",
                expected_status="triage")

    assert held_when_read, "the precondition never read the store at all"
    assert all(held_when_read), (
        "the precondition's read ran OUTSIDE the canonical lock — the item's "
        "status is unowned between that read and the append, which is the "
        "race this whole change exists to close"
    )


def test_read_all_items_takes_no_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of the same prerequisite, stated positively."""
    _seed(tmp_path)

    def _forbidden():
        raise AssertionError("read_all_items must not acquire the write lock")

    monkeypatch.setattr(triage, "_load_file_lock_cls", _forbidden)
    assert len(read_all_items(tmp_path)) == 1


