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
        --fr-id FR-01.01 \\
        --launch-payload "/shipwright-iterate --type bug \\"fix X\\""

`--launch-payload` is optional (see `DEFAULT_LAUNCH_PAYLOAD` below);
`--no-launch-payload` opts a card out of the default entirely.

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

from triage import append_triage_item, should_route_to_outbox  # noqa: E402

# Canonical FR-ID shape — matches what `shipwright-project` emits and
# what the RTM generator reads back from triage.jsonl's `frId` field.
# Two numeric segments separated by `.`, dash-prefixed: `FR-01.01`,
# `FR-12.34`. Format-only validation; cross-FR existence is deferred.
FR_ID_RE = re.compile(r"^FR-\d+\.\d+$")

# Manual-card default (iterate-2026-08-05-triage-launch-payload-cli): nearly
# every operator-filed card is later worked by typing /shipwright-iterate, so
# that's the default launchPayload when --launch-payload is omitted. `<id>` is
# a literal placeholder, not a template slot — matches the `<ref>` convention
# in aggregate_triage.py's rendered `--task-ref EXT:<ref>` promote command.
# It can't be substituted with the card's real id here: that id is generated
# by triage.append_triage_item() itself, after this default is already built.
# The operator swaps it in using the id printed in this CLI's JSON result.
DEFAULT_LAUNCH_PAYLOAD = "/shipwright-iterate <id>"


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
                        "out the card when context is available. SENSITIVITY: "
                        "triage is git-tracked (the outbox sweeps into the PR "
                        "-> tracked -> public) - keep --title/--detail NEUTRAL: no "
                        "security/vuln detail, file:line, exploit steps, or "
                        "secrets (put those in a gitignored artifact). See "
                        "shared/constitution.md (NEVER).")
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
    launch_group = p.add_mutually_exclusive_group()
    launch_group.add_argument(
        "--launch-payload", default=None,
        help="Ready-to-paste command (stored verbatim as `launchPayload`; "
             "shown fenced on the rendered card for copy-paste into a new "
             "session). Optional — omit to default to "
             f"{DEFAULT_LAUNCH_PAYLOAD!r} ('<id>' is a literal placeholder "
             "for this card's own id, printed in this command's JSON "
             "result). Mutually exclusive with --no-launch-payload.")
    launch_group.add_argument(
        "--no-launch-payload", action="store_true",
        help="Record no launch payload (skips the manual-card default) for "
             "a card with no sensible launch command. Stays a legal card; "
             "the board's missing-payload warning may still apply to it, "
             "same as any other producer that omits the field.")
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


def _resolve_launch_payload(
    raw: str | None, *, no_launch_payload: bool
) -> tuple[str | None, bool]:
    """Resolve --launch-payload / --no-launch-payload into (value, used_default).

    Three cases:

    - ``no_launch_payload`` → ``(None, False)``. Explicit opt-out for a card
      with no sensible launch command — stays legal, matches any other
      producer that omits the field.
    - ``raw`` given (non-blank) → ``(raw, False)``. Overrides the
      manual-card default verbatim.
    - ``raw is None`` (flag omitted) → ``(DEFAULT_LAUNCH_PAYLOAD, True)``.

    Raises ``ValueError`` on a blank/whitespace-only ``--launch-payload``
    (ambiguous with "no payload" — use --no-launch-payload instead).
    """
    if no_launch_payload:
        return None, False
    if raw is None:
        return DEFAULT_LAUNCH_PAYLOAD, True
    if not raw.strip():
        raise ValueError(
            "--launch-payload must not be blank; use --no-launch-payload "
            "to record a card with no launch command."
        )
    return raw, False


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

    try:
        launch_payload, used_default_payload = _resolve_launch_payload(
            args.launch_payload, no_launch_payload=args.no_launch_payload
        )
    except ValueError as exc:
        print(json.dumps({
            "success": False,
            "error": "invalid_launch_payload",
            "detail": str(exc),
        }, indent=2))
        return 1
    if used_default_payload:
        print(
            f"note: no --launch-payload given; defaulting to "
            f"{DEFAULT_LAUNCH_PAYLOAD!r} (nearly every manually filed card "
            "is later worked via /shipwright-iterate). '<id>' is a literal "
            "placeholder — swap in this card's own id (see the JSON result "
            "below) before pasting into a new session. Pass "
            "--no-launch-payload to record none instead.",
            file=sys.stderr,
        )

    # 2) Delegate the rest of validation (title/severity/kind/source) to
    #    triage.append_triage_item — single source of truth (OpenAI #5).
    project_root = Path(args.project_root).resolve()
    # D1 (campaign 2026-06-08-triage-outbox-delivery): when invoked against the
    # idle main tree this CLI fires as a background producer — route to the
    # gitignored outbox (no main drift). Invoked inside an iterate/* branch
    # (worktree or PR branch) it writes the tracked log directly (AC4) since
    # that write ships in the PR.
    to_outbox = should_route_to_outbox(project_root)
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
            launch_payload=launch_payload,
            to_outbox=to_outbox,
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
        "launchPayload": launch_payload,
    }
    if fr_id is not None:
        result["note"] = (
            "--fr-id format-validated only; cross-FR existence not checked. "
            "If the FR doesn't exist in spec.md, the RTM render will silently "
            "omit the deep-link until spec is updated."
        )
    # Constant touchpoint reminder (stderr — keeps the stdout JSON contract clean).
    # "is this content sensitive" is a semantic call code can't make, so the
    # mechanism just surfaces the git-tracked nature on every add.
    print(
        "note: triage is git-tracked (the outbox sweeps into the iterate PR -> "
        "tracked -> public). Keep items NEUTRAL - no security/vuln detail, "
        "file:line, exploit steps, or secrets; put that in a gitignored artifact "
        "(Spec/ report or the gitignored campaign dir). See shared/constitution.md (NEVER).",
        file=sys.stderr,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
