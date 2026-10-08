"""Per-entry checks of the review record that :mod:`lib.review_record_schema` delegates.

Split out so the schema module stays at its size cap: the finding shape check
that used to live there, and the closed-vocabulary ``reason_code`` an entry may
carry next to its free-text ``disposition``.

``reason_code`` is the machine-readable half of a ``not_run`` /
``not_applicable`` answer. A record without it is LEGACY (a free-text
disposition only) and stays valid: 65+ immutable, git-tracked histories were
written that way. A record WITH it must use a code from the
``review_not_run`` family (``lib.reason_codes``).
"""

from __future__ import annotations

from typing import Any

try:
    from .reason_codes import reason_code_error
except ImportError:  # loaded with lib/ itself on sys.path
    from reason_codes import reason_code_error  # type: ignore[no-redef]

__all__ = ["REVIEW_FAMILY", "SEVERITIES", "default_disposition", "reason_code_entry_error", "validate_finding"]

REVIEW_FAMILY = "review_not_run"
_CODE_STATUSES = frozenset({"not_run", "not_applicable"})
SEVERITIES = frozenset({"high", "medium", "low"})


def default_disposition(reason_code: str) -> str:
    """A disposition that names the rule, for a writer given only a code."""
    return f"closed by reason_code {reason_code}"


def reason_code_entry_error(entry: dict[str, Any], where: str) -> str | None:
    """``None`` when ``entry`` carries no ``reason_code`` or a legal one."""
    if entry.get("reason_code") is None:
        return None
    if entry.get("status") not in _CODE_STATUSES:
        return f"{where}.reason_code is only meaningful on a not_run / not_applicable row"
    return reason_code_error(REVIEW_FAMILY, entry["reason_code"], where=f"{where}.reason_code")


def validate_finding(item: Any, where: str) -> str | None:
    if not isinstance(item, dict):
        return f"{where}: finding is not an object"
    text = item.get("finding")
    if not isinstance(text, str) or not text.strip():
        return f"{where}: finding text is empty"
    severity = item.get("severity")
    if severity is not None and severity not in SEVERITIES:
        return f"{where}: severity {severity!r} is not one of {sorted(SEVERITIES)} or null"
    line = item.get("line")
    if line is not None and (isinstance(line, bool) or not isinstance(line, int)):
        return f"{where}: line must be an integer or null"
    for key in ("file", "suggestion", "category", "source"):
        value = item.get(key)
        if value is not None and not isinstance(value, str):
            return f"{where}: {key} must be a string or null"
    return None
