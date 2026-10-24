"""The enforced phase gate finds the canon verifiers in EVERY layout the run plugin ships in.

A5 precondition for turning enforcement on: ``phase_gate.evaluate_gate`` promotes a degraded
canon run (``tools.verifiers`` not importable) to an ask-level finding, so a layout in which
``shared/scripts/tools/verifiers`` does not resolve would stop EVERY enforced apply on a
non-retryable ``canon_degraded``. ``phase_validators`` finds ``shared/`` five directories
up from its own file, so each layout below is a real tree, copied, and probed in a fresh
isolated interpreter (``-I``: nothing from this test process leaks in) that runs the REAL
gate over a minimal valid project and must come back clean:

    installed   ~/.claude/plugins/cache/shipwright/shipwright-run/<version>/   (CLAUDE_PLUGIN_ROOT)
                ~/.claude/plugins/cache/shipwright/shared/
    mirror      ~/.claude/plugins/cache/shipwright/plugins/shipwright-run/      (the cache's
                ~/.claude/plugins/cache/shipwright/shared/                      plugins/ tree)
    codex       ~/.codex/plugins/cache/shipwright/shipwright/<version>/origin/shipwright-run/
                ~/.codex/plugins/cache/shipwright/shipwright/<version>/shared/  (one umbrella
                bundle, ``shared/scripts/tools/build_codex_plugin.py``)
    checkout    <repo>/plugins/shipwright-run/ + <repo>/shared/   (this checkout as-is: the
                dev repo, or a git worktree under .worktrees/, which has the same shape)

The ``shared/`` tree must actually be there: a plain ``claude plugin install`` does not copy
it, the SessionStart healer (``ensure_shared_cache.py``) mirrors it from the marketplace
clone. Where the verifiers are missing the gate fails CLOSED (the negative control below):
it never passes.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.covers("FR-01.01/AC02")

_PLUGIN = Path(__file__).resolve().parents[1]
_REPO = _PLUGIN.parents[1]
_TESTKIT = _REPO / "shared" / "testkit"
_SKIP = shutil.ignore_patterns("tests", "__pycache__", "*.pyc", ".venv", ".pytest_cache",
                               ".coverage*", "uv.lock")

_PROBE = """
import json, sys
from pathlib import Path
lib, testkit, project = sys.argv[1:4]
sys.path.insert(0, lib)
sys.path.insert(0, testkit)
import importlib, importlib.util
from datetime import datetime, timezone
import minimal_valid_project as mvp
from orchestrator import create_config
from orchestrator_pkg import phase_gate
root = Path(project)
cfg = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", root,
                    mode="single_session")
task = {"phase": "project", "splitId": None,
        "startedAt": datetime.now(timezone.utc).isoformat()}   # claimed, then the phase ran
mvp.write_phase(root, "project")
verdict = phase_gate.evaluate_gate(root, task, json.loads(
    (root / "shipwright_run_config.json").read_text(encoding="utf-8")))
spec = importlib.util.find_spec("tools.verifiers")
modules = {}
if spec:  # every module a driven phase's canon run imports, not only project's
    for name in ("common", "project_checks", "design_checks", "plan_checks", "build_checks",
                 "test_checks", "changelog_checks", "deploy_checks"):
        modules[name] = importlib.import_module("tools.verifiers." + name).__file__
print(json.dumps({"verdict": verdict, "enforced": phase_gate.ENFORCE_PHASE_GATE_DEFAULT,
                  "verifiers": spec.origin if spec else None, "modules": modules}))
"""


def _copy_plugin(dest: Path) -> Path:
    # dirs_exist_ok: the cache fixture is module-scoped, so a re-run of a case reuses it
    shutil.copytree(_PLUGIN / "scripts", dest / "scripts", ignore=_SKIP, dirs_exist_ok=True)
    return dest / "scripts" / "lib"


@pytest.fixture(scope="module")
def cache(tmp_path_factory) -> Path:
    """One plugin cache holding both run-plugin trees and the shared tree they resolve."""
    root = tmp_path_factory.mktemp("plugins-cache") / "shipwright"
    shutil.copytree(_REPO / "shared", root / "shared", ignore=_SKIP)
    return root


def _layout(cache: Path, name: str) -> tuple[Path, Path]:
    """(the run plugin's scripts/lib, the shared tree it must resolve) for one layout."""
    if name == "checkout":
        return _PLUGIN / "scripts" / "lib", _REPO / "shared"
    if name == "codex":  # build_codex_plugin.py: <bundle>/origin/<plugin>/ + <bundle>/shared/
        bundle = cache.parent / "codex-cache" / "shipwright" / "shipwright" / "9.9.9"
        shutil.copytree(cache / "shared", bundle / "shared", dirs_exist_ok=True)
        return _copy_plugin(bundle / "origin" / "shipwright-run"), bundle / "shared"
    plugin = cache / "shipwright-run" / "9.9.9" if name == "installed" else (
        cache / "plugins" / "shipwright-run")
    return _copy_plugin(plugin), cache / "shared"


def _probe(lib: Path, project: Path) -> dict:
    project.mkdir()
    proc = subprocess.run(
        [sys.executable, "-I", "-c", _PROBE, str(lib), str(_TESTKIT), str(project)],
        cwd=project.parent, capture_output=True, text=True, encoding="utf-8", timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("layout", ["installed", "mirror", "codex", "checkout"])
def test_the_enforced_gate_runs_its_canon_checks_in_every_layout(cache, tmp_path, layout):
    lib, shared = _layout(cache, layout)
    out = _probe(lib, tmp_path / "project")
    verdict = out["verdict"]
    assert out["enforced"] is True
    assert verdict["checked"] is True
    assert verdict["ask"] == [], verdict["ask"]          # no canon_degraded promoted to ask
    assert not any(i.get("kind") == "canon_degraded" for i in verdict["inform"])
    assert any(i["message"].startswith("[canon]") for i in verdict["inform"])  # canon ran
    verifiers = (shared / "scripts" / "tools" / "verifiers").resolve()
    assert Path(out["verifiers"]).resolve().is_relative_to(verifiers)
    assert len(out["modules"]) == 8
    for name, origin in out["modules"].items():   # all seven phases' checks + common
        assert Path(origin).resolve().is_relative_to(verifiers), (name, origin)


def test_a_layout_without_the_verifiers_stops_the_gate_loudly(cache, tmp_path):
    """The negative control: the probe can tell a missing verifiers package apart."""
    broken = tmp_path / "broken" / "shipwright"
    shutil.copytree(cache / "shared", broken / "shared",
                    ignore=shutil.ignore_patterns("verifiers"))
    out = _probe(_copy_plugin(broken / "shipwright-run" / "9.9.9"), tmp_path / "project")
    assert out["verifiers"] is None
    verdict = out["verdict"]
    degraded = [i for i in verdict["ask"] if i.get("kind") == "canon_degraded"]
    assert degraded, verdict
    assert "installation problem" in degraded[0]["message"]   # names the fix, not the artifact
