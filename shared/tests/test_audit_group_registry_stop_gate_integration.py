"""INTEGRATION — the audit group registry, the detector's default set, and the
lifecycle-authority coverage contract must compose (iterate-2026-07-18-fr-
authoring-rules; re-scoped by iterate-2026-08-09-p2-59-branch-feedback-authority
when merge/release coverage moved from the Stop hook's own frozenset into
``lib.compliance_lifecycle``).

Three components each carry their own list of audit group letters:

  1. ``scripts/audit/_registry.register_all`` — what is actually registered
  2. ``audit_detector.run_all``'s default ``wanted`` set — what actually runs
  3. ``lib.compliance_lifecycle.ALL_GROUPS`` — what merge/release authority
     demands before coverage counts as complete and may converge the backlog

Each is unit-tested in isolation, and each was individually green while the three
disagreed. Adding Group I proved why that is not enough: the registry and the
detector were updated, the coverage set was not, and the result was a silent
false dismiss — coverage was reported complete over a set that no longer
contained every group that ran, so a failing Group I would have been mirrored away
rather than surfaced. That is the same defect class the F20 comment documents for
Group H, one letter later, and no unit test could see it because the bug lives in
the DISAGREEMENT between the three, not inside any one of them.

This proves they agree, on the real registry and the real detector — so the next
group added cannot repeat it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
_COMPLIANCE = _WORKTREE / "plugins" / "shipwright-compliance"

for _p in (str(_SHARED_SCRIPTS), str(_COMPLIANCE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The Stop hook is loaded by path (it is a script, not an importable package).
_HOOK_PATH = _SHARED_SCRIPTS / "hooks" / "audit_compliance_on_stop.py"
_spec = importlib.util.spec_from_file_location("audit_stop_hook_integration_uut", _HOOK_PATH)
assert _spec is not None and _spec.loader is not None
hook = importlib.util.module_from_spec(_spec)
sys.modules["audit_stop_hook_integration_uut"] = hook
_spec.loader.exec_module(hook)

from scripts.audit import _registry, audit_detector  # noqa: E402
from lib.compliance_lifecycle import ALL_GROUPS, coverage_for  # noqa: E402


def _register() -> set[str]:
    """Run the REAL registry and return the letters it registered."""
    _registry.register_all()
    return set(audit_detector._GROUPS)


def test_registry_and_lifecycle_contract_agree_on_the_group_set():
    """Release expects exactly what the registry makes runnable."""
    assert _register() == set(ALL_GROUPS)

def test_a_real_audit_run_satisfies_the_coverage_gate(tmp_path):
    """End-to-end: register → run the real audit → the gate accepts it.

    Uses the real ``run_all`` (not a fake report) so the detector's default
    ``wanted`` set is exercised too — the third list, and the one that decides
    what actually executes.
    """
    (tmp_path / "shipwright_run_config.json").write_text(
        '{"status": "in_progress"}\n', encoding="utf-8"
    )
    _register()

    report = audit_detector.run_all(tmp_path, run_gate=False)

    ran = set(report.groups_run)
    assert "I" in ran, f"Group I did not run — groups_run={sorted(ran)}"

    coverage = coverage_for(report, "release")
    assert coverage.complete, f"release coverage rejected a full real run: {coverage.to_dict()}"


def test_every_registered_group_actually_runs_by_default(tmp_path):
    """A group can be registered yet left out of the detector's default set.

    That combination reads as healthy from the registry's side while the group
    never executes — the failure mode the F20 comment records for Group H.
    """
    (tmp_path / "shipwright_run_config.json").write_text(
        '{"status": "in_progress"}\n', encoding="utf-8"
    )
    registered = _register()

    report = audit_detector.run_all(tmp_path, run_gate=False)

    never_ran = registered - set(report.groups_run)
    assert not never_ran, (
        f"registered but not in the default run set: {sorted(never_ran)}"
    )
