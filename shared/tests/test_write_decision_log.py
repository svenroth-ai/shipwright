"""Tests for decision log writer (compact ADR format)."""

from tools.write_decision_log import (
    append_decision,
    check_field_length,
    collect_length_warnings,
    get_next_adr_number,
)


def test_get_next_adr_number_empty():
    assert get_next_adr_number("# Decision Log\n") == 1


def test_get_next_adr_number_compact_format():
    content = "### ADR-001: Title\n### ADR-002: Title\n### ADR-003: Title\n"
    assert get_next_adr_number(content) == 4


def test_get_next_adr_number_old_format():
    """Backwards compat: reads old ## ADR-NNN format too."""
    content = "## ADR-001 | ...\n## ADR-002 | ...\n"
    assert get_next_adr_number(content) == 3


def test_append_decision_creates_file(tmp_project):
    number = append_decision(
        tmp_project,
        section_ref="Build — 01-auth",
        commit_hash="abc1234",
        context="Need to decide on auth approach",
        decision="Use Supabase Auth with JWT",
        consequences="Stateless, scales horizontally",
        rejected="Session cookies",
    )
    assert number == 1

    log_path = tmp_project / ".shipwright" / "agent_docs" / "decision_log.md"
    assert log_path.exists()

    content = log_path.read_text()
    assert "### ADR-001:" in content
    assert "01-auth" in content
    assert "abc1234" in content
    assert "Supabase Auth with JWT" in content
    assert "Session cookies" in content


def test_compact_format_structure(tmp_project):
    """Verify the compact bullet-point format."""
    append_decision(
        tmp_project,
        section_ref="Build — 02-api",
        commit_hash="def5678",
        context="Need lightweight state management",
        decision="Use Zustand over Redux",
        consequences="Less boilerplate",
        rejected="Redux, MobX",
        title="Zustand for State Management",
        rationale="Simpler API, smaller bundle",
    )
    content = (tmp_project / ".shipwright" / "agent_docs" / "decision_log.md").read_text()
    assert "### ADR-001: Zustand for State Management" in content
    assert "- **Date:**" in content
    assert "02-api" in content
    assert "**Section:**" in content
    assert "- **Context:** Need lightweight state management" in content
    assert "- **Decision:** Use Zustand over Redux" in content
    assert "- **Commit:** def5678" in content
    assert "- **Rationale:** Simpler API, smaller bundle" in content
    assert "- **Consequences:** Less boilerplate" in content
    assert "- **Rejected:** Redux, MobX" in content


def test_title_auto_generated_from_decision(tmp_project):
    """Without --title, decision text is used as title."""
    append_decision(
        tmp_project,
        section_ref="Build — 01-auth",
        commit_hash="abc",
        context="C",
        decision="Use magic link authentication",
        consequences="X",
    )
    content = (tmp_project / ".shipwright" / "agent_docs" / "decision_log.md").read_text()
    assert "### ADR-001: Use magic link authentication" in content


def test_title_truncated_for_long_decisions(tmp_project):
    long_decision = "A" * 100
    append_decision(
        tmp_project,
        section_ref="Test",
        commit_hash="abc",
        context="C",
        decision=long_decision,
        consequences="X",
    )
    content = (tmp_project / ".shipwright" / "agent_docs" / "decision_log.md").read_text()
    # Title should be truncated with ...
    # Find the ADR header line
    adr_line = [l for l in content.splitlines() if l.startswith("### ADR-")][0]
    assert "..." in adr_line


def test_append_decision_sequential_numbering(tmp_project):
    for i in range(3):
        number = append_decision(
            tmp_project,
            section_ref=f"Section {i + 1:02d}",
            commit_hash=f"hash{i}",
            context=f"Context {i}",
            decision=f"Decision {i}",
            consequences=f"Consequence {i}",
        )
        assert number == i + 1

    content = (tmp_project / ".shipwright" / "agent_docs" / "decision_log.md").read_text()
    assert "### ADR-001:" in content
    assert "### ADR-002:" in content
    assert "### ADR-003:" in content


def test_append_decision_does_not_overwrite(tmp_project):
    append_decision(
        tmp_project,
        section_ref="First",
        commit_hash="aaa",
        context="C1",
        decision="D1",
        consequences="X1",
    )
    append_decision(
        tmp_project,
        section_ref="Second",
        commit_hash="bbb",
        context="C2",
        decision="D2",
        consequences="X2",
    )

    content = (tmp_project / ".shipwright" / "agent_docs" / "decision_log.md").read_text()
    assert "First" in content
    assert "Second" in content
    assert "### ADR-001:" in content
    assert "### ADR-002:" in content


def test_check_field_length_under_budget_returns_none():
    assert check_field_length("context", "short", max_chars=500) is None


def test_check_field_length_over_budget_returns_warning():
    long = "x" * 750
    warning = check_field_length("context", long, max_chars=500)
    assert warning is not None
    assert "context" in warning
    assert "750" in warning
    assert "500" in warning


def test_collect_length_warnings_collects_all_over_budget_fields():
    warnings = collect_length_warnings(
        context="x" * 600,
        decision="short",
        consequences="y" * 1000,
        rationale="",
        rejected="",
    )
    assert len(warnings) == 2
    joined = "\n".join(warnings)
    assert "context" in joined
    assert "consequences" in joined
    assert "decision" not in joined


def test_optional_fields_omitted_when_empty(tmp_project):
    append_decision(
        tmp_project,
        section_ref="Build — 01",
        commit_hash="abc",
        context="C",
        decision="D",
        consequences="X",
        # No rejected, no rationale
    )
    content = (tmp_project / ".shipwright" / "agent_docs" / "decision_log.md").read_text()
    assert "**Rejected:**" not in content
    assert "**Rationale:**" not in content
