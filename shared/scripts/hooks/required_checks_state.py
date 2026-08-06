"""Throttle + outcome state for the required-checks SessionStart producer.

Split out of `check_required_checks_hook.py` when that file reached its 300-line
budget, and modelled on `github_triage/state.py` — the sibling network producer's
own state module — down to the run-config → env → default resolution order.

**Two things are recorded, not one, and the second is the important one.**
`lastRun` bounds how often the producer may reach the network. `lastSuccess`
answers a different question: *has this check actually worked recently?* Without
it the design has a silent fail-open — the producer's documented `exit 2` covers
"no `gh`", "not authenticated" and "repo unreachable", the wrapper is silent on
that path by contract, and the attempt still consumes its window. An expired
token would therefore end the check permanently with no trace anywhere, and the
failure correlates with the event being watched: the person who rotates
credentials is often the person editing the host's rules. So a run that has not
*succeeded* for several windows says so, once.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE_FILENAME = "required_checks_state.json"
DEFAULT_THROTTLE_HOURS = 6.0
ENV_THROTTLE = "SHIPWRIGHT_REQUIRED_CHECKS_THROTTLE_HOURS"

#: How many consecutive throttle windows may pass with no SUCCESSFUL comparison
#: before the operator is told once. Deliberately several: a single failure is
#: routine (laptop offline, `gh` mid-upgrade) and speaking about it would train
#: the reader to ignore this prefix — which is the channel the undocumented-exit
#: warning depends on.
STALE_WINDOWS = 8

#: …and a wall-clock FLOOR under that, because the window is configurable down to
#: arbitrarily small values. Without it, shortening the throttle also shortens the
#: patience: a sub-second interval (what the integration tests set, and what an
#: operator debugging the producer would set) makes eight windows elapse
#: instantly, so the very first unauthenticated run reports itself as stale. The
#: operator's tolerance for "this has not worked lately" is measured in days, not
#: in multiples of a knob they may have turned for an unrelated reason.
STALE_FLOOR_DAYS = 2


def state_path(project_root: Path) -> Path:
    return Path(project_root) / ".shipwright" / STATE_FILENAME


def _read(project_root: Path) -> dict:
    try:
        return json.loads(state_path(project_root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _parse(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def throttle_hours(project_root: Path | None = None) -> float:
    """Run-config, then env, then the default.

    Mirrors `github_triage/state.py` deliberately: an operator who sets background
    cadence in `shipwright_run_config.json` — the durable, checked-in place — must
    not find that one of the two network producers honours it and the other does
    not. Non-positive or unparseable values fall through rather than disabling the
    throttle, since "0" from a typo would mean "every session".
    """
    if project_root is not None:
        try:
            raw = (Path(project_root) / "shipwright_run_config.json").read_text(
                encoding="utf-8"
            )
            cfg = json.loads(raw).get("triage")
            value = cfg.get("required_checks_throttle_hours") if isinstance(cfg, dict) else None
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
                return float(value)
        except (OSError, json.JSONDecodeError, AttributeError, TypeError):
            pass
    raw_env = os.environ.get(ENV_THROTTLE)
    if raw_env:
        try:
            parsed = float(raw_env)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return DEFAULT_THROTTLE_HOURS


def is_due(project_root: Path, *, now: datetime | None = None) -> bool:
    """True when no run is recorded, or the throttle interval has elapsed.

    Unreadable, malformed or FUTURE state reads as due. The last of those is not
    hypothetical — a restored VM snapshot, a corrected clock or a state file
    copied between machines all parse cleanly, and the elapsed comparison would
    then stay negative until wall-clock caught up: permanent silence, the one
    outcome this function's contract rules out.
    """
    now = now or datetime.now(timezone.utc)
    last = _parse(_read(project_root).get("lastRun"))
    if last is None or last > now:
        return True
    return (now - last) >= timedelta(hours=throttle_hours(project_root))


def record(project_root: Path, *, succeeded: bool,
           when: datetime | None = None) -> bool:
    """Reserve/close a window. Returns False if the state could not be written.

    ``succeeded`` carries the producer's own verdict: exit 0 means it compared,
    exit 2 means it could not read the configuration. A failed attempt still
    stamps ``lastRun`` — bounding the cost on a broken host is the whole point —
    but leaves ``lastSuccess`` where it was, which is what makes staleness
    visible.
    """
    when = when or datetime.now(timezone.utc)
    iso = when.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    doc = _read(project_root)
    doc["v"] = 1
    doc["lastRun"] = iso
    if succeeded:
        doc["lastSuccess"] = iso
        doc.pop("unhealthySince", None)
    else:
        # The START of the current unsuccessful streak, set once and then left
        # alone. Measuring staleness from `lastRun` cannot work: every attempt
        # rewrites it, so on a tree that has NEVER succeeded the reference would
        # advance with each failure and the age would be pinned at zero forever —
        # exactly the case (an expired token from day one) that staleness exists
        # to surface.
        doc.setdefault("unhealthySince", iso)
    try:
        path = state_path(project_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc), encoding="utf-8")
        return True
    except OSError:
        return False


def release(project_root: Path) -> None:
    """Give a reservation back, for a producer that never started."""
    try:
        state_path(project_root).unlink(missing_ok=True)
    except OSError:
        pass  # the stamp stands; worst case is one skipped comparison


def stale_since(project_root: Path, *, now: datetime | None = None) -> int | None:
    """Whole days since the last SUCCESSFUL comparison, if that is now overdue.

    ``None`` while healthy — including on a tree that has never succeeded and has
    never run, so a fresh clone is not greeted with a warning about a check it
    has not had the chance to perform yet.
    """
    now = now or datetime.now(timezone.utc)
    doc = _read(project_root)
    last_ok = _parse(doc.get("lastSuccess"))
    # When it last WORKED; failing that, when it started not working. Never
    # `lastRun`, which every attempt rewrites (see `record`).
    reference = last_ok if last_ok is not None else _parse(doc.get("unhealthySince"))
    if reference is None or reference > now:
        return None
    overdue = max(
        timedelta(hours=throttle_hours(project_root) * STALE_WINDOWS),
        timedelta(days=STALE_FLOOR_DAYS),
    )
    if (now - reference) < overdue:
        return None
    return max(0, (now - reference).days)
