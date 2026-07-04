#!/usr/bin/env python3
"""grade.py — standalone CLI wrapper over the shipwright-grade core library.

Deterministic and non-interactive: ``grade.py <path> [--format ...]``. This is a
*thin wrapper* — resolve → snapshot → project → grade → render — over the core
library (the same core the ``/shipwright-grade`` plugin command drives and the
eventual ``npx`` CLI will carve from).

Usage:
    uv run scripts/tools/grade.py <path-to-repo> [--format terminal|markdown|json]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

# Make the core library importable bare (see scripts/lib/__init__.py).
_LIB = Path(__file__).resolve().parent.parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from engine_bridge import EngineUnavailableError  # noqa: E402
from gh_bridge import run_gh  # noqa: E402
from git_exec import remote_url  # noqa: E402
from grade_inputs_projector import grade_context  # noqa: E402
from network_policy import resolve_network_policy  # noqa: E402
from render_markdown import render_markdown  # noqa: E402
from render_terminal import render_terminal  # noqa: E402
from repo_context import RepoContext  # noqa: E402
from resolve_target import TargetError, resolve_target  # noqa: E402


def _force_utf8_stdio() -> None:
    """Emit UTF-8 regardless of the console code page.

    The card carries em dashes / ellipses / emoji; on a Windows cp1252 console a
    bare ``print`` of those raises ``UnicodeEncodeError``. Reconfigure to UTF-8
    with replacement so the CLI never crashes on output.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - defensive
                pass


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="shipwright-grade",
        description="Grade a local git repository against the Control Grade rubric.",
    )
    parser.add_argument("path", help="Path to a local git repository")
    parser.add_argument(
        "--format", choices=("terminal", "markdown", "json"),
        default="terminal", help="Output format (default: terminal)",
    )
    parser.add_argument(
        "--allow-network", action="store_true",
        help="Opt into GitHub enrichment (CI test tiers + code-scanning). "
             "Default OFF — private repos never leave the machine.",
    )
    parser.add_argument(
        "--allow-network-private", action="store_true",
        help="Also enrich when the remote is private/unverifiable (implies the "
             "repo identity is sent to GitHub). Requires --allow-network.",
    )
    return parser.parse_args(argv)


def run(argv: list[str]) -> int:
    _force_utf8_stdio()
    args = _parse_args(argv)
    try:
        target = resolve_target(args.path)
    except TargetError as exc:
        print(f"shipwright-grade: {exc}", file=sys.stderr)
        return 2

    try:
        context = RepoContext(target)
        policy = resolve_network_policy(
            allow_network=args.allow_network,
            allow_private=args.allow_network_private,
            remote_url=remote_url(target.local_path),
            gh=run_gh,
        )
        model = grade_context(context, policy=policy, gh=run_gh)
    except EngineUnavailableError as exc:
        print(f"shipwright-grade: engine unavailable: {exc}", file=sys.stderr)
        return 3

    if args.format == "json":
        print(json.dumps(dataclasses.asdict(model), indent=2, ensure_ascii=False))
    elif args.format == "markdown":
        print(render_markdown(model))
    else:
        print(render_terminal(model))
    return 0


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
