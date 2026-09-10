"""AC-K12 — shape test for P3.6's one `ci.yml` edit.

Parses the REAL, checked-in `.github/workflows/ci.yml` (never a synthetic
fixture), per this repo's "anchor on structure, then mutate and watch it fail"
convention (`.shipwright/agent_docs/conventions.md`). Mirrors
`test_ci_yml_provenance_step_shape.py`, which does the same for P3.4c's steps.

The keystone gate is the campaign's north star, and every one of its properties
lives in YAML that nothing else asserts on: a rename, a `continue-on-error`, a
reorder before the regeneration step, or a widened trigger each turn the gate
into theatre without failing a single Python test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

KEYSTONE_STEP_NAME = "Keystone AC gate (gate)"
DRIFT_STEP_NAME = "Check traceability manifest against a fresh regeneration"


def _steps() -> list[dict]:
    data = yaml.safe_load(_CI_YML.read_text(encoding="utf-8"))
    return data["jobs"]["python-checks"]["steps"]


def _index_of(name: str) -> int:
    for i, step in enumerate(_steps()):
        if step.get("name") == name:
            return i
    raise AssertionError(f"no step named {name!r} in ci.yml python-checks job")


def _keystone() -> dict:
    return _steps()[_index_of(KEYSTONE_STEP_NAME)]


def test_the_step_exists_and_runs_the_real_gate_script():
    body = _keystone()["run"]
    assert "shared/scripts/tools/check_keystone_ac_gate.py" in body
    assert (_REPO_ROOT / "shared" / "scripts" / "tools"
            / "check_keystone_ac_gate.py").is_file()


def test_the_step_name_ends_in_gate_so_the_ci_gate_guard_enrols_it():
    """`check_ci_gate_coverage.GATE_NAME_KEYWORDS` contains "(gate)". Enrolment
    is what makes a future `continue-on-error` on this step fail the CI-gate
    guard instead of silently disarming the campaign's keystone."""
    assert KEYSTONE_STEP_NAME.endswith("(gate)")


def test_the_step_has_no_continue_on_error():
    assert "continue-on-error" not in _keystone()


def test_the_step_runs_on_pull_request_only():
    """The keystone gate is a MERGE condition: a push run has no PR to block and
    no base branch to diff against."""
    assert _keystone()["if"] == "github.event_name == 'pull_request'"


def test_the_step_and_the_regeneration_step_share_one_job():
    """External plan review (glm, low; openai, medium) — the design rests on
    "same run, same JUnit, regeneration two steps earlier **in the same job**",
    but ordering alone does not say that.

    If `ci.yml` ever splits manifest regeneration into its own job — a plausible
    refactor — the keystone step would read the *committed* manifest again,
    exactly the hand-edit Probe A proves is currently inert, and an
    ordering-only assertion would stay green through it. Asserted by naming the
    job for both, so a move fails here with the job name in the message.
    """
    data = yaml.safe_load(_CI_YML.read_text(encoding="utf-8"))
    owners = {
        job_id: {s.get("name") for s in job.get("steps") or []}
        for job_id, job in data["jobs"].items()
    }
    hosting = {j for j, names in owners.items() if KEYSTONE_STEP_NAME in names}
    regenerating = {j for j, names in owners.items() if DRIFT_STEP_NAME in names}
    assert hosting == regenerating == {"python-checks"}, (
        f"keystone step in {hosting}, regeneration step in {regenerating} — they must "
        "share one job, or the gate reads a committed manifest instead of a regenerated one"
    )


def test_no_merge_group_trigger_exists_without_revisiting_the_event_filter():
    """External plan review (openai, medium) — a tripwire, not a claim.

    The step's `if:` accepts `pull_request` only. If a merge queue is ever
    enabled, `merge_group` runs become a merge path this gate does not see, and
    the filter has to be widened deliberately (with the right base/head refs)
    rather than discovered later. This repo has no merge queue today
    (deferred); this test is what makes enabling one a conscious edit here.
    """
    data = yaml.safe_load(_CI_YML.read_text(encoding="utf-8"))
    # PyYAML parses a bare `on:` key as the boolean True.
    triggers = data.get("on") or data.get(True) or {}
    assert "merge_group" not in triggers, (
        "ci.yml now triggers on merge_group — widen the Keystone AC gate's `if:` to cover it "
        "(and check the base/head refs a merge_group event provides), or state why not."
    )


