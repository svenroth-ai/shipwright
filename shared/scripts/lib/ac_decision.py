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
* **Answers** come through the operator channel, bound to the sha256 of run id + item index + question text. An
  unattended run (:func:`lib.ac_hold.is_unattended`) refuses inline answers and answers not from the operator
  channel. Every decision records ``answered_via`` (none, inline, answer-file, operator).

Presence and shape only: whether the sentence is TRUE is for the reviewers. Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from lib.ac_wording import wording_violations

__all__ = ["KINDS", "ac_body", "catalog_texts", "count_decisions", "decide", "frozen_fields", "load_catalog", "question_sha", "render_question", "stub_lines"]

KINDS = ("add", "change", "remove", "restore", "exempt")
ANSWERS = ("yes", "no")
_AC_ID = re.compile(r"^FR-\d+\.\d+\.AC\d+$")
_FR_ID = re.compile(r"^FR-\d+\.\d+$")
_FR_HEAD = re.compile(r"^###\s+(FR-\d+\.\d+)")
_AC_HEAD = re.compile(r"^-\s+(?:\([A-Z]\)\s+)?\[AC(\d+)\]")
_TEXT_FIELDS = ("new_text", "old_text", "owner_fr", "ac", "restores_ac")


def _norm(text: object) -> str:
    return " ".join(str(text if text is not None else "").split())


def ac_body(text: object) -> str:
    """An AC's wording without list markup (``- (E) [AC05]``) and the trailing run-id note, lower-cased."""
    body = re.sub(r"^-?\s*(?:\([A-Z]\)\s*)?(?:\[AC\d+\]\s*)?", "", _norm(text))
    return re.sub(r"\s*\(iterate-[^)]*\)\s*$", "", body).strip().lower()


def catalog_texts(spec_text: str) -> dict[str, str]:
    """``{"FR-01.03.AC05": "its text", ...}`` for one ``spec.md`` (same line shapes as ``spec_chain.parse_spec_acs``)."""
    out: dict[str, str] = {}
    fr, cur = "", ""
    for line in (spec_text or "").splitlines():
        h, a = _FR_HEAD.match(line), _AC_HEAD.match(line)
        if h or a or line.startswith("#"):
            cur = ""
        if h:
            fr = h.group(1)
        elif line.startswith("## "):
            fr = ""
        elif a and fr:
            cur = f"{fr}.AC{int(a.group(1)):02d}"
            out[cur] = line
        elif cur and line.startswith(" "):
            out[cur] += " " + line.strip()
        elif cur and line.strip():
            cur = ""
    return {k: _norm(v) for k, v in out.items()}


