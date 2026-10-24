"""Profile access for ``performance_check`` (split out: that file is bloat-grandfathered).

The budgets live in the stack profile's ``testing.performance``. The profile is
resolved by NAME (project > user > bundled) or read from an explicit file; an
unknown, corrupt or too-new profile is an ERROR, never "continue with no budgets".
A run config that names nothing, or a reserved sentinel (``generic`` /
``detecting``), means "no profile": an explicit skip, exit 0.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SHARED = str(Path(__file__).resolve().parents[4] / "shared" / "scripts")
_ADDED = _SHARED not in sys.path
if _ADDED:
    sys.path.append(_SHARED)
import profile_consumer as pc  # noqa: E402

if _ADDED:  # shared/scripts holds a `tools` package that would shadow this plugin's own
    sys.path.remove(_SHARED)

NO_PROFILE_REASON = "no budgets (no profile)"
PROFILE_KEYS_READ = ("testing",)  # D6: consumed profile keys (checked against the schema)


def load_profile_perf(profile, profile_path, project_root):
    """-> ``(testing.performance | None, source | None, no_profile)``; ValueError on a bad profile."""
    project_root = Path(project_root).resolve()
    profile, profile_path, from_path = pc.name_over_bundled_path(profile, profile_path)
    if profile_path:
        res = pc.load_explicit(profile_path, project_root)
    else:
        name, origin = profile, "--profile-path" if from_path else "--profile"
        if not name:
            name, origin = pc.config_profile(project_root), pc.RUN_CONFIG
        if not name:
            return None, None, True
        res = pc.resolve_named(name, project_root, origin=origin)
    if res.source == "builtin":
        return None, res.source, True
    return (res.data.get("testing") or {}).get("performance"), res.source, False


def report_failure(exc: ValueError) -> int:
    """Print the error (stderr text + a JSON object on stdout) and return the exit code."""
    sys.stderr.write(f"error: {exc}\n")
    print(json.dumps({"success": False, **pc.error_fields(exc)}, indent=2))
    return pc.exit_code(exc)
