"""Per-hook launcher-script materialization for R1b's config-layer Codex
hooks sync. Split out of ``codex_hooks_sync.py`` (the orchestrating
producer, which imports :class:`CodexHooksSyncError` and :func:`_materialize`
from here) to stay under the repo's 300-LOC guideline.

**Launcher scripts, not inline commands.** Codex runs a hook's ``command``
string via ``cmd.exe /C "<command_line>"`` on Windows — wrapping the WHOLE
string in one extra quote pair, unconditionally. `cmd.exe /C` only parses
cleanly with exactly one quote pair total, so any command embedding its own
quoted paths (every real Shipwright hook command does, e.g. ``uv run
"${CLAUDE_PLUGIN_ROOT}/scripts/x.py" "${CLAUDE_PLUGIN_ROOT}/../../shared/y.py"``)
breaks silently — confirmed empirically (8 live Codex invocations, zero
fires, traced to this bug by reading
``codex-rs/hooks/src/engine/command_runner.rs`` directly). The fix: write
one small launcher script per hook handler (``.cmd`` on Windows, ``.sh`` +
executable bit on POSIX) holding the real, normally-quoted invocation, and
put only that launcher's path into ``hooks.json``. A single quoted token
with no arguments satisfies ``cmd.exe``'s documented "preserve as executable
name" special case even when the path itself contains spaces — but on
POSIX, Codex runs the whole ``command`` string via ``$SHELL -lc
"<command_line>"``, which then re-parses it as a shell command line and
word-splits on whitespace: an unquoted launcher path containing a space
(plausible on macOS, e.g. ``/Users/Sven Roth/.codex/...``) breaks the exact
opposite way (external code review, both legs, high). So the string written
into ``hooks.json`` is platform-shaped: bare on Windows (cmd.exe's special
case needs no quoting and shell-quoting would reintroduce the double-quote
bug this module exists to fix), ``shlex.quote()``-wrapped on POSIX (a single
shell token even with embedded spaces). :func:`_hooks_json_command` is the
write side of that split; :func:`_command_to_launcher_path` is the read
side, used by ``codex_hooks_sync.py``'s ownership check to recover the real
filesystem path from either shape.
"""

from __future__ import annotations

import hashlib
import re
import shlex
import stat
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from atomic_write import durable_atomic_write  # noqa: E402

_PLACEHOLDER = "${CLAUDE_PLUGIN_ROOT}"

# ``bundle_root`` is spliced into a launcher-script body wherever the
# bundle's own raw_command text places _PLACEHOLDER — which may or may not
# sit inside quotes, depending on how that command was authored (unlike
# _hooks_json_command()'s single, known context). Rather than escape for an
# assumed quoting context, reject any character outside this conservative
# path-safe allowlist: real bundle roots (plugin cache directories) never
# legitimately need shell/cmd.exe metacharacters (F11 PR-review preflight,
# 2026-09-22 — see the ADR's Accepted Risk section for why the sibling
# raw_command-content case is handled differently).
_UNSAFE_BUNDLE_ROOT_RE = re.compile(r"[^A-Za-z0-9 ._/\\:~+@,()-]")


class CodexHooksSyncError(RuntimeError):
    """Raised on malformed bundle or existing config-layer input — a
    genuine problem to surface loudly, never an absence signal to route
    around silently."""


