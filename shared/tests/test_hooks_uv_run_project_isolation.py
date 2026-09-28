"""Integration test for iterate-2026-09-28-hooks-uv-run-project-pin.

Proves the *mechanism* behind the `--no-project` fix, not just that the
flag string is present in a JSON file: a hook script invoked via the
EXACT `uv run --no-project "<script>"` command shape shipped in a real
hooks.json must succeed even when the session's current working
directory is an unrelated, uv-managed Python project whose dependency
cannot be resolved (a "poisoned" project) — because `--no-project` skips
project discovery/resolution entirely. A paired negative control, the
same invocation WITHOUT `--no-project`, must fail against that same
poisoned CWD, proving this test would have caught the original bug (a
real hook script hard-failing because `uv run` resolved and tried to
sync an unrelated CWD project instead of running standalone).

Both subprocess calls run with `VIRTUAL_ENV`/`UV_*` stripped from the
environment, so a venv this test happens to run under cannot mask (or
fake) either result. The poisoned project is a syntactically INVALID
`pyproject.toml` — `uv run` (project mode) always parses that file
during settings discovery, before any interpreter/dependency check runs,
so this fails at the earliest possible step and cannot depend on a uv
version's interpreter-resolution behavior. `uv run --no-project` skips
project discovery entirely (that flag's whole contract), so it still
succeeds even though the same broken file is on disk. Two earlier
poisoning mechanisms were each version/platform-dependent instead: a
nonexistent `file://` dependency path failed as expected with uv 0.11.9
on Windows but silently succeeded on Linux CI, since uv resolves/parses
that URI form differently there; an impossible `requires-python`
(`==99.99.99`) failed locally but silently succeeded on CI's newer uv,
which apparently does not re-validate `requires-python` against a
project with zero dependencies before running (main-repair for
iterate/fix-main-a6bb2537457f, CI run 36432205060). A malformed TOML
file has no such escape hatch: parsing it is unconditional and has no
version-dependent branch to skip through.

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
    """Negative control: the same invocation WITHOUT --no-project resolves
    the poisoned CWD project and fails its impossible interpreter check —
    proving this pair of tests would have caught the original bug, and
    that the failure is specifically about project resolution (not some
    unrelated error)."""
    prefix, script_path = real_hook_command
    unpinned_prefix = [tok for tok in shlex.split(prefix) if tok != "--no-project"]
    assert unpinned_prefix == ["uv", "run"], (
        f"expected the real prefix minus --no-project to be exactly 'uv run', "
        f"got {unpinned_prefix} — this negative control must strip ONLY the "
        f"flag under test, not approximate the command"
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
    assert result.returncode != 0, (
        "uv run without --no-project was expected to fail against a "
        "poisoned CWD project (impossible requires-python), but it "
        f"succeeded — the negative control is not discriminating.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    combined = (result.stdout + result.stderr).lower()
    assert any(
        term in combined
        for term in ("resolve", "resolution", "project", "dependenc", "interpreter", "python")
    ), (
        "expected the failure to mention project/interpreter resolution "
        f"(proving it failed for the right reason), got:\n{result.stderr}"
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
