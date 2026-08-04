"""F0-specific adapters around the reusable repository host-resource lease."""

from __future__ import annotations

import argparse
import os
import socket
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.lib.host_resource_lease import (
    HostLeaseError,
    LeaseGrant,
    host_resource_lease,
)
from scripts.tools.suite_units import SuiteConfig

__all__ = [
    "HostLeaseError", "f0_cpu_lease", "hardware_cpu_budget",
    "lease_cpu_weight", "normalize_cpu_weight", "uv_warmup_lease",
]


def hardware_cpu_budget() -> int:
    """Host-wide F0 capacity, retaining the existing two-CPU reserve."""
    return max(1, (os.cpu_count() or 2) - 2)


def normalize_cpu_weight(requested: int | None) -> int:
    """Normalize any F0 CPU request to one satisfiable host-wide weight."""
    if requested is not None and (
            isinstance(requested, bool) or not isinstance(requested, int) or requested < 1):
        raise ValueError(f"F0 CPU weight must be a positive integer, got {requested!r}")
    capacity = hardware_cpu_budget()
    return min(requested or capacity, capacity)


def lease_cpu_weight(config: SuiteConfig) -> int:
    """Normalize every F0 request so it can fit within the host capacity."""
    return normalize_cpu_weight(config.max_workers)


def _owner(root: Path) -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{root.name}"


@contextmanager
def uv_warmup_lease(root: Path, *, run_id: str | None) -> Iterator[LeaseGrant]:
    with host_resource_lease(
            root, resource="uv-warmup", capacity=1, weight=1,
            owner=_owner(root), run_id=run_id) as grant:
        yield grant


@contextmanager
def f0_cpu_lease(root: Path, config: SuiteConfig, *,
                 run_id: str | None) -> Iterator[LeaseGrant]:
    capacity = hardware_cpu_budget()
    with host_resource_lease(
            root, resource="f0-cpu", capacity=capacity,
            weight=lease_cpu_weight(config), owner=_owner(root),
            run_id=run_id) as grant:
        yield grant


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe F0 host-resource leases.")
    parser.add_argument("--probe", action="store_true", required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--run-id", default="f0-host-resource-probe")
    args = parser.parse_args()
    root = args.project_root.resolve()
    try:
        with uv_warmup_lease(root, run_id=args.run_id):
            pass
        with f0_cpu_lease(root, SuiteConfig(max_workers=1), run_id=args.run_id):
            pass
    except HostLeaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"F0 host-resource probe: PASS run_id={args.run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
