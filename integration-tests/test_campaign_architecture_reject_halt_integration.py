"""Integration coverage: an architecture-review `reject` inside a campaign unit.

The `category:"integration"` behavior the `cross_component` flag requires for the
campaign-mode.md change. Four pieces each pass their own unit tests; the defect
class this guards lives BETWEEN them — a runner result that is well-formed by
prose but rejected by the schema, or accepted by the schema but dropped by the
loop before the orchestrator can print it:

    real verdict parser (review_verdict.summarize_reviews)
      -> the runner's escalation result (campaign-step-3-5-plan-review.md shape)
      -> the runner contract schema
      -> the REAL `autonomous_loop.py record` subprocess, on the PRODUCTION shape:
         a `kind: "sub_iterate"` row that was claimed (carries an `attempt_id`)
      -> the campaign-end scan campaign-mode.md finalize step 5 describes

The production shape matters: for a claimed row `resolve_record_status` collapses
`escalated` to a row status of `failed`, so a step-5 that filtered on the ROW
would find nothing — only the persisted `result.json` keeps `reason_code`.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LOOP = REPO_ROOT / "shared" / "scripts" / "lib" / "autonomous_loop.py"
VERDICT_PARSER = REPO_ROOT / "shared" / "scripts" / "lib" / "review_verdict.py"
SCHEMA = (
    REPO_ROOT / "plugins" / "shipwright-iterate" / "agents"
    / "sub_iterate_runner_contract.schema.json"
)
CODE = "architecture_review_rejected"
ATTEMPT_ID = "att-0001"

#: Reviewer prose is untrusted model output. This proves the payload round-trips
#: through record and the persisted result.json unchanged; it does NOT exercise the
#: 3f shell quoting (argv is a list here, no shell parses it).
HOSTILE_ALTERNATIVE = "reuse the resolver's writer; don't add a second $(whoami) one"


def _summarize(reviews: dict) -> dict:
    # Loaded under a unique module name (ADR-044/045): a bare `sys.path` import of
    # a `lib`-sibling collides with whatever loaded first in the same process.
    spec = importlib.util.spec_from_file_location("_arch_reject_review_verdict", VERDICT_PARSER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.summarize_reviews(reviews)


def _runner_result(envelope: dict, halted_patch: str = "runs/loop-1/3.1/a0/halted.patch") -> dict:
    """A result shaped as the reference tells the runner to build it. The runner's
    own assembly is prose an LLM executes, so this test pins the parser -> schema
    -> record -> step-5 boundaries, NOT that a runner copies fields correctly."""
    return {
        "sub_iterate_id": "3.1", "status": "escalated",
        "reason": "architecture_review_rejected: choose the alternative, keep the plan, or rework",
        "reason_code": CODE,
        "detected_complexity": "medium",
        "architecture_review": {
            "verdicts": envelope["verdicts"],
            "recommended_alternative": HOSTILE_ALTERNATIVE,
            "findings": ["a second writer to the same file; it's redundant"],
        },
        "halted_patch": halted_patch,
    }


def _unit_row(unit_id: str, status: str) -> dict:
    return {"id": unit_id, "status": status, "attempt": 0, "attempt_id": ATTEMPT_ID,
            "started_at": None, "finished_at": None, "commit": None,
            "head_sha": None, "branch": None, "result_path": None,
            "handoff_path": None, "failure_reason": None}


@pytest.fixture
def loop_state(tmp_path: Path) -> Path:
    ship = tmp_path / ".shipwright"
    ship.mkdir()
    state = ship / "loop_state.json"
    state.write_text(json.dumps({
        "loop_id": "loop-1", "kind": "sub_iterate", "root_session_id": "",
        "branch_strategy": "serial",
        "units": [_unit_row("3.1", "running"), _unit_row("3.2", "running")],
    }), encoding="utf-8")
    return state


def _record(state: Path, cwd: Path, unit: str, result: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LOOP), "record", "--state", str(state), "--unit", unit,
         "--attempt-id", ATTEMPT_ID, "--result", json.dumps(result)],
        capture_output=True, encoding="utf-8", cwd=cwd,
    )


def _halted_units(state: Path) -> list[dict]:
    """Finalize step 5, as campaign-mode.md describes it: every NON-COMPLETE
    unit's persisted result, filtered on reason_code — never on the row status."""
    found = []
    for row in json.loads(state.read_text(encoding="utf-8"))["units"]:
        if row["status"] in ("built", "merged"):
            continue
        # 3f STRICT-STOPs on the first exit 3, so a later sibling may never be
        # recorded (no result_path): step 5 falls back to the runner's own file.
        path = row.get("result_path") or str(
            state.parent / "runs" / "loop-1" / row["id"] / f"a{row['attempt']}" / "result.json")
        if not Path(path).is_file():
            continue
        persisted = json.loads(Path(path).read_text(encoding="utf-8"))
        if persisted.get("reason_code") == CODE:
            found.append(persisted)
    return found


