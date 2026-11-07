"""How the pre-build acceptance-criterion decision treats its questions: ``ask``, ``auto`` or ``off``.

* ``ask``  - the operator confirms every question (default for an interactive iterate).
* ``auto`` - Shipwright takes its own pick without asking (the model's requirement, else the best match by shared words, else a new
  requirement drafted by Shipwright); every such decision is recorded as unconfirmed and listed at the end of the run
  (:func:`lib.ac_auto.unconfirmed_lines`). The default under ``--autonomous`` / an unattended campaign unit, so an ask never stops a unit.
* ``off``  - the decision does nothing: no question, no record, no F11 warning.

Where it is set, highest first: the ``--ac-mode`` flag (the campaign orchestrator passes the campaign's own setting), the
``SHIPWRIGHT_AC_MODE`` variable, ``ac_decision.mode`` in the project's ``shipwright_iterate_config.json``, then the default above.
An unknown value is an error, never a silent default. Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

__all__ = ["ENV", "MODES", "is_safe_run_id", "marker_path", "read_marker", "resolve_mode", "source_label", "write_marker"]

ENV = "SHIPWRIGHT_AC_MODE"
MODES = ("ask", "auto", "off")
CONFIG_FILE = "shipwright_iterate_config.json"


def is_safe_run_id(run_id: object) -> bool:
    """A plain run id (letters, digits, ``_ . -``, no ``..``) - the same rule ``write_plan_stub.py`` applies; it is used as a directory name."""
    return isinstance(run_id, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", run_id) is not None and ".." not in run_id


def source_label(source: str) -> str:
    """``flag`` | ``env`` | ``config`` | ``default`` for a source returned by :func:`resolve_mode`."""
    return {"--ac-mode": "flag", ENV: "env", CONFIG_FILE: "config"}.get(source, "default")


def marker_path(project_root: str | Path, run_id: str) -> Path:
    return Path(project_root) / ".shipwright" / "planning" / "iterate" / run_id / "ac-mode.json"


def write_marker(project_root: str | Path, run_id: str, mode: str, source: str) -> tuple[Path, bool]:
    """Write the mode the tool actually used for this run beside the AC record (code writes it, committed with the run), so F11 sees a ``--ac-mode`` flag too.

    The FIRST marker of a run is kept: a later run with another mode returns ``(path, True)`` and changes nothing, so re-running with ``--ac-mode off``
    cannot silence the F11 check of a run that already decided otherwise.
    """
    path = marker_path(project_root, run_id)
    if read_marker(project_root, run_id):
        return path, True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"run_id": run_id, "mode": mode, "source": source_label(source)}, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return path, False


def read_marker(project_root: str | Path, run_id: str, commit: str = "") -> dict:
    """The run's mode marker (read from ``commit`` when given, else the working tree); ``{}`` when absent or unreadable."""
    rel = f".shipwright/planning/iterate/{run_id}/ac-mode.json"
    try:
        if commit:
            from lib.ac_surface import read_blobs  # a sibling lib import, kept lazy so this module stays stdlib-only at import time
            text = read_blobs(project_root, commit, [rel]).get(rel) or ""
        else:
            text = marker_path(project_root, run_id).read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, ValueError, RuntimeError):
        return {}
    return data if isinstance(data, dict) and data.get("mode") in MODES else {}


def _project_mode(project_root: str | Path) -> str:
    try:
        data = json.loads((Path(project_root) / CONFIG_FILE).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return ""
    except (OSError, ValueError) as exc:
        raise ValueError(f"{CONFIG_FILE} is unreadable ({exc}); fix it or pass --ac-mode") from exc
    block = data.get("ac_decision") if isinstance(data, dict) else None
    return str(block.get("mode") or "") if isinstance(block, dict) else ""


def resolve_mode(project_root: str | Path = ".", cli: str = "", unattended: bool = False) -> tuple[str, str]:
    """``(mode, where it came from)``; raises ``ValueError`` for a value that is not ask, auto or off."""
    for source, raw in (("--ac-mode", cli), (ENV, os.environ.get(ENV, "")), (CONFIG_FILE, _project_mode(project_root))):
        value = str(raw or "").strip().lower()
        if value:
            if value not in MODES:
                raise ValueError(f"{source}: ac mode must be one of {', '.join(MODES)}, not {raw!r}")
            return value, source
    return ("auto", "default (unattended)") if unattended else ("ask", "default")
