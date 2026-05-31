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
    AllowEntry(
        "ci.yml", "Lint (ruff)",
        "Tracked debt: ruff is not yet a real gate (261 baseline violations and "
        "ruff is not a declared dep, so the step is currently a no-op). Hardening "
        "needs a dedicated cleanup iterate. Listed so the loose gate is explicit, "
        "not silent.",
        "tracked-debt",
    ),
    AllowEntry(
        "ci.yml", "Run shared tests (non-gating, tracked-debt)",
        "Tracked debt: shared/**/tests carries Linux-portability debt from "
        "Windows-only development (leaked os.name='nt' monkeypatches crash "
        "pytest's reporter on the ubuntu-only runner; some tests assume "
        "gitignored main-tree staging). Runs non-gating for visibility until a "
        "follow-up iterate makes the suite Linux-CI-clean; the dirs stay "
        "referenced so check (a) still catches a NEW uncovered shared dir. When "
        "the debt clears, the step hardens and this entry goes stale (forcing "
        "removal).",
        "tracked-debt",
    ),
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
]
