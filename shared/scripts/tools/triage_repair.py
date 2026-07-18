#!/usr/bin/env python3
"""Repair triage log lines that hold more than one record (or none).

WHY (iterate-2026-07-18-outbox-newline-corruption)
--------------------------------------------------
A writer left no trailing newline, so the next writer appended onto the same
physical line and the reader dropped BOTH records. The reader now recovers such
lines in memory, but that is not sufficient on its own: ``lib.sweep_outbox`` folds
the outbox into the tracked log by RAW TEXT LINE, so a concatenated line survives
verbatim into the git-tracked ``triage.jsonl`` and can trip ``validate_triage_text``,
blocking the sweep. The corruption has to be fixed on disk too.

The outbox is UNTRACKED, so a corrupted line has no git history to recover from.
This pass therefore never discards: recovered records are rewritten one per line,
and any text that cannot be decoded is quarantined before the source is touched.

MINIMAL REWRITE
---------------
Lines that were already fine are re-emitted BYTE-FOR-BYTE and the file's existing
EOL style is preserved. Re-serializing every line would (a) reflow a CRLF-written
tracked log to LF, producing a whole-file diff on a ``merge=union`` artifact — a
defect this repo has already been bitten by, see
``shared/tests/test_sweep_drift_commit.py`` — and (b) break the byte-identity dedup
in ``lib.churn_merge.dedup_triage_lines``, which can duplicate ``status`` events into
the tracked log.

SAFETY
------
``--apply`` additionally requires ``--writers-quiesced``. The repair publishes via
``durable_atomic_write``, which replaces the inode; a writer that opened the file
beforehand would go on appending to the unlinked inode and its records would vanish.
The webui writer uses ``proper-lockfile`` (directory-based), which — as
``server/src/core/triage-write.ts`` documents — does NOT compose with the Python
``msvcrt``/``fcntl`` byte-lock this tool takes. So the operator must confirm no other
writer is live. Writers that DO cooperate with that lock are handled properly: under
``--apply`` the scan happens INSIDE the lock, so nothing can slip in between the read
and the atomic replace.

A file containing undecodable bytes is reported but never rewritten — repairing it
could not preserve those bytes, and this pass does not destroy what it cannot keep.

Exit codes: ``0`` nothing to do / repaired, ``1`` repair needed (report mode) or a
file was skipped as unsafe, ``2`` refused (``--apply`` without ``--writers-quiesced``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]  # shared/scripts
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

import triage  # noqa: E402
from lib.atomic_write import durable_atomic_write  # noqa: E402
from lib.jsonl_records import ends_without_newline, split_records  # noqa: E402
from lib.sweep_quarantine import append_quarantine  # noqa: E402
from lib.sweep_text import normalize_lines  # noqa: E402

_QUARANTINE_REASON = "concatenated-records: undecodable remainder on a shared physical line"


@dataclass
class RepairReport:
    """What one file needs. ``lines`` is the repaired content, ready to write."""

    path: Path
    recovered_records: int = 0
    unrecoverable: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    split_lines: int = 0
    unterminated: bool = False
    undecodable_bytes: bool = False
    was_non_empty: bool = False
    eol: str = "\n"

    @property
    def needs_repair(self) -> bool:
        return bool(self.split_lines or self.unrecoverable or self.unterminated)

    @property
    def unsafe(self) -> str:
        """Non-empty reason iff this file must NOT be rewritten."""
        if self.undecodable_bytes:
            return "contains bytes that are not valid UTF-8; a rewrite could not preserve them"
        if self.was_non_empty and not self.lines:
            return "every line is unrecoverable; rewriting would empty the log (and drop its header)"
        return ""


def _read_text(path: Path) -> tuple[str, bool]:
    """``(text, had_undecodable_bytes)`` — never raises on invalid UTF-8."""
    data = path.read_bytes()
    try:
        return data.decode("utf-8"), False
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="surrogateescape"), True


def scan_path(path: Path) -> RepairReport:
    """Read ``path`` and compute the repaired content without writing anything."""
    report = RepairReport(path=path)
    if not path.exists():
        return report
    report.unterminated = ends_without_newline(path)
    text, report.undecodable_bytes = _read_text(path)
    report.was_non_empty = bool(text.strip())
    raw_lines, report.eol = normalize_lines(text)
    for raw_line in raw_lines:
        stripped = raw_line.strip()
        if not stripped:
            continue
        records, remainder = split_records(stripped)
        if len(records) == 1 and not remainder:
            # Already fine — re-emit the ORIGINAL bytes, do not re-serialize.
            report.recovered_records += 1
            report.lines.append(raw_line)
            continue
        if len(records) > 1:
            report.split_lines += 1
        report.recovered_records += len(records)
        report.lines.extend(
            json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in records
        )
        if remainder:
            report.unrecoverable.append(remainder)
    return report


def _fragment_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="surrogateescape")).hexdigest()[:16]


def _already_quarantined(quarantine: Path) -> set[str]:
    """Fragment keys already recorded, so a retry after a crash does not duplicate."""
    if not quarantine.exists():
        return set()
    keys: set[str] = set()
    for line in quarantine.read_text(encoding="utf-8", errors="surrogateescape").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        original = entry.get("original")
        if isinstance(original, str):
            keys.add(_fragment_key(original))
    return keys


def _repair(report: RepairReport, quarantine: Path) -> None:
    """Quarantine first, then publish — never the other way round.

    If the quarantine append succeeds and the replace then fails, the retry
    deduplicates on the content hash. If the replace happened first and quarantine
    failed, the bytes would already be gone.
    """
    if report.unrecoverable:
        seen = _already_quarantined(quarantine)
        fresh, batch_keys = [], set()
        for text in report.unrecoverable:
            key = _fragment_key(text)
            if key in seen or key in batch_keys:
                continue
            batch_keys.add(key)
            fresh.append(text)
        if fresh:
            append_quarantine(quarantine, fresh, reason=_QUARANTINE_REASON)
    text = "".join(line + report.eol for line in report.lines)
    durable_atomic_write(report.path, text)


def _resolve_targets(project_root: Path) -> list[tuple[str, Path]]:
    """The explicit, in-root set of files this tool touches.

    No worktree discovery and no symlink traversal: a repair tool that follows
    repo-controlled paths could otherwise rewrite a file outside the root.
    """
    out: list[tuple[str, Path]] = []
    for kind, path in (
        ("tracked", triage._triage_path(project_root)),
        ("outbox", triage._outbox_path(project_root)),
    ):
        resolved = Path(path).resolve()
        if project_root not in resolved.parents:
            print(f"  SKIP {kind}: {resolved} escapes {project_root}", file=sys.stderr)
            continue
        if path.is_symlink():
            print(f"  SKIP {kind}: {path} is a symlink", file=sys.stderr)
            continue
        out.append((kind, path))
    return out


def _print_reports(reports: list[tuple[str, RepairReport]]) -> None:
    for kind, report in reports:
        state = "NEEDS REPAIR" if report.needs_repair else "clean"
        print(f"{state:>12}  {kind:<8} {report.path}")
        if report.split_lines:
            print(f"               {report.split_lines} concatenated line(s), "
                  f"{report.recovered_records} record(s) recoverable")
        if report.unterminated:
            print("               file does not end with a newline "
                  "(the next append would concatenate)")
        for frag in report.unrecoverable:
            print(f"               unrecoverable ({len(frag)} bytes): {frag[:80]!r}")
        if report.unsafe:
            print(f"               UNSAFE, will not rewrite: {report.unsafe}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project-root", default=".", help="Project directory to repair")
    parser.add_argument(
        "--apply", action="store_true",
        help="Rewrite the files. Without this, the tool only reports.",
    )
    parser.add_argument(
        "--writers-quiesced", action="store_true",
        help="Acknowledge that no other writer (webui, background producer) is live. "
             "Required with --apply: the atomic replace swaps the inode.",
    )
    args = parser.parse_args(argv)

    # Resolve ONCE: the lock, the quarantine and the targets must all agree on the
    # same path string, or the lock guards a different file than the one rewritten.
    project_root = Path(args.project_root).resolve()
    quarantine = project_root / ".shipwright" / "triage.outbox.quarantine.jsonl"
    targets = _resolve_targets(project_root)

    if not args.apply:
        # Read-only: no lock needed, and none taken.
        reports = [(kind, scan_path(path)) for kind, path in targets]
        _print_reports(reports)
        if not any(r.needs_repair for _k, r in reports):
            print("Nothing to repair.")
            return 0
        print("\nReport only. Re-run with --apply --writers-quiesced to repair.")
        return 1

    lock_cls = triage._load_file_lock_cls()
    with lock_cls(triage._lock_path(project_root)):
        # Scan INSIDE the lock: scanning outside it would let a cooperating writer
        # append between the read and the atomic replace, and the stale snapshot
        # would silently overwrite that record.
        reports = [(kind, scan_path(path)) for kind, path in targets]
        _print_reports(reports)
        dirty = [(k, r) for k, r in reports if r.needs_repair]
        if not dirty:
            print("Nothing to repair.")
            return 0
        if not args.writers_quiesced:
            print(
                "\nRefusing to --apply without --writers-quiesced.\n"
                "The repair replaces the file inode. A writer that already has the file\n"
                "open (the webui uses a different lock primitive and does not share this\n"
                "lock) would keep appending to the unlinked inode and those records would\n"
                "be lost. Stop other writers, then re-run with --writers-quiesced.",
                file=sys.stderr,
            )
            return 2
        skipped = 0
        for _kind, report in dirty:
            if report.unsafe:
                print(f"SKIPPED {report.path}: {report.unsafe}", file=sys.stderr)
                skipped += 1
                continue
            _repair(report, quarantine)
            print(f"repaired {report.path}")
    return 1 if skipped else 0


if __name__ == "__main__":
    raise SystemExit(main())
