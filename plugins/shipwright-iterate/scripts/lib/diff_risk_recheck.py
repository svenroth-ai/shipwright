#!/usr/bin/env python3
"""Post-Build diff-driven risk re-check for the campaign sub-iterate-runner.

The campaign `sub-iterate-runner` classifies once, at its Step 2, from the spec
text before any code exists, and `classify()` detects risk by regex over that
message. The diff-driven detectors in :mod:`risk_detectors` are reached only by
the Stage-2 Repo Scout, which the runner never runs — so those flags cannot fire
for a campaign unit. This is its Stage-2 equivalent (contract Step 3.4).
Rationale: `references/campaign-mode.md`.

**One-way ratchet.** Complexity rises to the detectors' floor, never falls, and
Stage-1's flags are UNIONED in, never replaced — see :func:`recheck`.

**Process contract.** `0` continue · `3` valid CI escalation · any other non-zero
is an operational failure the caller must treat as a failed unit, never continuing
on Stage 1's stale estimate. Every exit this module *decides* writes valid JSON to
stdout; no exit `3` is ever emitted without JSON. Branch on the status *and* parse
stdout; never run under bare ``set -e``.

**The escalation must be exitable.** An operator who records the acknowledgement
and re-runs the unit would otherwise hit the same escalation forever — Build
re-creates the same CI edit. So a recorded ack for THIS run clears the stop while
leaving the flag and paths reported. Presence is all that is checked here;
`check_ci_supplychain_ack` still validates the ack's content, run binding and
diff fingerprint at F11, so a bogus file buys nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

# Self-bootstrap: sibling modules must resolve even under
# importlib.spec_from_file_location (contracts/iterate.py, test harnesses).
_LIB_DIR = str(Path(__file__).resolve().parent)
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from complexity_vocabulary import COMPLEXITY_ORDER  # noqa: E402
from diff_change_set import (  # noqa: E402, F401 — re-exported surface
    _git, collect_change_set, parse_numstat_z, parse_untracked_z, resolve_base,
)
from risk_detectors import (  # noqa: E402
    _normalize_diff_path,
    is_ci_supplychain_change,
    is_cross_component_change,
    is_io_boundary_change,
    touches_build_files,
)

#: Reason code carried by an escalated result. Bound to the operator decision of
#: 2026-08-01: a runner touching the CI trust boundary STOPS and hands back. It
#: never writes its own ack — that names the recorded posture decision a change
#: agrees with, and a machine authoring its own permission slip is what
#: `check_ci_supplychain_ack` exists to prevent.
CI_ESCALATION_REASON_CODE = "ci_supplychain_requires_operator"

#: Step 3.7's diff-size arm, mirrored onto Step 3.5 (AC5). Strictly greater-than,
#: matching the contract's "> 100" wording exactly.
PLAN_REVIEW_DIFF_LOC_THRESHOLD = 100

Detector = Callable[[list[str]], bool]

#: (flag, detector, floor). Floors mirror `risk_taxonomy.RISK_TAXONOMY`;
#: `cross_component` alone floors at medium, which is what stops
#: `check_integration_coverage` green-SKIPping (it reads the F5c complexity).
_DETECTORS: tuple[tuple[str, Detector, str], ...] = (
    ("cross_component", is_cross_component_change, "medium"),
    ("touches_ci_supplychain", is_ci_supplychain_change, "small"),
    ("touches_io_boundary", is_io_boundary_change, "small"),
    ("touches_build", touches_build_files, "small"),
)


def _rank(level: str) -> int:
    """Index in the canonical order. Never compare complexity as strings:
    lexicographically "small" > "medium", so ``max()`` would DOWNGRADE a run."""
    return COMPLEXITY_ORDER.index(level)


def normalized_paths(changed_files) -> list[str]:
    """One canonical de-duplicated set — drives detection, counting AND reporting.

    Normalising BEFORE detection is load-bearing: only the CI and build detectors
    normalise internally. git quotes non-ASCII paths, so an unnormalised
    ``"plugins/x/hooks/hök.py"`` keeps a trailing quote that defeats the ``\\.py$``
    anchor and silently leaves cross_component down."""
    seen: set[str] = set()
    out: list[str] = []
    for path in changed_files or []:
        norm = _normalize_diff_path(path)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def detect_diff_flags(changed_files) -> list[str]:
    """Return the sorted, de-duplicated diff-driven risk flags for a file list."""
    files = normalized_paths(changed_files)
    if not files:
        return []
    return sorted(name for name, detect, _ in _DETECTORS if detect(files))


def ci_paths(changed_files) -> list[str]:
    """The CI trust-boundary files in this change set, for the operator handback."""
    return [p for p in normalized_paths(changed_files) if is_ci_supplychain_change([p])]


def ack_path(project_root: Path, run_id: str) -> Path:
    """Where `record_ci_supplychain_ack.py` writes this run's acknowledgement."""
    return (Path(project_root) / ".shipwright" / "planning" / "iterate"
            / run_id / "ci_supplychain_ack.json")


