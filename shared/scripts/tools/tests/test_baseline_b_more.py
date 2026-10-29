"""BP unit BL0b - run command shape, probe plumbing (candidates, JUnit, bindings), and the phase-A summary arithmetic."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools
sys.path.insert(0, str(Path(__file__).resolve().parent))

from verifiers import _baseline_b_probes as probes  # noqa: E402
from verifiers import _baseline_b_summary as summary  # noqa: E402
from verifiers import _baseline_head_run as head_run  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")

TEST_SRC = 'import pytest\n\n\n@pytest.mark.covers("FR-01.09/AC02")\ndef test_bound():\n    assert True\n\n\ndef test_free():\n    assert True\n'
JUNIT = (
    '<testsuites><testsuite><testcase classname="tests.test_m.TestC" name="test_bound"><failure message="x"/></testcase>'
    '<testcase classname="tests.test_m" name="test_free"/></testsuite></testsuites>'
)


def test_root_command_runs_plugin_roots_from_their_directory_and_shared_roots_from_the_tree(tmp_path):
    (tmp_path / "plugins/shipwright-x/scripts").mkdir(parents=True)
    cmd, cwd = head_run.root_command(tmp_path, "plugins/shipwright-x/tests", tmp_path / "db", tmp_path / "j.xml")
    assert cwd == tmp_path / "plugins/shipwright-x" and "--cov=scripts" in cmd and "--cov-context=test" in cmd and "tests/" in cmd
    cmd, cwd = head_run.root_command(tmp_path, "shared/tests", tmp_path / "db", tmp_path / "j.xml")
    assert cwd == tmp_path and "--cov=shared" in cmd and "not slow and not cross_plugin" in cmd


def test_run_root_records_exit_code_summary_and_database_size(tmp_path, monkeypatch):
    tree, out = tmp_path / "tree", tmp_path / "out"
    tree.mkdir()

    def fake_run(cmd, cwd, env, stdout, stderr, timeout, check):
        stdout.write("3 passed in 0.1s\n")
        Path(env["COVERAGE_FILE"]).write_bytes(b"x" * 10)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(head_run.subprocess, "run", fake_run)
    runs = head_run.run_all(tree, ["shared/tests"], out)
    assert runs[0]["rc"] == 0 and runs[0]["summary"] == "3 passed in 0.1s" and runs[0]["db_bytes"] == 10 and (out / "runs.json").is_file()

    def slow(*a, **k):
        raise subprocess.TimeoutExpired("uv", 1)

    monkeypatch.setattr(head_run.subprocess, "run", slow)
    assert head_run.run_root(tree, "shared/tests", out, {}, 1)["timed_out"] is True


def test_candidate_tests_need_a_covers_mark_and_the_module_name(tmp_path):
    (tmp_path / "shared/tests").mkdir(parents=True)
    (tmp_path / "shared/tests/test_widget.py").write_text(TEST_SRC + "\n# uses widget\n")
    (tmp_path / "shared/tests/test_other.py").write_text("def test_x():\n    widget = 1\n")  # names it, no covers mark
    got = probes.candidate_tests(tmp_path, {"file": "shared/scripts/widget.py"})
    assert got == {"shared/tests": ["shared/tests/test_widget.py"]}


def test_junit_failures_resolve_class_names_to_files_and_bindings_are_read(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_m.py").write_text(TEST_SRC.replace("def test_bound", "class TestC:\n    def test_bound").replace("    assert True\n\n\ndef test_free", "        assert True\n\n\ndef test_free", 1))
    xml = tmp_path / "j.xml"
    xml.write_text(JUNIT)
    failed = probes.junit_failures(xml, tmp_path, "")
    assert failed == {"tests/test_m.py::TestC.test_bound"}
    assert probes.junit_failures(tmp_path / "missing.xml", tmp_path, "") == set()
    (tmp_path / "tests/test_b.py").write_text(TEST_SRC)
    assert probes.tokens_for(tmp_path, {"tests/test_b.py::test_bound", "tests/test_b.py::test_free[p1]"}) == {"tests/test_b.py::test_bound": True, "tests/test_b.py::test_free[p1]": False}
    assert len(probes.draw([{"i": i} for i in range(10)], 3, 1)) == 3


def test_junit_failures_treat_dtd_garbled_and_oversized_reports_as_no_failures(tmp_path, monkeypatch):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_m.py").write_text("")
    xml = tmp_path / "j.xml"
    xml.write_text(JUNIT)
    assert probes.junit_failures(xml, tmp_path, "") == {"tests/test_m.py::TestC.test_bound"}
    xml.write_text('<!DOCTYPE r [<!ENTITY a "x">]>' + JUNIT)  # entity-expansion door stays shut
    assert probes.junit_failures(xml, tmp_path, "") == set()
    xml.write_text("<testsuites><testcase")
    assert probes.junit_failures(xml, tmp_path, "") == set()
    xml.write_bytes(b"\xff\xfe<testsuites/>")
    assert probes.junit_failures(xml, tmp_path, "") == set()
    xml.write_text(JUNIT)
    monkeypatch.setattr(probes, "_MAX_XML_BYTES", 10)
    assert probes.junit_failures(xml, tmp_path, "") == set()


def test_run_probe_reads_failures_from_the_junit_file(tmp_path, monkeypatch):
    (tmp_path / "plugins/shipwright-x/tests").mkdir(parents=True)
    (tmp_path / "plugins/shipwright-x/tests/test_m.py").write_text(TEST_SRC)

    def fake_run(cmd, cwd, env, capture_output, text, timeout, check):
        junit = next(c.split("=", 1)[1] for c in cmd if c.startswith("--junitxml="))
        Path(junit).write_text('<testsuites><testsuite><testcase classname="tests.test_m" name="test_bound"><error/></testcase></testsuite></testsuites>')
        return subprocess.CompletedProcess(cmd, 1)

    monkeypatch.setattr(probes.subprocess, "run", fake_run)
    res = probes.run_probe(tmp_path, "plugins/shipwright-x/tests", ["plugins/shipwright-x/tests/test_m.py"], tmp_path, {}, 5)
    assert res["rc"] == 1 and res["failed"] == ["plugins/shipwright-x/tests/test_m.py::test_bound"]


def _record(pr, sources, declared, new=()):
    return {"pr": pr, "sources": {fr: ["test"] for fr in sources}, "declared": list(declared), "class": "iterate", "new_frs": list(new), "code": {}}


def test_phase_a_summary_scores_sources_and_counts_holds():
    replay = {"records": [_record(1, ["FR-01.09"], ["FR-01.09"]), _record(2, [], ["FR-01.10"]), _record(3, ["FR-01.05"], [])],
              "code": {"prs": [{"pr": 2, "code": {"FR-01.10": ["f"]}, "fan_out": {"a.py::f": ["FR-01.10"]}}]}}
    head = {"2": {"touched": {"FR-01.10": ["a.py::f"]}, "fan_out": {"a.py::f": ["FR-01.10"]}, "tokens": {"a.py::f": ["FR-01.10/AC01"]},
                  "notes": [{"kind": "missing_at_head", "key": "b.py::g"}, {"kind": "module_level", "key": "m"}], "new_code": {"class": "a"}},
            "1": {"touched": {}, "fan_out": {}, "tokens": {}, "notes": [], "new_code": {"class": "none"}},
            "3": {"touched": {}, "fan_out": {}, "tokens": {}, "notes": [], "new_code": {"class": "b"}}}
    a = {"headmap": {"per_pr": head}, "paths": {"per_pr": {"3": {"FR-01.05": ["x"]}}},
         "ac_git_leg": {"1": {"test": {"FR-01.09/AC01": ["t"]}, "static": {}}, "2": {"test": {}, "static": {}}, "3": {"test": {}, "static": {}}}}
    out = summary.summarise_phase_a(replay, a, {"2": "declared_only_behaviour"})
    assert out["head_mapping"]["missing_at_head"] == 1 and out["head_mapping"]["mapped_to_an_fr"] == 1
    assert out["crosscheck_vs_merge_base_db"]["pairs_agree"] == 1 and out["crosscheck_vs_merge_base_db"]["pairs_only_head"] == 0
    assert out["hold_empty_scope"]["git+tcode_head"] == 3 and out["hold_scope_eq_declared_fr_level"]["git+tcode_head"] == 1
    assert out["declared_only_16"]["tcode_head_finds_a_declared_fr"] == [2] and out["declared_only_16"]["new_code_class"] == {"a": 1}
    assert out["vs_declared_reference_45_prs"]["git"]["recall"] == 0.5
    assert out["ac_level"]["explicit_ac_tokens"] == 2


def test_probe_summary_separates_caught_from_not_caught_and_reports_tcode_recall():
    results = [{"status": "judged", "cause": "caught", "tcode_attributes_fr": True},
               {"status": "judged", "cause": "caught", "tcode_attributes_fr": False},
               {"status": "judged", "cause": "bound_test_executes_but_assertion_survives", "tcode_attributes_fr": True, "second_pass": {"bound_failures": ["t"]}},
               {"status": "skipped_mutation_did_not_parse"}]
    out = summary.summarise_probes({"results": results, "eligible_functions": 9, "seed": 1})
    assert out["judged"] == 3 and out["caught_by_a_bound_test"] == 2 and out["tcode_recall_on_caught"] == {"hit": 1, "of": 2, "rate": 0.5}
    assert out["tcode_flags_but_no_bound_test_fails"] == 1 and out["second_pass_tcode_flagged_without_textual_candidate"] == {"probes": 1, "a_bound_test_failed": 1}
