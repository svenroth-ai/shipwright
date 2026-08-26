"""F0's own unit discovery vs the canonical test-root discovery
(iterate-2026-08-26-r1b-ci-manifest-regen-gate, AC2).

`suite_units.discover_units` is a THIRD, independently-hardcoded selection
rule (plugins/*/ with pyproject.toml+tests/, the three SHARED_TEST_DIRS,
integration-tests) alongside `conftest.py::discover_test_roots` (the repo-root
pytest guard's own root enumeration, also what `ci_junit_plan.py`/
`run_full_suite_evidence.py` plan against). `test_f0_ci_parity.py` already
pins F0's rule against ci.yml's literal loop text; this pins it against the
OTHER independent list, so a newly added test root cannot silently diverge
between "F0 will run it" and "the canonical discovery sees it" while every
existing parity test stays green.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.tools.suite_units import discover_units  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _load_discover_test_roots(repo_root: Path):
    """ADR-045: register in sys.modules BEFORE exec_module, a unique synthetic
    name — mirrors ci_junit_plan.py's own loader."""
    conftest_path = repo_root / "conftest.py"
    spec = importlib.util.spec_from_file_location("_f0_unit_root_parity_conftest", conftest_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_f0_unit_root_parity_conftest"] = module
    spec.loader.exec_module(module)
    return module.discover_test_roots


def test_every_unit_f0_would_run_is_a_root_the_canonical_discovery_also_sees():
    """Forward direction: F0 must never claim to cover a root discover_test_roots
    does not recognize — that would certify coverage the canonical list disputes."""
    discover_test_roots = _load_discover_test_roots(_REPO_ROOT)
    canonical_roots = {r.resolve() for r in discover_test_roots(_REPO_ROOT)}

    unit_roots = {(_REPO_ROOT / u.cwd / u.target).resolve() for u in discover_units(_REPO_ROOT)}

    assert unit_roots <= canonical_roots, (
        f"discover_units() claims root(s) discover_test_roots() does not see: "
        f"{sorted(str(p) for p in unit_roots - canonical_roots)} — F0's own selection "
        f"has drifted from the canonical one ci_junit_plan.py/run_full_suite_evidence.py plan against"
    )


def test_every_canonical_root_is_a_unit_f0_would_run():
    """Reverse direction: a root the canonical discovery sees but F0 does not run would
    be silently uncovered by F0 while still counted as a real test root elsewhere
    (ci.yml's Plan/Verify steps, the manifest regeneration's staged evidence)."""
    discover_test_roots = _load_discover_test_roots(_REPO_ROOT)
    canonical_roots = {r.resolve() for r in discover_test_roots(_REPO_ROOT)}

    unit_roots = {(_REPO_ROOT / u.cwd / u.target).resolve() for u in discover_units(_REPO_ROOT)}

    assert canonical_roots <= unit_roots, (
        f"discover_test_roots() sees root(s) discover_units() does not run: "
        f"{sorted(str(p) for p in canonical_roots - unit_roots)} — F0 would silently "
        f"skip a root ci.yml's own planning treats as real"
    )