def recheck(
    changed_files,
    stage1_complexity: str,
    diff_loc: int = 0,
    stage1_flags=None,
    ack_recorded: bool = False,
) -> dict:
    """Re-decide risk + complexity from the actual change set.

    ``stage1_flags`` (Step 2's message-derived flags) are unioned in, not replaced:
    seven canonical flags — ``touches_auth``, ``touches_rls``, ``touches_middleware``,
    ``touches_migrations``, ``touches_billing``, ``touches_shared_infra``,
    ``touches_public_api`` — have no diff-driven detector, so discarding them would
    make Step 3.5 skip cases the pre-Step-3.4 rule ran.
    """
    if stage1_complexity not in COMPLEXITY_ORDER:
        raise ValueError(
            f"unknown stage-1 complexity {stage1_complexity!r} — "
            f"expected one of {COMPLEXITY_ORDER}"
        )
    # Validated here rather than in main() so direct callers are covered too. A
    # negative value is not merely odd: the result schema requires `minimum: 0`,
    # so it would emit a result that cannot be represented in the contract, and it
    # suppresses the diff-size review trigger on the way.
    if diff_loc < 0:
        raise ValueError(f"diff_loc must be >= 0, got {diff_loc}")
    files = normalized_paths(changed_files)
    diff_flags = detect_diff_flags(files)
    # Floors come from the DIFF flags only — Stage 1 already applied its own flags'
    # floors when it produced stage1_complexity.
    floors = [floor for name, _, floor in _DETECTORS if name in diff_flags]
    complexity_floor = max(floors, key=_rank) if floors else "trivial"
    effective = max([stage1_complexity, complexity_floor], key=_rank)
    flags = sorted(set(diff_flags) | set(stage1_flags or []))
    hits = ci_paths(files)
    return {
        "changed_file_count": len(files),
        "diff_loc": diff_loc,
        "risk_flags": flags,
        "diff_risk_flags": diff_flags,
        "complexity_floor": complexity_floor,
        "stage1_complexity": stage1_complexity,
        "effective_complexity": effective,
        "upgraded": effective != stage1_complexity,
        # AC5: Step 3.5's trigger, now identical to Step 3.7's.
        "plan_review_required": (
            _rank(effective) >= _rank("medium")
            or bool(flags)
            or diff_loc > PLAN_REVIEW_DIFF_LOC_THRESHOLD
        ),
        # `paths` and the flag are reported even once acked — the operator's
        # answer clears the STOP, it does not un-touch the trust boundary.
        "ci_ack_recorded": bool(ack_recorded),
        "escalate": {
            "required": bool(hits) and not ack_recorded,
            "reason_code": CI_ESCALATION_REASON_CODE if hits and not ack_recorded else None,
            "paths": hits,
        },
    }


def _split_flags(raw: str | None) -> list[str]:
    """Accept comma/newline lists AND a JSON array.

    `classify_complexity` emits `risk_flags` as a JSON array, so the obvious
    interpolation of Step 2's output is `["touches_auth", "touches_rls"]`. A
    naive split would yield `['["touches_auth"', '"touches_rls"]']` — tokens that
    still make `plan_review_required` fire (so AC5 looks fine) while Step 3.8's
    named-flag lookup for `touches_io_boundary` silently misses. Strip the JSON
    punctuation rather than trusting the caller to reformat.
    """
    if not raw:
        return []
    cleaned = raw.strip().lstrip("[").rstrip("]")
    parts = cleaned.replace(",", "\n").splitlines()
    return [p.strip().strip('"').strip("'") for p in parts if p.strip(" \"'\t")]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Post-Build diff-driven risk re-check (runner contract Step 3.4)"
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument(
        "--base-ref",
        help="Branch point; its fork point with HEAD is used. Defaults to HEAD — "
             "correct for a first stacked sub-iterate whose base is null, since "
             "nothing is committed until F6.",
    )
    parser.add_argument(
        "--changed-files",
        help="NEWLINE-separated explicit paths (testing / precomputed sets); "
             "requires --diff-loc for an accurate plan-review decision.",
    )
    parser.add_argument("--diff-loc", type=int, default=0)
    parser.add_argument("--stage1-complexity", required=True)
    parser.add_argument(
        "--run-id",
        help="Clears a CI stop once this run has a recorded acknowledgement, so "
             "the operator's answer is not asked again on every re-run.",
    )
    parser.add_argument(
        "--stage1-flags",
        help="Step 2's message-derived flags (comma/newline separated), UNIONED "
             "with the diff-driven flags — never replaced.",
    )
    args = parser.parse_args()

    try:
        if args.changed_files is not None:
            files = [ln for ln in args.changed_files.splitlines() if ln.strip()]
            loc = args.diff_loc
        else:
            files, loc = collect_change_set(
                Path(args.project_root), args.base_ref or "HEAD"
            )
        acked = bool(
            args.run_id
            and ack_path(Path(args.project_root), args.run_id).is_file()
        )
        result = recheck(
            files, args.stage1_complexity, loc,
            _split_flags(args.stage1_flags), acked,
        )
    except (RuntimeError, ValueError, OSError) as exc:
        # Still valid JSON on stdout: the caller parses unconditionally.
        print(json.dumps({"error": str(exc), "escalate": {"required": False}}))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 3 if result["escalate"]["required"] else 0


if __name__ == "__main__":
    sys.exit(main())
