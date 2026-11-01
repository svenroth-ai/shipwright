"""The pre-build acceptance-criterion (AC) decision: ask the operator or decide alone, deterministically.

Before an iterate builds, the agent records what it promises: the exact catalog AC text (old and new for a
change), the id of the AC a fix restores, or an exemption. Code decides everything it can:

* **The ask rule** (the only one): ask the operator when (1) an existing AC is changed or removed, (2) no single
  FR in the catalog owns a new AC, or (3) a new AC declares a new area of the product (``new_fr``). Everything
  else is decided alone and shown in the PR body.
* **Wording** is a hard validation, not a question (:mod:`lib.ac_wording`); it covers every text field.
* **The catalog** is read from the base ref (``git show <base>:<spec>``), never from the working tree, so an
  agent cannot make a claim true by editing the catalog first.
* **Exemption** is only a claim before the build (the diff is empty then). If a diff exists it must show nothing
  observable (:mod:`lib.ac_surface`); the real check is F11, against the committed diff, as a warning.
* **A restore** must name an AC that exists in the catalog; otherwise it is a catalog gap (kind add).
* **Answers** come through ``ac_decision.py answer``, bound to the sha256 of the run's stable id + item index +
  question text and signed (HMAC, per-user key: a guard against accident and casual forgery, NOT authentication).
  Every decision records ``answered_via`` (none, inline, operator, self-reported - both of the last two self-reported
  unless the signature verifies). An unattended run (:func:`lib.ac_hold.is_unattended`) refuses anything unsigned.

Presence and shape only: whether the sentence is TRUE is for the reviewers. Stdlib only.
"""

from __future__ import annotations

import json
import re

from lib.ac_catalog import ac_body, area_blurb, candidates, catalog_texts, load_catalog, parse_catalog
from lib.ac_gloss import gloss
from lib.ac_hold import load_key, question_sha, signature_ok
from lib.ac_wording import wording_violations

__all__ = ["KINDS", "ac_body", "candidates", "catalog_texts", "count_decisions", "decide", "frozen_fields", "load_catalog", "parse_catalog", "question_options", "question_sha", "render_question", "stub_lines"]

KINDS = ("add", "change", "remove", "restore", "unchanged", "exempt")
ANSWERS = ("yes", "no", "other", "not_a_promise")
_AC_ID = re.compile(r"^FR-\d+\.\d+\.AC\d+$")
_FR_ID = re.compile(r"^FR-\d+\.\d+$")
_TEXT_FIELDS = ("new_text", "old_text", "owner_fr", "ac", "restores_ac")


def _norm(text: object) -> str:
    return " ".join(str(text if text is not None else "").split())


def render_question(item: dict, cat: dict | None = None) -> str:
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
    layout = _area_options(new, cat or {})
    lines = "\n".join(f"{letter} {text}" for letter, (text, _) in layout.items())
    return f"This change adds a new promise: {new}{gloss(new)}. Where does it belong?\n{lines}"


def _area_options(new: str, cat: dict) -> dict[str, tuple[str, dict]]:
    """The pick list of a no-owner question: ``{letter: (printed text, machine answer)}``; area ids stay in the machine answer only."""
    out: dict[str, tuple[str, dict]] = {}
    for fr, title in candidates(new, cat):
        blurb = area_blurb(fr, cat)
        out[chr(ord("A") + len(out))] = (f"{title or 'An existing area'}" + (f": {blurb}" if blurb else ""), {"choice": "yes", "text": fr})
    if not out:
        out["A"] = ("An area that already exists (tell us which).", {"choice": "yes"})
    for text, ans in (("Somewhere new (tell us the name).", {"choice": "other"}), ("It is not a promise, only how it is built.", {"choice": "not_a_promise"}),
                      ("Not wanted: <your wording>", {"choice": "no"})):
        out[chr(ord("A") + len(out))] = (text, ans)
    return out


def question_options(item: dict, cat: dict | None = None) -> dict:
    """``{letter: {choice, text?}}`` for the pick list of a no-owner question (empty for every other question)."""
    if item.get("kind") != "add" or isinstance(item.get("new_fr"), dict):
        return {}
    return {k: v for k, (_, v) in _area_options(_norm(item.get("new_text")), cat or {}).items()}


def count_decisions(decisions: object) -> dict:
    """The one producer of the decision counts: ``{total, auto, asked, exempt, restore, unchanged, exempt_share, restore_share}``.

    Priority per decision: exempt, restore, unchanged, asked, auto - every decision lands in exactly one bucket. Malformed input counts as nothing.
    There is no aggregator across runs yet: a report over many runs is made by a one-off script over the per-run records.
    """
    rows = [d for d in decisions if isinstance(d, dict)] if isinstance(decisions, list) else []
    n = {k: sum(1 for d in rows if d.get("kind") == k) for k in ("exempt", "restore", "unchanged")}
    asked = sum(1 for d in rows if d.get("kind") not in n and d.get("mode") == "asked")
    total = len(rows)
    return {"total": total, "auto": total - sum(n.values()) - asked, "asked": asked, **n,
            "exempt_share": round(n["exempt"] / total, 2) if total else 0.0, "restore_share": round(n["restore"] / total, 2) if total else 0.0}


