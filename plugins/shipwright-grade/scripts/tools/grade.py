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
from datetime import datetime, timezone
from pathlib import Path

# Make the core library importable bare (see scripts/lib/__init__.py).
_LIB = Path(__file__).resolve().parent.parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from engine_bridge import EngineUnavailableError  # noqa: E402
from gh_bridge import is_github_com_remote, run_gh  # noqa: E402
from git_exec import remote_url  # noqa: E402
from grade_inputs_projector import grade_context  # noqa: E402
from html_report import render_html  # noqa: E402
from network_policy import resolve_network_policy  # noqa: E402
from render_markdown import render_markdown  # noqa: E402
from render_terminal import render_terminal  # noqa: E402
from repo_context import RepoContext  # noqa: E402
from resolve_target import TargetError, open_target  # noqa: E402


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
        "--format", choices=("terminal", "markdown", "json", "html"),
        default="terminal",
        help="Output format (default: terminal). 'html' emits a single "
             "self-contained report to stdout — redirect it: "
             "grade.py <path> --format html > report.html",
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
    parser.add_argument(
        "--no-clone", action="store_true",
        help="Forbid cloning: a URL / owner/repo target then errors instead of "
             "being shallow-cloned. Local paths are unaffected.",
    )
    return parser.parse_args(argv)


def run(argv: list[str]) -> int:
    _force_utf8_stdio()
    args = _parse_args(argv)
    # A remote target is shallow-cloned into a throwaway tempdir that is purged
    # when the `with` block exits — the model is fully materialised inside it, so
    # rendering below is safe after the clone is gone.
    try:
        with open_target(args.path, allow_clone=not args.no_clone) as target:
            context = RepoContext(target)
            target_remote = remote_url(target.local_path)
            # A github.com URL / owner-repo target is fetched from github.com
            # anyway — its identity is already sent there to clone it — so default
            # network enrichment ON for it. A LOCAL path stays local-only by
            # default (privacy-first: never send a private repo's identity without
            # an explicit --allow-network). A GitHub Enterprise / other host is
            # EXCLUDED from the default: gh enrichment queries github.com, a host
            # the clone never contacted, so its slug must not leak without a flag.
            # resolve_network_policy still probes visibility and auto-disables on a
            # private/unverifiable remote (--allow-network-private stays opt-in),
            # and falls back to a local grade when gh is unavailable — so a URL
            # grade is never a false F.
            allow_network = args.allow_network or (
                target.input_kind == "url" and is_github_com_remote(target_remote))
            policy = resolve_network_policy(
                allow_network=allow_network,
                allow_private=args.allow_network_private,
                remote_url=target_remote,
                gh=run_gh,
            )
            model = grade_context(context, policy=policy, gh=run_gh)
    except TargetError as exc:
        print(f"shipwright-grade: {exc}", file=sys.stderr)
        return 2
    except EngineUnavailableError as exc:
        print(f"shipwright-grade: engine unavailable: {exc}", file=sys.stderr)
        return 3

    if args.format == "json":
        print(json.dumps(dataclasses.asdict(model), indent=2, ensure_ascii=False))
    elif args.format == "markdown":
        print(render_markdown(model))
    elif args.format == "html":
        # The wall-clock lands ONLY in the footer; scored content stays
        # deterministic (see html_report.render_html). Write (not print) so a
        # redirected `> report.html` is exactly the document — the rendered
        # string already ends with a single trailing newline.
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        sys.stdout.write(render_html(model, generated_at=stamp))
    else:
        print(render_terminal(model))
    return 0


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
