"""Tests for the P4.1 Skill Bootstrap Pack (SP2 + SP4).

SP2 — session_start_using_shipwright.py (SessionStart bootstrap inject):
    - run config present -> emits additionalContext routing to /shipwright-iterate
    - run config absent   -> silent (non-Shipwright project, no false trigger)
    - once-per-session dedup (the hook fires in all 12 plugins)

SP4 — mark_plugin_edit.py (PostToolUse) + plugin_sync_reminder_on_stop.py (Stop):
    - plugin-side edit -> marker written; non-plugin-side / non-Shipwright -> not
    - Stop with marker -> block-once reminder (update-marketplace.sh +
      check_plugin_cache_sync.py) + triage item; second Stop -> silent

Registry meta-test (analog to test_hook_registry_bloat.py, ADR-044):
    - forward: all 12 plugins register the 3 hooks exactly once
    - reverse: the 3 referenced scripts exist on disk
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts" / "hooks"))

import mark_plugin_edit as mpe  # noqa: E402
import plugin_sync_reminder_on_stop as reminder  # noqa: E402
import session_start_using_shipwright as boot  # noqa: E402

_PROMPTS_DIR = _REPO_ROOT / "shared" / "prompts"
_PLUGINS_DIR = _REPO_ROOT / "plugins"


def _make_project(tmp_path: Path, *, shipwright: bool, monorepo: bool = False) -> Path:
    if shipwright:
        (tmp_path / "shipwright_run_config.json").write_text(
            json.dumps({"status": "complete", "schemaVersion": 2}), encoding="utf-8"
        )
    if monorepo:
        # The Shipwright plugin-dev monorepo marker that gates SP4.
        sync = tmp_path / "scripts" / "update-marketplace.sh"
        sync.parent.mkdir(parents=True, exist_ok=True)
        sync.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------- #
# SP2 — SessionStart bootstrap
# --------------------------------------------------------------------------- #

def test_bootstrap_emits_iterate_routing(tmp_path: Path):
    root = _make_project(tmp_path, shipwright=True)
    out = boot.run(project_root=root, session_id="sid-A", prompts_dir=_PROMPTS_DIR)
    assert out, "expected additionalContext on a Shipwright project"
    payload = json.loads(out)
    ctx = payload["hookSpecificOutput"]["additionalContext"]
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "/shipwright-iterate" in ctx


def test_bootstrap_silent_without_run_config(tmp_path: Path):
    root = _make_project(tmp_path, shipwright=False)
    out = boot.run(project_root=root, session_id="sid-B", prompts_dir=_PROMPTS_DIR)
    assert out == "", "must stay silent in a non-Shipwright project"


def test_bootstrap_dedups_within_session(tmp_path: Path):
    root = _make_project(tmp_path, shipwright=True)
    first = boot.run(project_root=root, session_id="sid-C", prompts_dir=_PROMPTS_DIR)
    second = boot.run(project_root=root, session_id="sid-C", prompts_dir=_PROMPTS_DIR)
    assert first and second == "", "second fire in same session must be silent"
    # A different session id is not deduped.
    other = boot.run(project_root=root, session_id="sid-D", prompts_dir=_PROMPTS_DIR)
    assert other, "a new session id must re-emit"


def test_bootstrap_silent_when_prompt_missing(tmp_path: Path):
    root = _make_project(tmp_path, shipwright=True)
    out = boot.run(project_root=root, session_id="sid-E", prompts_dir=tmp_path / "nope")
    assert out == "", "missing prompt file fails open (silent)"


def test_main_keys_dedup_off_payload_session_id(tmp_path, monkeypatch, capsys):
    """Regression: SHIPWRIGHT_SESSION_ID is unset in sibling SessionStart hook
    processes, so main() MUST take the session id from the stdin payload — else
    the sentinel never rotates and only the first session ever gets bootstrapped.
    """
    root = _make_project(tmp_path, shipwright=True)
    monkeypatch.chdir(root)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_PROJECT_ROOT", raising=False)

    def _fire(sid: str) -> str:
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"session_id": sid})))
        boot.main()
        return capsys.readouterr().out

    assert "/shipwright-iterate" in _fire("payload-1")     # session 1 emits
    assert _fire("payload-1").strip() == ""                # same session deduped
    assert "/shipwright-iterate" in _fire("payload-2")     # new session re-emits


# --------------------------------------------------------------------------- #
# SP4 — plugin-side edit detection
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "rel,expected",
    [
        ("plugins/shipwright-build/skills/build/SKILL.md", True),
        ("plugins/shipwright-iterate/scripts/lib/x.py", True),
        ("shared/scripts/hooks/foo.py", True),
        ("shared/prompts/using-shipwright.md", True),
        ("shared/tests/test_x.py", False),
        ("docs/guide.md", False),
        ("README.md", False),
        ("some/deep/path/SKILL.md", True),
    ],
)
def test_is_plugin_side(rel: str, expected: bool):
    assert mpe.is_plugin_side(rel) is expected


def test_mark_records_plugin_side_edit(tmp_path: Path):
    root = _make_project(tmp_path, shipwright=True, monorepo=True)
    fp = str(root / "plugins" / "shipwright-build" / "skills" / "build" / "SKILL.md")
    assert mpe.run(project_root=root, session_id="sid-1", file_path=fp) is True
    paths = mpe.read_paths(root, "sid-1")
    assert "plugins/shipwright-build/skills/build/SKILL.md" in paths


def test_mark_ignores_non_plugin_side(tmp_path: Path):
    root = _make_project(tmp_path, shipwright=True, monorepo=True)
    fp = str(root / "docs" / "guide.md")
    assert mpe.run(project_root=root, session_id="sid-2", file_path=fp) is False
    assert mpe.read_paths(root, "sid-2") == []


def test_mark_ignores_end_user_project(tmp_path: Path):
    # Managed end-user project (has run_config) but NOT the plugin-dev monorepo.
    root = _make_project(tmp_path, shipwright=True, monorepo=False)
    fp = str(root / "plugins" / "shipwright-build" / "skills" / "build" / "SKILL.md")
    assert mpe.run(project_root=root, session_id="sid-3", file_path=fp) is False


def test_relativize_rejects_traversal(tmp_path: Path):
    root = _make_project(tmp_path, shipwright=True, monorepo=True)
    fp = str(root / "plugins" / ".." / ".." / "escape" / "SKILL.md")
    assert mpe.run(project_root=root, session_id="sid-esc", file_path=fp) is False


# --------------------------------------------------------------------------- #
# SP4 — Stop reminder (block-once + triage)
# --------------------------------------------------------------------------- #

def test_reminder_silent_without_marker(tmp_path: Path):
    root = _make_project(tmp_path, shipwright=True, monorepo=True)
    assert reminder.run(project_root=root, session_id="sid-X") == ""


def test_reminder_silent_in_end_user_project(tmp_path: Path):
    # Even with a pending marker, a non-monorepo project must not block.
    root = _make_project(tmp_path, shipwright=True, monorepo=False)
    mpe.add_path(root, "sid-EU", "plugins/x/skills/y/SKILL.md")
    assert reminder.run(project_root=root, session_id="sid-EU") == ""


def test_reminder_blocks_once_and_emits_triage(tmp_path: Path):
    root = _make_project(tmp_path, shipwright=True, monorepo=True)
    mpe.add_path(root, "sid-Y", "plugins/shipwright-build/skills/build/SKILL.md")

    out = reminder.run(project_root=root, session_id="sid-Y")
    assert out, "first Stop with a pending plugin edit must surface the reminder"
    payload = json.loads(out)
    assert payload["decision"] == "block"
    assert "update-marketplace.sh" in payload["reason"]
    assert "check_plugin_cache_sync.py" in payload["reason"]

    # Triage item appended (durable follow-up). triage.jsonl is compact JSON,
    # so assert on the value substring rather than a spaced key:value form.
    triage = (root / ".shipwright" / "triage.jsonl").read_text(encoding="utf-8")
    assert "plugin-sync" in triage

    # Block-once: a second Stop in the same session is silent (no hard loop).
    assert reminder.run(project_root=root, session_id="sid-Y") == ""


def test_reminder_build_text_mentions_both_commands():
    text = reminder.build_reminder(["plugins/shipwright-build/skills/build/SKILL.md"])
    assert "update-marketplace.sh" in text and "check_plugin_cache_sync.py" in text


# --------------------------------------------------------------------------- #
# Prompt content
# --------------------------------------------------------------------------- #

def test_using_shipwright_prompt_routes_phases():
    text = (_PROMPTS_DIR / "using-shipwright.md").read_text(encoding="utf-8")
    assert "/shipwright-iterate" in text
    assert "/shipwright-compliance" in text


def test_writing_plugin_prompt_has_sync_gate():
    text = (_PROMPTS_DIR / "writing-plugin.md").read_text(encoding="utf-8")
    assert "update-marketplace.sh" in text
    assert "check_plugin_cache_sync.py" in text


# --------------------------------------------------------------------------- #
# Registry meta-test (acceptance #4) — analog to test_hook_registry_bloat.py
# --------------------------------------------------------------------------- #

def _plugins() -> list[Path]:
    return sorted(
        p for p in _PLUGINS_DIR.iterdir() if (p / "hooks" / "hooks.json").is_file()
    )


def _commands(doc: dict, event: str) -> list[str]:
    out: list[str] = []
    for block in doc.get("hooks", {}).get(event, []):
        if isinstance(block, dict):
            out.extend(
                h.get("command", "") for h in block.get("hooks", []) if isinstance(h, dict)
            )
    return out


def _load(plugin: Path) -> dict:
    return json.loads((plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("plugin", _plugins(), ids=lambda p: p.name)
def test_registers_sessionstart_bootstrap(plugin: Path):
    hits = [c for c in _commands(_load(plugin), "SessionStart")
            if "session_start_using_shipwright.py" in c]
    assert len(hits) == 1, f"{plugin.name}: expected exactly one bootstrap SessionStart hook"


@pytest.mark.parametrize("plugin", _plugins(), ids=lambda p: p.name)
def test_registers_mark_plugin_edit(plugin: Path):
    doc = _load(plugin)
    found = []
    for block in doc.get("hooks", {}).get("PostToolUse", []):
        matcher = block.get("matcher", "") if isinstance(block, dict) else ""
        for h in block.get("hooks", []) if isinstance(block, dict) else []:
            if "mark_plugin_edit.py" in h.get("command", ""):
                assert "Write" in matcher and "Edit" in matcher, (
                    f"{plugin.name}: mark_plugin_edit matcher must include Write|Edit"
                )
                found.append(h)
    assert len(found) == 1, f"{plugin.name}: expected exactly one mark_plugin_edit hook"


@pytest.mark.parametrize("plugin", _plugins(), ids=lambda p: p.name)
def test_registers_stop_reminder(plugin: Path):
    hits = [c for c in _commands(_load(plugin), "Stop")
            if "plugin_sync_reminder_on_stop.py" in c]
    assert len(hits) == 1, f"{plugin.name}: expected exactly one Stop reminder hook"


def test_referenced_hook_scripts_exist():
    hooks = _REPO_ROOT / "shared" / "scripts" / "hooks"
    assert (hooks / "session_start_using_shipwright.py").is_file()
    assert (hooks / "mark_plugin_edit.py").is_file()
    assert (hooks / "plugin_sync_reminder_on_stop.py").is_file()
