"""The pre-build acceptance-criterion (AC) decision: ask the operator or decide alone, deterministically.

Before a FEATURE or CHANGE is built, the agent writes down what it will promise (the exact catalog AC
text, old and new for a change), or why nothing observable changes (an exemption by OUTCOME), or - for a
restore - the id of the AC it restores. This module turns that declaration into a decision:

* **Validation.** A restore must name an AC that exists in the catalog (otherwise it is a catalog gap and
  gets an AC). An exemption names a closed kind and gives a reason in words about the outcome; a reason
  that is only a label (bug, trivial, tooling, a complexity tier, a path label) is refused.
* **The table, first matching row wins** (``decide``): (1) an existing AC is changed or removed: ask;
  (2) no single FR owns a new AC: ask; (3) the AC text trips the lexical HOW test (:func:`how_hits`): ask;
  (4) the request leaves open what the user sees: ask; otherwise auto. An exemption "this is only how" is
  an operator's call, so it asks; "no observable change" is decided alone and counted.
* **A plain question.** The question shows a one-sentence outcome the agent wrote (``plain_new`` /
  ``plain_old``); that sentence itself must pass the HOW test, so a question never carries a path, a
  symbol, a flag or a threshold.
* **Freezing.** :func:`frozen_hash` hashes the resolved items; the hash goes into the plan stub, so a later
  edit of the text is a visible difference.

Presence and shape only: whether the sentence is TRUE is for the reviewers. Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

__all__ = [
    "EXEMPT_KINDS", "KINDS", "decide", "frozen_hash", "how_hits", "label_only", "load_catalog_acs", "render_question",
    "stub_lines", "parse_stub_ac",
]

KINDS = ("add", "change", "remove", "restore", "exempt")
EXEMPT_KINDS = ("no-observable-change", "how-only")
ANSWERS = ("yes", "no", "only-how")

# The lexical HOW test: the same shapes the Step 1a altitude self-check names (a GET/POST verb, a snake_case
# symbol, an ADR number, an iterate slug), plus the path, the flag and the number with a unit.
_HOW = {
    "path": re.compile(r"(?<![\w/])(?:[\w.-]+/)+[\w.-]+|\b[\w-]+\.(?:py|md|json|jsonl|ya?ml|toml|sh|js|ts|tsx|css|html|txt|cfg|ini)\b"),
    "snake_case": re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b"),
    "flag": re.compile(r"(?<![\w-])--?[A-Za-z][\w-]*"),
    "adr_number": re.compile(r"\bADR-\d+\b"),
    "slug": re.compile(r"\b(?=[a-z0-9-]*[a-z])[a-z0-9]+(?:-[a-z0-9]+){2,}\b"),
    "number_with_unit": re.compile(
        r"\b\d+(?:[.,]\d+)?\s?(?:ms|s|secs?|seconds?|minutes?|mins?|hours?|hrs?|days?|weeks?|percent|kb|mb|gb|bytes?|lines?|loc|chars?|characters?|times|retries)\b"
        r"|\b\d+(?:[.,]\d+)?\s?%"),
    "http_verb": re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE)\b"),
}
_LABEL_WORDS = frozenset(
    "a an the this that it is are was be as of for to in on and or no not bug bugfix fix fixes trivial tooling tiny small "
    "minor medium large simple docs doc chore refactor infra test tests only just change update cleanup internal".split())
_AC_ID = re.compile(r"^FR-\d+\.\d+\.AC\d+$")
_FR_ID = re.compile(r"^FR-\d+\.\d+$")


def how_hits(text: object) -> list[str]:
    """Names of the HOW shapes found in ``text`` (empty = the sentence reads as an outcome)."""
    if not isinstance(text, str):
        return []
    return [name for name, rx in _HOW.items() if rx.search(text)]


def _norm(text: object) -> str:
    return " ".join(str(text or "").split())


def label_only(reason: object) -> bool:
    """True when ``reason`` says nothing about the outcome: after dropping label words fewer than 2 words remain."""
    words = re.findall(r"[a-z]+", _norm(reason).lower())
    return len([w for w in words if w not in _LABEL_WORDS]) < 2


_FR_HEAD = re.compile(r"^###\s+(FR-\d+\.\d+)")
_AC_HEAD = re.compile(r"^-\s+(?:\([A-Z]\)\s+)?\[AC(\d+)\]")


def _ac_body(text: object) -> str:
    """An AC's wording without its list markup (``- (E) [AC05]``) and trailing run-id note, lower-cased."""
    body = re.sub(r"^-?\s*(?:\([A-Z]\)\s*)?(?:\[AC\d+\]\s*)?", "", _norm(text))
    return re.sub(r"\s*\(iterate-[^)]*\)\s*$", "", body).strip().lower()


def _catalog_texts(spec_text: str) -> dict[str, str]:
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


