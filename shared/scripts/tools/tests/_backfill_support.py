"""Shared helpers + path wiring for the TT6 backfill-engine tests.

Not a test module (no ``test_`` prefix) — imported by ``test_backfill_*`` so the
two suites share the fixture-copy + adapter helpers and stay each under the
300-LOC bloat cap.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_SHARED = _TESTS.parents[1]                      # shared/scripts
REPO = _TESTS.parents[3]                          # repo root
for _p in (str(_SHARED / "lib"), str(_SHARED / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import backfill_llm  # noqa: E402
import backfill_signals as sig  # noqa: E402,F401  (re-exported to the LLM suite)
import backfill_test_links as bf  # noqa: E402

FIXTURE = _TESTS / "fixtures" / "backfill" / "tagless_repo"
P1_ADAPTER = (
    REPO / "plugins" / "shipwright-compliance" / "tests" / "fixtures"
    / "traceability" / "llm_adapter" / "record_replay.py"
)

# Runs the real TT1 collector in a CLEAN subprocess (a process boundary, like
# production) so this shared-side test never trips the ADR-045 ``lib`` collision
# between the shared and compliance ``lib`` packages under one interpreter.
_TT1_DRIVER = """
import sys, json
from pathlib import Path
comp, repo, spec = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, comp)
from lib.collectors import test_links
m = test_links.build_manifest(Path(repo), spec_files=[Path(spec)], test_roots=[Path(repo)])
print(json.dumps(m))
"""


def copy_repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURE, dest)
    return dest


def run(repo: Path, **kw):
    return bf.run_backfill(repo, spec_files=[repo / "spec.md"], **kw)


def auto_frs(report) -> set[str]:
    return {w["fr"] for w in report["auto_written"]}


def import_p1_adapter():
    spec = importlib.util.spec_from_file_location("_tt6_rr", P1_ADAPTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tt1_manifest(repo: Path) -> dict:
    comp_scripts = REPO / "plugins" / "shipwright-compliance" / "scripts"
    proc = subprocess.run(
        [sys.executable, "-c", _TT1_DRIVER, str(comp_scripts), str(repo), str(repo / "spec.md")],
        capture_output=True, text=True, cwd=str(REPO),
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


class SpyAdjudicator:
    """Records every payload it is asked to adjudicate (to assert R4 no-body)."""

    def __init__(self, proposed_fr="FR-05.01", confidence=0.55):
        self.payloads: list[dict] = []
        self._fr = proposed_fr
        self._conf = confidence

    def adjudicate(self, payload: dict) -> dict:
        backfill_llm.validate_payload(payload)      # same guard the production leg uses
        self.payloads.append(dict(payload))
        return {"proposed_fr": self._fr, "confidence": self._conf, "auto_write": False}
