"""Two contracts this change rests on that nothing else asserts directly.

1. **A dedup warning must never, by itself, stop delivery.** Three independent
   external-review findings warned that folding the new warnings into the sweep's
   error channel would turn a safety improvement into a fresh delivery wedge — the
   exact failure class the card exists to remove. The end-to-end proof lives in
   ``test_triage_write_path_integration.py``; this is the unit pin at
   ``sweep_quarantine.decide``, because that is the function a future refactor
   would break.

2. **The re-export surfaces still resolve.** Four modules were extracted to make
   room for the fixes, and every historical import path was preserved by
   re-exporting. A rename or a circular import would break callers that this
   diff never touched, so both the OLD paths and the NEW ones are imported here —
   and each pair is asserted to be the SAME object, since a re-export that has
   drifted into a second copy resolves fine and behaves differently.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[1]
for _p in (_SHARED / "scripts", _SHARED / "scripts" / "tools", _SHARED / "tests"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import _sweep_helpers as h  # noqa: E402
from lib.sweep_quarantine import decide  # noqa: E402

_ANCHOR = "2026-08-01T00:00:00Z"


def _append(iid: str, *, title: str, ts: str) -> str:
    return (f'{{"event":"append","id":"{iid}","ts":"{ts}","originalTs":"{_ANCHOR}",'
            f'"title":"{title}","status":"triage"}}')


# --- 1. a warning is informational, an error is not --------------------------

def test_benign_keep_last_collapse_stays_clean_and_carries_the_warning() -> None:
    """R1's named pin: ``action == "clean"`` AND ``warnings != []`` together."""
    v1 = _append("trg-ref", title="v1", ts="2026-08-01T00:00:00Z")
    v2 = _append("trg-ref", title="v2", ts="2026-08-02T00:00:00Z")

    decision = decide([h.HEADER], [v1, v2], "\n")

    assert decision.action == "clean", decision
    assert decision.warnings and "superseded" in decision.warnings[0]
    assert decision.errors == []
    assert v2 in decision.deduped_text and v1 not in decision.deduped_text


def test_an_id_collision_is_what_blocks_and_it_says_why() -> None:
    """The contrast case: blocking comes from the RETAINED duplicate reaching the
    validator, and the collision diagnosis rides along so the block is actionable."""
    a = ('{"event":"append","id":"trg-dupe","ts":"2026-08-01T00:00:00Z",'
         '"originalTs":"2026-01-01T00:00:00Z","title":"A","status":"triage"}')
    b = ('{"event":"append","id":"trg-dupe","ts":"2026-08-02T00:00:00Z",'
         '"originalTs":"2026-07-07T00:00:00Z","title":"B","status":"triage"}')

    decision = decide([h.HEADER], [a, b], "\n")

    assert decision.action == "block"
    assert any("duplicate append" in e for e in decision.errors)
    assert decision.warnings and "32-bit id collision" in decision.warnings[0]


def test_no_same_id_appends_means_no_warnings_at_all() -> None:
    """Control: the warning list is not simply always populated."""
    decision = decide([h.HEADER], [_append("trg-a", title="a", ts="2026-08-01T00:00:00Z")], "\n")
    assert decision.action == "clean"
    assert decision.warnings == []


# --- 2. the extracted modules are reachable from both sides ------------------

#: ``(old dotted path, new dotted path, attribute)`` for every name this change moved.
_REEXPORTS = [
    # ``reconcile_triage``'s moved names are re-exported under their historical
    # PRIVATE spellings, so they live in _PRIVATE_ALIASES below, not here.
    ("lib.churn_merge", "lib.triage_dedup", "dedup_triage_lines"),
    ("triage_gc", "lib.triage_gc_core", "plan_gc"),
    ("triage_gc", "lib.triage_gc_core", "apply_gc"),
    ("triage_gc", "lib.triage_gc_core", "is_machine_churn"),
    ("triage_gc", "lib.triage_gc_core", "MACHINE_REASONS"),
    ("triage_gc", "lib.triage_gc_core", "MACHINE_DISMISSERS"),
    ("triage_gc", "lib.triage_gc_publish", "commit_compaction"),
    ("triage_gc", "lib.triage_gc_publish", "describe_post_gc_divergence"),
    ("lib.sweep_drift", "lib.sweep_drift_restore", "restore_tracked_log"),
]

#: Private names history depends on: ``reconcile_triage`` re-exports the three guards
#: under their old underscore spellings, and its tests patch/call them that way.
#: ``sweep_outbox`` re-exports the same two it uses (no ``is_detached`` — see its
#: module docstring for the asymmetry) since iterate-2026-08-07-shared-op-predicates.
_PRIVATE_ALIASES = [
    ("lib.reconcile_triage", "_op_in_progress", "lib.main_tree_guards", "op_in_progress"),
    ("lib.reconcile_triage", "_is_detached", "lib.main_tree_guards", "is_detached"),
    ("lib.reconcile_triage", "_has_staged_changes", "lib.main_tree_guards", "has_staged_changes"),
    ("lib.reconcile_triage", "_atomic_write", "lib.reconcile_rollback", "atomic_write_verbatim"),
    ("lib.reconcile_triage", "_rollback_failed_commit", "lib.reconcile_rollback",
     "rollback_failed_commit"),
    ("lib.sweep_outbox", "_op_in_progress", "lib.main_tree_guards", "op_in_progress"),
    ("lib.sweep_outbox", "_has_staged_changes", "lib.main_tree_guards", "has_staged_changes"),
]


def test_every_moved_name_resolves_from_its_old_and_new_home() -> None:
    import importlib
    for old_mod, new_mod, attr in _REEXPORTS:
        old = getattr(importlib.import_module(old_mod), attr)
        new = getattr(importlib.import_module(new_mod), attr)
        assert old is new, f"{old_mod}.{attr} is no longer the same object as {new_mod}.{attr}"


def test_private_aliases_still_point_at_the_shared_implementation() -> None:
    import importlib
    for old_mod, old_attr, new_mod, new_attr in _PRIVATE_ALIASES:
        old = getattr(importlib.import_module(old_mod), old_attr)
        new = getattr(importlib.import_module(new_mod), new_attr)
        assert old is new, f"{old_mod}.{old_attr} drifted from {new_mod}.{new_attr}"


def test_each_module_imports_cleanly_in_a_fresh_interpreter() -> None:
    """Same-process imports pass on whatever ``sys.modules`` already holds, so a
    circular import introduced by the extraction can hide behind an earlier import.
    Each module is therefore imported ALONE in an isolated subprocess (``-I``).
    """
    # Derived from BOTH tables plus the unchanged callers, so a row removed from
    # _REEXPORTS cannot silently drop a module out of this sweep.
    modules = sorted({new for _, new, _ in _REEXPORTS} |
                     {new for _, _, new, _ in _PRIVATE_ALIASES} |
                     {"lib.churn_merge", "lib.reconcile_triage", "lib.sweep_drift",
                      "lib.sweep_outbox", "lib.sweep_quarantine", "lib.sweep_result",
                      "lib.triage_gc_core", "lib.triage_gc_publish",
                      "lib.sweep_drift_restore", "triage_gc"})
    assert len(modules) >= 12, modules
    scripts = str(_SHARED / "scripts")
    tools = str(_SHARED / "scripts" / "tools")
    for mod in modules:
        code = f"import sys; sys.path[:0] = [{scripts!r}, {tools!r}]; import {mod}"
        proc = subprocess.run([sys.executable, "-I", "-c", code],
                              capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, f"{mod} failed to import alone:\n{proc.stderr}"
