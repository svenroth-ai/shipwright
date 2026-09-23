"""AC0 combined end-to-end fixture (R2 mini-plan Step 9): both new Codex
hooks invoked back-to-back under one shared, realistic session, proving they
don't interfere with each other when no genuine Codex bundle is resolvable.
Split out of ``test_codex_hooks_noop_under_claude.py`` (bloat gate, 2026-09-22)
— that file covers the mint hook alone; this one covers both hooks together."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HOOK_SCRIPT = (
    Path(__file__).resolve().parent.parent / "scripts" / "hooks" / "codex_activation_mint.py"
)
sys.path.insert(0, str(HOOK_SCRIPT.parent))
from codex_activation_mint import handle_payload  # noqa: E402
import codex_pretooluse_gate  # noqa: E402


def _record_path(project_root: Path, session_id: str) -> Path:
    # Delegates to the real library function -- see the identical note in
    # test_codex_hooks_noop_under_claude.py (external review fix, R2).
    from lib.codex_activation_record import _record_path as _lib_record_path

    return _lib_record_path(project_root, session_id)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (
        "SHIPWRIGHT_PLUGIN_ROOT",
        "PLUGIN_ROOT",
        "CLAUDE_PLUGIN_ROOT",
        "SHIPWRIGHT_PROJECT_ROOT",
    ):
        monkeypatch.delenv(var, raising=False)


class TestAC0CombinedEndToEnd:
    """R2 mini-plan Step 9's own AC0 fixture: both new hooks invoked back-to-
    back under a shared, realistic session_id/cwd/turn sequence — not
    re-proving either hook's individually-tested no-op behavior (Step 5/6
    already did that). Both hooks early-return on `is_codex_runtime()` before
    ever reaching the record-write/record-read code path in these two cases
    (no genuine bundle is resolvable), so no record is actually produced for
    the gate to consume — this proves the two hooks don't interfere with each
    other under a shared session, not a record round-trip, matching
    iterate-spec.md's AC0 fixture requirement verbatim."""

    def _run_session(self, monkeypatch, tmp_path, prompt: str, tool_name: str, command: str | None):
        """UserPromptSubmit then PreToolUse, same session_id/cwd, under
        whatever env `monkeypatch` already set up (absent or wrong-value
        PLUGIN_ROOT). Returns the gate hook's decision."""
        monkeypatch.chdir(tmp_path)
        prompt_payload = {
            "session_id": "s1",
            "turn_id": "t1",
            "cwd": str(tmp_path),
            "prompt": prompt,
        }
        handle_payload(prompt_payload)

        tool_payload = {
            "session_id": "s1",
            "turn_id": "t2",
            "cwd": str(tmp_path),
            "tool_name": tool_name,
        }
        if command is not None:
            tool_payload["tool_input"] = {"command": command}
        return codex_pretooluse_gate.handle_payload(tool_payload)

    def test_plugin_root_absent_armed_prompt_then_wrong_tool_never_denies(self, monkeypatch, tmp_path):
        from lib.codex_envelope_grammar import compose

        envelope = compose("shipwright-iterate:iterate", {})
        decision = self._run_session(
            monkeypatch, tmp_path, envelope, "Bash", "rm -rf /"
        )
        assert decision is None  # allow — no genuine Codex bundle resolvable
        assert not _record_path(tmp_path, "s1").exists()

    def test_wrong_value_plugin_root_armed_prompt_then_wrong_tool_never_denies(
        self, monkeypatch, tmp_path
    ):
        unrelated = tmp_path / "unrelated"
        unrelated.mkdir()
        monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", str(unrelated))

        from lib.codex_envelope_grammar import compose

        envelope = compose("shipwright-iterate:iterate", {})
        decision = self._run_session(
            monkeypatch, tmp_path, envelope, "Bash", "rm -rf /"
        )
        assert decision is None  # allow — a stray real directory is not a bundle
        assert not _record_path(tmp_path, "s1").exists()
