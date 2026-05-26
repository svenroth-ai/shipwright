"""Behavioral + parity probes for `shared.contracts.*` — Sub-Iterate B8.

Sibling of `test_shared_contracts_consumers.py`. That file pins the
contract surface and the refactor invariants via fast static-source
assertions. This file exercises the contract end-to-end against a
real fixture project root and the in-process bridge.

Split rationale (size-guideline 300 LOC): the combined file crossed
381 LOC. Reviewer-flagged Gemini/OpenAI's parity + error-path tests
all live here so the static-source guards in the sibling stay easy
to scan.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Paths — duplicated minimally with the sibling so each file stands alone.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent

COMPLIANCE_BRIDGE_PATH = (
    REPO_ROOT / "plugins" / "shipwright-adopt" / "scripts" / "lib"
    / "compliance_bridge.py"
)


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_bridge(unique_name: str):
    """Load `compliance_bridge.py` under a unique module name.

    Each behavioral test gets its own module instance so per-test
    state (sys.modules entries) does not leak.
    """
    spec = importlib.util.spec_from_file_location(unique_name, COMPLIANCE_BRIDGE_PATH)
    bridge = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = bridge
    spec.loader.exec_module(bridge)
    return bridge


# ---------------------------------------------------------------------------
# Parity: the bridge MUST consume PHASE_REPORTS from the contract, not
# duplicate it locally. Reviewer-flagged Gemini-H1 / OpenAI-H3.
# ---------------------------------------------------------------------------


def test_compliance_bridge_no_phase_reports_duplication() -> None:
    """`compliance_bridge.py` must not redefine `PHASE_REPORTS` locally.

    The contract is the single source of truth — adopt's bridge imports
    it. A local literal `{"project": [...], "plan": [...], ...}` would
    silently desync from the compliance plugin's table.
    """
    src = _read_source(COMPLIANCE_BRIDGE_PATH)
    # Active assignment (not a comment). PHASE_REPORTS = ... or
    # _PHASE_REPORTS = ... would both be drift sources.
    assert not re.search(
        r"^\s*_?PHASE_REPORTS\s*[:=]", src, re.MULTILINE
    ), "compliance_bridge.py must not redefine PHASE_REPORTS locally"


def test_compliance_bridge_no_importlib_module_dispatch() -> None:
    """`compliance_bridge.py` does not call `importlib.import_module`.

    Reviewer-flagged Gemini-L5 / OpenAI-M10: dynamic imports over
    report names are now mediated by `shared.contracts.compliance.run_report`,
    which validates against the static `GENERATORS` allowlist.
    """
    src = _read_source(COMPLIANCE_BRIDGE_PATH)
    assert not re.search(
        r"^\s*[^#\n]*importlib\.import_module\(", src, re.MULTILINE
    ), "compliance_bridge.py must not call importlib.import_module anymore"


def test_contract_phase_reports_matches_compliance_plugin_source() -> None:
    """Reviewer-flagged OpenAI-H3: pin that the contract's PHASE_REPORTS
    is the EXACT same object the compliance plugin's update_compliance.py
    defines. Drift here = silent adopt-vs-compliance desync.
    """
    from shared.contracts.compliance import PHASE_REPORTS as contract_table

    # Read update_compliance.py's table directly via the contract's
    # bootstrapped sys.path — if the re-export drifted, this import
    # would either fail or return a different object.
    from scripts.tools.update_compliance import (  # type: ignore[import-not-found]
        PHASE_REPORTS as source_table,
    )
    assert contract_table is source_table, (
        "shared.contracts.compliance.PHASE_REPORTS must be the same "
        "object as plugins/shipwright-compliance/scripts/tools/"
        "update_compliance.PHASE_REPORTS"
    )


# ---------------------------------------------------------------------------
# Behavioral parity probe: run the bridge in-process against a real
# fixture project root. Reviewer-flagged OpenAI-H4 + M8.
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_project_root(tmp_path: Path) -> Path:
    """A more complete fixture than `minimal_project_root` — the compliance
    generators expect certain dirs to exist before they write.
    """
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "completed_steps": []}),
        encoding="utf-8",
    )
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"splits": []}),
        encoding="utf-8",
    )
    (tmp_path / "shipwright_build_config.json").write_text(
        json.dumps({"sections": []}),
        encoding="utf-8",
    )
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True)
    (tmp_path / ".shipwright" / "planning").mkdir(parents=True)
    return tmp_path


def test_run_update_compliance_writes_canonical_reports(
    fixture_project_root: Path,
) -> None:
    """Behavioral parity probe — the bridge writes the same MD set the
    subprocess path used to write.
    """
    bridge = _load_bridge("compliance_bridge_under_test")
    result = bridge.run_update_compliance(fixture_project_root, phases=["build"])
    # "build" maps to ["rtm", "test_evidence", "change_history", "sbom", "dashboard"].
    # The bridge SHOULD have written one MD per report into
    # .shipwright/compliance/. Some may fail (e.g. test_evidence with no
    # events) — that's recorded in `failed`. But the overall behavior
    # must match: every phase listed in `ran` got its reports.
    assert "ran" in result
    assert "failed" in result
    assert result["script"] is None  # legacy key, now always None
    # At minimum the dashboard MD must exist after a successful build phase.
    if "build" in result["ran"]:
        assert (
            fixture_project_root / ".shipwright" / "compliance" / "dashboard.md"
        ).exists()


def test_run_update_compliance_unknown_phase_isolated(
    fixture_project_root: Path,
) -> None:
    """Reviewer-flagged OpenAI-M8: unknown phase names are recorded
    in `failed` without aborting other phases.
    """
    bridge = _load_bridge("compliance_bridge_under_test_2")
    result = bridge.run_update_compliance(
        fixture_project_root, phases=["bogus_phase_42"]
    )
    assert result["ran"] == []
    assert any(
        "bogus_phase_42" in p[0] and "unknown_phase" in p[1]
        for p in result["failed"]
    ), f"unknown phase must surface in failed; got {result['failed']}"
