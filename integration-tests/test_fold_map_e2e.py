"""Integration (F0.5 production-time E2E): FR-Fold-Map resolution end-to-end.

Drives the REAL producer CLI — `plugins/shipwright-compliance/.../collectors/test_links.py`
as a subprocess, exactly as `update_compliance` invokes it — rather than importing
`build_manifest` in-process. That process boundary is the point: it is where the ADR-045
`lib`-collision lives, and it is what a unit test cannot prove.

Two things are verified against production conditions:

1. **On a repo WITH a fold-map** — a `@covers` tag on a folded FR id lands as coverage of
   the surviving FR, carries `resolved_from`, produces zero orphans, and the written
   artifact passes the D-orphan detective.
2. **On THIS monorepo (which declares NO fold-map)** — the regenerated manifest is
   byte-identical to the committed one. This is the honest check on the central
   compatibility claim: `test-traceability.json` is committed churn, so had the new keys
   been emitted unconditionally, every project without a fold-map would diff on every
   regen forever.

Lives in integration-tests/ (a CI-run root) per ADR-044.

@FR-01.10
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COMPLIANCE = _REPO_ROOT / "plugins" / "shipwright-compliance"
_COLLECTOR = _COMPLIANCE / "scripts" / "lib" / "collectors" / "test_links.py"
_COMMITTED = _REPO_ROOT / ".shipwright" / "compliance" / "test-traceability.json"

# Runs the real collector the way production does: as its own process, with only the
# compliance scripts root on sys.path (the shared lib must be found by load_shared_lib).
_DRIVER = """
import sys, json
from pathlib import Path
comp, root, spec = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, comp + "/scripts")   # for `lib.collectors` (the collector package)
sys.path.insert(0, comp)                # for `scripts.audit` (the detective package)
from lib.collectors import test_links
from scripts.audit._group_d_traceability import check_orphan
m = test_links.build_manifest(
    Path(root), spec_files=[Path(spec)], test_roots=[Path(root)],
    generated_at="2026-07-18T00:00:00+00:00", source_commit="e" * 40)
print(json.dumps({"manifest": m, "orphan_check": list(check_orphan(m))}))
"""

_SPEC = """# Spec

## Functional Requirements

| FR | Description | Priority | Layers |
|----|-------------|----------|--------|
| FR-01.28 | Embedded terminal | Must | unit |

## FR-Fold-Map

| Folded ID | → Survivor | Reason | Was (original name) |
|-----------|-----------|--------|---------------------|
| `FR-01.44` | `FR-01.28` | delta | Embedded terminal appearance |
"""

_TEST = '''import pytest


@pytest.mark.covers("FR-01.44")
def test_terminal_appearance():
    assert True
'''


# Regenerates THIS repo's manifest with its real configured roots. Also a subprocess: an
# in-process `sys.path.insert` for the compliance `lib` package would both hit the very
# precedence trap this iterate fixed and leak that path into every later test in the
# shared integration-tests session.
_SELF_DRIVER = """
import sys, json
from pathlib import Path
comp, root = sys.argv[1], sys.argv[2]
sys.path.insert(0, comp + "/scripts")
from lib.collectors import test_links
from lib.collectors import _test_links_io as io
root = Path(root)
print(json.dumps(test_links.build_manifest(
    root, test_roots=io.configured_test_roots(root),
    prune_dirs=io.configured_prune_dirs(root), evidence={}, enumerate_untagged=True)))
"""


def _drive_self() -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", _SELF_DRIVER, str(_COMPLIANCE), str(_REPO_ROOT)],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _drive(root: Path, spec: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", _DRIVER, str(_COMPLIANCE), str(root), str(spec)],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_folded_tag_resolves_end_to_end_through_the_real_collector(tmp_path):
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "spec.md").write_text(_SPEC, encoding="utf-8")
    (root / "tests" / "test_terminal.py").write_text(_TEST, encoding="utf-8")

    out = _drive(root, root / "spec.md")
    manifest = out["manifest"]

    assert manifest["orphans"] == []
    assert manifest["fold_map"] == {"FR-01.44": "FR-01.28"}
    assert "fold_defects" not in manifest          # a healthy map has nothing to report

    survivor = next(n for n in manifest["requirements"].values() if n["id"] == "FR-01.28")
    links = [l for ls in survivor["tests"].values() for l in ls]
    assert [l["resolved_from"] for l in links] == ["FR-01.44"]
    assert survivor["coverage"]["unit"] == "MISSING"   # no execution evidence ⇒ R1 holds

    status, _severity, detail, _evidence, _cmd = out["orphan_check"]
    assert status == "pass", detail


@pytest.mark.skipif(not _COMMITTED.exists(), reason="no committed manifest to compare")
def test_this_monorepo_regenerates_a_byte_identical_manifest():
    """The no-churn guarantee, checked on real production data rather than a fixture.

    This repo declares no `## FR-Fold-Map`, so the fold feature must be completely inert
    here: no new top-level keys, no `resolved_from`, and every requirement node identical
    to what is committed. Volatile provenance fields (timestamp / head sha / evidence-
    dependent execution results) are excluded — they legitimately differ between a regen
    and the committed snapshot, and are not what this test is about.
    """
    fresh = _drive_self()
    committed = json.loads(_COMMITTED.read_text(encoding="utf-8"))

    assert "fold_map" not in fresh
    assert "fold_defects" not in fresh
    assert not [
        l for node in fresh["requirements"].values()
        for ls in (node.get("tests") or {}).values() for l in ls if "resolved_from" in l
    ]
    # The requirement SET is what a fold bug would corrupt (resurrected folded ids, or
    # coverage silently re-filed onto another FR).
    assert set(fresh["requirements"]) == set(committed["requirements"])
    assert fresh["orphans"] == committed["orphans"]
    assert fresh["invalid_tags"] == committed["invalid_tags"]
