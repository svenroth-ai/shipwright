#!/usr/bin/env python3
"""Record what a design round or a build section changed about the requirements.

The write boundary for the mechanism described in :mod:`lib.requirement_impact`:
one declaration per ``(run_id, phase, scope)``, validated before anything
reaches disk.

Usage::

    # design — a feedback round that only changed how things look
    uv run record_requirement_impact.py --project-root . \\
      --run-id "$RUN" --phase design --scope round-2 \\
      --impact none --reason "spacing and colour only; no flow changed" --worktree

    # design — a round that changed what a flow DOES
    uv run record_requirement_impact.py --project-root . \\
      --run-id "$RUN" --phase design --scope round-3 \\
      --impact modify --fr FR-01.09 --worktree

    # build — a section, after its commit, that had to touch something shared
    uv run record_requirement_impact.py --project-root . \\
      --run-id "$RUN" --phase build --scope 01-auth \\
      --impact none --reason "section matched the mockup and the spec" \\
      --base-ref main --head-ref HEAD \\
      --extra "src/lib/http.py=section needed a shared retry helper"

**Fail-closed.** Any validation error exits 1 and writes nothing at all — a
half-recorded declaration is worse than none, because a later completion gate
would read it as satisfied.

Origin: trg-e9e5188e (FR-01.04, FR-01.05).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]  # shared/scripts
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.atomic_write import durable_atomic_write  # noqa: E402
from lib.fr_classification import (  # noqa: E402
    is_behavior_affecting,
    is_valid_none_reason,
)
from lib.requirement_impact import (  # noqa: E402
    PHASE_VALUES,
    SPEC_IMPACT_VALUES,
    check_declaration,
    declaration_error,
    is_requirement_spec,
    normalize_extras,
)
from lib.requirement_impact_git import (  # noqa: E402
    SOURCE_ERROR,
    SOURCE_SKIPPED,
    changed_paths,
)
from lib.requirement_impact_baseline import (  # noqa: E402
    changed_specs_since,
    read_baseline,
    write_baseline,
)
from lib.requirement_impact_store import (  # noqa: E402
    declaration_dir,
    declaration_filename,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record a design round's or build section's requirement impact",
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--run-id", required=True,
                        help="the run this declaration belongs to — part of its identity")
    # No argparse `choices` for --phase/--impact: argparse would exit 2 with
    # plain-text stderr, bypassing the documented fail-closed exit-1 JSON path
    # AND duplicating a vocabulary the shared validator already owns.
    parser.add_argument("--phase", required=True,
                        help=f"one of {list(PHASE_VALUES)}")
    parser.add_argument("--scope", required=True,
                        help="design round (e.g. round-2) or build section (e.g. 01-auth)")
    # Not `required`: --snapshot-baseline declares no impact yet, and argparse
    # would reject it before main() could dispatch. Absence is validated below.
    parser.add_argument("--impact",
                        help=f"one of {list(SPEC_IMPACT_VALUES)} "
                             "(required unless --snapshot-baseline)")
    parser.add_argument("--reason",
                        help="one-line justification — REQUIRED when --impact none")
    parser.add_argument("--fr", action="append", dest="frs", default=[],
                        metavar="FR-XX.YY",
                        help="requirement this changed (repeatable, required "
                             "when --impact is add/modify/remove)")
    parser.add_argument("--extra", action="append", dest="extras", default=[],
                        metavar="PATH=WHY",
                        help="a shared file this section had to touch that its "
                             "plan did not list, and why (repeatable)")
    parser.add_argument("--contradiction",
                        help="when the approved mockup and the section description "
                             "disagreed: who decided and what they decided")
    group = parser.add_argument_group("evidence (exactly one mode)")
    group.add_argument("--worktree", action="store_true",
                       help="uncommitted changes vs HEAD (design rounds)")
    group.add_argument("--base-ref", help="range start (build sections)")
    group.add_argument("--head-ref", help="range end (build sections)")
    parser.add_argument("--snapshot-baseline", action="store_true",
                        help="capture this round's requirement-spec baseline and "
                             "exit — run BEFORE the round revises anything")
    return parser


def _evidence_mode_error(args) -> dict | None:
    """Each phase has exactly one legitimate evidence boundary.

    A **design** round has no commit, so it is judged against the baseline it
    snapshotted (`--worktree`). A **build** section has one, so it is judged
    against that commit and nothing wider — an older or broader range containing
    some unrelated requirement edit would otherwise satisfy `--impact modify`
    while the section itself touched no requirement.
    """
    if args.phase == "design" and not args.worktree:
        return {
            "error": "requirement_impact_wrong_evidence_mode",
            "detail": (
                "a design round is judged against the baseline it snapshotted, "
                "so it must use --worktree. A committed range would let any "
                "historical spec edit satisfy this round's declaration."
            ),
        }
    if args.phase == "build" and args.worktree:
        return {
            "error": "requirement_impact_wrong_evidence_mode",
            "detail": (
                "a build section is judged against its own commit, so it must "
                "use --base-ref/--head-ref (normally HEAD^ and HEAD, run after "
                "the section commit)."
            ),
        }
    return None


def _fail(payload: dict) -> int:
    print(json.dumps({"success": False, **payload}, indent=2))
    return 1


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = Path(args.project_root).resolve()

    if args.snapshot_baseline:
        return _snapshot(args, project_root)

    if args.impact is None:
        return _fail({
            "error": "requirement_impact_invalid_impact",
            "detail": f"--impact is required, and must be one of "
                      f"{list(SPEC_IMPACT_VALUES)}.",
        })

    if args.worktree and (args.base_ref or args.head_ref):
        return _fail({
            "error": "requirement_impact_ambiguous_evidence",
            "detail": "--worktree and --base-ref/--head-ref are mutually exclusive.",
        })

    # The evidence mode belongs to the PHASE, not to the caller's argv. Leaving
    # it free let a design round skip its baseline by naming any historical
    # range that happened to contain a spec edit — the boundary defeated by flag
    # choice rather than by argument.
    mode_error = _evidence_mode_error(args)
    if mode_error is not None:
        return _fail(mode_error)

    try:
        extras = normalize_extras(args.extras)
    except ValueError as exc:
        return _fail({"error": "requirement_impact_invalid_extra", "detail": str(exc)})

    # `--reason` is validated by the rule only on the `none` branch, and
    # `--contradiction` / `--scope` not at all. Bound them here so no free-text
    # field can carry a multi-line wall of text into a record meant to stay
    # one-line greppable.
    for flag, value in (("--reason", args.reason),
                        ("--contradiction", args.contradiction),
                        ("--scope", args.scope)):
        if value is not None and not is_valid_none_reason(value):
            return _fail({
                "error": "requirement_impact_invalid_text",
                "detail": (f"{flag} must be a non-empty single line, max 280 chars, "
                           "with no control characters."),
            })

    evidence = changed_paths(
        project_root,
        base_ref=args.base_ref, head_ref=args.head_ref, worktree=args.worktree,
        single_commit=(args.phase == "build"),
    )
    # A bad ref is a caller mistake, not an unavailable environment. Letting it
    # degrade into "check skipped" is exactly how a typo would silently disable
    # the gate, so it rejects.
    if evidence["source"] == SOURCE_ERROR:
        return _fail({
            "error": "requirement_impact_evidence_unusable",
            "detail": evidence["detail"],
        })

    changed = evidence["changed"]
    baseline_specs = None
    if args.phase == "design" and is_behavior_affecting(args.impact):
        # A worktree diff answers "what is uncommitted", which in the standard
        # pipeline (nothing commits before build) lists every untracked spec the
        # project phase wrote — so ANY modify passed on a spec nobody edited.
        # The round's own baseline is what restores the boundary a commit gives
        # a build section. Absent baseline ⇒ refuse: fail-closed.
        baseline = read_baseline(declaration_dir(project_root),
                                 run_id=args.run_id, phase=args.phase,
                                 scope=args.scope)
        if baseline is None:
            return _fail({
                "error": "requirement_impact_no_baseline",
                "detail": (
                    f"--impact {args.impact} in --worktree mode needs this round's "
                    "baseline, and none was recorded for "
                    f"({args.run_id!r}, {args.phase!r}, {args.scope!r}). Run this "
                    "command with --snapshot-baseline BEFORE the round revises "
                    "anything, so 'the requirement was corrected' can be checked "
                    "against what it said when the round started."
                ),
            })
        baseline_specs = changed_specs_since(baseline, project_root)
        changed = baseline_specs

    error = check_declaration(
        run_id=args.run_id, phase=args.phase, scope=args.scope,
        impact=args.impact, reason=args.reason, frs=args.frs,
        extras=extras, changed_paths=changed,
    )
    if error is not None:
        return _fail(error)

    if evidence["source"] == SOURCE_SKIPPED:
        print(
            f"[record_requirement_impact] WARNING: {evidence['detail']} — the "
            "requirements-touch check did NOT run for this declaration.",
            file=sys.stderr,
        )

    record = {
        "run_id": args.run_id,
        "phase": args.phase,
        "scope": args.scope,
        "impact": args.impact,
        "reason": (args.reason or "").strip() or None,
        "frs": list(args.frs),
        "extras": extras,
        "contradiction": (args.contradiction or "").strip() or None,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        # Whether the touch check actually ran is part of the record. A reader
        # must be able to tell a verified declaration from one made where no
        # evidence was obtainable, instead of assuming every record was checked.
        "touch_check": {
            "source": evidence["source"],
            "detail": evidence["detail"],
            # The RESOLVED endpoints, so a later reader can audit which range was
            # inspected. A symbolic "HEAD~1..HEAD" means something different from
            # every commit, so on its own it proves nothing after the fact.
            "base_sha": evidence.get("base_sha"),
            "head_sha": evidence.get("head_sha"),
            # For a baselined design round these are the specs that actually
            # differ from the round's starting state, not merely everything
            # uncommitted.
            "baselined": baseline_specs is not None,
            "spec_files": [
                p for p in ((baseline_specs if baseline_specs is not None
                             else evidence["changed"]) or [])
                if is_requirement_spec(p)
            ],
        },
    }

    target_dir = declaration_dir(project_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / declaration_filename(args.run_id, args.phase, args.scope)
    durable_atomic_write(target, json.dumps(record, indent=2) + "\n")

    print(json.dumps({
        "success": True,
        "path": str(target.relative_to(project_root)),
        "impact": args.impact,
        "touch_check": record["touch_check"]["source"],
    }, indent=2))
    return 0


def _snapshot(args, project_root: Path) -> int:
    """``--snapshot-baseline``: capture the round's starting requirement state."""
    error = _identity_error(args)
    if error is not None:
        return _fail(error)
    try:
        payload = write_baseline(declaration_dir(project_root),
                                 run_id=args.run_id, phase=args.phase,
                                 scope=args.scope, project_root=project_root)
    except OSError as exc:
        return _fail({"error": "requirement_impact_baseline_unwritable",
                      "detail": str(exc)})
    print(json.dumps({
        "success": True, "action": "baseline",
        "run_id": args.run_id, "phase": args.phase, "scope": args.scope,
        "specs_captured": len(payload["specs"]),
    }, indent=2))
    return 0


def _identity_error(args) -> dict | None:
    """Validate only the identity fields — a baseline declares no impact yet."""
    return declaration_error(
        run_id=args.run_id, phase=args.phase, scope=args.scope,
        impact="none", reason="baseline snapshot", frs=[], extras=[])


if __name__ == "__main__":
    sys.exit(main())
