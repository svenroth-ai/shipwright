"""The question text and pick list the operator sees for an AC decision, and what the record keeps about a model's display suggestion.

The agent's ORIGINAL promise is always shown first, word for word; a model's plain wording (:mod:`lib.ac_suggest`) is only a gloss
under it ("In plain words: ..."). The text is display only: an answer is bound to the stable content, not to this text (:mod:`lib.ac_hold`).
"""

from __future__ import annotations

from lib.ac_catalog import area_blurb, candidates
from lib.ac_gloss import gloss

__all__ = ["question_options", "render_question", "suggestion_meta"]


def _norm(text: object) -> str:
    return " ".join(str(text if text is not None else "").split())


def render_question(item: dict, cat: dict | None = None, sugg: dict | None = None) -> str:
    """The plain-language question the operator answers (what the product promises, not how it is built)."""
    new, old = _norm(item.get("new_text")), _norm(item.get("old_text"))
    if item.get("kind") == "remove":
        return (f"This change removes a promise. Until now this held: {old}. After this change it no longer holds.\n"
                "1 Yes, that is intended.\n2 No, keep the promise (the change is then reworked).")
    if item.get("kind") == "change":
        return (f"This change alters a promise the product makes. Until now: {old}. After this change: {new}. Should it hold like this?\n"
                "1 Yes, change it.\n2 No, instead: <your wording>")
    if isinstance(item.get("new_fr"), dict):
        return (f"This is a new area of the product: {_norm(item['new_fr'].get('title'))}. It would promise: {new}. Is it OK to add this area?\n"
                "1 Yes, add it.\n2 No, do not add it (the change is then reworked).")
    layout = _area_options(new, cat or {}, sugg)
    lines = "\n".join(f"{letter} {text}" for letter, (text, _) in layout.items())
    head = (f"This change adds a new promise: {new.rstrip('.')}. In plain words: {_norm(sugg['plain_promise']).rstrip('.')}." if _is_model(sugg)
            else f"This change adds a new promise: {new}{gloss(new)}.")  # the agent's own words come first: display = frozen text
    return f"{head} Where does it belong?\n{lines}"


def _is_model(sugg: dict | None) -> bool:
    """True for a validated model suggestion (:mod:`lib.ac_suggest`); anything else uses the deterministic wording."""
    return isinstance(sugg, dict) and sugg.get("source") == "model" and isinstance(sugg.get("plain_promise"), str) and isinstance(sugg.get("areas"), list)


def _area_options(new: str, cat: dict, sugg: dict | None = None) -> dict[str, tuple[str, dict]]:
    """The pick list of a no-owner question: ``{letter: (printed text, machine answer)}``; area ids stay in the machine answer only."""
    out: dict[str, tuple[str, dict]] = {}
    rows = ([(a["fr_id"], cat.get("titles", {}).get(a["fr_id"], ""), _norm(a["plain_description"])) for a in sugg["areas"]] if _is_model(sugg) and sugg["areas"]
            else [(fr, title, area_blurb(fr, cat)) for fr, title in candidates(new, cat)])
    for fr, title, blurb in rows:
        out[chr(ord("A") + len(out))] = (f"{title or 'An existing area'}" + (f": {blurb}" if blurb else ""), {"choice": "yes", "text": fr})
    if not out:
        out["A"] = ("An area that already exists (tell us which).", {"choice": "yes"})
    for text, ans in (("Somewhere new (tell us the name).", {"choice": "other"}), ("It is not a promise, only how it is built.", {"choice": "not_a_promise"}),
                      ("Not wanted: <your wording>", {"choice": "no"})):
        out[chr(ord("A") + len(out))] = (text, ans)
    return out


def question_options(item: dict, cat: dict | None = None, sugg: dict | None = None) -> dict:
    """``{letter: {choice, text?}}`` for the pick list of a no-owner question (empty for every other question)."""
    if item.get("kind") != "add" or isinstance(item.get("new_fr"), dict):
        return {}
    return {k: v for k, (_, v) in _area_options(_norm(item.get("new_text")), cat or {}, sugg).items()}


def suggestion_meta(sugg: dict | None) -> dict:
    """What the record keeps about a display suggestion: its source and, for a model, both wordings, the model id and the prompt sha."""
    if not isinstance(sugg, dict) or "source" not in sugg:
        return {}
    if not _is_model(sugg):
        return {"suggestion_source": "fallback", **({"suggestion_reason": sugg["reason"]} if sugg.get("reason") else {})}
    return {"suggestion_source": "model", **{f"suggestion_{k}": sugg[k] for k in ("original_promise", "plain_promise", "model", "prompt_sha") if k in sugg}}
