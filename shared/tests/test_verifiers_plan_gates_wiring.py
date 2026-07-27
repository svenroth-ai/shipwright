"""The four gates are actually wired into phase completion (AC10).

Split from ``test_verifiers_plan_gates.py``, which pins what each gate
decides. This file pins that ``run_plan_checks`` — and therefore
``_validate_plan``, which blocks ``update-step --step plan --status
complete`` — actually runs them. A gate nobody calls is the thing this
whole change exists to stop.
"""

import sys
from pathlib import Path

import pytest

# APPEND, never insert(0): shared/tests/ contains its own `tools/`
# directory, which shadows shared/scripts/tools when it comes first.
sys.path.append(str(Path(__file__).resolve().parent))
from _plan_gate_fixtures import WELL_FORMED, seed

from tools.verifiers.common import Severity
from tools.verifiers.plan_checks import run_plan_checks


def test_run_plan_checks_includes_all_four_gates(tmp_path):
    names = {r.name for r in run_plan_checks(tmp_path, run_id="plan-x")}
    for expected in (
        "section dependency order matches the numbering",
        "every requirement lands in a section",
        "every section traces back to a requirement",
        "sections state purpose, steps and test strategy",
    ):
        assert expected in names


def _red_names(root) -> set[str]:
    return {
        r.name for r in run_plan_checks(root, run_id="plan-x")
        if r.is_failure and r.severity == Severity.ERROR.value
    }


# One seeded failure PER gate, each driven through the real run_plan_checks.
# Asserting only that the four names appear (above) would still pass if a
# registration invoked the wrong callback, or if three of the four silently
# returned green — which is precisely the class of defect this change exists to
# stop, so each gate has to be caught failing here.
PER_GATE = [
    (
        "dependency order",
        "01-a: 02-b\n02-b",
        {"01-a": WELL_FORMED.format(name="01-a", frs="FR-01.01"),
         "02-b": WELL_FORMED.format(name="02-b", frs="FR-01.01")},
        ("FR-01.01",),
    ),
    (
        "every requirement lands in a section",
        "01-a",
        {"01-a": WELL_FORMED.format(name="01-a", frs="FR-01.01")},
        ("FR-01.01", "FR-01.02"),          # FR-01.02 lands nowhere
    ),
    (
        "every section traces back to a requirement",
        "01-a\n02-b",
        {"01-a": WELL_FORMED.format(name="01-a", frs="FR-01.01"),
         "02-b": WELL_FORMED.format(name="02-b", frs="FR-09.99")},   # dead id
        ("FR-01.01",),
    ),
    (
        "sections state purpose, steps and test strategy",
        "01-a\n02-b",
        {"01-a": WELL_FORMED.format(name="01-a", frs="FR-01.01"),
         # adopts the heading format, then omits the test strategy
         "02-b": "# Section: 02-b\n\nRequirements: FR-01.01\n\n"
                 "## Overview\nx\n\n## Implementation Steps\n1. one\n2. two\n"},
        ("FR-01.01",),
    ),
]


@pytest.mark.parametrize(
    "gate,manifest,sections,frs", PER_GATE, ids=[p[0] for p in PER_GATE]
)
def test_each_gate_blocks_phase_completion_on_its_own(tmp_path, gate, manifest, sections, frs):
    root = seed(tmp_path, manifest=manifest, sections=sections, frs=frs)
    red = _red_names(root)
    assert any(gate in name for name in red), f"{gate} did not block; red={red}"


def test_a_clean_plan_trips_none_of_the_four(tmp_path):
    """The complement: without it, a gate that fails unconditionally would
    satisfy every test above."""
    root = seed(
        tmp_path,
        manifest="01-a\n02-b: 01-a",
        sections={
            "01-a": WELL_FORMED.format(name="01-a", frs="FR-01.01"),
            "02-b": WELL_FORMED.format(name="02-b", frs="FR-01.01"),
        },
    )
    red = _red_names(root)
    for gate, *_ in PER_GATE:
        assert not any(gate in name for name in red), f"{gate} false-blocked; red={red}"
