#!/usr/bin/env python3
"""Treat a coverage manifest read from a file as UNTRUSTED input.

We write the manifest, so it is tempting to trust it on the way back in. But
``generate_security_report.py --input <artifact>`` and `scan.py
--input-from-cache <artifact>` both take it from a caller-supplied file, and its
`class` / `tool` / `status` strings flow into two dangerous places:

- a Markdown report an operator reads — where a newline can escape a blockquote
  or add table rows;
- the **launch payload of a triage card**, which the agent that executes the card
  reads back as INSTRUCTIONS — where a newline plus imperative text opens a new
  instruction line.

So the manifest is normalized at the boundary where it enters from a file, and
every label is flattened at the single chokepoint that renders it
(``scan_coverage.class_label``). Hardening only the obviously caller-supplied
values (``--repo``, the report path) and trusting the manifest was the gap the
PR-head review found.
"""

from __future__ import annotations

import re
from typing import Any

# Newline above all, but every C0/C7F control character: they break markdown
# structure and payload line boundaries alike.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")

TEXT_CAP = 160
DETAIL_CAP = 400

# Mirrors scan_coverage.COVERAGE_STATUSES. Duplicated rather than imported
# because the dependency runs the other way — scan_coverage imports THIS module,
# so importing back would cycle. The pair is pinned by
# tests/test_coverage_untrusted_manifest.py::TestSanitizeCoverage
# ::test_the_vocabulary_matches_scan_coverage.
VALID_STATUSES: frozenset[str] = frozenset(
    {"covered", "degraded", "not_requested", "not_available"})


def safe_text(value: Any, cap: int = TEXT_CAP) -> str:
    """Flatten control characters to a single space and cap the length."""
    return _CONTROL_CHARS.sub(" ", str(value)).strip()[:cap]


def sanitize_coverage(rows: Any) -> list[dict[str, Any]]:
    """Normalize a file-sourced manifest into safe scalar rows.

    - Non-list input yields ``[]``; non-dict rows are dropped. A sidecar
      containing ``{"coverage": ["bad-row"]}`` used to crash report generation
      with an ``AttributeError``, which defeated the whole point of tolerating
      malformed and pre-feature artifacts.
    - Every field becomes a capped, control-character-free string. ``tool`` and
      ``detail`` stay ``None`` when absent, so a caller can still tell "no tool"
      from "empty string".
    - An out-of-vocabulary ``status`` is COERCED to ``degraded`` and the original
      is preserved in ``detail``. AC-1 makes the closed vocabulary a schema
      guarantee, and these rows get re-emitted — ``scan.py --input-from-cache``
      writes a fresh ``findings.json`` from them — so passing an invalid status
      through would launder it into a new artifact that downstream readers (a CI
      jq gate, the WebUI) are entitled to assume is well-formed. ``degraded`` is
      the honest coercion: a row we cannot interpret is a row we cannot trust,
      and the operator still sees what the producer actually wrote.
    """
    out: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        tool = row.get("tool")
        detail = safe_text(row["detail"], DETAIL_CAP) if row.get("detail") else None
        raw_status = safe_text(row["status"]) if row.get("status") else ""
        if raw_status in VALID_STATUSES:
            status = raw_status
        else:
            status = "degraded"
            note = (f"status {raw_status!r} is not in the closed vocabulary"
                    if raw_status else "the producer recorded no status")
            # Re-cap AFTER composing: prepending the note to an already-capped
            # detail would otherwise push the field over DETAIL_CAP.
            detail = safe_text(f"{note}; {detail}" if detail else note, DETAIL_CAP)
        out.append({
            "class": safe_text(row.get("class", "?")),
            "tool": safe_text(tool) if tool else None,
            "status": status,
            "detail": detail,
        })
    return out
