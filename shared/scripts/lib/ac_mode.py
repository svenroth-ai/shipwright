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
from pathlib import Path

__all__ = ["ENV", "MODES", "resolve_mode"]

ENV = "SHIPWRIGHT_AC_MODE"
MODES = ("ask", "auto", "off")
CONFIG_FILE = "shipwright_iterate_config.json"


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
