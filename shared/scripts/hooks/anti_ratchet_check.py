#!/usr/bin/env python3
"""Pre-commit + CI gate that blocks bloat anti-ratchet.

Thin CLI shim over ``shared/scripts/lib/anti_ratchet.py`` (core logic).
Two measurement modes: ``--staged`` (default, pre-commit use) and
``--worktree`` (CI use). Block rule: for every entry in
``shipwright_bloat_baseline.json``, if measured > entry.current → exit 1.
New files outside the baseline are advisory. An ABSENT baseline →
fail-open exit 0; a PRESENT-but-malformed baseline → fail-closed exit 1
(a corrupt baseline must not silently disable the gate).

# source-hash-canonical: see shared/tests/test_anti_ratchet_check_staged.py
# — webui vendored copy pins the canonical hash via this marker.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib import anti_ratchet as _ar  # noqa: E402
from lib import bloat_baseline as _bb  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="anti_ratchet_check",
        description=(
            "Bloat-baseline anti-ratchet gate. Exits 1 on ratchet, "
            "0 otherwise. Modes: --staged (default, pre-commit), "
            "--worktree (CI)."
        ),
    )
    p.add_argument("--project-root", default=".", help="Repository root.")
    p.add_argument(
        "--baseline",
        default=None,
        help="Override baseline path (default: <root>/shipwright_bloat_baseline.json).",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--staged", dest="mode", action="store_const", const="staged",
        help="Measure staged content (pre-commit use). DEFAULT.",
    )
    mode.add_argument(
        "--worktree", dest="mode", action="store_const", const="worktree",
        help="Measure files on disk (CI use).",
    )
    p.add_argument("--json", action="store_true", help="Emit JSON on stdout.")
    p.set_defaults(mode="staged")
    return p


def _print_advisory(label: str, items: list[dict], key: str = "path") -> None:
    if not items:
        return
    head = ", ".join(it[key] for it in items[:5])
    tail = f" + {len(items) - 5} more" if len(items) > 5 else ""
    print(
        f"anti_ratchet_check: {label} (advisory): {head}{tail}",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = Path(args.project_root).resolve()

    doc = _ar.load_baseline_override(project_root, args.baseline)
    if doc is None:
        baseline_path = (
            Path(args.baseline) if args.baseline is not None
            else project_root / _bb.BASELINE_FILENAME
        )
        # A PRESENT-but-unreadable/malformed/wrong-shape baseline must NOT
        # silently disable the gate: fail-open here would let a real ratchet
        # sail through under a broken baseline. Fail CLOSED. A genuinely ABSENT
        # baseline (fresh repo) still fails open.
        if baseline_path.is_file():
            print(
                f"anti_ratchet_check: baseline at {baseline_path} exists but is "
                "unreadable or malformed — failing closed (a corrupt baseline must "
                "not disable the gate). Fix or regenerate it.",
                file=sys.stderr,
            )
            if args.json:
                print(json.dumps(
                    {"status": "error", "reason": "malformed-baseline", "ratchets": []}
                ))
            return 1
        if args.baseline is None:
            print(
                "anti_ratchet_check: baseline not found at "
                f"{project_root / _bb.BASELINE_FILENAME} — skipping check (fail-open)",
                file=sys.stderr,
            )
        if args.json:
            print(json.dumps({"status": "skipped", "ratchets": []}))
        return 0

    entries = doc.get("entries", [])
    ratchets, stale = _ar.classify_entries(project_root, entries, args.mode)
    new_crossings: list[dict] = []
    if args.mode == "worktree":
        new_crossings = _ar.scan_new_crossings(project_root, entries)

    _print_advisory("stale baseline entries", stale)
    _print_advisory("new crossings outside baseline", new_crossings)

    if args.json:
        print(json.dumps({
            "status": "block" if ratchets else "ok",
            "ratchets": ratchets,
            "stale": stale,
            "new_crossings": new_crossings,
            "mode": args.mode,
        }))

    if ratchets:
        _ar.emit_iron_law_block(ratchets, sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
