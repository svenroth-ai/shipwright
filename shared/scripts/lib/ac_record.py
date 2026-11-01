"""The append-only record of what a run froze before the build, and the compare that checks it at finalize.

The freeze lives OUTSIDE the plan stub, in ``.shipwright/planning/iterate/<run_id>/ac-record.jsonl``: one JSON line
per write, never rewritten. The first write is ``frozen``; a later write (``write_plan_stub.py --force``) appends a
``superseded`` line that names the line it replaces, so editing the plan stub cannot quietly move the promise.

Freeze = compare, not hash. At finalize the recorded ``new_text`` of every add/change item is compared with the
catalog AC text actually in the diff; any difference is a WARNING naming both texts. The record is read from the
committed ``head`` (git), not the working tree, and is checked for append-only growth since the base and for being
committed no later than the first code. All of it is warning-only: F11 never holds a PR on this.
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.ac_catalog import ac_body, catalog_texts, load_catalog
from lib.ac_decision import count_decisions, frozen_fields
from lib.ac_hold import is_unattended
from lib.ac_surface import git_changes, is_observable_path, is_test_path, observable_files, read_blobs, run_git
from lib.ac_wording import diff_identifiers, wording_violations

__all__ = ["append_record", "changed_catalog", "freeze_differences", "read_records", "record_path", "undeclared_edits", "verify"]


def record_path(project_root: str | Path, run_id: str) -> Path:
    return Path(project_root) / ".shipwright" / "planning" / "iterate" / run_id / "ac-record.jsonl"


def _rel(run_id: str) -> str:
    return f".shipwright/planning/iterate/{run_id}/ac-record.jsonl"


def _parse_records(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def read_records(project_root: str | Path, run_id: str, text: str | None = None) -> list[dict]:
    """Every readable record line, in write order (an unreadable line or a non-object line is skipped); ``text`` overrides the file."""
    if text is None:
        try:
            text = record_path(project_root, run_id).read_text(encoding="utf-8")
        except (OSError, ValueError):
            return []
    return _parse_records(text)


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


def _texts(root: Path, ref: str | None, paths: list[str]) -> dict[str, str]:
    """Each path's text at ``ref`` (one git call), or from the working tree when ``ref`` is None; a missing file reads as empty."""
    if ref is not None:
        return {p: t or "" for p, t in read_blobs(root, ref, paths).items()}
    out = {}
    for p in paths:
        try:
            out[p] = (root / p).read_text(encoding="utf-8")
        except (OSError, ValueError):
            out[p] = ""
    return out


def changed_catalog(project_root: str | Path, base: str, head: str | None, spec_paths: list[str]) -> tuple[dict[str, str], set[str]]:
    """``(changed, removed)``: the catalog ACs whose text differs ``base`` -> ``head`` (id -> new text), and the ids that vanished."""
    root, changed, removed = Path(project_root), {}, set()
    before, after = _texts(root, base, spec_paths), _texts(root, head, spec_paths)
    for rel in spec_paths:
        old, new = catalog_texts(before[rel]), catalog_texts(after[rel])
        changed.update({k: v for k, v in new.items() if old.get(k) != v})
        removed.update(k for k in old if k not in new)
    return changed, removed


def freeze_differences(items: object, changed: dict[str, str], removed: set[str], base_acs: object = ()) -> list[str]:
    """Where the frozen records and the catalog in the diff disagree; each line names both sides. Empty = they agree.

    An ``add`` may only claim an id that is absent from the base catalog (``base_acs``); a changed existing id is never matched by an add's text.
    """
    out: list[str] = []
    free = {k: v for k, v in changed.items() if k not in base_acs}
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            out.append("a frozen item is not readable")
            continue
        kind, ac, new = it.get("kind"), str(it.get("ac") or ""), str(it.get("new_text") or "")
        if kind == "remove" and ac not in removed:
            out.append(f"frozen: remove {ac}; catalog in the diff: {ac} is still there")
        elif kind == "add" and ac in base_acs:
            out.append(f"frozen: add {ac}; catalog at the base: {ac} already exists - an add may only claim a new id")
        elif kind in ("add", "change") and ac and ac in changed:
            if ac_body(changed[ac]) != ac_body(new):
                out.append(f"frozen: {new!r}; catalog in the diff ({ac}): {ac_body(changed[ac])!r}")
        elif kind in ("add", "change") and not any(ac_body(t) == ac_body(new) for t in (free if kind == "add" else changed).values()):
            out.append(f"frozen: {new!r}; catalog in the diff: " + (repr(ac_body(changed[ac])) if ac in changed else "no AC with this wording was added or changed"))
    return out


