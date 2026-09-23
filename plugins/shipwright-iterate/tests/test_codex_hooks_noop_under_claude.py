"""Tests for ``codex_activation_mint.py`` (R2 — AC0, AC1a mint half).

Direct-import convention mirrors ``test_suggest_iterate.py``: insert the
hook's own directory on ``sys.path`` and import its functions directly
rather than spawning a subprocess, so ``is_codex_runtime()``'s env-var/
bundle-shape fixtures can be set up precisely per test.

AC0's actual claim: both new hooks, invoked without a genuine Codex bundle
resolvable (``PLUGIN_ROOT``-family env vars absent, or pointing at an
unrelated real directory), never touch activation-record state — this file
covers the ``UserPromptSubmit`` mint hook's half of that claim; the
``PreToolUse`` gate hook's half is Step 6's own test file."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

HOOK_SCRIPT = (
    Path(__file__).resolve().parent.parent / "scripts" / "hooks" / "codex_activation_mint.py"
)
sys.path.insert(0, str(HOOK_SCRIPT.parent))
import codex_activation_mint  # noqa: E402
from codex_activation_mint import handle_payload  # noqa: E402


def _make_bundle(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "BUILD_MANIFEST.json").write_text(
        json.dumps({"version": "0.0.0-test", "files": {"plugin.json": "0" * 64}}),
        encoding="utf-8",
    )
    codex_plugin_dir = root / ".codex-plugin"
    codex_plugin_dir.mkdir(parents=True, exist_ok=True)
    (codex_plugin_dir / "plugin.json").write_text(
        json.dumps({"hooks": {"hooks": {}}}), encoding="utf-8"
    )


def _record_path(project_root: Path, session_id: str) -> Path:
    return project_root / ".shipwright" / "runtime" / "codex-activation" / f"{session_id}.json"


def _make_project(root: Path) -> None:
    """Marks *root* as a Shipwright project (``is_shipwright_project``'s
    config-marker arm) -- required since the HIGH project-boundary guard
    (code review) so fixtures anchored on a bare ``tmp_path`` still resolve
    as in-scope."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "shipwright_run_config.json").write_text("{}", encoding="utf-8")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (
        "SHIPWRIGHT_PLUGIN_ROOT",
        "PLUGIN_ROOT",
        "CLAUDE_PLUGIN_ROOT",
        "SHIPWRIGHT_PROJECT_ROOT",
    ):
        monkeypatch.delenv(var, raising=False)


