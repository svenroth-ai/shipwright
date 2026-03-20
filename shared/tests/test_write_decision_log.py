"""Tests for decision log writer."""

from tools.write_decision_log import append_decision, get_next_adr_number


def test_get_next_adr_number_empty():
    assert get_next_adr_number("# Decision Log\n") == 1


def test_get_next_adr_number_sequential():
    content = "## ADR-001 | ...\n## ADR-002 | ...\n## ADR-003 | ...\n"
    assert get_next_adr_number(content) == 4


def test_append_decision_creates_file(tmp_project):
    number = append_decision(
        tmp_project,
        section_ref="Section 01: Setup",
        commit_hash="abc1234",
        context="Need to decide on auth approach",
        decision="Use Supabase Auth with JWT",
        consequences="Stateless, scales horizontally",
        rejected="Session cookies",
    )
    assert number == 1

    log_path = tmp_project / "agent_docs" / "decision_log.md"
    assert log_path.exists()

    content = log_path.read_text()
    assert "ADR-001" in content
    assert "Section 01: Setup" in content
    assert "abc1234" in content
    assert "Supabase Auth with JWT" in content
    assert "Session cookies" in content


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

    content = (tmp_project / "agent_docs" / "decision_log.md").read_text()
    assert "ADR-001" in content
    assert "ADR-002" in content
    assert "ADR-003" in content


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

    content = (tmp_project / "agent_docs" / "decision_log.md").read_text()
    # Both entries should be present
    assert "First" in content
    assert "Second" in content
    assert "ADR-001" in content
    assert "ADR-002" in content
