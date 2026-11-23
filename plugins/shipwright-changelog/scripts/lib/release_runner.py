"""The one place the release CLI starts a process: a runner a test can replace.

``release.py`` wraps existing tools and never reimplements them, so every tool call goes
through a ``Runner`` (the run-state file asks git for its own path directly): ``runner(key, argv, cwd) -> CmdResult``. Production uses
``subprocess_runner``; the L1 tests inject a fake that answers by ``key``. ``Recorder`` keeps
every result so the CLI can put the commands it ran into its JSON (the caller, and the golden CLI
driver, read each tool's own stdout, stderr and exit code from there).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence


@dataclass(frozen=True)
class CmdResult:
    key: str
    argv: tuple[str, ...]
    exit: int
    stdout: str = ""
    stderr: str = ""

    def as_json(self) -> dict:
        return {"key": self.key, "argv": list(self.argv), "exit": self.exit, "stdout": self.stdout, "stderr": self.stderr}


Runner = Callable[[str, Sequence[str], Path], CmdResult]


def subprocess_runner(key: str, argv: Sequence[str], cwd: Path) -> CmdResult:
    """Run ``argv`` in ``cwd``; a program that is not installed is a result (exit 127), never a crash."""
    try:
        done = subprocess.run(list(argv), cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=600)
    except FileNotFoundError as exc:
        return CmdResult(key, tuple(argv), 127, "", f"{type(exc).__name__}: {exc}")
    except subprocess.TimeoutExpired:
        return CmdResult(key, tuple(argv), 124, "", "timed out after 600 s")
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

    def run(self, key: str, argv: Sequence[str]) -> CmdResult:
        result = self.runner(key, argv, self.cwd)
        self.results.append(result)
        return result

    def as_json(self) -> list[dict]:
        return [r.as_json() for r in self.results]
