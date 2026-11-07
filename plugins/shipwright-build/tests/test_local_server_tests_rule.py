"""Build rules for local servers from run 27: free port, listen queue, one page-load burst test."""

from __future__ import annotations

from pathlib import Path

BUILD = Path(__file__).resolve().parents[1]
REFERENCE = BUILD / "skills" / "build" / "references" / "local-server-tests.md"


def test_reference_states_the_three_rules():
    text = REFERENCE.read_text(encoding="utf-8")
    assert "binds port `0`" in text
    assert "request_queue_size" in text
    assert "burst test" in text


def test_tdd_tests_and_code_reviewer_point_at_it():
    tdd = (BUILD / "skills" / "build" / "references" / "tdd-tests.md").read_text(encoding="utf-8")
    reviewer = (BUILD / "agents" / "code-reviewer.md").read_text(encoding="utf-8")
    assert "local-server-tests.md" in tdd
    assert "local-server-tests.md" in reviewer and "listen queue" in reviewer
