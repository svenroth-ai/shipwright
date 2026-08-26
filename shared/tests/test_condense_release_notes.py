"""Tests for `condense_release_notes.py` — the tool-less, single-turn LLM
completion call that turns an extracted CHANGELOG section into release-note
prose. Every provider call is mocked; this never hits a real API.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools import condense_release_notes as crn  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_PROMPT_PATH = (
    _REPO_ROOT
    / "plugins" / "shipwright-changelog" / "skills" / "changelog"
    / "references" / "release-notes-prompt.md"
)


def test_no_api_key_skips(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = crn.condense("some section text", "1.2.3", "prompt template", project_root=tmp_path)
    assert result == {"status": "skipped", "reason": "no_api_key"}


def test_openrouter_success(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="## Highlights\n\nStuff shipped.\n"))]

    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = fake_response
        result = crn.condense("some section text", "1.2.3", "prompt template", project_root=tmp_path)

    assert result["status"] == "ok"
    assert result["via"] == "openrouter"
    assert "Highlights" in result["text"]


def test_empty_completion_reports_error(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content=""))]

    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = fake_response
        result = crn.condense("some section text", "1.2.3", "prompt template", project_root=tmp_path)

    assert result["status"] == "error"
    assert result["reason"] == "empty completion"


def test_provider_exception_reports_error_not_raise(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.side_effect = RuntimeError("boom")
        result = crn.condense("some section text", "1.2.3", "prompt template", project_root=tmp_path)

    assert result["status"] == "error"
    assert "boom" in result["reason"]


def test_call_carries_no_tool_definitions(tmp_path: Path, monkeypatch):
    """The completion call must never pass `tools=`/`functions=` — the whole
    point is that this call is structurally incapable of taking action
    (Round 2, deepseek finding: prompt injection cannot escalate to a
    tool-enabled agent because there is no tool-enabled agent here)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="## Highlights\n\nStuff.\n"))]

    with patch("openai.OpenAI") as MockClient:
        mock_create = MockClient.return_value.chat.completions.create
        mock_create.return_value = fake_response
        crn.condense("some section text", "1.2.3", "prompt template", project_root=tmp_path)

    _, kwargs = mock_create.call_args
    assert "tools" not in kwargs
    assert "functions" not in kwargs


def test_detect_provider_prefers_openrouter_over_direct(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assert crn._detect_provider() == "openrouter"


def test_detect_provider_falls_back_to_direct(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assert crn._detect_provider() == "direct"


def test_direct_provider_success(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="## Highlights\n\nStuff shipped.\n"))]

    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = fake_response
        result = crn.condense("some section text", "1.2.3", "prompt template", project_root=tmp_path)

    assert result["status"] == "ok"
    assert result["via"] == "direct"
    assert "Highlights" in result["text"]


def test_direct_provider_empty_completion_reports_error(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content=""))]

    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = fake_response
        result = crn.condense("some section text", "1.2.3", "prompt template", project_root=tmp_path)

    assert result["status"] == "error"
    assert result["reason"] == "empty completion"


def test_direct_provider_exception_reports_error_not_raise(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.side_effect = RuntimeError("boom")
        result = crn.condense("some section text", "1.2.3", "prompt template", project_root=tmp_path)

    assert result["status"] == "error"
    assert "boom" in result["reason"]


def test_openrouter_reports_missing_package_as_error(tmp_path: Path, monkeypatch):
    """If the `openai` package is ever absent, this must be a reported
    provider error, not an uncaught ImportError crashing the orchestrator."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "openai", None)

    result = crn.condense("some section text", "1.2.3", "prompt template", project_root=tmp_path)

    assert result == {"status": "error", "reason": "openai package not installed"}


def test_main_reports_missing_section_file(tmp_path: Path, capsys):
    rc = crn.main([
        "--section-file", str(tmp_path / "missing-section.md"),
        "--prompt-file", str(tmp_path / "prompt.md"),
        "--version", "1.2.3",
    ])
    assert rc == 1
    assert "section file not found" in capsys.readouterr().out


def test_main_reports_missing_prompt_file(tmp_path: Path, capsys):
    section_file = tmp_path / "section.md"
    section_file.write_text("## Highlights\n\nStuff.\n", encoding="utf-8")
    rc = crn.main([
        "--section-file", str(section_file),
        "--prompt-file", str(tmp_path / "missing-prompt.md"),
        "--version", "1.2.3",
    ])
    assert rc == 1
    assert "prompt file not found" in capsys.readouterr().out


def test_main_success_prints_condense_result(tmp_path: Path, monkeypatch, capsys):
    section_file = tmp_path / "section.md"
    section_file.write_text("## Highlights\n\nStuff shipped.\n", encoding="utf-8")
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("prompt template", encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    rc = crn.main([
        "--section-file", str(section_file),
        "--prompt-file", str(prompt_file),
        "--version", "1.2.3",
        "--project-root", str(tmp_path),
    ])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"status": "skipped", "reason": "no_api_key"}


def test_release_notes_prompt_file_exists_with_required_markers():
    """Drift guard (Round 2 finding): SKILL.md references this file by path
    — if it moves or loses its structure, the skill silently breaks at
    runtime with no test ever noticing."""
    assert _PROMPT_PATH.is_file(), f"expected prompt file at {_PROMPT_PATH}"
    text = _PROMPT_PATH.read_text(encoding="utf-8")
    for marker in ("Highlights", "Features", "Breaking Changes", "Changed", "Fixed", "Security"):
        assert marker in text, f"prompt file is missing the {marker!r} section marker"
