"""End-to-end: real CLIs, real generated documents on disk.

The unit tests call the renderers directly. This drives the two production
entry points a person actually uses — ``run_audit.py`` (the cross-check) and
``update_compliance.py`` (the document generator) — as subprocesses against a
scratch project, then reads the resulting ``.md`` files off disk.

It is the F0.5 surface runner for this iterate, so it has to fail if ANY link in
the chain breaks: recording, collection, or rendering.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
RUN_AUDIT = PLUGIN_ROOT / "scripts" / "audit" / "run_audit.py"
UPDATE_COMPLIANCE = PLUGIN_ROOT / "scripts" / "tools" / "update_compliance.py"

COMPLIANCE_DIR = Path(".shipwright") / "compliance"
# The four documents that carry the one-line header disclosure.
HEADER_DOCS = (
    "traceability-matrix.md",
    "test-evidence.md",
    "change-history.md",
    "sbom.md",
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "profile": "python", "scope": "library"}),
        encoding="utf-8",
    )
    return root


def _run(script: Path, project_root: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), "--project-root", str(project_root), *extra],
        capture_output=True, text=True, encoding="utf-8",
    )


def _regenerate(project_root: Path) -> None:
    result = _run(UPDATE_COMPLIANCE, project_root, "--phase", "iterate")
    assert result.returncode == 0, result.stderr or result.stdout


def _header(project_root: Path, doc: str) -> str:
    """The document's ``Consistency-audit:`` provenance line, read off disk."""
    text = (project_root / COMPLIANCE_DIR / doc).read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("Consistency-audit:"):
            return line
    raise AssertionError(f"{doc} has no 'Consistency-audit:' provenance line")


def test_documents_disclose_never_run_before_any_audit(project: Path):
    _regenerate(project)
    for doc in HEADER_DOCS:
        assert "never run" in _header(project, doc), doc
    dashboard = (project / COMPLIANCE_DIR / "dashboard.md").read_text(encoding="utf-8")
    assert "Never run" in dashboard


def test_documents_disclose_the_audit_after_it_runs(project: Path):
    """The whole chain: cross-check → durable record → regenerated documents."""
    audit = _run(RUN_AUDIT, project)
    assert audit.returncode in (0, 1), audit.stderr
    ran_at = json.loads(audit.stdout)["last_audit_recorded"]["last_audit"]["ran_at"]
    day = ran_at[:10]

    _regenerate(project)

    for doc in HEADER_DOCS:
        header = _header(project, doc)
        assert day in header, f"{doc}: {header}"
        assert "never run" not in header, doc

    dashboard = (project / COMPLIANCE_DIR / "dashboard.md").read_text(encoding="utf-8")
    assert "## 🔎 Consistency Audit" in dashboard
    assert day in dashboard
    assert "Never run" not in dashboard


def test_a_partial_audit_does_not_claim_a_full_cross_check(project: Path):
    """After ``--only``, the documents still lead with the last FULL run."""
    full = _run(RUN_AUDIT, project)
    assert full.returncode in (0, 1), full.stderr
    full_day = json.loads(full.stdout)["last_audit_recorded"]["last_audit"]["ran_at"][:10]

    partial = _run(RUN_AUDIT, project, "--only", "A")
    assert partial.returncode in (0, 1), partial.stderr

    _regenerate(project)

    header = _header(project, "traceability-matrix.md")
    assert "last full run" in header
    assert full_day in header
    assert "partial" in header

    dashboard = (project / COMPLIANCE_DIR / "dashboard.md").read_text(encoding="utf-8")
    assert "Last full run" in dashboard
    assert "does not re-check the rest of the project" in dashboard


def test_the_compliance_phase_refreshes_every_documents_disclosure(project: Path):
    """``/shipwright-compliance``'s own regen must not leave documents behind.

    The audit records the run; if the compliance phase only rebuilt the
    dashboard, the other four documents would still say "never run" at exactly
    the moment the operator asked for the check.
    """
    _regenerate(project)  # seed all five documents in the "never run" state
    audit = _run(RUN_AUDIT, project)
    assert audit.returncode in (0, 1), audit.stderr
    day = json.loads(audit.stdout)["last_audit_recorded"]["last_audit"]["ran_at"][:10]

    result = _run(UPDATE_COMPLIANCE, project, "--phase", "compliance")
    assert result.returncode == 0, result.stderr or result.stdout

    for doc in HEADER_DOCS:
        header = _header(project, doc)
        assert day in header, f"{doc} not refreshed: {header}"
        assert "never run" not in header, doc


def _audit_section(project_root: Path) -> str:
    text = (project_root / COMPLIANCE_DIR / "dashboard.md").read_text(encoding="utf-8")
    start = text.index("## 🔎 Consistency Audit")
    return text[start:text.index("\n## ", start + 1)]


def test_regenerating_twice_leaves_the_disclosure_byte_identical(project: Path):
    """Determinism through the real generator, not just the render function.

    Asserted on the disclosure specifically rather than on whole documents: each
    dashboard regen appends a ``grade_snapshot`` event to the event log, so parts
    of the dashboard legitimately move between regens. That is pre-existing
    generator behaviour; what must not move is anything this change introduced.
    """
    _run(RUN_AUDIT, project)
    _regenerate(project)
    headers = {doc: _header(project, doc) for doc in HEADER_DOCS}
    section = _audit_section(project)

    _regenerate(project)
    for doc, before in headers.items():
        assert _header(project, doc) == before, doc
    assert _audit_section(project) == section
