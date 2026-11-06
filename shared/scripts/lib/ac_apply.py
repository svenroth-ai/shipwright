"""Apply the operator's answer to one pre-build AC item (split from :mod:`lib.ac_decision`, which stays under the file-size cap).

An answer is ``{choice, text}``: ``yes`` approves the item (for a new AC, ``text`` is the requirement it is recorded under),
``new_fr`` records it under a new requirement, ``no`` declines it (the operator tells the agent in the chat what they want instead).
``explain`` ("Don't understand, need help") is not applied here: the caller asks the agent to explain and ask again. Stdlib only.
"""

from __future__ import annotations

import re

__all__ = ["ANSWERS", "FR_ID", "apply_answer", "next_fr_id"]

ANSWERS = ("yes", "no", "new_fr", "explain")
FR_ID = re.compile(r"^FR-\d+\.\d+$")


def _norm(text: object) -> str:
    return " ".join(str(text if text is not None else "").split())


def next_fr_id(cat: dict) -> str:
    """A provisional id for a new requirement: the next free number in the highest group of the catalog (the catalog writer may renumber)."""
    pairs = [tuple(int(x) for x in fr[3:].split(".")) for fr in cat.get("frs", ()) if FR_ID.match(fr)]
    major = max((p[0] for p in pairs), default=1)
    return f"FR-{major:02d}.{max((p[1] for p in pairs if p[0] == major), default=0) + 1:02d}"


def apply_answer(it: dict, ans: dict, cat: dict) -> tuple[dict, str]:
    """``(item with the answer applied, error)``; the error is empty when the answer resolves the item."""
    out, choice, text = dict(it), _norm(ans.get("choice")).lower(), _norm(ans.get("text"))
    if choice not in ANSWERS:
        return out, f"answer choice must be one of {', '.join(ANSWERS)}"
    if choice == "no":
        return out, ("the operator said no: ask them in the chat what they want instead (other wording, or another requirement), then change the declaration and run again; "
                     "a unit in a hands-off run stops here")
    if isinstance(it.get("new_fr"), dict):
        out["owner_fr"] = _norm(it["new_fr"]["id"])
    elif it["kind"] == "add" and choice == "new_fr":
        out["new_fr"] = {"id": next_fr_id(cat), "title": _norm(it.get("new_text"))}
        out["owner_fr"] = out["new_fr"]["id"]
    elif it["kind"] == "add":
        owner = text if text in cat["frs"] else ""
        if not owner:
            return out, "answer 'yes' for a new AC needs the requirement it belongs to (as in the catalog) in 'text'"
        out["owner_fr"] = owner
    return out, ""
