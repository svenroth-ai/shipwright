"""Unit tests for hook_installer.install_suggest_iterate_hook."""

import json
from pathlib import Path

import pytest

from lib.hook_installer import _HOOK_COMMAND, install_suggest_iterate_hook

# Canonical command literal that the installer must emit and that any
# legacy form must be rewritten to. Asserting against the imported
# constant (rather than a duplicated string) makes the contract
# unambiguous: tests fail loudly if either the constant or its expected
# shape changes.
CANONICAL = (
    'uv run --no-project '
    '"${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/suggest_iterate.py"'
)

# Six known legacy command literals that pre-fix installs of this
# module (or pre-fix copy-paste from the SKILL.md docs) wrote into the
# wild. Re-running install must upgrade each in place to CANONICAL —
# both Shape A and Shape B carriers.
_LEGACY_COMMANDS = [
    pytest.param(
        "uv run ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/suggest_iterate.py",
        id="unquoted-CLAUDE_PLUGIN_ROOT",
    ),
    pytest.param(
        "uv run {plugin_root}/../../shared/scripts/hooks/suggest_iterate.py",
        id="unquoted-legacy-plugin_root",
    ),
    pytest.param(
        "uv run --no-project ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/suggest_iterate.py",
        id="no-project-but-unquoted-CLAUDE_PLUGIN_ROOT",
    ),
    pytest.param(
        "uv run --no-project {plugin_root}/../../shared/scripts/hooks/suggest_iterate.py",
        id="no-project-but-unquoted-legacy-plugin_root",
    ),
    pytest.param(
        'uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/suggest_iterate.py"',
        id="quoted-no-no-project-CLAUDE_PLUGIN_ROOT",
    ),
    pytest.param(
        'uv run "{plugin_root}/../../shared/scripts/hooks/suggest_iterate.py"',
        id="quoted-no-no-project-legacy-plugin_root",
    ),
]


# ---- Sven's Shape B install tests (kept verbatim from origin/main) -------

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


# ---- AC-1: fresh install emits canonical quoted + --no-project ----------

def test_installer_emits_quoted_command_with_no_project(tmp_path: Path) -> None:
    """AC-1: fresh install emits a hook command whose path is quoted and
    runs uv with --no-project, so that target projects on paths
    containing spaces (OneDrive-synced folders) do not break
    UserPromptSubmit and corrupt project .venv files cannot stall uv on
    resolution.

    Asserts equality with the canonical form rather than substring
    presence — substring asserts let an implementation with extra args,
    wrong order, or both forms concatenated still pass.
    """
    settings = tmp_path / ".claude" / "settings.json"
    install_suggest_iterate_hook(settings)
    data = json.loads(settings.read_text(encoding="utf-8"))
    cmd = data["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert cmd == CANONICAL, (
        f"installed command must equal the canonical quoted + --no-project "
        f"form so paths with spaces don't word-split and uv doesn't stall "
        f"on a corrupt project .venv — got: {cmd!r}"
    )
    # Belt-and-braces: the constant the installer emits and the constant
    # this test asserts against must remain in sync.
    assert _HOOK_COMMAND == CANONICAL


# ---- AC-2 + AC-3: upgrade-in-place across legacy forms (Shape B carrier) -

@pytest.mark.parametrize("legacy_command", _LEGACY_COMMANDS)
def test_installer_upgrades_legacy_unquoted_entry_in_place_shape_b(
    tmp_path: Path, legacy_command: str
) -> None:
    """AC-2 + AC-3 (Shape B carrier): a project whose
    .claude/settings.json already contains a Shape B entry whose command
    is any of the known legacy forms must be:

      1. recognized as already-present (no duplicate row appended), and
      2. have its inner sub.command REWRITTEN to the canonical quoted +
         --no-project form so the next user prompt actually survives
         paths with spaces.

    Without (2), an already-adopted project on a path with spaces stays
    blocked even after re-running /shipwright-adopt — defeating the
    point of this iterate. The carrier shape stays Shape B.
    """
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({
        "hooks": {
            "UserPromptSubmit": [{
                "hooks": [{"type": "command", "command": legacy_command}],
            }]
        }
    }))
    result = install_suggest_iterate_hook(settings)
    assert result["already_present"] is True
    assert result["upgraded"] is True, (
        f"legacy form must be flagged as upgraded so callers/telemetry "
        f"can surface that re-running adopt actually fixed something: "
        f"{legacy_command!r}"
    )
    data = json.loads(settings.read_text(encoding="utf-8"))
    rows = data["hooks"]["UserPromptSubmit"]
    assert len(rows) == 1, (
        f"installer appended a duplicate row instead of upgrading legacy "
        f"form: {legacy_command!r}"
    )
    inner = rows[0]["hooks"]
    assert len(inner) == 1
    assert inner[0]["command"] == CANONICAL, (
        f"legacy form must be rewritten in place to the canonical quoted "
        f"+ --no-project command so the hook stops blocking prompts on "
        f"paths with spaces — input: {legacy_command!r}, "
        f"got: {inner[0]['command']!r}"
    )


