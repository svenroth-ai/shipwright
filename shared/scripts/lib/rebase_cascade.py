"""Rebase-cascade counter + exhaustion decision for campaign-mode.md's step
3f-bis (campaign-dag-scheduler R5b, round 7 Tier-3 review: "add executable
integration coverage for ... conflict/rebase").

Before this module, 3f-bis parsed and compared `rebase_count` inline in
bash (`cat "$run_dir/rebase_count" 2>/dev/null`, a `case` guard for a
missing/non-numeric file, then `[ "$rebase_count" -ge 2 ]`) — logic a
prose-guard test can only confirm by string-matching, never by actually
running it against the edge cases that matter (missing file, a corrupted
non-numeric value, the exact boundary between the last permitted rebase and
exhaustion). This module extracts exactly that decision logic into real,
directly-testable Python; the surrounding orchestration (invalidate the
review pin, demote the unit, call `ensure_current.py`, re-enter 3f-bis)
stays in campaign-mode.md's own prose, since it only sequences three
already-independently-tested tools (`check_review_attribution.py`,
`loop_claim.py`, `ensure_current.py`) and has no logic of its own to pull
out — extracting a call sequence into a script would just relocate the
orchestration, not make it more testable.
"""

from __future__ import annotations

import argparse
from pathlib import Path

#: Mirrors the bash block's own literal `max_rebase_reviews = 2` (a unit may
#: rebase twice; the third `CONFLICTING` result exhausts the cascade).
DEFAULT_MAX_REBASE_REVIEWS = 2

_COUNT_FILENAME = "rebase_count"


def read_rebase_count(run_dir: Path | str) -> int:
    """Mirrors the shell's own `cat ... 2>/dev/null` + non-numeric guard —
    a missing file or non-numeric contents both read as 0 (a fresh cascade),
    never raise."""
    path = Path(run_dir) / _COUNT_FILENAME
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return 0
    return int(raw) if raw.isdigit() else 0


def write_rebase_count(run_dir: Path | str, count: int) -> None:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / _COUNT_FILENAME).write_text(f"{count}\n", encoding="utf-8")


def decide_rebase_action(rebase_count: int, *, max_rebase_reviews: int = DEFAULT_MAX_REBASE_REVIEWS) -> str:
    """`"exhausted"` once `rebase_count` has reached the cap (the unit goes
    `held`, `reason_code: staleness_cascade_exhausted`); else `"rebase"`
    (invalidate the pin, demote to `built`, call `ensure_current.py`)."""
    return "exhausted" if rebase_count >= max_rebase_reviews else "rebase"


def _cmd_read_count(args: argparse.Namespace) -> int:
    print(read_rebase_count(args.run_dir))
    return 0


def _cmd_write_count(args: argparse.Namespace) -> int:
    write_rebase_count(args.run_dir, args.count)
    return 0


def _cmd_decide(args: argparse.Namespace) -> int:
    print(decide_rebase_action(args.rebase_count, max_rebase_reviews=args.max_rebase_reviews))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    read_p = sub.add_parser("read-count", help="Print the current rebase_count for a run dir (0 if absent/invalid).")
    read_p.add_argument("--run-dir", type=Path, required=True)
    read_p.set_defaults(func=_cmd_read_count)

    write_p = sub.add_parser("write-count", help="Persist rebase_count for a run dir.")
    write_p.add_argument("--run-dir", type=Path, required=True)
    write_p.add_argument("--count", type=int, required=True)
    write_p.set_defaults(func=_cmd_write_count)

    decide_p = sub.add_parser("decide", help="Print 'exhausted' or 'rebase' for a given rebase_count.")
    decide_p.add_argument("--rebase-count", type=int, required=True)
    decide_p.add_argument("--max-rebase-reviews", type=int, default=DEFAULT_MAX_REBASE_REVIEWS)
    decide_p.set_defaults(func=_cmd_decide)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