def _launcher_slug(event: str, matcher: str | None, group_idx: int, handler_idx: int) -> str:
    key = f"{event}|{matcher or ''}|{group_idx}|{handler_idx}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _write_launcher(launcher_dir: Path, slug: str, command_line: str, bundle_root: str) -> Path:
    """*bundle_root* is injected as ``SHIPWRIGHT_PLUGIN_ROOT`` into the
    launcher body itself — config-layer hooks get no env vars from Codex at
    all (``"env": {}``, confirmed by R1b's live capture), so
    ``resolve_plugin_root()``/``is_codex_runtime()`` are permanently false
    under real Codex unless the launcher supplies this itself (mini-plan
    §0.2; this is literally what ``plugin_root.py``'s own docstring already
    prescribes for "a thin launcher"). Already validated safe by
    :func:`_validate_bundle_root_for_launcher` before this is called."""
    if sys.platform == "win32":
        launcher_path = launcher_dir / f"{slug}.cmd"
        body = (
            "@echo off\r\n"
            f'set "SHIPWRIGHT_PLUGIN_ROOT={bundle_root}"\r\n'
            f"{command_line}\r\n"
            "exit /b %ERRORLEVEL%\r\n"
        )
        durable_atomic_write(launcher_path, body)
    else:
        launcher_path = launcher_dir / f"{slug}.sh"
        # Three separate lines, not inline `VAR=val exec cmd` — assignment
        # export semantics ahead of a special builtin are murky across
        # shells (mini-plan §0.2). shlex.quote() is belt-and-braces: the
        # bundle-root allowlist already forbids shell metacharacters, but a
        # bare space (legal in that allowlist) still needs quoting here.
        body = (
            "#!/bin/sh\n"
            f"SHIPWRIGHT_PLUGIN_ROOT={shlex.quote(bundle_root)}\n"
            "export SHIPWRIGHT_PLUGIN_ROOT\n"
            f"exec {command_line}\n"
        )
        durable_atomic_write(launcher_path, body)
        # Owner-only execute: these launchers embed real, unquoted filesystem
        # paths, so group/other on a shared machine gain nothing by being able
        # to execute them (doubt-reviewer, low).
        mode = launcher_path.stat().st_mode
        launcher_path.chmod(mode | stat.S_IXUSR)
    return launcher_path


def _hooks_json_command(launcher_path: Path) -> str:
    """The string written into ``hooks.json``'s ``command`` field for
    *launcher_path* — bare on Windows, ``shlex``-quoted on POSIX (module
    docstring)."""
    if sys.platform == "win32":
        return str(launcher_path)
    return shlex.quote(str(launcher_path))


def _command_to_launcher_path(command: str) -> Path | None:
    """Recover the real filesystem path from a ``hooks.json`` command
    string shaped by :func:`_hooks_json_command`, or ``None`` if *command*
    is not a single-token launcher reference (foreign entry). Mirrors that
    function's platform split: POSIX strings may be ``shlex``-quoted,
    Windows strings are always bare."""
    command = command.strip()
    if not command:
        return None
    if sys.platform == "win32":
        return Path(command)
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if len(tokens) != 1:
        return None
    return Path(tokens[0])


def _validate_bundle_root_for_launcher(bundle_root: Path) -> None:
    """Raise loudly rather than splice an unsafe character into a launcher
    script body — surfacing a genuine problem instead of silently risking
    shell/cmd.exe injection (this module's "surface loudly" commitment)."""
    text = str(bundle_root)
    match = _UNSAFE_BUNDLE_ROOT_RE.search(text)
    if match:
        raise CodexHooksSyncError(
            f"bundle root contains a character unsafe for launcher-script "
            f"generation ({match.group()!r} in {text!r}) — refusing to "
            "materialize hooks rather than risk shell/cmd.exe injection"
        )


def _materialize(
    bundle_hooks: dict, bundle_root: Path, launcher_dir: Path
) -> tuple[dict, list[dict]]:
    _validate_bundle_root_for_launcher(bundle_root)
    new_hooks: dict = {}
    manifest_entries: list[dict] = []

    for event, groups in bundle_hooks.items():
        new_groups = []
        for group_idx, group in enumerate(groups):
            matcher = group.get("matcher")
            new_handlers = []
            for handler_idx, handler in enumerate(group.get("hooks", [])):
                raw_command = handler.get("command") or ""
                if not raw_command.strip():
                    raise CodexHooksSyncError(
                        f"bundle hook {event}[{group_idx}].hooks[{handler_idx}] has "
                        "no command — a malformed bundle, not an absence signal"
                    )
                command_line = raw_command.replace(_PLACEHOLDER, str(bundle_root))
                slug = _launcher_slug(event, matcher, group_idx, handler_idx)
                launcher_path = _write_launcher(launcher_dir, slug, command_line, str(bundle_root))
                hooks_json_command = _hooks_json_command(launcher_path)
                new_handlers.append({**handler, "command": hooks_json_command})
                manifest_entries.append(
                    {
                        "event": event,
                        "matcher": matcher,
                        "command": hooks_json_command,
                    }
                )
            if new_handlers:
                new_group = {**group, "hooks": new_handlers}
                new_groups.append(new_group)
        if new_groups:
            new_hooks[event] = new_groups

    return new_hooks, manifest_entries
