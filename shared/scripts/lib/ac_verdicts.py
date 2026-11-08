"""The spec-reviewer's per-AC verdicts (Q2, phase 1): read from its reply, cleaned, and carried onto the ``spec`` review row.

When the reviewer is given the claims file (:mod:`lib.ac_claims`) its reply carries ``ac_verdicts``: one
``{ac, verdict: matches|diverges, diff_location, reason, weakens}`` per claim. :func:`verdict_fields` is what
``record_review_pass.py`` merges into the row of a COMPLETED ``spec`` pass; every other row type, a pass that did not run
and a reply that cannot be read yield nothing, so recording never fails on this and a reply without the key records
exactly as before. Entries that are not well formed are dropped (F11 then names the claim as unreviewed), text is
bounded, and the count is capped. The verdict is the reviewer's judgement: evidence for a person, not proof.
"""

from __future__ import annotations

from pathlib import Path

from lib.review_findings import ReviewFindingsError, extract_json_payload

__all__ = ["MAX_ENTRIES", "MAX_REASON", "VERDICTS", "clean", "verdict_fields"]

VERDICTS = ("matches", "diverges")
MAX_ENTRIES = 50
MAX_REASON = 500
_MAX_REF = 80
_MAX_LOCATION = 200


def clean(raw: object) -> list[dict]:
    """The well-formed entries of ``raw`` (at most :data:`MAX_ENTRIES`), each with all five keys."""
    out: list[dict] = []
    for v in raw if isinstance(raw, list) else []:
        if len(out) >= MAX_ENTRIES:
            break
        if not isinstance(v, dict) or v.get("verdict") not in VERDICTS or not isinstance(v.get("ac"), str) or not v["ac"].strip():
            continue
        loc = v.get("diff_location")
        out.append({"ac": v["ac"].strip()[:_MAX_REF], "verdict": v["verdict"],
                    "diff_location": loc.strip()[:_MAX_LOCATION] if isinstance(loc, str) and loc.strip() else None,
                    "reason": str(v.get("reason") or "")[:MAX_REASON], "weakens": v["weakens"] if isinstance(v.get("weakens"), bool) else None})
    return out


def verdict_fields(review_type: str, status: str, payload_file: str | None) -> dict:
    """``{"ac_verdicts": [...]}`` for a completed ``spec`` pass whose reply carries some, else ``{}``."""
    if review_type != "spec" or status != "completed" or not payload_file:
        return {}
    try:
        payload = extract_json_payload(Path(payload_file).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ReviewFindingsError):
        return {}
    rows = clean(payload.get("ac_verdicts")) if isinstance(payload, dict) else []
    return {"ac_verdicts": rows} if rows else {}
