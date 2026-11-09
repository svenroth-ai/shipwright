"""A criterion an ``fr_split`` moved (``## AC-Move-Map`` in spec.md) is neither removed nor added at the keystone gate.

Real git, same fixtures as ``test_keystone_ac_digest.py``. Measured first on a probe tree (a real FR-01.11 cut of AC21-25):
before this change the gate reported 5 added, 5 removed-with-bindings and 5 unbound; after it, nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests dir (helper)

from _keystone_repo import BASE_SPEC, SPEC_REL, make_repo, manifest  # noqa: E402
from _keystone_repo import commit_spec as _commit_spec  # noqa: E402
from _keystone_repo import git as _git  # noqa: E402
from verifiers import _keystone_ac_digest as kd  # noqa: E402
from verifiers._keystone_core import evaluate_keystone  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.10")  # nearest FR; the gate's own ACs live in the keystone design

MOVE_MAP = "\n## AC-Move-Map\n\n| Old id | New id |\n|---|---|\n| `FR-01.01/AC01` | `FR-01.03/AC01` |\n"


def _moved_spec(reword: bool = False, with_map: bool = True) -> str:
    text = "The widget must fizz loudly." if reword else "The widget must fizz."
    spec = BASE_SPEC.replace("- [AC01] The widget must fizz.\n", "") + f"\n### FR-01.03: Fizzing\n\n- [AC01] {text}\n"
    return spec + (MOVE_MAP if with_map else "")


def _change_set(tmp_path: Path, spec: str):
    repo = make_repo(tmp_path)
    head = _commit_spec(repo, spec)
    base = _git("rev-parse", "HEAD~1", cwd=repo)
    m = manifest(ids=("FR-01.01", "FR-01.02", "FR-01.03"))
    return kd.ac_change_set(repo, base, head, m, m)


def test_a_moved_criterion_with_unchanged_wording_is_not_a_change(tmp_path):
    cs = _change_set(tmp_path, _moved_spec())
    assert (cs.added, cs.removed, cs.changed) == (set(), set(), set())


def test_a_moved_and_reworded_criterion_is_changed_not_added_or_removed(tmp_path):
    cs = _change_set(tmp_path, _moved_spec(reword=True))
    assert cs.changed == {("FR-01.03", "AC01")} and not cs.added and not cs.removed


def test_without_a_move_map_the_same_edit_reads_as_removed_plus_added(tmp_path):
    cs = _change_set(tmp_path, _moved_spec(with_map=False))
    assert cs.added == {("FR-01.03", "AC01")} and cs.removed == {("FR-01.01", "AC01")}


def test_a_hand_written_row_onto_a_living_id_does_not_hide_a_removal(tmp_path):
    spec = BASE_SPEC.replace("- [AC01] The widget must fizz.\n", "") + "\n## AC-Move-Map\n\n| Old id | New id |\n|---|---|\n| `FR-01.01/AC01` | `FR-01.01/AC02` |\n"
    cs = _change_set(tmp_path, spec)
    assert cs.removed == {("FR-01.01", "AC01")} and not cs.moved


def test_a_moved_and_reworded_criterion_keeps_its_old_links_for_the_binding_check(tmp_path):
    cs = _change_set(tmp_path, _moved_spec(reword=True))
    assert cs.moved == {("FR-01.03", "AC01"): ("FR-01.01", "AC01")}


def _bound(fr: str, n_tests: int) -> dict:
    tests = [{"id": f"tests/test_widget.py::test_{i}", "layer": "unit", "status": "enabled", "executed": "pass"} for i in range(n_tests)]
    node = {"id": fr, "status": "active", "spec_path": SPEC_REL, "required_layers": ["unit"], "required_layers_source": "inferred_legacy",
            "acs": {"AC01": {"tests": {"unit": tests}}} if tests else {}}
    other = {"id": "FR-01.01" if fr != "FR-01.01" else "FR-01.03", "status": "active", "spec_path": SPEC_REL, "acs": {}}
    return {"requirements": {f"ns::{fr}": node, f"ns::{other['id']}": other}}


def test_a_moved_and_reworded_criterion_that_lost_all_its_tests_is_binding_removed(tmp_path):
    """The base links sit under the OLD id; reading them under the new id would see none and never block."""
    cs = _change_set(tmp_path, _moved_spec(reword=True))
    verdict = evaluate_keystone(cs, _bound("FR-01.03", 0), _bound("FR-01.01", 2))
    assert [f.kind for f in verdict.hard] == ["binding_removed"]
    clean = evaluate_keystone(cs, _bound("FR-01.03", 2), _bound("FR-01.01", 2))
    assert [f.kind for f in clean.hard] == []
