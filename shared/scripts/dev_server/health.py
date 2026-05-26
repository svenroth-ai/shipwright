"""Health probes: TCP port + HTTP readiness polling for a dev service.

Extracted from `shared/scripts/dev_server.py` during B4 split (campaign
`2026-05-25-bloat-cleanup-B-shipwright`). The producer/consumer surface
is preserved: the package-level `__init__.py` re-exports
`_is_port_in_use_for_host`, `_is_port_in_use`, `_probe_hosts_for`,
`_http_probe`, `_wait_for_service`, and `_wait_for_ready`, so existing
tests (`shared/tests/test_dev_server*.py`) and `dev_server.py` shim
callers continue to address the same names.
"""

from __future__ import annotations

import socket
import sys
import time
import urllib.error
import urllib.request


def _pkg():
    """Return the live dev_server package module (honors test monkeypatches)."""
    return sys.modules[__package__]


def _is_port_in_use_for_host(host: str, port: int) -> bool:
    """Probe whether a TCP listener is accepting connections at host:port."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            return s.connect_ex((host, port)) == 0
    except OSError:
        return False


def _is_port_in_use(port: int) -> bool:  # legacy compat for tests/import sites
    return _is_port_in_use_for_host("127.0.0.1", port) or _is_port_in_use_for_host(
        "::1", port
    )


def _probe_hosts_for(service_host: str) -> list[str]:
    """Return the list of host literals to probe for a service's host."""
    if service_host == "localhost":
        return ["127.0.0.1", "::1"]
    return [service_host]


def _http_probe(url: str, timeout: float = 2.0) -> bool:
    """Issue a GET; accept 2xx/3xx as ready. Errors / 4xx / 5xx → not ready."""
    try:
        req = urllib.request.Request(url, method="GET")
        # URL targets a local dev service (localhost/127.0.0.1 + configured port); not driven by external user input.
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            return 200 <= status < 400
    except urllib.error.HTTPError as e:
        return 200 <= e.code < 400
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _wait_for_service(service: dict, proc, deadline: float) -> tuple[bool, str]:
    """Poll until ready or deadline. See plan §AC3.

    Looks up `_is_port_in_use_for_host`, `_probe_hosts_for`, and
    `_http_probe` on the package surface at call time so test
    monkeypatches like `@patch("dev_server._is_port_in_use_for_host")`
    propagate into the wait loop.
    """
    host = service.get("host", "localhost")
    port = service["port"]
    ready_path = service.get("ready_path")
    scheme = service.get("scheme", "http")
    pkg = _pkg()
    probe_hosts = pkg._probe_hosts_for(host)

    while True:
        # 1. Liveness
        if proc is not None and proc.poll() is not None:
            return False, "process_exited"

        # 2. Port probe
        port_open_host = None
        for ph in probe_hosts:
            if pkg._is_port_in_use_for_host(ph, port):
                port_open_host = ph
                break

        if port_open_host is None:
            if time.time() >= deadline:
                return False, "timeout"
            time.sleep(0.5)
            continue

        # 3. No ready_path → port-open is enough
        if not ready_path:
            return True, ""

        # 4. HTTP probe
        url_host = host if host == "localhost" else port_open_host
        # IPv6 literal needs bracketing
        url_host_part = f"[{url_host}]" if ":" in url_host else url_host
        url = f"{scheme}://{url_host_part}:{port}{ready_path}"
        if pkg._http_probe(url, timeout=2.0):
            return True, ""

        if time.time() >= deadline:
            return False, "timeout"
        time.sleep(1.0)


def _wait_for_ready(port: int, timeout: int) -> bool:
    """Legacy: poll port until open or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        if _is_port_in_use_for_host("127.0.0.1", port) or _is_port_in_use_for_host(
            "::1", port
        ):
            return True
        time.sleep(1)
    return False
