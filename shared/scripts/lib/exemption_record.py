"""The per-exemption record carried by the F5c iterate entry.

Every gate that accepts a per-test exemption (an untagged test, a mechanical
refactor ...) records it *individually* under the entry's ``exemptions`` key, so
the number is countable and printable instead of being buried in prose. A review
pass closed ``not_run`` is NOT an exemption: it explains itself through its own
``reason_code`` in ``reviews.json``::

    "exemptions": {
        "count": 2,
        "items": [
            {"kind": "test_exemption", "scope": "tests/test_x.py::test_helper",
             "reason_code": "fixture-or-helper"},
            ...
        ]
    }

``kind`` names the reason-code family (``lib.reason_codes``); ``scope`` says
what was exempted and must be a path-safe string (no absolute path, no ``..``
segment, no control character). ``count`` repeats ``len(items)`` on purpose: a
reader that only wants the number does not parse the list, and a writer that
cannot keep the two consistent is refused. An entry without the key is legacy:
it validates, and its summary line says ``not recorded (legacy entry)`` - never
``0``, which would be indistinguishable from a recorded zero.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

try:
    from .reason_codes import EXEMPTION_FAMILIES, reason_code_error
except ImportError:  # loaded with lib/ itself on sys.path
    from reason_codes import EXEMPTION_FAMILIES, reason_code_error  # type: ignore[no-redef]

__all__ = ["LEGACY_SUMMARY", "entry_exemptions_error", "entry_summary_line", "exemption_counts", "exemptions_error", "format_summary_line"]

_MAX_SCOPE_CHARS = 300
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_ITEM_KEYS = frozenset({"kind", "scope", "reason_code"})
#: What F12 / the PR body print for an entry that predates the ``exemptions`` block.
LEGACY_SUMMARY = "not recorded (legacy entry)"


def _scope_error(scope: Any) -> str | None:
    if not isinstance(scope, str) or not scope.strip():
        return "scope must be a non-empty string"
    if len(scope) > _MAX_SCOPE_CHARS:
        return f"scope is longer than {_MAX_SCOPE_CHARS} characters"
    if _CONTROL_RE.search(scope):
        return "scope contains a control character"
    path = scope.split("::", 1)[0].replace("\\", "/")
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        return "scope must be project-relative, not an absolute path"
    if ".." in re.split(r"[\\/]|::", scope):
        return "scope must not climb out of the project with '..'"
    return None


def _item_error(item: Any, where: str) -> str | None:
    if not isinstance(item, dict):
        return f"{where} is not an object"
    if set(item) != _ITEM_KEYS:
        return f"{where} must carry exactly {sorted(_ITEM_KEYS)}"
    err = _scope_error(item["scope"])
    if err:
        return f"{where}: {err}"
    kind = item["kind"]
    if not isinstance(kind, str):
        return f"{where}.kind must be a string"
    if kind not in EXEMPTION_FAMILIES:
        return f"{where}.kind {kind!r} is not an exemption family {sorted(EXEMPTION_FAMILIES)} (review_not_run / untestable answers are not exemptions)"
    return reason_code_error(kind, item["reason_code"], where=f"{where}.reason_code")


def exemptions_error(block: Any) -> str | None:
    """``None`` for a well-formed block, else why not. A present-but-null block is malformed:
    absence is expressed by the key missing (see :func:`entry_exemptions_error`)."""
    if not isinstance(block, dict):
        return "exemptions must be an object {count, items}"
    items = block.get("items")
    if not isinstance(items, list):
        return "exemptions.items must be a list"
    count = block.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count != len(items):
        return f"exemptions.count is {count!r} but exemptions.items has {len(items)} item(s)"
    for index, item in enumerate(items):
        err = _item_error(item, f"exemptions.items[{index}]")
        if err:
            return err
    return None


def entry_exemptions_error(entry: dict[str, Any]) -> str | None:
    """Validate an F5c entry's block; a MISSING key is legacy and valid, an explicit null is not."""
    return exemptions_error(entry["exemptions"]) if "exemptions" in entry else None


def entry_summary_line(entry: dict[str, Any]) -> str:
    """:func:`format_summary_line` for a whole entry; a missing key prints :data:`LEGACY_SUMMARY`."""
    return format_summary_line(entry["exemptions"]) if "exemptions" in entry else LEGACY_SUMMARY


def exemption_counts(block: Any) -> dict[str, int]:
    """Items per ``reason_code`` - empty for an absent or malformed block."""
    if exemptions_error(block):
        return {}
    return dict(sorted(Counter(i["reason_code"] for i in block["items"]).items()))


def format_summary_line(block: Any) -> str:
    """The one line F12 and the PR body print, e.g. ``2 (fixture-or-helper: 2)``."""
    err = exemptions_error(block)
    if err:
        return f"INVALID - {err}"
    by_code = exemption_counts(block)
    total = sum(by_code.values())
    if not total:
        return "0"
    return f"{total} (" + ", ".join(f"{code}: {n}" for code, n in by_code.items()) + ")"
