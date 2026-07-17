"""Regression test for compliance_bridge.run_lib_fallback sys.path setup.

Iterate 2 Sub-2C: 3 of 5 compliance generators (sbom_generator,
change_history, test_evidence) use `from scripts.lib.mermaid import …`
which requires the plugin root (parent of `scripts/`) on sys.path,
not just `scripts/` itself. The bridge previously inserted only
`lib_dir.parent` (= `scripts/`) and the three modules failed with
`ModuleNotFoundError("No module named 'scripts'")`. This test
guards the fix.

We invoke the bridge via `seed_adopt_compliance.py` as a subprocess so the
sys.path matches the real CLI invocation — pytest's own sys.path includes
the monorepo root and would mask the bug.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Locate seed_adopt_compliance.py (this test lives at
# plugins/shipwright-adopt/tests/, so the tool is two dirs up + scripts/tools).
_THIS_DIR = Path(__file__).resolve().parent
_PLUGIN_ROOT = _THIS_DIR.parent
_SEED_TOOL = _PLUGIN_ROOT / "scripts" / "tools" / "seed_adopt_compliance.py"


def _is_module_not_found_for_scripts(skipped_entry: str) -> bool:
    """Detect the specific ModuleNotFoundError that this fix targets."""
    return (
        "ModuleNotFoundError" in skipped_entry
        and "No module named 'scripts'" in skipped_entry
    )


@pytest.fixture
def project_root_with_basics(tmp_path: Path) -> Path:
    """Create a minimal project_root that data_collector can read."""
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "completed_steps": ["project", "plan"]}),
        encoding="utf-8",
    )
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    (tmp_path / ".shipwright").mkdir()
    (tmp_path / ".shipwright" / "compliance").mkdir()
    return tmp_path


@pytest.mark.covers("FR-01.13")
def test_run_lib_fallback_no_scripts_module_error(project_root_with_basics: Path) -> None:
    """The CLI subprocess (matching real invocation) must not surface
    `ModuleNotFoundError("No module named 'scripts'")` for any of
    sbom_generator / change_history / test_evidence.
    """
    proc = subprocess.run(
        [
            sys.executable,
            str(_SEED_TOOL),
            "--project-root",
            str(project_root_with_basics),
            "--fallback",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    # The tool exits 0 even when generators are skipped (best-effort).
    assert proc.returncode == 0, (
        f"seed_adopt_compliance --fallback exited {proc.returncode}; "
        f"stderr: {proc.stderr[:500]}"
    )
    payload = json.loads(proc.stdout)
    fallback = payload.get("fallback") or {}
    skipped = fallback.get("skipped", [])
    scripts_errors = [s for s in skipped if _is_module_not_found_for_scripts(s)]
    assert not scripts_errors, (
        f"compliance_bridge.py sys.path setup is missing plugin-root: "
        f"{scripts_errors}\nFull skipped: {skipped}"
    )
