"""Integration test for `shared.contracts.*` — Sub-Iterate B8.

This test acts as the round-trip probe for the contract boundary
introduced by Campaign-B Sub-Iterate B8. It pins two invariants:

1.  **Producer → Contract → Consumer** for the compliance surface:
    `shipwright-compliance/scripts/lib/data_collector.collect_all`
    is re-exported by `shared.contracts.compliance.collect_all`, and
    `shipwright-adopt/scripts/lib/compliance_bridge.py` consumes the
    contract directly (no subprocess, no ancestor-path-walk).

2.  **Producer → Contract → Consumer** for the iterate surface:
    `shipwright-iterate/scripts/lib/classify_complexity.is_io_boundary_change`
    is re-exported by `shared.contracts.iterate.is_io_boundary_change`,
    and `shipwright-test/scripts/tools/boundary_coverage_report.py`
    consumes the contract directly (no `_ITERATE_LIB` path constant,
    no `sys.path.insert`).

Both checks are empirical — they import the contracts at module scope
and exercise them against fixture data. Static-source assertions guard
the refactor of the two consumer files so a future contributor cannot
silently re-introduce the subprocess / sys.path patterns.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Repo root resolution
# ---------------------------------------------------------------------------
# This test lives at `integration-tests/test_shared_contracts_consumers.py`.
# The repo root is its parent directory.
REPO_ROOT = Path(__file__).resolve().parent.parent

COMPLIANCE_BRIDGE_PATH = (
    REPO_ROOT / "plugins" / "shipwright-adopt" / "scripts" / "lib"
    / "compliance_bridge.py"
)
BOUNDARY_REPORT_PATH = (
    REPO_ROOT / "plugins" / "shipwright-test" / "scripts" / "tools"
    / "boundary_coverage_report.py"
)


# ---------------------------------------------------------------------------
# Contract imports — these MUST work at module scope (no path manipulation).
# ---------------------------------------------------------------------------


def test_compliance_contract_importable() -> None:
    """`shared.contracts.compliance` exports `collect_all` + `ComplianceData`."""
    from shared.contracts import compliance as contract

    assert callable(contract.collect_all)
    assert hasattr(contract, "ComplianceData")
    # WorkEvent + TestRunEvent are part of the stable surface — adopt's
    # bridge constructs ComplianceData and downstream generators read
    # these. Pin them so a future refactor of compliance/data_collector
    # cannot silently drop them from the contract.
    assert hasattr(contract, "WorkEvent")
    assert hasattr(contract, "TestRunEvent")
    # PHASE_REPORTS + run_report — added after reviewer-flagged
    # Gemini-H1 / OpenAI-H3 to make the contract the single source of
    # truth for the phase → reports table.
    assert isinstance(contract.PHASE_REPORTS, dict)
    assert callable(contract.run_report)
    assert "build" in contract.PHASE_REPORTS
    assert "dashboard" in contract.PHASE_REPORTS["build"]


def test_iterate_contract_importable() -> None:
    """`shared.contracts.iterate` exports `is_io_boundary_change`."""
    from shared.contracts import iterate as contract

    assert callable(contract.is_io_boundary_change)
    # Re-exported risk taxonomy + touches_build_files helper — these are
    # part of the iterate plugin's classifier surface that downstream
    # consumers (boundary_coverage_report, test plugin reviewers) may
    # rely on.
    assert hasattr(contract, "RISK_TAXONOMY")
    assert hasattr(contract, "touches_build_files")


def test_iterate_contract_idempotent_import() -> None:
    """Re-importing the contract does not accumulate paths on `sys.path`.

    Reviewer-flagged Gemini-H2 / OpenAI-L11: the contract mutates
    `sys.path` at module load. The guard `if path not in sys.path` makes
    it idempotent; this test pins that property by counting iterate-lib
    occurrences before and after a `importlib.reload`.
    """
    import importlib
    import sys

    from shared.contracts import iterate as contract

    repo_root = REPO_ROOT
    iterate_lib_path = str(
        (repo_root / "plugins" / "shipwright-iterate" / "scripts" / "lib").resolve()
    )
    occurrences_before = sys.path.count(iterate_lib_path)
    importlib.reload(contract)
    occurrences_after = sys.path.count(iterate_lib_path)
    assert occurrences_before == occurrences_after, (
        f"Reloading shared.contracts.iterate ratcheted sys.path: "
        f"{occurrences_before} -> {occurrences_after} entries for "
        f"{iterate_lib_path}"
    )


def test_top_level_shared_contracts_init_reexports() -> None:
    """`from shared.contracts import compliance, iterate` works."""
    from shared.contracts import compliance, iterate  # noqa: F401

    # Sanity-check both modules are real modules with __name__.
    assert compliance.__name__.endswith("compliance")
    assert iterate.__name__.endswith("iterate")


# ---------------------------------------------------------------------------
# End-to-end: compliance contract against a real fixture.
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_project_root(tmp_path: Path) -> Path:
    """Minimal layout the compliance collector tolerates without crashing."""
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete"}),
        encoding="utf-8",
    )
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)
    (tmp_path / ".shipwright" / "planning").mkdir(parents=True)
    return tmp_path


def test_compliance_contract_end_to_end(minimal_project_root: Path) -> None:
    """`collect_all` returns a `ComplianceData` instance with stable fields.

    Producer surface — what compliance currently emits.
    """
    from shared.contracts import compliance as contract

    data = contract.collect_all(minimal_project_root)

    assert isinstance(data, contract.ComplianceData)
    # Fields the adopt-bridge and downstream generators consume.
    assert hasattr(data, "project_root")
    assert hasattr(data, "work_events")
    assert hasattr(data, "test_runs")
    assert hasattr(data, "configs")
    assert hasattr(data, "timestamp")
    # Lists default to empty (not None) — generators expect iterables.
    assert isinstance(data.work_events, list)
    assert isinstance(data.test_runs, list)


# ---------------------------------------------------------------------------
# End-to-end: iterate contract — IO-boundary detection.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("changed_files", "expected"),
    [
        ([".env"], True),
        ([".env.local"], True),
        ([".env.production.local"], True),
        (["plugins/shipwright-build/hooks/hooks.json"], True),
        (["shipwright_iterate_config.json"], True),
        ([".shipwright/loop_state.json"], True),
        # Negative cases — these MUST NOT flip the gate.
        (["plugins/shipwright-build/skills/build/SKILL.md"], False),
        (["docs/guide.md"], False),
        ([], False),
        (None, False),
    ],
)
def test_iterate_contract_is_io_boundary_change(
    changed_files: list[str] | None, expected: bool
) -> None:
    """Round-trip the producer's classifier through the contract."""
    from shared.contracts import iterate as contract

    assert contract.is_io_boundary_change(changed_files) is expected


