"""Canon verifier bridge for the phase validators (extracted from ``phase_validators``).

Import this only through ``phase_validators``: it puts ``shared/scripts`` on ``sys.path``,
without which the canon verifiers cannot be imported and the bridge reports a degraded
result (see ``DEGRADED_PREFIX``). To patch the bridge in a test, patch
``phase_validators_canon._run_canon_checks`` and the name re-bound in
``phase_validators`` / ``phase_validators_late`` / ``phase_validators_split``.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Optional

# Prefix on the inform-level note raised when the canon checks could not run in full.
DEGRADED_PREFIX = "[canon-degraded]"


def _degraded(phase: str, what: str) -> dict[str, str]:
    """One visible note standing in for canon checks that did not (fully) run.

    Inform, not ask: the phase's own checks still ran, and blocking every run whose
    environment lacks the verifiers would wedge it. ``kind`` lets a caller tell this
    note apart from a real finding without parsing the message.

    One caller reverses this on purpose: the v2 phase gate (``orchestrator_pkg.phase_gate.
    evaluate_gate``) promotes this note to ask, because a gate exists to fail closed. So
    once that gate is enforced, a missing verifiers package stops every driven apply —
    which is why A5 must prove ``shared/scripts/tools/verifiers`` ships in every
    plugin-cache layout before flipping it on.
    """
    return {
        "severity": "inform",
        "kind": "canon_degraded",
        "message": f"{DEGRADED_PREFIX} {phase}: {what}",
    }


def _verifiers_present() -> bool:
    """Whether the ``tools.verifiers`` package can be located at all."""
    try:
        return importlib.util.find_spec("tools.verifiers") is not None
    except (ImportError, ValueError):
        return False


def _import_failure(phase: str, exc: ImportError) -> dict[str, str]:
    """Tell an ABSENT canon package apart from a canon package that is present but broken.

    Absent (``tools.verifiers`` cannot be located, as in a stubbed or partial install) is
    the degraded inform note. Once the package is locatable, ANY import failure under it
    means the canon gate is broken, not missing — ask-level, so the phase stops rather
    than passing unchecked.
    """
    if not _verifiers_present():
        return _degraded(phase, f"canon verifiers are not importable ({exc}); no canon check ran")
    return {
        "severity": "ask",
        "kind": "canon_degraded",
        "message": (
            f"{DEGRADED_PREFIX} {phase}: a canon verifier failed to import "
            f"({type(exc).__name__}: {exc}), so the canon checks could not run. "
            "Fix the installation before completing this phase?"
        ),
    }


def _run_canon_checks(
    phase: str,
    project_root: Path,
    issues: list[dict[str, str]],
    *,
    run_id: Optional[str] = None,
) -> None:
    """Shared canon verifier bridge used by every phase validator.

    Dispatches to the matching ``tools.verifiers.<phase>_checks`` module lazily.
    Appends ask-level issues for every ERROR-severity result and inform-level issues
    for every WARNING. SKIPPED and green results are ignored.

    ``run_id`` is passed by the caller; only when it is None does the bridge fall back
    to ``SHIPWRIGHT_RUN_ID`` (legacy v1 / hook callers). Nothing is swallowed: absent
    verifiers or no run id at all are inform notes (``kind: canon_degraded``); broken
    verifiers or an explicitly empty run id are ask-level with the same ``kind``.
    """
    try:
        from tools.verifiers.common import Severity
        if phase == "project":
            from tools.verifiers.project_checks import run_project_checks as _run
        elif phase == "design":
            from tools.verifiers.design_checks import run_design_checks as _run
        elif phase == "plan":
            from tools.verifiers.plan_checks import run_plan_checks as _run
        elif phase == "build":
            from tools.verifiers.build_checks import run_build_checks as _run
        elif phase == "test":
            from tools.verifiers.test_checks import run_test_checks as _run
        elif phase == "changelog":
            from tools.verifiers.changelog_checks import run_changelog_checks as _run
        elif phase == "deploy":
            from tools.verifiers.deploy_checks import run_deploy_checks as _run
        else:
            return
    except ImportError as exc:
        issues.append(_import_failure(phase, exc))
        return

    if run_id is not None and not run_id.strip():
        # An explicit empty id is a caller bug (the v2 apply path passes config.runId),
        # not a legacy environment — refuse it instead of checking nothing.
        issues.append({
            "severity": "ask",
            "kind": "canon_degraded",
            "message": (
                f"{DEGRADED_PREFIX} {phase}: the caller passed an empty run id, so "
                f"phase_history[{phase}] cannot be checked. Pass the run's runId?"
            ),
        })
        return
    if run_id is None:
        run_id = os.environ.get("SHIPWRIGHT_RUN_ID", "")
    if not run_id:
        issues.append(_degraded(
            phase, f"no run id was supplied; phase_history[{phase}] was not checked",
        ))
    for r in _run(project_root, run_id=run_id):
        if r.is_skipped or r.ok:
            continue
        severity = "ask" if r.severity == Severity.ERROR.value else "inform"
        issues.append({
            "severity": severity,
            "message": f"[canon] {r.name}: {r.detail}",
        })
