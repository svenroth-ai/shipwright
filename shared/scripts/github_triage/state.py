"""Throttle-state read/write for the GitHub triage importer.

This submodule owns the on-disk throttle state file
(`.shipwright/github_import_state.json`) and the resolution chain for the
throttle interval (run-config → env var → default).

See the package docstring in ``__init__.py`` for the action-unit model
overview. Public surface re-exported from ``github_triage``:

- ``DEFAULT_THROTTLE_HOURS`` — default throttle interval in hours.
- ``throttle_hours(project_root)`` — resolved throttle interval.
- ``read_last_import(project_root)`` / ``write_last_import(project_root, when)``.
- ``is_due(project_root, *, now=None)`` — throttle gate.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE_FILENAME = "github_import_state.json"
DEFAULT_THROTTLE_HOURS = 6.0
_ENV_THROTTLE = "SHIPWRIGHT_GITHUB_IMPORT_THROTTLE_HOURS"


def _state_path(project_root) -> Path:
    return Path(project_root) / ".shipwright" / STATE_FILENAME


def _run_config(project_root) -> dict:
    try:
        raw = (
            Path(project_root) / "shipwright_run_config.json"
        ).read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def throttle_hours(project_root) -> float:
    """Throttle interval in hours. Resolution order: run-config
    ``triage.github_import_throttle_hours`` -> env var -> default. Non-positive
    or unparseable values are ignored in favour of the next source.
    """
    triage_cfg = _run_config(project_root).get("triage")
    if isinstance(triage_cfg, dict):
        value = triage_cfg.get("github_import_throttle_hours")
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value > 0
        ):
            return float(value)
    env_value = os.environ.get(_ENV_THROTTLE)
    if env_value:
        try:
            parsed = float(env_value)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return DEFAULT_THROTTLE_HOURS


def read_last_import(project_root) -> datetime | None:
    """Last-import timestamp from the state file; ``None`` if absent/malformed."""
    try:
        raw = _state_path(project_root).read_text(encoding="utf-8")
        stored = json.loads(raw).get("lastImport")
        parsed = datetime.fromisoformat(str(stored).replace("Z", "+00:00"))
    except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def read_last_security_run_id(project_root) -> int | None:
    """Id of the security scan run the last import saw; ``None`` if unrecorded."""
    try:
        value = json.loads(_state_path(project_root).read_text(encoding="utf-8"))
        value = value.get("securityRunId")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _read_state(project_root) -> dict:
    try:
        data = json.loads(_state_path(project_root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_last_import(
    project_root, when: datetime, security_run_id: int | None = None,
    branch: str | None = None,
) -> None:
    """Persist ``when`` (ISO-8601 UTC, Z-suffix) and the security run it saw."""
    path = _state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    iso = when.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    state = {"v": 1, "lastImport": iso}
    branch = branch or _read_state(project_root).get("defaultBranch")
    if isinstance(branch, str) and branch:
        state["defaultBranch"] = branch
    run_id = security_run_id if security_run_id is not None else read_last_security_run_id(project_root)
    if run_id is not None:
        state["securityRunId"] = run_id
    path.write_text(json.dumps(state), encoding="utf-8")


def record_security_run(project_root, run_id, branch: str | None = None) -> None:
    """Remember the scan (and default branch) this import saw; the clock stays as it was."""
    if not isinstance(run_id, int):
        return
    try:  # best-effort: a failed write only costs the early-refresh hint
        write_last_import(
            project_root, read_last_import(project_root) or datetime.now(timezone.utc),
            run_id, branch)
    except OSError:
        pass


def _security_scan_is_newer(project_root) -> bool:
    """A scan newer than the last one imported means main moved: do not wait."""
    seen = read_last_security_run_id(project_root)
    if seen is None:
        return False
    try:
        import github_api  # noqa: PLC0415 - network helper, only on this path
        branch = _read_state(project_root).get("defaultBranch")
        run = github_api.latest_security_workflow_run(
            **({"branch": branch} if isinstance(branch, str) and branch else {}))
        newest = (run or {}).get("id")
    except Exception:  # noqa: BLE001 - a failed probe falls back to the throttle
        return False
    return isinstance(newest, int) and newest != seen


def is_due(project_root, *, now: datetime | None = None) -> bool:
    """True if an import is due — no prior state, or the throttle interval
    has elapsed since the last import, or a newer security scan exists."""
    now = now or datetime.now(timezone.utc)
    last = read_last_import(project_root)
    if last is None:
        return True
    if (now - last) >= timedelta(hours=throttle_hours(project_root)):
        return True
    return _security_scan_is_newer(project_root)
