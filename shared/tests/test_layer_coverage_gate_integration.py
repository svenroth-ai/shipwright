"""END-TO-END integration test for the two enforcing F11 traceability gates (TT5).

The ``category:"integration"`` scenario the non-dodgeable ``check_integration_coverage`` gate
demands for this cross-component change. Proves the four pieces compose on REAL git: (1)
git-diff regeneration (``regenerate_base_head`` resolves the merge-base and ``git archive``\\s
base+head into throwaway trees, R3); (2) the TT1 ``build_manifest`` collector over each tree;
(3) execution-evidence (TT-EV) — emit-side stages a report+provenance, the gate builds the
per-test index IN-MEMORY from ONLY those staged reports (MUST-FIX 2); (4) the gate verdicts
through the real ``check_*`` signatures. Real git via ``subprocess``; every repo sets up a
``main`` base ref + a ``feature`` branch (there is no ``commit^`` fallback — MUST-FIX 4). NOT
``slow`` — it gates in CI.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import evidence_drop  # noqa: E402
from tools.verifiers.layer_coverage import (  # noqa: E402
    check_cross_layer_coverage,
    check_removal_coverage,
)


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


pytestmark = pytest.mark.skipif(not _git_available(), reason="git not available")


def _init(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.dev")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    # Force the initial branch to `main` (whatever the git default is) so the base commit
    # lands there — the gate's `_merge_base` resolves against a real branch base (no `commit^`
    # fallback exists anymore, MUST-FIX 4), so the diff must have a discoverable base ref.
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")


def _write(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _commit(root: Path, msg: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", msg)
    return _git(root, "rev-parse", "HEAD")


def _commit_base(root: Path) -> str:
    """Commit the base state on ``main``, then branch to ``feature`` for the head commits so
    ``merge-base(main, feature-HEAD)`` is the real branch base."""
    sha = _commit(root, "base")
    _git(root, "checkout", "-q", "-b", "feature")
    return sha


def _seed_medium(root: Path, run_id: str) -> None:
    (root / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [{"run_id": run_id, "complexity": "medium", "type": "feature"}],
    }), encoding="utf-8")


_SPEC_ACTIVE = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-03.03 | Persist an order | Should | integration |\n"
)
_SPEC_REMOVED = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n\n"
    "## Removed Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-03.03 | Persist an order | Should | integration |\n"
)
_TEST = ("import pytest\n\n\n@pytest.mark.covers(\"FR-03.03\")\n"
         "def test_persist():\n    assert True\n")


def test_removal_gate_blocks_on_real_git(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_ACTIVE)
    _write(root, "tests/integration/test_orders.py", _TEST)
    _commit_base(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_REMOVED)  # move FR to Removed
    head = _commit(root, "head: remove FR-03.03, leave its test standing")
    _seed_medium(root, "iterate-rm")

    result = check_removal_coverage(root, "iterate-rm", head)
    assert result.ok is False and not result.is_skipped, result.detail
    assert "test_orders.py" in result.detail


def test_removal_gate_blocks_on_rename_plus_tag_strip(tmp_path):
    # External-review MUST-FIX, end-to-end: MOVE the test file AND strip its @FR tag in the
    # same commit that removes the FR. git rename detection (-M) must follow it so the moved,
    # now-untagged test is caught as an escape, not credited as "deleted".
    body = ("def test_persist():\n    a = 1\n    b = 2\n    c = a + b\n"
            "    assert c == 3\n    assert a < b\n    assert isinstance(c, int)\n")
    tagged = "import pytest\n\n\n@pytest.mark.covers(\"FR-03.03\")\n" + body
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_ACTIVE)
    _write(root, "tests/integration/test_orders.py", tagged)
    _commit_base(root)
    _git(root, "rm", "-q", "tests/integration/test_orders.py")
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_REMOVED)
    _write(root, "tests/integration/test_relocated.py", body)  # moved + tag stripped (body kept)
    head = _commit(root, "head: remove FR-03.03, move+untag its test")
    _seed_medium(root, "iterate-mv")

    result = check_removal_coverage(root, "iterate-mv", head)
    assert result.ok is False and not result.is_skipped, result.detail


def test_removal_gate_fires_below_medium(tmp_path):
    # SHOULD-FIX 6: a removal is never trivial, so removal_coverage runs at ALL complexities —
    # a small iterate that removes an FR and leaves its test standing still FAILs.
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_ACTIVE)
    _write(root, "tests/integration/test_orders.py", _TEST)
    _commit_base(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_REMOVED)
    head = _commit(root, "head")
    (root / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [{"run_id": "iterate-sm", "complexity": "small", "type": "change"}],
    }), encoding="utf-8")
    result = check_removal_coverage(root, "iterate-sm", head)
    assert result.ok is False and not result.is_skipped, result.detail


_SPEC_E2E = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-03.02 | Dashboard shows live orders | Must | e2e |\n"
)
_SPEC_E2E_CHANGED = _SPEC_E2E.replace("live orders", "live orders with running totals")
_E2E_SPEC = (
    "import { test } from '@playwright/test';\n"
    "test('dashboard shows orders', { tag: ['@FR-03.02'] }, async () => {});\n"
)


def _playwright_report(status: str) -> str:
    """A minimal Playwright JSON report for e2e/dashboard.spec.ts::dashboard shows orders."""
    return json.dumps({
        "suites": [{
            "title": "dashboard.spec.ts", "file": "e2e/dashboard.spec.ts",
            "specs": [{
                "title": "dashboard shows orders", "tags": ["@FR-03.02"], "ok": True,
                "tests": [{"expectedStatus": status, "status":
                           "expected" if status == "passed" else status,
                           "results": [{"status": status}]}],
            }],
        }],
    })


def _stage_e2e_evidence(root: Path, run_id: str, status: str, head_commit: str = "") -> None:
    """Emit-side: stage a playwright report + provenance. The gate builds the per-test
    evidence IN-MEMORY from this staged report (MUST-FIX 2) — no index write here."""
    report = root / "playwright-report.json"
    report.write_text(_playwright_report(status), encoding="utf-8")
    evidence_drop.stage_reports(root, run_id=run_id, playwright=report, head_commit=head_commit)


def test_cross_layer_gate_green_when_e2e_executed_passing(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_E2E)
    _write(root, "e2e/dashboard.spec.ts", _E2E_SPEC)
    _write(root, ".gitignore", ".shipwright/compliance/\n")
    _commit_base(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_E2E_CHANGED)
    head = _commit(root, "head: FR-03.02 description change (behaviour delta)")
    _seed_medium(root, "iterate-cl")
    _stage_e2e_evidence(root, "iterate-cl", "passed", head_commit=head)

    result = check_cross_layer_coverage(root, "iterate-cl", head)
    assert result.ok is True and not result.is_skipped, result.detail
    assert "behaviour-changed FR" in result.detail


def test_cross_layer_gate_blocks_when_e2e_skipped(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_E2E)
    _write(root, "e2e/dashboard.spec.ts", _E2E_SPEC)
    _write(root, ".gitignore", ".shipwright/compliance/\n")
    _commit_base(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_E2E_CHANGED)
    head = _commit(root, "head")
    _seed_medium(root, "iterate-cl2")
    _stage_e2e_evidence(root, "iterate-cl2", "skipped", head_commit=head)

    result = check_cross_layer_coverage(root, "iterate-cl2", head)
    assert result.ok is False and not result.is_skipped, result.detail
    assert "e2e" in result.detail


def test_cross_layer_gate_ignores_planted_pass_index_regenerates_from_report(tmp_path):
    # External-review MUST-FIX 2 (R3 for evidence): the gate NEVER reads the persisted index —
    # it builds in-memory from the staged report. Here the staged report has the e2e SKIPPED,
    # so a hand-planted PASS index is ignored → e2e MISSING → block.
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_E2E)
    _write(root, "e2e/dashboard.spec.ts", _E2E_SPEC)
    _write(root, ".gitignore", ".shipwright/compliance/\n")
    _commit_base(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_E2E_CHANGED)
    head = _commit(root, "head")
    _seed_medium(root, "iterate-stale")
    report = root / "pw.json"
    report.write_text(_playwright_report("skipped"), encoding="utf-8")  # real evidence: SKIPPED
    evidence_drop.stage_reports(root, run_id="iterate-stale", head_commit=head, playwright=report)
    idx = root / ".shipwright" / "compliance" / "test-evidence-index.json"
    idx.write_text(json.dumps({  # planted PASS — must be ignored by regeneration
        "schema_version": 2, "source_reports": [".shipwright/compliance/evidence/playwright.json"],
        "results": {"e2e/dashboard.spec.ts::dashboard shows orders":
                    {"status": "enabled", "executed": "pass", "runner": "playwright"}},
    }), encoding="utf-8")
    result = check_cross_layer_coverage(root, "iterate-stale", head)
    assert result.ok is False and not result.is_skipped, result.detail


def test_refactor_does_not_block_on_real_git(tmp_path):
    # The critical "must NOT block" green case: source changes, spec identical → no gate.
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_E2E)
    _write(root, "orders.py", "def persist(o):\n    return [o]\n")
    _commit_base(root)
    _write(root, "orders.py", "def persist(o):\n    return list([o])  # pure refactor\n")
    head = _commit(root, "head: pure refactor, no spec delta")
    _seed_medium(root, "iterate-rf")

    result = check_cross_layer_coverage(root, "iterate-rf", head)
    assert result.ok is True and not result.is_skipped, result.detail
    assert "no behaviour-changed FR" in result.detail


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
