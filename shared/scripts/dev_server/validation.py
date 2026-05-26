"""Service-list schema validation + topological dependency sort.

Extracted from `shared/scripts/dev_server.py` during B4 split (campaign
`2026-05-25-bloat-cleanup-B-shipwright`). Producer/consumer surface
preserved via package-level re-exports in `__init__.py`.

Validation runs after normalization (`profile_config._normalize_service_entry`)
so all entries here already have the canonical keys. Cycle detection
piggybacks on the topo-sort algorithm (any input that can't be fully
placed has a cycle).
"""

from __future__ import annotations

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _validate_services(services: list[dict]) -> None:
    """Validate normalized service list. Raises ValueError on any defect."""
    if not isinstance(services, list) or len(services) == 0:
        raise ValueError("services must be a non-empty list")

    names_seen: set[str] = set()
    primaries = 0
    for i, s in enumerate(services):
        name = s.get("name")
        if not name or not isinstance(name, str):
            raise ValueError(f"services[{i}].name is empty or not a string")
        if name in names_seen:
            raise ValueError(f"duplicate service name: {name}")
        names_seen.add(name)
        cmd = s.get("command")
        if not cmd or not isinstance(cmd, str):
            raise ValueError(f"services[{i}].command is missing or not a string")
        port = s.get("port")
        if not isinstance(port, int) or isinstance(port, bool):
            raise ValueError(
                f"services[{i}].port must be an integer (got {type(port).__name__})"
            )
        rts = s.get("ready_timeout_seconds", 60)
        if not isinstance(rts, int) or isinstance(rts, bool):
            raise ValueError(
                f"services[{i}].ready_timeout_seconds must be an integer "
                f"(got {type(rts).__name__} {rts!r})"
            )
        deps = s.get("depends_on") or []
        if not isinstance(deps, list):
            raise ValueError(
                f"services[{i}].depends_on must be a list of strings"
            )
        for j, d in enumerate(deps):
            if not isinstance(d, str):
                raise ValueError(
                    f"services[{i}].depends_on[{j}] must be a string "
                    f"(got {type(d).__name__} {d!r})"
                )
        host = s.get("host", "localhost")
        if host not in LOOPBACK_HOSTS:
            raise ValueError(
                f"services[{i}].host must be a loopback address "
                f"(localhost / 127.0.0.1 / ::1); got {host!r}"
            )
        if s.get("primary"):
            primaries += 1

    if primaries > 1:
        raise ValueError("multiple services declare primary: true; at most one allowed")

    # Default primary if no explicit one
    if primaries == 0:
        services[0]["primary"] = True

    # depends_on validation
    for s in services:
        deps = s.get("depends_on") or []
        for d in deps:
            if d == s["name"]:
                raise ValueError(f"service {s['name']!r} has self dependency")
            if d not in names_seen:
                raise ValueError(
                    f"service {s['name']!r} depends_on missing target {d!r}"
                )

    # Cycle check via topo sort attempt
    try:
        _topo_sort(services)
    except ValueError as e:
        if "cycle" in str(e).lower():
            raise
        raise


def _topo_sort(services: list[dict]) -> list[list[dict]]:
    """Return services grouped into layers; each layer can start in parallel.

    Within a layer, declaration order is preserved as the deterministic
    tiebreaker. Cycles raise ValueError.
    """
    by_name = {s["name"]: s for s in services}
    remaining = {s["name"]: set(s.get("depends_on") or []) for s in services}
    declaration_order = [s["name"] for s in services]

    layers: list[list[dict]] = []
    placed: set[str] = set()

    while remaining:
        # Names whose deps are all placed
        ready = [
            n for n in declaration_order
            if n in remaining and remaining[n].issubset(placed)
        ]
        if not ready:
            raise ValueError(
                f"dependency cycle detected among services: {sorted(remaining.keys())}"
            )
        layers.append([by_name[n] for n in ready])
        for n in ready:
            placed.add(n)
            del remaining[n]

    return layers


def _pick_primary(services: list[dict]) -> dict:
    for s in services:
        if s.get("primary"):
            return s
    return services[0]
