"""Integration test for iterate-2026-09-28-hooks-uv-run-project-pin.

Proves the *mechanism* behind the `--no-project` fix, not just that the
flag string is present in a JSON file: a hook script invoked via the
EXACT `uv run --no-project "<script>"` command shape shipped in a real
hooks.json must succeed even when the session's current working
directory is an unrelated, uv-managed Python project whose dependency
cannot be resolved (a "poisoned" project) — because `--no-project` skips
project discovery/resolution entirely.

A paired test covers the same invocation WITHOUT `--no-project` against
that same poisoned CWD. Historically this was a strict negative control
(must fail, and fail specifically on project/interpreter resolution).
Since uv 0.12 shipped target-workspace-discovery (astral-sh/uv#14585),
`uv run <script-path>` resolves the project relative to the SCRIPT's own
directory, not the CWD, whenever the two diverge — which is exactly this
shape (hook scripts are always invoked by absolute path from the plugin
cache, cwd = the caller's project). On that uv generation the poisoned
CWD `pyproject.toml` is never even opened, so the run now succeeds
regardless of `--no-project`, confirmed empirically: CI's floating uv
(0.12.19) returns 0 here where local uv (0.11.9, still CWD-discovering
for this shape) returns nonzero. Both outcomes are safe: a malformed
TOML can never be used successfully by uv — it either gets skipped
entirely (clean success) or gets opened and rejected (failure clearly
attributable to project/interpreter resolution). There is no third,
unsafe outcome the malformed content could produce, so accepting either
still proves the poisoned project never influenced what the hook ran.

Both subprocess calls run with `VIRTUAL_ENV`/`UV_*` stripped from the
environment, so a venv this test happens to run under cannot mask (or
fake) either result. The poisoned project is a syntactically INVALID
`pyproject.toml` — `uv run` (project mode), on a uv generation that
still does CWD discovery for this invocation shape, always parses that
file during settings discovery before any interpreter/dependency check
runs, so a discovery attempt fails at the earliest possible step. Two
earlier poisoning mechanisms were each version/platform-dependent
instead: a nonexistent `file://` dependency path failed as expected with
uv 0.11.9 on Windows but silently succeeded on Linux CI, since uv
resolves/parses that URI form differently there; an impossible
`requires-python` (`==99.99.99`) failed locally but silently succeeded
on CI's newer uv, which apparently does not re-validate `requires-python`
against a project with zero dependencies before running (main-repair for
iterate/fix-main-a6bb2537457f, CI run 36432205060). A malformed TOML
file has no such escape hatch within a single uv generation: parsing it,
when attempted at all, is unconditional.

This is the `category:"integration"` Test Completeness Ledger behavior
required by the `cross_component` risk flag for hooks.json changes.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_TARGET_SCRIPT_NAME = "write_terminal_marker.py"
_PLACEHOLDER = "${CLAUDE_PLUGIN_ROOT}"

# Syntactically invalid TOML — unconditional and version-independent.
# `uv run` (project mode) parses pyproject.toml during settings discovery
# before any interpreter/dependency logic runs at all, so this fails at
# the earliest possible step regardless of uv version or platform.
# `--no-project` never reaches this parse, by that flag's own contract.
_POISONED_PYPROJECT = """\
[project
this is not valid toml
"""


def _scrubbed_env() -> dict[str, str]:
    """Drop every uv/venv-identifying variable so this test's own
    interpreter/venv can't leak into, or be mistaken for, the child
    processes' project resolution."""
    return {
        k: v
        for k, v in os.environ.items()
        if k != "VIRTUAL_ENV" and not k.startswith("UV_")
    }


def _find_real_uv_run_command(script_name: str) -> tuple[str, Path]:
    """Pull the exact `uv run --no-project "..."` prefix Shipwright ships
    for *script_name* out of a real hooks.json, plus the resolved absolute
    path that command's ``${CLAUDE_PLUGIN_ROOT}`` placeholder points at, so
    this test builds its subprocess argv from the literal shape hooks fire —
    not a hand-written approximation of it. Fails loudly if no hooks.json
    invokes the script (fixture broken). Matches `uv run` regardless of
    whether `--no-project` is present, so a future regression (the flag
    silently dropped) surfaces as "prefix != 'uv run --no-project'" rather
    than this fixture's own "not found"."""
    for hooks_path in sorted(REPO_ROOT.glob("plugins/*/hooks*/hooks.json")):
        plugin_root = hooks_path.parent.parent
        config = json.loads(hooks_path.read_text(encoding="utf-8"))
        for cmd in _collect_command_strings(config):
            if script_name not in cmd or "uv run" not in cmd:
                continue
            match = re.search(
                r'(uv run(?:\s+--\S+)*)\s+"([^"]*' + re.escape(script_name) + r')"',
                cmd,
            )
            if match:
                prefix = match.group(1)
                raw_path = match.group(2).replace(_PLACEHOLDER, str(plugin_root))
                return prefix, Path(raw_path).resolve()
    raise AssertionError(
        f"no hooks.json command found invoking {script_name} via `uv run` — "
        f"fixture broken, or the script was renamed/moved"
    )


def _collect_command_strings(node: object) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "command" and isinstance(value, str):
                found.append(value)
            else:
                found.extend(_collect_command_strings(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_collect_command_strings(item))
    return found


@pytest.fixture
def poisoned_cwd(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(_POISONED_PYPROJECT, encoding="utf-8")
    return tmp_path


@pytest.fixture
def real_hook_command() -> tuple[str, Path]:
    """(flag_prefix, resolved_script_path) for a real, currently-shipped
    hooks.json entry invoking a stdlib-only, side-effect-free hook —
    resolved from the actual command string, not reconstructed
    independently, so the subprocess calls below exercise the literal
    shape hooks fire."""
    prefix, script_path = _find_real_uv_run_command(_TARGET_SCRIPT_NAME)
    assert script_path.name == _TARGET_SCRIPT_NAME
    assert script_path.is_file(), f"resolved hook script missing: {script_path}"
    return prefix, script_path


def test_no_project_ignores_poisoned_cwd(
    poisoned_cwd: Path, real_hook_command: tuple[str, Path]
) -> None:
    """The real `uv run --no-project` prefix hooks.json ships must succeed
    regardless of the CWD project."""
    prefix, script_path = real_hook_command
    assert prefix == "uv run --no-project"

    result = subprocess.run(
        [*shlex.split(prefix), str(script_path)],
        cwd=poisoned_cwd,
        input="{}",
        capture_output=True,
        text=True,
        timeout=60,
        env=_scrubbed_env(),
    )
    assert result.returncode == 0, (
        f"uv run --no-project should ignore the poisoned CWD project and "
        f"succeed; got exit {result.returncode}\nstdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )


def test_without_no_project_is_poisoned_by_cwd(
    poisoned_cwd: Path, real_hook_command: tuple[str, Path]
) -> None:
    """The same invocation WITHOUT --no-project must never actually run
    against the poisoned CWD project — whether that shows up as a clean
    success (modern uv's target-workspace-discovery skips CWD discovery
    entirely for this out-of-tree script shape, astral-sh/uv#14585) or as
    a failure clearly attributable to project/interpreter resolution
    (older uv, which still discovers from the CWD for this shape and
    then chokes on the malformed TOML). A malformed pyproject.toml has no
    third outcome it could produce: uv either never opens it (success) or
    opens and rejects it (failure naming project/resolution/interpreter),
    so either branch proves the poisoned project never influenced what
    actually ran."""
    prefix, script_path = real_hook_command
    assert "--no-project" in shlex.split(prefix), (
        f"hooks.json's real command for {_TARGET_SCRIPT_NAME} no longer ships "
        f"--no-project (got prefix {prefix!r}) — this test's whole premise is "
        f"stripping a flag that must actually be there to strip; without this "
        f"check it would keep passing even if the flag were silently dropped "
        f"from hooks.json, since removing an absent token is a no-op"
    )
    unpinned_prefix = [tok for tok in shlex.split(prefix) if tok != "--no-project"]
    assert unpinned_prefix == ["uv", "run"], (
        f"expected the real prefix minus --no-project to be exactly 'uv run', "
        f"got {unpinned_prefix} — this check must strip ONLY the flag under "
        f"test, not approximate the command"
    )

    result = subprocess.run(
        [*unpinned_prefix, str(script_path)],
        cwd=poisoned_cwd,
        input="{}",
        capture_output=True,
        text=True,
        timeout=60,
        env=_scrubbed_env(),
    )
    combined = (result.stdout + result.stderr).lower()
    if result.returncode != 0:
        assert any(
            term in combined
            for term in ("resolve", "resolution", "project", "dependenc", "interpreter", "python")
        ), (
            "uv run without --no-project failed, but not in a way "
            "attributable to project/interpreter resolution — expected "
            "either a clean success (modern uv skips CWD discovery for "
            "this shape) or a failure naming project resolution (older "
            f"uv, still discovering from the CWD), got:\n{result.stderr}"
        )
    else:
        # On the success branch (modern uv, target-workspace-discovery
        # never opens the poisoned pyproject.toml at all) the run must be
        # unremarkable — no stray warning about the malformed file it
        # skipped. A quiet success is what "never opened it" actually
        # looks like; noisy output here would mean something DID touch
        # the poisoned project and merely failed to treat that as fatal.
        assert result.stdout == "" and result.stderr == "", (
            "uv run without --no-project succeeded but produced unexpected "
            f"output — expected total silence for a run that never touched "
            f"the poisoned CWD project:\nstdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
