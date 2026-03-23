"""Enforcement thresholds for compliance hooks.

Reads configurable thresholds from shipwright_compliance_config.json
field "enforcement". All thresholds have sensible defaults.

Usage:
    thresholds = load_thresholds(project_root)
    if coverage < thresholds.rtm_coverage_min:
        # block
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EnforcementThresholds:
    """Compliance enforcement thresholds."""
    rtm_coverage_min: float = 0.80
    allowed_critical_findings: int = 0
    sbom_completeness_min: float = 0.90


def load_thresholds(project_root: str | Path) -> EnforcementThresholds:
    """Load enforcement thresholds from compliance config.

    Reads from {project_root}/shipwright_compliance_config.json
    field "enforcement". Falls back to defaults if missing.
    """
    config_path = Path(project_root) / "shipwright_compliance_config.json"
    if not config_path.exists():
        return EnforcementThresholds()

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return EnforcementThresholds()

    enforcement = config.get("enforcement", {})
    return EnforcementThresholds(
        rtm_coverage_min=enforcement.get("rtm_coverage_min", 0.80),
        allowed_critical_findings=enforcement.get("allowed_critical_findings", 0),
        sbom_completeness_min=enforcement.get("sbom_completeness_min", 0.90),
    )
