"""Shared runtime helpers for compliance collectors.

Hosts the small cross-collector utilities (config-file lookup + read).
Dataclass definitions live in ``_types.py``; keeping helpers separate
keeps both files well under the 300-LOC budget.

Iterate Campaign B (B2): split out of ``data_collector.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys as _sys, pathlib as _pl; _p = str(_pl.Path(__file__).resolve().parents[5] / "shared" / "scripts" / "lib"); _a = _p not in _sys.path; _a and _sys.path.append(_p); import shipwright_paths as _sp; _a and _sys.path.remove(_p)  # noqa: E402


#: config key -> resolver key (R1c-2: a moving config is found in either layout)
CONFIG_KEYS = {"run": "run_config", "project": "project_config", "plan": "plan_config", "build": "build_config"}
#: config key -> FILE NAME (a label; :func:`config_path` resolves the place), derived from CONFIG_KEYS (R1c-3)
CONFIG_FILES = {key: _sp.name(rk) for key, rk in CONFIG_KEYS.items()}


def config_path(key: str, project_root: Path) -> Path:
    """Where the *key* config (``CONFIG_FILES`` key) lives under *project_root*."""
    return _sp.path(CONFIG_KEYS[key], project_root)


def collect_configs(project_root: Path) -> dict[str, dict]:
    """Read all shipwright config files. Returns empty dicts for missing files."""
    configs: dict[str, dict] = {}
    for key in CONFIG_FILES:
        path = config_path(key, project_root)
        if path.exists():
            configs[key] = json.loads(path.read_text(encoding="utf-8"))
        else:
            configs[key] = {}
    return configs
