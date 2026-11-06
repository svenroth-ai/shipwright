"""The question the operator sees for an AC decision, and what the record keeps about a model's proposal.

Fixed shape, no wording of ours or a model's: why it is asked (the finding), the part, the exact acceptance-criterion wording the
agent wrote, and the exact text of the requirement from the spec. The options are numbered in order and "Don't understand, need
help" is always last. The text is display only: an answer is bound to the stable content, not to this text (:mod:`lib.ac_hold`).
A model may only propose WHICH requirement a new AC belongs to (:mod:`lib.ac_suggest`); code checks the id and fetches its text.
"""

from __future__ import annotations

from lib.ac_catalog import candidates, fr_text
from lib.ac_context import part_line

__all__ = ["best_fr", "question_options", "render_question", "suggestion_meta"]

INTRO = ("Shipwright keeps a list of requirements (FRs). Before building, it checks how\n"
         "this change fits that list: it changes a requirement, adds to one, or creates\n"
         "a new one. Please check that Shipwright made the correct selection.")
HELP = "Don't understand, need help."
_NO = "No. (You tell the agent in the chat what you want instead.)"


def _norm(text: object) -> str:
    return " ".join(str(text if text is not None else "").split())


def best_fr(item: dict, cat: dict, sugg: dict | None = None) -> str:
    """The single requirement a new AC is recorded under: the model's proposal when it names a real one, else the best match by shared words, else ``""``."""
    fr = sugg.get("fr_id") if isinstance(sugg, dict) else None
    if isinstance(fr, str) and fr in cat.get("frs", ()):
        return fr
    found = candidates(_norm(item.get("new_text")), cat, 1)
    return found[0][0] if found else ""


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
    declared = item.get("new_fr")
    if isinstance(declared, dict):
        return "this change needs a requirement that does not exist yet.", ac, "", [("Yes, create it.", {"choice": "yes"}), (_NO, {"choice": "no"})]
    fr = best_fr(item, cat, sugg)
    if not fr:
        return "this change needs a requirement that does not exist yet.", ac, "", [("Yes, create it.", {"choice": "new_fr"}), (_NO, {"choice": "no"})]
    return ("this change adds a new acceptance criterion to an existing requirement.", ac, fr,
            [("Yes, add it there.", {"choice": "yes", "text": fr}), ("No, wrong requirement. (You tell the agent in the chat which one.)", {"choice": "no"}),
             ("No requirement fits, create a new one.", {"choice": "new_fr"})])


def _options(item: dict, cat: dict, sugg: dict | None) -> list[tuple[str, dict]]:
    return [*_plan(item, cat, sugg)[3], (HELP, {"choice": "explain"})]


def render_question(item: dict, cat: dict | None = None, sugg: dict | None = None, paths: object = None) -> str:
    """The question the operator answers: the finding, the part, the exact acceptance-criterion wording and the exact requirement text."""
    cat = cat or {}
    finding, ac_lines, fr, _ = _plan(item, cat, sugg)
    declared = item.get("new_fr") if isinstance(item.get("new_fr"), dict) else None
    req = f'Requirement {_norm(declared["id"])}: "{_norm(declared.get("title"))}"' if declared else (f'Requirement {fr}: "{fr_text(fr, cat)}"' if fr and fr_text(fr, cat) else "")
    part = part_line([fr] if fr else [], cat, paths)
    lines = "\n".join(f"{n} {text}" for n, (text, _) in enumerate(_options(item, cat, sugg), 1))
    body = "\n".join(x for x in (f"Finding: {finding}", part, *ac_lines, req) if x)
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
