"""Pins `compare_traceability_manifest.py`'s two-tier drift contract
(iterate-2026-08-26-r1b-ci-manifest-regen-gate, AC1).

Structural tier (enforced, exit 1 on drift): every field EXCEPT
`generated_at`/`source_commit` at the top level, and EXCEPT the entire
`tests` map and `coverage` map per requirement — both are execution-derived
(`_test_links_requirements.py::_cov_status` computes `coverage` straight from
`tests`), so a marker/OS-selection difference in which tests ran must never
gate. Execution tier (report-only, never gates): shared test-id
status/executed agreement, and one-sided ids reported as platform-selection
differences.

Exit codes: 0 = no structural drift, 1 = structural drift (advisory only —
the CI step reports, never fails, on this code), 2 = usage/runtime error
(malformed input, missing file) — must never be swallowed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.compare_traceability_manifest as mod  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _requirement(**overrides):
    node = {
        "id": "FR-01.06",
        "spec_path": ".shipwright/planning/01-adopted/spec.md",
        "title": "Example requirement.",
        "priority": "Must",
        "status": "active",
        "required_layers": ["unit"],
        "required_layers_source": "inferred_legacy",
        "tests": {
            "unit": [
                {
                    "id": "plugins/x/tests/test_a.py::test_one",
                    "path": "plugins/x/tests/test_a.py::test_one",
                    "layer": "unit",
                    "status": "enabled",
                    "executed": "pass",
                },
            ],
        },
        "coverage": {"unit": "ok"},
    }
    node.update(overrides)
    return node


def _manifest(*, generated_at="2026-08-26T00:00:00+00:00",
              source_commit="a" * 40, requirements=None):
    return {
        "schema_version": 3,
        "collector_version": "test_links/1.0.0",
        "generated_at": generated_at,
        "source_commit": source_commit,
        "spec_hash": "sha256:" + "b" * 64,
        "requirements": requirements if requirements is not None else {
            "01::FR-01.06": _requirement(),
        },
        "orphans": [],
        "invalid_tags": [],
        "invalid_layers": [],
        "untagged_tests": [],
    }


def _write(tmp_path: Path, name: str, data: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _run(tmp_path, old: dict, new: dict) -> tuple[int, str]:
    committed = _write(tmp_path, "committed.json", old)
    regenerated = _write(tmp_path, "regenerated.json", new)
    code, stdout = mod.main_with_output(
        ["--check", "--committed", str(committed), "--regenerated", str(regenerated)]
    )
    return code, stdout


class TestIdenticalExceptProvenance:
    def test_only_generated_at_and_source_commit_differ_is_not_drift(self, tmp_path):
        old = _manifest(generated_at="2026-08-01T00:00:00+00:00", source_commit="a" * 40)
        new = _manifest(generated_at="2026-08-26T12:00:00+00:00", source_commit="c" * 40)
        code, stdout = _run(tmp_path, old, new)
        assert code == mod.EXIT_OK
        assert "structural" in stdout.lower()


class TestExecutionTierNeverGates:
    def test_shared_id_differing_status_is_reported_not_gated(self, tmp_path):
        old_req = _requirement()
        new_req = _requirement(tests={
            "unit": [{
                "id": "plugins/x/tests/test_a.py::test_one",
                "path": "plugins/x/tests/test_a.py::test_one",
                "layer": "unit",
                "status": "deselected",
                "executed": "not_run",
            }],
        })
        old = _manifest(requirements={"01::FR-01.06": old_req})
        new = _manifest(requirements={"01::FR-01.06": new_req})
        code, stdout = _run(tmp_path, old, new)
        assert code == mod.EXIT_OK
        assert "test_one" in stdout

    def test_shared_id_differing_executed_is_reported_not_gated(self, tmp_path):
        old_req = _requirement()
        new_req = _requirement(tests={
            "unit": [{
                "id": "plugins/x/tests/test_a.py::test_one",
                "path": "plugins/x/tests/test_a.py::test_one",
                "layer": "unit",
                "status": "enabled",
                "executed": "fail",
            }],
        })
        old = _manifest(requirements={"01::FR-01.06": old_req})
        new = _manifest(requirements={"01::FR-01.06": new_req})
        code, stdout = _run(tmp_path, old, new)
        assert code == mod.EXIT_OK
        assert "test_one" in stdout

    def test_one_sided_ids_never_gate(self, tmp_path):
        old_req = _requirement(tests={
            "unit": [
                {
                    "id": "plugins/x/tests/test_a.py::test_one",
                    "path": "plugins/x/tests/test_a.py::test_one",
                    "layer": "unit",
                    "status": "enabled",
                    "executed": "pass",
                },
                {
                    "id": "plugins/x/tests/test_win.py::test_windows_only",
                    "path": "plugins/x/tests/test_win.py::test_windows_only",
                    "layer": "unit",
                    "status": "enabled",
                    "executed": "pass",
                },
            ],
        })
        new_req = _requirement()  # only test_one, as if collected on Linux
        old = _manifest(requirements={"01::FR-01.06": old_req})
        new = _manifest(requirements={"01::FR-01.06": new_req})
        code, stdout = _run(tmp_path, old, new)
        assert code == mod.EXIT_OK
        assert "test_windows_only" in stdout

    def test_coverage_map_disagreement_alone_is_not_structural(self, tmp_path):
        old_req = _requirement(coverage={"unit": "ok"})
        new_req = _requirement(coverage={"unit": "MISSING"})
        old = _manifest(requirements={"01::FR-01.06": old_req})
        new = _manifest(requirements={"01::FR-01.06": new_req})
        code, _stdout = _run(tmp_path, old, new)
        assert code == mod.EXIT_OK


class TestStructuralDriftGates:
    def test_priority_change_is_structural_drift(self, tmp_path):
        old_req = _requirement(priority="Must")
        new_req = _requirement(priority="Should")
        old = _manifest(requirements={"01::FR-01.06": old_req})
        new = _manifest(requirements={"01::FR-01.06": new_req})
        code, stdout = _run(tmp_path, old, new)
        assert code == mod.EXIT_STRUCTURAL_DRIFT
        assert "priority" in stdout.lower() or "Should" in stdout

    def test_required_layers_change_is_structural_drift(self, tmp_path):
        old_req = _requirement(required_layers=["unit"])
        new_req = _requirement(required_layers=["unit", "e2e"])
        old = _manifest(requirements={"01::FR-01.06": old_req})
        new = _manifest(requirements={"01::FR-01.06": new_req})
        code, _stdout = _run(tmp_path, old, new)
        assert code == mod.EXIT_STRUCTURAL_DRIFT

    def test_added_requirement_is_structural_drift(self, tmp_path):
        old = _manifest(requirements={"01::FR-01.06": _requirement()})
        new = _manifest(requirements={
            "01::FR-01.06": _requirement(),
            "01::FR-01.07": _requirement(id="FR-01.07"),
        })
        code, _stdout = _run(tmp_path, old, new)
        assert code == mod.EXIT_STRUCTURAL_DRIFT

    def test_top_level_orphans_change_is_structural_drift(self, tmp_path):
        old = _manifest()
        old["orphans"] = []
        new = _manifest()
        new["orphans"] = ["plugins/x/tests/test_orphan.py::test_x"]
        code, _stdout = _run(tmp_path, old, new)
        assert code == mod.EXIT_STRUCTURAL_DRIFT


class TestErrorHandling:
    def test_missing_required_top_level_field_exits_2(self, tmp_path):
        old = _manifest()
        new = _manifest()
        del new["spec_hash"]
        code, stdout = _run(tmp_path, old, new)
        assert code == mod.EXIT_ERROR
        assert "spec_hash" in stdout or "spec_hash" in stdout.lower()

    def test_missing_required_requirement_field_exits_2(self, tmp_path):
        old = _manifest()
        bad_req = _requirement()
        del bad_req["required_layers_source"]
        new = _manifest(requirements={"01::FR-01.06": bad_req})
        code, _stdout = _run(tmp_path, old, new)
        assert code == mod.EXIT_ERROR

    def test_null_tests_field_exits_2_not_an_unhandled_crash(self, tmp_path):
        """External review: `"tests": null` reached execution_report()'s
        `set(old_tests)` uncaught, exiting 1 (Python's default) instead of the
        documented EXIT_ERROR — a malformed-input case must fail here, not
        three calls downstream."""
        old = _manifest()
        bad_req = _requirement(tests=None)
        new = _manifest(requirements={"01::FR-01.06": bad_req})
        code, stdout = _run(tmp_path, old, new)
        assert code == mod.EXIT_ERROR
        assert "tests" in stdout

    def test_non_list_layer_in_tests_exits_2(self, tmp_path):
        old = _manifest()
        bad_req = _requirement(tests={"unit": "not-a-list"})
        new = _manifest(requirements={"01::FR-01.06": bad_req})
        code, stdout = _run(tmp_path, old, new)
        assert code == mod.EXIT_ERROR
        assert "unit" in stdout

    def test_test_record_missing_id_exits_2(self, tmp_path):
        """External review: `t["id"]` in execution_report()'s dict comprehension
        raised an uncaught KeyError for a record with no `id`."""
        old = _manifest()
        bad_req = _requirement(tests={"unit": [{"status": "enabled", "executed": "pass"}]})
        new = _manifest(requirements={"01::FR-01.06": bad_req})
        code, stdout = _run(tmp_path, old, new)
        assert code == mod.EXIT_ERROR
        assert "id" in stdout

    def test_missing_file_exits_2(self, tmp_path):
        committed = _write(tmp_path, "committed.json", _manifest())
        missing = tmp_path / "does-not-exist.json"
        code, stdout = mod.main_with_output(
            ["--check", "--committed", str(committed), "--regenerated", str(missing)]
        )
        assert code == mod.EXIT_ERROR
        assert "does-not-exist" in stdout

    def test_malformed_json_exits_2(self, tmp_path):
        committed = _write(tmp_path, "committed.json", _manifest())
        regenerated = tmp_path / "regenerated.json"
        regenerated.write_text("{not valid json", encoding="utf-8")
        code, stdout = mod.main_with_output(
            ["--check", "--committed", str(committed), "--regenerated", str(regenerated)]
        )
        assert code == mod.EXIT_ERROR
        assert stdout  # some diagnostic was printed, not silently swallowed

    def test_missing_check_flag_exits_2(self, tmp_path):
        committed = _write(tmp_path, "committed.json", _manifest())
        regenerated = _write(tmp_path, "regenerated.json", _manifest())
        code, _stdout = mod.main_with_output(
            ["--committed", str(committed), "--regenerated", str(regenerated)]
        )
        assert code == mod.EXIT_ERROR


class TestCliSmoke:
    def test_real_subprocess_invocation_imports_and_runs(self, tmp_path):
        committed = _write(tmp_path, "committed.json", _manifest())
        regenerated = _write(tmp_path, "regenerated.json", _manifest())
        result = subprocess.run(
            ["uv", "run", "shared/scripts/tools/compare_traceability_manifest.py",
             "--check", "--committed", str(committed), "--regenerated", str(regenerated)],
            cwd=_REPO_ROOT, capture_output=True, text=True, timeout=60,
        )
        assert "ModuleNotFoundError" not in result.stderr
        assert result.returncode == mod.EXIT_OK