def _check(it: dict, n: int, cat: dict, surface: dict | None, idents: set[str] | None) -> list[str]:
    tag, kind = f"item {n}", it.get("kind")
    if kind not in KINDS:
        return [f"{tag}: kind must be one of {', '.join(KINDS)}"]
    bad_type = [k for k in _TEXT_FIELDS if it.get(k) is not None and not isinstance(it[k], str)]
    if bad_type:
        return [f"{tag}: {', '.join(bad_type)} must be text"]
    errs: list[str] = []
    key = "restores_ac" if kind == "restore" else "ac"
    ac = _norm(it.get(key))
    if kind in ("change", "remove", "restore", "unchanged"):
        if not _AC_ID.match(ac):
            errs.append(f"{tag}: {kind} needs an AC id like FR-01.03.AC05 in '{key}'")
        elif ac not in cat["acs"]:
            errs.append(f"{tag}: {ac} is not in the catalog - " + ("a restore must name an AC that exists; if none does it is a catalog gap, so add the AC instead (kind add)" if kind in ("restore", "unchanged") else "a change or removal needs an existing AC"))
        elif kind in ("change", "remove") and ac_body(it.get("old_text")) != ac_body(cat["acs"][ac]):
            errs.append(f"{tag}: old_text is not the current text of {ac} in the catalog - copy it exactly")
    if kind == "add" and ac in cat["acs"]:
        errs.append(f"{tag}: {ac} already exists in the catalog - an add may only claim a new id; reword an existing AC with kind change")
    if kind == "unchanged":
        files = it.get("files")
        if not isinstance(files, list) or not files or not all(isinstance(f, str) and f.strip() for f in files):
            errs.append(f"{tag}: unchanged needs 'files', the non-empty list of observable files this work changes while the promise stays")
    if kind in ("add", "change") and not _norm(it.get("new_text")):
        errs.append(f"{tag}: {kind} needs the exact AC text in 'new_text'")
    if kind in ("add", "change", "restore") and _norm(it.get("new_text")):
        bad = wording_violations(it["new_text"], idents)
        if bad:
            errs.append(f"{tag}: the AC text must read as an outcome, not as how it is built - remove " + "; ".join(bad[:6]) + " and say what a user or operator can rely on")
    fr = it.get("new_fr")
    if fr is not None:
        title = _norm(fr.get("title")) if isinstance(fr, dict) else ""
        if kind != "add" or not isinstance(fr, dict) or not _FR_ID.match(_norm(fr.get("id"))) or not title or (it.get("owner_fr") and _norm(it["owner_fr"]) != _norm(fr.get("id"))):
            errs.append(f"{tag}: new_fr is for an add without owner_fr: {{id: FR-01.30, title: one sentence}}")
        elif _norm(fr["id"]) in cat["frs"]:
            errs.append(f"{tag}: {_norm(fr['id'])} already exists in the catalog - use it as owner_fr")
        elif wording_violations(title, idents):
            errs.append(f"{tag}: the new area's title must read as an outcome, not as how it is built")
    if kind == "exempt" and surface and surface.get("observable"):
        errs.append(f"{tag}: the diff changes observable behaviour ({', '.join(surface['files'][:5])}) - an exemption does not apply; name the AC it restores or add one")
    return errs


def _row(it: dict, cat: dict) -> tuple[int, str] | None:
    """The ask rule: (row, why) when the operator must answer, else None (decided alone)."""
    if it["kind"] in ("change", "remove"):
        return 1, "an existing AC is changed or removed"
    if it["kind"] != "add":
        return None
    if isinstance(it.get("new_fr"), dict):
        return 3, "a new area of the product"
    owner = it.get("owner_fr")
    return None if isinstance(owner, str) and owner.strip() in cat["frs"] else (2, "no single FR owns this AC")


def _apply(it: dict, ans: dict, cat: dict) -> tuple[dict, str]:
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
    elif it["kind"] == "add":
        owner = text if text in cat["frs"] else next((fr for fr, t in cat.get("titles", {}).items() if t and t.lower() == text.lower()), "")
        if not owner:
            return out, ("answer 'yes' or 'other' for a new AC needs the area of the product it belongs to (named as in the catalog) in 'text'; "
                         "for a new area declare new_fr in the item and ask again")
        out["owner_fr"] = owner
    return out, ""


def _decision(it: dict, mode: str, answer: str, via: str) -> dict:
    if it["kind"] == "exempt":
        return {"ac": "none", "mode": mode, "answer": answer, "kind": "exempt", "outcome": "no-observable-change", "answered_via": via}
    ac = _norm(it.get("restores_ac") if it["kind"] == "restore" else it.get("ac")) or (
        f"{_norm(it.get('owner_fr') or (it.get('new_fr') or {}).get('id'))}.new" if (it.get("owner_fr") or it.get("new_fr")) else "new")
    return {"ac": ac, "mode": mode, "answer": answer, "kind": it["kind"], "answered_via": via}


