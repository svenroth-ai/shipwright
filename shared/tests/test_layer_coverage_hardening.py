"""Coordinator adversarial-panel hardening for the two enforcing F11 gates (TT5).

Pins the fail-CLOSED integrity fixes the panel required: an infra gap ERRORs (never silently
SKIPs) at medium+ (MUST-FIX 1); a wholesale FR-row deletion with a surviving test FAILs while
a genuine relocation does NOT false-red (MUST-FIX 3); an unresolvable base ref ERRORs instead
of narrowing the diff (MUST-FIX 4); and the evidence-freshness rejections. Real-git helpers +
the corpus constants are reused from ``test_layer_coverage_gate_integration``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling test-module import

from test_layer_coverage_gate_integration import (  # noqa: E402
    _E2E_SPEC,
    _SPEC_ACTIVE,
    _SPEC_E2E,
    _SPEC_E2E_CHANGED,
    _TEST,
    _commit,
    _commit_base,
    _git,
    _git_available,
    _init,
    _seed_medium,
    _stage_e2e_evidence,
    _write,
)
from tools.verifiers._layer_coverage_regen import clear_regen_cache  # noqa: E402
from tools.verifiers.layer_coverage import (  # noqa: E402
    check_cross_layer_coverage,
    check_removal_coverage,
)

pytestmark = pytest.mark.skipif(not _git_available(), reason="git not available")

_SPEC_NO_ROW = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"  # FR-03.03 row deleted
)


def _seed(root: Path, run_id: str, complexity: str) -> None:
    (root / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [{"run_id": run_id, "complexity": complexity, "type": "change"}],
    }), encoding="utf-8")


# --- MUST-FIX 1: infra gap ERRORs at medium+, SKIPs below --------------------


def test_missing_commit_errors_at_medium_not_skip(tmp_path):
    _seed(tmp_path, "r", "medium")
    for fn in (check_removal_coverage, check_cross_layer_coverage):
        r = fn(tmp_path, "r", "")  # no commit → cannot enforce a medium+ iterate
        assert r.ok is False and not r.is_skipped, r.detail


def test_missing_commit_skips_below_medium(tmp_path):
    _seed(tmp_path, "r", "small")
    # removal runs at all complexities but a below-medium infra gap SKIPs (not ERROR).
    assert check_removal_coverage(tmp_path, "r", "").is_skipped
    assert check_cross_layer_coverage(tmp_path, "r", "").is_skipped  # cross-layer is medium+ only


def test_non_git_project_skips(tmp_path):
    # A CLEAN non-git context (git ran and said "not a work tree") is inapplicable for a
    # git-diff gate, so it SKIPs — distinct from a git subprocess failure (ERROR, below).
    _seed(tmp_path, "r", "medium")
    r = check_removal_coverage(tmp_path, "r", "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
    assert r.is_skipped, r.detail


def test_git_subprocess_failure_errors_at_medium(tmp_path, monkeypatch):
    # Coordinator FIX 1: a git SUBPROCESS failure/timeout (synthesized rc=1, empty stderr) on a
    # medium+ iterate must ERROR (block) — NOT be conflated with a clean non-git SKIP (fail-open).
    import tools.verifiers.layer_coverage as lc  # noqa: PLC0415

    _seed(tmp_path, "r", "medium")
    monkeypatch.setattr(lc, "_run_git", lambda *a, **k: (1, "", ""))  # OSError/timeout shape
    for fn in (lc.check_removal_coverage, lc.check_cross_layer_coverage):
        r = fn(tmp_path, "r", "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
        assert r.ok is False and not r.is_skipped, r.detail


# --- FIX 2: base resolves via the branch's upstream on an adopted non-main default ----


def test_base_resolves_via_upstream_on_adopted_default(tmp_path):
    # Coordinator FIX 2: an adopted repo whose default is `develop` (origin/HEAD unset, no
    # main/master) must still resolve a base via the branch's upstream @{u} — no false-red ERROR.
    clear_regen_cache()
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.dev")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "symbolic-ref", "HEAD", "refs/heads/develop")  # non-main default, origin/HEAD unset
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_ACTIVE)
    _commit(root, "base")
    _git(root, "branch", "trunk-base")  # a local ref to act as the tracking upstream, at base
    _git(root, "branch", "--set-upstream-to=trunk-base", "develop")  # @{u} = trunk-base
    _write(root, "orders.py", "x = 1\n")  # benign head change (no removal)
    head = _commit(root, "head: benign change")
    _seed_medium(root, "iterate-adopt")
    r = check_removal_coverage(root, "iterate-adopt", head)
    # base resolved via @{u} → the gate RAN (no removal → clean pass), not an ERROR-on-no-base.
    assert r.ok is True and "cannot enforce" not in r.detail, r.detail


# --- MUST-FIX 4: no resolvable base ref → ERROR (not a narrowed-diff pass) ----


def test_no_base_ref_errors_not_narrowed_diff(tmp_path):
    clear_regen_cache()
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.dev")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "symbolic-ref", "HEAD", "refs/heads/work")  # NOT main/master/origin
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_ACTIVE)
    _write(root, "tests/integration/test_orders.py", _TEST)
    _commit(root, "base")
    _write(root, "tests/integration/test_orders.py", _TEST + "\n# edit\n")
    head = _commit(root, "head (2nd commit, no discoverable base branch)")
    _seed_medium(root, "iterate-nobase")
    r = check_removal_coverage(root, "iterate-nobase", head)
    assert r.ok is False and not r.is_skipped, r.detail


# --- MUST-FIX 3: wholesale row deletion FAILs; relocation is NOT false-red ----


def test_deleted_row_with_surviving_test_fails(tmp_path):
    clear_regen_cache()
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_ACTIVE)
    _write(root, "tests/integration/test_orders.py", _TEST)
    _commit_base(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_NO_ROW)  # row DELETED outright
    head = _commit(root, "head: delete the FR-03.03 row, leave its test tagged")
    _seed_medium(root, "iterate-del")
    r = check_removal_coverage(root, "iterate-del", head)
    assert r.ok is False and not r.is_skipped, r.detail


def test_relocation_to_another_namespace_is_not_false_red(tmp_path):
    clear_regen_cache()
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_ACTIVE)
    _write(root, "tests/integration/test_orders.py", _TEST)
    _commit_base(root)
    # The FR-03.03 row leaves app/ but reappears ACTIVE under app2/ (a genuine relocation).
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_NO_ROW)
    _write(root, ".shipwright/planning/app2/spec.md", _SPEC_ACTIVE)
    head = _commit(root, "head: relocate FR-03.03 to the app2 split")
    _seed_medium(root, "iterate-reloc")
    r = check_removal_coverage(root, "iterate-reloc", head)
    assert r.ok is True and not r.is_skipped, r.detail  # still active elsewhere → no removal


# --- moved evidence-freshness rejections -------------------------------------


def test_cross_layer_blocks_when_evidence_is_stale_run(tmp_path):
    clear_regen_cache()
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_E2E)
    _write(root, "e2e/dashboard.spec.ts", _E2E_SPEC)
    _write(root, ".gitignore", ".shipwright/compliance/\n")
    _commit_base(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_E2E_CHANGED)
    head = _commit(root, "head")
    _seed_medium(root, "iterate-fresh")
    _stage_e2e_evidence(root, "iterate-OTHER-RUN", "passed", head_commit=head)  # wrong run_id
    r = check_cross_layer_coverage(root, "iterate-fresh", head)
    assert r.ok is False and not r.is_skipped, r.detail


def test_cross_layer_blocks_when_evidence_head_is_foreign(tmp_path):
    clear_regen_cache()
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_E2E)
    _write(root, "e2e/dashboard.spec.ts", _E2E_SPEC)
    _write(root, ".gitignore", ".shipwright/compliance/\n")
    _commit_base(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_E2E_CHANGED)
    head = _commit(root, "head")
    _seed_medium(root, "iterate-foreign")
    _stage_e2e_evidence(root, "iterate-foreign", "passed", head_commit="0" * 40)  # non-ancestor
    r = check_cross_layer_coverage(root, "iterate-foreign", head)
    assert r.ok is False and not r.is_skipped, r.detail


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
