"""engine_bridge — load the shared Control Grade engine from shipwright-compliance.

The scoring engine (``control_grade.compute_grade`` + ``GradeInputs`` /
``GradeReport``) lives in the compliance plugin and is **repo-agnostic by
design**. We reuse it UNCHANGED — the grader's whole point is that a cold-repo
grade equals the dashboard grade by construction (one engine).

Cross-plugin import (ADR-045 mitigations, plan §14 E):

- The import is **lazy** (inside :func:`load_engine`, cached), never at module
  top-level — an eager cross-plugin import would bind ``scripts.lib`` in
  ``sys.modules`` for the whole session and shadow a sibling plugin's own
  ``scripts.lib`` in a combined pytest run.
- ``control_grade`` uses absolute ``from scripts.lib._grade_gate import ...``
  imports, so we place the **compliance plugin root** on ``sys.path`` and import
  ``scripts.lib.control_grade`` normally. The grader's own modules are imported
  *bare* (never as ``scripts.lib.*``), so this package never competes for that
  dotted namespace — no collision.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

_ENV_COMPLIANCE_ROOT = "SHIPWRIGHT_GRADE_COMPLIANCE_ROOT"


class EngineUnavailableError(RuntimeError):
    """The shared Control Grade engine could not be located/imported."""


@dataclass(frozen=True)
class Engine:
    """A thin handle over the shared engine's public surface."""

    compute_grade: Callable[[Any], Any]
    GradeInputs: type
    GradeReport: type


_CACHED: Engine | None = None


def _compliance_root() -> Path | None:
    """Locate the compliance plugin root (monorepo sibling or env override)."""
    override = os.environ.get(_ENV_COMPLIANCE_ROOT)
    if override:
        cand = Path(override)
        return cand if (cand / "scripts" / "lib" / "control_grade.py").is_file() else None
    # plugins/shipwright-grade/scripts/lib/engine_bridge.py -> plugins/
    plugins_dir = Path(__file__).resolve().parents[3]
    cand = plugins_dir / "shipwright-compliance"
    if (cand / "scripts" / "lib" / "control_grade.py").is_file():
        return cand
    return None


def compliance_plugin_root() -> Path | None:
    """Public accessor for the compliance plugin root (used by reuse_bridge)."""
    return _compliance_root()


def load_engine() -> Engine:
    """Return the shared engine handle (cached). Raises on unavailability."""
    global _CACHED
    if _CACHED is not None:
        return _CACHED

    root = _compliance_root()
    if root is None:
        raise EngineUnavailableError(
            "could not locate shipwright-compliance (set "
            f"{_ENV_COMPLIANCE_ROOT} to its plugin root)"
        )

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from scripts.lib.control_grade import (  # type: ignore
            GradeInputs,
            GradeReport,
            compute_grade,
        )
    except ImportError as exc:  # pragma: no cover - defensive
        raise EngineUnavailableError(
            f"failed to import control_grade from {root}: {exc}"
        ) from exc

    _CACHED = Engine(
        compute_grade=compute_grade,
        GradeInputs=GradeInputs,
        GradeReport=GradeReport,
    )
    return _CACHED
