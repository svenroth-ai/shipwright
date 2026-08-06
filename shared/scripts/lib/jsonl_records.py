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
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:  # imported as ``lib.jsonl_records`` (shared/scripts on sys.path)
    from .atomic_write import durable_read_text
except ImportError:  # pragma: no cover - exercised in a subprocess test
    # ``shared_lib_loader`` execs THIS file directly under a sentinel name when a
    # plugin's own ``scripts/lib`` shadows shared's (ADR-045), and that load has
    # no package context, so the relative spelling cannot resolve. ``atomic_write``
    # documents itself as a unique top-level name importable either way.
    #
    # ``lib/review_marker.py`` carries the same two SPELLINGS but not this path
    # insert — it relies on callers having put the directory there. The sentinel
    # load gives no such guarantee (``load_shared_lib`` adds ``shared/scripts``, not
    # ``lib``), so this adds it, guarded. Pinned by test_jsonl_records_load_modes.
    # APPEND, never insert(0): prepending would put 160+ generic module names
    # (config, errors, state, ...) ahead of everything else for the rest of the
    # process. `plugins/shipwright-compliance/.../collectors/_lib_loader.py`
    # documents exactly that discipline and scopes its own front-precedence to
    # the import. Appending is enough here - we only need the directory to be
    # findable - and it cannot shadow a plugin's own lib (Stage-3 doubt).
    _here = str(Path(__file__).resolve().parent)
    if _here not in sys.path:
        sys.path.append(_here)
    from atomic_write import durable_read_text  # type: ignore[no-redef]

__all__ = [
    "CorruptFragment",
    "RecordRead",
    "ends_without_newline",
    "read_jsonl_records",
    "split_records",
]

_DECODER = json.JSONDecoder()
_JSON_WS = " \t\r\n"

