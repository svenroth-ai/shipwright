"""The question text and pick list the operator sees for an AC decision, and what the record keeps about a model's display suggestion.

The agent's ORIGINAL promise is always shown first, word for word. Under it, only when code finds it meaningfully different, a model's
plain wording ("In plain words: ..."); then two context lines computed by code (Affects, Already in the catalog). The text is display
only: an answer is bound to the stable content, not to this text (:mod:`lib.ac_hold`). Every question offers "I do not understand this".
"""

from __future__ import annotations

from lib.ac_catalog import area_blurb, candidates
from lib.ac_context import affects_line, differs, is_cross_cutting, related_titles
from lib.ac_gloss import gloss

__all__ = ["question_options", "render_question", "suggestion_meta"]

CROSS = "Applies to several areas: make it its own requirement."
EXPLAIN = "I do not understand this, please explain."


def _norm(text: object) -> str:
    return " ".join(str(text if text is not None else "").split())


def _context(item: dict, cat: dict, paths: object) -> str:
    """The code-computed lines under the promise: where the change reaches and what the catalog already says (each omitted when unknown)."""
    lines = [affects_line(paths)]
    related = related_titles(_norm(item.get("new_text")), cat) if item.get("kind") == "add" else []
    lines.append("Already in the catalog: " + "; ".join(related) + "." if related else "")
    return "".join(f"\n{ln}" for ln in lines if ln)


def render_question(item: dict, cat: dict | None = None, sugg: dict | None = None, paths: object = None) -> str:
    """The plain-language question the operator answers (what the product promises, not how it is built)."""
    new, old, cat = _norm(item.get("new_text")), _norm(item.get("old_text")), cat or {}
    ctx = _context(item, cat, paths)
    if item.get("kind") == "remove":
        return (f"This change removes a promise. Until now this held: {old}{gloss(old)}. After this change it no longer holds.{ctx}\n"
                f"1 Yes, that is intended.\n2 No, keep the promise (the change is then reworked).\n3 {EXPLAIN}")
    if item.get("kind") == "change":
        return (f"This change alters a promise the product makes. Until now: {old}. After this change: {new}{gloss(f'{old} {new}')}. Should it hold like this?{ctx}\n"
                f"1 Yes, change it.\n2 No, instead: <your wording>\n3 {EXPLAIN}")
    if isinstance(item.get("new_fr"), dict):
        return (f"This is a new area of the product: {_norm(item['new_fr'].get('title'))}. It would promise: {new}. Is it OK to add this area?{ctx}\n"
                f"1 Yes, add it.\n2 No, do not add it (the change is then reworked).\n3 {EXPLAIN}")
    lines = "\n".join(f"{letter} {text}" for letter, (text, _) in _area_options(new, cat, sugg, paths).items())
    plain = _norm(sugg["plain_promise"]).rstrip(".") if _is_model(sugg) else ""
    shown = plain if plain and differs(new, plain) else ""  # a gloss that only swaps a word or two says nothing new: the glossary explains the jargon instead
    head = f"This change adds a new promise: {new.rstrip('.')}{'' if shown else gloss(new)}."  # the agent's own words come first
    if shown:
        head += f"\nIn plain words: {shown}."
    return f"{head}{ctx}\nWhich requirement would this promise belong to?\n{lines}"


def _is_model(sugg: dict | None) -> bool:
    """True for a validated model suggestion (:mod:`lib.ac_suggest`); anything else uses the deterministic wording."""
    return isinstance(sugg, dict) and sugg.get("source") == "model" and isinstance(sugg.get("plain_promise"), str) and isinstance(sugg.get("areas"), list)


def _area_options(new: str, cat: dict, sugg: dict | None = None, paths: object = None) -> dict[str, tuple[str, dict]]:
    """The pick list of a no-owner question: ``{letter: (printed text, machine answer)}``; area ids stay in the machine answer only."""
    out: dict[str, tuple[str, dict]] = {}
    rows = ([(a["fr_id"], cat.get("titles", {}).get(a["fr_id"], ""), _norm(a["plain_description"])) for a in sugg["areas"]] if _is_model(sugg) and sugg["areas"]
            else [(fr, title, area_blurb(fr, cat)) for fr, title in candidates(new, cat)])

    def add(text: str, answer: dict) -> None:
        out[chr(ord("A") + len(out))] = (text, answer)
    if is_cross_cutting(paths) or not rows:  # several plugins, or no single owning area: its own requirement comes first
        add(CROSS, {"choice": "cross_cutting"})
    for fr, title, blurb in rows:
        add(f"{title or 'An existing area'}" + (f": {blurb}" if blurb else ""), {"choice": "yes", "text": fr})
    if not rows:
        add("An area that already exists (tell us which).", {"choice": "yes"})
    for text, ans in (("Somewhere new (tell us the name).", {"choice": "other"}), ("It is not a promise, only how it is built.", {"choice": "not_a_promise"}),
                      ("Not wanted: <your wording>", {"choice": "no"}), (EXPLAIN, {"choice": "explain"})):
        add(text, ans)
    return out


def question_options(item: dict, cat: dict | None = None, sugg: dict | None = None, paths: object = None) -> dict:
    """``{letter: {choice, text?}}`` for the pick list of a no-owner question (empty for every other question)."""
    if item.get("kind") != "add" or isinstance(item.get("new_fr"), dict):
        return {}
    return {k: v for k, (_, v) in _area_options(_norm(item.get("new_text")), cat or {}, sugg, paths).items()}


def suggestion_meta(sugg: dict | None) -> dict:
    """What the record keeps about a display suggestion: its source and, for a model, both wordings, the model id and the prompt sha."""
    if not isinstance(sugg, dict) or "source" not in sugg:
        return {}
    if not _is_model(sugg):
        return {"suggestion_source": "fallback", **({"suggestion_reason": sugg["reason"]} if sugg.get("reason") else {})}
    return {"suggestion_source": "model", **{f"suggestion_{k}": sugg[k] for k in ("original_promise", "plain_promise", "model", "prompt_sha") if k in sugg}}
