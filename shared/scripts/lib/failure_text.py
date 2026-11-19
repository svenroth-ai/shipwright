"""Readable failure text for a child process that exited non-zero.

``update_compliance.py`` reports generator errors as JSON on stdout and leaves stderr empty; any other failure
(a missing binary, a cold-start ``uv`` environment build, a traceback) only has stderr. ``uv`` prints advisory
``warning:`` lines first, which once filled a 200-character head cut and hid the real error behind them.
"""

from __future__ import annotations

import json
import subprocess

_STDERR_TAIL = 1500
_STDOUT_TAIL = 500


def failure_detail(result: subprocess.CompletedProcess) -> str:
    """Generator-error detail parsed from stdout JSON; else the stderr tail without advisory ``warning:`` lines."""
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        payload = None
    errors = payload.get("generator_errors") if isinstance(payload, dict) else None
    valid = [e for e in errors if isinstance(e, dict)] if isinstance(errors, list) else []
    if valid:
        return "; ".join(f"{e.get('report')}: {e.get('error')}: {e.get('detail')}" for e in valid)
    lines = (result.stderr or "").splitlines()
    real = [ln for ln in lines if not ln.lstrip().startswith("warning:")]
    text = "\n".join(real or lines)[-_STDERR_TAIL:]
    if not real and isinstance(result.stdout, str) and result.stdout.strip():
        text += " | stdout: " + result.stdout.strip()[-_STDOUT_TAIL:]
    return text
