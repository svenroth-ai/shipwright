"""The dependency-order gate, as a phase-completion check.

`SKILL.md` Step 9 lists "Dependency Order" among its "verification gates (all
must pass)". It could not exist before: `SECTION_MANIFEST` was a flat list of
names, so dependencies were not expressible and nothing could establish that
the numbering was right. Declaring the dependency is what makes the promise
checkable — these pin that it is now checked, and that a plan which declares
nothing is not stranded by it.
"""

from pathlib import Path

from tools.verifiers.common import Severity
from tools.verifiers.plan_checks import run_plan_checks
from tools.verifiers.plan_gate_checks import (
    check_section_dependency_order,
    find_planning_split_dirs,
)

GATE = "section dependency order matches the numbering"


def seed(tmp_path: Path, manifest: str, sections: list[str], split: str = "01-auth") -> Path:
    split_dir = tmp_path / ".shipwright" / "planning" / split
    (split_dir / "sections").mkdir(parents=True, exist_ok=True)
    (split_dir / "spec.md").write_text(
        "# Spec\n\n| ID | Requirement | Priority |\n| FR-01.01 | thing | Must |\n",
        encoding="utf-8",
    )
    (split_dir / "plan.md").write_text(
        f"# Plan\n\n<!-- SECTION_MANIFEST\n{manifest}\nEND_MANIFEST -->\n", encoding="utf-8"
    )
    for name in sections:
        (split_dir / "sections" / f"{name}.md").write_text("# Section\n", encoding="utf-8")
    return tmp_path


def test_a_project_with_no_plan_is_vacuously_green(tmp_path):
    assert check_section_dependency_order(tmp_path).ok is True


def test_find_planning_split_dirs_skips_iterate_and_dotdirs(tmp_path):
    planning = tmp_path / ".shipwright" / "planning"
    for name in ("01-auth", "iterate", ".hidden", "02-api"):
        d = planning / name
        d.mkdir(parents=True)
        (d / "plan.md").write_text("x", encoding="utf-8")
    (planning / "03-nothing").mkdir()
    assert [d.name for d in find_planning_split_dirs(tmp_path)] == ["01-auth", "02-api"]


def test_consistent_order_passes(tmp_path):
    root = seed(tmp_path, "01-a\n02-b: 01-a", ["01-a", "02-b"])
    r = check_section_dependency_order(root)
    assert r.ok is True
    assert "1 declared dependenc" in r.detail


def test_prerequisite_after_its_user_fails(tmp_path):
    root = seed(tmp_path, "01-a: 02-b\n02-b", ["01-a", "02-b"])
    r = check_section_dependency_order(root)
    assert r.ok is False
    assert r.severity == Severity.ERROR.value
    assert "numbered after it" in r.detail


def test_a_manifest_declaring_nothing_has_nothing_to_contradict(tmp_path):
    """A plan written before dependencies were expressible promises nothing
    about order, so the rule is vacuously satisfied — no migration is owed."""
    root = seed(tmp_path, "03-c\n01-a\n02-b", ["01-a", "02-b", "03-c"])
    assert check_section_dependency_order(root).ok is True


def test_a_dependency_on_an_undeclared_section_fails(tmp_path):
    root = seed(tmp_path, "01-a\n02-b: 09-ghost", ["01-a", "02-b"])
    r = check_section_dependency_order(root)
    assert r.ok is False
    assert "09-ghost" in r.detail and "not declared" in r.detail


def test_the_gate_runs_at_phase_completion(tmp_path):
    """A gate nobody calls is the thing this change exists to stop."""
    assert GATE in {r.name for r in run_plan_checks(tmp_path, run_id="plan-x")}


def test_a_bad_order_blocks_phase_completion(tmp_path):
    root = seed(tmp_path, "01-a: 02-b\n02-b", ["01-a", "02-b"])
    red = [
        r for r in run_plan_checks(root, run_id="plan-x")
        if r.is_failure and r.severity == Severity.ERROR.value
    ]
    assert any(GATE in r.name for r in red)


def test_a_good_order_does_not_block_phase_completion(tmp_path):
    """The complement: without it, a gate failing unconditionally would still
    satisfy the test above."""
    root = seed(tmp_path, "01-a\n02-b: 01-a", ["01-a", "02-b"])
    red = [r for r in run_plan_checks(root, run_id="plan-x") if r.is_failure]
    assert not any(GATE in r.name for r in red)
