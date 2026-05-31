"""Profile loading + service-entry normalization + URL helpers + legacy config.

Extracted from `shared/scripts/dev_server.py` during B4 split (campaign
`2026-05-25-bloat-cleanup-B-shipwright`). Producer/consumer surface
preserved via package-level re-exports in `__init__.py`.

This module is the configuration surface — it turns profile JSON (or
inline `--services-json`, or `shipwright_build_config.json#dev_url`)
into a normalized list[dict] that `validation._validate_services`
accepts. Constants exported here (`STATE_FILE`, `STATE_VERSION`,
`LOOPBACK_HOSTS`, `_DEFAULT_SERVICE`, `PROFILE_DEV_SERVERS`) are
re-exported at the package level for legacy callers.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Re-imported in __init__.py for the package-level surface.
from .validation import _validate_services


def _pkg():
    """Return the live dev_server package module (honors test monkeypatches)."""
    return sys.modules[__package__]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATE_FILE = "shipwright_dev_server.json"
STATE_VERSION = 2

# Default service used if no profile / no build_config / no inline JSON.
_DEFAULT_SERVICE: dict[str, Any] = {
    "name": "primary",
    "command": "npm run dev",
    "host": "localhost",
    "scheme": "http",
    "port": 3000,
    "ready_path": "/",
    "ready_timeout_seconds": 60,
    "primary": True,
}

# Profile-specific dev_server overrides (legacy single-service map).
PROFILE_DEV_SERVERS: dict[str, dict] = {
    "supabase-nextjs": {
        "command": "npm run dev",
        "port": 3000,
        "ready_timeout_seconds": 60,
        "ready_path": "/",
    },
}


# Matches ${VAR} or ${VAR:-default}. Var name follows shell convention
# (uppercase + underscore + digits, leading non-digit).
_PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _expand_env(value: Any) -> Any:
    """Expand ${VAR} / ${VAR:-default} placeholders in a string.

    Non-string values pass through unchanged. Used so profiles can declare
    e.g. `"port": "${PORT:-3847}"` and have adopt override via env without
    ever editing the profile file.
    """
    if not isinstance(value, str):
        return value

    def _sub(m: re.Match) -> str:
        var_name = m.group(1)
        default = m.group(2) if m.group(2) is not None else ""
        return os.environ.get(var_name, default)

    return _PLACEHOLDER_RE.sub(_sub, value)


# ---------------------------------------------------------------------------
# Profile loading
# ---------------------------------------------------------------------------

def _profiles_dir() -> Path:
    """Resolve the shared/profiles directory relative to this script.

    Walks up from this submodule: dev_server/profile_config.py →
    dev_server/ → scripts/ → shared/ → shared/profiles. The original
    `dev_server.py` lived at scripts/dev_server.py (one level shallower),
    so we walk one extra step here to land on the same directory.
    """
    return Path(__file__).resolve().parent.parent.parent / "profiles"


def _load_profile_data(profile_name: str | None) -> dict | None:
    """Load <profiles_dir>/<name>.json. Falls back to PROFILE_DEV_SERVERS map.

    The `_profiles_dir` call goes through the package surface so tests
    that monkeypatch `dev_server._profiles_dir` (to point at a tmp_path
    fixture) take effect.
    """
    if not profile_name:
        return None
    profiles_dir = _pkg()._profiles_dir()
    candidate = profiles_dir / f"{profile_name}.json"
    if candidate.exists():
        try:
            return json.loads(candidate.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    # Fallback: legacy in-script map for very old callers
    if profile_name in PROFILE_DEV_SERVERS:
        return {"dev_server": PROFILE_DEV_SERVERS[profile_name]}
    return None


def _normalize_legacy_dev_server(block: dict) -> dict:
    """Wrap a legacy `dev_server` block as a single-service entry."""
    return {
        "name": "primary",
        "command": block.get("command", _DEFAULT_SERVICE["command"]),
        "host": block.get("host", "localhost"),
        "scheme": block.get("scheme", "http"),
        "port": int(block.get("port", _DEFAULT_SERVICE["port"])),
        "ready_path": block.get("ready_path", _DEFAULT_SERVICE["ready_path"]),
        "ready_timeout_seconds": int(
            block.get("ready_timeout_seconds", _DEFAULT_SERVICE["ready_timeout_seconds"])
        ),
        "primary": True,
    }


def _normalize_service_entry(entry: dict, default_primary: bool = False) -> dict:
    """Apply defaults to a `services[]` entry.

    Expands ${VAR}/${VAR:-default} placeholders in `command`, `ready_path`,
    and string `port`. After expansion, a string `port` is coerced to int
    (so a profile may declare `"port": "${PORT:-3847}"`); a non-numeric
    expansion is left as-is and produces a clear `_validate_services`
    error rather than crashing here.
    """
    raw_port = entry.get("port")
    expanded_port: Any = raw_port
    if isinstance(raw_port, str):
        substituted = _expand_env(raw_port)
        try:
            expanded_port = int(substituted)
        except (TypeError, ValueError):
            expanded_port = substituted  # _validate_services will reject

    return {
        "name": entry.get("name"),
        "command": _expand_env(entry.get("command")),
        "host": entry.get("host", "localhost"),
        "scheme": entry.get("scheme", "http"),
        "port": expanded_port,
        "ready_path": _expand_env(entry.get("ready_path")),
        "ready_timeout_seconds": entry.get("ready_timeout_seconds", 60),
        "depends_on": entry.get("depends_on") or [],
        "primary": bool(entry.get("primary", default_primary)),
    }


def _service_url(service: dict) -> str:
    host = service.get("host", "localhost")
    scheme = service.get("scheme", "http")
    port = service["port"]
    # IPv6 needs bracketing in URLs
    host_part = f"[{host}]" if ":" in str(host) else host
    return f"{scheme}://{host_part}:{port}"


def _get_services(
    profile_name: str | None, cwd: Path
) -> tuple[list[dict], list[str]]:
    """Resolve a normalized service list + warning messages."""
    warnings: list[str] = []
    profile_data = _load_profile_data(profile_name)
    return _services_from_profile_data(profile_data, cwd, warnings)


def _services_from_profile_data(
    profile_data: dict | None, cwd: Path, warnings: list[str]
) -> tuple[list[dict], list[str]]:
    if profile_data and "services" in profile_data:
        if "dev_server" in profile_data:
            warnings.append(
                "both 'services' and 'dev_server' present in profile; ignoring 'dev_server'"
            )
        raw = profile_data["services"]
        if not isinstance(raw, list) or len(raw) == 0:
            raise ValueError("profile 'services' must be a non-empty array")
        services: list[dict] = []
        for i, entry in enumerate(raw):
            if not isinstance(entry, dict):
                raise ValueError(f"services[{i}] must be an object")
            services.append(_normalize_service_entry(entry))
        return services, warnings

    if profile_data and "dev_server" in profile_data:
        return [_normalize_legacy_dev_server(profile_data["dev_server"])], warnings

    # Build config fallback
    build_config = cwd / "shipwright_build_config.json"
    if build_config.exists():
        try:
            data = json.loads(build_config.read_text(encoding="utf-8"))
            dev_url = data.get("dev_url")
            if dev_url:
                parsed = urlparse(dev_url)
                host = parsed.hostname or "localhost"
                scheme = parsed.scheme or "http"
                port = parsed.port or 3000
                return ([{
                    **_DEFAULT_SERVICE,
                    "host": host,
                    "scheme": scheme,
                    "port": port,
                }], warnings)
        except (json.JSONDecodeError, OSError):
            pass

    return [dict(_DEFAULT_SERVICE)], warnings


# Test-friendly accessor: lets tests pass profile_data inline instead of a name.
def _get_services_for_test(
    profile_data: dict | None, cwd: Path
) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    services, warnings = _services_from_profile_data(profile_data, cwd, warnings)
    _validate_services(services)
    return services, warnings


# ---------------------------------------------------------------------------
# Backwards-compat: legacy single-service config dict
# ---------------------------------------------------------------------------

def _get_config(profile: str | None, cwd: Path | None = None) -> dict:
    """Legacy: return a single-service config dict."""
    if profile and profile in PROFILE_DEV_SERVERS:
        return dict(PROFILE_DEV_SERVERS[profile])
    if cwd:
        build_config = cwd / "shipwright_build_config.json"
        if build_config.exists():
            try:
                data = json.loads(build_config.read_text(encoding="utf-8"))
                dev_url = data.get("dev_url", "")
                if dev_url:
                    parsed = urlparse(dev_url)
                    port = parsed.port or 3000
                    return {
                        "command": _DEFAULT_SERVICE["command"],
                        "port": port,
                        "ready_timeout_seconds": _DEFAULT_SERVICE["ready_timeout_seconds"],
                        "ready_path": _DEFAULT_SERVICE["ready_path"],
                    }
            except (json.JSONDecodeError, OSError):
                pass
    return {
        "command": _DEFAULT_SERVICE["command"],
        "port": _DEFAULT_SERVICE["port"],
        "ready_timeout_seconds": _DEFAULT_SERVICE["ready_timeout_seconds"],
        "ready_path": _DEFAULT_SERVICE["ready_path"],
    }
