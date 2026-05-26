"""Package surface for `dev_server` — re-exports the pre-split public API.

Before B4 (campaign `2026-05-25-bloat-cleanup-B-shipwright`),
`shared/scripts/dev_server.py` was a single 997-LOC module. The B4
split moved the implementation into this package, organized by
cohesive sub-surface (spawn, health, profile_config, validation,
state, multiservice). To preserve the import contract used by:

  - `shared/tests/test_dev_server*.py`  (`import dev_server`)
  - `shared/scripts/dev_server.py` shim (`uv run` callers)
  - test monkeypatches like `dev_server._is_port_in_use_for_host`

every name reachable via `dev_server.X` pre-split is re-exported here.

The legacy `os`/`subprocess` module aliases at the package level are
also re-bound below so `patch("dev_server.subprocess.Popen", ...)` and
`monkeypatch.setattr(dev_server.os, "name", "nt")` continue to work
against the same objects the submodules use internally. This is
intentional — the pre-split module exposed those names via top-level
`import` statements, and tests relied on the package == submodule
identity to monkeypatch the live references.
"""

from __future__ import annotations

# Submodule references kept so tests can `patch("dev_server.subprocess.Popen")`
# style. These aliases point at the SAME module objects the implementation
# submodules use, so patching here affects both.
import os  # noqa: F401  -- re-exported for monkeypatch surface
import subprocess  # noqa: F401  -- re-exported for patch() target
import sys  # noqa: F401

# ---------------------------------------------------------------------------
# Lazy binding for resolve_executable (B3 lesson).
# We DO NOT do `from lib.cmd_resolver import resolve_executable` at module
# top because that mutates sys.modules['lib'] in the SHARED scripts path
# and shadows plugin-local `lib/` packages later in the same pytest
# session. Instead, bind a lazy proxy here that resolves on first call.
# Tests can override via `monkeypatch.setattr(dev_server, "resolve_executable", ...)`.
# ---------------------------------------------------------------------------

def _lazy_resolve_executable(name: str) -> str:
    """First-call lazy proxy → real cmd_resolver.resolve_executable.

    On first invocation, adds the shared/scripts dir to sys.path and
    imports `lib.cmd_resolver.resolve_executable`, then rebinds the
    package attribute so subsequent calls go straight to the real
    function (no recursion through this proxy).
    """
    from pathlib import Path as _Path

    scripts_dir = _Path(__file__).resolve().parent.parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from lib.cmd_resolver import resolve_executable as _real  # noqa: E402

    # Rebind the package attribute so future calls skip this proxy. We
    # only do this if the attribute is still pointing AT this proxy —
    # respect any test monkeypatch that ran first.
    pkg = sys.modules[__name__]
    if getattr(pkg, "resolve_executable", None) is _lazy_resolve_executable:
        pkg.resolve_executable = _real
    return _real(name)


resolve_executable = _lazy_resolve_executable


# ---------------------------------------------------------------------------
# Public surface re-exports.
# ---------------------------------------------------------------------------

from .profile_config import (  # noqa: E402
    PROFILE_DEV_SERVERS,
    STATE_FILE,
    STATE_VERSION,
    _DEFAULT_SERVICE,
    _PLACEHOLDER_RE,
    _expand_env,
    _get_config,
    _get_services,
    _get_services_for_test,
    _load_profile_data,
    _normalize_legacy_dev_server,
    _normalize_service_entry,
    _profiles_dir,
    _service_url,
    _services_from_profile_data,
)
from .validation import (  # noqa: E402
    LOOPBACK_HOSTS,
    _pick_primary,
    _topo_sort,
    _validate_services,
)
from .state import (  # noqa: E402
    _clear_state,
    _load_state,
    _save_state,
    _save_state_atomic,
)
from .health import (  # noqa: E402
    _http_probe,
    _is_port_in_use,
    _is_port_in_use_for_host,
    _probe_hosts_for,
    _wait_for_ready,
    _wait_for_service,
)
from .spawn import (  # noqa: E402
    _StartFailed,
    _is_pid_running,
    _kill_one,
    _rollback_and_report,
    _start_one,
)
from .multiservice import (  # noqa: E402
    _already_running_owned,
    _emit_warnings,
    cmd_start,
    cmd_start_with_services,
    cmd_status,
    cmd_stop,
)


# ---------------------------------------------------------------------------
# CLI entry point — `main_with_args` is re-exported so the existing shim
# at `shared/scripts/dev_server.py` and `python -m shared.scripts.dev_server`
# both dispatch through the same code path.
# ---------------------------------------------------------------------------

from .cli import main, main_with_args  # noqa: E402  -- after surface bound

__all__ = [
    # CLI
    "main",
    "main_with_args",
    # constants
    "STATE_FILE",
    "STATE_VERSION",
    "LOOPBACK_HOSTS",
    "PROFILE_DEV_SERVERS",
    # commands
    "cmd_start",
    "cmd_start_with_services",
    "cmd_stop",
    "cmd_status",
    # legacy helpers
    "_get_config",
    "_wait_for_ready",
    "_is_port_in_use",
    # private helpers tests address by name
    "_DEFAULT_SERVICE",
    "_PLACEHOLDER_RE",
    "_StartFailed",
    "_already_running_owned",
    "_clear_state",
    "_emit_warnings",
    "_expand_env",
    "_get_services",
    "_get_services_for_test",
    "_http_probe",
    "_is_pid_running",
    "_is_port_in_use_for_host",
    "_kill_one",
    "_load_profile_data",
    "_load_state",
    "_normalize_legacy_dev_server",
    "_normalize_service_entry",
    "_pick_primary",
    "_probe_hosts_for",
    "_profiles_dir",
    "_rollback_and_report",
    "_save_state",
    "_save_state_atomic",
    "_service_url",
    "_services_from_profile_data",
    "_start_one",
    "_topo_sort",
    "_validate_services",
    "_wait_for_service",
    # lazy module aliases
    "os",
    "subprocess",
    "resolve_executable",
]
