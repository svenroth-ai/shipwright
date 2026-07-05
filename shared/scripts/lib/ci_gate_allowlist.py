"""SSoT for CI quality-gate steps that are intentionally non-gating.

Consumed by ``shared/scripts/tools/check_ci_gate_coverage.py``. Each entry
documents one ``|| true`` / ``continue-on-error: true`` that the guard must
tolerate. The guard enforces both-direction drift protection against this list:

  - forward  — ``stale_allowlist_entries``: an entry that matches no real loose
    step on disk is flagged (a step was renamed/hardened but the entry lingers).
  - reverse  — ``check_loose_gates``: a real loose step that is NOT listed here
    is flagged (a gate went silently loose).

``category``:
  - ``by-design``    — non-gating is correct (e.g. a scan that feeds a separate
    threshold gate; SARIF upload that needs GitHub Advanced Security).
  - ``tracked-debt`` — should become gating; deferred to a follow-up iterate and
    documented here so it is explicit, never silent.

``launch_gate`` marks a ``continue-on-error`` that exists only because the repo
is private (no code scanning) and MUST be removed at public launch.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AllowEntry:
    workflow: str  # workflow file basename, e.g. "ci.yml"
    step: str  # step ``name:`` — byte-identical to the workflow
    reason: str
    category: str  # "by-design" | "tracked-debt"
    launch_gate: bool = False


LOOSE_GATE_ALLOWLIST: list[AllowEntry] = [
    # NOTE: ci.yml's lint + shared-tests steps were tracked-debt allowlist
    # entries in this PR's original form (when they were loose). They are now
    # GATING on main — lint via PR #125 (uvx ruff@0.15.15, curated F-ruleset)
    # and shared/tests via PR #124 (set -e, `-m "not cross_plugin"`) — so the
    # tracked-debt entries were dropped; a gating step is not loose, and a stale
    # allowlist entry would (correctly) fail the guard's own stale-entry check.
    AllowEntry(
        "security.yml", "Run OSS security scan (Semgrep + Trivy + Gitleaks)",
        "By design: the scan must not gate the workflow — the 'Check for critical "
        "findings' step is the real gate; a scanner crash is caught by the "
        "missing-findings guard.",
        "by-design",
    ),
    AllowEntry(
        "security.yml", "Generate SARIF outputs",
        "By design: SARIF rendering is non-gating; the critical-gate decides.",
        "by-design",
    ),
    AllowEntry(
        "security.yml", "Run Prompt Injection scan",
        "By design: feeds the report + critical-gate; does not gate on its own.",
        "by-design",
    ),
    AllowEntry(
        "security.yml", "Upload SARIF to GitHub Security",
        "Private-repo: code scanning (Advanced Security) is unavailable, so "
        "upload-sarif would fail closed without continue-on-error. Revisit at "
        "public launch.",
        "by-design", launch_gate=True,
    ),
    AllowEntry(
        "codeql.yml", "Perform analysis",
        "Private-repo: codeql-action/analyze uploads SARIF, which needs code "
        "scanning (Advanced Security). MUST be removed at public launch so "
        "analysis failures gate again.",
        "by-design", launch_gate=True,
    ),
    AllowEntry(
        "ci.yml", "Diff coverage (warn-only gate)",
        "Tracked-debt (diff-coverage roadmap Phase 4, warn-only): the step now "
        "runs `diff-cover --fail-under=80`, so an under-tested PR shows a visible "
        "FAILURE on this step — but continue-on-error stays TRUE for the ~1-2 "
        "week settling window, so it WARNS without blocking merge. The hard flip "
        "(drop continue-on-error) REMOVES this entry, at which point the guard's "
        "stale-entry + reverse-drift checks enforce that it stays gating.",
        "tracked-debt",
    ),
]
