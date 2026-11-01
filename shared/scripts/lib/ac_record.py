"""The append-only record of what a run froze before the build, and the compare that checks it at finalize.

The freeze lives OUTSIDE the plan stub, in ``.shipwright/planning/iterate/<run_id>/ac-record.jsonl``: one JSON line
per write, never rewritten. The first write is ``frozen``; a later write (``write_plan_stub.py --force``) appends a
``superseded`` line that names the line it replaces, so editing the plan stub cannot quietly move the promise.

Freeze = compare, not hash. At finalize the recorded ``new_text`` of every add/change item is compared with the
catalog AC text actually in the diff; any difference is a WARNING naming both texts.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from lib.ac_decision import ac_body, catalog_texts, count_decisions, frozen_fields, load_catalog
from lib.ac_surface import git_changes, is_test_path, observable_files
from lib.ac_wording import diff_identifiers, wording_violations

__all__ = ["append_record", "changed_catalog", "freeze_differences", "read_records", "record_path", "undeclared_edits", "verify"]


def record_path(project_root: str | Path, run_id: str) -> Path:
    return Path(project_root) / ".shipwright" / "planning" / "iterate" / run_id / "ac-record.jsonl"


def read_records(project_root: str | Path, run_id: str) -> list[dict]:
    """Every readable record line, in write order (an unreadable line or a non-object line is skipped)."""
    try:
        lines = record_path(project_root, run_id).read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return []
    out = []
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def append_record(project_root: str | Path, run_id: str, result: dict) -> dict:
    """Append the decided declaration; the first line is ``frozen``, every later one ``superseded`` (never a replace)."""
    prior = read_records(project_root, run_id)
    rec = {"seq": len(prior) + 1, "kind": "superseded" if prior else "frozen", "supersedes": prior[-1].get("seq") if prior else None,
           "items": [frozen_fields(i) for i in result["resolved_items"]], "decisions": result["ac_decisions"], "counts": count_decisions(result["ac_decisions"]),
           "unattended": bool(result.get("unattended"))}
    path = record_path(project_root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    return rec


def _show(root: Path, ref: str | None, path: str) -> str:
    if ref is None:  # the working tree
        try:
            return (root / path).read_text(encoding="utf-8")
        except (OSError, ValueError):
            return ""
    done = subprocess.run(["git", "-C", str(root), "show", f"{ref}:{path}"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return done.stdout if done.returncode == 0 else ""


def changed_catalog(project_root: str | Path, base: str, head: str | None, spec_paths: list[str]) -> tuple[dict[str, str], set[str]]:
    """``(changed, removed)``: the catalog ACs whose text differs ``base`` -> ``head`` (id -> new text), and the ids that vanished."""
    root, changed, removed = Path(project_root), {}, set()
    for rel in spec_paths:
        old, new = catalog_texts(_show(root, base, rel)), catalog_texts(_show(root, head, rel))
        changed.update({k: v for k, v in new.items() if old.get(k) != v})
        removed.update(k for k in old if k not in new)
    return changed, removed


def freeze_differences(items: object, changed: dict[str, str], removed: set[str]) -> list[str]:
    """Where the frozen records and the catalog in the diff disagree; each line names both sides. Empty = they agree."""
    out: list[str] = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            out.append("a frozen item is not readable")
            continue
        kind, ac, new = it.get("kind"), str(it.get("ac") or ""), str(it.get("new_text") or "")
        if kind == "remove" and ac not in removed:
            out.append(f"frozen: remove {ac}; catalog in the diff: {ac} is still there")
        elif kind in ("add", "change") and ac and ac in changed:
            if ac_body(changed[ac]) != ac_body(new):
                out.append(f"frozen: {new!r}; catalog in the diff ({ac}): {ac_body(changed[ac])!r}")
        elif kind in ("add", "change") and not any(ac_body(t) == ac_body(new) for t in changed.values()):
            out.append(f"frozen: {new!r}; catalog in the diff: " + (repr(ac_body(changed[ac])) if ac in changed else "no AC with this wording was added or changed"))
    return out


def undeclared_edits(items: object, changed: dict[str, str], removed: set[str]) -> list[str]:
    """Catalog AC ids edited or removed in the diff that no item names - the "existing AC changes" rule enforced from the diff, not from a label."""
    rows = [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []
    named = {str(i.get("ac")) for i in rows if i.get("ac")}
    bodies = {ac_body(i.get("new_text")) for i in rows if i.get("kind") in ("add", "change") and i.get("new_text")}
    named |= {ac for ac, text in changed.items() if ac_body(text) in bodies}
    return sorted((set(changed) | removed) - named)


def _mentions(changes: dict[str, dict], ac: str) -> bool:
    forms = (ac, ac.replace(".AC", "/AC"))
    return any(is_test_path(p) and any(f in line for line in rec.get("added", []) for f in forms) for p, rec in changes.items())


def verify(project_root: str | Path, run_id: str, base: str, head: str | None) -> list[str]:
    """Every way the recorded AC declaration and the diff ``base`` -> ``head`` (None = working tree) disagree. Empty = they agree.

    Used by the F11 check and by ``ac_decision.py verify``. Nothing here blocks: callers report warnings.
    """
    root = Path(project_root)
    changes = git_changes(root, base, head)
    surface = observable_files(changes)
    specs = [f for f in changes if f.startswith(".shipwright/planning/") and f.endswith("/spec.md")]
    changed, removed = changed_catalog(root, base, head, specs)
    records = read_records(root, run_id)
    last = records[-1] if records else {}
    items = last.get("items") if isinstance(last.get("items"), list) else []
    out: list[str] = []
    if surface["observable"] and not records:
        out.append(f"the diff changes observable behaviour ({', '.join(surface['files'][:4])}) but no AC record exists - write the declaration with tools/ac_decision.py, then tools/write_plan_stub.py --ac-decision")
    elif records and (not items or not all(isinstance(i, dict) for i in items)):
        return out + ["the AC record carries no readable items"]
    elif records and surface["observable"] and all(i.get("kind") == "exempt" for i in items):
        out.append(f"recorded as no observable change, but the diff changes observable behaviour ({', '.join(surface['files'][:4])}) - name the AC it restores, or add one")
    catalog = load_catalog(root, base)["acs"]
    for i in items:
        if i.get("kind") == "restore":
            ac = str(i.get("restores_ac") or "")
            if ac not in catalog:
                out.append(f"restores {ac}, which is not in the catalog at the base - that is a catalog gap, so add the AC")
            elif not _mentions(changes, ac):
                out.append(f"restores {ac}, but no test file in the diff mentions that AC id")
    idents = diff_identifiers(changes)
    for i in items:
        bad = wording_violations(i.get("new_text"), idents) if i.get("kind") in ("add", "change", "restore") else []
        if bad:
            out.append(f"the recorded AC text does not read as an outcome against the committed diff: {'; '.join(bad[:4])}")
    out += [f"the frozen AC differs from the catalog - {d}" for d in freeze_differences(items, changed, removed)]
    if undeclared_edits(items, changed, removed):
        out.append("the diff edits or removes catalog AC(s) that no record item names: " + ", ".join(undeclared_edits(items, changed, removed)))
    if len(records) > 1:
        out.append(f"the AC record was superseded {len(records) - 1} time(s); first frozen: {records[0].get('items')!r}; now: {items!r}")
    if records:
        decisions = last.get("decisions")
        if not isinstance(decisions, list) or count_decisions(decisions)["total"] != len(items):
            out.append("the AC record has no usable decisions (one {ac, mode, answer, kind, answered_via} per item)")
        elif last.get("unattended") and any(isinstance(d, dict) and d.get("mode") == "asked" and d.get("answered_via") != "operator" for d in decisions):
            out.append("an unattended run recorded an asked decision that was not answered through the operator channel")
    return out