# ---------------------------------------------------------------------------
# Refactor invariants — the consumer files MUST NOT re-introduce the
# subprocess/path-walk patterns the contract was introduced to eliminate.
# ---------------------------------------------------------------------------


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_compliance_bridge_uses_contract() -> None:
    """`compliance_bridge.py` imports from `shared.contracts.compliance`."""
    src = _read_source(COMPLIANCE_BRIDGE_PATH)
    # The contract import is the only sanctioned path now.
    assert "from shared.contracts" in src or "shared.contracts.compliance" in src, (
        "compliance_bridge.py must import the compliance contract directly"
    )


def test_compliance_bridge_no_subprocess_for_compliance() -> None:
    """`compliance_bridge.py` no longer spawns `update_compliance.py`.

    Allow `subprocess` references in comments/docstrings (historical
    rationale), but disallow active `subprocess.run` / `subprocess.Popen`
    statements in module code.
    """
    src = _read_source(COMPLIANCE_BRIDGE_PATH)
    # No live subprocess invocation.
    assert not re.search(r"^\s*[^#\n]*subprocess\.run\(", src, re.MULTILINE), (
        "compliance_bridge.py must not call subprocess.run anymore"
    )
    assert not re.search(r"^\s*[^#\n]*subprocess\.Popen\(", src, re.MULTILINE), (
        "compliance_bridge.py must not call subprocess.Popen anymore"
    )


def test_compliance_bridge_no_ancestor_walk() -> None:
    """`compliance_bridge.py` no longer walks parent dirs to locate the plugin."""
    src = _read_source(COMPLIANCE_BRIDGE_PATH)
    # The original ancestor-walk pattern was `for ancestor in [here, *here.parents]`.
    assert "*here.parents" not in src, (
        "compliance_bridge.py must not walk ancestors anymore"
    )
    # No live `sys.path.insert` either — the contract handles imports.
    assert not re.search(r"^\s*[^#\n]*sys\.path\.insert\(", src, re.MULTILINE), (
        "compliance_bridge.py must not manipulate sys.path anymore"
    )


def test_boundary_coverage_uses_contract() -> None:
    """`boundary_coverage_report.py` imports from `shared.contracts.iterate`."""
    src = _read_source(BOUNDARY_REPORT_PATH)
    assert "from shared.contracts" in src or "shared.contracts.iterate" in src, (
        "boundary_coverage_report.py must import the iterate contract directly"
    )


def test_boundary_coverage_no_iterate_lib_path() -> None:
    """`boundary_coverage_report.py` no longer has the `_ITERATE_LIB` constant."""
    src = _read_source(BOUNDARY_REPORT_PATH)
    assert "_ITERATE_LIB" not in src, (
        "boundary_coverage_report.py must not reference _ITERATE_LIB anymore"
    )


def test_boundary_coverage_no_sys_path_insert() -> None:
    """`boundary_coverage_report.py` no longer does `sys.path.insert(...)`."""
    src = _read_source(BOUNDARY_REPORT_PATH)
    assert not re.search(r"^\s*[^#\n]*sys\.path\.insert\(", src, re.MULTILINE), (
        "boundary_coverage_report.py must not manipulate sys.path anymore"
    )


# Parity, end-to-end, and error-path tests for the same contract live in
# `test_shared_contracts_consumers_behavior.py` (split per the 300-LOC
# guideline). The two files are paired; do not delete one without the other.
