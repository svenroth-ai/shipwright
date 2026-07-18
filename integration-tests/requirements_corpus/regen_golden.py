"""Regenerate ``golden.json``. Deliberately NOT a pytest flag.

    uv run integration-tests/requirements_corpus/regen_golden.py

A ``pytest --update-golden`` flag would let anyone rerun-to-green the moment
campaign step S2 breaks this harness. That would make S2's "behaviour-preserving"
claim self-certifying and destroy the one guarantee this corpus provides. The
separate script is the friction, and the friction is the point.

Before committing a regenerated baseline, read the diff. Every changed line is a
behaviour change in the requirements machinery; if you cannot say which change
caused it and why it is intended, do not commit it.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

_PKG_PARENT = str(Path(__file__).resolve().parent.parent)
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)

from requirements_corpus.collect import collect_all, dumps  # noqa: E402
from requirements_corpus.frozen_bugs import as_json_block  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden.json"


def build(reason: str | None = None) -> str:
    payload = collect_all()
    payload["frozen_bugs"] = as_json_block()
    if reason:
        payload["regenerated_for"] = reason
    return dumps(payload)


def _committed_reason() -> str | None:
    if not GOLDEN.exists():
        return None
    import json
    return json.loads(GOLDEN.read_text(encoding="utf-8")).get("regenerated_for")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="print the diff and exit 1 if stale; write nothing")
    ap.add_argument(
        "--reason",
        help="REQUIRED to write. Name the behaviour change this baseline is "
             "being updated for. It is stamped into golden.json, so the "
             "justification travels in the same diff a reviewer reads.",
    )
    args = ap.parse_args()

    if not args.check and not args.reason:
        print(
            "Refusing to regenerate without --reason.\n\n"
            "Every line this would rewrite is a behaviour change in the\n"
            "requirements machinery. A bare regeneration is how a baseline\n"
            "gets destroyed: someone runs it to make a red suite green, and\n"
            "the behaviour-preserving claim the corpus exists to check\n"
            "becomes self-certifying.\n\n"
            "  --check                 show the diff, write nothing\n"
            '  --reason "<what changed and why it is intended>"\n',
            file=sys.stderr,
        )
        return 2

    fresh = build(args.reason or _committed_reason())
    old = GOLDEN.read_text(encoding="utf-8") if GOLDEN.exists() else ""

    if old == fresh:
        print("golden.json is current.")
        return 0

    diff = "".join(difflib.unified_diff(
        old.splitlines(keepends=True), fresh.splitlines(keepends=True),
        fromfile="golden.json (committed)", tofile="golden.json (fresh)",
    ))
    print(diff or "(no textual diff, but content differs)")

    if args.check:
        print("\nSTALE -- the machinery's behaviour differs from the baseline.")
        return 1

    GOLDEN.write_text(fresh, encoding="utf-8")
    print(f"\nWrote {GOLDEN}.")
    print("Every line above is a BEHAVIOUR CHANGE. Do not commit it unless you "
          "can name the change that caused it and why it is intended.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
