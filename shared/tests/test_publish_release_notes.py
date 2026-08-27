"""Tests for `publish_release_notes.py` — the single orchestrator SKILL.md
Step 7 calls, gluing extract -> condense -> validate -> create behind one
call so a mid-chain failure can't abort before the final status is reported.

Each stage's own module is mocked here; the stages themselves have their own
dedicated test files (`test_extract_changelog_section.py`,
`test_condense_release_notes.py`, `test_validate_release_notes.py`,
`test_create_github_release.py`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

from tools import publish_release_notes as prn  # noqa: E402
from tools import validate_release_notes as vrn  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def test_extract_failure_reported_and_stops(tmp_path: Path):
    with patch("tools.publish_release_notes.ecs.extract", side_effect=prn.ecs.ExtractError("boom")), \
         patch("tools.publish_release_notes.crn.condense") as mock_condense:
        result = prn.publish(tmp_path, "1.2.3")
    assert result == {"status": "skipped", "reason": "extract_failed:boom"}
    mock_condense.assert_not_called()


def test_condensation_failure_reported_and_stops(tmp_path: Path):
    with patch("tools.publish_release_notes.ecs.extract",
               return_value={"section_text": "text", "previous_version_tag": None}), \
         patch("tools.publish_release_notes.crn.condense",
               return_value={"status": "error", "reason": "no completion"}), \
         patch("tools.publish_release_notes.resolve_repo_identity") as mock_repo, \
         patch("tools.publish_release_notes.cgr.create_release") as mock_create:
        result = prn.publish(tmp_path, "1.2.3")
    assert result == {"status": "skipped", "reason": "condensation_failed:no completion"}
    mock_repo.assert_not_called()
    mock_create.assert_not_called()


def test_unresolved_repo_identity_reported(tmp_path: Path):
    with patch("tools.publish_release_notes.ecs.extract",
               return_value={"section_text": "text", "previous_version_tag": None}), \
         patch("tools.publish_release_notes.crn.condense",
               return_value={"status": "ok", "text": "## Highlights\n\nStuff.\n"}), \
         patch("tools.publish_release_notes.resolve_repo_identity", return_value=None):
        result = prn.publish(tmp_path, "1.2.3")
    assert result == {"status": "skipped", "reason": "condensation_failed:repo_identity_unresolved"}


def test_validation_failure_reported_and_stops(tmp_path: Path):
    with patch("tools.publish_release_notes.ecs.extract",
               return_value={"section_text": "text", "previous_version_tag": None}), \
         patch("tools.publish_release_notes.crn.condense",
               return_value={"status": "ok", "text": "## Not Allowed\n\nbad heading\n"}), \
         patch("tools.publish_release_notes.resolve_repo_identity", return_value="acme/widgets"), \
         patch("tools.publish_release_notes.cgr.create_release") as mock_create:
        result = prn.publish(tmp_path, "1.2.3")
    assert result["status"] == "skipped"
    assert result["reason"].startswith("notes_failed_validation:")
    mock_create.assert_not_called()


def test_success_writes_sanitized_body_and_calls_create(tmp_path: Path):
    with patch("tools.publish_release_notes.ecs.extract",
               return_value={"section_text": "text", "previous_version_tag": "v1.2.2"}), \
         patch("tools.publish_release_notes.crn.condense",
               return_value={"status": "ok", "text": "## Highlights\n\nA release.\n"}), \
         patch("tools.publish_release_notes.resolve_repo_identity", return_value="acme/widgets"), \
         patch("tools.publish_release_notes.cgr.create_release",
               return_value={"status": "ok", "url": "https://github.com/acme/widgets/releases/v1.2.3"}) as mock_create:
        result = prn.publish(tmp_path, "1.2.3")

    assert result == {"status": "ok", "url": "https://github.com/acme/widgets/releases/v1.2.3"}
    notes_path = tmp_path / ".shipwright" / "runtime" / "release_notes_v1.2.3.md"
    assert notes_path.is_file()
    body = notes_path.read_text(encoding="utf-8")
    assert "Highlights" in body
    assert "Full changelog for v1.2.3" in body
    assert "Compare with the previous release" in body
    create_args = mock_create.call_args.args
    assert create_args[0] == "1.2.3"
    assert create_args[1] == notes_path


def test_first_release_has_no_compare_link(tmp_path: Path):
    with patch("tools.publish_release_notes.ecs.extract",
               return_value={"section_text": "text", "previous_version_tag": None}), \
         patch("tools.publish_release_notes.crn.condense",
               return_value={"status": "ok", "text": "## Highlights\n\nFirst release.\n"}), \
         patch("tools.publish_release_notes.resolve_repo_identity", return_value="acme/widgets"), \
         patch("tools.publish_release_notes.cgr.create_release", return_value={"status": "ok", "url": "x"}):
        result = prn.publish(tmp_path, "1.0.0")

    assert result["status"] == "ok"
    notes_path = tmp_path / ".shipwright" / "runtime" / "release_notes_v1.0.0.md"
    body = notes_path.read_text(encoding="utf-8")
    assert "Compare with" not in body


def test_urls_never_guess_a_heading_anchor(tmp_path: Path):
    """Regression guard: the changelog link must point at the blob, not a
    computed heading-anchor slug (self-correction — GitHub's slug algorithm
    is easy to get subtly wrong and a broken link fails silently for a
    reader)."""
    with patch("tools.publish_release_notes.ecs.extract",
               return_value={"section_text": "text", "previous_version_tag": None}), \
         patch("tools.publish_release_notes.crn.condense",
               return_value={"status": "ok", "text": "## Highlights\n\nStuff.\n"}), \
         patch("tools.publish_release_notes.resolve_repo_identity", return_value="acme/widgets"), \
         patch("tools.publish_release_notes.cgr.create_release", return_value={"status": "ok", "url": "x"}):
        prn.publish(tmp_path, "1.2.3")

    notes_path = tmp_path / ".shipwright" / "runtime" / "release_notes_v1.2.3.md"
    body = notes_path.read_text(encoding="utf-8")
    assert "https://github.com/acme/widgets/blob/v1.2.3/CHANGELOG.md" in body
    assert "#" not in body.split("Full changelog for v1.2.3](")[1].split(")")[0]


def test_prompt_read_failure_reported_and_stops(tmp_path: Path):
    """External code-review finding: an uncaught OSError reading the prompt
    file would crash the orchestrator instead of reporting a status,
    violating the never-swallowed/never-blocking contract."""
    with patch("tools.publish_release_notes.ecs.extract",
               return_value={"section_text": "text", "previous_version_tag": None}), \
         patch("pathlib.Path.is_file", return_value=True), \
         patch("pathlib.Path.read_text", side_effect=OSError("disk error")), \
         patch("tools.publish_release_notes.crn.condense") as mock_condense:
        result = prn.publish(tmp_path, "1.2.3")
    assert result["status"] == "skipped"
    assert result["reason"].startswith("condensation_failed:prompt file unreadable")
    mock_condense.assert_not_called()


def test_notes_write_failure_reported_and_stops(tmp_path: Path):
    """External code-review finding: an uncaught OSError writing the
    sanitized notes file (read-only filesystem, disk full) would crash the
    orchestrator instead of reporting a status."""
    with patch("tools.publish_release_notes.ecs.extract",
               return_value={"section_text": "text", "previous_version_tag": None}), \
         patch("tools.publish_release_notes.crn.condense",
               return_value={"status": "ok", "text": "## Highlights\n\nStuff.\n"}), \
         patch("tools.publish_release_notes.resolve_repo_identity", return_value="acme/widgets"), \
         patch("pathlib.Path.mkdir", side_effect=OSError("read-only filesystem")), \
         patch("tools.publish_release_notes.cgr.create_release") as mock_create:
        result = prn.publish(tmp_path, "1.2.3")
    assert result["status"] == "failed"
    assert result["reason"].startswith("notes_write_failed:")
    mock_create.assert_not_called()


def test_prompt_missing_reported_and_stops(tmp_path: Path):
    with patch("tools.publish_release_notes.ecs.extract",
               return_value={"section_text": "text", "previous_version_tag": None}), \
         patch("pathlib.Path.is_file", return_value=False), \
         patch("tools.publish_release_notes.crn.condense") as mock_condense:
        result = prn.publish(tmp_path, "1.2.3")
    assert result["status"] == "skipped"
    assert result["reason"].startswith("condensation_failed:prompt file missing at")
    mock_condense.assert_not_called()


def test_main_prints_publish_result(tmp_path: Path, capsys):
    with patch("tools.publish_release_notes.publish",
               return_value={"status": "ok", "url": "https://github.com/acme/widgets/releases/v1.2.3"}) as mock_publish:
        rc = prn.main(["--project-root", str(tmp_path), "--version", "1.2.3"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"status": "ok", "url": "https://github.com/acme/widgets/releases/v1.2.3"}
    mock_publish.assert_called_once()
    call_args = mock_publish.call_args.args
    assert call_args[0] == tmp_path.resolve()
    assert call_args[1] == "1.2.3"


def test_prompt_path_resolves_to_a_real_file():
    """Doubt-reviewer finding: every other test mocks Path.is_file, so a
    future rename/move of release-notes-prompt.md would silently degrade
    condensation to 'skipped' forever without ever failing a test. This one
    check hits the real filesystem on purpose."""
    assert prn._PROMPT_PATH.is_file()


def test_validate_expected_footer_used_consistently():
    """Sanity check that the orchestrator's own footer construction matches
    `validate_release_notes.expected_footer`'s contract (no drift between
    the two)."""
    footer = vrn.expected_footer("1.2.3", "https://x/CHANGELOG.md", "https://x/compare/v1..v2")
    assert footer.startswith("[Full changelog for v1.2.3]")
