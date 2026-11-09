"""The claims file the post-build AC review reads, built by code from the committed AC record (Q2, phase 1).

``ac-claims.json`` sits next to ``ac-record.jsonl`` and lists, per item the run froze before the build: ``ac``
(``item-N`` when an exemption names none), ``kind``, ``new_text``, ``old_text`` (the catalog text AT THE MERGE-BASE,
never the record's own copy), ``decided_by``, ``confirmed``, ``files`` and ``grade``. No AI and no agent-written
field: every value is copied from the append-only record or read from git.

``grade`` says how far a ``diverges`` verdict on that item may go: ``reject`` for an item an operator confirmed or
code decided alone, ``warn`` for an unconfirmed ``auto`` assignment (and for a record that does not say). Phase 1 only
ever warns; the grade is carried so that a later phase can refuse on ``reject`` without changing the input.

:func:`judge` turns the claims plus the reviewer's per-AC verdicts into the warnings F11 prints. Stdlib + sibling libs.
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.ac_catalog import load_catalog
from lib.ac_record import read_records
from lib.ac_surface import read_blobs

__all__ = ["REJECT_GRADE", "build_claims", "claims_path", "judge", "write_claims"]

#: ``decided_by`` values whose per-AC divergence is reject-grade; ``auto`` (unconfirmed) and an unknown source are not.
REJECT_GRADE = ("operator", "code")
_PROMISING = ("restore", "unchanged")  # the promise to hold is the catalog text at the base


def claims_path(project_root: str | Path, run_id: str) -> Path:
    return Path(project_root) / ".shipwright" / "planning" / "iterate" / run_id / "ac-claims.json"


def _record_text(root: Path, run_id: str, head: str | None) -> str:
    rel = f".shipwright/planning/iterate/{run_id}/ac-record.jsonl"
    if head is None:
        try:
            return (root / rel).read_text(encoding="utf-8")
        except (OSError, ValueError):
            return ""
    return read_blobs(root, head, [rel])[rel] or ""


def _claim(n: int, it: dict, base_acs: dict) -> dict:
    kind = it.get("kind")
    ac = str(it.get("restores_ac") or it.get("ac") or "") if kind == "restore" else str(it.get("ac") or "")
    old = base_acs.get(ac) if ac else None
    new = it.get("new_text") or (old if kind in _PROMISING else None)
    by = it.get("decided_by") if it.get("decided_by") in ("operator", "auto", "code") else None
    confirmed = it.get("confirmed") if isinstance(it.get("confirmed"), bool) else None
    files = sorted(str(f) for f in it["files"]) if isinstance(it.get("files"), list) else []
    return {"ac": ac or f"item-{n}", "kind": kind, "new_text": new, "old_text": old, "decided_by": by, "confirmed": confirmed,
            "files": files, "grade": "reject" if by in REJECT_GRADE else "warn"}


def build_claims(project_root: str | Path, run_id: str, base: str, head: str | None = None) -> dict:
    """The claims of the run's LAST record line, read at ``head`` (None = working tree), with old texts from ``base``."""
    root = Path(project_root)
    records = read_records(root, run_id, _record_text(root, run_id, head))
    last = records[-1] if records else {}
    items = [i for i in last.get("items", []) if isinstance(i, dict)] if isinstance(last.get("items"), list) else []
    base_acs = load_catalog(root, base)["acs"] if items else {}
    return {"schema_version": 1, "run_id": run_id, "base": base, "head": head or "working-tree", "record_seq": last.get("seq"),
            "claims": [_claim(n, it, base_acs) for n, it in enumerate(items, 1)]}


def write_claims(project_root: str | Path, run_id: str, base: str, head: str | None = None) -> dict:
    """Build the claims once, write them beside the record (:func:`claims_path`) and return the document."""
    doc = build_claims(project_root, run_id, base, head)
    path = claims_path(project_root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return doc


def judge(claims: list[dict], verdicts: object) -> list[str]:
    """The warnings for the claims against the reviewer's ``ac_verdicts``; empty = every claim was reviewed and matches.

    No verdicts at all reads as "no AC review ran". A claim with no verdict is named; a ``diverges`` names its line and says
    whether its grade is reject or warning only; ``weakens`` on a change is named. Nothing here refuses anything.
    """
    rows = [v for v in verdicts if isinstance(v, dict) and v.get("verdict") in ("matches", "diverges")] if isinstance(verdicts, list) else []
    if not rows:
        return [f"no AC review ran: {len(claims)} claim(s) ({', '.join(c['ac'] for c in claims[:6])}) were not checked against the diff"] if claims else []
    by_ac: dict[str, dict] = {}
    for v in rows:  # a repeated reference merges: diverges if any entry diverges (its line and reason win), weakens if any weakens
        cur = by_ac.get(str(v.get("ac")))
        if cur is None:
            by_ac[str(v.get("ac"))] = dict(v)
            continue
        if v.get("verdict") == "diverges" and cur.get("verdict") != "diverges":
            cur.update(verdict="diverges", diff_location=v.get("diff_location"), reason=v.get("reason"))
        cur["weakens"] = True if (cur.get("weakens") is True or v.get("weakens") is True) else cur.get("weakens")
    out: list[str] = []
    for c in claims:
        v = by_ac.get(c["ac"])
        if v is None:
            out.append(f"{c['ac']} ({c['kind']}): the reviewer gave no verdict")
            continue
        if v.get("verdict") == "diverges":
            how = "reject-grade, would hold the change in a later phase" if c["grade"] == "reject" else "warning only: not confirmed by an operator"
            out.append(f"{c['ac']} ({c['kind']}) diverges [{how}] at {v.get('diff_location') or 'no line given'}: {v.get('reason') or 'no reason given'}")
        if v.get("weakens") is True and c["kind"] == "change":
            out.append(f"{c['ac']} (change): the new wording weakens a promise that held before")
    return out
