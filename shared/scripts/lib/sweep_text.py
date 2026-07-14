"""EOL-normalize + verbatim-read helpers for the triage sweep (pure; no git, no lib deps).

A NEUTRAL LEAF, deliberately: :mod:`lib.sweep_outbox`, :mod:`lib.sweep_drift` and
:mod:`lib.sweep_gc` all need the same line/EOL idiom, and this repo has a history of
CodeQL import-cycle findings resolved exactly by extracting one (#281). Parking the
helpers in whichever module happened to need them first is how those cycles start.

The idiom is byte-compatible with :mod:`lib.reconcile_triage` (Codex Q3), so the union
merge driver, the reconcile CLI and the sweep all agree on what a "line" is.
"""

from __future__ import annotations

from pathlib import Path


def normalize_lines(raw: str) -> tuple[list[str], str]:
    """Split ``raw`` into CRLF-absorbed lines + the file's EOL style.

    Strips a trailing ``\\r`` per line and drops the artifact empty line a trailing
    newline leaves. Returns ``(lines, eol)`` where ``eol`` is ``\\r\\n`` iff ``raw``
    contained one. Lines are otherwise VERBATIM — no ``.strip()``: a caller comparing
    them against a git blob must see exactly what is there, or a whitespace-only edit
    slips through as "unchanged".
    """
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = [ln[:-1] if ln.endswith("\r") else ln for ln in raw.split("\n")]
    if lines and lines[-1] == "":
        lines = lines[:-1]
    return lines, eol


def normalized_set(text: str) -> set[str]:
    """Stripped, CRLF-absorbed, non-blank line set of ``text`` (empty if falsy)."""
    if not text:
        return set()
    lines, _ = normalize_lines(text)
    return {ln.strip() for ln in lines if ln.strip()}


def read_text_verbatim(path: Path) -> str:
    """Read ``path`` with NO newline translation; empty string if absent.

    NOT ``Path.read_text(..., newline="")``: that keyword is Python 3.13+ only, while the
    shared scripts run on the CONSUMING project's interpreter (>= 3.11). It took every
    iterate down mid-setup once already (#367).
    """
    if not path.exists():
        return ""
    with path.open("r", encoding="utf-8", newline="") as fh:
        return fh.read()
