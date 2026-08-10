"""Portable Bash resolution for shell-hook tests."""

import os
import shutil
from pathlib import Path

import pytest


def bash() -> str:
    """Find Git Bash when Windows exposes only git.exe on PATH."""
    if os.name == "nt":
        git = shutil.which("git")
        candidates = ([Path(git).resolve().parent.parent / "bin" / "bash.exe"]
                      if git else [])
        candidates += [Path(os.environ.get(key, "")) / "Git" / "bin" / "bash.exe"
                       for key in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    if resolved := shutil.which("bash"):
        return resolved
    pytest.skip("bash is required to exercise shell hook behavior")
