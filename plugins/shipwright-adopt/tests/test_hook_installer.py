"""Unit tests for hook_installer.install_suggest_iterate_hook."""

import json
from pathlib import Path

from lib.hook_installer import install_suggest_iterate_hook


def test_creates_settings_file_if_missing(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    result = install_suggest_iterate_hook(settings)
    assert result["installed"] is True
    assert result["created_file"] is True
    data = json.loads(settings.read_text(encoding="utf-8"))
    hooks = data["hooks"]["UserPromptSubmit"]
    assert len(hooks) == 1
    # Canonical Claude Code shape: matcher group with inner "hooks" array.
    assert "suggest_iterate.py" in hooks[0]["hooks"][0]["command"]
    assert hooks[0]["hooks"][0]["type"] == "command"


def test_idempotent_on_second_call(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    install_suggest_iterate_hook(settings)
    result2 = install_suggest_iterate_hook(settings)
    assert result2["installed"] is False
    assert result2["already_present"] is True
    # Still only one hook entry
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert len(data["hooks"]["UserPromptSubmit"]) == 1


def test_preserves_existing_unrelated_hooks(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({
        "hooks": {
            "UserPromptSubmit": [{
                "hooks": [{"type": "command", "command": "some-other-hook.py"}],
            }],
            "SessionStart": [{
                "hooks": [{"type": "command", "command": "xyz.py"}],
            }],
        }
    }))
    result = install_suggest_iterate_hook(settings)
    assert result["installed"] is True
    data = json.loads(settings.read_text(encoding="utf-8"))
    ups = data["hooks"]["UserPromptSubmit"]
    assert len(ups) == 2
    # SessionStart unchanged
    assert data["hooks"]["SessionStart"][0]["hooks"][0]["command"] == "xyz.py"


def test_detects_legacy_plugin_root_syntax(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({
        "hooks": {
            "UserPromptSubmit": [{
                "hooks": [{
                    "type": "command",
                    "command": "uv run {plugin_root}/../../shared/scripts/hooks/suggest_iterate.py",
                }],
            }]
        }
    }))
    result = install_suggest_iterate_hook(settings)
    assert result["already_present"] is True


def test_detects_legacy_shape_a_install(tmp_path: Path) -> None:
    """Backward compat: pre-fix installs wrote Shape A directly. Reader
    must still detect them so re-running install is idempotent on
    upgraded systems."""
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({
        "hooks": {
            "UserPromptSubmit": [{
                "type": "command",
                "command": "uv run ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/suggest_iterate.py",
            }]
        }
    }))
    result = install_suggest_iterate_hook(settings)
    assert result["already_present"] is True