def load_catalog_acs(project_root: str | Path) -> dict[str, str]:
    """Every AC in the project's requirement catalogs (``.shipwright/planning/*/spec.md``): id -> its current text."""
    found: dict[str, str] = {}
    for spec in sorted((Path(project_root) / ".shipwright" / "planning").glob("*/spec.md")):
        try:
            found.update(_catalog_texts(spec.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return found


def _resolve(item: dict) -> dict:
    """Apply the operator's answer: yes keeps it, no replaces the text, only-how turns it into an exemption."""
    out = dict(item)
    ans = item.get("answer") if isinstance(item.get("answer"), dict) else None
    out["_asked"] = ans is not None
    if not ans:
        return out
    choice = str(ans.get("choice") or "").strip().lower()
    text = _norm(ans.get("text"))
    if choice not in ANSWERS:
        out["_answer_error"] = f"answer choice must be one of {', '.join(ANSWERS)}"
    elif choice == "no" and not text:
        out["_answer_error"] = "answer 'no' needs the operator's wording in 'text'"
    elif choice == "no" and item.get("kind") == "remove":
        out["_answer_error"] = "the operator wants this promise kept: drop the removal and keep the behaviour consistent with it"
    elif choice == "no" and item.get("kind") == "exempt":
        out.update(kind="add", new_text=text)
        for k in ("exempt_kind", "exempt_reason"):
            out.pop(k, None)
    elif choice == "no":
        out["new_text"] = text
    elif choice == "only-how":
        out.update(kind="exempt", exempt_kind="how-only", exempt_reason=_norm(ans.get("text")) or "the operator said this is only how it is built, not a promise")
    return out


def _frozen_fields(item: dict) -> dict:
    keys = ("kind", "ac", "restores_ac", "owner_fr", "old_text", "new_text", "exempt_kind", "exempt_reason")
    return {k: _norm(item.get(k)) for k in keys if _norm(item.get(k))}


def frozen_hash(items: list[dict]) -> str:
    """sha256 over the canonical frozen fields of the resolved items (answers excluded; their effect is included)."""
    canon = json.dumps([_frozen_fields(i) for i in items], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


def render_question(item: dict) -> str:
    """The plain-language question, three answers (the removal variant states what stops holding)."""
    new = _norm(item.get("plain_new") or item.get("new_text"))
    old = _norm(item.get("plain_old") or item.get("old_text"))
    if item.get("kind") == "remove":
        head = f"This change removes a promise. Until now this held: {old}. After this change it no longer holds."
        yes = "1 Yes, that is intended."
    else:
        head = f"This change gives the product a new promise: {new}. Until now: {old or 'nothing'}. Should it hold like this?"
        yes = "1 Yes, write it."
    if item.get("kind") == "exempt":
        head = f"This change does not add a promise. The agent says it is only how the product works: {_norm(item.get('plain_new') or item.get('exempt_reason'))}. Do you agree?"
        return f"{head}\n1 Yes, it is only how it is built, not a promise.\n2 No, it is a promise: <your wording>"
    return f"{head}\n{yes}\n2 No, instead: <your wording>\n3 This is only how it is built, not a promise."


def _check(item: dict, i: int, catalog: dict[str, str] | set[str]) -> list[str]:
    errs: list[str] = []
    if item.get("_answer_error"):
        errs.append(f"item {i}: {item['_answer_error']}")
    kind = item.get("kind")
    tag = f"item {i}"
    if kind not in KINDS:
        return [f"{tag}: kind must be one of {', '.join(KINDS)}"]
    ac = _norm(item.get("ac"))
    if kind in ("change", "remove", "restore"):
        key = "restores_ac" if kind == "restore" else "ac"
        ac = _norm(item.get(key))
        if not _AC_ID.match(ac):
            errs.append(f"{tag}: {kind} needs an AC id like FR-01.03.AC05 in '{key}'")
        elif ac not in catalog:
            errs.append(f"{tag}: {ac} is not in the catalog - " + ("a restore must name an AC that exists; if none does it is a catalog gap, so add the AC instead (kind add)" if kind == "restore" else "a change or removal needs an existing AC"))
    if kind in ("add", "change") and not _norm(item.get("new_text")):
        errs.append(f"{tag}: {kind} needs the exact AC text in 'new_text'")
    if kind in ("change", "remove") and not _norm(item.get("old_text")):
        errs.append(f"{tag}: {kind} needs the current AC text in 'old_text'")
    elif kind in ("change", "remove") and isinstance(catalog, dict) and ac in catalog and _ac_body(item.get("old_text")) != _ac_body(catalog[ac]):
        errs.append(f"{tag}: old_text is not the current text of {ac} in the catalog - copy it exactly")
    if kind == "add" and item.get("owner_fr") and not _FR_ID.match(_norm(item.get("owner_fr"))):
        errs.append(f"{tag}: owner_fr must look like FR-01.03")
    if kind == "exempt":
        if item.get("exempt_kind") not in EXEMPT_KINDS:
            errs.append(f"{tag}: exempt_kind must be one of {', '.join(EXEMPT_KINDS)}")
        if label_only(item.get("exempt_reason")):
            errs.append(f"{tag}: the exemption must say in words what stays the same for users and operators; a label (bug, trivial, tooling, a tier or a path label) is not a reason")
    return errs


def _row(item: dict) -> tuple[int | str, str] | None:
    """(row, why) of the first table row that asks, or None for auto. First match wins."""
    kind = item["kind"]
    if kind in ("change", "remove"):
        return 1, "an existing AC is changed or removed"
    if kind == "add" and not _norm(item.get("owner_fr")):
        return 2, "no single FR owns this AC"
    if kind in ("add", "change"):
        hits = how_hits(item.get("new_text"))
        if hits:
            return 3, "the AC text trips the HOW test (" + ", ".join(hits) + ")"
    if kind in ("add", "change") and item.get("request_open"):
        return 4, "the request leaves open what the user sees"
    if kind == "exempt" and item.get("exempt_kind") == "how-only":
        return "exempt", "a how-only exemption is the operator's call"
    return None


def decide(items: list[dict], catalog: dict[str, str] | set[str], autonomous: bool = False) -> dict:
    """Decide every item. ``status``: ``ok`` (all decided), ``ask`` (questions to put to the operator), ``invalid``."""
    if not isinstance(items, list) or not items:
        return {"status": "invalid", "errors": ["items must be a non-empty list: every feature/change records an AC, an exemption or a restore"],
                "autonomous": autonomous}
    resolved = [_resolve(i) if isinstance(i, dict) else {} for i in items]
    errors = [e for n, it in enumerate(resolved) for e in _check(it, n, catalog)]
    decisions, questions = [], []
    for n, it in enumerate(resolved):
        if errors and not it.get("kind"):
            continue
        asked = it.pop("_asked", False)
        row = None if asked else _row(it) if it.get("kind") in KINDS else None
        ac = _norm(it.get("restores_ac") if it.get("kind") == "restore" else it.get("ac")) or (
            f"{_norm(it.get('owner_fr'))}.new" if it.get("kind") == "add" and _norm(it.get("owner_fr")) else ("none" if it.get("kind") == "exempt" else "new"))
        if row:
            sentence = _norm(it.get("plain_new") or it.get("exempt_reason") or it.get("new_text")) if it.get("kind") != "remove" else _norm(it.get("plain_old") or it.get("old_text"))
            if how_hits(sentence) or (it.get("kind") in ("change",) and how_hits(_norm(it.get("plain_old") or it.get("old_text")))):
                errors.append(f"item {n}: the question sentence (plain_new / plain_old) must read as an outcome - no path, symbol, flag, ADR number, slug or number with a unit; reword it")
                continue
            questions.append({"item": n, "row": row[0], "why": row[1], "text": render_question(it)})
            continue
        decisions.append({"ac": ac, "mode": "asked" if asked else "auto",
                          "answer": str((items[n].get("answer") or {}).get("choice")) if asked else "auto"})
    if errors:
        return {"status": "invalid", "errors": errors, "autonomous": autonomous}
    clean = [{k: v for k, v in it.items() if k != "answer"} for it in resolved]
    base = {"autonomous": autonomous, "resolved_items": clean, "frozen_hash": frozen_hash(clean)}
    if questions:
        return {**base, "status": "ask", "questions": questions, "ac_decisions": decisions}
    return {**base, "status": "ok", "ac_decisions": decisions}


# --- plan stub lines -----------------------------------------------------------------------------

def stub_lines(result: dict) -> list[str]:
    """The lines a decided declaration adds to the plan stub (frozen hash, one line per item, the decisions)."""
    lines = [f"AC frozen: {result['frozen_hash']}"]
    lines += [f"AC item: {json.dumps(_frozen_fields(i), ensure_ascii=False, sort_keys=True)}" for i in result["resolved_items"]]
    lines.append("AC decisions: " + json.dumps(result["ac_decisions"], ensure_ascii=False))
    return lines


def parse_stub_ac(text: str) -> dict:
    """``{"frozen", "items", "decisions", "hash_ok"}`` read back from a stub; ``frozen`` is "" when absent."""
    frozen, items, decisions = "", [], []
    for line in (text or "").splitlines():
        if line.startswith("AC frozen:"):
            frozen = line.split(":", 1)[1].strip()
        elif line.startswith("AC item:"):
            try:
                items.append(json.loads(line.split(":", 1)[1]))
            except ValueError:
                items.append({"_unreadable": True})
        elif line.startswith("AC decisions:"):
            try:
                decisions = json.loads(line.split(":", 1)[1])
            except ValueError:
                decisions = []
    return {"frozen": frozen, "items": items, "decisions": decisions,
            "hash_ok": bool(frozen) and bool(items) and frozen_hash(items) == frozen}
