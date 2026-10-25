"""Resume / dispatch guard for a run started from a Brief package (campaign brief-driven-run, B2; BRIEF D2).

``single-session-resume``, ``-next`` and ``-apply`` call :func:`refusal` first: when run_config records a
Brief package, the package is re-verified against the hash recorded there, and a refusal blocks the
command in code (exit 3). A run without a package is untouched (a package directory next to it is only
a warning, see :func:`warnings`).

``shared/scripts/lib/brief_dir_intake.py`` is loaded by file path under a private module name
(ADR-045: no ``lib`` namespace import), registered BEFORE exec.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Optional

_NAME = "_shipwright_brief_resume_guard_bdi"
_BDI = Path(__file__).resolve().parents[5] / "shared" / "scripts" / "lib" / "brief_dir_intake.py"
_CONFIG = "shipwright_run_config.json"


def _load() -> Any:
    if _NAME not in sys.modules:
        spec = importlib.util.spec_from_file_location(_NAME, _BDI)
        sys.modules[_NAME] = module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(_NAME, None)
            raise
    return sys.modules[_NAME]


def _records_package(project_root: Path) -> bool:
    try:
        cfg = json.loads((Path(project_root) / _CONFIG).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    return isinstance(cfg, dict) and ("brief_dir" in cfg or "brief_package" in cfg)


def _refused(code: str, message: str) -> dict:
    return {"refused": True, "code": code, "message": message, "issues": []}


def check(project_root: Path) -> tuple[Optional[dict], list[str]]:
    """``(refusal or None, warnings)`` for the package recorded in run_config."""
    if not _BDI.is_file():  # no shared tree: fail CLOSED when the run records a package
        if _records_package(project_root):
            return _refused("intake_unavailable", f"{_BDI.name} is missing, so the recorded Brief package "
                            "cannot be verified"), []
        return None, []
    try:
        out = _load().verify_run_config(Path(project_root))
    except Exception as exc:  # noqa: BLE001 -- BriefRefused is a class per loader: duck-typed
        if hasattr(exc, "as_dict"):
            return exc.as_dict(), []
        code = "io_error" if isinstance(exc, (OSError, RuntimeError)) else "internal_error"
        return _refused(code, f"{type(exc).__name__}: {exc}"), []
    return None, list(out.get("warnings") or [])


def refusal(project_root: Path) -> Optional[dict]:
    """The structured refusal when the recorded package no longer verifies, else ``None``."""
    return check(project_root)[0]