class TestAC0NoOpUnderClaude:
    def test_no_op_when_plugin_root_not_set(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        payload = {"session_id": "s1", "turn_id": "t1", "cwd": str(tmp_path), "prompt": "hello"}
        handle_payload(payload)
        assert not _record_path(tmp_path, "s1").exists()

    def test_no_op_with_wrong_value_plugin_root(self, monkeypatch, tmp_path):
        """A stray/unrelated ``PLUGIN_ROOT`` value (a real directory, not a
        genuine bundle) must still no-op — external review's 'wrong-value'
        case. Already proven at ``codex_runtime``'s own unit level; this
        proves the hook actually calls ``is_codex_runtime()`` rather than a
        bare env-var-presence check of its own."""
        monkeypatch.chdir(tmp_path)
        unrelated = tmp_path / "unrelated"
        unrelated.mkdir()
        monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", str(unrelated))
        payload = {"session_id": "s1", "turn_id": "t1", "cwd": str(tmp_path), "prompt": "hello"}
        handle_payload(payload)
        assert not _record_path(tmp_path, "s1").exists()

    def test_no_op_when_session_id_absent(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        bundle = tmp_path / "bundle"
        _make_bundle(bundle)
        monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", str(bundle))
        payload = {"cwd": str(tmp_path), "prompt": "hello"}
        handle_payload(payload)  # must not raise
        assert not (tmp_path / ".shipwright" / "runtime" / "codex-activation").exists()

    def test_main_never_raises_on_garbage_stdin(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
        assert codex_activation_mint.main() == 0

    def test_main_never_raises_on_non_dict_json(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO("[1, 2, 3]"))
        assert codex_activation_mint.main() == 0


class TestMalformedPayloadFields:
    """Code review MEDIUM: ``handle_payload()``'s own docstring claimed
    'never raises', but a non-string ``session_id``/``cwd`` previously
    reached ``mint()``/``normalize_cwd()`` directly (``AttributeError`` /
    ``TypeError``), masked only by ``main()``'s unrelated blanket
    ``except``. These call ``handle_payload()`` directly (not ``main()``)
    so a regression here fails loudly instead of being re-masked."""

    def test_non_string_session_id_does_not_raise(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        bundle = tmp_path / "bundle"
        _make_bundle(bundle)
        monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", str(bundle))
        payload = {"session_id": 12345, "turn_id": "t1", "cwd": str(tmp_path), "prompt": "hello"}
        handle_payload(payload)
        assert not (tmp_path / ".shipwright" / "runtime" / "codex-activation").exists()

    def test_non_string_cwd_does_not_raise(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        bundle = tmp_path / "bundle"
        _make_bundle(bundle)
        monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", str(bundle))
        payload = {
            "session_id": "s1",
            "turn_id": "t1",
            "cwd": ["not", "a", "string"],
            "prompt": "hello",
        }
        handle_payload(payload)
        assert not _record_path(tmp_path, "s1").exists()

    def test_none_cwd_does_not_raise(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        bundle = tmp_path / "bundle"
        _make_bundle(bundle)
        monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", str(bundle))
        payload = {"session_id": "s1", "turn_id": "t1", "cwd": None, "prompt": "hello"}
        handle_payload(payload)
        assert not _record_path(tmp_path, "s1").exists()


class TestArmedBranches:
    def test_armed_when_grammar_matches(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        bundle = tmp_path / "bundle"
        _make_bundle(bundle)
        _make_project(tmp_path)
        monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", str(bundle))

        from lib.codex_envelope_grammar import compose

        envelope_text = compose("shipwright-iterate:iterate", {"foo": "bar"})
        payload = {
            "session_id": "s1",
            "turn_id": "t1",
            "cwd": str(tmp_path),
            "prompt": envelope_text,
        }
        handle_payload(payload)

        path = _record_path(tmp_path, "s1")
        assert path.exists()
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["armed"] is True
        assert record["skill_id"] == "shipwright-iterate:iterate"
        assert record["args"] == {"foo": "bar"}

    def test_unarmed_when_grammar_does_not_match(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        bundle = tmp_path / "bundle"
        _make_bundle(bundle)
        _make_project(tmp_path)
        monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", str(bundle))

        payload = {
            "session_id": "s1",
            "turn_id": "t1",
            "cwd": str(tmp_path),
            "prompt": "just an ordinary first message, no envelope here",
        }
        handle_payload(payload)

        path = _record_path(tmp_path, "s1")
        assert path.exists()
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["armed"] is False
        assert record["skill_id"] is None
        assert record["args"] is None

    def test_unarmed_when_envelope_names_an_unaccepted_skill_id(self, monkeypatch, tmp_path):
        # external review, openai medium: a syntactically valid envelope for
        # a DIFFERENT skill must not arm this iterate-only gate.
        monkeypatch.chdir(tmp_path)
        bundle = tmp_path / "bundle"
        _make_bundle(bundle)
        _make_project(tmp_path)
        monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", str(bundle))

        from lib.codex_envelope_grammar import compose

        envelope_text = compose("some-other-plugin:some-skill", {})
        payload = {
            "session_id": "s1",
            "turn_id": "t1",
            "cwd": str(tmp_path),
            "prompt": envelope_text,
        }
        handle_payload(payload)

        path = _record_path(tmp_path, "s1")
        assert path.exists()
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["armed"] is False
        assert record["skill_id"] is None


class TestSecondPromptNeverOverwrites:
    def test_second_call_does_not_change_first_verdict(self, monkeypatch, tmp_path):
        """Wiring test, not re-proving Step 4's library: the hook itself
        must not do anything (e.g. delete-then-remint) that would defeat
        ``mint()``'s own exclusive-create guarantee."""
        monkeypatch.chdir(tmp_path)
        bundle = tmp_path / "bundle"
        _make_bundle(bundle)
        _make_project(tmp_path)
        monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", str(bundle))

        from lib.codex_envelope_grammar import compose

        first_payload = {
            "session_id": "s1",
            "turn_id": "t1",
            "cwd": str(tmp_path),
            "prompt": "ordinary first message, unarmed",
        }
        handle_payload(first_payload)

        second_prompt = compose("shipwright-iterate:iterate", {})
        second_payload = {
            "session_id": "s1",
            "turn_id": "t2",
            "cwd": str(tmp_path),
            "prompt": second_prompt,
        }
        handle_payload(second_payload)

        path = _record_path(tmp_path, "s1")
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["armed"] is False  # first verdict, not overwritten by the second (armed) prompt
        assert record["turn_id"] == "t1"  # first mint's turn_id, unchanged


