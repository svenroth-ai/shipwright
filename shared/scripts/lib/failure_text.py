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


def _text(value: object) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else (value or "")


def failure_detail(result: subprocess.CompletedProcess) -> str:
    """Generator-error detail parsed from stdout JSON; else the stderr tail without advisory ``warning:`` lines.

    When stderr is empty or holds only ``warning:`` lines, the stdout tail is appended, so the log is never blank."""
    stdout, stderr = _text(result.stdout), _text(result.stderr)
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        payload = None
    errors = payload.get("generator_errors") if isinstance(payload, dict) else None
    valid = [e for e in errors if isinstance(e, dict)] if isinstance(errors, list) else []
    if valid:
        return "; ".join(f"{e.get('report')}: {e.get('error')}: {e.get('detail')}" for e in valid)
    lines = stderr.splitlines()
    real = [ln for ln in lines if not ln.lstrip().startswith("warning:")]
    parts = ["\n".join(real or lines)[-_STDERR_TAIL:]]
    if not real and stdout.strip():
        parts.append("stdout: " + stdout.strip()[-_STDOUT_TAIL:])
    return " | ".join(p for p in parts if p)
