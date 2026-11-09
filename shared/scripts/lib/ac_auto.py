"""``auto`` mode of the pre-build AC decision: Shipwright takes its own pick without asking, and says so afterwards.

Nothing here asks anybody. For an item that would have been a question:

* a **changed or removed** existing acceptance criterion passes through as declared;
* a **new** criterion goes under the requirement the model picked (else the best match by shared words);
* when none fits (the model said so, or nothing matches), Shipwright drafts a **new requirement** - title and one sentence -
  and records the criterion under it.

Every such decision is recorded ``mode: "auto-assigned"`` with ``unconfirmed: true`` and a one-line ``note``, and
:func:`unconfirmed_lines` turns the notes into the short list "assignments made without you" printed at the end of a run or
campaign - changed and removed criteria first, because they alter a promise that already existed. Stdlib only.
"""

from __future__ import annotations

from lib.ac_apply import next_fr_id
from lib.ac_question import best_fr, draft_fr

__all__ = ["MODE", "auto_assign", "unconfirmed_lines"]

MODE = "auto-assigned"
_FIRST = ("change", "remove")
_CAP = 160


def _norm(text: object) -> str:
    return " ".join(str(text if text is not None else "").split())


def _cut(text: object) -> str:
    t = _norm(text)
    return t if len(t) <= _CAP else t[:_CAP - 3] + "..."


def auto_assign(it: dict, cat: dict, sugg: dict | None, minted: set[str]) -> tuple[dict, dict]:
    """``(the item with its owner filled in, extra decision fields)`` for one item the operator would have been asked about.

    ``minted`` holds the ids of requirements this run already drafted, so two new ones never share an id; the new id is added to it.
    """
    kind, new, old = it["kind"], _cut(it.get("new_text")), _cut(it.get("old_text"))
    if kind == "change":
        return it, {"note": f'changed {_norm(it.get("ac"))}: "{old}" -> "{new}"'}
    if kind == "remove":
        return it, {"note": f'removed {_norm(it.get("ac"))}: "{old}"'}
    declared = it.get("new_fr") if isinstance(it.get("new_fr"), dict) else None
    fr = "" if declared else best_fr(it, cat, sugg)
    if fr:
        title = _cut((cat.get("titles") or {}).get(fr))
        return {**it, "owner_fr": fr}, {"assigned_fr": fr, "note": f'new criterion "{new}" under {fr} ({title})'}
    if declared:
        fr_new = {"id": _norm(declared.get("id")), "title": _norm(declared.get("title"))}
    else:
        title, summary = draft_fr(it, sugg)
        fr_new = {"id": next_fr_id({**cat, "frs": set(cat.get("frs", ())) | minted}), "title": title, **({"summary": summary} if summary else {})}
    minted.add(fr_new["id"])
    return ({**it, "new_fr": fr_new, "owner_fr": fr_new["id"]},
            {"assigned_fr": fr_new["id"], "created_fr": True, "note": f'new requirement {fr_new["id"]} "{_cut(fr_new["title"])}" for the new criterion "{new}"'})


def unconfirmed_lines(decisions: object) -> list[str]:
    """The short list printed at the end: ``[]`` when nothing was assigned without the operator, else a header and one line per decision, changed/removed first."""
    rows = [d for d in decisions if isinstance(d, dict) and d.get("unconfirmed")] if isinstance(decisions, list) else []
    rows.sort(key=lambda d: 0 if d.get("kind") in _FIRST else 1)  # stable: the order of the declaration otherwise
    if not rows:
        return []
    return ["Assignments made without you (auto-assigned, unconfirmed):",
            *(f'{n}. {"EXISTING CRITERION " if d.get("kind") in _FIRST else ""}{_norm(d.get("note")) or _norm(d.get("ac"))} (decided_by={d.get("decided_by", "auto")}, confirmed={str(d.get("confirmed", False)).lower()}{", requirement created" if d.get("created_fr") else ""})' for n, d in enumerate(rows, 1))]
