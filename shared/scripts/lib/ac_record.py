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

from lib.ac_decision import ac_body, catalog_texts, count_decisions, frozen_fields

__all__ = ["append_record", "changed_catalog", "freeze_differences", "read_records", "record_path"]


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
           "items": [frozen_fields(i) for i in result["resolved_items"]], "decisions": result["ac_decisions"], "counts": count_decisions(result["ac_decisions"])}
    path = record_path(project_root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    return rec


def _show(root: Path, ref: str, path: str) -> str:
    done = subprocess.run(["git", "-C", str(root), "show", f"{ref}:{path}"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return done.stdout if done.returncode == 0 else ""


def changed_catalog(project_root: str | Path, base: str, head: str, spec_paths: list[str]) -> tuple[dict[str, str], set[str]]:
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
