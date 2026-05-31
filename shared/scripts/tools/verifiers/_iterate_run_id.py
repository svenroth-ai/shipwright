"""run_id-resolution guard for the iterate spec checks (S2/S3).

Layer 2 of iterate-2026-05-31-phasequality-triage-bundle. When the resolved
run_id is a sentinel (``""`` / ``"unknown"`` — emitted by the phase-quality
Stop audit when no iterate run_id is resolvable) or has no exact
``iterate_history`` entry, AND no matching spec/mini-plan file is on disk,
S2/S3 SKIP — instead of tail-falling-back to the most-recent entry's
complexity and emitting an unsatisfiable FAIL. A matching file on disk
preserves the file-exists -> PASS signal.

Extracted into its own module (rather than inlined in ``spec_checks.py``) to
keep that already-grandfathered file under its bloat baseline.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.phase_quality import STATUS_SKIP, make_finding  # noqa: E402

_RUN_ID_SENTINELS = frozenset({"", "unknown"})


def has_exact_iterate_entry(project_root: Path, run_id: str) -> bool:
    """True when ``run_id`` matches an ``iterate_history`` entry EXACTLY.

    Unlike ``spec_checks._read_iterate_entry``, this does NOT tail-fall-back
    to the most-recent entry — a sentinel run_id must not inherit the latest
    iterate's complexity.
    """
    if not run_id or run_id.lower() in _RUN_ID_SENTINELS:
        return False
    from lib.iterate_entry import read_iterate_entries

    try:
        entries = read_iterate_entries(project_root)
    except Exception:  # noqa: BLE001 — fail-safe: treat as no exact match
        return False
    return any(
        isinstance(e, dict) and e.get("run_id") == run_id
        for e in (entries or [])
    )


def unresolvable_run_id_skip(
    project_root: Path,
    run_id: str,
    candidates: list[Any],
    check_id: str,
    name: str,
    provenance: str | None = None,
) -> dict[str, Any] | None:
    """Return a SKIP finding when ``run_id`` is unresolvable AND no file on disk.

    Returns ``None`` (caller proceeds with normal logic) when ``run_id`` has
    an exact ``iterate_history`` entry OR a matching spec/mini-plan file
    already exists (``candidates`` non-empty) — so the file-exists -> PASS
    signal is preserved.
    """
    if has_exact_iterate_entry(project_root, run_id) or candidates:
        return None
    kw: dict[str, Any] = {"name": name}
    if provenance:
        kw["provenance"] = provenance
    return make_finding(
        check_id, STATUS_SKIP,
        f"run_id={run_id} is not a resolvable iterate run "
        "(no exact iterate_history entry, no matching file) — "
        "spec check not applicable in this audit context",
        **kw,
    )