def test_the_step_comes_after_the_manifest_regeneration_step():
    """The one genuinely load-bearing ordering constraint. The drift step
    regenerates `.shipwright/compliance/test-traceability.json` IN PLACE from
    this run's real JUnit before comparing, so the committed file's own
    execution claims are already overwritten by the time this gate reads them.
    Running first would grade the PR against self-reported bytes.
    """
    assert _index_of(KEYSTONE_STEP_NAME) > _index_of(DRIFT_STEP_NAME)


def test_the_step_takes_no_conditional_dependency_on_another_step():
    """The negative half of §5.7. No reviewer asked for this — found during
    build: the first version asserted `"Diff coverage" not in` the step's own
    body, which is trivially true of any step that does not mention it, and
    would have passed a `hashFiles('coverage.xml')` condition worded differently.

    The real constraint: the keystone step's execution must not be predicated on
    anything OTHER than the event. `Diff coverage (gate)` is itself conditional
    on `hashFiles('coverage.xml')`, so hanging the gate off it would pin a hard
    precondition on a soft dependency — remove diff coverage later and the
    keystone gate silently stops running while every other assertion stays green.
    So: no `needs:`, and no artifact/step reference in the `if`.
    """
    step = _keystone()
    assert "needs" not in step
    condition = str(step.get("if", ""))
    for token in ("hashFiles", "coverage.xml", "steps.", "needs."):
        assert token not in condition, (
            f"the keystone step's `if:` references {token!r} — its execution must depend on the "
            "EVENT alone, never on another step's outcome or artifact"
        )


def test_the_step_passes_github_sha_as_the_head_and_resolves_the_base_itself():
    """`--base-sha` must NOT appear: CI has to let `_merge_base` resolve the base
    through its own candidate chain (`origin/HEAD` → `@{u}` → `origin/main` →
    `origin/master` → local). A pinned base in YAML is how a repo whose default
    branch is not `main` gets a false verdict."""
    body = _keystone()["run"]
    assert '--head-sha "${{ github.sha }}"' in body
    assert "--base-sha" not in body


def test_the_regeneration_step_overwrites_the_very_file_the_gate_reads():
    """External code review (openai, medium) — the assumption under Probe A.

    Probe A shows a hand-edited COMMITTED manifest cannot flip the verdict, but it
    demonstrates that by writing the regenerated bytes itself; it would stay green
    if `ci_manifest_drift_check` stopped regenerating **in place**. The real
    invariant is a two-way one, and it is an inversion away from silently failing:
    the COMMITTED bytes go to a scratch path, and `generate_file` writes the
    tracked path — swap those and the keystone gate reads self-reported claims
    again with every assertion in this file still passing.

    Asserted structurally (path identity + the regen script's argument), because
    the alternative — driving the real regeneration with controlled JUnit input —
    needs a `uv run --project plugins/shipwright-compliance` subprocess and a
    populated `.ci-junit/` tree. That fuller integration probe is deferred with a
    card; this pins the specific bypass the finding names.
    """
    sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts" / "tools"))
    import ci_manifest_drift_check as drift
    from verifiers import _keystone_ac_digest as kd

    assert drift.TRACKED_MANIFEST_REL.as_posix() == kd.MANIFEST_RELPATH, (
        "the drift step regenerates a different file than the keystone gate reads"
    )
    # `generate_file(project_root)` -- the project root, so it lands on the TRACKED
    # path. A scratch argument here would mean the committed bytes survive on disk.
    assert "generate_file(project_root)" in drift._REGEN_SCRIPT
    assert "scratch" not in drift._REGEN_SCRIPT
    # ...and the committed bytes are the ones diverted to scratch.
    source = (_REPO_ROOT / "shared" / "scripts" / "tools"
              / "ci_manifest_drift_check.py").read_text(encoding="utf-8")
    assert "def capture_committed_manifest(project_root: Path, scratch_path: Path)" in source


def test_the_gate_is_not_registered_as_a_separate_required_check():
    """It lives inside the existing `python-checks` job, which is already a
    Required Check — branch protection is untouched by this iterate."""
    data = yaml.safe_load(_CI_YML.read_text(encoding="utf-8"))
    jobs = set(data["jobs"])
    assert "keystone" not in " ".join(jobs).lower()
