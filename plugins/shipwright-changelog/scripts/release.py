#!/usr/bin/env python3
"""The release CLI of ``/shipwright-changelog``: one call per step, JSON out.

    uv run release.py prepare   [--project-root .] [--phase-task-id ID] [--version X.Y.Z] [--from vX]
    uv run release.py aggregate [--project-root .] --version X.Y.Z [--dry-run] [--release-date YYYY-MM-DD]
                                [--fallback-entry "Category:text"]...

Thin wrappers over the existing tools with their own flags (``lib/release_*.py``); the JSON on stdout carries the
answer, ``commands`` lists every tool call with its exit code and output, the exit code is the failing tool's own.
Imports follow programme P16: this plugin's modules as ``lib.release_*``, shared modules never as ``lib.<x>``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import release_aggregate, release_prepare  # noqa: E402
from lib.release_runner import Recorder, subprocess_runner  # noqa: E402


def _date(text: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise argparse.ArgumentTypeError(f"{text!r} is not YYYY-MM-DD")
    return text


def _version(text: str) -> str:
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", text):
        raise argparse.ArgumentTypeError(f"{text!r} is not X.Y.Z (no leading v)")
    return text


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="release.py", description="Release steps of /shipwright-changelog")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "aggregate"):
        p = sub.add_parser(name)
        p.add_argument("--project-root", default=".")
        p.add_argument("--version", required=name == "aggregate", type=_version, help="X.Y.Z, no leading v")
    sub.choices["prepare"].add_argument("--phase-task-id")
    sub.choices["prepare"].add_argument("--from", dest="from_version")
    agg = sub.choices["aggregate"]
    agg.add_argument("--dry-run", action="store_true")
    agg.add_argument("--release-date", type=_date, help="YYYY-MM-DD; default: the date prepare stored")
    agg.add_argument("--fallback-entry", action="append", default=[], metavar="CATEGORY:TEXT")
    return parser


def _echo_stderr(payload: dict) -> None:
    for note in payload.get("notices", []):
        print(note, file=sys.stderr)
    for cmd in payload.get("commands", []):
        if cmd["stderr"].strip() and (cmd["exit"] != 0 or cmd["key"] in ("aggregate", "aggregate-dry")):
            print(cmd["stderr"].rstrip(), file=sys.stderr)


def main(argv: list[str] | None = None, runner=subprocess_runner) -> int:
    args = _parser().parse_args(argv)
    rec = Recorder(runner, Path(args.project_root).resolve())
    if args.command == "prepare":
        code, payload = release_prepare.prepare(rec, PLUGIN_ROOT, phase_task_id=args.phase_task_id, version=args.version,
                                                from_version=args.from_version)
    else:
        bad = [e for e in args.fallback_entry if ":" not in e]
        if bad:
            _parser().error(f"--fallback-entry wants CATEGORY:TEXT, got {bad[0]!r}")
        entries = [tuple(e.split(":", 1)) for e in args.fallback_entry]
        code, payload = release_aggregate.aggregate(rec, PLUGIN_ROOT, version=args.version, dry_run=args.dry_run,
                                                    release_date=args.release_date, fallback_entries=entries)
    for stream in (sys.stdout, sys.stderr):  # the banner has an em dash; a Windows code page would mangle it
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", newline="\n")
    _echo_stderr(payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
