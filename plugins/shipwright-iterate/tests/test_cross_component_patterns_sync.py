"""Drift-pin: the F11 verifier's self-contained `_CROSS_COMPONENT_PATTERNS` MUST
equal the SSoT `classify_complexity.CROSS_COMPONENT_FILE_PATTERNS`
(iterate-2026-06-12-cross-component-gate).

The verifier keeps a LOCAL copy on purpose — it is load-bearing and runs in every
shared/tests + CI session, so it must never cross-plugin-import the iterate lib
(ADR-044). This test (the iterate plugin owns `classify_complexity`; `iterate_checks`
is in shared/, not another plugin, so this is NOT cross_plugin) keeps the two copies
honest in BOTH directions, mirroring `test_untestable_vocab_doc_sync`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "shipwright-iterate" / "scripts" / "lib"))
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))

import classify_complexity as cc  # noqa: E402
from tools.verifiers import iterate_checks as ic  # noqa: E402


def test_verifier_copy_equals_ssot_both_directions():
    ssot = set(cc.CROSS_COMPONENT_FILE_PATTERNS)
    copy = set(ic._CROSS_COMPONENT_PATTERNS)
    assert copy == ssot, (
        "verifier _CROSS_COMPONENT_PATTERNS drifted from "
        f"classify_complexity.CROSS_COMPONENT_FILE_PATTERNS\n"
        f"  only in SSoT: {ssot - copy}\n  only in verifier: {copy - ssot}"
    )


def test_ssot_and_detector_agree():
    # The SSoT detector and the verifier's local detector classify the same.
    for p in ["shared/scripts/tools/integrate_main.py",
              "x/hooks/hooks.json", "shared/scripts/tools/verify_phase.py",
              "src/app/page.tsx", "docs/guide.md"]:
        assert cc.is_cross_component_change([p]) == ic._is_cross_component([p]), p
