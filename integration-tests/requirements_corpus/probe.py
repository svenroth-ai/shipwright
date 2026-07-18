"""Test-side helper: run a false-verdict probe against a fixture.

Kept in the package so both false-verdict test modules share one invocation
path -- a second copy would be free to drift into disagreeing about what
"failed" means.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .corpus import materialize

_RUNNER = Path(__file__).resolve().parent / "_probe_runner.py"


class ProbeFailed(RuntimeError):
    """The probe subprocess did not complete. Never treat this as a verdict --
    a crashed probe must not be readable as 'the check passed'."""


def probe(name: str, fixture: str):
    """Materialize *fixture*, run probe *name* against it, return its JSON."""
    with tempfile.TemporaryDirectory(prefix="swfv-") as tmp:
        root = materialize(fixture, Path(tmp) / "project")
        proc = subprocess.run(
            [sys.executable, str(_RUNNER), "--probe", name, "--root", str(root)],
            capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
    if proc.returncode != 0:
        raise ProbeFailed(
            f"probe {name!r} on fixture {fixture!r} failed "
            f"(exit {proc.returncode}):\n{proc.stderr[-2500:]}"
        )
    return json.loads(proc.stdout)
