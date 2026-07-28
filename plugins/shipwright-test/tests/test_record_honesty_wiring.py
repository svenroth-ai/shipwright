"""The new checks are reachable the way the phase actually invokes them.

External plan review, finding R1 (both reviewers, HIGH): *"the modules could be
fully tested in isolation while no production test run emits journey results or
durable warning triage."* A module with a CLI that nothing calls is dead code
with a green suite.

Two things are pinned here:

1. **The CLIs run end-to-end** over a realistic project tree, as subprocesses,
   with the arguments the skill documents — not through an in-process import.
2. **The skill still names them.** If a future edit drops the invocation from
   the reference prose, the wiring is gone even though every unit test stays
   green. That is exactly how these layers ended up orphaned in the first place.

iterate-2026-07-27-test-phase-record-honesty, FR-01.06.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
LIB = PLUGIN_ROOT / "scripts" / "lib"
REFERENCES = PLUGIN_ROOT / "skills" / "test" / "references"

PLAN = """# E2E Test Plan

## User Flows

### Flow 1: Sign Up
- go to /signup

### Flow 2: Checkout
- pay
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    planning = tmp_path / ".shipwright" / "planning" / "01-core"
    planning.mkdir(parents=True)
    (planning / "claude-plan-e2e.md").write_text(PLAN, encoding="utf-8")

    flows = tmp_path / "e2e" / "flows"
    flows.mkdir(parents=True)
    (flows / "01-sign-up.spec.ts").write_text("test('signs up', () => {});", encoding="utf-8")

    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"adoption": {"adopted_at": "2026-01-01"}}), encoding="utf-8")
    (tmp_path / "shipwright_test_results.json").write_text(json.dumps({
        "unit": {"passed": 10, "total": 10},
        "e2e": {
            "passed": 1, "total": 2, "flaky": 1,
            "failures": [{"title": "pays", "file": "e2e/flows/02-checkout.spec.ts"}],
            "flaky_tests": [{"title": "signs up", "file": "e2e/flows/01-sign-up.spec.ts",
                             "retries": 1}],
        },
        "consistency": {"passed": 1, "total": 2,
                        "categories": {"spacing": {"status": "INCONSISTENT"}}},
        "design_fidelity": {"passed": 0, "total": 1,
                            "screens": [{"mockup": "home.html", "status": "needs_review"}]},
    }), encoding="utf-8")
    return tmp_path


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LIB / script), *args],
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )


def _triage(project: Path) -> list[dict]:
    path = project / ".shipwright" / "triage.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("event") == "append"
    ]


@pytest.mark.integration
@pytest.mark.covers("FR-01.06")
def test_the_journey_check_runs_as_the_skill_invokes_it(project: Path):
    proc = _run("journey_coverage.py", "--project-root", str(project), "--json")

    assert proc.returncode == 0, proc.stderr  # brownfield → does not block
    report = json.loads(proc.stdout)
    assert report["status"] == "gaps"
    assert [j["title"] for j in report["uncovered"]] == ["Checkout"]
    assert report["triage_appended"] == 1


@pytest.mark.integration
@pytest.mark.covers("FR-01.06")
def test_a_greenfield_journey_gap_makes_the_check_exit_non_zero(project: Path):
    (project / "shipwright_run_config.json").write_text(
        json.dumps({"scope": "full_app"}), encoding="utf-8")

    proc = _run("journey_coverage.py", "--project-root", str(project), "--json")

    assert proc.returncode == 1
    assert json.loads(proc.stdout)["blocking"] is True


@pytest.mark.integration
@pytest.mark.covers("FR-01.06")
def test_the_warning_emitter_runs_over_the_record_the_phase_writes(project: Path):
    proc = _run("warning_followups.py", "--project-root", str(project), "--json")

    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    # one failing spec + one flaky test + one category + one screen
    assert out["triage_appended"] == 4
    assert out["summary"]["e2e"]["flaky"] == 1


@pytest.mark.integration
@pytest.mark.covers("FR-01.06")
def test_both_checks_together_leave_one_coherent_backlog(project: Path):
    _run("journey_coverage.py", "--project-root", str(project))
    _run("warning_followups.py", "--project-root", str(project))

    sources = sorted(i["source"] for i in _triage(project))
    assert sources == [
        "journey-coverage", "test-warning", "test-warning", "test-warning",
        "test-warning",
    ]
    # Re-running the whole phase must not duplicate any of it.
    _run("journey_coverage.py", "--project-root", str(project))
    _run("warning_followups.py", "--project-root", str(project))
    assert len(_triage(project)) == 5


@pytest.mark.integration
@pytest.mark.covers("FR-01.06")
def test_the_summary_only_mode_reports_without_filing(project: Path):
    proc = _run("warning_followups.py", "--project-root", str(project),
                "--summary-only", "--json")

    assert json.loads(proc.stdout)["triage_appended"] == 0
    assert _triage(project) == []


# ---------------------------------------------------------------------------
# The prose still names them — drift protection for the wiring itself
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.06")
@pytest.mark.parametrize(("reference", "script"), [
    ("step-2.5-e2e-spec-generation.md", "journey_coverage.py"),
    ("step-5-report-results.md", "warning_followups.py"),
])
def test_the_step_that_owns_a_check_still_invokes_it(reference: str, script: str):
    text = (REFERENCES / reference).read_text(encoding="utf-8")
    assert script in text, (
        f"{reference} no longer invokes {script} — the check exists but nothing "
        f"in the phase runs it, which is the defect this iterate closed"
    )


@pytest.mark.covers("FR-01.06")
def test_every_script_the_prose_invokes_exists_on_disk():
    """The reverse direction: a documented invocation must resolve.

    Scoped to this plugin's OWN scripts (``{plugin_root}/scripts/lib/…``) —
    the prose also invokes other plugins' and the shared tree's scripts, which
    are not ours to resolve here.
    """
    own = "{plugin_root}/scripts/lib/"
    referenced = set()
    for reference in REFERENCES.glob("*.md"):
        for line in reference.read_text(encoding="utf-8").splitlines():
            if own not in line:
                continue
            for token in line.split():
                name = token.strip('`"\'(),\\')
                if own in name and name.endswith(".py"):
                    referenced.add(Path(name).name)

    assert referenced, "no plugin-owned script invocations found in the prose"
    missing = sorted(n for n in referenced if not (LIB / n).exists())
    assert missing == [], f"prose invokes scripts that do not exist: {missing}"
