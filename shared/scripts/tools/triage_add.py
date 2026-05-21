#!/usr/bin/env python3
"""Manual triage card creation CLI with optional FR stamping.

AC-1 of iterate-2026-05-21-empirical-followups. Operators stamp FRs onto
new triage cards via this CLI; the existing aggregator + RTM consumer
then render `FAIL → [trg-XXX]` deep-links automatically (the deep-link
infrastructure was empirically verified in V-3 of the artifact-polish
campaign — see `.shipwright/planning/campaigns/2026-05-21-artifact-
polish-empirical-results.md`).

This CLI is the **minimum viable producer** for the B.4 RTM deep-link
unlock. It doesn't auto-map FRs from diffs or test suites (handover
Options 1 + 2 — deferred). Operators with context type the FR-ID
explicitly; the regex `^FR-\\d+\\.\\d+$` is format-validated, not
cross-checked against spec.md (intentional — see iterate spec
Out-of-Scope).

Usage:
    uv run shared/scripts/tools/triage_add.py \\
        --project-root . \\
        --title "Manual card for FR-01.01" \\
        --detail "Operator-stamped via triage_add" \\
        --severity high --kind bug \\
        --source manual \\
        --fr-id FR-01.01

Output: JSON on stdout for both success and validation failures. Exit
0 on success, 1 on validation error. Argparse errors continue to use
argparse's default stderr+exit-2.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Wire up shared/scripts so `triage` resolves whether the file is run as a
# script (`uv run .../triage_add.py`) or imported as a module
# (`tools.triage_add` via tests).
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # shared/scripts
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from triage import append_triage_item  # noqa: E402

# Canonical FR-ID shape — matches what `shipwright-project` emits and
# what the RTM generator reads back from triage.jsonl's `frId` field.
# Two numeric segments separated by `.`, dash-prefixed: `FR-01.01`,
# `FR-12.34`. Format-only validation; cross-FR existence is deferred.
FR_ID_RE = re.compile(r"^FR-\d+\.\d+$")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Add a manual triage card (optionally stamped with an FR ID)."
    )
    p.add_argument("--project-root", required=True,
                   help="Path to the project root (.shipwright/ lives under this).")
    p.add_argument("--title", required=True,
                   help="Short card title (one line, max 160 chars in render).")
    p.add_argument("--detail", default="",
                   help="Card detail body (free-form; downstream renderer "
                        "escapes). Optional — defaults to empty string. "
                        "AC-1 lists --title / --severity / --kind / --source "
                        "/ --fr-id as the canonical surface; --detail rounds "
                        "out the card when context is available.")
    p.add_argument("--severity", required=True,
                   help="Severity: critical | high | medium | low | info "
                        "(validated by triage.append_triage_item).")
    p.add_argument("--kind", required=True,
                   help="Kind: bug | feature | improvement | compliance | maintenance.")
    p.add_argument("--source", default="manual",
                   help="Source label (open vocab; defaults to 'manual').")
    p.add_argument("--fr-id", default=None,
                   help="Optional FR-ID to stamp the card with (e.g. FR-01.01). "
                        "Enables RTM deep-link in `### FRs with open triage items`. "
                        "Must match ^FR-\\d+\\.\\d+$; cross-FR existence is NOT verified.")
    p.add_argument("--evidence-path", default=None,
                   help="Optional path to evidence (relative to project root).")
    p.add_argument("--run-id", default=None,
                   help="Optional run_id tag.")
    p.add_argument("--commit", default=None,
                   help="Optional commit hash tag.")
    return p.parse_args(argv)


def _validate_fr_id(value: str | None) -> str | None:
    """Return the validated fr_id, or raise ValueError.

    `None` (flag omitted) is allowed and returned as-is. An empty or
    whitespace-only string is rejected as "malformed" (the regex's
    anchors handle that, but spell it out for clarity).

    Per OpenAI #5 + Gemini #2: validate ONLY when supplied; don't
    error on the optional path.
    """
    if value is None:
        return None
    if not FR_ID_RE.match(value):
        raise ValueError(
            f"--fr-id {value!r} does not match ^FR-\\d+\\.\\d+$ "
            "(canonical shape: FR-NN.NN, e.g. FR-01.01)."
        )
    return value


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    # 1) Validate --fr-id format (own concern — triage.append_triage_item
    #    doesn't enforce FR-shape, it only type-checks str-or-None).
    try:
        fr_id = _validate_fr_id(args.fr_id)
    except ValueError as exc:
        print(json.dumps({
            "success": False,
            "error": "invalid_fr_id",
            "detail": str(exc),
        }, indent=2))
        return 1

    # 2) Delegate the rest of validation (title/severity/kind/source) to
    #    triage.append_triage_item — single source of truth (OpenAI #5).
    project_root = Path(args.project_root).resolve()
    try:
        item_id = append_triage_item(
            project_root,
            source=args.source,
            severity=args.severity,
            kind=args.kind,
            title=args.title,
            detail=args.detail,
            evidence_path=args.evidence_path,
            run_id=args.run_id,
            commit=args.commit,
            fr_id=fr_id,
        )
    except ValueError as exc:
        # Severity / kind / title validation, or non-str optional fields.
        print(json.dumps({
            "success": False,
            "error": "invalid_input",
            "detail": str(exc),
        }, indent=2))
        return 1

    # 3) Success — JSON on stdout. Include a one-line operator-information
    #    note about format-only validation when --fr-id was supplied
    #    (OpenAI #12: reduce false confidence that the FR exists in spec.md).
    result: dict = {
        "success": True,
        "id": item_id,
        "frId": fr_id,
    }
    if fr_id is not None:
        result["note"] = (
            "--fr-id format-validated only; cross-FR existence not checked. "
            "If the FR doesn't exist in spec.md, the RTM render will silently "
            "omit the deep-link until spec is updated."
        )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
