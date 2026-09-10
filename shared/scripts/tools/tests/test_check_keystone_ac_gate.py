"""P3.6 THE KEYSTONE GATE — the CI CLI (``check_keystone_ac_gate.py``).

Covers the 0/1/2 exit-code mapping, the JSON shape p3.7 will consume, AC-K13
(Probe A — a hand-edited committed manifest is inert) and AC-K14 (Probe C — the
``@covers``-suffix dodge). The CLI's infrastructure boundaries — AC-K9(e)'s
base-manifest three-way read, AC-K11's base resolution and the one subprocess
smoke — are in ``test_keystone_gate_infra.py``.

**In-process ``main(argv)``, deliberately.** This repo's diff-coverage gate is
HARD at 80 % and subprocess-only tests contribute 0 % to it, so a
subprocess-per-case suite would be invisible to the very gate that guards this
file. Exactly ONE subprocess case exists (in the infra module), for the opposite
reason: it is the only thing that proves the module imports and starts as a real
``uv run`` CLI, which is a bug class this repo has shipped before.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

import check_keystone_ac_gate as gate  # noqa: E402
from verifiers import _keystone_ac_digest as kd  # noqa: E402
from verifiers import _keystone_core as kc  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests dir (helper)

from _keystone_repo import BASE_SPEC, MANIFEST_RELPATH  # noqa: E402
from _keystone_repo import bound_manifest as _manifest_with_binding  # noqa: E402
from _keystone_repo import commit_all as _commit_all  # noqa: E402
from _keystone_repo import commit_spec as _commit_spec  # noqa: E402
from _keystone_repo import edit_ac01 as _edit_ac01  # noqa: E402
from _keystone_repo import git as _git  # noqa: E402
from _keystone_repo import make_repo, write_manifest  # noqa: E402
from _keystone_repo import run_gate as _run  # noqa: E402


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path, manifest_obj=_manifest_with_binding())


# --------------------------------------------------------------------------
# Exit-code mapping and the JSON contract
# --------------------------------------------------------------------------

def test_a_green_bound_ac_exits_zero_and_reports_the_changed_ac(repo, capsys):
    code, payload = _run(repo, _edit_ac01(repo), capsys=capsys)
    assert code == gate.EXIT_OK
    assert payload["status"] == "clean"
    assert payload["changed_acs"] == ["FR-01.01/AC01"]
    assert payload["findings"] == []


def test_a_red_bound_ac_exits_one(repo, capsys):
    write_manifest(repo, _manifest_with_binding(executed="fail"))
    head = _commit_spec(
        repo, BASE_SPEC.replace("The widget must fizz.", "fizz TWICE."), "edit + red")
    code, payload = _run(repo, head, capsys=capsys)
    assert code == gate.EXIT_BLOCKED
    assert payload["status"] == "blocked"
    assert [f["kind"] for f in payload["findings"]] == ["failed"]


def test_a_docs_only_commit_exits_zero_with_an_empty_change_set(repo, capsys):
    """AC-K1 at the CLI level."""
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    code, payload = _run(repo, _commit_all(repo, "docs"), capsys=capsys)
    assert code == gate.EXIT_OK
    assert payload["changed_acs"] == [] and payload["added_acs"] == []


def test_the_json_carries_the_report_only_lists_p3_7_consumes(repo, capsys):
    head = _commit_spec(repo, BASE_SPEC.replace(
        "- [AC03] The gadget must whirr.",
        "- [AC04] The gadget must whirr differently.",
    ), "swap AC03 for AC04")
    code, payload = _run(repo, head, capsys=capsys)
    assert code == gate.EXIT_OK
    assert payload["removed_acs"] == ["FR-01.02/AC03"]
    assert payload["added_acs"] == ["FR-01.02/AC04"]
    assert payload["unbound"] == ["FR-01.02/AC04"]


def test_removing_a_bound_ac_outright_is_reported_but_does_not_block(repo, capsys):
    """Stage-3 doubt review, low. `removed_with_bindings` is report-only (design
    §7); this pins that it is populated, non-blocking, and surfaced as a stderr
    annotation (otherwise invisible in a green exit-0 CI log) when a criterion
    carrying a live test binding at base disappears from the spec outright --
    not merely edited, the ``changed``-only ``binding_removed`` gap the external
    plan review (glm medium + openai high, found from opposite directions) disclosed
    and §7 records."""
    head = _commit_spec(
        repo, BASE_SPEC.replace("- [AC01] The widget must fizz.\n", ""), "delete AC01")
    base = _git("rev-parse", "HEAD~1", cwd=repo)
    code = gate.main(["--project-root", str(repo), "--head-sha", head, "--base-sha", base])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == gate.EXIT_OK
    assert payload["removed_acs"] == ["FR-01.01/AC01"]
    assert payload["removed_with_bindings"] == ["FR-01.01/AC01"]
    assert "::warning::" in captured.err
    assert "FR-01.01/AC01" in captured.err


# --------------------------------------------------------------------------
# AC-K14 / Probe C — the @covers-suffix dodge
# --------------------------------------------------------------------------

def test_dropping_the_ac_suffix_while_editing_the_criterion_is_binding_removed(repo, capsys):
    """AC-K14. The head manifest no longer binds AC01 because the tag lost its
    ``/AC01`` suffix; the criterion changed in the same commit."""
    write_manifest(repo, _manifest_with_binding(bind_ac=False))
    head = _commit_spec(
        repo, BASE_SPEC.replace("The widget must fizz.", "fizz TWICE."), "dodge")
    code, payload = _run(repo, head, capsys=capsys)
    assert code == gate.EXIT_BLOCKED
    assert [f["kind"] for f in payload["findings"]] == ["binding_removed"]


def test_the_same_input_would_exit_zero_under_head_manifest_only_resolution(repo, capsys):
    """AC-K14's companion — the test must demonstrably FAIL against round 1's
    head-manifest-only design, not merely pass against the shipped one.

    Re-evaluates the IDENTICAL change set with no base manifest at all — which is
    what "resolve bindings from the head manifest only" amounts to, since round 1
    read ``acs[ac_id]``'s absence at head as report-only and had no base link
    count to contradict it. The verdict flips to a silent exit 0.
    """
    write_manifest(repo, _manifest_with_binding(bind_ac=False))
    head = _commit_spec(
        repo, BASE_SPEC.replace("The widget must fizz.", "fizz TWICE."), "dodge")
    base = _git("rev-parse", "HEAD~1", cwd=repo)
    head_manifest = _manifest_with_binding(bind_ac=False)
    change_set = kd.ac_change_set(
        repo, base, head, head_manifest, _manifest_with_binding())
    assert change_set.changed == {("FR-01.01", "AC01")}, "same input as the test above"

    round_one = kc.evaluate_keystone(change_set, head_manifest, {})
    assert round_one.hard == [], "round 1's design lets the dodge through"
    assert round_one.unbound == [("FR-01.01", "AC01")]

    shipped = kc.evaluate_keystone(change_set, head_manifest, _manifest_with_binding())
    assert [f.kind for f in shipped.hard] == ["binding_removed"]


# --------------------------------------------------------------------------
# AC-K13 / Probe A — a hand-edited COMMITTED manifest is inert
# --------------------------------------------------------------------------

def test_a_hand_edited_committed_manifest_cannot_flip_the_verdict(repo, capsys):
    """AC-K13. The gate reads the REGENERATED manifest on disk, which the
    preceding ci.yml step rewrites in place from this run's own JUnit. Committing
    a manifest that claims green changes nothing, because those bytes are
    overwritten before this gate ever reads them.
    """
    forged = _manifest_with_binding(executed="pass")
    write_manifest(repo, forged)
    head = _commit_spec(
        repo, BASE_SPEC.replace("The widget must fizz.", "fizz TWICE."), "forge")
    # CI's regeneration lands the truth on disk, uncommitted.
    write_manifest(repo, _manifest_with_binding(executed="fail"))
    code, payload = _run(repo, head, capsys=capsys)
    assert code == gate.EXIT_BLOCKED
    assert [f["kind"] for f in payload["findings"]] == ["failed"]
    committed = json.loads(_git("show", f"HEAD:{MANIFEST_RELPATH}", cwd=repo))
    assert committed == forged, "the forged bytes really are what was committed"


