"""Direct-import pin for `shared/scripts/lib/suite_root_plan.py`
(iterate-2026-08-26-r1b-ci-manifest-regen-gate, AC2/AC4).

Behavior is already exhaustively covered via `scripts/run_full_suite_evidence.py`'s
re-export (`test_run_full_suite_evidence.py`) — this file exists only to prove the
module is importable on its own (`from lib import suite_root_plan`, the same path
F0's suite runner and ci.yml's manifest-drift step each take independently), and
that the re-export is a genuine alias, not a silently-diverging copy.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import suite_root_plan  # noqa: E402


def test_base_for_root_of_a_plugin_root():
    repo_root = Path("/repo")
    root = repo_root / "plugins" / "shipwright-x" / "tests"
    assert suite_root_plan.base_for_root(repo_root, root) == "plugins/shipwright-x"


def test_base_for_root_of_a_non_plugin_root_is_empty():
    repo_root = Path("/repo")
    assert suite_root_plan.base_for_root(repo_root, repo_root / "shared" / "tests") == ""
    assert suite_root_plan.base_for_root(repo_root, repo_root / "integration-tests") == ""


def test_plan_root_is_importable_directly_and_plans_a_plugin_root():
    repo_root = Path("/repo")
    root = repo_root / "plugins" / "shipwright-x" / "tests"
    plan = suite_root_plan.plan_root(repo_root, root, repo_root / "raw", 1)
    assert plan.base == "plugins/shipwright-x"
    assert plan.cwd == repo_root / "plugins" / "shipwright-x"


def test_run_full_suite_evidence_re_exports_the_same_function_object():
    import importlib.util

    subject = REPO_ROOT / "scripts" / "run_full_suite_evidence.py"
    spec = importlib.util.spec_from_file_location("_rfse_reexport_probe", subject)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_rfse_reexport_probe"] = module
    spec.loader.exec_module(module)
    assert module.plan_root is suite_root_plan.plan_root
    assert module.plan_all_roots is suite_root_plan.plan_all_roots
    assert module.RootPlan is suite_root_plan.RootPlan
