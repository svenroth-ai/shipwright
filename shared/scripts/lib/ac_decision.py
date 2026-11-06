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
  kind + promise + the numbered options (never the rendered text) and signed (HMAC, per-user key: a guard against accident and casual forgery, NOT authentication).
  Every decision records ``answered_via`` (none, inline, operator, self-reported - both of the last two self-reported
  unless the signature verifies). An unattended run (:func:`lib.ac_hold.is_unattended`) refuses anything unsigned.

Presence and shape only: whether the sentence is TRUE is for the reviewers. Stdlib only.
"""

from __future__ import annotations

import json
import re

from lib.ac_apply import FR_ID as _FR_ID, apply_answer as _apply
from lib.ac_catalog import ac_body, candidates, catalog_texts, load_catalog, parse_catalog
from lib.ac_hold import load_key, question_sha, signature_ok
from lib.ac_question import question_options, render_question, suggestion_meta
from lib.ac_wording import wording_violations

__all__ = ["KINDS", "ac_body", "candidates", "catalog_texts", "count_decisions", "decide", "frozen_fields", "load_catalog", "parse_catalog", "question_options", "question_sha", "render_question", "stub_lines"]

KINDS = ("add", "change", "remove", "restore", "unchanged", "exempt")
_AC_ID = re.compile(r"^FR-\d+\.\d+\.AC\d+$")
_TEXT_FIELDS = ("new_text", "old_text", "owner_fr", "ac", "restores_ac")


def _norm(text: object) -> str:
    return " ".join(str(text if text is not None else "").split())


def count_decisions(decisions: object) -> dict:
    """The one producer of the decision counts: ``{total, auto, asked, exempt, restore, unchanged, answered_inline, exempt_share, restore_share}``.

    ``answered_inline`` counts asked decisions answered inline in an attended run (one count line in the PR body, not a warning).

    Priority per decision: exempt, restore, unchanged, asked, auto - every decision lands in exactly one bucket. Malformed input counts as nothing.
    There is no aggregator across runs yet: a report over many runs is made by a one-off script over the per-run records.
    """
    rows = [d for d in decisions if isinstance(d, dict)] if isinstance(decisions, list) else []
    n = {k: sum(1 for d in rows if d.get("kind") == k) for k in ("exempt", "restore", "unchanged")}
    asked = sum(1 for d in rows if d.get("kind") not in n and d.get("mode") == "asked")
    total = len(rows)
    inline = sum(1 for d in rows if d.get("mode") == "asked" and d.get("answered_via") == "inline")
    return {"total": total, "auto": total - sum(n.values()) - asked, "asked": asked, **n, "answered_inline": inline,
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


def _identity(it: dict) -> tuple[str, dict]:
    """The stable content an answer is bound to: the kind and the ORIGINAL promise text (old, new, new-area title) - not the rendered question."""
    fr = it.get("new_fr")
    return str(it.get("kind")), {"old": _norm(it.get("old_text")), "new": _norm(it.get("new_text")), "title": _norm(fr.get("title")) if isinstance(fr, dict) else ""}


def _in_options(entry: dict, choice: str, text: str) -> bool:
    """A file answer must be one of the options it was signed with (an empty map = a question with fixed answers)."""
    opts = entry.get("options")
    return not opts or any(isinstance(v, dict) and v.get("choice") == choice and ("text" not in v or v["text"] == text) for v in opts.values())


def _ask_one(it: dict, n: int, cat: dict, bind_id: str, unattended: bool, chain: list, inline: object, key: bytes | None, suggest=None, paths: object = None):
    """Walk one item through its questions: ``(final item, answered?, answer, via, question or None, error or None)``.

    A signed answer is found by its STABLE content (bind id, item index, kind, original promise, the options it carries), so
    a resume neither calls the model nor re-renders from a moved catalog. Normally one question; an add answered 'no, instead'
    without an owner is asked again about the new wording.
    """
    via, ans, used = "none", None, 0
    while True:
        row = _row(it, cat)
        if row is None:
            return it, used > 0, ans, via, None, None
        kind, promise = _identity(it)
        entry = inline if isinstance(inline, dict) and used == 0 else next((a for a in chain if isinstance(a.get("options"), dict)
                                                                              and a.get("question_sha256") == question_sha(bind_id, n, kind, promise, a["options"])), None)
        if entry is None:
            if used == 0 and any(_norm(a.get("choice")).lower() != "explain" for a in chain):  # an old "I do not understand" settles nothing: the reworded promise is asked afresh
                return it, False, None, via, None, f"item {n}: the answer was given for a different question (other run, item, promise or option list) - ask again"
            sg = suggest(n, it) if suggest and used == 0 else None  # a re-asked "no, instead" wording was not seen by the model
            options = question_options(it, cat, sg, paths)
            return it, False, None, via, {"item": n, "row": row[0], "why": row[1], "question": render_question(it, cat, sg, paths), "kind": kind, "promise": promise,
                                          "options": options, "question_sha256": question_sha(bind_id, n, kind, promise, options), **suggestion_meta(sg)}, None
        used += 1
        via = "inline" if entry is inline else ("operator" if signature_ok(key, entry) else "self-reported")
        if unattended and via in ("inline", "self-reported"):
            return it, False, None, via, None, f"item {n}: an unattended run takes answers only from the operator channel (ac_decision.py answer run by the operator, signed)"
        if entry is not inline and not _in_options(entry, _norm(entry.get("choice")).lower(), _norm(entry.get("text"))):
            return it, False, None, via, None, f"item {n}: the answer is not one of the options of the question it was signed for"
        if _norm(entry.get("choice")).lower() == "explain":  # "I do not understand this": the agent rewords the promise and asks again
            return it, False, entry, via, None, None
        it, err = _apply(it, entry, cat)
        ans = entry
        if err:
            return it, False, None, via, None, f"item {n}: {err}"
        if not (_norm(entry.get("choice")).lower() == "no" and _row(it, cat) is not None and it["kind"] == "add"):
            return it, True, ans, via, None, None


def decide(items: object, catalog: dict, unattended: bool = False, surface: dict | None = None, identifiers: set[str] | None = None,
           answers: object = None, bind_id: str = "", suggest=None, paths: object = None) -> dict:
    """Decide every item. ``status``: ``ok`` (all decided), ``ask`` (questions for the operator), ``explain`` (reword and run again), ``invalid`` (``errors``), ``skipped`` (catalog unreadable).

    ``suggest`` is ``(item index, item) -> suggestion | None`` (:func:`lib.ac_suggest.make_suggester`); it is called only when a question must be rendered.
    ``paths`` are the changed paths (the diff); the files the items declare are added. They only feed the question's ``Part:`` line (when the spec names no grouping).
    ``explain``: the operator did not understand an item; ``explain`` lists them, the agent rewords each promise and runs the tool again.
    """
    base = {"unattended": unattended}
    if catalog.get("unparsed"):
        return {**base, "status": "skipped", "note": "the requirement catalog is missing, or a spec has text but no FR heading this tool can read; the pre-build AC decision is skipped, nothing is asked, refused or held"}
    if not isinstance(items, list) or not items:
        return {**base, "status": "invalid", "errors": ["items must be a non-empty list: every iterate records an AC, an exemption or a restore"]}
    given = _answers_by_item(answers)
    try:
        key = load_key(False) if given else None
    except RuntimeError:
        key = None  # an unreadable key verifies nothing: every file answer is then self-reported
    errors: list[str] = []
    resolved, decisions, questions, explain = [], [], [], []
    paths = sorted({str(p) for p in paths or []} | {f for it in items if isinstance(it, dict) for f in (it.get('files') or []) if isinstance(f, str)})
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
        it, done, ans, via, question, err = _ask_one(it, n, catalog, bind_id, unattended, given.get(n, []), inline, key, suggest, paths)
        if err:
            errors.append(err)
        elif question:
            questions.append(question)
        elif ans is not None and _norm(ans.get("choice")).lower() == "explain":
            explain.append({"item": n, "message": f"item {n}: the operator did not understand the question - explain it to them in everyday words in the chat, reword the acceptance criterion with the real names of things and no role nouns, and run this tool again; the new wording is asked again as a new question"})
        elif done:
            errs = _check(it, n, catalog, surface, identifiers)
            if errs:
                errors += errs
                continue
            resolved.append(it)
            decisions.append({**_decision(it, "asked", _norm(ans.get("choice")).lower(), via), **{k: v for k, v in ans.items() if k.startswith("suggestion_")}})
    if errors:
        return {**base, "status": "invalid", "errors": errors}
    out = {**base, "resolved_items": resolved, "ac_decisions": decisions, "counts": count_decisions(decisions)}
    if explain:
        return {**out, "status": "explain", "explain": explain, **({"questions": questions} if questions else {})}
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
