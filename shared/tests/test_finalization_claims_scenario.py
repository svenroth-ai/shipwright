"""Integration scenario: the finalization-claims gates, each asserted in isolation (U11).

One compliant run is built in ``tmp_path`` at run time (a ``main`` trunk, an
``iterate/probe`` branch, the run's records and staged evidence), so no untagged
fixture test is ever committed here. Each case then breaks exactly ONE claim and
asserts (1) the owning gate fails with its own diagnostic and (2) every other
gate stays green. A second red gate would mask a missing check, so the second
half is what makes the cases independent.

Gates: U1 test-tag, U3 review record (every complexity), U4 cascade trigger
(small), U5 F0.5 surface (medium+), U6 requirement gates (``spec_impact: none``
needs a closed code; ``change_type`` is checked against the diff).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.append(str(Path(__file__).resolve().parent))  # after shared/scripts: tests/ has its own `tools`

import pytest  # noqa: E402

from _cascade_trigger_fixtures import commit_file, git, hermetic_git, init_repo, lines  # noqa: E402, F401 - hermetic_git is an autouse fixture
from _finalization_scenario_records import RUN, event, write_entry, write_review_record  # noqa: E402
from _surface_check_fixtures import NONE_BLOCK, cli_block, stage  # noqa: E402
from lib.fr_gates import run_fr_gates  # noqa: E402
from tools.verifiers._layer_coverage_regen import clear_regen_cache  # noqa: E402
from tools.verifiers.cascade_trigger import CHECK_NAME as U4_NAME  # noqa: E402
from tools.verifiers.cascade_trigger import check_cascade_trigger  # noqa: E402
from tools.verifiers.iterate_checks import run_all_checks  # noqa: E402
from tools.verifiers.review_record_check import check_review_record  # noqa: E402
from tools.verifiers.surface_check import CHECK_NAME as U5_NAME  # noqa: E402
from tools.verifiers.surface_check import check_surface_verification  # noqa: E402
from tools.verifiers.tag_binding_gate import CHECK_NAME as U1_NAME  # noqa: E402
from tools.verifiers.tag_binding_gate import check_test_tag_binding  # noqa: E402

_SPEC = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-02.01 | Log in | Must | unit |\n\n### FR-02.01 — Log in\n\n"
    "- (E) [AC01] Given a user, when they log in, then they see the dashboard.\n"
)
_OLD = "def test_old():\n    assert 1 + 1 == 2\n"
_TAGGED = '\n\nimport pytest\n\n\n@pytest.mark.covers("FR-02.01/AC01")\ndef test_new():\n    pass\n'
_UNTAGGED = "\n\ndef test_new():\n    pass\n"
_DELEGATED = {"status": "not_run", "reason_code": "delegated-to-orchestrator"}
_EXTERNAL = {"status": "completed", "provider": "openrouter"}  # medium+ needs a review that ran
GATES = ("U1", "U3", "U4", "U5", "U6")
#: Gates whose own scope does not reach a complexity SKIP there (ok=True, severity SKIPPED). A skip is
#: not a pass: the compliant run must skip exactly this set, so a gate that silently stops running
#: (or starts running where it should not) fails the scenario instead of reading green.
EXPECTED_SKIPS = {"trivial": {"U4", "U5"}, "small": {"U5"}, "medium": {"U4"}}


class Gate(NamedTuple):
    ok: bool
    detail: str
    skipped: bool = False


def scenario(tmp_path: Path, complexity: str, *, tagged: bool = True, extra: dict | None = None,
             code_row: dict | None = None, surface: dict | None = None, evidence: bool = True):
    """A compliant run at ``complexity``; the keyword arguments break (or reshape) one claim."""
    clear_regen_cache()
    root = tmp_path / "repo"
    init_repo(root)
    for rel, text in {".shipwright/planning/app/spec.md": _SPEC, "tests/test_a.py": _OLD,
                      "base.txt": lines(200)}.items():
        commit_file(root, rel, text, f"base {rel}")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(root, "checkout", "-q", "-b", "iterate/probe")
    files = {"tests/test_a.py": _OLD + (_TAGGED if tagged else _UNTAGGED), "src/a.py": "x = 1\n",
             "shipwright_run_config.json": json.dumps({"iterate_history": [
                 {"run_id": RUN, "complexity": complexity, "type": "change"}]}),
             "shipwright_events.jsonl": json.dumps({"type": "work_completed", "adr_id": RUN,
                                                    "affected_frs": ["FR-02.01"], "new_frs": []}) + "\n",
             **(extra or {})}
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "change")
    write_entry(root, complexity, cli_block() if surface is None else surface)
    medium = complexity == "medium"
    write_review_record(root, complexity, code_row=code_row or (_DELEGATED if medium else None),
                        external_row=_EXTERNAL if medium else None)
    if evidence:
        stage(root, run_id=RUN)
    return root, git(root, "rev-parse", "HEAD")


def run_gates(root: Path, sha: str, ev: dict | None = None) -> dict[str, Gate]:
    """Every gate once -> ``{gate: Gate(ok, diagnostic, skipped)}``; a gate's result never gates another."""
    err = run_fr_gates(ev or event(), root, "scenario")
    others = {"U1": check_test_tag_binding(root, RUN, sha), "U3": check_review_record(root, RUN),
              "U4": check_cascade_trigger(root, RUN, sha), "U5": check_surface_verification(root, RUN, sha)}
    out = {gate: Gate(bool(result.ok), result.detail, result.is_skipped) for gate, result in others.items()}
    out["U6"] = Gate(err is None, "" if err is None else f"{err['error']}: {err['detail']}")
    return out


