"""The enforced phase gate accepts what the REAL phase skills' finalization blocks write.

A5 review (doubt, high): the gate's canon ``phase_history`` check matches one run id exactly,
and the phase skills mint their own ``SHIPWRIGHT_RUN_ID`` — the minimal-valid-project builder
alone could not show that, because it was the thing writing the entry. So here the builder
writes only each phase's own artifacts (``canon=False``) and the canon comes from the skill's
finalization block itself: extracted from the skill reference doc as written, its
placeholders filled, ``uv run`` swapped for this interpreter, the v1 ``update-step`` line
dropped (in a driven run the master applies the result), and run through ``bash`` in the
project directory. Then ``single-session-apply`` must pass, both when the skill mints its own
id and when the phase-runner exported the run's ``runId`` first. With that one id on every
entry, a second split (plan/02, build/02 via the build skill's own block) must still pass
only on the entry it recorded during its own task.

It also pins a production property of driven runs: the skill records ``phase_completed``
first, so the loop's own end event for the same ``(phase, splitId)`` in the same session is
deduped away (``record_event`` first-wins) — one tracked end per phase, the skill's.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ORCHESTRATOR = str(REPO / "plugins" / "shipwright-run" / "scripts" / "lib" / "orchestrator.py")
sys.path.insert(0, str(REPO / "shared" / "testkit"))
import minimal_valid_project as mvp  # noqa: E402

pytestmark = [pytest.mark.integration, pytest.mark.covers("FR-01.01/AC02")]

_SKILLS = {  # phase -> (plugin root, the reference doc holding its finalization block)
    "project": ("shipwright-project", "skills/project/references/step-8-completion.md"),
    "design": ("shipwright-design", "skills/design/references/step-9-finalization.md"),
    "plan": ("shipwright-plan", "skills/plan/references/step-9-completion.md"),
    "build": ("shipwright-build", "skills/build/references/section-state.md"),
}
_SESSION = "real-skill-canon-session"
_FILL = {"{N}": "1", "{M}": "0", "{tests_passed}": "1", "{tests_total}": "1","{scope}": "full_app", "{name}": "demo",
         "{profile}": "supabase-nextjs", "{SHIPWRIGHT_SESSION_ID}": "$SHIPWRIGHT_SESSION_ID"}
_BASH = shutil.which("bash")


def _env(run_id: str | None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if k not in ("AIKIDO_CLIENT_ID", "SHIPWRIGHT_RUN_ID")}
    env["SHIPWRIGHT_SESSION_ID"] = _SESSION
    if run_id:
        env["SHIPWRIGHT_RUN_ID"] = run_id
    return env


def _cli(project: Path, *args: str) -> tuple[int, dict]:
    proc = subprocess.run([sys.executable, ORCHESTRATOR, *args, "--project-root", str(project)],
                          capture_output=True, text=True, encoding="utf-8", timeout=90,
                          env=_env(None))
    assert proc.returncode in (0, 1, 2), proc.stderr
    return proc.returncode, json.loads(proc.stdout)


def _canon_block(phase: str, split: str | None, *, drop: str | None = None) -> str:
    plugin, doc = _SKILLS[phase]
    text = (REPO / "plugins" / plugin / doc).read_text(encoding="utf-8")
    block = next(b for b in re.findall(r"```bash\n(.*?)```", text, re.S)
                 if "append_phase_history.py" in b)
    lines = block.splitlines()
    cut = next((i for i, ln in enumerate(lines) if "orchestrator.py" in ln), None)
    if cut is not None:
        assert "update-step" in lines[cut + 1], lines[cut:cut + 2]   # the v1 completion call
        del lines[cut:cut + 2]
    if phase == "build":   # the fixture has no section commits to derive a category from
        lines = ["  commit_type=feat" if "git show" in ln else ln for ln in lines]
    if drop:   # remove one whole command (its lines up to the next blank line)
        start = next(i for i, ln in enumerate(lines) if drop in ln)
        end = next((i for i in range(start, len(lines)) if not lines[i].strip()), len(lines))
        del lines[start:end]
    script = "\n".join(lines)
    script = script.replace('uv run "', f'"{Path(sys.executable).as_posix()}" "')
    script = script.replace("{shared_root}", (REPO / "shared").as_posix())
    script = script.replace("{plugin_root}", (REPO / "plugins" / plugin).as_posix())
    for key, value in {**_FILL, "{split_name}": split or "", "{current_split}": split or "",
                       "{completed_sections_of_current_split}": mvp.SECTION,
                       "{section_name}": "$section"}.items():
        script = script.replace(key, value)
    left = re.findall(r"(?<!\$)\{[A-Za-z_]+\}", script)
    assert not left, f"unfilled placeholders in the {phase} block: {left}"
    return "set -e\n" + script


def _next(project: Path) -> dict:
    code, out = _cli(project, "single-session-next")
    assert code == 0 and out["action"] == "dispatch", out
    return out["dispatch"]


def _run_phase(project: Path, phase: str, *, runner_run_id: str | None,
               drop: str | None = None) -> tuple[dict, int, dict]:
    d = _next(project)
    assert d["phase"] == phase, d
    code, applied = _finish(project, d, runner_run_id=runner_run_id, drop=drop)
    return d, code, applied


def _finish(project: Path, d: dict, *, runner_run_id: str | None,
            drop: str | None = None) -> tuple[int, dict]:
    """Run dispatch ``d`` as the real skill would, then ``single-session-apply`` it."""
    phase = d["phase"]
    artifacts = mvp.write_phase(project, phase, d.get("splitId"), canon=False)
    proc = subprocess.run([_BASH, "-c", _canon_block(phase, d.get("splitId"), drop=drop)],
                          cwd=project, capture_output=True, text=True, encoding="utf-8",
                          timeout=180, env=_env(runner_run_id))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = {"ok": True, "phase": phase, "summary": "done", "artifacts": artifacts}
    if d.get("splitId"):
        payload["splitId"] = d["splitId"]
    result = project / f".result-{d['phaseTaskId']}.json"
    result.write_text(json.dumps(payload), encoding="utf-8")
    return _cli(project, "single-session-apply", "--phase-task-id", d["phaseTaskId"],
                "--session-uuid", d["sessionUuid"], "--version", str(d["version"]),
                "--result-json", str(result))


def _start(tmp_path: Path) -> tuple[Path, str]:
    project = tmp_path / "proj"
    project.mkdir()
    code, cfg = _cli(project, "write-config", "--scope", "full_app", "--profile",
                     "supabase-nextjs", "--autonomy", "guided", "--mode", "single_session")
    assert code == 0
    return project, cfg["runId"]


def _history(project: Path, phase: str) -> list[dict]:
    cfg = json.loads((project / "shipwright_run_config.json").read_text(encoding="utf-8"))
    return cfg["phase_history"][phase]


@pytest.mark.parametrize("runner_exports_run_id", [False, True],
                         ids=["skill-mints-its-own-id", "runner-exports-the-run-id"])
def test_real_skill_finalization_passes_the_enforced_gate(tmp_path, runner_exports_run_id):
    assert _BASH, "bash is required to run the skills' finalization blocks"
    project, run_id = _start(tmp_path)
    for phase in ("project", "design", "plan"):
        _d, code, applied = _run_phase(
            project, phase, runner_run_id=run_id if runner_exports_run_id else None)
        assert code == 0 and applied["gate"]["result"] == "pass", applied
        recorded = _history(project, phase)[-1]["run_id"]
        if runner_exports_run_id:
            assert recorded == run_id                       # the skill kept the run's id
        else:
            assert recorded.startswith(f"{phase}-") and recorded != run_id

    events = [json.loads(ln) for ln in
              (project / "shipwright_events.jsonl").read_text(encoding="utf-8").splitlines()
              if ln.strip()]
    ends = [e for e in events if e.get("type") == "phase_completed" and e.get("phase") == "design"]
    # Known event loss: the skill's end event wins the (phase, splitId) dedup, so the loop's
    # own (phaseTaskId-carrying) end event for the design phase is not recorded.
    assert len(ends) == 1 and "phaseTaskId" not in ends[0], ends


def test_a_phase_that_writes_no_audit_entry_is_still_rejected(tmp_path):
    """The resolution accepts the phase's own entry; with none, the check still bites."""
    assert _BASH, "bash is required to run the skills' finalization blocks"
    project, _run_id = _start(tmp_path)
    _d, code, applied = _run_phase(project, "project", runner_run_id=None)
    assert code == 0, applied
    _d, code, rejected = _run_phase(project, "design", runner_run_id=None,
                                    drop="append_phase_history.py")
    assert code == 1 and rejected["reason"] == "phase_gate_failed", rejected
    assert any("phase_history[design]" in i["message"] for i in rejected["issues"]), rejected


