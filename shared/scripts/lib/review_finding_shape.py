"""The normalized finding shape, shared by every adapter.

Its own module so :mod:`lib.review_findings` (native adapters) and
:mod:`lib.review_prose` (external prose) can both build findings without one
importing the other.

    {"severity": "high|medium|low"|None, "category": str|None, "file": str|None,
     "line": int|None, "finding": str, "suggestion": str|None, "source": str}

Every coercion here fails toward ``None`` rather than toward a guess. A severity
this module does not recognise becomes ``None``, not ``"medium"`` — the record
exists to say what a review actually found, and a plausible invented value is
worse than an honest blank.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "MAX_FINDINGS",
    "MAX_TEXT_CHARS",
    "SEVERITY_LEVELS",
    "TRUNCATION_MARKER",
    "coerce_line",
    "coerce_severity",
    "coerce_text",
    "make_finding",
]

#: Bound a pathological payload. Far above any real review — a payload that
#: exceeds it is REJECTED by the adapters rather than silently shortened, so a
#: partial review can never be recorded as a complete one.
MAX_FINDINGS = 200
MAX_TEXT_CHARS = 4000

#: Appended when a single finding's text is shortened, so a reader can see that
#: what they are looking at is not the whole thing.
TRUNCATION_MARKER = " […truncated]"

SEVERITY_LEVELS = ("high", "medium", "low")

#: Anchored at the START of the value, not searched anywhere inside it. A
#: substring scan turns "medium — would be high if the lock were shared" into
#: "high" and "not high" into "high": overstating a severity the reviewer never
#: gave is the same fabrication the null-severity rule exists to prevent.
_SEVERITY_RE = re.compile(r"^\W*(high|medium|low)\b", re.IGNORECASE)


def coerce_text(value: Any, limit: int = MAX_TEXT_CHARS) -> str | None:
    """Trim and bound. A shortened value carries :data:`TRUNCATION_MARKER` so
    truncation is visible rather than silent."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if len(stripped) <= limit:
        return stripped
    return stripped[: max(0, limit - len(TRUNCATION_MARKER))] + TRUNCATION_MARKER


def coerce_severity(value: Any) -> str | None:
    """Normalize onto the closed vocabulary; anything else becomes ``None``
    rather than an invented level."""
    if not isinstance(value, str):
        return None
    match = _SEVERITY_RE.match(value.strip())
    return match.group(1).lower() if match else None


def coerce_line(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip()) or None
    return None


def make_finding(
    *,
    finding: str,
    source: str,
    severity: Any = None,
    category: Any = None,
    file: Any = None,
    line: Any = None,
    suggestion: Any = None,
) -> dict[str, Any]:
    return {
        "severity": coerce_severity(severity),
        "category": coerce_text(category, 120),
        "file": coerce_text(file, 400),
        "line": coerce_line(line),
        "finding": finding,
        "suggestion": coerce_text(suggestion),
        "source": source,
    }
