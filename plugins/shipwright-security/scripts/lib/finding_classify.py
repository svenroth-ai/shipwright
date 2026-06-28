"""Backend-agnostic finding classification.

Extracted into its OWN leaf module so both the generic scanner interface
(:mod:`scanner_backend`) and the specific Aikido client (:mod:`aikido_client`)
can import :func:`classify_finding` WITHOUT importing each other. That broke the
``scanner_backend -> aikido_client -> scanner_backend`` import cycle (CodeQL
``py/cyclic-import``) and removed the duplicated inline copies. The classifier
only inspects a finding's ``severity`` / ``type`` fields — it has no Aikido or
scanner dependency, so it is a pure leaf (stdlib only).
"""

from __future__ import annotations

from typing import Any

# Finding-type → remediation-class buckets.
AUTO_FIXABLE_TYPES = {"dependency", "sca"}
AGENT_FIXABLE_TYPES = {"sast", "secret_detection"}


def classify_finding(finding: dict[str, Any]) -> str:
    """Classify a finding into a remediation category.

    Returns one of: auto-fixable, agent-fixable, needs-review, informational.
    """
    severity = finding.get("severity", "").lower()
    finding_type = finding.get("type", "").lower()

    # Low severity and informational → just log
    if severity in ("low", "info", "informational"):
        return "informational"

    # Dependency/SCA issues with known patches → auto-fixable
    if finding_type in AUTO_FIXABLE_TYPES:
        return "auto-fixable"

    # SAST / secret detection → agent can analyze and fix
    if finding_type in AGENT_FIXABLE_TYPES:
        return "agent-fixable"

    # Everything else (architecture, business logic, etc.) → human review
    return "needs-review"
