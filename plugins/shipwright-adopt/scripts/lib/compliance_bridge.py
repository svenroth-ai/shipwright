"""Bridge to shipwright-compliance generator libs for adopted projects.

Primary path: subprocess-call update_compliance.py per retroactive phase
marker. Fallback: direct library imports for full-suite generation.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from typing import Any


def _compliance_script(project_root: Path) -> Path | None:
    """Locate update_compliance.py — walk up from project_root to find plugins/."""
    # Primary: look relative to this file (same monorepo)
    here = Path(__file__).resolve()
    for ancestor in [here, *here.parents]:
        candidate = ancestor.parent / "plugins" / "shipwright-compliance" / "scripts" / "tools" / "update_compliance.py"
        if candidate.exists():
            return candidate
    return None


def run_update_compliance(
    project_root: Path, phases: list[str] | None = None
) -> dict[str, Any]:
    """Run update_compliance.py for each retroactive phase. Non-blocking on errors.

    Returns {"ran": [phase, ...], "failed": [(phase, stderr), ...], "script": path|None}.
    """
    if phases is None:
        phases = ["project", "plan", "build", "test"]
    script = _compliance_script(project_root)
    if script is None:
        return {"ran": [], "failed": [], "script": None, "skipped_reason": "script_not_found"}
    ran: list[str] = []
    failed: list[tuple[str, str]] = []
    for phase in phases:
        try:
            result = subprocess.run(
                ["uv", "run", str(script), "--phase", phase, "--project-root", str(project_root)],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if result.returncode == 0:
                ran.append(phase)
            else:
                failed.append((phase, result.stderr.strip()[:500]))
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            failed.append((phase, str(e)[:500]))
    return {"ran": ran, "failed": failed, "script": str(script)}


def run_lib_fallback(project_root: Path) -> dict[str, Any]:
    """Direct library import fallback — calls each generator via Python import.

    Useful when update_compliance.py is unavailable or produces partial output.
    Best-effort: skips gracefully on missing modules.
    """
    results: dict[str, Any] = {"generated": [], "skipped": []}
    # Try to locate the compliance plugin's lib dir and add to sys.path
    here = Path(__file__).resolve()
    lib_dir: Path | None = None
    for ancestor in [here, *here.parents]:
        candidate = ancestor.parent / "plugins" / "shipwright-compliance" / "scripts" / "lib"
        if candidate.exists():
            lib_dir = candidate
            break
    if lib_dir is None:
        results["skipped"].append("compliance_lib_not_found")
        return results
    # Also add scripts/ so its internal relative imports resolve
    sys.path.insert(0, str(lib_dir.parent))
    # And the plugin root, so generators that do `from scripts.lib.X import Y`
    # (sbom_generator, change_history, test_evidence) can resolve `scripts`
    # as a namespace package. Without this, those three modules failed with
    # ModuleNotFoundError("No module named 'scripts'") while rtm_generator
    # and compliance_report (which don't use that import pattern) succeeded.
    sys.path.insert(0, str(lib_dir.parent.parent))
    try:
        # Import data_collector for ComplianceData
        from lib import data_collector  # type: ignore
        data = data_collector.collect_all(project_root)
        results["data_collected"] = True
    except Exception as e:  # pragma: no cover — defensive
        results["skipped"].append(f"collect_all: {e!r}")
        return results
    # Call each generator if importable
    _COMPLIANCE_DIR = ".shipwright/compliance"
    for mod_name, output_name in [
        ("sbom_generator", f"{_COMPLIANCE_DIR}/sbom.md"),
        ("change_history", f"{_COMPLIANCE_DIR}/change-history.md"),
        ("rtm_generator", f"{_COMPLIANCE_DIR}/traceability-matrix.md"),
        ("test_evidence", f"{_COMPLIANCE_DIR}/test-evidence.md"),
        ("compliance_report", f"{_COMPLIANCE_DIR}/dashboard.md"),
    ]:
        try:
            # `mod_name` comes from the hardcoded for-loop allowlist above (sbom_generator, change_history, etc.), not user input.
            # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
            mod = importlib.import_module(f"lib.{mod_name}")
            out = mod.generate(data) if hasattr(mod, "generate") else None
            if out is not None:
                out_path = project_root / output_name
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(out, encoding="utf-8")
                results["generated"].append(output_name)
            else:
                results["skipped"].append(f"{mod_name}:no-generate-fn")
        except Exception as e:  # pragma: no cover — defensive
            results["skipped"].append(f"{mod_name}: {e!r}")
    return results