def _answers_by_item(answers: object) -> dict:
    out: dict = {}
    for a in answers if isinstance(answers, list) else []:
        if isinstance(a, dict):
            out.setdefault(a.get("item"), []).append(a)
    return out


def _ask_one(it: dict, n: int, cat: dict, bind_id: str, unattended: bool, chain: list, inline: object, key: bytes | None):
    """Walk one item through its questions: ``(final item, answered?, answer, via, question or None, error or None)``.

    Normally one question; an add answered 'no, instead' without an owner is asked again about the new wording.
    """
    via, ans, used = "none", None, 0
    while True:
        row = _row(it, cat)
        if row is None:
            return it, used > 0, ans, via, None, None
        text = render_question(it, cat)
        sha = question_sha(text, bind_id, n)
        entry = inline if isinstance(inline, dict) and used == 0 else next((a for a in chain if a.get("question_sha256") == sha), None)
        if entry is None:
            if chain and used == 0:
                return it, False, None, via, None, f"item {n}: the answer was given for a different question (other run, item or wording) - ask again"
            return it, False, None, via, {"item": n, "row": row[0], "why": row[1], "question": text, "question_sha256": sha, "options": question_options(it, cat)}, None
        used += 1
        via = "inline" if entry is inline else ("operator" if signature_ok(key, entry) else "self-reported")
        if unattended and via in ("inline", "self-reported"):
            return it, False, None, via, None, f"item {n}: an unattended run takes answers only from the operator channel (ac_decision.py answer run by the operator, signed)"
        it, err = _apply(it, entry, cat)
        ans = entry
        if err:
            return it, False, None, via, None, f"item {n}: {err}"
        if not (_norm(entry.get("choice")).lower() == "no" and _row(it, cat) is not None and it["kind"] == "add"):
            return it, True, ans, via, None, None


def decide(items: object, catalog: dict, unattended: bool = False, surface: dict | None = None, identifiers: set[str] | None = None,
           answers: object = None, bind_id: str = "") -> dict:
    """Decide every item. ``status``: ``ok`` (all decided), ``ask`` (questions for the operator), ``invalid`` (``errors``), ``skipped`` (catalog unreadable)."""
    base = {"unattended": unattended}
    if catalog.get("unparsed"):
        return {**base, "status": "skipped", "note": "the requirement catalog has text but no FR heading this tool can read; the pre-build AC decision is skipped, nothing is asked or refused"}
    if not isinstance(items, list) or not items:
        return {**base, "status": "invalid", "errors": ["items must be a non-empty list: every iterate records an AC, an exemption or a restore"]}
    given = _answers_by_item(answers)
    key = load_key(False) if given else None
    errors: list[str] = []
    resolved, decisions, questions = [], [], []
    for n, raw in enumerate(items):
        it = {k: v for k, v in raw.items() if k != "answer"} if isinstance(raw, dict) else {}
        inline = raw.get("answer") if isinstance(raw, dict) else None
        if inline is not None and unattended:
            errors.append(f"item {n}: an inline answer is refused in an unattended run - the operator answers through the operator channel (ac_decision.py answer)")
            continue
        errs = _check(it, n, catalog, surface, identifiers)
        if errs:
            errors += errs
            continue
        if _row(it, catalog) is None:
            resolved.append(it)
            decisions.append(_decision(it, "auto", "auto", "none"))
            continue
        it, done, ans, via, question, err = _ask_one(it, n, catalog, bind_id, unattended, given.get(n, []), inline, key)
        if err:
            errors.append(err)
        elif question:
            questions.append(question)
        elif done:
            errs = _check(it, n, catalog, surface, identifiers)
            if errs:
                errors += errs
                continue
            resolved.append(it)
            decisions.append(_decision(it, "asked", _norm(ans.get("choice")).lower(), via))
    if errors:
        return {**base, "status": "invalid", "errors": errors}
    out = {**base, "resolved_items": resolved, "ac_decisions": decisions, "counts": count_decisions(decisions)}
    return {**out, "status": "ask", "questions": questions} if questions else {**out, "status": "ok"}


def frozen_fields(it: dict) -> dict:
    keys = ("kind", "ac", "restores_ac", "owner_fr", "old_text", "new_text")
    out = {k: _norm(it.get(k)) for k in keys if _norm(it.get(k))}
    if isinstance(it.get("files"), list):
        out["files"] = sorted(str(f).strip() for f in it["files"] if str(f).strip())
    if isinstance(it.get("new_fr"), dict):
        out["new_fr"] = {"id": _norm(it["new_fr"].get("id")), "title": _norm(it["new_fr"].get("title"))}
    return out


def stub_lines(result: dict) -> list[str]:
    """Readable copy for the plan stub (the authoritative freeze is the append-only record, :mod:`lib.ac_record`)."""
    return [*(f"AC item: {json.dumps(frozen_fields(i), ensure_ascii=False, sort_keys=True)}" for i in result["resolved_items"]),
            "AC decisions: " + json.dumps(result["ac_decisions"], ensure_ascii=False)]
