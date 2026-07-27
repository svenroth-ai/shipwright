"""The four gates are actually wired into phase completion (AC10).

Split from ``test_verifiers_plan_gates.py``, which pins what each gate
decides. This file pins that ``run_plan_checks`` — and therefore
``_validate_plan``, which blocks ``update-step --step plan --status
complete`` — actually runs them. A gate nobody calls is the thing this
whole change exists to stop.
"""

import sys
from pathlib import Path

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


def test_a_bad_dependency_order_blocks_phase_completion(tmp_path):
    root = seed(
        tmp_path,
        manifest="01-a: 02-b\n02-b",
        sections={
            "01-a": WELL_FORMED.format(name="01-a", frs="FR-01.01"),
            "02-b": WELL_FORMED.format(name="02-b", frs="FR-01.01"),
        },
    )
    red = [
        r for r in run_plan_checks(root, run_id="plan-x")
        if r.is_failure and r.severity == Severity.ERROR.value
    ]
    assert any("dependency order" in r.name for r in red)