#: Resync candidates tried per physical line before giving up (see
#: :func:`split_records`). Each candidate re-parses the rest of the line, so an
#: unbounded scan is quadratic in line length; a malformed line is exactly where
#: candidate density is highest. Exhausting the budget degrades to the pre-2026-08
#: behaviour — the whole damaged span is reported as one fragment — never to a hang.
_MAX_RESYNC_ATTEMPTS = 64


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

    Anything ELSE that goes wrong returns True, i.e. "assume unterminated". This
    function is the PREVENTION half of the module, so it must fail CLOSED, and the
    two error directions are not symmetric:

    * a wrong ``True`` prepends one newline, leaving a blank line that
      :func:`read_jsonl_records` skips outright (``if not stripped: continue``);
    * a wrong ``False`` lets the next writer append onto an unterminated line, and
      the reader then loses BOTH records — the exact corruption documented at the
      top of this module.

    One blank line against two destroyed records is not a close call. Only the two
    states that are genuinely appendable — absent and empty — return False.
    """
    path = Path(path)
    try:
        if path.stat().st_size == 0:
            return False
        with path.open("rb") as fh:
            fh.seek(-1, 2)  # 2 == os.SEEK_END
            return fh.read(1) != b"\n"
    except FileNotFoundError:
        # Nothing to append ONTO — the first write creates a well-formed file.
        return False
    except (OSError, ValueError):
        # Unreadable, not seekable, a race that deleted it mid-stat: we cannot
        # prove the file is terminated, so we must not assume it is.
        return True


def split_records(line: str, *, is_record=None) -> tuple[list[dict], str]:
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
    * Recovery is also BIDIRECTIONAL (iterate-2026-08-06-p2-19c-corruption-absence,
      IT-1 audit finding 21): records decoded *after* the bad byte are returned too.
      Until then a damaged PREFIX sent the whole rest of the line to the remainder,
      discarding every valid record behind it — and the primary cause this module
      documents, a truncated predecessor appended onto, has exactly that shape.

    **Forward recovery needs ``is_record``, and does nothing without it.** Syntax
    alone cannot locate a record boundary: an object nested INSIDE the damaged
    prefix decodes cleanly. Requiring the candidate's run to reach end-of-line is
    necessary but NOT sufficient — a prefix ending ``…"meta":{"embedded":1}``
    followed by a real append lets one run consume both and surface ``embedded``
    (measured; external plan review round 2, high). Only the caller knows what a
    record looks like, so it passes a predicate that **every** object in the run
    must satisfy. Without one this fails closed — no resync, pre-2026-08 behaviour.
    No default is offered because the two logs reading through here disagree:
    triage records key on ``event`` (1464/1465 live, none nested) while
    ``shipwright_events.jsonl`` keys on ``type`` and 306 of 799 DO nest.

    A line carrying TWO damaged spans finds no candidate and degrades to reporting
    the whole span — the safe direction.
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
            # RecursionError (not a ValueError) escapes from json's scanner on a
            # deeply nested blob — plausible from a truncated/interleaved write.
            # Letting it propagate would crash every reader instead of degrading.
            obj, next_idx = _DECODER.raw_decode(line, idx)
        except (ValueError, RecursionError):
            obj = None
            next_idx = idx
        if isinstance(obj, dict):
            records.append(obj)
            idx = next_idx
            continue
        # Undecodable, or valid JSON of the wrong shape (a bare scalar). Either
        # way the text at `idx` is not a record; look for the next one behind it.
        recovered, resume = _resync(line, idx, is_record)
        if resume is None:
            return records, line[idx:]
        records.extend(recovered)
        return records, line[idx:resume]
    return records, ""


def _resync(line: str, bad_from: int, is_record) -> tuple[list[dict], int | None]:
    """Find the next record start after ``bad_from``.

    Returns ``(records, resume_index)`` where ``resume_index`` is the offset the
    recovered run began at, so the caller can report ``line[bad_from:resume]`` as
    the damaged span. ``(_, None)`` means nothing trustworthy follows — which is
    also the answer whenever the caller supplied no ``is_record`` predicate.
    """
    if is_record is None:
        return [], None
    probe = line.find("{", bad_from + 1)
    attempts = 0
    while probe != -1 and attempts < _MAX_RESYNC_ATTEMPTS:
        objs, complete = _decode_run(line, probe)
        # EVERY object must look like a record: accepting a run because its LAST
        # member is genuine is how a nested object from the wreckage gets in.
        if complete and objs and all(is_record(o) for o in objs):
            return objs, probe
        probe = line.find("{", probe + 1)
        attempts += 1
    return [], None


def _decode_run(line: str, start: int) -> tuple[list[dict], bool]:
    """Decode objects from ``start`` to end of line.

    ``complete`` is True only when the run consumed everything to the end with no
    leftover — the condition that makes a resync candidate trustworthy.
    """
    objs: list[dict] = []
    idx = start
    end = len(line)
    while idx < end:
        while idx < end and line[idx] in _JSON_WS:
            idx += 1
        if idx >= end:
            break
        try:
            obj, idx = _DECODER.raw_decode(line, idx)
        except (ValueError, RecursionError):
            return objs, False
        if not isinstance(obj, dict):
            return objs, False
        objs.append(obj)
    return objs, True


def read_jsonl_records(path: Path | str, *, is_record=None) -> RecordRead:
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

    The read goes through :func:`lib.atomic_write.durable_read_text`
    (iterate-2026-08-06-p2-19c-corruption-absence, IT-1 audit finding 5). This file
    is published by ``durable_atomic_write`` — the D2 sweep rewrites it — and that
    function's own docstring says callers of such files should read through the
    durable reader, because on Windows a replaced-but-still-open file leaves the old
    entry *delete-pending* and an unlocked reader's ``open`` fails with
    ``PermissionError`` until the last handle goes. It also explicitly reserved
    ``surrogateescape`` for "a triage-side caller … the day one exists". This is it.

    **The separator alphabet is deliberately unchanged.** ``durable_read_text`` opens
    in text mode with universal newlines, exactly as the previous file-handle
    iteration did, so splitting the result on ``"\\n"`` reproduces the old line set
    byte-for-byte (measured across LF, CRLF, lone CR, missing final newline, and
    invalid UTF-8). ``str.splitlines()`` must NOT be used here: it additionally
    breaks on VT, FF, NEL and U+2028, which would silently promote four characters
    that may appear INSIDE a record into record separators.
    """
    path = Path(path)
    result = RecordRead()
    if not path.exists():
        return result
    text = durable_read_text(path, errors="surrogateescape")
    for line_no, raw in enumerate(text.split("\n"), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        records, remainder = split_records(stripped, is_record=is_record)
        result.records.extend(records)
        if remainder:
            result.corrupt.append(
                CorruptFragment(path=str(path), line_no=line_no, text=remainder)
            )
    return result