def _drive_until(project: Path, run_id: str, stop: tuple[str, str]) -> dict:
    """Pass every dispatch through its real skill until ``stop`` = (phase, split) is next."""
    for _ in range(12):
        d = _next(project)
        if (d["phase"], d.get("splitId")) == stop:
            return d
        code, applied = _finish(project, d, runner_run_id=run_id)
        assert code == 0 and applied["gate"]["result"] == "pass", json.dumps([d["phase"], applied])
    raise AssertionError(f"{stop} was never dispatched")


def test_a_second_split_needs_its_own_entry_under_the_runs_id(tmp_path):
    """With the run's id exported, plan/01's entry carries the id plan/02's would, and
    build/01's the id build/02's would: each split must still pass on its OWN entry."""
    assert _BASH, "bash is required to run the skills' finalization blocks"
    if not shutil.which("jq"):
        pytest.skip("the build skill's phase_history block needs jq")
    project, run_id = _start(tmp_path)
    plan_02 = _drive_until(project, run_id, ("plan", "02-ui"))
    code, rejected = _finish(project, plan_02, runner_run_id=run_id,
                             drop="append_phase_history.py")
    assert code == 1 and rejected["reason"] == "phase_gate_failed", rejected
    assert any("phase_history[plan]" in i["message"] for i in rejected["issues"]), rejected

    retry = _next(project)                                    # the counted retry, same task
    assert retry["phaseTaskId"] == plan_02["phaseTaskId"], retry
    code, applied = _finish(project, retry, runner_run_id=run_id)
    assert code == 0 and applied["gate"]["result"] == "pass", applied

    build_02 = _drive_until(project, run_id, ("build", "02-ui"))
    code, applied = _finish(project, build_02, runner_run_id=run_id)
    assert code == 0 and applied["gate"]["result"] == "pass", applied
    builds = [(e["run_id"], e.get("split")) for e in _history(project, "build")]
    assert builds == [(run_id, "01-core"), (run_id, "02-ui")], builds
