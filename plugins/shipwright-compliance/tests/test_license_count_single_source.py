"""R3 (intent-pyramid): the dashboard and the SBOM report ONE unresolved-license count.

Bug: the dashboard said "0 unresolved / 16 licenses" while sbom.md said "8
dependency(ies) could not be resolved" -- the dashboard counted only the
literal ``unknown`` strings and missed ``NOT_INSTALLED`` (``not-installed``).
The SBOM render helpers are the one source; the dashboard reads them.
"""

from __future__ import annotations

import re

import pytest
from pathlib import Path

from scripts.lib._control_block import build_grade_inputs
from scripts.lib.collectors import NOT_INSTALLED, UNKNOWN_LICENSE
from scripts.lib.data_collector import ComplianceData, DependencyInfo
from scripts.lib.sbom_generator import generate
from scripts.lib.sbom_render import unresolved_count


def _dep(name: str, lic: str) -> DependencyInfo:
    return DependencyInfo(name=name, version="1.0", license=lic, dep_type="runtime")


def _data() -> ComplianceData:
    d = ComplianceData(project_root=Path("."))
    d.dependencies = (
        [_dep(f"ok{i}", "MIT") for i in range(8)]
        + [_dep(f"ghost{i}", NOT_INSTALLED) for i in range(5)]
        + [_dep(f"nolic{i}", UNKNOWN_LICENSE) for i in range(3)]
    )
    d.timestamp = "2026-11-28T00:00:00Z"
    return d


@pytest.mark.covers("FR-01.10/AC01")
def test_dashboard_and_sbom_agree_on_unresolved_count():
    data = _data()
    inputs = build_grade_inputs(data)
    assert inputs.deps_unknown_license == 8
    assert inputs.deps_total == 16
    sbom = generate(data)
    not_resolved = int(re.search(r"\*\*(\d+) dependency\(ies\) could not be resolved", sbom).group(1))
    declare_none = int(re.search(r"\*\*(\d+) dependency\(ies\) declare no license", sbom).group(1))
    assert not_resolved + declare_none == inputs.deps_unknown_license
    assert f"| Licenses resolved | {16 - inputs.deps_unknown_license} / 16 |" in sbom


@pytest.mark.covers("FR-01.10/AC01")
def test_unresolved_count_is_the_sbom_definition():
    assert unresolved_count(_data().dependencies) == 8
    assert unresolved_count([]) == 0
