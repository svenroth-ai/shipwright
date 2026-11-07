"""The question the operator sees for an AC decision, and what the record keeps about a model's proposal.

Fixed shape, no wording of ours or a model's: why it is asked (the finding), the part, the exact acceptance-criterion wording the
agent wrote, and the name of the requirement from the spec. The options are numbered in order and "Don't understand, need
help" is always last. The text is display only: an answer is bound to the stable content, not to this text (:mod:`lib.ac_hold`).
A model may only propose WHICH requirement a new AC belongs to, one plain line about it and a draft of a new requirement
(:mod:`lib.ac_suggest`); code checks the id and every line, and fetches the name. When the code's own top choices differ
from the model's pick they are offered as extra "add it to ... instead" options.
"""

from __future__ import annotations

from lib.ac_catalog import candidates, fr_text
from lib.ac_context import part_line

__all__ = ["best_fr", "draft_fr", "question_options", "render_question", "suggestion_meta"]

INTRO = ("Shipwright keeps a list of requirements (FRs). Before building, it checks how\n"
         "this change fits that list: it changes a requirement, adds to one, or creates\n"
         "a new one. Please check that Shipwright made the correct selection.")
HELP = "Don't understand, need help."
_NO = "No. (You tell the agent in the chat what you want instead.)"


def _norm(text: object) -> str:
    return " ".join(str(text if text is not None else "").split())


def best_fr(item: dict, cat: dict, sugg: dict | None = None) -> str:
    """The single requirement a new AC is recorded under: the model's pick when it names a real one; ``""`` when the model said none fits;
    else (no model answer) the best match by shared words, else ``""``."""
    if isinstance(sugg, dict) and sugg.get("source") == "model":
        fr = sugg.get("fr_id")
        if isinstance(fr, str) and fr in cat.get("frs", ()):
            return fr
        if sugg.get("none"):  # the model said no requirement fits; an id the catalog lacks is no answer, so the best match by shared words is used
            return ""
    found = candidates(_norm(item.get("new_text")), cat, 1)
    return found[0][0] if found else ""


def draft_fr(item: dict, sugg: dict | None = None) -> tuple[str, str]:
    """``(title, one sentence)`` of the requirement Shipwright drafts for a new AC: the checked model draft, else the criterion's own wording and no sentence."""
    sugg = sugg if isinstance(sugg, dict) else {}
    return _norm(sugg.get("title")) or _norm(item.get("new_text")), _norm(sugg.get("sentence"))


def _alternatives(item: dict, cat: dict, sugg: dict | None, fr: str) -> list[tuple[str, str]]:
    """The code's own top three by shared words, shown only when the model's pick is not the code's first choice."""
    if not (isinstance(sugg, dict) and sugg.get("source") == "model" and fr):
        return []
    found = candidates(_norm(item.get("new_text")), cat, 4)
    return [] if not found or found[0][0] == fr else [c for c in found if c[0] != fr][:3]


def _create_option(item: dict, sugg: dict | None, again: bool) -> tuple[str, dict]:
    """The "create a new requirement" answer; ``again`` asks one more question that shows the drafted requirement (the operator picked it from a list)."""
    title, summary = draft_fr(item, sugg)
    return (("No requirement fits, create a new one." if again else "Yes, create it."),
            {"choice": "new_fr", "text": title, **({"summary": summary} if summary else {}), **({"again": True} if again else {})})


