"""One event-log read policy for the audit groups (Group B + Group D).

WHY THIS MODULE EXISTS
----------------------
``group_b._load_events`` and ``group_d._load_events`` were **byte-identical
duplicates**. Both used the pre-fix idiom — bare ``json.loads(line)`` under an
``except json.JSONDecodeError`` that skips the WHOLE physical line — so a
``merge=union`` merge that joins an unterminated blob to the next side's first
line discarded BOTH records on it. On an append-only audit trail, corruption
must never read as absence: a dropped ``work_completed`` makes a step that
happened read as one that never did (iterate-2026-07-19-…-readers).

Fixing that in two places is how the two copies drift. It lives here once.

WHY NOT ``audit_adapters.py``
-----------------------------
That was the first instinct and it is wrong twice over. ``audit_adapters.py`` is
``state: grandfathered`` in the bloat baseline — already OVER the 300-line limit
— so adding to it ratchets an over-limit file further over and the anti-ratchet
pre-commit hook blocks the commit. And semantically it is the module for
*crossing the cross-package import boundary*; event-log read policy is a
different concern. Extracting a cohesive cluster into a new sub-300 module is
this repo's sanctioned remedy for exactly this shape.

SCOPE — deliberately narrow
---------------------------
Path selection, shared-parser invocation, and absence/``OSError`` mapping. That
is all. Group-specific interpretation of the returned events stays in
``group_b`` / ``group_d``, so this cannot quietly accrete a second audit
abstraction layer (external plan review, GPT #5).
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

from scripts.audit.audit_adapters import load_shared_lib

EVENT_FILE = "shipwright_events.jsonl"


def _jsonl_records() -> ModuleType:
    """The SHARED ``lib.jsonl_records`` — record-boundary SSoT.

    Crossed via ``audit_adapters.load_shared_lib`` and NOT a bare
    ``from lib import jsonl_records``: this plugin ships its own ``scripts/lib``
    package, so the bare form resolves THERE and raises ImportError — the
    ``sys.modules['lib']`` collision ADR-045 describes, verified empirically for
    this plugin rather than assumed.

    ``audit_adapters`` (not ``collectors/_lib_loader``) is the correct loader for
    audit-group code, per that loader's own documented split. Both reach the same
    file; keeping the split intact is what stops the two from diverging.

    A DUPLICATE of the parser was considered and rejected: mirroring a ~70-line
    partial-recovery contract into a second package trades a real fix for a drift
    liability, and the loader already crosses the barrier cleanly.

    ONE SOURCE FILE, TWO RUNTIME OBJECTS. ``collectors/_lib_loader`` yields
    ``lib.jsonl_records`` while this loader execs the same file under a sentinel
    name, so ``change_history`` and the audit groups hold *distinct module
    objects* built from identical source. That is inherent to the two-loader
    split (kept deliberately — see the loader's own docstring) and is harmless
    for a stateless parser, but it means monkeypatching one copy in a test does
    NOT affect the other. Worth knowing before writing a test that assumes it.
    """
    return load_shared_lib("jsonl_records")


def load_events(project_root: Path) -> list[dict] | None:
    """Read ``shipwright_events.jsonl``, recovering concatenated records.

    Returns ``None`` when the log is absent or unreadable, mirroring the
    contract both groups relied on — they distinguish "no log" from "empty log",
    so absence must not collapse into ``[]``.

    SILENT on corruption, by design. Both call sites are silent today and the
    governing invariant for this change is *behaviour-preserving except for
    record recovery*. Both external reviewers flagged that adding warnings here
    is unnecessary for the fix and risks contaminating audit output or tripping
    fail-on-stderr CI. Surfacing an unrecoverable fragment belongs in the groups'
    own findings layer (a ``Finding``, not a ``warnings.warn`` side channel) —
    filed as follow-up, deliberately not folded into a defect repair.

    Only JSON **objects** count as records. The previous code appended
    ``json.loads(line)`` with no ``isinstance`` guard, so a bare scalar entered
    the list as a non-dict and crashed the first downstream ``.get()``.
    """
    path = project_root / EVENT_FILE
    if not path.exists():
        return None
    try:
        result = _jsonl_records().read_jsonl_records(path)
    except OSError:
        return None
    return list(result.records)


__all__ = ["load_events"]
