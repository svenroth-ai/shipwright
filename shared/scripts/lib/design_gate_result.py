"""Result type shared by the /shipwright-design gate modules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GateResult:
    ok: bool
    detail: str
    warnings: tuple[str, ...] = ()