def _plan(item: dict, cat: dict, sugg: dict | None) -> tuple[str, list[str], str, list[tuple[str, dict]]]:
    """``(finding, ac lines, requirement id, [(option text, machine answer)])`` for one item; the help option is appended by the caller."""
    new, old, kind = _norm(item.get("new_text")), _norm(item.get("old_text")), item.get("kind")
    if kind in ("change", "remove"):
        fr = _norm(item.get("ac")).rsplit(".AC", 1)[0]
        if kind == "remove":
            return ("this change removes an acceptance criterion.", [f'Acceptance criterion that no longer holds: "{old}"'], fr,
                    [("Yes, that is intended.", {"choice": "yes"}), ("No, keep it. (The change is then reworked.)", {"choice": "no"})])
        return ("this change changes an existing acceptance criterion.", [f'Acceptance criterion today: "{old}"', f'Acceptance criterion after this change: "{new}"'], fr,
                [("Yes, change it.", {"choice": "yes"}), (_NO, {"choice": "no"})])
    ac = [f'New acceptance criterion: "{new}"']
    if isinstance(item.get("new_fr"), dict):
        return "this change needs a requirement that does not exist yet.", ac, "", [("Yes, create it.", {"choice": "yes"}), (_NO, {"choice": "no"})]
    fr = best_fr(item, cat, sugg)
    if not fr:
        return "this change needs a requirement that does not exist yet.", ac, "", [_create_option(item, sugg, False), (_NO, {"choice": "no"})]
    alts = [(f"Add it to {a} instead: {t}", {"choice": "yes", "text": a}) for a, t in _alternatives(item, cat, sugg, fr)]
    return ("this change adds a new acceptance criterion to an existing requirement.", ac, fr,
            [("Yes, add it there.", {"choice": "yes", "text": fr}), *alts, ("No, wrong requirement. (You tell the agent in the chat which one.)", {"choice": "no"}),
             _create_option(item, sugg, True)])


def _options(item: dict, cat: dict, sugg: dict | None) -> list[tuple[str, dict]]:
    return [*_plan(item, cat, sugg)[3], (HELP, {"choice": "explain"})]


def _requirement_lines(item: dict, cat: dict, sugg: dict | None, fr: str) -> list[str]:
    """The requirement as the operator reads it: its NAME from the spec and, for a model pick, one checked plain line; a new one shows its drafted name and purpose."""
    declared = item.get("new_fr") if isinstance(item.get("new_fr"), dict) else None
    if declared or not fr:
        title, summary = (_norm(declared.get("title")), _norm(declared.get("summary"))) if declared else draft_fr(item, sugg)
        return [f"New requirement: {title}", *([f"Purpose: {summary}"] if summary else [])]
    name = _norm((cat.get("titles") or {}).get(fr) or fr_text(fr, cat))
    line = _norm(sugg.get("line")) if isinstance(sugg, dict) and sugg.get("fr_id") == fr else ""
    return [f'Requirement {fr}: "{name}"' if name else f"Requirement {fr}", *([f"In plain words: {line}"] if line else [])]


def render_question(item: dict, cat: dict | None = None, sugg: dict | None = None, paths: object = None) -> str:
    """The question the operator answers: the finding, the part, the exact acceptance-criterion wording and the requirement's name."""
    cat = cat or {}
    finding, ac_lines, fr, _ = _plan(item, cat, sugg)
    part = part_line([fr] if fr else [], cat, paths)
    lines = "\n".join(f"{n} {text}" for n, (text, _) in enumerate(_options(item, cat, sugg), 1))
    body = "\n".join(x for x in (f"Finding: {finding}", part, *ac_lines, *_requirement_lines(item, cat, sugg, fr)) if x)
    return f"{INTRO}\n\n{body}\n\nDoes this fit?\n{lines}"


def question_options(item: dict, cat: dict | None = None, sugg: dict | None = None, paths: object = None) -> dict:
    """``{"1": {choice, text?}, ...}``: the numbered answers of the question, help last."""
    return {str(n): ans for n, (_, ans) in enumerate(_options(item, cat or {}, sugg), 1)}


def suggestion_meta(sugg: dict | None) -> dict:
    """What the record keeps about a model's proposal: its source and, for a model, the requirement it named, the model id and the prompt sha."""
    if not isinstance(sugg, dict) or "source" not in sugg:
        return {}
    if sugg.get("source") != "model":
        return {"suggestion_source": "fallback", **({"suggestion_reason": sugg["reason"]} if sugg.get("reason") else {})}
    return {"suggestion_source": "model", **{f"suggestion_{k}": sugg[k] for k in ("fr_id", "model", "prompt_sha") if k in sugg}}
