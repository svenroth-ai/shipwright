#!/usr/bin/env python3
"""Resolve single-session phase-gate policies (Campaign 2026-07-07, SS2).

The CLI a phase skill invokes to honour the non-interactive gate mode. It reads
``shared/config/gate_catalog.json`` (via ``lib.gate_policy``) and the run mode,
then prints the effective policy for a gate — or the whole phase.

Mode precedence: ``--mode`` > ``$SHIPWRIGHT_RUN_MODE`` > ``run_config.mode``
(via ``--project-root``) > ``standalone`` (inert). Outside a driven single-session run
every gate resolves to ``interactive`` (today's behaviour).

Examples::

    # one gate (JSON: effective_policy, should_stop, default_answer, ...)
    resolve_gate_policy.py --gate deploy.prod-deploy-confirm --project-root .
    # every gate for a phase, resolved for the current mode
    resolve_gate_policy.py --phase deploy --list --project-root .
    # regenerate the human doc
    resolve_gate_policy.py --render-doc > docs/gate-catalog.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]  # shared/scripts
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.gate_policy import (  # noqa: E402
    COVERED_PHASES,
    INTERACTIVE,
    GateCatalogError,
    effective_mode,
    load_catalog,
    render_catalog_markdown,
    resolve_gate_policy,
)

_ENV_MODE = "SHIPWRIGHT_RUN_MODE"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="resolve_gate_policy.py",
        description="Resolve single-session phase-gate policies.",
    )
    action = p.add_mutually_exclusive_group(required=True)
    action.add_argument("--gate", help="resolve a single gate id")
    action.add_argument("--list", action="store_true", help="list gates (optionally --phase)")
    action.add_argument("--render-doc", action="store_true", help="print docs/gate-catalog.md")
    p.add_argument("--phase", choices=COVERED_PHASES, help="filter --list to one phase")
    p.add_argument("--mode", help="explicit run mode (highest precedence)")
    p.add_argument("--project-root", default=".", help="root holding shipwright_run_config.json")
    p.add_argument(
        "--output",
        help="with --render-doc: write UTF-8/LF to this path directly "
        "(shell-agnostic — avoids a PowerShell '>' re-encoding the doc to UTF-16)",
    )
    return p


def _resolved_rows(catalog: dict, mode: str, phase: str | None) -> list[dict]:
    rows: list[dict] = []
    for gid, g in catalog["gates"].items():
        if phase and g["phase"] != phase:
            continue
        r = resolve_gate_policy(gid, mode=mode, catalog=catalog)
        rows.append(
            {
                "gate_id": gid,
                "phase": g["phase"],
                "policy": g["policy"],
                "effective_policy": r["effective_policy"],
                "should_stop": r["should_stop"],
                "default_answer": r["default_answer"],
                "constitution": g["constitution"],
                "fires": g["fires"],
                "summary": g["summary"],
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    # The doc/JSON may carry non-ASCII in future; a Windows cp1252 stdout would
    # crash on write. Force UTF-8 (no-op where already UTF-8 or not reconfigurable).
    try:
        # newline="\n": don't let a Windows text-mode stdout translate \n -> \r\n
        # (the generated doc must be LF so the drift-guard round-trips cleanly).
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    args = _build_parser().parse_args(argv)

    try:
        catalog = load_catalog()
    except (GateCatalogError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": f"gate catalog unavailable: {exc}"}), file=sys.stderr)
        return 2

    if args.render_doc:
        doc = render_catalog_markdown(catalog)
        if args.output:
            # Explicit UTF-8/LF write — no shell-redirect encoding surprises.
            Path(args.output).write_text(doc, encoding="utf-8", newline="\n")
        else:
            sys.stdout.write(doc)
        return 0

    mode = effective_mode(
        explicit=args.mode,
        env=os.environ.get(_ENV_MODE),
        project_root=args.project_root,
    )

    if args.gate:
        try:
            result = resolve_gate_policy(args.gate, mode=mode, catalog=catalog)
        except KeyError:
            # LLM-facing SAFE fallback: an unknown gate must not crash a phase
            # subagent into a retry loop. Resolve to `interactive` (ask the
            # human — always safe), and warn on stderr so a dev/CI still notices
            # the bad id. (Programmatic callers use the lib, which raises.)
            print(
                f"warning: unknown gate id {args.gate!r} not in the catalog — "
                "falling back to interactive (ask the human)",
                file=sys.stderr,
            )
            result = {
                "gate_id": args.gate,
                "mode": mode,
                "effective_policy": INTERACTIVE,
                "should_stop": True,
                "default_answer": None,
                "unknown_gate": True,
            }
        print(json.dumps(result, indent=2))
        return 0

    # --list (optionally --phase)
    print(json.dumps({"mode": mode, "gates": _resolved_rows(catalog, mode, args.phase)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