def _spec_texts(root: Path, base_ref: str | None) -> list[str]:
    """Every ``.shipwright/planning/*/spec.md``: from ``base_ref`` when given (git), else from the working tree."""
    if base_ref:
        names = subprocess.run(["git", "-C", str(root), "ls-tree", "-r", "--name-only", base_ref, ".shipwright/planning"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        if names.returncode != 0:
            raise RuntimeError(f"cannot read the catalog at {base_ref}: {names.stderr.strip()}")
        out = []
        for rel in sorted(n for n in names.stdout.splitlines() if re.fullmatch(r"\.shipwright/planning/[^/]+/spec\.md", n)):
            shown = subprocess.run(["git", "-C", str(root), "show", f"{base_ref}:{rel}"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
            out.append(shown.stdout)
        return out
    out = []
    for spec in sorted((root / ".shipwright" / "planning").glob("*/spec.md")):
        try:
            out.append(spec.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return out


def load_catalog(project_root: str | Path, base_ref: str | None = None) -> dict:
    """``{"acs": {id: text}, "frs": {FR ids}}`` of the requirement catalogs, from ``base_ref`` (git) when given."""
    acs: dict[str, str] = {}
    frs: set[str] = set()
    for text in _spec_texts(Path(project_root), base_ref):
        acs.update(catalog_texts(text))
        frs.update(m.group(1) for m in (_FR_HEAD.match(ln) for ln in text.splitlines()) if m)
    return {"acs": acs, "frs": frs}


def question_sha(text: str, run_id: str = "", index: int = 0) -> str:
    """sha256 binding an answer to the run, the item index and the exact question text."""
    return "sha256:" + hashlib.sha256(f"{run_id}\n{index}\n{text}".encode("utf-8")).hexdigest()


def render_question(item: dict) -> str:
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
    return (f"This change adds a new promise that does not clearly belong to one feature: {new}. Should it hold, and under which feature?\n"
            "1 Yes, write it under this feature: <feature id like FR-01.03>\n2 No, instead: <your wording>")


def count_decisions(decisions: object) -> dict:
    """The one producer of the decision counts: ``{total, auto, asked, exempt, restore, exempt_share, restore_share}``.

    Priority per decision: exempt, restore, asked, auto - every decision lands in exactly one bucket. Malformed input counts as nothing.
    """
    rows = [d for d in decisions if isinstance(d, dict)] if isinstance(decisions, list) else []
    exempt = sum(1 for d in rows if d.get("kind") == "exempt")
    restore = sum(1 for d in rows if d.get("kind") == "restore")
    asked = sum(1 for d in rows if d.get("kind") not in ("exempt", "restore") and d.get("mode") == "asked")
    total = len(rows)
    return {"total": total, "auto": total - exempt - restore - asked, "asked": asked, "exempt": exempt, "restore": restore,
            "exempt_share": round(exempt / total, 2) if total else 0.0, "restore_share": round(restore / total, 2) if total else 0.0}


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
    if kind in ("change", "remove", "restore"):
        if not _AC_ID.match(ac):
            errs.append(f"{tag}: {kind} needs an AC id like FR-01.03.AC05 in '{key}'")
        elif ac not in cat["acs"]:
            errs.append(f"{tag}: {ac} is not in the catalog - " + ("a restore must name an AC that exists; if none does it is a catalog gap, so add the AC instead (kind add)" if kind == "restore" else "a change or removal needs an existing AC"))
        elif kind != "restore" and ac_body(it.get("old_text")) != ac_body(cat["acs"][ac]):
            errs.append(f"{tag}: old_text is not the current text of {ac} in the catalog - copy it exactly")
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
    elif it["kind"] == "add":
        if text not in cat["frs"]:
            return out, "answer 'yes' for a new AC needs the owning feature (an FR id of the catalog) in 'text'"
        out["owner_fr"] = text
    return out, ""


def _decision(it: dict, mode: str, answer: str, via: str) -> dict:
    if it["kind"] == "exempt":
        return {"ac": "none", "mode": mode, "answer": answer, "kind": "exempt", "outcome": "no-observable-change", "answered_via": via}
    ac = _norm(it.get("restores_ac") if it["kind"] == "restore" else it.get("ac")) or (
        f"{_norm(it.get('owner_fr') or (it.get('new_fr') or {}).get('id'))}.new" if (it.get("owner_fr") or it.get("new_fr")) else "new")
    return {"ac": ac, "mode": mode, "answer": answer, "kind": it["kind"], "answered_via": via}


def decide(items: object, catalog: dict, unattended: bool = False, surface: dict | None = None, identifiers: set[str] | None = None,
           answers: object = None, run_id: str = "") -> dict:
    """Decide every item. ``status``: ``ok`` (all decided), ``ask`` (questions for the operator), ``invalid`` (``errors``)."""
    base = {"unattended": unattended}
    if not isinstance(items, list) or not items:
        return {**base, "status": "invalid", "errors": ["items must be a non-empty list: every iterate records an AC, an exemption or a restore"]}
    given = {a.get("item"): a for a in answers if isinstance(a, dict)} if isinstance(answers, list) else {}
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
        row = _row(it, catalog)
        if row is None:
            resolved.append(it)
            decisions.append(_decision(it, "auto", "auto", "none"))
            continue
        text = render_question(it)
        sha = question_sha(text, run_id, n)
        filed = given.get(n)
        ans, via = (inline, "inline") if isinstance(inline, dict) else (filed, "operator" if isinstance(filed, dict) and filed.get("via") == "operator" else "answer-file")
        if isinstance(ans, dict) and via != "inline":
            if ans.get("question_sha256") != sha:
                errors.append(f"item {n}: the answer was given for a different question (other run, item or wording) - ask again")
                continue
            if unattended and via != "operator":
                errors.append(f"item {n}: an unattended run takes answers only from the operator channel (ac_decision.py answer run by the operator)")
                continue
        if not isinstance(ans, dict):
            questions.append({"item": n, "row": row[0], "why": row[1], "question": text, "question_sha256": sha})
            continue
        it, err = _apply(it, ans, catalog)
        errs = [f"item {n}: {err}"] if err else _check(it, n, catalog, surface, identifiers)
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
    if isinstance(it.get("new_fr"), dict):
        out["new_fr"] = {"id": _norm(it["new_fr"].get("id")), "title": _norm(it["new_fr"].get("title"))}
    return out


def stub_lines(result: dict) -> list[str]:
    """Readable copy for the plan stub (the authoritative freeze is the append-only record, :mod:`lib.ac_record`)."""
    return [*(f"AC item: {json.dumps(frozen_fields(i), ensure_ascii=False, sort_keys=True)}" for i in result["resolved_items"]),
            "AC decisions: " + json.dumps(result["ac_decisions"], ensure_ascii=False)]
