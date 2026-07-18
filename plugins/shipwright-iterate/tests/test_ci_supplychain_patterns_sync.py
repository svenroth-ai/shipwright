"""Drift-pin: the F11 verifier's self-contained `_CI_SUPPLYCHAIN_PATTERNS` MUST
equal the SSoT `risk_detectors.CI_SUPPLYCHAIN_FILE_PATTERNS`
(iterate-2026-07-18-ci-supplychain-risk-flag).

The verifier keeps a LOCAL copy on purpose — it is load-bearing and runs in every
shared/tests + CI session, so it must never cross-plugin-import the iterate lib
(ADR-044). This test keeps the two copies honest in BOTH directions, mirroring
`test_cross_component_patterns_sync`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "shipwright-iterate" / "scripts" / "lib"))
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))

import risk_detectors as rd  # noqa: E402
from tools.verifiers import iterate_checks as ic  # noqa: E402


def test_verifier_copy_equals_ssot_both_directions():
    ssot = set(rd.CI_SUPPLYCHAIN_FILE_PATTERNS)
    copy = set(ic._CI_SUPPLYCHAIN_PATTERNS)
    assert copy == ssot, (
        "verifier _CI_SUPPLYCHAIN_PATTERNS drifted from "
        f"risk_detectors.CI_SUPPLYCHAIN_FILE_PATTERNS\n"
        f"  only in SSoT: {ssot - copy}\n  only in verifier: {copy - ssot}"
    )


def test_ssot_and_detector_agree():
    """Same verdict from both implementations across the full path matrix —
    source-text equality alone would not catch a divergent matcher."""
    for p in [".github/workflows/ci.yml",
              ".github/workflows/security.yaml",
              ".github/workflows/nested/deep.yml",
              ".github/dependabot.yml",
              ".github/dependabot.yaml",
              ".github/actions/gate/action.yml",
              ".github\\workflows\\ci.yml",
              "docs/.github/workflows/x.yml",
              ".github/workflow/x.yml",
              ".github/dependabot.json",
              ".github/CODEOWNERS",
              "shared/templates/github-actions/security.yml.template",
              "src/app/page.tsx"]:
        assert rd.is_ci_supplychain_change([p]) == ic._is_ci_supplychain([p]), p


def test_taxonomy_entry_exists_and_does_not_mandate_pinning():
    """The flag must force the change to be REASONED ABOUT, never force pinning.

    GitHub-owned actions stay on mutable tags by decision
    (webui ADR iterate-2026-07-18-unpin-actions-no-dependabot); a flag demanding
    pins would contradict the very posture it exists to protect.
    """
    import classify_complexity as cc

    entry = cc.RISK_TAXONOMY["touches_ci_supplychain"]
    assert entry["min_complexity"] == "small"
    assert "ci_supplychain_ack" in entry["enforces"]

    # The guard that actually matters is the PROSE a future author reads, not the
    # regex hints (which would never plausibly contain "pin"). SKILL.md is the
    # normative surface, so assert there: it must state the rule, and must not
    # instruct anyone to SHA-pin.
    row = next(
        ln for ln in (_REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" /
                      "iterate" / "SKILL.md").read_text(encoding="utf-8").splitlines()
        if ln.startswith("| `touches_ci_supplychain`")
    )
    low = row.lower()
    assert "never be read as" in low and "pin everything" in low, (
        "the SKILL.md row must keep the explicit 'never pin everything' caveat"
    )
    assert "sha-pin all" not in low, "SKILL.md must not instruct anyone to SHA-pin"
