"""Bridge to shipwright-compliance generator libs for adopted projects.

Calls the compliance plugin's report generators directly via the
public contract at ``shared.contracts.compliance``. No subprocess, no
ancestor-path-walk — the contract owns plugin-path resolution AND the
phase / generator dispatch tables.

Iterate B8 (2026-05-25): the legacy primary path was a subprocess call
to ``update_compliance.py`` per retroactive phase, and the legacy
fallback path walked ``Path(__file__).parents`` to locate the
compliance plugin's ``scripts/lib`` directory. Both patterns are
replaced by direct calls into ``shared.contracts.compliance``:

* :data:`shared.contracts.compliance.PHASE_REPORTS` is the single
  source of truth for the phase → reports mapping (no longer
  duplicated here — reviewer-flagged Gemini-H1 / OpenAI-H3).
* :func:`shared.contracts.compliance.run_report` invokes the named
  generator with the canonical signature, so the bridge does not need
  ``importlib.import_module`` over user-influenced names
  (reviewer-flagged Gemini-L5 / OpenAI-M10: the contract validates
  ``report_name`` against the static allowlist in
  ``GENERATORS``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Contract imports — single source of truth for both the phase table and
# the generator dispatch.
# ---------------------------------------------------------------------------

from shared.contracts.compliance import (
    PHASE_REPORTS,
    collect_all,
    run_report,
)


# Iterate B8: callers using the fallback path expect a stable set of
# reports written to disk, regardless of phase. Keep a local immutable
# tuple covering all five core docs — derived once at module load.
# Any future change to PHASE_REPORTS keys is mirrored automatically.
_ALL_FALLBACK_REPORTS: tuple[str, ...] = tuple(
    sorted({name for reports in PHASE_REPORTS.values() for name in reports})
)


def run_update_compliance(
    project_root: Path, phases: list[str] | None = None
) -> dict[str, Any]:
    """Run the compliance generators for each retroactive phase.

    Iterate B8: this function previously shelled out to
    ``update_compliance.py``. It now runs the generators in-process via
    the ``shared.contracts.compliance`` surface — orders of magnitude
    faster (no Python startup per phase) and immune to plugin-path
    breakage when ``adopt`` is invoked from a worktree.

    Returns::

        {
          "ran":    [phase, ...],
          "failed": [(phase, error_message), ...],
          "script": None,           # legacy key — kept for callers that
                                    # checked it for None to decide
                                    # whether to run the fallback. Now
                                    # always None because the in-process
                                    # path handles everything.
        }
    """
    if phases is None:
        phases = ["project", "plan", "build", "test"]
    ran: list[str] = []
    failed: list[tuple[str, str]] = []

    # Reviewer-flagged OpenAI-M10: validate ``phases`` against the
    # static allowlist BEFORE we touch any IO. Unknown phases collapse
    # to ["dashboard"] in PHASE_REPORTS.get(), which matches the
    # compliance plugin's own behavior, so this is a soft validation —
    # we log unknowns to ``failed`` rather than raising.
    valid_phases = set(PHASE_REPORTS.keys())

    # Collect data once across all phases — same pattern as
    # ``update_compliance.main``.
    try:
        data = collect_all(project_root)
    except Exception as exc:  # noqa: BLE001 — defensive top-level guard
        for phase in phases:
            failed.append((phase, f"collect_all: {exc!r}"[:500]))
        return {"ran": ran, "failed": failed, "script": None}

    for phase in phases:
        if phase not in valid_phases:
            failed.append(
                (phase, f"unknown_phase: not in PHASE_REPORTS allowlist"[:500])
            )
            continue
        reports = PHASE_REPORTS[phase]
        phase_failed = False
        for report_name in reports:
            try:
                # ``run_report`` is the contract-validated dispatch —
                # it returns None for unknown report names and invokes
                # the canonical ``generate_file(project_root, data)``
                # signature for known ones.
                if run_report(project_root, data, report_name) is None:
                    raise KeyError(f"unknown report: {report_name}")
            except Exception as exc:  # noqa: BLE001 — phase isolation
                failed.append((phase, f"{report_name}: {exc!r}"[:500]))
                phase_failed = True
                break
        if not phase_failed:
            ran.append(phase)

    return {"ran": ran, "failed": failed, "script": None}


def run_lib_fallback(project_root: Path) -> dict[str, Any]:
    """Generator-by-generator fallback that writes ALL report MDs to disk.

    Same surface as the legacy fallback: returns ``{"generated": [...],
    "skipped": [...]}``. Best-effort — failures in one generator do
    not abort the others.

    Iterate B8: the legacy implementation walked ancestors to find the
    plugin and inserted both ``scripts/lib`` and the plugin root onto
    ``sys.path``. The contract handles both. Semantics kept intact:
    write each report to its canonical
    ``.shipwright/compliance/...`` path. We exercise the full
    ``_ALL_FALLBACK_REPORTS`` set (derived once from PHASE_REPORTS at
    module load) so the fallback's output is the union of every
    phase's expected docs.
    """
    results: dict[str, Any] = {"generated": [], "skipped": []}

    try:
        data = collect_all(project_root)
        results["data_collected"] = True
    except Exception as exc:  # noqa: BLE001 — defensive
        results["skipped"].append(f"collect_all: {exc!r}")
        return results

    for report_name in _ALL_FALLBACK_REPORTS:
        try:
            out_path = run_report(project_root, data, report_name)
            if out_path is None:
                results["skipped"].append(f"{report_name}:no-generate-fn")
                continue
            try:
                rel = out_path.relative_to(project_root)
            except ValueError:
                rel = out_path
            results["generated"].append(str(rel))
        except Exception as exc:  # noqa: BLE001 — defensive per-generator
            results["skipped"].append(f"{report_name}: {exc!r}")

    return results
