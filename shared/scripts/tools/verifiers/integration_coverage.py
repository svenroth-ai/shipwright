"""``cross_component`` integration-coverage gate.

Extracted verbatim from ``iterate_checks.py``
(iterate-2026-06-13-risk-detector-extract) so that load-bearing verifier
stays under the bloat limit. Behaviour is unchanged — ``iterate_checks``
re-exports ``check_integration_coverage`` (used by ``run_all_checks``) plus
``_is_cross_component`` / ``_CROSS_COMPONENT_PATTERNS`` (pinned by the drift
test ``test_cross_component_patterns_sync``), so every existing import path
keeps resolving.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.iterate_entry import find_entry_by_run_id  # noqa: E402

from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import _commit_changed_paths, _run_git  # noqa: E402


# --- cross_component integration-coverage gate ------------------------------
# Self-contained copy of ``classify_complexity.CROSS_COMPONENT_FILE_PATTERNS`` so
# this load-bearing verifier (runs in every shared/tests + CI session) never
# cross-plugin-imports the iterate-plugin lib (ADR-044). The drift test
# ``test_cross_component_patterns_sync`` pins this == the SSoT, forward + reverse.
_CROSS_COMPONENT_PATTERNS = (
    r"(^|/)(integrate_main|ensure_current|resolve_churn_conflicts)\.py$",
    r"(^|/)(churn_merge|gitattributes_union|gitattributes_selfheal)\.py$",
    r"(^|/)(autonomous_loop|events_log)\.py$",
    r"(^|/)campaign_[^/]*\.py$",
    r"(^|/)campaign-mode\.md$",
    r"(^|/)hooks\.json$",
    r"(^|/)hooks/.+\.py$",  # any hook script under a hooks/ dir (incl. scripts/hooks/ + nested)
    r"(^|/)(verify_phase|get_phase_context)\.py$",
)


def _is_cross_component(changed_files: list[str] | None) -> bool:
    for path in changed_files or []:
        norm = path.replace("\\", "/")
        for pat in _CROSS_COMPONENT_PATTERNS:
            if re.search(pat, norm):
                return True
    return False


def _iterate_changed_paths(project_root: Path, commit: str) -> list[str] | None:
    """All paths the iterate branch changed vs its merge-base with the default
    branch — the robust full-branch view (NOT one commit), so the gate sees a
    cross-component edit even if it landed in an earlier commit than HEAD. Falls
    back to the single-commit paths when the merge-base can't be resolved."""
    if not commit:
        return None
    rc, ref, _ = _run_git(project_root, "rev-parse", "--abbrev-ref", "origin/HEAD")
    base_ref = ref.strip() if rc == 0 and ref.strip().startswith("origin/") else "origin/main"
    rc, mb, _ = _run_git(project_root, "merge-base", base_ref, commit)
    if rc == 0 and mb.strip():
        rc2, out, _ = _run_git(project_root, "diff", "--name-only", f"{mb.strip()}..{commit}")
        if rc2 == 0:
            return [ln.strip() for ln in out.splitlines() if ln.strip()]
    return _commit_changed_paths(project_root, commit)


def check_integration_coverage(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    """Non-dodgeable ``cross_component`` gate. A medium+ iterate that touches
    FRAMEWORK cross-component machinery (merge/churn resolver, Claude-Code hooks +
    hook fan-out, pipeline phase validators, campaign drain) MUST carry a behavior
    with ``category: "integration"`` in the Test Completeness Ledger — a
    real-scenario test proving the pieces compose. The empirical machinery is
    otherwise boundary-centric (``touches_io_boundary`` → round-trip) and
    app-surface-centric (F0.5), so it forces NOTHING for framework composition;
    this closes that hole (motivating class: the auto-merge churn cascade). The
    flag is RECOMPUTED from the diff (merge-base..HEAD), never an agent-reported
    value, so it cannot be dodged by omitting a self-report.
    """
    name = "integration coverage (cross-component)"
    entry = find_entry_by_run_id(project_root, run_id)
    complexity = str((entry or {}).get("complexity", "")).lower()
    if complexity not in ("medium", "large"):
        return CheckResult(name, True, f"skipped (complexity={complexity or 'unknown'})",
                           severity=Severity.SKIPPED.value)
    if not commit_hash:
        return CheckResult(name, True, "skipped (no --commit supplied)",
                           severity=Severity.SKIPPED.value)
    changed = _iterate_changed_paths(project_root, commit_hash)
    if changed is None:
        return CheckResult(name, True, "skipped (git unavailable / no diff)",
                           severity=Severity.SKIPPED.value)
    hit = [p for p in changed if _is_cross_component([p])]
    if not hit:
        return CheckResult(name, True, "no cross-component machinery touched")
    block: dict = {}
    results_path = project_root / "shipwright_test_results.json"
    if results_path.exists():
        try:
            il = json.loads(results_path.read_text(encoding="utf-8")).get("iterate_latest", {})
            block = il.get("test_completeness", {}) if isinstance(il, dict) else {}
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            # Surface corruption EXPLICITLY — never misreport an unreadable results
            # file as "missing integration coverage" (external-review fix).
            return CheckResult(
                name, False,
                f"cross-component change touched ({', '.join(hit[:3])}) but "
                f"shipwright_test_results.json is unreadable/corrupt ({exc}) — "
                "cannot verify integration coverage",
            )
    behaviors = block.get("behaviors", []) if isinstance(block, dict) else []
    has_integration = any(
        isinstance(b, dict) and str(b.get("category", "")).lower() == "integration"
        for b in behaviors
    )
    if has_integration:
        return CheckResult(name, True, f"cross-component change has integration coverage ({hit[0]})")
    return CheckResult(
        name, False,
        f"cross-component machinery touched ({', '.join(hit[:3])}) but NO Test "
        "Completeness behavior has category='integration' — add a real-scenario "
        "integration test proving the components compose (see "
        "shared/tests/test_parallel_merge_cascade_integration.py), mark it "
        "category:integration, or split the cross-component change out.",
    )
