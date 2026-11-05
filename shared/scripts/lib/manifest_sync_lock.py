"""``package_lock_json`` format support for ``manifest_sync_core``.

An npm ``package-lock.json`` (lockfileVersion 2/3) carries the project's own
version twice: top-level ``"version"`` and ``packages[""].version``. Neither is
declarable via ``package_json`` (which only touches one field), so the lock
stayed on the old version after a release and the next ``npm install``
rewrote it, leaving a dirty tree. This module syncs both in one step.

``packages`` / ``packages[""]`` may legitimately be absent (lockfileVersion 1);
then only the top-level field is compared and written. Writes are surgical:
the exact string spans are replaced, so CRLF/LF and indentation survive
byte-for-byte. Dependency entries (``packages["node_modules/x"].version``)
are never touched.
"""

from __future__ import annotations

import json

from .manifest_sync_errors import ManifestSyncError

__all__ = [
    "assert_unambiguous",
    "find_stale_root_package",
    "render_lock_write",
    "validate_lock_structure",
]

_TOP = ("version",)
_ROOT_PKG = ("packages", "", "version")
_LABELS = {_TOP: '"version"', _ROOT_PKG: 'packages[""].version'}


def validate_lock_structure(parsed: dict) -> None:
    """``packages`` (when present) must be an object, and ``packages[""]``
    (when present) an object whose ``version`` (when present) is a string."""
    if "packages" not in parsed:
        return
    packages = parsed["packages"]
    if not isinstance(packages, dict):
        raise ManifestSyncError("invalid_manifest_structure", '"packages" must be a JSON object')
    if "" not in packages:
        return
    root = packages[""]
    if not isinstance(root, dict):
        raise ManifestSyncError("invalid_manifest_structure", 'packages[""] must be a JSON object')
    if "version" in root and not isinstance(root["version"], str):
        raise ManifestSyncError(
            "invalid_manifest_structure", 'packages[""].version is not a string'
        )


def find_stale_root_package(parsed: dict, target_version: str) -> bool:
    """True iff ``packages[""]`` carries a ``version`` other than the target.
    A missing ``packages``/``packages[""]``/``version`` is not stale."""
    root = (parsed.get("packages") or {}).get("")
    return isinstance(root, dict) and "version" in root and root["version"] != target_version


def _locate_string_values(text: str) -> dict[tuple[str, ...], list[tuple[int, int]]]:
    """Walk the (valid) JSON text and return the (start, end) span of the
    *contents* of every string value at the two interesting key paths.
    Spans, not regexes, so a dependency's identical version can never be
    mistaken."""
    wanted = {_TOP, _ROOT_PKG}
    found: dict[tuple[str, ...], list[tuple[int, int]]] = {}
    stack: list[dict] = []  # frames: {"obj": bool, "key": str|None, "expect_key": bool}
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            top = stack[-1] if stack else None
            if top is not None and top["obj"] and top["expect_key"]:
                top["key"] = json.loads(text[i : j + 1])
                top["expect_key"] = False
            else:
                path = tuple(f["key"] if f["obj"] else "\0" for f in stack)
                if path in wanted:
                    found.setdefault(path, []).append((i + 1, j))
            i = j + 1
            continue
        if c in "{[":
            stack.append({"obj": c == "{", "key": None, "expect_key": c == "{"})
        elif c in "}]":
            stack.pop()
        elif c == "," and stack and stack[-1]["obj"]:
            stack[-1]["expect_key"] = True
        i += 1
    return found


def _checked_spans(text: str) -> dict[tuple[str, ...], list[tuple[int, int]]]:
    """Spans for the two target paths. Validates the JSON first (the scanner
    assumes well-formed input) and refuses a duplicated target key."""
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManifestSyncError("parse_error", f"invalid JSON: {exc}") from exc
    spans = _locate_string_values(text)
    for path, hits in spans.items():
        if len(hits) > 1:
            raise ManifestSyncError(
                "ambiguous_manifest_structure", f"duplicate {_LABELS[path]} key"
            )
    return spans


def assert_unambiguous(text: str) -> None:
    """Read-path twin of the write path's duplicate-key refusal, so verify
    and write reject the same input."""
    _checked_spans(text)


def render_lock_write(original_text: str, new_version: str) -> tuple[str, bool]:
    """Replace top-level ``version`` and (if present) ``packages[""].version``
    with ``new_version``. Always surgical: ``reformatted`` is always False."""
    spans = _checked_spans(original_text)
    if _TOP not in spans:
        raise ManifestSyncError("missing_version_field", 'no top-level "version" key')
    text = original_text
    for start, end in sorted((h[0] for h in spans.values()), reverse=True):
        text = text[:start] + new_version + text[end:]
    return text, False
