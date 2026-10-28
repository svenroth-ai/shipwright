"""The F-phase scripts must import in a consumer project that has no PyYAML.

F11 runs ``uv run "{shared_root}/scripts/tools/deliver_pr.py"`` inside the
*consumer* project, where ``uv run`` resolves only that project's dependencies.
``deliver_pr`` once died at import (``ModuleNotFoundError: No module named
'yaml'``) because ``lib.automerge_readiness`` imported PyYAML at module level
for a function the delivery path never calls — it only needs the
``POSTED_STATUS_CONTEXTS`` constant. The yaml import is now local to
``workflow_report``.

Each script is imported in a fresh interpreter with ``yaml`` blocked, so a
module-level (or transitive) ``import yaml`` anywhere in the chain fails here
instead of in a consumer repo.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SHARED = REPO / "shared"
REFS = REPO / "plugins" / "shipwright-iterate" / "skills" / "iterate" / "references"

# Blocks yaml, then imports the script as a module (not as __main__).
_PROBE = """
import importlib.abc, importlib.util, sys

class _BlockYaml(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name == "yaml" or name.startswith("yaml."):
            raise ModuleNotFoundError("No module named 'yaml' (blocked by test)")
        return None

sys.meta_path.insert(0, _BlockYaml())
sys.modules.pop("yaml", None)
# Register in sys.modules BEFORE exec (ADR-045 loader shape): a module that is
# missing from sys.modules breaks module-level @dataclass under
# `from __future__ import annotations`, which would die for a reason unrelated
# to yaml and hide a later yaml import behind it.
spec = importlib.util.spec_from_file_location("probe_target", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
sys.modules["probe_target"] = mod
spec.loader.exec_module(mod)
"""


def _documented_shared_scripts() -> list[str]:
    """Every ``{shared_root}/scripts/...py`` the iterate skill and references run."""
    found: set[str] = set()
    for md in [*REFS.glob("*.md"), REFS.parent / "SKILL.md"]:
        text = md.read_text(encoding="utf-8")
        found.update(re.findall(r'\{shared_root\}/(scripts/[\w/.-]+\.py)', text))
    return sorted(found)


def _import_without_yaml(script: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _PROBE, str(script)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120, cwd=str(script.parent),
        env={**{k: v for k, v in os.environ.items()
                if k not in ("PYTHONPATH", "PYTHONSAFEPATH")},
             "PYTHONIOENCODING": "utf-8"},
    )


@pytest.mark.covers("FR-01.11/AC16")
def test_deliver_pr_import_chain_needs_no_yaml():
    result = _import_without_yaml(SHARED / "scripts" / "tools" / "deliver_pr.py")
    assert result.returncode == 0, result.stderr[-2000:]


@pytest.mark.covers("FR-01.11/AC16")
def test_probe_really_blocks_yaml(tmp_path):
    """Guard the guard: the blocker must fail a module that imports yaml."""
    probe = tmp_path / "needs_yaml.py"
    probe.write_text("import yaml\n", encoding="utf-8")
    result = _import_without_yaml(probe)
    assert result.returncode != 0
    assert "yaml" in result.stderr


@pytest.mark.covers("FR-01.11/AC16")
def test_documented_scripts_are_discovered():
    scripts = _documented_shared_scripts()
    assert "scripts/tools/deliver_pr.py" in scripts
    assert len(scripts) > 10


@pytest.mark.covers("FR-01.11/AC16")
@pytest.mark.parametrize("rel", _documented_shared_scripts())
def test_documented_f_phase_script_imports_without_yaml(rel: str):
    script = SHARED / rel
    if not script.exists():
        raise AssertionError(f"{rel} is referenced by the iterate references but missing")
    result = _import_without_yaml(script)
    assert result.returncode == 0, (
        f"{rel} does not import cleanly with PyYAML blocked. If the cause is "
        f"yaml, make that import local to the function that parses YAML; in a "
        f"consumer project it is a crash.\n{result.stderr[-1500:]}"
    )
