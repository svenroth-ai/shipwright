"""The ``SHIPWRIGHT_TEST_*`` seams of the release path, read in ONE place.

A seam lets an offline test drive the real release scripts without GitHub or a
model. Every seam is an environment variable named ``SHIPWRIGHT_TEST_*``, is
read only in this file, and is **inert when unset** (or empty): the default
path is byte-for-byte what it was before the seam existed.

=========================================  =====================================
``SHIPWRIGHT_TEST_GH_ARGV_PREFIX``         JSON array of strings, e.g.
                                           ``["python", "/x/gh_stub.py"]``. It
                                           replaces the leading ``gh`` of every
                                           ``gh`` call the release path makes
                                           (``setup-changelog.py``,
                                           ``create_github_release.py``). An
                                           argv prefix, not a ``.cmd`` shim: on
                                           Windows ``gh`` is spawned as
                                           ``["gh", ...]``, which cannot run a
                                           batch file.
``SHIPWRIGHT_TEST_CONDENSE_FIXTURE_MODEL`` ``ok`` or ``bad-shape``. The release
                                           notes condensation returns fixed
                                           fixture text instead of calling a
                                           model: ``ok`` passes the shape
                                           check, ``bad-shape`` fails it.
=========================================  =====================================

**Publish guard.** Fixture text carries :data:`FIXTURE_MARKER`.
``create_github_release`` refuses a notes file that contains the marker unless
the ``gh`` seam is also set, so a stray condensation variable can never put
fixture notes on a real release page (:func:`fixture_notes_refusal`).

A set-but-malformed value raises :class:`SeamError` rather than being ignored:
a test that believes it is driving a stub must not silently reach the real
``gh``. Known limit: the condensation script loads ``.env.local`` into the process
environment, so a seam set there is a seam set. Seams belong in the process
environment of a test; nothing here distinguishes the two sources.

**Why top level, not ``lib/``:** same reason as ``repo_identity.py`` (ADR-045).
This file is consumed by a plugin's ``scripts/checks`` and by
``shared/scripts/tools``; both would bind ``sys.modules['lib']`` to whichever
package won the race. It imports only the standard library.
"""

from __future__ import annotations

import json
import os
from pathlib import PurePath

GH_ARGV_PREFIX_ENV = "SHIPWRIGHT_TEST_GH_ARGV_PREFIX"
CONDENSE_FIXTURE_ENV = "SHIPWRIGHT_TEST_CONDENSE_FIXTURE_MODEL"

SEAM_ENV_VARS = (GH_ARGV_PREFIX_ENV, CONDENSE_FIXTURE_ENV)

FIXTURE_MODES = ("ok", "bad-shape")

# Plain words on purpose: the notes sanitizer keeps them verbatim (no @, #,
# link or HTML form for it to rewrite), so the marker survives to the file the
# publish guard reads.
FIXTURE_MARKER = "SHIPWRIGHT-TEST-FIXTURE-NOTES-7c41e9d2b8a05f36 (test seam output, no model wrote this)."


class SeamError(ValueError):
    """A ``SHIPWRIGHT_TEST_*`` variable is set but its value is unusable."""


def _read(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None  # unset and empty are the same: inert


def gh_seam_active() -> bool:
    return _read(GH_ARGV_PREFIX_ENV) is not None


def gh_argv_prefix() -> list[str]:
    """The argv prefix every ``gh`` call starts with: ``["gh"]`` unless seamed."""
    raw = _read(GH_ARGV_PREFIX_ENV)
    if raw is None:
        return ["gh"]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SeamError(f"{GH_ARGV_PREFIX_ENV} is not valid JSON: {exc.msg}") from exc
    if (not isinstance(parsed, list) or not parsed
            or not all(isinstance(item, str) and item for item in parsed)):
        raise SeamError(f"{GH_ARGV_PREFIX_ENV} must be a non-empty JSON array of non-empty strings")
    if any(ch < " " for item in parsed for ch in item):
        # An unescaped Windows path in JSON ("C:\tools\new") parses \t and \n into control characters.
        raise SeamError(f"{GH_ARGV_PREFIX_ENV} holds a control character: escape backslashes or use forward slashes")
    if PurePath(parsed[0].replace("\\", "/")).stem.lower() == "gh":
        # The publish guard trusts "the gh seam is set": a prefix that IS the real gh would defeat it.
        # A typo-level check on argv[0] only: a deliberate wrapper (env, cmd /c) is not caught.
        raise SeamError(f"{GH_ARGV_PREFIX_ENV} must lead with a stub interpreter, never the real gh")
    return list(parsed)


def gh_command(*args: str) -> list[str]:
    """The full argv for ``gh <args>``: the one place a ``gh`` call is built."""
    return [*gh_argv_prefix(), *args]


def condense_fixture_mode() -> str | None:
    raw = _read(CONDENSE_FIXTURE_ENV)
    if raw is None:
        return None
    if raw not in FIXTURE_MODES:
        raise SeamError(f"{CONDENSE_FIXTURE_ENV} must be one of {', '.join(FIXTURE_MODES)}")
    return raw


def fixture_notes(version: str, mode: str) -> str:
    """The fixture model's answer: the same text every time for one version."""
    heading = "Highlights" if mode == "ok" else "Release Summary"  # not in the allowed vocabulary
    return f"## {heading}\n\nRelease {version}. {FIXTURE_MARKER}\n"


def fixture_notes_refusal(notes_text: str) -> str | None:
    """A reason to refuse publishing ``notes_text``, or ``None`` to allow it.

    Two independent triggers, so neither a lost marker nor a quoted marker is
    the only line of defence: the notes carry the marker, or the fixture model
    is switched on in this process. Either one needs the ``gh`` seam as well.
    """
    if gh_seam_active():
        return None
    if FIXTURE_MARKER in notes_text or _read(CONDENSE_FIXTURE_ENV) is not None:
        return f"fixture_notes_refused:{GH_ARGV_PREFIX_ENV}_unset"
    return None
