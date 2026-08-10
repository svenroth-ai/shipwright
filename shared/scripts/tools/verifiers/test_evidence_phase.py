"""I2 test-evidence provenance verifier."""

from pathlib import Path
from typing import Any

from lib.phase_quality import STATUS_FAIL, STATUS_PASS, STATUS_SKIP, make_finding
from test_evidence_phase_source import latest_phase_source, parse_phase_source
from tools.verifiers.common import read_events_jsonl

_DOC = ".shipwright/compliance/test-evidence.md"
_NAME = "I2 test-evidence.md matches phase-start run identity"
_REMEDIATION = (
    "Regenerate .shipwright/compliance/test-evidence.md via "
    "`uv run update_compliance.py --phase test` (or the build/iterate equivalent); "
    "test results feed this doc."
)


def check_i2_test_evidence_fresh(project_root: Path, phase: str) -> dict[str, Any]:
    """Verify test evidence against its producing phase invocation, not mtime."""
    doc = project_root / _DOC
    if not doc.exists():
        return make_finding("I2", STATUS_FAIL, f"{_DOC} missing", name=_NAME,
                            remediation=_REMEDIATION)
    expected = latest_phase_source(read_events_jsonl(project_root), phase)
    if expected is None:
        return make_finding("I2", STATUS_SKIP,
                            f"latest phase_started[phase={phase}] has no usable run identity — "
                            "test-evidence provenance not verifiable yet", name=_NAME,
                            provenance="unverified_marker")
    try:
        actual = parse_phase_source(doc.read_text(encoding="utf-8"), phase)
    except (OSError, UnicodeError) as exc:
        return make_finding("I2", STATUS_FAIL, f"{_DOC} could not be read: {type(exc).__name__}",
                            name=_NAME, remediation=_REMEDIATION)
    if actual is None:
        return make_finding("I2", STATUS_FAIL, f"{_DOC} lacks Test-Evidence-Phase for phase={phase}",
                            name=_NAME, remediation=_REMEDIATION)
    if actual != expected:
        return make_finding("I2", STATUS_FAIL,
                            f"{_DOC} phase source is phase={actual.phase} run={actual.run_id}; "
                            f"expected phase={expected.phase} run={expected.run_id}",
                            name=_NAME, remediation=_REMEDIATION)
    return make_finding("I2", STATUS_PASS, f"{_DOC} matches phase_started run={expected.run_id}",
                        name=_NAME)
