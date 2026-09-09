"""Shape test for the two `ci.yml` edits P3.4c
(iterate-2026-09-08-ci-provenance-attestation) made to the "python-checks"
job: the drift-check step's captured exit-code output, and the new
provenance-confirmation step gated on it.

Parses the REAL, checked-in `.github/workflows/ci.yml` (not a synthetic
fixture) — a mutation to any of the pinned literals below must fail this
test, per this repo's own "anchor on structure, then mutate and watch it
fail" convention (`.shipwright/agent_docs/conventions.md`, 2026-07-31
iterate/test learning).
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import ci_provenance  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _load_steps() -> list[dict]:
    data = yaml.safe_load(_CI_YML.read_text(encoding="utf-8"))
    job = data["jobs"]["python-checks"]
    return job["steps"]


def _find(steps: list[dict], name: str) -> dict:
    for step in steps:
        if step.get("name") == name:
            return step
    raise AssertionError(f"no step named {name!r} in ci.yml python-checks job")


def test_drift_check_step_emits_code_output_before_any_exit():
    steps = _load_steps()
    drift_step = _find(steps, "Check traceability manifest against a fresh regeneration")
    assert drift_step.get("id") == "manifest_drift"
    body = drift_step["run"]
    output_line_pos = body.find('echo "code=$code" >> "$GITHUB_OUTPUT"')
    assert output_line_pos != -1, "missing the GITHUB_OUTPUT line"
    # The output line must precede every `exit "$code"` branch, so the output
    # is written on every exit path (External Review finding).
    search_from = 0
    while True:
        exit_pos = body.find('exit "$code"', search_from)
        if exit_pos == -1:
            break
        assert output_line_pos < exit_pos, "GITHUB_OUTPUT line must precede exit \"$code\""
        search_from = exit_pos + 1


def test_provenance_step_name_matches_the_python_constant():
    steps = _load_steps()
    # Fails loudly (KeyError via _find) if the YAML step was renamed without
    # updating ci_provenance.PROVENANCE_STEP_NAME, or vice versa.
    step = _find(steps, ci_provenance.PROVENANCE_STEP_NAME)
    assert step["if"] == "steps.manifest_drift.outputs.code == '0'"


def test_provenance_step_has_no_fallible_logic():
    steps = _load_steps()
    step = _find(steps, ci_provenance.PROVENANCE_STEP_NAME)
    # No continue-on-error needed and none present: a bare echo cannot fail.
    assert "continue-on-error" not in step
    # Exact match, not startswith — External Review (openai): `echo ...;
    # false` or any appended fallible command would pass a startswith check
    # while making the step's own conclusion no longer infallible.
    assert step["run"].strip() == 'echo "manifest verified clean at ${{ github.sha }}"'


def test_drift_check_set_plus_e_precedes_the_capture_and_output_line():
    """External code review (glm): the `$GITHUB_OUTPUT` capture is only
    reachable because the script disables `set -e` first — a future edit
    that removes `set +e` (or reorders it after `code=$?`) would make the
    script die on a nonzero exit before either line runs, silently starving
    `outputs.code` and making the provenance step always `skipped` for a
    drift-found commit, while the two existing assertions above would stay
    green. Pin the full ordering, not just the output-line-before-exit part.
    """
    steps = _load_steps()
    body = _find(steps, "Check traceability manifest against a fresh regeneration")["run"]
    set_plus_e_pos = body.find("set +e")
    code_capture_pos = body.find("code=$?")
    output_line_pos = body.find('echo "code=$code" >> "$GITHUB_OUTPUT"')
    assert set_plus_e_pos != -1, "missing 'set +e' guard"
    assert set_plus_e_pos < code_capture_pos < output_line_pos, (
        "'set +e' must precede 'code=$?' must precede the $GITHUB_OUTPUT echo"
    )


def test_drift_check_exit_code_contract_unchanged():
    """AC5 — the existing 0/1/2 branching survives byte-for-byte except for
    the one added output line."""
    steps = _load_steps()
    body = _find(steps, "Check traceability manifest against a fresh regeneration")["run"]
    assert 'code=$?' in body
    assert 'if [ "$code" -eq 1 ]; then' in body
    assert '::warning::' in body
    assert 'elif [ "$code" -ne 0 ]; then' in body
    assert 'exit "$code"' in body
