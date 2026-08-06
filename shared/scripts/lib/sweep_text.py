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


def decode_store_text(data: bytes) -> str:
    """Decode triage-store bytes to text — the ONE rule, for BOTH sides of the seam.

    A triage line is compared across a seam: one side is a git blob, the other is the
    file on disk. Whoever reads a side must decode it THIS way, or the comparison is
    between two different renderings of the same bytes.

    ``errors="surrogateescape"``, for the same reason :func:`lib.jsonl_records.read_jsonl_records`
    uses it and stated first: an interrupted append truncates the store mid multi-byte
    sequence, and a STRICT decode turns that into a ``UnicodeDecodeError`` out of every
    caller. :func:`read_text_verbatim` is called from ``setup_iterate_worktree`` step 5 —
    i.e. AFTER ``git worktree add`` has already succeeded — so a raise there orphans the
    worktree it just created. Surrogate escapes also round-trip: re-encoding with the same
    error handler reproduces the original bytes, so a repair pass can still recover them,
    which a lossy ``errors="replace"`` would prevent.

    That last property is why this, and not ``replace``, is the shared rule.
    ``replace`` is non-injective — every invalid byte collapses to the same ``U+FFFD``
    — so two DIFFERENT broken lines render identically. A membership test built on it
    could judge a buffered line "delivered" on the strength of some *other* line in
    origin and delete it. Surrogate escaping is exact, so parity here can never become
    a lossy match (iterate-2026-08-06-gc-decode-parity).

    Scope is deliberately this store, not text in general: ``lib.git_base.run_git``
    keeps ``errors="replace"`` for its ~133 other callers, and lone surrogates must not
    escape into code that re-encodes.
    """
    return data.decode("utf-8", errors="surrogateescape")


def read_text_verbatim(path: Path) -> str:
    """Read ``path`` with NO newline translation; empty string if absent.

    Reads BYTES and routes them through :func:`decode_store_text`, so the file side of
    the seam and the git-blob side share one decode rule by construction rather than by
    two call sites happening to agree.

    Reading binary also sidesteps ``Path.read_text(..., newline="")``, whose keyword is
    Python 3.13+ only while the shared scripts run on the CONSUMING project's
    interpreter (>= 3.11) — it took every iterate down mid-setup once already (#367).
    Bytes carry no newline translation to disable, and no BOM is stripped (that is
    ``utf-8-sig``, which this never was), so ordinary reads are unchanged.
    """
    if not path.exists():
        return ""
    return decode_store_text(path.read_bytes())
