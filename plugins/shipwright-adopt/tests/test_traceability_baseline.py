"""TT7 — adopt traceability-baseline pure helpers (unit).

Covers the scaffold / repo-wide skip inventory (incl. the os.walk prune +
``@pytest.mark.skip`` scan + rollup) / triage-spec builders (``traceability_baseline`` +
``traceability_skip_inventory``). The ``required_layers`` resolver lives in
``test_traceability_layers``; the orchestrator wiring is exercised end-to-end by the
subprocess test ``test_seed_traceability_baseline.py``.

Import discipline (ADR-045): imported by BARE name off ``scripts/lib`` (not ``from
lib.X``) so this test never binds ``sys.modules['lib']`` to adopt's package.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_PLUGIN = Path(__file__).resolve().parent.parent
_REPO = _PLUGIN.parents[1]
sys.path.insert(0, str(_PLUGIN / "scripts" / "lib"))

import traceability_baseline as tb  # noqa: E402

_TEMPLATES = _REPO / "shared" / "templates" / "rules"
_SHARED_SCRIPTS = _REPO / "shared" / "scripts"
_COMPLIANCE_SCRIPTS = _REPO / "plugins" / "shipwright-compliance" / "scripts"


# --------------------------------------------------------------------------- #
# scaffold_tag_convention                                                     #
# --------------------------------------------------------------------------- #

def test_scaffold_writes_convention_rules(tmp_path: Path):
    res = tb.scaffold_tag_convention(tmp_path, _TEMPLATES)
    assert ".claude/rules/tests.md" in res.written
    tests_rule = tmp_path / ".claude" / "rules" / "tests.md"
    assert tests_rule.exists()
    # The scaffolded rule carries the @FR convention section (TT1).
    assert "@FR" in tests_rule.read_text(encoding="utf-8")


def test_scaffold_is_idempotent_when_convention_present(tmp_path: Path):
    tb.scaffold_tag_convention(tmp_path, _TEMPLATES)   # writes the full template (has @FR)
    res = tb.scaffold_tag_convention(tmp_path, _TEMPLATES)
    assert ".claude/rules/tests.md" in res.skipped_existing  # not re-appended
    assert res.written == []


def test_scaffold_appends_convention_to_a_preexisting_rule_file(tmp_path: Path):
    # A brownfield repo that already curates its own tests.md (no @FR convention).
    rules = tmp_path / ".claude" / "rules"
    rules.mkdir(parents=True)
    (rules / "tests.md").write_text("# My rules\n\n- Write good tests\n", encoding="utf-8")
    res = tb.scaffold_tag_convention(tmp_path, _TEMPLATES)
    assert ".claude/rules/tests.md" in res.appended
    body = (rules / "tests.md").read_text(encoding="utf-8")
    assert "# My rules" in body                     # user content preserved
    assert "@FR" in body                             # convention now present
    assert "shipwright:@FR-tag-convention BEGIN" in body
    # Idempotent: a second pass sees the marker and does not double-append.
    res2 = tb.scaffold_tag_convention(tmp_path, _TEMPLATES)
    assert ".claude/rules/tests.md" in res2.skipped_existing
    assert body == (rules / "tests.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# repo_wide_skip_inventory — reuses TT4 scanners, NOT diff-scoped             #
# --------------------------------------------------------------------------- #

def test_skip_inventory_catches_python_and_ts_skips_repo_wide(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "e2e").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(
        "import pytest\ndef test_x():\n    pytest.skip('rot')\n", encoding="utf-8")
    (tmp_path / "e2e" / "b.spec.ts").write_text(
        "test.only('focused', async () => {});\n", encoding="utf-8")
    # A vendored dir must be pruned — not scanned.
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "c.spec.ts").write_text(
        "test.skip('vendored', async () => {});\n", encoding="utf-8")
    inv = tb.repo_wide_skip_inventory(tmp_path, _SHARED_SCRIPTS)
    patterns = {(f["file"], f["pattern"]) for f in inv}
    assert ("tests/test_a.py", "pytest.skip") in patterns
    assert ("e2e/b.spec.ts", "js.only") in patterns
    assert not any("node_modules" in f["file"] for f in inv)  # pruned


def test_skip_inventory_empty_on_clean_repo(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    assert tb.repo_wide_skip_inventory(tmp_path, _SHARED_SCRIPTS) == []


def test_enumerate_prunes_vendored_dirs_during_descent(tmp_path: Path):
    # MUST-FIX 1 (doubt MED#2): a large committed node_modules must never be DESCENDED into
    # — os.walk with an in-place dirnames prune, not rglob-then-filter.
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
    vendored = tmp_path / "node_modules" / "pkg" / "deep"
    vendored.mkdir(parents=True)
    (vendored / "test_vendored.py").write_text("def test_v():\n    pass\n", encoding="utf-8")
    (vendored / "b.spec.ts").write_text("test('x', () => {});\n", encoding="utf-8")
    py, ts = tb.enumerate_test_files(tmp_path, lambda p: p.suffix == ".ts")
    assert [p.name for p in py] == ["test_a.py"]      # node_modules test NOT enumerated
    assert ts == []


def test_enumerate_prunes_fixtures_only_under_a_tests_tree(tmp_path: Path):
    # A ``fixtures`` dir UNDER a ``tests`` tree holds test DATA (sample/mini repos a
    # collector test deliberately asserts on) — an intentional input, not rot — so it is
    # pruned during descent. But a ``fixtures`` dir OUTSIDE a tests tree may hold real
    # rotting tests, so it is NOT pruned (narrower than a global prune → adopt keeps its
    # brownfield sensitivity).
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(
        "import pytest\ndef test_a():\n    pytest.skip('real rot')\n", encoding="utf-8")
    under_tests = tmp_path / "tests" / "fixtures" / "mini_repo" / "e2e"
    under_tests.mkdir(parents=True)
    (under_tests / "auth.spec.ts").write_text("test.skip('data', async () => {});\n", encoding="utf-8")
    (under_tests / "test_sample.py").write_text(
        "import pytest\ndef test_s():\n    pytest.skip('data')\n", encoding="utf-8")
    # A top-level fixtures dir (NOT under tests/) with a genuinely rotting skipped test.
    top = tmp_path / "fixtures"
    top.mkdir()
    (top / "test_real.py").write_text(
        "import pytest\ndef test_r():\n    pytest.skip('genuine rot outside a tests tree')\n",
        encoding="utf-8")
    py, ts = tb.enumerate_test_files(tmp_path, lambda p: p.suffix == ".ts")
    names = sorted(p.name for p in py)
    assert names == ["test_a.py", "test_real.py"]     # tests/fixtures pruned; top-level fixtures kept
    assert ts == []                                    # the fixture-data ts spec NOT enumerated
    inv = tb.repo_wide_skip_inventory(tmp_path, _SHARED_SCRIPTS)
    flagged = {f["file"] for f in inv}
    assert "tests/test_a.py" in flagged                # real rot still caught
    assert "fixtures/test_real.py" in flagged          # real rot OUTSIDE a tests tree still caught
    assert not any("tests/fixtures" in f for f in flagged)  # fixture DATA under tests/ is silent


def test_skip_inventory_flags_unconditional_pytest_mark_skip(tmp_path: Path):
    # doubt LOW#3: the commonest disable idiom the shared scanner does NOT flag.
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_m.py").write_text(
        "import pytest\n"
        "@pytest.mark.skip(reason='later')\n"
        "def test_disabled():\n    assert True\n"
        "@pytest.mark.skipif(True, reason='cond')\n"
        "def test_cond():\n    assert True\n",
        encoding="utf-8")
    inv = tb.repo_wide_skip_inventory(tmp_path, _SHARED_SCRIPTS)
    patterns = {f["pattern"] for f in inv}
    assert "pytest.mark.skip" in patterns          # unconditional decorator caught
    assert "pytest.mark.skipif" in patterns        # shared scanner still catches skipif


def test_skip_triage_rolls_up_above_threshold(tmp_path: Path):
    # doubt LOW#4: don't flood the Inbox — >threshold findings collapse to one summary card.
    inv = [{"file": f"e2e/a{i}.spec.ts", "line": i, "pattern": "js.skip.no_quarantine",
            "reason": "r", "language": "ts/js"} for i in range(15)]
    items = tb.build_skip_triage_items(inv)
    assert len(items) == 1
    assert items[0].dedup_key == "adopt-skip-summary"
    assert "15" in items[0].title
    # At/below threshold stays granular (one card per finding).
    small = inv[:10]
    assert len(tb.build_skip_triage_items(small)) == 10


# --------------------------------------------------------------------------- #
# triage-spec builders — carry the TT6 orphan category                        #
# --------------------------------------------------------------------------- #

def test_orphan_triage_carries_category_and_no_stale_accusation():
    report = {
        "orphans": {
            "confirmed_orphan": [{"test": "e2e/x.spec.ts::y", "tagged_fr": "FR-09.09",
                                  "reason": "fr_removed"}],
            "possible_orphan": [{"test": "t/z.py::w", "candidate_fr": "FR-01.01",
                                 "reason": "title", "confidence": 0.4}],
            "unmapped": ["t/legacy.py::old"],
        },
        "proposals": [{"test": "t/p.py::q", "candidates": [{"fr": "FR-02.02"}]}],
    }
    items = tb.build_orphan_triage_items(report)
    by_cat = {i.category: i for i in items}
    assert by_cat["confirmed_orphan"].severity == "medium"
    unmapped = by_cat["unmapped"]
    # An unmapped test is a REVIEW candidate — never a stale-feature accusation (§11-R4).
    assert "never" in unmapped.detail.lower()
    assert "stale" not in unmapped.title.lower()
    assert {"confirmed_orphan", "possible_orphan", "unmapped", "proposal"} <= set(by_cat)


def test_skip_triage_severity_mapping():
    inv = [
        {"file": "e2e/a.spec.ts", "line": 1, "pattern": "js.only", "reason": "r", "language": "ts/js"},
        {"file": "t/b.py", "line": 2, "pattern": "pytest.skip", "reason": "r", "language": "python"},
    ]
    items = {i.dedup_key.split("::")[-1]: i for i in tb.build_skip_triage_items(inv)}
    assert items["js.only"].severity == "high"
    assert items["pytest.skip"].severity == "low"


# --------------------------------------------------------------------------- #
# Fast wiring guard (NON-slow): tag → FR → manifest coverage link             #
# --------------------------------------------------------------------------- #

# The full adopt→backfill→collector round-trip is proven by the slow subprocess suite,
# which DOES run in the adopt CI (addopts carry no `-m "not slow"`). This fast guard is
# belt-and-suspenders (code L4): it subprocesses ONLY the TT1 collector over a tiny fixture
# in a clean interpreter (the _backfill_support ADR-045 pattern), so a regression in the
# core "manifest carries a test→FR link" claim is caught by the DEFAULT gate even if the
# slow lane is ever excluded.
_COLLECTOR_DRIVER = """
import sys, json
from pathlib import Path
comp, repo = sys.argv[1], sys.argv[2]
sys.path.insert(0, comp)
from lib.collectors import test_links
m = test_links.build_manifest(Path(repo),
                              spec_files=[Path(repo) / '.shipwright/planning/01-adopted/spec.md'],
                              test_roots=[Path(repo)])
print(json.dumps(m))
"""


def test_collector_links_a_tagged_test_to_its_fr(tmp_path: Path):
    (tmp_path / ".shipwright" / "planning" / "01-adopted").mkdir(parents=True)
    (tmp_path / ".shipwright" / "planning" / "01-adopted" / "spec.md").write_text(
        "## Functional Requirements\n"
        "| ID | Name | Priority | Description | Source | Layers |\n"
        "|----|------|----------|-------------|--------|--------|\n"
        "| FR-01.01 | Sign in | Must | user signs in | `app/auth.py` | unit (inferred) |\n",
        encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_auth.py").write_text(
        "import pytest\n@pytest.mark.covers('FR-01.01')\n"
        "def test_sign_in():\n    assert True\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-c", _COLLECTOR_DRIVER, str(_COMPLIANCE_SCRIPTS), str(tmp_path)],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    manifest = json.loads(proc.stdout)
    node = manifest["requirements"]["01::FR-01.01"]
    unit_ids = [t["id"] for t in node["tests"].get("unit", [])]
    assert any("test_sign_in" in tid for tid in unit_ids), node["tests"]
