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
    - An out-of-vocabulary ``status`` is preserved verbatim rather than coerced
      to something plausible: it is a producer bug the operator should SEE, and
      ``scan_coverage.is_complete`` already refuses to call it covered.
    """
    out: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        tool = row.get("tool")
        detail = row.get("detail")
        status = row.get("status")
        out.append({
            "class": safe_text(row.get("class", "?")),
            "tool": safe_text(tool) if tool else None,
            # An ABSENT status becomes "", never the string "None" — rendering
            # "None" would read like a status value the vocabulary defines.
            "status": safe_text(status) if status else "",
            "detail": safe_text(detail, DETAIL_CAP) if detail else None,
        })
    return out
