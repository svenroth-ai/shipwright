"""What could not be read in the triage store — and what a record even is.

``triage.read_all_items`` returns one dict per item: a *view*. An unreadable span
is invisible in it, which was a live defect (IT-1 audit finding 22, closed by
iterate-2026-08-06-p2-19c-corruption-absence): ``read_jsonl_records`` reports damage
on ``RecordRead.corrupt``, but ``triage._iter_raw_lines_at`` warned once per
fragment and then dropped it, so no consumer could tell "this item is not in the
log" from "the bytes where it would be are unreadable". ``lib/jsonl_records.py``
names that exact confusion as the thing that must never happen, and
``warnings.warn`` is globally suppressible on top.

The sibling question — *has this decision been delivered?* — lives in
:mod:`lib.triage_delivery`, which this module composes in :func:`store_facts`.

**This module lives beside the store, not inside it.** It takes concrete *paths*,
never a project root, and never imports :mod:`triage` — that direction would close
an import cycle of the kind ``lib/jsonl_records.py`` records as the origin of this
repo's CodeQL cycle findings (#281). Callers already hold the two paths.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path, PurePosixPath

try:  # imported as ``lib.triage_integrity`` (shared/scripts on sys.path)
    from .jsonl_records import CorruptFragment, read_jsonl_records
    from .triage_delivery import undelivered_amends_from_records, undelivered_from_records
except ImportError:  # pragma: no cover - exercised in a subprocess test
    # Same two-spelling requirement as ``lib/jsonl_records.py`` itself: a plugin's
    # own ``scripts/lib`` can shadow shared's, and ``shared_lib_loader`` then execs
    # this file by path with no package context (ADR-045). This module IS reached
    # that way in production — ``triage._iter_raw_lines_at`` calls
    # ``load_shared_lib("triage_integrity")`` on every store read — so the branch is
    # live, and ``test_jsonl_records_load_modes.py`` drives it directly.
    #
    # KNOWN CONSEQUENCE of the fallback: it binds ``jsonl_records`` under its
    # top-level name, a DISTINCT module object from the sentinel-named one the
    # loader may also hold. Two ``CorruptFragment`` classes then coexist. Every
    # consumer here duck-types the attributes, which is why it works; do NOT add an
    # ``isinstance(frag, CorruptFragment)`` check or a frozen-dataclass ``==``
    # across that boundary — both silently return False.
    # APPEND, never insert(0): prepending would put 160+ generic module names
    # (config, errors, state, ...) ahead of everything else for the rest of the
    # process. `plugins/shipwright-compliance/.../collectors/_lib_loader.py`
    # documents exactly that discipline and scopes its own front-precedence to
    # the import. Appending is enough here - we only need the directory to be
    # findable - and it cannot shadow a plugin's own lib (Stage-3 doubt).
    _here = str(Path(__file__).resolve().parent)
    if _here not in sys.path:
        sys.path.append(_here)
    from jsonl_records import CorruptFragment, read_jsonl_records  # type: ignore[no-redef]
    from triage_delivery import undelivered_amends_from_records, undelivered_from_records  # type: ignore[no-redef]

__all__ = [
    "basename",
    "format_corruption_notice",
    "is_triage_record",
    "report_corruption",
    "span_bytes",
    "store_corruption",
    "store_facts",
    "undelivered_status_ids",
]

#: Keys `triage.py`'s three writers ALWAYS emit, per event kind. Read off the
#: writers (`append_triage_item`, `mark_status`, `amend_triage_item`), not off a
#: sample of the store — see :func:`is_triage_record` for why that distinction is
#: load-bearing.
_REQUIRED_KEYS = {
    "append": ("id", "ts", "source", "severity", "kind", "title", "status"),
    "status": ("id", "ts", "newStatus", "by"),
    "amend": ("id", "ts", "by"),
}

#: Mirrors `lib.triage_amend.AMENDABLE_FIELDS` — inlined, not imported, to keep
#: this module's no-intra-lib-imports-beyond-jsonl_records/triage_delivery design.
#: An `amend` record naming none of these is key-complete but CONTENT-empty; see
#: :func:`is_triage_record`'s amend paragraph for why that must also be refused.
_AMEND_CONTENT_KEYS = ("title", "detail", "severity", "kind")

#: Detail lines the stderr notice prints before summarising the rest.
_NOTICE_SPAN_CAP = 20

#: Spans already reported this process, so one damaged span is announced once. A
#: single ``triage_cli list`` reads each store several times over, and an operator
#: seeing the same damage four times learns nothing extra while being told, wrongly,
#: that there is more of it. Bounded by the number of damaged lines, not by process
#: lifetime. NOTE the guarantee is once per LOADED MODULE, not once per process: in
#: a process holding both the package and the path-loaded copy (the ADR-045 case
#: above) two sets coexist and a span is announced twice. Cosmetic, and named here
#: rather than overclaimed (Stage-3 doubt).
_REPORTED: set[tuple[str, int, str]] = set()


def is_triage_record(obj: dict) -> bool:
    """What a record of THIS store looks like, for boundary resync.

    ``jsonl_records.split_records`` will not recover past a damaged prefix without a
    predicate, because syntax alone cannot tell a genuine appended record from an
    object nested inside the wreckage. This is the triage store's answer; it lives
    here because the other log reading through that leaf
    (``shipwright_events.jsonl``) has a different one — its records carry ``type``,
    not ``event``, and unlike triage records they routinely nest.

    **It matches the writers, not the shape of today's data**, and this predicate
    has been widened-then-narrowed twice because getting that wrong is not
    display-only: ``tools/triage_repair.py`` feeds the recovered objects back into
    ``report.lines`` and republishes the file, so a fabricated record is **written
    into the append-only log**.

    * v1 accepted any object with a string ``event``, justified by "none of 1465
      live records nests". An observation, not an invariant.
    * v2 added a string ``id``. Still too loose: an external code review produced
      ``{"meta":{"event":"append","id":"forged"}`` — a nested object satisfying
      BOTH keys — and the resync surfaced ``forged`` as a record (reproduced).
    * v3, this one, requires every key the corresponding writer always emits
      (:data:`_REQUIRED_KEYS`, read off ``append_triage_item``, ``mark_status``
      and ``amend_triage_item``). A nested object now has to be a COMPLETE triage
      record to qualify, which the store never writes — the three writers emit
      records only at top level.

    The residual risk is honest and bounded: this is a shape test, not a proof of a
    record boundary, so wreckage that happens to contain a whole valid record would
    still be recovered. That is the conservative direction anyway — such an object
    IS a record by every check the reader itself applies.

    ``amend`` (iterate-2026-08-08-triage-amend-event) adds one more refusal beyond
    key-completeness: a record naming none of ``title``/``detail``/``severity``/
    ``kind`` is key-complete but content-EMPTY, which the wire schema's ``anyOf``
    already refuses — and would otherwise be indistinguishable from a valid,
    minimal amend during boundary resync (external plan review, HIGH).

    The schema header ``{"v": 1, …}`` carries no ``event`` and stays excluded.
    """
    if not isinstance(obj, dict):
        return False
    event = obj.get("event")
    required = _REQUIRED_KEYS.get(event)
    if required is None:
        return False
    if not (isinstance(obj.get("id"), str) and all(k in obj for k in required)):
        return False
    return event != "amend" or any(k in obj for k in _AMEND_CONTENT_KEYS)


def basename(path: str) -> str:
    """Last path component, for a path produced on EITHER platform.

    One spelling for both operator surfaces: ``PurePosixPath`` alone strips nothing
    from a Windows path on POSIX and ``Path`` alone strips nothing from a POSIX path
    on Windows, so the two would disagree about the same fragment.
    """
    return PurePosixPath(str(path).replace("\\", "/")).name


def span_bytes(frag: CorruptFragment) -> int:
    """How many BYTES the damaged span occupies on disk.

    ``len(frag.text)`` counts code points, so a span holding one two-byte UTF-8
    character was reported as "1 byte" by both the notice and the JSON contract,
    which promise a byte count (external code review). ``surrogateescape`` on the
    encode round-trips the undecodable bytes the reader preserved, so this is the
    real on-disk length either way.
    """
    return len(frag.text.encode("utf-8", "surrogateescape"))


def _span_key(frag: CorruptFragment) -> tuple[str, int, str]:
    """Identity of a damaged span, by CONTENT.

    ``tools/triage_repair._fragment_key`` answers the same question the same way,
    two files over; a byte-length would collide across a repair that changes the
    span while leaving its line number and size alone.
    """
    digest = hashlib.sha256(frag.text.encode("utf-8", "surrogateescape"))
    return (str(frag.path), frag.line_no, digest.hexdigest()[:16])


def store_corruption(*paths: Path | str) -> list[CorruptFragment]:
    """Every unrecoverable span across ``paths``, in file order.

    A missing file contributes nothing — absence of a store is not corruption.

    Reads with :func:`is_triage_record`, exactly as ``triage._iter_raw_lines_at``
    does. Without it this would report a WIDER span than the reader experienced —
    the whole line rather than the damaged prefix — so the two channels would
    disagree about the same damage and :func:`report_corruption`'s key would
    announce it twice.
    """
    fragments: list[CorruptFragment] = []
    for path in paths:
        fragments.extend(
            read_jsonl_records(path, is_record=is_triage_record).corrupt)
    return fragments


def format_corruption_notice(fragments: list[CorruptFragment]) -> str | None:
    """The one operator-facing line per damaged span, or ``None`` if clean.

    **Shape only, never content.** ``read_jsonl_records`` preserves undecodable
    bytes via ``surrogateescape``, so a fragment can hold arbitrary bytes —
    including terminal control sequences — and this text goes to a terminal. It
    reports path, line number and byte count; it never echoes the span. The path
    goes through ``ascii()`` because it also reaches Windows cp1252 consoles, where
    a raw non-ASCII byte would raise inside the diagnostic itself.

    **Bounded, like the JSON block.** A hostile or badly damaged log can hold
    hundreds of corrupt physical lines; the detail list is capped and the header
    always carries the true total, so a capped report can never read as a complete
    one (external code review — the JSON side was capped, this one was not).
    """
    if not fragments:
        return None
    lines = [
        f"triage: {len(fragments)} unrecoverable span(s) in the append-only log. "
        f"Valid records on the same lines were recovered; run triage_repair.py "
        f"to quarantine the rest."
    ]
    for frag in fragments[:_NOTICE_SPAN_CAP]:
        lines.append(
            f"  {ascii(basename(frag.path))}:{frag.line_no} - "
            f"{span_bytes(frag)} bytes unrecoverable"
        )
    if len(fragments) > _NOTICE_SPAN_CAP:
        lines.append(f"  (+{len(fragments) - _NOTICE_SPAN_CAP} more not shown)")
    return "\n".join(lines)


def report_corruption(fragments: list[CorruptFragment]) -> None:
    """Write the notice to stderr, once per distinct span per loaded module.

    Deliberately **not** ``warnings.warn``: that was the pre-fix report and it is
    globally suppressible (``-W ignore``, ``PYTHONWARNINGS``, or any library that
    installs a blanket filter), so the only signal that the log was damaged could
    vanish for reasons entirely unrelated to triage. stderr also keeps machine
    output on stdout parseable, which ``triage_cli list --json`` depends on.

    Suppressing the repeat is display-only: :func:`store_corruption` recomputes from
    the files every time (as does :func:`store_facts`, the CLI's caller), so no
    consumer's view of the damage is affected. The write
    happens BEFORE the span is marked reported, so a failed write cannot silence it.
    """
    fresh = [f for f in fragments if _span_key(f) not in _REPORTED]
    if not fresh:
        return
    sys.stderr.write(format_corruption_notice(fresh) + "\n")
    _REPORTED.update(_span_key(f) for f in fresh)


def store_facts(tracked_path: Path | str, outbox_path: Path | str,
                *, applied_statuses, is_valid_amend) -> tuple[list[CorruptFragment], set[str], set[str]]:
    """Return corruption plus independent status- and amend-delivery facts.

    The caller supplies the same amend validator used by its resolved view so a
    damaged amend cannot manufacture a reassuring or alarming delivery signal.
    """
    reads = [
        read_jsonl_records(p, is_record=is_triage_record)
        for p in (tracked_path, outbox_path)
    ]
    corruption = [frag for r in reads for frag in r.corrupt]
    undelivered_statuses = undelivered_from_records(
        reads[0].records, reads[1].records, applied_statuses=applied_statuses)
    undelivered_amends = undelivered_amends_from_records(
        reads[0].records, reads[1].records, is_valid_amend=is_valid_amend)
    return corruption, undelivered_statuses, undelivered_amends


def undelivered_status_ids(tracked_path: Path | str, outbox_path: Path | str,
                           *, applied_statuses) -> set[str]:
    """Return the existing status-delivery fact without considering amends."""
    return store_facts(
        tracked_path, outbox_path, applied_statuses=applied_statuses,
        is_valid_amend=lambda _event: False,
    )[1]