def assert_only(results: dict, broken: str, *needles: str) -> None:
    """``broken`` fails with each needle in its diagnostic; every other gate is green."""
    assert not results[broken].ok, f"{broken} accepted a broken claim: {results[broken].detail}"
    for needle in needles:
        assert needle in results[broken].detail, f"{broken} diagnostic lacks {needle!r}: {results[broken].detail}"
    assert not results[broken].skipped, f"{broken} was skipped, not run: {results[broken].detail}"
    masked = {g: r.detail for g, r in results.items() if g != broken and not r.ok}
    assert not masked, f"{broken} is not isolated, other gates also failed: {masked}"


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("complexity", ["trivial", "small", "medium"])
def test_a_compliant_run_passes_every_gate_at_every_complexity(tmp_path, complexity):
    root, sha = scenario(tmp_path, complexity)
    results = run_gates(root, sha)
    assert {g: r.ok for g, r in results.items()} == dict.fromkeys(GATES, True), results
    assert {g for g, r in results.items() if r.skipped} == EXPECTED_SKIPS[complexity], results


@pytest.mark.covers("FR-01.11/AC41")
def test_u1_an_untagged_added_test_is_the_only_red_gate(tmp_path):
    root, sha = scenario(tmp_path, "small", tagged=False)
    assert_only(run_gates(root, sha), "U1", "tests/test_a.py::test_new", "untagged-added")


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("complexity", ["trivial", "small", "medium"])
def test_u3_a_record_with_no_self_review_is_the_only_red_gate(tmp_path, complexity):
    root, sha = scenario(tmp_path, complexity)
    medium = complexity == "medium"  # keep the medium rows: only `self` may be broken
    write_review_record(root, complexity, self_status="not_run",
                        code_row=_DELEGATED if medium else None, external_row=_EXTERNAL if medium else None)
    assert_only(run_gates(root, sha), "U3", "the Self-Review is the one pass that runs at EVERY")


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("complexity", ["trivial", "small", "medium"])
def test_u3_free_text_closures_are_the_only_red_gate(tmp_path, complexity):
    root, sha = scenario(tmp_path, complexity)
    medium = complexity == "medium"
    write_review_record(root, complexity, reason_code=None,
                        code_row=_DELEGATED if medium else None, external_row=_EXTERNAL if medium else None)
    assert_only(run_gates(root, sha), "U3", "reason_code")


@pytest.mark.covers("FR-01.11")
def test_u4_a_150_line_small_diff_with_a_vocab_code_that_denies_the_trigger_is_the_only_red_gate(tmp_path):
    root, sha = scenario(tmp_path, "small", extra={"src/big.py": lines(150)},
                         code_row={"status": "not_run", "reason_code": "diff-below-threshold"})
    assert_only(run_gates(root, sha), "U4", "changed lines > 100", "says the trigger did not fire")


