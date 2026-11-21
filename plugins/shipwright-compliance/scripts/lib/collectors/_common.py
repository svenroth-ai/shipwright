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


CONFIG_FILES = {
    "run": _sp.rel("run_config"),
    "project": _sp.rel("project_config"),
    "plan": _sp.rel("plan_config"),
    "build": _sp.rel("build_config"),
}


def collect_configs(project_root: Path) -> dict[str, dict]:
    """Read all shipwright config files. Returns empty dicts for missing files."""
    configs: dict[str, dict] = {}
    for key, filename in CONFIG_FILES.items():
        path = project_root / filename
        if path.exists():
            configs[key] = json.loads(path.read_text(encoding="utf-8"))
        else:
            configs[key] = {}
    return configs
