"""Facts derived from ``shipwright_run_config.json``, read by more than one plugin.

Kept deliberately small and stdlib-only. Lives at ``shared/scripts/`` top level
(the ``triage.py`` precedent) rather than ``shared/scripts/lib/`` — ADR-045:
a shared module inside a ``lib/`` namespace shadows a plugin's own
``scripts/lib/`` when the plugin puts ``shared/scripts`` on ``sys.path``, which
turns into a green local run and a red CI one.

Currently one fact: **was this project onboarded from an existing codebase?**
That answer routes decisions in two places already (the compliance dashboard's
adopted-project rendering, and the test phase's greenfield-blocks /
brownfield-files-a-follow-up split), so it gets one definition rather than two.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys as _sys, pathlib as _pl; _p = str(_pl.Path(__file__).resolve().parents[0] / "lib"); _a = _p not in _sys.path; _a and _sys.path.append(_p); import shipwright_paths as _sp; _a and _sys.path.remove(_p)  # noqa: E402

RUN_CONFIG_NAME = _sp.name("run_config")


def read_run_config(project_root: Path | str) -> dict:
    """Return the parsed run config, or ``{}`` when absent / unreadable.

    Tolerant by design: every caller here is answering "which flavour of
    project is this?", and a missing or corrupt config must degrade to the
    conservative answer, never raise into a phase.
    """
    try:  # path() inside: two copies (LayoutError) also degrade to the conservative answer
        data = json.loads(_sp.path("run_config", Path(project_root)).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError, _sp.LayoutError):
        return {}
    return data if isinstance(data, dict) else {}


def is_adopted_run_config(run_config: dict) -> bool:
    """True when this run config describes a project onboarded via /shipwright-adopt.

    The signal is the presence of a non-empty ``adoption`` object (carrying
    ``adopted_at``, ``commit_at_adoption``, ...). Chosen empirically in
    Iterate B.1 (2026-05-21) over ``scope``, which carries ``"library"`` /
    ``"full_app"`` — orthogonal to adoption status.
    """
    adoption = run_config.get("adoption")
    return isinstance(adoption, dict) and bool(adoption)


def is_adopted_project(project_root: Path | str) -> bool:
    """``is_adopted_run_config`` over the project's config on disk."""
    return is_adopted_run_config(read_run_config(project_root))


__all__ = [
    "RUN_CONFIG_NAME",
    "is_adopted_project",
    "is_adopted_run_config",
    "read_run_config",
]
