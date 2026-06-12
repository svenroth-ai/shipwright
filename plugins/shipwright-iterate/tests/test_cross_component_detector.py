"""`classify_complexity.is_cross_component_change` — the diff-driven detector for
the `cross_component` risk flag (iterate-2026-06-12-cross-component-gate).

Mirrors `is_io_boundary_change`: a change touching the cross-component framework
machinery (merge/churn/event-log resolver, Claude-Code hooks + hook fan-out,
pipeline phase validators, campaign drain) trips the flag, which at medium+ forces
an INTEGRATION-coverage behavior in the Test Completeness Ledger — the gap that let
the merge-cascade fixes ship unit-tested but composition-unproven.
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"
sys.path.insert(0, str(_LIB))

import classify_complexity as cc  # noqa: E402


def test_positive_merge_and_pipeline_machinery():
    for p in [
        "shared/scripts/tools/integrate_main.py",
        "shared/scripts/lib/churn_merge.py",
        "shared/scripts/lib/gitattributes_union.py",
        "shared/scripts/tools/ensure_current.py",
        "shared/scripts/tools/resolve_churn_conflicts.py",
        "shared/scripts/lib/autonomous_loop.py",
    ]:
        assert cc.is_cross_component_change([p]) is True, p


def test_positive_hooks_config_and_fanout_scripts():
    assert cc.is_cross_component_change(["plugins/shipwright-iterate/hooks/hooks.json"]) is True
    assert cc.is_cross_component_change(["plugins/shipwright-build/scripts/hooks/suggest_iterate.py"]) is True
    assert cc.is_cross_component_change(["shared/scripts/hooks/audit_compliance_on_stop.py"]) is True
    # nested hook script (recursive match — external-review fix)
    assert cc.is_cross_component_change(["plugins/x/hooks/group/deep_hook.py"]) is True


def test_positive_pipeline_validators_and_campaign():
    assert cc.is_cross_component_change(["shared/scripts/tools/verify_phase.py"]) is True
    assert cc.is_cross_component_change(
        ["plugins/shipwright-iterate/scripts/tools/campaign_progress.py"]
    ) is True
    assert cc.is_cross_component_change(
        ["plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md"]
    ) is True


def test_negative_ordinary_changes():
    for p in [
        "src/app/routes/courses/page.tsx",
        "plugins/shipwright-iterate/skills/iterate/references/F4.md",
        ".shipwright/agent_docs/architecture.md",
        "shared/scripts/tools/write_changelog_drop.py",
        "docs/guide.md",
        "README.md",
    ]:
        assert cc.is_cross_component_change([p]) is False, p


def test_empty_and_windows_paths():
    assert cc.is_cross_component_change(None) is False
    assert cc.is_cross_component_change([]) is False
    assert cc.is_cross_component_change(
        ["shared\\scripts\\tools\\integrate_main.py"]
    ) is True  # backslash-normalized


def test_taxonomy_entry_present_and_medium_gated():
    flag = cc.RISK_TAXONOMY.get("cross_component")
    assert flag is not None, "cross_component must be in RISK_TAXONOMY"
    assert flag["min_complexity"] == "medium"
    assert "integration_coverage" in flag["enforces"]
