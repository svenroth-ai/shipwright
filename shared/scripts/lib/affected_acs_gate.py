"""``affected_acs`` on a ``work_completed`` event: which acceptance criteria a runtime change touched.

A requirement (FR) says what a capability is for; its acceptance criteria (AC)
say what a person could observe or demand. An iterate that changes runtime
behaviour answers, per AC, one of three things - **changed**, **implemented**,
or **checked and unchanged** (each with one line on why the promise still
holds) - or states that no AC covers the change (``catalog_gap: true`` plus the
nearest FR in ``catalog_gap_fr``). The answer rides on the event as::

    "affected_acs": [{"ac": "FR-01.03.AC05", "disposition": "checked-unchanged",
                      "why": "the new field is additive; the output is the same"}]
    # or, when no AC covers the change:
    "catalog_gap": true, "catalog_gap_fr": "FR-01.11"

This module judges **presence only**. It never reads the sentence, the ids or
the disposition: whether the declaration is true is a question for a reviewer,
and a content gate here would turn the field into a ritual to satisfy. A
declaration is *present* when ``affected_acs`` is a non-empty list, or
``catalog_gap`` is true next to a non-empty ``catalog_gap_fr``.

Scope: a feature/change/bug iterate whose diff touches a runtime path -
``plugins/**`` or ``shared/**`` except tests and docs. Everything else (docs,
tests, planning records, compliance output) is not asked.
"""

from __future__ import annotations

from typing import Iterable

from lib.spec_impact_gate import SPEC_IMPACT_INTENTS

__all__ = ["declaration_present", "is_runtime_path", "is_scoped_intent", "requires_declaration", "touches_runtime"]

_RUNTIME_ROOTS = ("plugins/", "shared/")
#: A directory with one of these names holds tests or docs, never runtime.
_NON_RUNTIME_DIRS = frozenset({"tests", "docs", "__pycache__"})


def is_runtime_path(path: object) -> bool:
    """True for a file under ``plugins/`` or ``shared/`` that is not a test or a doc."""
    if not isinstance(path, str):
        return False
    norm = path.replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    if not norm.startswith(_RUNTIME_ROOTS):
        return False
    # Directory names only: runtime modules are named test_*.py (shipwright-test, test_hygiene.py) and the
    # shipwright-test skill lives in a folder called ``test``, so neither a filename nor a bare "test" dir counts.
    return not any(part in _NON_RUNTIME_DIRS for part in norm.split("/")[:-1])


def touches_runtime(paths: Iterable[object]) -> bool:
    """True when any of ``paths`` is a runtime path."""
    return any(is_runtime_path(p) for p in paths or ())


def declaration_present(event: object) -> bool:
    """Presence of the declaration (see the module docstring); the content is never read."""
    if not isinstance(event, dict):
        return False
    acs = event.get("affected_acs")
    if isinstance(acs, list) and len(acs) > 0:
        return True
    gap_fr = event.get("catalog_gap_fr")
    return event.get("catalog_gap") is True and isinstance(gap_fr, str) and bool(gap_fr.strip())


def is_scoped_intent(event: object) -> bool:
    """True for an event whose intent is feature, change or bug."""
    return isinstance(event, dict) and str(event.get("intent") or "").strip().lower() in SPEC_IMPACT_INTENTS


def requires_declaration(event: object, changed_paths: Iterable[object]) -> bool:
    """True for a feature/change/bug iterate event whose diff touches a runtime path."""
    return is_scoped_intent(event) and touches_runtime(changed_paths)
