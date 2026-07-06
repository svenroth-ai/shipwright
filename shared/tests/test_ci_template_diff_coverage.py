"""Every vitest-based adopt CI template ships the warn-only diff-coverage gate.

Diff-coverage rollout (``iterate-2026-07-07-diff-coverage-adopt-templates``): an
adopted vitest repo gets the changed-line coverage gate for free — a
``diff-coverage`` job that feeds each package's cobertura report to a pinned
``diff-cover``. WARN-ONLY at rollout (``continue-on-error``) so it never blocks
an adopter's first PRs; they flip it to hard-block after a settling window,
mirroring the shipwright monorepo's proven warn -> prove -> flip path.

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
            body = "\n".join(
                s.get("run", "")
                for s in job.get("steps", [])
                if isinstance(s, dict)
            )
            assert "diff-cover@10.3.0" in body, (
                f"profile {profile!r}: diff-coverage job must run the PINNED "
                f"diff-cover@10.3.0 (a release can't silently change the gate)."
            )
            assert "--fail-under=80" in body, (
                f"profile {profile!r}: diff-coverage job must gate at 80% "
                f"(the shipwright reference threshold)."
            )
