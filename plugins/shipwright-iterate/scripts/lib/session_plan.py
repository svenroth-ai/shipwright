#!/usr/bin/env python3
"""Persist the iterate *session plan* for the WebUI scoped Plan-Card (M-Pre-2).

`classify_complexity.py` prints its classification to stdout under a
byte-stable contract. This module additionally projects that classification
into a compact session plan — complexity, planned phases, skipped phases +
why, risk flags, run_id — and writes it next to the finalized
`.shipwright/agent_docs/iterates/<run_id>.json` as `<run_id>.plan.json`.

Boundary (touches_io_boundary):
    Producer:  classify_complexity.main() (opt-in — only when --run-id given).
    File:      <project_root>/.shipwright/agent_docs/iterates/<run_id>.plan.json
    Consumer:  shipwright-webui scoped Plan-Card (webui A15/A16), which reads
               the live working copy. The file is GITIGNORED transient
               run-scoped state (regenerated each classify, superseded by the
               durable <run_id>.json at finalize) — see .gitignore managed
               block. A run predating this simply has no plan file; the WebUI
               degrades gracefully.

Phase/skip gating mirrors the NORMATIVE SKILL.md §6 Phase Matrix (the labeled
SSoT for phase selection). It is a projection for display, not the authority —
§6 wins. The per-phase gates below cite the exact §6 row; the pinning tests in
tests/test_session_plan.py assert every cell against §6 so an unmirrored §6
edit fails a test (drift is detectable, not silent).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Complexity levels that fall below the medium+ review/interview thresholds.
_LOW = ("trivial", "small")

# Canonical run_id shape — SSoT: shared/scripts/lib/iterate_entry.py RUN_ID_STRICT.
# Copied local because the classify_complexity plugin-lib is standalone at runtime
# (deliberately never imports shared/); the pinning test keeps this in lock-step.
RUN_ID_STRICT = re.compile(r"^iterate-\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*$")


def _skip_interview(complexity: str, risk_flags: list[str]) -> str | None:
    # §6 Interview: skip | 1 confirmation Q | Q — skipped only at trivial.
    return "trivial complexity runs no interview" if complexity == "trivial" else None


def _skip_iterate_spec(complexity: str, risk_flags: list[str]) -> str | None:
    # §6 Iterate Spec: skip | skip | own file — skipped at trivial + small.
    return "iterate spec is medium+ only" if complexity in _LOW else None


def _skip_external_plan_review(complexity: str, risk_flags: list[str]) -> str | None:
    # §6 External LLM Review: skip | skip | auto — medium+ ONLY, NOT risk-gated.
    # (The risk-flag trigger belongs to Full Code Review, handled separately.)
    if complexity in _LOW:
        return "external review is medium+ only (§6 Phase Matrix)"
    return None


def _skip_code_review(complexity: str, risk_flags: list[str]) -> str | None:
    # §6 Full Code Review: "only if risk flags" | "only if risk flags" | always.
    if complexity in _LOW and not risk_flags:
        return "code review at trivial/small is risk-flag-gated (§6); no risk flag"
    return None


def _skip_confidence_calibration(complexity: str, risk_flags: list[str]) -> str | None:
    # §6 Confidence Calibration: skip | if touches_io_boundary | always | always.
    if complexity == "trivial":
        return "calibration is skipped at trivial (§6 Phase Matrix)"
    if complexity == "small" and "touches_io_boundary" not in risk_flags:
        return "calibration at small requires touches_io_boundary (§6 Phase Matrix)"
    return None


# Ordered iterate phase catalog. Each entry: (phase_id, group, skip_fn|None).
# `group` follows the narrator grouping (concept §5a): scope -> build -> review
# -> test -> finalize. skip_fn(complexity, risk_flags) -> reason | None; None
# means the phase always runs (§6 rows: Repo Scout / Build / Self-Review /
# Unit Test / Test Results JSON are unconditional). Deliberately small — only
# the phases whose presence a reader of the Plan-Card cares about.
_PHASE_CATALOG = [
    ("repo_scout", "scope", None),
    ("interview", "scope", _skip_interview),
    ("iterate_spec", "scope", _skip_iterate_spec),
    ("build", "build", None),
    ("external_plan_review", "review", _skip_external_plan_review),
    ("self_review", "review", None),
    ("code_review", "review", _skip_code_review),
    ("confidence_calibration", "review", _skip_confidence_calibration),
    ("test", "test", None),
    ("finalize", "finalize", None),
]


def build_session_plan(result: dict, run_id: str) -> dict:
    """Project a classify_complexity result into the WebUI session plan.

    Returns ``{run_id, complexity, risk_flags[], phases[], skips[]}``. Robust
    to a partial ``result`` (missing estimate -> "trivial", missing flags -> []).
    """
    complexity = result.get("estimate", "trivial")
    risk_flags = list(result.get("risk_flags", []))
    phases: list[dict] = []
    skips: list[dict] = []
    for phase_id, group, skip_fn in _PHASE_CATALOG:
        reason = skip_fn(complexity, risk_flags) if skip_fn else None
        if reason is None:
            phases.append({"id": phase_id, "group": group})
        else:
            skips.append({"id": phase_id, "group": group, "reason": reason})
    return {
        "run_id": run_id,
        "complexity": complexity,
        "risk_flags": risk_flags,
        "phases": phases,
        "skips": skips,
    }


def plan_path(project_root, run_id: str) -> Path:
    """On-disk location of the session plan for ``run_id``.

    ``Path(run_id).name`` strips any directory components so a crafted run_id
    (e.g. ``../../etc/x``) can never escape the iterates directory
    (defense-in-depth — real run_ids are RUN_ID_STRICT slugs, no separators).
    """
    safe = Path(str(run_id)).name
    return (
        Path(project_root) / ".shipwright" / "agent_docs" / "iterates"
        / f"{safe}.plan.json"
    )


def persist_session_plan(result: dict, run_id: str, project_root) -> Path:
    """Write the session plan next to ``<run_id>.json``. Returns the path.

    Validates ``run_id`` against RUN_ID_STRICT before writing (rejects path
    separators, ``..``, drive letters, NUL, etc.) — belt-and-suspenders with
    the ``Path(run_id).name`` containment in ``plan_path``. Raises ``ValueError``
    on a malformed run_id; ``persist_session_plan_safe`` swallows it.
    """
    if not isinstance(run_id, str) or not RUN_ID_STRICT.match(run_id):
        raise ValueError(f"run_id {run_id!r} is not a canonical iterate run_id")
    plan = build_session_plan(result, run_id)
    target = plan_path(project_root, run_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return target


def persist_session_plan_safe(result: dict, run_id: str, project_root) -> Path | None:
    """Fail-soft wrapper used by the classifier CLI.

    The plan is a best-effort WebUI convenience — a persist failure must NEVER
    abort the iterate session that invoked the classifier. Catches OSError
    (permission / disk full), ValueError (malformed run_id, NUL in path) and
    TypeError (None project_root); logs to stderr and returns None.
    """
    try:
        return persist_session_plan(result, run_id, project_root)
    except (OSError, ValueError, TypeError) as exc:  # defensive: never abort
        print(f"[classify_complexity] session-plan persist skipped: {exc}",
              file=sys.stderr)
        return None