def undeclared_edits(items: object, changed: dict[str, str], removed: set[str], base_acs: object = ()) -> list[str]:
    """Catalog AC ids edited or removed in the diff that no item names - the "existing AC changes" rule enforced from the diff, not from a label.

    Only a change/remove names an existing id; an add names an id only when it is absent from the base catalog.
    """
    rows = [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []
    named = {str(i.get("ac")) for i in rows if i.get("ac") and (i.get("kind") in ("change", "remove") or (i.get("kind") == "add" and str(i.get("ac")) not in base_acs))}
    bodies = {ac_body(i.get("new_text")) for i in rows if i.get("kind") in ("add", "change") and i.get("new_text")}
    named |= {ac for ac, text in changed.items() if ac not in base_acs and ac_body(text) in bodies}
    return sorted((set(changed) | removed) - named)


def _mentions(changes: dict[str, dict], ac: str) -> bool:
    forms = (ac, ac.replace(".AC", "/AC"))
    return any(is_test_path(p) and any(f in line for line in rec.get("added", []) for f in forms) for p, rec in changes.items())


def _order_problem(root: Path, rel: str, base: str, head: str) -> str:
    """Best effort: the record is committed no later than the first code commit (a single squashed commit is fine)."""
    try:
        log = run_git(root, "log", "--reverse", "--name-only", "--format=%x00%H", f"{base}..{head}").decode("utf-8", "replace")
    except RuntimeError:
        return ""
    rec_at = code_at = None
    for n, block in enumerate(b for b in log.split("\x00") if b.strip()):
        files = block.splitlines()[1:]
        if rec_at is None and rel in files:
            rec_at = n
        if code_at is None and any(f != rel and is_observable_path(f) for f in files):
            code_at = n
    if code_at is not None and (rec_at is None or rec_at > code_at):
        return "the AC record was committed after the first code commit (or not at all) - it is instructed to be written before any code"
    return ""


def _record_problems(root: Path, run_id: str, base: str, head: str | None) -> tuple[list[dict], list[str]]:
    rel = _rel(run_id)
    if head is None:
        return read_records(root, run_id), []
    now, was = _texts(root, head, [rel])[rel], _texts(root, base, [rel])[rel]
    out = []
    old_lines, new_lines = was.splitlines(), now.splitlines()
    if old_lines and new_lines[:len(old_lines)] != old_lines:
        out.append("the AC record is not append-only: a line present at the base was removed or changed")
    order = _order_problem(root, rel, base, head) if now else ""
    return _parse_records(now), out + ([order] if order else [])


def _item_problems(items: list, catalog: dict, changes: dict, surface: dict, idents: set[str]) -> list[str]:
    out: list[str] = []
    for i in items:
        if i.get("kind") in ("restore", "unchanged"):
            ac = str(i.get("restores_ac") or i.get("ac") or "")
            if ac not in catalog:
                out.append(f"{i.get('kind')} names {ac}, which is not in the catalog at the base - that is a catalog gap, so add the AC")
            elif not _mentions(changes, ac):
                out.append(f"{i.get('kind')} names {ac}, but no test file in the diff mentions that AC id")
        if i.get("kind") == "unchanged":
            listed, seen = set(i.get("files") or []), set(surface["files"])
            if seen - listed or listed - seen:
                out.append(f"unchanged lists files that differ from the observable files the diff changes (not listed: {sorted(seen - listed)[:4]}; listed but not changed: {sorted(listed - seen)[:4]}) - it is then not a behaviour-preserving refactor of those files")
        bad = wording_violations(i.get("new_text"), idents) if i.get("kind") in ("add", "change", "restore") else []
        if bad:
            out.append(f"the recorded AC text does not read as an outcome against the committed diff: {'; '.join(bad[:4])}")
    return out


def verify(project_root: str | Path, run_id: str, base: str, head: str | None, catalog: dict | None = None) -> list[str]:
    """Every way the recorded AC declaration and the diff ``base`` -> ``head`` (None = working tree) disagree. Empty = they agree.

    Used by the F11 check and by ``ac_decision.py verify``. Nothing here blocks: callers report warnings. An unreadable
    catalog (text but no FR the parser can read) returns an empty list: the caller skips with a note.
    """
    root = Path(project_root)
    catalog = catalog or load_catalog(root, base)
    if catalog["unparsed"]:
        return []
    changes = git_changes(root, base, head)
    surface = observable_files(changes)
    specs = [f for f in changes if f.startswith(".shipwright/planning/") and f.endswith("/spec.md")]
    changed, removed = changed_catalog(root, base, head, specs)
    records, out = _record_problems(root, run_id, base, head)
    last = records[-1] if records else {}
    items = last.get("items") if isinstance(last.get("items"), list) else []
    if surface["observable"] and not records:
        out.append(f"the diff changes observable behaviour ({', '.join(surface['files'][:4])}) but no AC record exists - write the declaration with tools/ac_decision.py, then tools/write_plan_stub.py --ac-decision")
    elif records and (not items or not all(isinstance(i, dict) for i in items)):
        return out + ["the AC record carries no readable items"]
    elif records and surface["observable"] and all(i.get("kind") == "exempt" for i in items):
        out.append(f"recorded as no observable change, but the diff changes observable behaviour ({', '.join(surface['files'][:4])}) - name the AC it restores, or add one")
    out += _item_problems(items, catalog["acs"], changes, surface, diff_identifiers(changes))
    out += [f"the frozen AC differs from the catalog - {d}" for d in freeze_differences(items, changed, removed, catalog["acs"])]
    undeclared = undeclared_edits(items, changed, removed, catalog["acs"])
    if undeclared:
        out.append("the diff edits or removes catalog AC(s) that no record item names: " + ", ".join(undeclared))
    if len(records) > 1:
        out.append(f"the AC record was superseded {len(records) - 1} time(s); first frozen: {records[0].get('items')!r}; now: {items!r}")
    if records:
        decisions = last.get("decisions")
        if not isinstance(decisions, list) or count_decisions(decisions)["total"] != len(items):
            out.append("the AC record has no usable decisions (one {ac, mode, answer, kind, answered_via} per item)")
        else:
            weak = sorted({str(d.get("answered_via")) for d in decisions if isinstance(d, dict) and d.get("mode") == "asked" and d.get("answered_via") != "operator"})
            if weak:
                out.append(f"an asked decision was not answered through the signed operator channel (answered_via: {', '.join(weak)})"
                           + (" in an unattended run" if is_unattended(root) else "") + " - answered_via is self-reported, a guard and not authentication")
    return out
