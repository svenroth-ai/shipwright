"""signal_bundle — compute the G2 signals + map them onto the engine surface.

One call site the projector uses: given the ``RepoContext``, the resolved
``NetworkPolicy`` and a ``gh`` runner, compute all four G2 dimensions (test
health, security, dependency hygiene, maintainability), then expose:

- :meth:`SignalBundle.grade_input_kwargs` — the ``GradeInputs`` fields to set for
  the dims that lit (unset dims keep their n/a engine defaults);
- :meth:`SignalBundle.detail_overrides` — the honest per-dimension detail strings;
- :meth:`SignalBundle.provenance` — the per-dimension source + disabled-enrichment
  metadata the report view-model stamps.

Each signal is computed defensively — an unavailable reused collector or a
misbehaving ``gh`` degrades that one dimension to ``n/a``, never crashing the
grade (the grader must always produce *some* honest verdict).
"""

from __future__ import annotations

from dataclasses import dataclass

from dependency_signal import DependencySignal, compute_dependency_signal
from gh_bridge import GhRunner
from network_policy import NetworkPolicy
from provenance_signal import ProvenanceSignal, compute_provenance_signal
from repo_context import RepoContext
from security_signal import SecuritySignal, compute_security_signal
from size_signal import SizeSignal, compute_size_signal
from test_health_signal import TestHealthSignal, compute_test_health_signal


@dataclass(frozen=True)
class SignalBundle:
    test_health: TestHealthSignal
    security: SecuritySignal
    dependency: DependencySignal
    size: SizeSignal
    change_provenance: ProvenanceSignal

    def grade_input_kwargs(self) -> dict:
        kwargs: dict = {}
        if self.size.measurable:
            kwargs["oversize_file_ratio"] = self.size.ratio
        if self.test_health.measurable:
            kwargs["latest_full_suite_passed"] = self.test_health.passed
            kwargs["latest_full_suite_total"] = self.test_health.total
            # date stays "" — deterministic scored content (plan §6).
        if self.security.measurable:
            kwargs["security_measurable"] = True
            kwargs["security_open_high_critical"] = self.security.open_high_critical
        if self.dependency.measurable:
            kwargs["deps_total"] = self.dependency.deps_total
            kwargs["deps_unknown_license"] = self.dependency.deps_unknown_license
            kwargs["deps_copyleft"] = self.dependency.deps_copyleft
        return kwargs

    def detail_overrides(self) -> dict[str, str]:
        overrides = {
            "security": self.security.detail,
            "maintainability": self.size.detail,
            "dependency_hygiene": self.dependency.detail,
        }
        # test_health: a scored tier labels itself; otherwise the projector's
        # static-inventory line (G1 behaviour) is kept.
        if self.test_health.measurable:
            overrides["test_health"] = self.test_health.detail
        # change_traceability: the network PR-association tier labels its own
        # provenance source (the git-log fallback keeps the engine's count detail).
        if self.change_provenance.measurable:
            overrides["change_traceability"] = self.change_provenance.detail
        return overrides

    def provenance(self) -> dict[str, dict]:
        th = self.test_health
        sec = self.security
        mt = self.size
        dep = self.dependency
        cp = self.change_provenance
        return {
            "change_traceability": (
                {"source": "PR-association (SLSA code-review, network)", "disabled": ()}
                if cp.measurable else
                {"source": "git-log PR/issue references (local)",
                 "disabled": ("pr-association",)}),
            "test_health": (
                {"source": f"CI test signal — {th.tier}", "disabled": ()}
                if th.measurable else
                {"source": "static test inventory — present, not executed",
                 "disabled": ("ci-junit-pass-ratio", "scorecard-check-runs")}),
            "security": (
                {"source": f"GitHub code-scanning SARIF ({sec.source})", "disabled": ()}
                if sec.measurable else
                {"source": sec.detail, "disabled": ("code-scanning-sarif",)}),
            "maintainability": (
                {"source": "static oversize-file ratio (local)", "disabled": ()}
                if mt.measurable else
                {"source": "size proxy unavailable — no source files",
                 "disabled": ("oversize-file-ratio",)}),
            "dependency_hygiene": (
                {"source": "lockfile → SBOM license resolution (local)", "disabled": ()}
                if dep.measurable else
                {"source": dep.detail, "disabled": ("lockfile-sbom",)}),
        }


def _safe(factory, fallback):
    try:
        return factory()
    except Exception:
        return fallback


def compute_signals(
    context: RepoContext, policy: NetworkPolicy, gh: GhRunner
) -> SignalBundle:
    """Compute the four G2 signals defensively (a failure degrades to n/a)."""
    size = _safe(
        lambda: compute_size_signal(context),
        SizeSignal(False, None, 0, 0, "size proxy unavailable", False))
    dependency = _safe(
        lambda: compute_dependency_signal(context.root),
        DependencySignal(False, 0, 0, 0, "dependency scan unavailable", 0))
    test_health = _safe(
        lambda: compute_test_health_signal(
            policy, gh,
            has_test_infra=context.test_file_count > 0 and context.has_ci),
        TestHealthSignal(False, None, None, "static-inventory",
                         "test-health signal unavailable"))
    security = _safe(
        lambda: compute_security_signal(policy, gh),
        SecuritySignal(False, None, "security signal unavailable", ""))
    change_provenance = _safe(
        lambda: compute_provenance_signal(policy, gh),
        ProvenanceSignal(False, None, "git-log", "provenance signal unavailable"))
    return SignalBundle(test_health=test_health, security=security,
                        dependency=dependency, size=size,
                        change_provenance=change_provenance)
