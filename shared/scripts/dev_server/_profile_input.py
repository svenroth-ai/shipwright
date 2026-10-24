"""Profile resolution + numeric coercion for `profile_config` (split out: 300-line limit).

Private to `dev_server`; `profile_config` re-exports what the package surface needs.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any


PROFILE_KEYS_READ = ("services", "dev_server")  # D6: consumed profile keys (checked against the schema)


def _pkg():
    """Return the live dev_server package module (honors test monkeypatches)."""
    return sys.modules[__package__]


def _coerce_int(value: Any, field: str, lo: int, hi: int) -> Any:
    """Integral floats (3000.0) become ints; NaN/Infinity/out-of-range raise ValueError.

    `json.load` accepts NaN, Infinity and 1e300, and `int()` of the first two raises
    OverflowError/ValueError with a bare traceback. Other types pass through for
    `_validate_services` to report.
    """
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a whole number (got {value!r})")
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError(f"{field} must be a whole number (got {value!r})")
        value = int(value)
    elif isinstance(value, str):
        try:
            value = int(value)
        except ValueError:
            raise ValueError(f"{field} must be a whole number (got {value!r})") from None
    if isinstance(value, int) and not lo <= value <= hi:
        raise ValueError(f"{field} must be between {lo} and {hi} (got {value})")
    return value


def _resolve_profile(profile_name: str | None, project_root: Path | None):
    """Resolve through the stack-profile resolver (project > user > bundled).

    Returns the ResolvedProfile, or None when no profile was named. Errors are the
    resolver's (ValueError with `.kind`) - a broken or unknown profile NEVER becomes
    "no profile". The bundled dir still comes from `_profiles_dir()` through the
    package surface, so tests that monkeypatch `dev_server._profiles_dir` take effect.
    """
    if not profile_name:
        return None
    from ._paths import _ensure_scripts_on_path
    _ensure_scripts_on_path()  # already on sys.path since `state.py` imported
    import profile_consumer as pc

    dirs = pc.search_dirs_with_bundled(project_root, str(_pkg()._profiles_dir()))
    return pc.resolve_named(profile_name, project_root, origin="--profile", search_dirs=dirs)
