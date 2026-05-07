"""Plugin-level hook registration tests for suggest_iterate.

Replaces the retired ``plugins/shipwright-adopt/tests/test_hook_installer.py``
suite. Covers AC-1, AC-11, and AC-13 of
``.shipwright/planning/iterate/2026-05-05-plugin-hook-registration.md``.

The premise of this iterate: ``suggest_iterate.py`` is registered in
``plugins/shipwright-iterate/hooks/hooks.json`` under
``UserPromptSubmit`` — *not* installed per-project into
``.claude/settings.json`` by an installer module. The ``${CLAUDE_PLUGIN_ROOT}``
variable expands correctly only inside plugin-context hooks; project-level
settings.json triggers a hard Claude Code error
("hook is not associated with a plugin").
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PLUGIN_HOOKS_JSON = (
    _REPO_ROOT / "plugins" / "shipwright-iterate" / "hooks" / "hooks.json"
)
_SUGGEST_ITERATE = (
    _REPO_ROOT / "shared" / "scripts" / "hooks" / "suggest_iterate.py"
)
_CLASSIFY_INTENT = (
    _REPO_ROOT
    / "plugins"
    / "shipwright-iterate"
    / "scripts"
    / "lib"
    / "classify_intent.py"
)

# Canonical command literal — must match exactly. ADR-019 mandates Shape B,
# ADR-020 mandates double-quoted path + ``--no-project``.
_CANONICAL_COMMAND = (
    'uv run --no-project '
    '"${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/suggest_iterate.py"'
)


def _load_hooks_json() -> dict:
    """Return the event-name → matcher-list mapping for the
    shipwright-iterate plugin, transparently unwrapping the Claude
    Code 2.1.132+ top-level ``hooks`` key (ADR-039). The wrapper
    invariant itself is asserted in
    ``shared/tests/test_hooks_json_wrapper.py`` — duplicating it here
    would just produce noisier failures, so we tolerate either shape."""
    raw = json.loads(_PLUGIN_HOOKS_JSON.read_text(encoding="utf-8"))
    inner = raw.get("hooks")
    return inner if isinstance(inner, dict) else raw


def test_user_prompt_submit_entry_exists():
    """AC-1: plugin hooks.json registers a UserPromptSubmit entry."""
    data = _load_hooks_json()
    assert "UserPromptSubmit" in data, (
        "shipwright-iterate plugin hooks.json must register suggest_iterate "
        "under UserPromptSubmit. The project-level installer model was retired "
        "in iterate-20260505-plugin-hook-registration."
    )
    entries = data["UserPromptSubmit"]
    assert isinstance(entries, list) and entries, (
        "UserPromptSubmit must be a non-empty list of matcher groups (Shape B)."
    )


def test_user_prompt_submit_uses_canonical_command():
    """AC-1: inner command literal must equal the canonical Shape B form."""
    data = _load_hooks_json()
    entries = data["UserPromptSubmit"]

    found_commands: list[str] = []
    for matcher in entries:
        assert isinstance(matcher, dict), (
            "Each UserPromptSubmit entry must be a Shape B matcher group "
            "(dict with 'hooks' list), not a bare {type, command} entry "
            "(Shape A is rejected by Claude Code per ADR-019)."
        )
        assert "command" not in matcher or "hooks" in matcher, (
            "Shape A bare command at top level is rejected by Claude Code."
        )
        for sub in matcher.get("hooks", []):
            if isinstance(sub, dict) and sub.get("command"):
                found_commands.append(sub["command"])

    assert _CANONICAL_COMMAND in found_commands, (
        f"Plugin hooks.json must register the canonical suggest_iterate "
        f"command. Expected: {_CANONICAL_COMMAND!r}. Found: {found_commands!r}."
    )


def test_no_unquoted_plugin_root_in_any_hook_command():
    """Drift guard: every hook command in shipwright-iterate quotes
    ${CLAUDE_PLUGIN_ROOT} per ADR-022 — same risk class as the bug
    this iterate fixes (paths with spaces would word-split)."""
    data = _load_hooks_json()
    for event_name, entries in data.items():
        for matcher in entries:
            if not isinstance(matcher, dict):
                continue
            for sub in matcher.get("hooks", []):
                cmd = sub.get("command", "") if isinstance(sub, dict) else ""
                if "${CLAUDE_PLUGIN_ROOT}" in cmd:
                    assert '"${CLAUDE_PLUGIN_ROOT}' in cmd, (
                        f"hook command in {event_name} must wrap "
                        f"${{CLAUDE_PLUGIN_ROOT}} in double quotes (ADR-022): "
                        f"{cmd!r}"
                    )


def test_suggest_iterate_script_exists_at_canonical_path():
    """AC-1 dependency: the script the canonical command points to
    must exist in the source tree. Cache verification lives in
    test_cache_layout (AC-13) — separate concern, optional in CI."""
    assert _SUGGEST_ITERATE.is_file(), (
        f"suggest_iterate.py missing at {_SUGGEST_ITERATE}; canonical "
        f"command refers to ${{CLAUDE_PLUGIN_ROOT}}/../../shared/scripts/"
        f"hooks/suggest_iterate.py which resolves to this path."
    )


def test_classify_intent_reachable_via_path_arithmetic():
    """The script does Path(__file__).parent.parent.parent.parent then
    /'plugins/shipwright-iterate/scripts/lib' — verify the file lives
    where the script expects."""
    parent4 = _SUGGEST_ITERATE.resolve().parent.parent.parent.parent
    expected = (
        parent4
        / "plugins"
        / "shipwright-iterate"
        / "scripts"
        / "lib"
        / "classify_intent.py"
    )
    assert expected == _CLASSIFY_INTENT.resolve(), (
        f"path arithmetic mismatch: parent^4 → {parent4}, expected "
        f"{_CLASSIFY_INTENT.parent}"
    )
    assert expected.is_file()


# --- AC-11: Round-trip boundary probe ----------------------------------


@pytest.fixture
def fake_plugin_cache(tmp_path: Path) -> Path:
    """Mirror the production plugin cache layout into a tmp dir so the
    canonical command (which relies on ${CLAUDE_PLUGIN_ROOT}/../../shared)
    actually resolves a real script."""
    cache = tmp_path / "shipwright-cache"
    plugin_root = cache / "shipwright-iterate" / "0.0.0-test"
    shared_hooks = cache / "shared" / "scripts" / "hooks"
    plugins_iterate_lib = (
        cache / "plugins" / "shipwright-iterate" / "scripts" / "lib"
    )
    shared_hooks.mkdir(parents=True)
    plugin_root.mkdir(parents=True)
    plugins_iterate_lib.mkdir(parents=True)

    # Copy the script we want to invoke.
    shutil.copy2(_SUGGEST_ITERATE, shared_hooks / "suggest_iterate.py")
    # Copy the dependency the script imports via path arithmetic.
    classify_intent_dir = _CLASSIFY_INTENT.parent
    for f in classify_intent_dir.glob("*.py"):
        shutil.copy2(f, plugins_iterate_lib / f.name)

    return plugin_root


def _spawn_canonical_command(
    plugin_root: Path,
    project_dir: Path,
    prompt: str,
) -> subprocess.CompletedProcess:
    """Run the canonical command exactly as Claude Code would, with
    ${CLAUDE_PLUGIN_ROOT} bound to a fake plugin install dir."""
    # Resolve the canonical command's path concretely (no shell expansion):
    script = (
        plugin_root / ".." / ".." / "shared" / "scripts" / "hooks"
        / "suggest_iterate.py"
    ).resolve()
    payload = json.dumps({
        "hook_event_name": "UserPromptSubmit",
        "prompt": prompt,
        "cwd": str(project_dir),
    })
    # Tightly controlled env: only what's needed (per external-review-finding-10).
    # uv on Windows needs SystemDrive + LOCALAPPDATA in addition to USERPROFILE
    # to resolve its data-dir path; missing SystemDrive caused uv to create a
    # literal "%SystemDrive%/ProgramData/..." dir under cwd in earlier test
    # runs (gitignored as a defensive belt+suspenders).
    env = {
        "PATH": os.environ.get("PATH", ""),
        "CLAUDE_PLUGIN_ROOT": str(plugin_root),
        "HOME": os.environ.get("HOME", ""),
        "USERPROFILE": os.environ.get("USERPROFILE", ""),
        "TEMP": os.environ.get("TEMP", ""),
        "TMP": os.environ.get("TMP", ""),
        "SystemRoot": os.environ.get("SystemRoot", ""),
        "SystemDrive": os.environ.get("SystemDrive", ""),
        "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
        "APPDATA": os.environ.get("APPDATA", ""),
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(
        ["uv", "run", "--no-project", str(script)],
        input=payload,
        text=True,
        capture_output=True,
        env={k: v for k, v in env.items() if v},
        timeout=60,
    )


def _make_shipwright_project(project_dir: Path, status: str = "complete") -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "shipwright_run_config.json").write_text(
        json.dumps({"status": status, "completed_steps": ["test"]}),
        encoding="utf-8",
    )


@pytest.mark.skipif(
    shutil.which("uv") is None,
    reason="uv binary not on PATH; round-trip test requires uv to spawn the hook",
)
def test_round_trip_routing_match_emits_additional_context(
    fake_plugin_cache: Path,
    tmp_path: Path,
):
    """AC-11: producer→file→consumer round-trip. Spawn the canonical
    command with a routing-pattern prompt, assert exit 0 + valid
    hookSpecificOutput on stdout."""
    project = tmp_path / "fake-shipwright-project"
    _make_shipwright_project(project)

    # Use a phrase guaranteed to match the 'test' phase pattern.
    result = _spawn_canonical_command(
        fake_plugin_cache, project, "run the unit tests"
    )
    assert result.returncode == 0, (
        f"hook exited {result.returncode}; stderr: {result.stderr!r}"
    )
    if result.stdout.strip():
        # Routing match → hookSpecificOutput emitted as JSON.
        payload = json.loads(result.stdout)
        assert "hookSpecificOutput" in payload
        ctx = payload["hookSpecificOutput"].get("additionalContext", "")
        assert "[Shipwright]" in ctx


@pytest.mark.skipif(
    shutil.which("uv") is None, reason="uv binary not on PATH"
)
def test_round_trip_non_shipwright_project_silent_exit(
    fake_plugin_cache: Path,
    tmp_path: Path,
):
    """Guard 1 of suggest_iterate.py: in a non-Shipwright project (no
    shipwright_run_config.json), the hook must exit 0 silently with
    no stdout. Regression test for external-review-finding-12."""
    project = tmp_path / "non-shipwright-project"
    project.mkdir()  # no shipwright_run_config.json

    result = _spawn_canonical_command(
        fake_plugin_cache, project, "run the tests"
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "", (
        f"non-shipwright project must exit silent; stdout: {result.stdout!r}"
    )


@pytest.mark.skipif(
    shutil.which("uv") is None, reason="uv binary not on PATH"
)
def test_round_trip_slash_command_skipped(
    fake_plugin_cache: Path, tmp_path: Path
):
    """Guard 3: slash-prefix prompts are skipped (user already chose a skill)."""
    project = tmp_path / "shipwright-project"
    _make_shipwright_project(project)

    result = _spawn_canonical_command(
        fake_plugin_cache, project, "/shipwright-iterate add a feature"
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


@pytest.mark.skipif(
    shutil.which("uv") is None, reason="uv binary not on PATH"
)
def test_round_trip_short_prompt_skipped(
    fake_plugin_cache: Path, tmp_path: Path
):
    """Guard 4: prompts under 10 chars are skipped (greetings)."""
    project = tmp_path / "shipwright-project"
    _make_shipwright_project(project)

    result = _spawn_canonical_command(fake_plugin_cache, project, "hi")
    assert result.returncode == 0
    assert result.stdout.strip() == ""


@pytest.mark.skipif(
    shutil.which("uv") is None, reason="uv binary not on PATH"
)
def test_round_trip_invalid_stdin_payload(
    fake_plugin_cache: Path, tmp_path: Path
):
    """Defensive: malformed stdin must not crash the hook (would
    cascade into a UserPromptSubmit block)."""
    script = (
        fake_plugin_cache
        / ".."
        / ".."
        / "shared"
        / "scripts"
        / "hooks"
        / "suggest_iterate.py"
    ).resolve()
    env = {
        "PATH": os.environ.get("PATH", ""),
        "CLAUDE_PLUGIN_ROOT": str(fake_plugin_cache),
        "HOME": os.environ.get("HOME", ""),
        "USERPROFILE": os.environ.get("USERPROFILE", ""),
        "TEMP": os.environ.get("TEMP", ""),
        "TMP": os.environ.get("TMP", ""),
        "SystemRoot": os.environ.get("SystemRoot", ""),
        "PYTHONIOENCODING": "utf-8",
    }
    result = subprocess.run(
        ["uv", "run", "--no-project", str(script)],
        input="this is not json {{{",
        text=True,
        capture_output=True,
        env={k: v for k, v in env.items() if v},
        timeout=60,
    )
    # Per suggest_iterate.py main(): JSONDecodeError → sys.exit(0)
    assert result.returncode == 0


# --- AC-13: Cache-vs-source verification -------------------------------


_CLAUDE_USER_HOME = Path.home() / ".claude" / "plugins" / "cache" / "shipwright"


@pytest.mark.skipif(
    not _CLAUDE_USER_HOME.exists(),
    reason=(
        "cache directory not present; this test only runs in environments "
        "where the user has installed the shipwright marketplace plugin. "
        "Run `bash scripts/update-marketplace.sh` to populate the cache."
    ),
)
def test_cache_layout_resolves_canonical_command_target():
    """AC-13: after marketplace sync, the canonical command literal
    must resolve to a real file at
    ~/.claude/plugins/cache/shipwright/shared/scripts/hooks/suggest_iterate.py."""
    cached_script = _CLAUDE_USER_HOME / "shared" / "scripts" / "hooks" / "suggest_iterate.py"
    assert cached_script.is_file(), (
        f"cached suggest_iterate.py missing at {cached_script}; run "
        f"`bash scripts/update-marketplace.sh` to refresh."
    )

    # Verify path arithmetic from the cache copy matches the source-tree
    # behavior (parent^4 → cache root with plugins/shipwright-iterate/scripts/lib).
    parent4 = cached_script.resolve().parent.parent.parent.parent
    cached_classify = (
        parent4
        / "plugins"
        / "shipwright-iterate"
        / "scripts"
        / "lib"
        / "classify_intent.py"
    )
    assert cached_classify.is_file(), (
        f"cached classify_intent.py missing at {cached_classify}; cache "
        f"layout drift — re-run update-marketplace.sh."
    )




def _active_iterate_plugin_install_path() -> Path | None:
    """Look up the ACTIVE shipwright-iterate plugin install path from
    ``~/.claude/plugins/installed_plugins.json``. The active version is
    what ``update-marketplace.sh`` syncs (it writes to the path stored
    there, not whatever happens to be alphabetically last in the cache
    directory). Picking the wrong version made AC-13 never fire — see
    P5 finding in the merge-gate probes."""
    ip_path = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    if not ip_path.is_file():
        return None
    try:
        data = json.loads(ip_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    entries = (
        data.get("plugins", {}).get("shipwright-iterate@shipwright") or []
    )
    if not entries:
        return None
    install = entries[0].get("installPath")
    if not install:
        return None
    return Path(install)


def _cache_hooks_json_in_sync_with_source() -> tuple[bool, Path | None]:
    """True when the cached plugin install carries the same hooks.json
    bytes as the source tree — meaning ``update-marketplace.sh`` has
    propagated the most recent push to the *active* install path."""
    install = _active_iterate_plugin_install_path()
    if install is None or not install.is_dir():
        return False, None
    candidate = install / "hooks" / "hooks.json"
    if not candidate.is_file():
        return False, candidate
    try:
        a = candidate.read_text(encoding="utf-8")
        b = _PLUGIN_HOOKS_JSON.read_text(encoding="utf-8")
    except OSError:
        return False, candidate
    return a == b, candidate


@pytest.mark.skipif(
    not _CLAUDE_USER_HOME.exists()
    or not _cache_hooks_json_in_sync_with_source()[0],
    reason=(
        "cache plugin install is stale or missing — runs after "
        "`git push && bash scripts/update-marketplace.sh`. Pre-push, "
        "this test is expected to skip; the source-tree static-shape "
        "assertions in test_user_prompt_submit_uses_canonical_command "
        "carry the must-pass invariant. External-review-finding M3."
    ),
)
def test_cache_hooks_json_registers_canonical_userpromptsubmit():
    """AC-13 (post-sync gate): when the marketplace cache is in sync
    with the source tree, the cached plugin's hooks.json must carry
    the canonical UserPromptSubmit registration. Catches packaging
    drift independent of the file-presence checks above. Pre-push,
    this test is skipped because the cache cannot carry a registration
    that has not yet been pushed to GitHub + synced via
    update-marketplace.sh."""
    _, cached_hooks_json = _cache_hooks_json_in_sync_with_source()
    assert cached_hooks_json is not None and cached_hooks_json.is_file()
    cache_raw = json.loads(cached_hooks_json.read_text(encoding="utf-8"))
    # Unwrap the Claude Code 2.1.132+ top-level "hooks" key (ADR-039);
    # tolerate either shape so the test stays useful through schema flips.
    cache_data = cache_raw.get("hooks") if isinstance(cache_raw.get("hooks"), dict) else cache_raw
    cache_user_prompt_cmds: list[str] = []
    for matcher in cache_data.get("UserPromptSubmit", []):
        if isinstance(matcher, dict):
            for sub in matcher.get("hooks", []):
                if isinstance(sub, dict) and sub.get("command"):
                    cache_user_prompt_cmds.append(sub["command"])
    assert _CANONICAL_COMMAND in cache_user_prompt_cmds, (
        f"cache plugin install at {cached_hooks_json.parent.parent} does "
        f"not carry the canonical suggest_iterate registration despite "
        f"hooks.json bytes matching source. Found commands: "
        f"{cache_user_prompt_cmds!r}."
    )
