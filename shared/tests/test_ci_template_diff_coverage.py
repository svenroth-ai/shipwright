"""Every vitest-based adopt CI template ships the warn-only diff-coverage gate.

Diff-coverage rollout (``iterate-2026-07-07-diff-coverage-adopt-templates``): an
adopted vitest repo gets the changed-line coverage gate for free — a
``diff-coverage`` job that feeds each package's cobertura report to a pinned
``diff-cover``. WARN-ONLY at rollout (``continue-on-error``) so it never blocks
an adopter's first PRs; they flip it to hard-block after a settling window,
mirroring the shipwright monorepo's proven warn -> prove -> flip path.

Composite-action refactor (``iterate-2026-07-07-diff-coverage-composite-action``):
the gate mechanics no longer live *inline* in the template. The template's
``diff-coverage`` job now consumes the monorepo's single-source-of-truth
composite action via
``uses: svenroth-ai/shipwright/.github/actions/diff-coverage-gate@main`` — so a
gate fix flows to every adopter without editing each template copy. This test
therefore asserts the ``uses:`` reference + the WARN-ONLY / ubuntu-only job
envelope; the pinned ``diff-cover@10.3.0`` / ``--fail-under=80`` invariants moved
into the action's own contract test (``test_diff_coverage_action.py``).

Split out of ``test_ci_workflow_convention.py`` to keep that file at its bloat
baseline (the convention test only gained the ``diff-coverage`` Linux-only
pattern; this positive assertion lives here).
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from lib.ci_workflow import TEMPLATE_BY_PROFILE  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

# The single-source-of-truth composite action every consumer references. The
# ``@main`` mutable ref is intentional first-party auto-propagation (a gate fix
# in the monorepo flows to every adopter on their next run).
ACTION_REF_PREFIX = "svenroth-ai/shipwright/.github/actions/diff-coverage-gate@"


def _vitest_templates() -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for profile, template_rel in TEMPLATE_BY_PROFILE.items():
        template = REPO_ROOT / template_rel
        if not template.exists():
            continue
        raw = template.read_text(encoding="utf-8")
        if "vitest" not in raw:  # python template is exempt (no vitest)
            continue
        out.append((profile, yaml.safe_load(raw)))
    return out


class TestCITemplatesDiffCoverageGate:
    def test_vitest_templates_carry_a_warn_only_diff_coverage_job(self) -> None:
        vt = _vitest_templates()
        assert vt, "expected at least one vitest CI template to exist"
        for profile, parsed in vt:
            jobs = parsed.get("jobs") or {}
            assert "diff-coverage" in jobs, (
                f"profile {profile!r}: vitest template has no `diff-coverage` "
                f"job — the changed-line coverage gate must ship with it."
            )
            job = jobs["diff-coverage"]
            assert job.get("continue-on-error") is True, (
                f"profile {profile!r}: the diff-coverage job must be WARN-ONLY "
                f"(continue-on-error: true) at rollout so it never blocks an "
                f"adopter's first PRs."
            )
            assert job.get("runs-on") == "ubuntu-latest", (
                f"profile {profile!r}: diff-coverage is OS-agnostic — run it once "
                f"on ubuntu-latest, not the cross-platform matrix."
            )
            steps = [s for s in job.get("steps", []) if isinstance(s, dict)]
            # The gate now runs through the single-source-of-truth composite
            # action, not an inline diff-cover copy.
            gate_step = next(
                (
                    s
                    for s in steps
                    if isinstance(s.get("uses"), str)
                    and s["uses"].startswith(ACTION_REF_PREFIX)
                ),
                None,
            )
            assert gate_step is not None, (
                f"profile {profile!r}: diff-coverage job must consume the gate via "
                f"`uses: {ACTION_REF_PREFIX}<ref>` — the pinned diff-cover / "
                f"--fail-under mechanics live in the action now, so a fix flows to "
                f"every adopter without editing this template."
            )
            with_block = gate_step.get("with") or {}
            assert with_block.get("coverage-files"), (
                f"profile {profile!r}: the gate `uses:` step must pass "
                f"`coverage-files` (the cobertura path(s) to gate) to the action."
            )
            # The template must still PRODUCE coverage before gating — a `uses:`
            # step with no upstream cobertura report would gate nothing.
            body = "\n".join(s.get("run", "") for s in steps)
            assert "cobertura" in body or "cobertura" in str(with_block), (
                f"profile {profile!r}: diff-coverage job must produce a cobertura "
                f"report (coverage.reporter=cobertura) before the gate step."
            )
            # fetch-depth:0 is the gate's #1 caller prerequisite — without full
            # history `origin/<base>` is unresolvable and diff-cover errors.
            # Drop it and the job stays green while gating nothing, so lock it.
            checkout = next(
                (s for s in steps if isinstance(s.get("uses"), str)
                 and s["uses"].startswith("actions/checkout@")),
                None,
            )
            assert checkout is not None, (
                f"profile {profile!r}: diff-coverage job needs an actions/checkout step."
            )
            assert (checkout.get("with") or {}).get("fetch-depth") == 0, (
                f"profile {profile!r}: diff-coverage checkout must set `fetch-depth: 0` "
                f"— the composite gate fetches the compare branch and needs full history."
            )
            # Dormant-trigger discipline: the job only runs on PRs (matches the
            # workflow's Phase-B activation contract).
            assert "pull_request" in str(job.get("if", "")), (
                f"profile {profile!r}: diff-coverage job must be gated on "
                f"`if: github.event_name == 'pull_request'`."
            )
