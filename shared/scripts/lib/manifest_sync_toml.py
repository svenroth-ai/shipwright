"""``pyproject_toml`` and ``uv_lock`` format support for ``manifest_sync_core``.

A Python project keeps its version in ``pyproject.toml`` (``[project].version``)
and, with uv, a second time in ``uv.lock`` (the ``version`` of the project's own
``[[package]]``, the one whose ``source`` is ``{ virtual = "." }`` or
``{ editable = "." }``). FINDINGS D111: neither was a declarable manifest, so a
release bumped every plugin manifest and left the root files behind.

Reads use ``tomllib``. Writes are line edits scoped to the target table: only a
``version = "<current>"`` line between the table's header and the next header is
replaced, so CRLF/LF, comments and every other byte survive. The result is
parsed again with ``tomllib`` and must equal the original document with only that
one value changed; anything else (a version line the scan cannot place, a
``version`` key of another table) is refused before a byte is written. Lines
inside a multi-line string are text: never a header, never the version line.
A ``[tool.*]`` version, the lock's own top-level ``version`` and every
dependency entry in the lock are never touched.
"""

from __future__ import annotations

import copy
import re

from .manifest_sync_errors import ManifestSyncError

__all__ = ["TOML_FORMATS", "read_toml_version", "render_toml_write"]

TOML_FORMATS = ("pyproject_toml", "uv_lock")

_ROOT_SOURCES = ("virtual", "editable")
_ANY_HEADER = re.compile(r"""^\s*\[\[?\s*[A-Za-z0-9_.\-"' ]+\s*\]\]?\s*(#.*)?\r?$""")  # a header, not an array row
_TABLE_HEADER = re.compile(r"^\s*\[\s*project\s*\]\s*(#.*)?\r?$")
_PACKAGE_HEADER = re.compile(r"^\s*\[\[\s*package\s*\]\]\s*(#.*)?\r?$")
_PLAIN_VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def _parse(text: str) -> dict:
    import tomllib  # here, not at module level: a JSON-only project never needs it

    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ManifestSyncError("parse_error", f"invalid TOML: {exc}") from exc


def _checked_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ManifestSyncError("invalid_version_type", f"{label} is not a string: {value!r}")
    return value


def _pyproject_version(doc: dict) -> str:
    project = doc.get("project")
    if not isinstance(project, dict):
        raise ManifestSyncError("missing_version_field", "no [project] table")
    if "version" not in project:
        dynamic = project.get("dynamic")
        hint = " (it is declared dynamic, which is not supported)" if isinstance(dynamic, list) and "version" in dynamic else ""
        raise ManifestSyncError("missing_version_field", f"no version in [project]{hint}")
    return _checked_string(project["version"], "[project].version")


def _root_package_index(doc: dict) -> int:
    """Index of the project's own package in ``doc["package"]``: exactly one
    entry whose ``source`` is ``virtual`` or ``editable`` at ``"."``."""
    packages = doc.get("package")
    if not isinstance(packages, list):
        raise ManifestSyncError("missing_root_package", "uv.lock has no [[package]] entries")
    hits = [
        i for i, pkg in enumerate(packages)
        if isinstance(pkg, dict) and isinstance(pkg.get("source"), dict)
        and any(pkg["source"].get(kind) == "." for kind in _ROOT_SOURCES)
    ]
    if not hits:
        raise ManifestSyncError(
            "missing_root_package", 'no [[package]] with source { virtual = "." } or { editable = "." }'
        )
    if len(hits) > 1:
        raise ManifestSyncError("ambiguous_manifest_structure", "more than one root [[package]] in uv.lock")
    return hits[0]


def _lock_version(doc: dict) -> str:
    index = _root_package_index(doc)  # first: it refuses a lock with no package array
    pkg = doc["package"][index]
    if "version" not in pkg:
        raise ManifestSyncError("missing_version_field", f"root package {pkg.get('name')!r} has no version")
    return _checked_string(pkg["version"], "root package version")


def read_toml_version(text: str, fmt: str) -> str:
    """The project version of a ``pyproject_toml`` / ``uv_lock`` manifest."""
    doc = _parse(text)
    return _pyproject_version(doc) if fmt == "pyproject_toml" else _lock_version(doc)


def _starts_inside_string(lines: list[str]) -> list[bool]:
    """Per line: does it begin inside a multi-line string (``\"\"\"`` / ``'''``)?
    Such a line is text, never a header or a key. A rough count of the
    delimiters; whatever it misjudges, the re-parse check refuses."""
    inside, open_delim, flags = False, "", []
    for line in lines:
        flags.append(inside)
        for m in re.finditer(r'"""|\'\'\'', line):
            if not inside:
                inside, open_delim = True, m.group()
            elif m.group() == open_delim:
                inside = False
    return flags


def _table_span(lines: list[str], text_line: list[bool], header: re.Pattern[str], occurrence: int) -> tuple[int, int]:
    """``(first, end)`` line indexes of the body of the ``occurrence``-th table
    whose header matches ``header``: from the line after it to the next header.
    ``text_line`` marks the lines inside a multi-line string."""
    starts = [i for i, line in enumerate(lines) if not text_line[i] and header.match(line)]
    if occurrence >= len(starts):
        raise ManifestSyncError("ambiguous_manifest_structure", "cannot locate the table that holds the version")
    first = starts[occurrence] + 1
    end = next((i for i in range(first, len(lines)) if not text_line[i] and _ANY_HEADER.match(lines[i])), len(lines))
    return first, end


def render_toml_write(original_text: str, fmt: str, current_version: str, new_version: str) -> tuple[str, bool]:
    """Replace the one version line of the target table. Always surgical:
    ``reformatted`` is always False; a line that cannot be placed is refused.
    Only a plain ``X.Y.Z`` is written: a SemVer pre-release or build part is
    not always valid PEP 440, and uv would then reject the project file."""
    if not _PLAIN_VERSION.match(new_version):
        raise ManifestSyncError(
            "unsupported_version_for_format", f"{fmt} takes only a plain X.Y.Z version, not {new_version!r}"
        )
    doc = _parse(original_text)
    if read_toml_version(original_text, fmt) != current_version:
        raise ManifestSyncError("ambiguous_manifest_structure", "the version changed under the sync")
    lines = original_text.split("\n")
    text_line = _starts_inside_string(lines)
    if fmt == "pyproject_toml":
        first, end = _table_span(lines, text_line, _TABLE_HEADER, 0)
    else:
        index = _root_package_index(doc)
        # The k-th [[package]] header is the k-th entry of the package array (uv writes no other).
        first, end = _table_span(lines, text_line, _PACKAGE_HEADER, index)

    line_re = re.compile(r"^(\s*version\s*=\s*)([\"'])" + re.escape(current_version) + r"\2(\s*(?:#.*)?\r?)$")
    hits = [i for i in range(first, end) if not text_line[i] and line_re.match(lines[i])]
    if len(hits) != 1:
        raise ManifestSyncError(
            "ambiguous_manifest_structure",
            f"expected one version line in the target table, found {len(hits)}",
        )
    m = line_re.match(lines[hits[0]])
    lines[hits[0]] = f"{m.group(1)}{m.group(2)}{new_version}{m.group(2)}{m.group(3)}"
    new_text = "\n".join(lines)

    expected = copy.deepcopy(doc)
    if fmt == "pyproject_toml":
        expected["project"]["version"] = new_version
    else:
        expected["package"][index]["version"] = new_version
    if _parse(new_text) != expected:
        raise ManifestSyncError(
            "ambiguous_manifest_structure", "the edited file does not parse back to only the version change"
        )
    return new_text, False
