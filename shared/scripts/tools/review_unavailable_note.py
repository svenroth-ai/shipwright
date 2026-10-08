"""Print the one line F12 and the PR body carry for review passes that did not run.

    uv run review_unavailable_note.py --project-root . --run-id iterate-2026-10-08-x [--file-triage]

Reads the run's review record and prints ``none``, or every pass closed
``reason_code: unavailable`` with the path of its captured adapter error, e.g.
``2 (plan, external_code) - adapter error: .shipwright/planning/iterate/<run>/external-plan-review-raw.json, ...``.
Paths only, never artifact content (stderr can carry provider URLs).

``--file-triage`` (autonomous runs) also files ONE triage card per run asking
for the review to be re-run, idempotent on the run id: a second call finds the
card instead of adding one, and the line ends ``; re-run card <id>`` (plus its
status, e.g. ``(dismissed)``, when that card is no longer open). File
it once, after the run's last external pass. A filing failure exits 1 and says
so - "loud, not silent" must not degrade into a card nobody filed.

Exit 0 on a readable record, 1 when it is missing/unreadable, when an
adapter-backed ``unavailable`` row has no valid capture (the line then says
``INVALID - ...`` and no card is filed), or when the card could not be filed - so
a PR body never claims ``none`` for a broken record, nor files a card for a
claim the F11 check would refuse.

A ``WARN`` on stderr names any ``.stderr.txt`` capture that backs no
``unavailable`` row: F6 stages the whole run dir, so delete it before commit.

Not itself a gate: ``none`` means no row says ``unavailable``; F11's
review-record check is what proves every pass answered. It reads the WORKING
tree (it runs at F12 / PR time, after the capture was staged); F11 reads the
commit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.review_record import ReviewRecordError, read_record  # noqa: E402
from lib.review_unavailable import (  # noqa: E402
    ADAPTER_REVIEW_TYPES,
    artifact_paths,
    artifact_problem,
    unavailable_rows,
    worktree_reader,
)

_SOURCE = "iterate"


def _dedup_key(run_id: str) -> str:
    return f"review-unavailable:{run_id}"


def _evidence(root: Path, run_id: str, rows: list[str]) -> tuple[list[str], list[str]]:
    """``(capture paths, problems)`` for the adapter-backed rows among ``rows``."""
    read = worktree_reader(root)
    paths, problems = [], []
    for review_type in rows:
        if review_type in ADAPTER_REVIEW_TYPES:
            problem, path = artifact_problem(run_id, review_type, read)
            if problem:
                problems.append(f"{review_type}: {problem}")
            else:
                paths.append(path)
    return paths, problems


def stray_stderr(root: Path, run_id: str, rows: list[str]) -> list[str]:
    """``.stderr.txt`` captures on disk that back no ``unavailable`` row (F6 stages the run dir)."""
    errs = (artifact_paths(run_id, t)[1] for t in ADAPTER_REVIEW_TYPES if t not in rows)
    return [e for e in errs if (root / e).exists() or (root / e).is_symlink()]


def summary_line(rows: list[str], paths: list[str]) -> str:
    if not rows:
        return "none"
    line = f"{len(rows)} ({', '.join(rows)}) - did NOT run (unavailable)"
    return line + (f"; adapter error: {', '.join(paths)}" if paths else "")


def file_card(root: Path, run_id: str, rows: list[str]) -> str:
    """The id of the run's re-run card — new, or the one already filed (its status when not open)."""
    from triage import append_triage_item_idempotent, read_all_items, should_route_to_outbox

    item_id = append_triage_item_idempotent(
        root, source=_SOURCE, severity="medium", kind="maintenance",
        title=f"Re-run the review(s) that did not run for {run_id}: {', '.join(rows)}",
        detail=(f"Run {run_id} closed {', '.join(rows)} not_run with reason_code "
                "unavailable (the reviewer could not run) and continued autonomously. "
                "The change was merged or is being merged without that review. Re-run "
                "it against the merged diff and record the outcome."),
        dedup_key=_dedup_key(run_id), match_commit=False, window_seconds=None,
        run_id=run_id, to_outbox=should_route_to_outbox(root),
        launch_payload=f"/shipwright-iterate re-run the external review for {run_id} ({', '.join(rows)})",
    )
    if item_id:
        return item_id
    for item in read_all_items(root):
        if item.get("source") == _SOURCE and item.get("dedupKey") == _dedup_key(run_id):
            status = item.get("status")
            return str(item.get("id")) + (f" ({status})" if status and status != "triage" else "")
    raise RuntimeError("the card was neither filed nor found")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--file-triage", action="store_true",
                        help="also file one re-run triage card for this run (autonomous runs)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # a cp1252 console cannot print the em dash in a refusal
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = Path(args.project_root)
    try:
        record = read_record(root, args.run_id)
    except ReviewRecordError as exc:
        print(f"INVALID - the review record is unreadable ({exc})")
        return 1
    if record is None:
        print(f"INVALID - no review record for {args.run_id}")
        return 1
    rows = unavailable_rows(record)
    for err in stray_stderr(root, args.run_id, rows):
        print(f"WARN - {err} backs no unavailable row: delete it before commit (F6 stages the run dir)",
              file=sys.stderr)
    paths, problems = _evidence(root, args.run_id, rows)
    if problems:
        print(f"INVALID - `unavailable` without a valid capture ({'; '.join(problems)}); no card filed")
        return 1
    line = summary_line(rows, paths)
    if rows and args.file_triage:
        try:
            line += f"; re-run card {file_card(root, args.run_id, rows)}"
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            print(f"{line}; re-run card NOT FILED ({exc})")
            return 1
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
