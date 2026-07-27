"""Every compliance evidence document discloses when the cross-check last ran.

AC-1/AC-2: a reader who opens ONE of these documents — not the dashboard, not
the whole set — must be able to weigh it. The audit has no schedule and no CI
trigger, so "no disclosure" and "never checked" are indistinguishable to a
reader unless the document says which it is.

These are integration tests: they go through the real ``collect_all`` and the
real renderers, so they fail if the fact stops being collected OR stops being
rendered.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.lib.audit_disclosure import record_audit_run
from scripts.lib.change_history import generate as render_change_history
from scripts.lib.compliance_report import generate as render_dashboard
from scripts.lib.data_collector import collect_all
from scripts.lib.rtm_generator import generate as render_rtm
from scripts.lib.sbom_generator import generate as render_sbom
from scripts.lib.test_evidence import generate as render_test_evidence

# The dashboard carries the full Consistency Audit section instead of the
# one-line header suffix, so it is asserted separately.
_HEADER_RENDERERS = {
    "traceability-matrix.md": render_rtm,
    "test-evidence.md": render_test_evidence,
    "change-history.md": render_change_history,
    "sbom.md": render_sbom,
}


def _header(text: str) -> str:
    """The document's ``Generated:`` line, where provenance is disclosed."""
    for line in text.splitlines():
        if line.startswith("Generated:"):
            return line
    raise AssertionError("document has no 'Generated:' header line")


@pytest.mark.parametrize("doc", sorted(_HEADER_RENDERERS))
def test_never_run_is_disclosed_in_every_document(doc: str, project_root: Path):
    text = _HEADER_RENDERERS[doc](collect_all(project_root))
    header = _header(text)
    assert "Consistency audit" in header
    assert "never run" in header


@pytest.mark.parametrize("doc", sorted(_HEADER_RENDERERS))
def test_recorded_run_is_disclosed_in_every_document(doc: str, project_root: Path):
    record_audit_run(
        project_root, statuses=["pass", "skip"], any_fail=False,
        ran_at="2026-07-15T00:00:00+00:00",
    )
    header = _header(_HEADER_RENDERERS[doc](collect_all(project_root)))
    assert "2026-07-15" in header
    assert "PASS" in header


@pytest.mark.parametrize("doc", sorted(_HEADER_RENDERERS))
def test_disclosure_does_not_displace_the_generated_timestamp(
    doc: str, project_root: Path,
):
    """The new fact is additive — when it was written is still readable."""
    data = collect_all(project_root)
    header = _header(_HEADER_RENDERERS[doc](data))
    assert header.startswith(f"Generated: {data.timestamp}")


def test_sbom_keeps_its_own_header_qualifier(project_root: Path):
    """SBOM's lock-resolution note must survive alongside the disclosure."""
    data = collect_all(project_root)
    data.dependencies_lock_resolved = True
    header = _header(render_sbom(data))
    assert "resolved from uv.lock" in header
    assert "Consistency audit" in header


def test_dashboard_carries_the_section_not_the_header_suffix(project_root: Path):
    text = render_dashboard(collect_all(project_root))
    assert "## 🔎 Consistency Audit" in text
    # No double-disclosure: the dashboard states it once, in full.
    assert "Consistency audit:" not in _header(text)


def test_dashboard_section_reflects_a_recorded_run(project_root: Path):
    record_audit_run(
        project_root, statuses=["pass"], any_fail=False,
        ran_at="2026-07-15T00:00:00+00:00",
    )
    text = render_dashboard(collect_all(project_root))
    assert "2026-07-15" in text
    assert "Never run" not in text


@pytest.mark.parametrize("doc", sorted(_HEADER_RENDERERS))
def test_render_stays_byte_stable_across_regens(doc: str, project_root: Path):
    """Determinism: the disclosure is event-pinned, never wall-clock."""
    render = _HEADER_RENDERERS[doc]
    record_audit_run(
        project_root, statuses=["pass"], any_fail=False,
        ran_at="2026-07-15T00:00:00+00:00",
    )
    assert render(collect_all(project_root)) == render(collect_all(project_root))


@pytest.mark.parametrize("doc", sorted(_HEADER_RENDERERS))
def test_the_audit_record_is_an_explicit_render_input(doc: str, project_root: Path):
    """Determinism is over (event log + audit record), not the event log alone.

    Running the audit between two regens SHOULD change the documents — that is
    the feature. What must never change them is the wall clock.
    """
    render = _HEADER_RENDERERS[doc]
    before = render(collect_all(project_root))
    record_audit_run(
        project_root, statuses=["pass"], any_fail=False,
        ran_at="2026-07-15T00:00:00+00:00",
    )
    after = render(collect_all(project_root))
    assert before != after
    assert "never run" in _header(before)
    assert "2026-07-15" in _header(after)


def test_directly_constructed_data_renders_without_the_note(project_root: Path):
    """Backwards compatibility: the field defaults to empty, not to a lie."""
    data = collect_all(project_root)
    data.audit_freshness_note = ""
    assert _header(render_rtm(data)) == f"Generated: {data.timestamp}"
