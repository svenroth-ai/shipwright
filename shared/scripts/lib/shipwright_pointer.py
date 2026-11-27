"""Recognise and render the root pointer stub ``shipwright_run_config.json`` becomes at the flip.

Campaign ``root-files-into-config``, BRIEF sections 11.5 (format, operator-signed 2026-11-27) and
14 (round-3 rules). Old plugins keep seeing a root ``shipwright_run_config.json``; from R3 on it is a
short plain-text stub that every old JSON reader rejects loudly. This module is the ONE recogniser
the resolver, the both-copies check, the R3 abort, the migration tool and CI share. It judges
CONTENT only; where a stub may legitimately sit (the repo root, never ``.shipwright/config/``) is
the caller's rule (R1c).

``classify`` is total - any bytes in, one :class:`Verdict` out, never an exception - and runs:

1. ``size`` = byte length with every CR removed (a UTF-8 BOM counts);
2. decode as ``utf-8-sig`` (a leading BOM is dropped); invalid UTF-8 -> ``not_stub``;
3. any line (split on ``\\n`` only) starting with a merge-conflict marker -> ``not_stub``;
4. the FIRST line, surrounding ASCII whitespace stripped (space, tab, CR, FF, VT - never NBSP,
   U+0085 or another BOM, so every port strips the same set), must fully match
   ``SHIPWRIGHT-POINTER/<n>`` with ``n`` ASCII digits without a leading zero (BRIEF 14.1's digits
   narrowed: ``/0`` and ``/01`` name no format, non-ASCII digits are not digits); otherwise
   ``not_stub`` (also a lower-case signature, a blank first line, the signature on line 2);
5. ``size > MAX_BYTES`` -> ``edited`` (checked before the version: an edited stub is reported
   as edited whatever it claims);
6. ``n > 1`` -> ``too_new`` (any length: a future format is never read as config); ``n == 1`` ->
   ``stub``. ``Verdict.version`` is ``None`` for a number too long to be meaningful (> 18 digits).

Apart from the conflict-marker scan (step 3), lines after a valid first line are not inspected (the
rule is signature + size cap, 14.1): text appended to a stub under the cap, JSON included, is a stub.

Nothing here returns a path: ``moved_to:`` is human text, never followed (BRIEF 14.2). Stdlib
only, no intra-package import (the module may load under several names, like the resolver, so
:class:`Verdict` is a plain NamedTuple and callers compare ``verdict.kind`` strings).
"""

from __future__ import annotations

import re
from typing import NamedTuple

SIGNATURE = "SHIPWRIGHT-POINTER"
FORMAT_VERSION = 1
MAX_BYTES = 512

STUB = "stub"
TOO_NEW = "too_new"
EDITED = "edited"
NOT_STUB = "not_stub"

_FIRST_LINE = re.compile(SIGNATURE + r"/([1-9][0-9]*)", re.ASCII)
_CONFLICT = ("<<<<<<<", "=======", ">>>>>>>")
# semver.org 2.0.0 grammar (no leading zeros in numeric identifiers, no empty identifiers)
_NUM = r"(?:0|[1-9][0-9]*)"
_PRE = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
_SEMVER = re.compile(rf"{_NUM}\.{_NUM}\.{_NUM}(?:-{_PRE}(?:\.{_PRE})*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?",
                     re.ASCII)


class Verdict(NamedTuple):
    kind: str
    version: int | None = None


def classify(data: bytes) -> Verdict:
    """Classify a root ``shipwright_run_config.json``'s bytes (see the module docstring)."""
    try:
        size = len(data.replace(b"\r", b""))
        text = data.decode("utf-8-sig")
    except (UnicodeDecodeError, AttributeError, TypeError):
        return Verdict(NOT_STUB)
    lines = text.split("\n")
    if any(line.startswith(_CONFLICT) for line in lines):
        return Verdict(NOT_STUB)
    m = _FIRST_LINE.fullmatch(lines[0].strip(" \t\r\f\v"))
    if m is None:
        return Verdict(NOT_STUB)
    digits = m.group(1)
    version = int(digits) if len(digits) <= 18 else None
    if size > MAX_BYTES:
        return Verdict(EDITED, version)
    return Verdict(STUB if digits == str(FORMAT_VERSION) else TOO_NEW, version)


def render(min_plugin_version: str) -> bytes:
    """The stub text of BRIEF 11.5 (ASCII, LF, at most :data:`MAX_BYTES`) for the flip release
    *min_plugin_version* (a SemVer string; anything else raises ``ValueError``)."""
    if not isinstance(min_plugin_version, str) or not _SEMVER.fullmatch(min_plugin_version):
        raise ValueError(f"min_plugin_version must be a SemVer string, got {min_plugin_version!r}")
    text = (
        f"{SIGNATURE}/{FORMAT_VERSION}\n"
        "moved_to: .shipwright/config/\n"
        f"min_plugin_version: {min_plugin_version}\n"
        "This file is a stub left so older Shipwright plugins still recognise this project. "
        "Shipwright now keeps its configuration in .shipwright/config/. "
        "Update the Shipwright plugins; do not edit or delete this file.\n"
    )
    data = text.encode("ascii")
    if len(data) > MAX_BYTES:
        raise ValueError(f"stub would be {len(data)} bytes, over the {MAX_BYTES}-byte cap")
    return data