@pytest.mark.covers("FR-01.11")
def test_reject_halts_the_unit_and_step_5_can_still_find_it(loop_state: Path, tmp_path: Path):
    jsonschema = pytest.importorskip("jsonschema")
    envelope = _summarize({
        "glm": {"status": "success",
                "feedback": "Reuse the resolver.\nSHIPWRIGHT_VERDICT: reject"},
        "openai": {"status": "success",
                   "feedback": "Fine.\nSHIPWRIGHT_VERDICT: approve"},
    })
    assert envelope["verdicts"] == {"glm": "reject", "openai": "approve"}

    patch = str(loop_state.parent / "runs" / "loop-1" / "3.1" / "a0" / "halted.patch")
    result = _runner_result(envelope, patch)
    jsonschema.validate(result, json.loads(SCHEMA.read_text(encoding="utf-8")))

    proc = _record(loop_state, tmp_path, "3.1", result)
    assert proc.returncode == 3, f"escalation must STRICT-STOP the wave: {proc.stderr}"

    rows = {r["id"]: r for r in json.loads(loop_state.read_text(encoding="utf-8"))["units"]}
    # The production collapse: a claimed row records `failed`, NOT `escalated` …
    assert rows["3.1"]["status"] == "failed"
    assert rows["3.1"]["failure_reason"].startswith(CODE), "the board text says what happened"
    assert rows["3.2"]["status"] == "running", "a sibling is untouched by the halt"

    # … so step 5 must read the persisted result, which keeps the whole decision.
    halted = _halted_units(loop_state)
    assert len(halted) == 1
    review = halted[0]["architecture_review"]
    assert review["verdicts"]["glm"] == "reject"
    assert review["recommended_alternative"] == HOSTILE_ALTERNATIVE
    # the patch the runner saves sits inside the unit's runs dir, beside the
    # persisted result (the layout coupling the reference relies on)
    assert Path(halted[0]["halted_patch"]).is_relative_to(Path(rows["3.1"]["result_path"]).parent)


@pytest.mark.covers("FR-01.11")
def test_a_reject_in_a_later_sibling_is_found_even_though_the_wave_stopped_first(
    loop_state: Path, tmp_path: Path
):
    """3.1 fails first -> exit 3 -> 3.2's record never runs; its reject must still
    surface from the runner's own attempt-scoped result.json."""
    failed = subprocess.run(
        [sys.executable, str(LOOP), "record", "--state", str(loop_state), "--unit", "3.1",
         "--attempt-id", ATTEMPT_ID, "--result", json.dumps({"status": "failed", "error": "tests red"})],
        capture_output=True, encoding="utf-8", cwd=tmp_path)
    assert failed.returncode == 3
    runner_dir = loop_state.parent / "runs" / "loop-1" / "3.2" / "a0"
    runner_dir.mkdir(parents=True)
    result = _runner_result({"verdicts": {"glm": "reject", "openai": "reject"}})
    (runner_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")

    rows = {r["id"]: r for r in json.loads(loop_state.read_text(encoding="utf-8"))["units"]}
    assert rows["3.2"]["result_path"] is None
    halted = _halted_units(loop_state)
    assert len(halted) == 1, "only the never-recorded sibling carries the reject"
    assert halted[0]["architecture_review"]["verdicts"] == {"glm": "reject", "openai": "reject"}


@pytest.mark.covers("FR-01.11")
def test_a_stale_attempt_cannot_overwrite_the_halt(loop_state: Path, tmp_path: Path):
    """The fencing token still guards the record: a superseded attempt's halt is
    rejected (exit 5), not silently recorded over the current attempt."""
    result = _runner_result({"verdicts": {"glm": "reject", "openai": "approve"}})
    proc = subprocess.run(
        [sys.executable, str(LOOP), "record", "--state", str(loop_state), "--unit", "3.1",
         "--attempt-id", "att-STALE", "--result", json.dumps(result)],
        capture_output=True, encoding="utf-8", cwd=tmp_path,
    )
    assert proc.returncode == 5
    assert _halted_units(loop_state) == []


@pytest.mark.covers("FR-01.11")
def test_unavailable_or_unknown_leg_is_not_a_reject():
    """A degraded provider must not halt a unit: only a real `reject` does."""
    envelope = _summarize({
        "glm": {"status": "error", "feedback": ""},
        "openai": {"status": "success", "feedback": "no sentinel here"},
    })
    assert "reject" not in envelope["verdicts"].values()
