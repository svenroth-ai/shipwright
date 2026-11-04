"""Apply the operator's answer to one pre-build AC item (split from :mod:`lib.ac_decision`, which stays under the file-size cap).

An answer is ``{choice, text}``. ``yes`` / ``other`` name the owning area, ``cross_cutting`` makes the promise its own requirement
(``new_fr`` with ``cross_cutting: true``), ``no`` gives the operator's own wording, ``not_a_promise`` drops the item. ``explain``
("I do not understand this") is not applied here: the caller asks the agent to reword the promise and ask again. Stdlib only.
"""

from __future__ import annotations

import re

__all__ = ["ANSWERS", "FR_ID", "apply_answer", "next_fr_id"]

ANSWERS = ("yes", "no", "other", "not_a_promise", "cross_cutting", "explain")
FR_ID = re.compile(r"^FR-\d+\.\d+$")


def _norm(text: object) -> str:
    return " ".join(str(text if text is not None else "").split())


def next_fr_id(cat: dict) -> str:
    """A provisional id for a new area: the next free number in the highest group of the catalog (the catalog writer may renumber)."""
    pairs = [tuple(int(x) for x in fr[3:].split(".")) for fr in cat.get("frs", ()) if FR_ID.match(fr)]
    major = max((p[0] for p in pairs), default=1)
    return f"FR-{major:02d}.{max((p[1] for p in pairs if p[0] == major), default=0) + 1:02d}"


def apply_answer(it: dict, ans: dict, cat: dict) -> tuple[dict, str]:
    """``(item with the answer applied, error)``; the error is empty when the answer resolves the item."""
    out, choice, text = dict(it), _norm(ans.get("choice")).lower(), _norm(ans.get("text"))
    if choice not in ANSWERS:
        return out, f"answer choice must be one of {', '.join(ANSWERS)}"
    if choice == "no":
        if it["kind"] == "remove" or isinstance(it.get("new_fr"), dict):
            return out, "the operator did not approve this: drop it and rework the change"
        if not text:
            return out, "answer 'no' needs the operator's wording in 'text'"
        out["new_text"] = text  # every other field, the owner included, stays as declared
    elif isinstance(it.get("new_fr"), dict):
        out["owner_fr"] = _norm(it["new_fr"]["id"])
    elif choice == "not_a_promise":
        return out, "the operator says this is not a promise, only how it is built: drop this item (record the work as unchanged or exempt)"
    elif choice == "cross_cutting":
        if it["kind"] != "add":
            return out, "'applies to several areas' is only an answer for a new promise"
        out["new_fr"] = {"id": next_fr_id(cat), "title": text or _norm(it.get("new_text")), "cross_cutting": True}
        out["owner_fr"] = out["new_fr"]["id"]
    elif choice == "other" and it["kind"] == "add":
        if not text:
            return out, "'Somewhere new' needs the name of the new area in 'text'"
        out["new_fr"] = {"id": next_fr_id(cat), "title": text}
        out["owner_fr"] = out["new_fr"]["id"]
    elif it["kind"] == "add":
        owner = text if text in cat["frs"] else next((fr for fr, t in cat.get("titles", {}).items() if t and t.lower() == text.lower()), "")
        if not owner:
            return out, ("answer 'yes' or 'other' for a new AC needs the area of the product it belongs to (named as in the catalog) in 'text'; "
                         "for a new area declare new_fr in the item and ask again")
        out["owner_fr"] = owner
    return out, ""
