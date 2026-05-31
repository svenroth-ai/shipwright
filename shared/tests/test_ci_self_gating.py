"""Regression guard: the repo's OWN integration-tests CI step must gate.

`.github/workflows/ci.yml`'s "Run integration tests" step previously ended
in ``|| true``, swallowing the suite's non-zero exit so a red integration
run still left CI green — a dormant-CI-era leftover (commit ``4107a6b``)
that the public-launch hardening pass (``d85210f``) missed. Removed in
iterate-2026-05-31-ci-gate-f821. Without this test, re-adding ``|| true``
(or ``continue-on-error: true``) to that step would silently un-gate the
layer again, and nobody would notice until a real regression shipped to
main.

Why the structural check is sufficient (empirically verified). Removing
``|| true`` gates on GitHub Actions' default Linux shell
(``bash --noprofile --norc -eo pipefail {0}`` — ``-e`` already active). A
4-case shell replication confirmed the semantics:

    NEW  fail(pytest exit 1)            -> exit 1   (GATES)
    NEW  pass(pytest exit 0)            -> exit 0   (green suite still passes)
    NEW  no-tests-collected(exit 5)     -> exit 5   (also gates — edge)
    OLD  fail + '|| true' (control)     -> exit 0   (swallow was REAL)

So the behavior is fully determined by the absence of the swallow on this
step; this test pins exactly that structural invariant (and stays
host-agnostic — no bash dependency on the test runner).

Scope: ONLY the integration-tests execution step. The lint step's own
``|| true`` + ``continue-on-error`` is a separate, intentionally-tolerated
item and is explicitly NOT covered here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")  # PyYAML — root + adopt + compliance deps

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _integration_step() -> dict:
    """Return the single CI step that executes ``pytest integration-tests``.

    Matched by command (not step name) so a rename can't silently drop the
    guard; a count != 1 fails loudly rather than skipping coverage.
    """
    assert CI_WORKFLOW.exists(), (
        f"{CI_WORKFLOW} is missing — the repo's CI workflow moved. Update "
        f"this guard to the new path."
    )
    parsed = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    jobs = parsed.get("jobs") or {}
    matches = [
        step
        for job in jobs.values()
        if isinstance(job, dict)
        for step in (job.get("steps") or [])
        if isinstance(step, dict)
        and "pytest integration-tests" in str(step.get("run", ""))
    ]
    assert len(matches) == 1, (
        f"expected exactly one step running `pytest integration-tests` in "
        f"{CI_WORKFLOW.name}, found {len(matches)}. The integration gate step "
        f"was renamed, removed, or duplicated — update this guard."
    )
    return matches[0]


def test_integration_step_does_not_swallow_failures() -> None:
    run_block = str(_integration_step().get("run", ""))
    assert "|| true" not in run_block, (
        "the integration-tests CI step contains `|| true`, which swallows a "
        "failing suite's non-zero exit and leaves CI green on real failures. "
        "Removed in iterate-2026-05-31-ci-gate-f821 — do not re-add it. (The "
        "lint step's `|| true` is a separate, out-of-scope item.)"
    )


def test_integration_step_not_continue_on_error() -> None:
    coe = _integration_step().get("continue-on-error")
    assert coe in (None, False), (
        f"the integration-tests CI step has continue-on-error={coe!r}, which "
        f"un-gates the layer exactly like `|| true` would — a failing suite "
        f"would not fail the job. Keep the integration gate hard."
    )