@pytest.mark.covers("FR-01.11")
def test_u4_the_same_diff_closed_with_an_accepted_code_passes(tmp_path):
    root, sha = scenario(tmp_path, "small", extra={"src/big.py": lines(150)},
                         code_row={"status": "not_run", "reason_code": "delegated-to-orchestrator"})
    results = run_gates(root, sha)
    assert all(r.ok for r in results.values()), results
    assert "delegated-to-orchestrator" in results["U4"].detail
    assert not results["U4"].skipped


@pytest.mark.covers("FR-01.11/AC07")
def test_u5_none_on_a_diff_that_touches_an_api_route_is_the_only_red_gate(tmp_path):
    root, sha = scenario(tmp_path, "medium", surface=NONE_BLOCK,
                         extra={"server/routes/tasks.ts": "export const t = 1;\n"})
    assert_only(run_gates(root, sha), "U5", "refused", "api_route", "server/routes/tasks.ts")


@pytest.mark.covers("FR-01.11/AC07")
def test_u5_a_claimed_run_with_no_staged_evidence_is_the_only_red_gate(tmp_path):
    root, sha = scenario(tmp_path, "medium", evidence=False)
    assert_only(run_gates(root, sha), "U5", "absent", "stage_f0_evidence.py")


@pytest.mark.covers("FR-01.11/AC07")
def test_u5_evidence_for_other_tests_than_the_claim_is_the_only_red_gate(tmp_path):
    root, sha = scenario(tmp_path, "medium", surface=cli_block(tests_run=9))
    assert_only(run_gates(root, sha), "U5", "the block records tests_run=9, but the staged evidence shows only")


@pytest.mark.covers("FR-01.11/AC03")
def test_u6_spec_impact_none_without_a_closed_code_is_the_only_red_gate(tmp_path):
    root, sha = scenario(tmp_path, "small")
    ev = event()
    del ev["spec_impact_reason_code"]
    assert_only(run_gates(root, sha, ev), "U6", "spec_impact_none_requires_reason_code")


@pytest.mark.covers("FR-01.11/AC03")
def test_u6_a_docs_label_over_a_diff_with_runtime_code_is_the_only_red_gate(tmp_path):
    root, sha = scenario(tmp_path, "small", extra={"docs/guide.md": "words\n"})
    ev = event(change_type="docs", none_reason="prose only")
    ev.pop("affected_frs")
    assert_only(run_gates(root, sha, ev), "U6", "change_type_not_covered_by_diff", "src/a.py")


@pytest.mark.covers("FR-01.11")
def test_breaking_every_small_claim_at_once_reports_each_gate_red_independently(tmp_path):
    """The converse of isolation: with every small-scope claim broken, each gate says so.

    U5 is a medium+ gate, so at small even a ``none`` claim over an API route is out of its scope.
    """
    root, sha = scenario(tmp_path, "small", tagged=False, surface=NONE_BLOCK,
                         extra={"src/big.py": lines(150), "server/routes/tasks.ts": "export const t = 1;\n"},
                         code_row={"status": "not_run", "reason_code": "diff-below-threshold"})
    write_review_record(root, "small", self_status="not_run",
                        code_row={"status": "not_run", "reason_code": "diff-below-threshold"})
    ev = event()
    del ev["spec_impact_reason_code"]
    results = run_gates(root, sha, ev)
    assert [g for g, r in results.items() if not r.ok] == ["U1", "U3", "U4", "U6"], results
    assert results["U5"].ok and results["U5"].skipped, results["U5"]
    assert not any(results[g].skipped for g in ("U1", "U3", "U4", "U6")), results


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize(("complexity", "name", "needle"), [
    ("small", U1_NAME, "untagged-added"), ("small", U4_NAME, "changed lines > 100"), ("medium", U5_NAME, "refused")])
def test_f11_entry_point_reports_each_broken_gate_under_its_own_name(tmp_path, complexity, name, needle):
    """``run_all_checks`` wires U1/U4/U5 and keeps their diagnostics when several gates fail together."""
    root, sha = scenario(tmp_path, complexity, tagged=False, surface=NONE_BLOCK,
                         extra={"src/big.py": lines(150), "server/routes/tasks.ts": "export const t = 1;\n"},
                         code_row={"status": "not_run", "reason_code": "diff-below-threshold"})
    by_name = {r.name: r for r in run_all_checks(root, RUN, sha)}
    assert name in by_name and not by_name[name].ok and needle in by_name[name].detail, by_name.get(name)
