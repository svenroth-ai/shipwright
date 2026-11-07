"""The build phase forbids running delete code on real folders in a test (run 23, split 04).

A red-phase test of an unguarded cleanup helper ran against `.`, `backend` and `.dev-data` and removed
real folders and part of `.git`. The rule is an instruction (a human read in review), so it needs a
test that it stays stated in the skill, in the reference and in the code reviewer.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BUILD = REPO_ROOT / "plugins" / "shipwright-build"
REFERENCE = BUILD / "skills" / "build" / "references" / "safe-delete-tests.md"


def test_skill_states_the_rule_and_links_the_reference():
    text = (BUILD / "skills" / "build" / "SKILL.md").read_text(encoding="utf-8")
    assert "A red test never runs delete code on real folders" in text
    assert "safe-delete-tests.md" in text


def test_reference_names_the_incident_and_the_temp_copy_rule():
    text = REFERENCE.read_text(encoding="utf-8")
    assert "tempfile.mkdtemp()" in text
    assert "`.git`" in text and "os.getcwd()" in text


def test_code_reviewer_rejects_tests_that_delete_on_real_paths():
    text = (BUILD / "agents" / "code-reviewer.md").read_text(encoding="utf-8")
    assert "temp copy" in text and "safe-delete-tests.md" in text
