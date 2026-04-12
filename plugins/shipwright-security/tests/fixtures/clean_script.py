"""Fixture: Clean Python script with no dangerous patterns."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def load_config(path: Path) -> dict:
    """Load a JSON config file safely."""
    return json.loads(path.read_text(encoding="utf-8"))


def run_command(args: list[str]) -> str:
    """Run a subprocess with shell=False (safe)."""
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout


def safe_computation(value: int) -> int:
    return value * 2 + 1
