"""Public cross-plugin contracts for Shipwright.

This package exposes the stable, typed surface that one plugin uses to
talk to another. Implementation lives inside the source plugins
(`plugins/shipwright-*/scripts/lib/...`); the modules here are thin
facades that re-export the supported names + types so consumers do not
reach into private plugin internals via subprocess, ancestor-path-walk,
or `sys.path.insert`.

Contracts currently published:

* :mod:`shared.contracts.compliance` — wraps the compliance plugin's
  `data_collector` so adopt's compliance_bridge can call into it
  directly.
* :mod:`shared.contracts.iterate` — wraps the iterate plugin's
  `classify_complexity` (is_io_boundary_change + risk taxonomy) so the
  test plugin's boundary_coverage_report can consume it directly.

**Stability promise.** Anything re-exported from this package is part of
Shipwright's cross-plugin API. Breaking changes go through an ADR; tests
under `integration-tests/` pin the surface (see
`test_shared_contracts_consumers.py`).
"""

from __future__ import annotations

from shared.contracts import compliance, iterate

__all__ = ["compliance", "iterate"]
