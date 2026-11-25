"""The one place the release CLI starts a process: a runner a test can replace.

``release.py`` wraps existing tools and never reimplements them, so every tool call goes
through a ``Runner`` (the run-state file asks git for its own path directly): ``runner(key, argv, cwd) -> CmdResult``. Production uses
``subprocess_runner``; the L1 tests inject a fake that answers by ``key``. ``Recorder`` keeps
every result so the CLI can put the commands it ran into its JSON (the caller, and the golden CLI
driver, read each tool's own stdout, stderr and exit code from there).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence


@dataclass(frozen=True)
class CmdResult:
    key: str
    argv: tuple[str, ...]
    exit: int
    stdout: str = ""
    stderr: str = ""

    def as_json(self) -> dict:
        return {"key": self.key, "argv": list(self.argv), "exit": self.exit, "stdout": self.stdout, "stderr": self.stderr}


Runner = Callable[..., CmdResult]  # (key, argv, cwd) and, only when a caller sets them, the keywords env= and timeout=
DEFAULT_TIMEOUT = 600


def subprocess_runner(key: str, argv: Sequence[str], cwd: Path, *, env: Mapping[str, str] | None = None,
                      timeout: float = DEFAULT_TIMEOUT) -> CmdResult:
    """Run ``argv`` in ``cwd``; a program that is not installed is a result (exit 127), never a crash. ``env`` is added to
    this process's environment (never replaces it); a run past ``timeout`` seconds is exit 124."""
    try:
        done = subprocess.run(list(argv), cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, env={**os.environ, **env} if env else None)
    except FileNotFoundError as exc:
        return CmdResult(key, tuple(argv), 127, "", f"{type(exc).__name__}: {exc}")
    except subprocess.TimeoutExpired:
        return CmdResult(key, tuple(argv), 124, "", f"timed out after {timeout:g} s")
    return CmdResult(key, tuple(argv), done.returncode, done.stdout, done.stderr)


def uv_script(script: Path, *args: str) -> list[str]:
    """``uv run <script> <args>``, the form every SKILL.md command takes."""
    return ["uv", "run", str(script), *args]


@dataclass
class Recorder:
    """Runs through ``runner`` and remembers every result, in order."""

    runner: Runner
    cwd: Path
    results: list[CmdResult] = field(default_factory=list)

    def run(self, key: str, argv: Sequence[str], *, env: Mapping[str, str] | None = None,
            timeout: float | None = None) -> CmdResult:
        """``env``/``timeout`` reach the runner only when set, so a test runner with the plain ``(key, argv, cwd)`` shape still fits."""
        opts = {name: value for name, value in (("env", env), ("timeout", timeout)) if value is not None}
        result = self.runner(key, argv, self.cwd, **opts)
        self.results.append(result)
        return result

    def scrub_last(self, stdout: str, stderr: str) -> None:
        """Replace what the last command printed in the record the JSON reports (a lookup whose output may name a URL)."""
        last = self.results[-1]
        self.results[-1] = CmdResult(last.key, last.argv, last.exit, stdout, stderr)

    def as_json(self) -> list[dict]:
        return [r.as_json() for r in self.results]
