"""Record-boundary + newline-termination primitives for the append-only triage log.

A NEUTRAL LEAF, deliberately — same reasoning as :mod:`lib.sweep_text`: the reader
(:mod:`triage`), the sweep and the repair CLI all need one agreed answer to "where
does a record end?", and parking that in whichever module happened to need it first
is how this repo's CodeQL import-cycle findings started (#281).

WHY THIS EXISTS (iterate-2026-07-18-outbox-newline-corruption)
--------------------------------------------------------------
The log's "every record is newline-terminated" invariant was a convention each
writer held independently, with no enforcement at the append boundary: the writer
appended its own terminated line without checking the file it appended TO was
terminated, and :func:`lib.atomic_write.durable_atomic_write` documents that it
never invents a trailing newline. One unterminated predecessor — an interrupted
write, an external writer, an operator edit — put two records on one physical line.
The reader then caught ``JSONDecodeError`` and skipped the line, discarding BOTH
records. On an append-only log, corruption must never read as absence.

So this module gives the two halves one home:

* :func:`ends_without_newline` — the writer-side probe (prevention).
* :func:`split_records` / :func:`read_jsonl_records` — record-boundary recovery,
  which is **partial by design**: a valid record followed by an unrecoverable
  fragment yields the valid record AND the fragment. All-or-nothing recovery would
  reproduce the very bug it is meant to fix (external plan review, both reviewers).

This module NEVER prints. Corruption is returned as data on :class:`RecordRead`;
reporting belongs at the command boundary so background callers, tests and CLIs all
behave predictably (external plan review, OpenAI #4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "CorruptFragment",
    "RecordRead",
    "ends_without_newline",
    "read_jsonl_records",
    "split_records",
]

_DECODER = json.JSONDecoder()
_JSON_WS = " \t\r\n"


@dataclass(frozen=True)
class CorruptFragment:
    """One stretch of text on a physical line that could not be decoded.

    ``text`` is the on-disk text apart from the surrounding whitespace the reader
    strips: the repair pass quarantines it unchanged, so a fragment is never
    silently rewritten or dropped.
    """

    path: str
    line_no: int
    text: str


@dataclass
class RecordRead:
    """Tolerant-read outcome: what was recovered, and what could not be.

    ``corrupt`` is the explicit side channel (mirroring the ``scan_errors``
    degraded-marker idiom) that keeps corruption from reading as absence.
    """

    records: list[dict] = field(default_factory=list)
    corrupt: list[CorruptFragment] = field(default_factory=list)


def ends_without_newline(path: Path | str) -> bool:
    """True iff ``path`` exists, is non-empty, and its final byte is not ``\\n``.

    A missing or zero-byte file is safely appendable and returns False — seeking
    ``-1`` from the end of an empty file raises ``OSError`` (external plan review,
    both reviewers). A file ending ``\\r\\n`` ends in ``\\n`` and so counts as
    already terminated; prefixing another newline would inject a blank line.
    """
    path = Path(path)
    try:
        if path.stat().st_size == 0:
            return False
        with path.open("rb") as fh:
            fh.seek(-1, 2)  # 2 == os.SEEK_END
            return fh.read(1) != b"\n"
    except (OSError, ValueError):
        # Missing, unreadable, or not seekable → treat as safely appendable. The
        # append itself will surface any real I/O problem.
        return False


def split_records(line: str) -> tuple[list[dict], str]:
    """Split one physical ``line`` into records + the unrecoverable remainder.

    Returns ``(records, remainder)``. ``remainder`` is ``""`` when the whole line
    decoded cleanly, otherwise the VERBATIM text from the first byte that could not
    be decoded to the end of the line.

    Contract (pinned by the external plan review):

    * JSON whitespace between records is skipped.
    * A blank / whitespace-only line yields ``([], "")`` — formatting, not corruption.
    * Only JSON **objects** count as records: a bare scalar is valid JSON but not a
      triage record, and callers do ``raw.get(...)``, so a scalar is a fragment.
    * Recovery is PARTIAL: records decoded before the bad byte are still returned.
    """
    records: list[dict] = []
    idx = 0
    end = len(line)
    while idx < end:
        # Explicitly JSON's whitespace set, NOT str.isspace(): the latter is
        # Unicode-aware and would silently accept NBSP / U+000B / U+000C between
        # records, diverging from every other JSON consumer of the same bytes.
        while idx < end and line[idx] in _JSON_WS:
            idx += 1
        if idx >= end:
            break
        try:
            obj, next_idx = _DECODER.raw_decode(line, idx)
        except (ValueError, RecursionError):
            # RecursionError (not a ValueError) escapes from json's scanner on a
            # deeply nested blob — plausible from a truncated/interleaved write.
            # Letting it propagate would crash every reader instead of degrading.
            return records, line[idx:]
        if not isinstance(obj, dict):
            # Valid JSON, wrong shape — hand it to the caller verbatim rather than
            # letting a scalar reach code that expects a mapping.
            return records, line[idx:]
        records.append(obj)
        idx = next_idx
    return records, ""


def read_jsonl_records(path: Path | str) -> RecordRead:
    """Tolerantly read ``path``, recovering concatenated records and reporting the rest.

    Order is preserved: records recovered from one physical line stay in wire order
    relative to each other and to surrounding lines, so the log's "later valid line
    wins" status resolution is unaffected.

    A missing file reads empty. The file handle is closed (the pre-fix reader
    iterated ``path.open(...)`` with no context manager and leaked it every read).

    Undecodable bytes are round-tripped via ``surrogateescape`` rather than raising:
    an interrupted write — one of this bug's documented causes — truncates mid
    multi-byte sequence, and a strict decode would turn that into a
    ``UnicodeDecodeError`` out of every reader. That is the fail-closed blackout the
    spec explicitly rejected, so such a line degrades to a fragment instead.
    """
    path = Path(path)
    result = RecordRead()
    if not path.exists():
        return result
    with path.open("r", encoding="utf-8", errors="surrogateescape") as fh:
        for line_no, raw in enumerate(fh, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            records, remainder = split_records(stripped)
            result.records.extend(records)
            if remainder:
                result.corrupt.append(
                    CorruptFragment(path=str(path), line_no=line_no, text=remainder)
                )
    return result