# ---- AC-2 + AC-3 + ADR-019 carry-over: Shape A entries upgrade to Shape B

@pytest.mark.parametrize("legacy_command", _LEGACY_COMMANDS)
def test_installer_upgrades_legacy_shape_a_entry_to_shape_b(
    tmp_path: Path, legacy_command: str
) -> None:
    """AC-2 + AC-3 + ADR-019 carry-over: a project whose
    .claude/settings.json contains a *Shape A* (bare {type, command})
    entry — which any pre-ADR-019 install of this module produced —
    must be CONVERTED to a canonical Shape B entry on re-run, AND have
    its command rewritten to CANONICAL. Both pieces matter: Claude Code
    rejects Shape A entirely (ADR-019), and an unquoted command breaks
    on paths with spaces (ADR-020). Recognizing without rewriting either
    one leaves the project broken.
    """
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({
        "hooks": {
            "UserPromptSubmit": [
                {"type": "command", "command": legacy_command}
            ]
        }
    }))
    result = install_suggest_iterate_hook(settings)
    assert result["already_present"] is True
    assert result["upgraded"] is True
    data = json.loads(settings.read_text(encoding="utf-8"))
    rows = data["hooks"]["UserPromptSubmit"]
    assert len(rows) == 1
    # Shape upgraded A -> B:
    assert "command" not in rows[0], (
        f"legacy Shape A entry must be replaced (not retained alongside "
        f"a new Shape B). Claude Code rejects Shape A. Got: {rows[0]!r}"
    )
    assert "hooks" in rows[0]
    assert rows[0]["hooks"][0]["command"] == CANONICAL


def test_installer_upgrades_shape_a_canonical_command_to_shape_b(
    tmp_path: Path,
) -> None:
    """Edge case from Sven's ADR-019: a Shape A entry that already
    happens to carry the CANONICAL command literal still has the wrong
    shape (Claude Code rejects it). Re-running install must convert
    that entry to Shape B and report upgraded=True even though the
    command literal was already canonical."""
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({
        "hooks": {
            "UserPromptSubmit": [{"type": "command", "command": CANONICAL}]
        }
    }))
    result = install_suggest_iterate_hook(settings)
    assert result["already_present"] is True
    assert result["upgraded"] is True
    data = json.loads(settings.read_text(encoding="utf-8"))
    rows = data["hooks"]["UserPromptSubmit"]
    assert len(rows) == 1
    assert "command" not in rows[0]
    assert rows[0]["hooks"][0]["command"] == CANONICAL


def test_installer_idempotent_returns_upgraded_false_when_already_canonical(
    tmp_path: Path,
) -> None:
    """Second-run sanity: when the canonical form is already in place
    (correct Shape B + canonical command), the installer returns
    upgraded=False AND does not rewrite the file. Distinguishes
    'already correct' from 'just upgraded'.

    The no-rewrite check compares file bytes before/after rather than
    mtime — mtime is too weak (passes whether the file was rewritten
    with the same content or not, and Windows mtime granularity makes
    it doubly unreliable).
    """
    settings = tmp_path / ".claude" / "settings.json"
    install_suggest_iterate_hook(settings)  # Fresh install
    bytes_before = settings.read_bytes()
    result = install_suggest_iterate_hook(settings)  # Second run
    bytes_after = settings.read_bytes()
    assert result["already_present"] is True
    assert result["upgraded"] is False, (
        "no-op re-run on already-canonical entry must report upgraded=False"
    )
    # File must not have been rewritten — byte-identical content. (A
    # gratuitous rewrite would also work functionally, but it dirties
    # mtime and trips file watchers / git diffs in target projects.)
    assert bytes_after == bytes_before, (
        "no-op re-run rewrote settings.json despite no upgrade "
        "needed — installer must skip the write_text call when "
        "the canonical form is already in place"
    )


# ---- Backward-compat aliases retained from origin/main test file --------

def test_detects_legacy_plugin_root_syntax(tmp_path: Path) -> None:
    """Original Shape B carrier with the {plugin_root} alias — kept as
    a smoke test of the alias-recognition path even though
    test_installer_upgrades_legacy_unquoted_entry_in_place_shape_b
    parametrized it explicitly."""
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
    """Backward compat (Sven's regression): pre-fix installs wrote
    Shape A directly with the unquoted ${CLAUDE_PLUGIN_ROOT} command.
    Reader must still detect them so re-running install is
    idempotent — and (since this iterate) upgrade them in place."""
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
