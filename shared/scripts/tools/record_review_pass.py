"""Record one review pass into the run's review record.

    .shipwright/planning/iterate/<run_id>/reviews.json

Every review pass of an iterate — Self-Review, the external plan/iterate review,
the internal ``code-reviewer``, the ``doubt-reviewer``, and the external
code-review cascade — closes its own row here. A row nobody closes stays
``pending`` and F11 stops the run, so an empty Review row in the Mission view
always means "genuinely not run", never "somebody forgot".

Subcommands: ``init`` (create-if-absent) · ``record`` (close one type, handing
over the reviewer's reply verbatim) · ``close-missing`` (close every still-open
type in one command — for a run that predates this record) · ``repair-markers``
· ``show``. Per-pass invocations and the payload shape per reviewer live in
``plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md``
→ "Recording each review pass"; ``--help`` covers the flags.

Exit codes: ``0`` ok · ``1`` error · ``2`` usage · ``3`` immutable (the type is
already recorded with a terminal status).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.file_lock import LockTimeout  # noqa: E402
from lib.review_companion import MARKER_TYPES, repair_markers, write_markers  # noqa: E402
from lib.review_findings import (  # noqa: E402
    PARSE_PARTIAL,
    PARSE_UNSTRUCTURED,
    ProseOverflowError,
    ReviewFindingsError,
)
from lib.review_marker import ALLOWED_STATUSES  # noqa: E402
from lib.review_payloads import ADAPTERS, build_findings  # noqa: E402
from lib.review_record import (  # noqa: E402
    REVIEW_TYPES,
    STATUS_COMPLETED,
    TERMINAL_STATUSES,
    ImmutableReviewError,
    ReviewRecordError,
    close_pending,
    init_record,
    make_entry,
    pending_types,
    read_record,
    record_path,
    upsert_and_write,
)

EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_IMMUTABLE = 0, 1, 2, 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fail(error: str, message: str, code: int = EXIT_ERROR) -> int:
    print(json.dumps({"success": False, "error": error, "message": message}))
    return code


def _marker_reason(
    disposition: str | None, parse_status: str | None, findings_count: int
) -> str | None:
    """Carry an unreadable parse into the marker's ``reason``.

    The marker has no ``parse_status`` field, and neither does the pinned
    cross-repo ``ReviewRow``. A review that RAN but whose prose could not be
    itemized would otherwise reach the consumer as
    ``status: completed, findings_count: 0`` — which every reader completes as
    "…and found nothing". That is the fabrication AC5 exists to prevent, merely
    displaced one repo downstream. ``reason`` is the one field the consumer
    already surfaces (as ``disposition``), so the caveat travels there.
    """
    if parse_status in (PARSE_UNSTRUCTURED, PARSE_PARTIAL):
        caveat = (
            "findings could not be itemized from the reviewer's prose — "
            f"the count ({findings_count}) is NOT a clean-review result"
            if parse_status == PARSE_UNSTRUCTURED else
            f"only some provider legs could be itemized — the count "
            f"({findings_count}) may understate what was found"
        )
        return f"{disposition} — {caveat}" if disposition else caveat
    return disposition


def _cmd_init(args: argparse.Namespace) -> int:
    try:
        record, created = init_record(Path(args.project_root), args.run_id)
        path = str(record_path(Path(args.project_root), args.run_id))
    except ReviewRecordError as exc:
        return _fail("init_failed", str(exc))
    print(json.dumps({
        "success": True, "created": created, "path": path,
        "pending": pending_types(record),
    }, indent=2))
    return EXIT_OK


def _cmd_repair_markers(
    args: argparse.Namespace, already_recorded_error: Exception | None = None
) -> int:
    """Re-write the legacy marker from the ALREADY-RECORDED entry."""
    if args.marker_status not in ALLOWED_STATUSES:
        return _fail("invalid_arguments",
                     f"--marker-status must be one of {sorted(ALLOWED_STATUSES)}",
                     EXIT_USAGE)
    try:
        markers = repair_markers(
            Path(args.project_root), args.run_id, args.review_type,
            marker_status=args.marker_status, provider=args.provider,
            reason=args.disposition,
        )
    except ReviewRecordError as exc:
        if already_recorded_error is not None:
            return _fail("immutable", str(already_recorded_error), EXIT_IMMUTABLE)
        return _fail("repair_failed", str(exc))
    except OSError as exc:
        return _fail("marker_write_failed", str(exc))

    print(json.dumps({
        "success": True, "repaired": True, "record_unchanged": True,
        "review_type": args.review_type, "markers": markers,
    }, indent=2))
    return EXIT_OK


def _validate_record_args(args: argparse.Namespace) -> str | None:
    """Return an error message, or ``None`` when the arguments are coherent."""
    if args.review_type not in REVIEW_TYPES:
        return f"--review-type must be one of {list(REVIEW_TYPES)}"
    if args.status not in TERMINAL_STATUSES:
        return (f"--status must be one of {sorted(TERMINAL_STATUSES)} — 'pending' "
                "is the absence of a record, not a way to close one")
    if args.marker_status and args.review_type not in MARKER_TYPES:
        return f"--marker-status applies only to {sorted(MARKER_TYPES)}"
    if (args.review_type in MARKER_TYPES and args.status == STATUS_COMPLETED
            and not args.marker_status):
        # AC7: these two types carry the legacy gate marker, so a review that
        # actually RAN must leave one — otherwise the new gate reads green while
        # existing marker consumers have no evidence. Only `completed` is
        # forced: the marker vocabulary has no term for "not applicable at this
        # complexity", and requiring one would make the caller pick a status
        # that misstates why the pass did not run.
        return (f"--marker-status is required when recording {args.review_type} "
                f"as completed (one of {sorted(ALLOWED_STATUSES)})")
    if args.force and args.review_type in MARKER_TYPES and not args.marker_status:
        # A forced correction that leaves the old marker in place is worse than
        # no correction: the record now says one thing and the artifact every
        # legacy consumer reads still says the other, with nothing to
        # invalidate it.
        return (f"--force on {args.review_type} also requires --marker-status, so the "
                "companion marker cannot be left stating the superseded result")
    if args.marker_status and args.marker_status not in ALLOWED_STATUSES:
        # The tool this replaces at the call sites rejects an out-of-vocabulary
        # status; losing that check would let a typo write a marker no consumer
        # understands while the CLI reports success.
        return (f"--marker-status must be one of {sorted(ALLOWED_STATUSES)}, "
                f"got {args.marker_status!r}")
    return None


def _cmd_record(args: argparse.Namespace) -> int:
    invalid = _validate_record_args(args)
    if invalid:
        return _fail("invalid_arguments", invalid, EXIT_USAGE)

    try:
        findings, parse_status, raw = build_findings(args.review_from, args.payload_file)
    except (ReviewFindingsError, ProseOverflowError) as exc:
        return _fail("payload_unreadable", str(exc))

    if args.status != STATUS_COMPLETED:
        # A pass that did not run has nothing to report; keeping findings from a
        # payload here would attribute them to a review that never happened.
        findings, parse_status, raw = [], None, None

    try:
        entry = make_entry(
            args.review_type, args.status,
            findings=findings, provider=args.provider,
            disposition=args.disposition, completed_at=_now(),
            recorded_by=args.recorded_by or args.review_from,
            parse_status=parse_status, raw_excerpt=raw,
        )
    except ReviewRecordError as exc:
        return _fail("invalid_entry", str(exc), EXIT_USAGE)

    project_root = Path(args.project_root)
    markers: list[str] = []

    # Set the moment the record is durable, so the OSError branch below reports
    # what ACTUALLY landed instead of asserting one specific outcome. An OSError
    # from mkdir, the lock open, or the record write itself reaches the same
    # handler, and claiming "the record was written" there would be a guess — in
    # a tool whose whole thesis is that absence must never be mistaken for a
    # result.
    record_written = False

    def write_companion(_record: dict) -> None:
        nonlocal record_written
        record_written = True
        if args.marker_status:
            markers.extend(write_markers(
                project_root, args.run_id, args.review_type,
                marker_status=args.marker_status, findings_count=len(findings),
                provider=args.provider,
                reason=_marker_reason(args.disposition, parse_status, len(findings)),
            ))

    try:
        record = upsert_and_write(project_root, args.run_id, entry,
                                  force=args.force, after_write=write_companion)
    except ImmutableReviewError as exc:
        return _repair_or_reject(project_root, args, exc)
    except ReviewRecordError as exc:
        return _fail("record_write_failed", str(exc))
    except OSError as exc:
        if not record_written:
            return _fail("record_write_failed",
                         f"nothing was written ({exc}) — the record did not land")
        hint = (f" Repair it with `{Path(__file__).name} repair-markers --run-id "
                f"{args.run_id} --review-type {args.review_type} --marker-status "
                f"{args.marker_status}`." if args.marker_status else "")
        return _fail("marker_write_failed",
                     f"the record was written but the marker was not ({exc}).{hint}")

    print(json.dumps({
        "success": True, "review_type": args.review_type, "status": args.status,
        "findings_count": len(findings), "parse_status": parse_status,
        "markers": markers, "pending": pending_types(record),
    }, indent=2))
    return EXIT_OK


def _repair_or_reject(
    project_root: Path, args: argparse.Namespace, exc: ImmutableReviewError
) -> int:
    """An immutable collision is an error — UNLESS this is genuinely a repair.

    Re-running the original command is what an operator does after a marker
    write fails, so that case repairs instead of dead-ending on exit 3. But it
    is only a repair when the command RESTATES what is already recorded: the
    requested status must equal the recorded one. Skipping that check let
    `--status not_run --marker-status skipped_config_disabled` be answered with
    exit 0 `"repaired": true` while the record still said `completed` with 17
    findings — no `--force`, a rejected write reported as success, and the two
    artifacts left contradicting each other.
    """
    if not args.marker_status:
        return _fail("immutable", str(exc), EXIT_IMMUTABLE)
    try:
        record = read_record(project_root, args.run_id)
    except ReviewRecordError:
        record = None
    recorded = ((record or {}).get("reviews", {}).get(args.review_type) or {})
    if recorded.get("status") != args.status:
        return _fail(
            "immutable",
            f"{args.review_type} is recorded as {recorded.get('status')!r}, so "
            f"asking to record it as {args.status!r} is a restatement, not a "
            f"marker repair — {exc}",
            EXIT_IMMUTABLE,
        )
    return _cmd_repair_markers(args, already_recorded_error=exc)


def _cmd_close_missing(args: argparse.Namespace) -> int:
    if args.status not in TERMINAL_STATUSES or args.status == STATUS_COMPLETED:
        return _fail("invalid_status",
                     "--status must be not_run or not_applicable — "
                     "'completed' cannot be asserted in bulk", EXIT_USAGE)
    project_root = Path(args.project_root)
    try:
        record = read_record(project_root, args.run_id)
    except ReviewRecordError as exc:
        return _fail("record_unreadable", str(exc))
    if record is None:
        record, _ = init_record(project_root, args.run_id)

    targets = pending_types(record)
    if args.only:
        requested = [t.strip() for t in args.only.split(",") if t.strip()]
        unknown = [t for t in requested if t not in REVIEW_TYPES]
        if unknown:
            return _fail("invalid_arguments",
                         f"--only names unknown review type(s): {', '.join(unknown)}",
                         EXIT_USAGE)
        targets = [t for t in targets if t in requested]

    try:
        # ONE batch write under ONE lock. Closing each type in its own
        # acquisition meant a mid-loop failure left some types permanently
        # closed as not_run and the rest open — an irreversible half-state that
        # only --force could move, on the very command whose job is to unblock a
        # stuck run.
        entries = [
            make_entry(t, args.status, disposition=args.disposition,
                       completed_at=_now(), recorded_by="close-missing")
            for t in targets
        ]
        record = close_pending(project_root, args.run_id, entries)
    except ImmutableReviewError as exc:
        return _fail("immutable", f"a type was closed concurrently: {exc}",
                     EXIT_IMMUTABLE)
    except ReviewRecordError as exc:
        return _fail("invalid_entry", str(exc), EXIT_USAGE)

    print(json.dumps({"success": True, "closed": targets,
                      "pending": pending_types(record)}, indent=2))
    return EXIT_OK


def _cmd_show(args: argparse.Namespace) -> int:
    try:
        record = read_record(Path(args.project_root), args.run_id)
    except ReviewRecordError as exc:
        return _fail("record_unreadable", str(exc))
    if record is None:
        return _fail("record_missing",
                     f"no review record for {args.run_id} — run `init` first")
    print(json.dumps(record, indent=2, ensure_ascii=False))
    return EXIT_OK


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--project-root", default=".")
        p.add_argument("--run-id", required=True)

    common(sub.add_parser("init", help="create the record if absent"))
    common(sub.add_parser("show", help="print the record"))

    rec = sub.add_parser("record", help="record one review pass")
    common(rec)
    rec.add_argument("--review-type", required=True, choices=list(REVIEW_TYPES))
    rec.add_argument("--status", required=True)
    rec.add_argument("--from", dest="review_from", default="none", choices=list(ADAPTERS),
                     help="how to read --payload-file")
    rec.add_argument("--payload-file",
                     help="the reviewer's reply — raw JSON, a ```json block, or prose")
    rec.add_argument("--provider", default=None)
    rec.add_argument("--disposition", default=None,
                     help="required for not_run / not_applicable; must name the rule")
    rec.add_argument("--recorded-by", default=None)
    rec.add_argument("--force", action="store_true",
                     help="overwrite an already-terminal record (corrections only)")
    rec.add_argument("--marker-status", default=None,
                     help="also write the legacy external_*review_state.json marker")

    close = sub.add_parser("close-missing", help="close every still-pending type")
    common(close)
    close.add_argument("--status", required=True)
    close.add_argument("--disposition", required=True)
    close.add_argument("--only", default=None,
                       help="comma-separated review types to close "
                            "(default: every still-pending type)")

    repair = sub.add_parser("repair-markers",
                            help="re-write the legacy marker from an already-recorded entry")
    common(repair)
    repair.add_argument("--review-type", required=True, choices=sorted(MARKER_TYPES))
    repair.add_argument("--marker-status", required=True, choices=sorted(ALLOWED_STATUSES))
    repair.add_argument("--provider", default=None)
    repair.add_argument("--disposition", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    handlers = {"init": _cmd_init, "record": _cmd_record,
                "close-missing": _cmd_close_missing, "show": _cmd_show,
                "repair-markers": _cmd_repair_markers}
    try:
        return handlers[args.command](args)
    except LockTimeout as exc:
        # Not a ReviewRecordError, so it would otherwise escape every handler
        # and break the JSON-on-stdout contract the orchestrator parses.
        return _fail("lock_timeout", str(exc))


if __name__ == "__main__":
    sys.exit(main())
