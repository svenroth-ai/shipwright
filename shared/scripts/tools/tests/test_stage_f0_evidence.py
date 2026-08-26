"""`stage_f0_evidence.py` (iterate-2026-08-26-r1b-ci-manifest-regen-gate, AC3).

Covers: the happy path stages via one `evidence_drop.stage_reports` call from
a real retained run; refusal when no published run matches `--run-id`; the
side-manifest's own validation (duplicate unit id, a `report_path` escaping
the run directory, a `report_path` naming a file that does not exist); and
the three completeness/greenness refusals (unit-set mismatch against the
LIVE `discover_units`, a non-`pass` outcome, a missing report).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.stage_f0_evidence as mod  # noqa: E402
from scripts.tools.suite_retention import Retention  # noqa: E402
from scripts.tools.suite_units import Unit  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _one_plugin_project(tmp_path: Path, name: str = "shipwright-x") -> Path:
    """A project root `discover_units` sees exactly ONE unit in."""
    root = tmp_path / "project"
    plugin = root / "plugins" / name
    (plugin / "tests").mkdir(parents=True)
    (plugin / "pyproject.toml").write_text("", encoding="utf-8")
    return root


def _publish_green_run(project_root: Path, run_id: str, unit_name: str = "shipwright-x") -> Path:
    retention = Retention(project_root=project_root, run_id=run_id)
    unit = Unit(id=unit_name, cwd=f"plugins/{unit_name}", target="tests")
    report = project_root.parent / "r.xml"
    report.write_text("<testsuites/>", encoding="utf-8")
    retention.record(unit, report, "pass")
    return retention.publish()


def _run(project_root: Path, run_id: str, head_commit: str = "deadbeef") -> tuple[int, str, str]:
    import io
    from contextlib import redirect_stderr, redirect_stdout

    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = mod.main([
            "--project-root", str(project_root), "--run-id", run_id,
            "--head-commit", head_commit,
        ])
    return code, out.getvalue(), err.getvalue()


class TestHappyPath:
    def test_stages_the_retained_run_via_one_call(self, tmp_path):
        project_root = _one_plugin_project(tmp_path)
        _publish_green_run(project_root, "r1")

        code, out, _err = _run(project_root, "r1")

        assert code == mod.EXIT_OK
        payload = json.loads(out)
        assert payload["staged"] == 1
        assert payload["run_id"] == "r1"
        staged_junit = project_root / ".shipwright" / "compliance" / "evidence" / "junit-01.xml"
        assert staged_junit.is_file()


class TestNoPublishedRun:
    def test_no_run_found_for_run_id_exits_2(self, tmp_path):
        project_root = _one_plugin_project(tmp_path)
        code, _out, err = _run(project_root, "does-not-exist")
        assert code == mod.EXIT_ERROR
        assert "no published F0 retention run" in err


class TestManifestValidation:
    def _write_manifest(self, run_dir: Path, units: list[dict]) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "manifest.json").write_text(
            json.dumps({"schema_version": 1, "run_id": "r1", "units": units}), encoding="utf-8")

    def test_duplicate_unit_id_is_refused(self, tmp_path):
        project_root = _one_plugin_project(tmp_path)
        run_dir = mod.retention_root(project_root) / "published" / "f0-fake"
        self._write_manifest(run_dir, [
            {"unit_id": "shipwright-x", "base": "plugins/shipwright-x",
             "report_path": None, "outcome": "pass"},
            {"unit_id": "shipwright-x", "base": "plugins/shipwright-x",
             "report_path": None, "outcome": "pass"},
        ])
        code, _out, err = _run(project_root, "r1")
        assert code == mod.EXIT_ERROR
        assert "duplicate unit_id" in err

    def test_report_path_escaping_the_run_dir_is_refused(self, tmp_path):
        project_root = _one_plugin_project(tmp_path)
        run_dir = mod.retention_root(project_root) / "published" / "f0-fake"
        run_dir.mkdir(parents=True)
        outside = tmp_path / "outside.xml"
        outside.write_text("<testsuites/>", encoding="utf-8")
        self._write_manifest(run_dir, [
            {"unit_id": "shipwright-x", "base": "plugins/shipwright-x",
             "report_path": "../../../outside.xml", "outcome": "pass"},
        ])
        code, _out, err = _run(project_root, "r1")
        assert code == mod.EXIT_ERROR
        assert "resolves outside the run directory" in err

    def test_report_path_naming_a_missing_file_is_refused(self, tmp_path):
        project_root = _one_plugin_project(tmp_path)
        run_dir = mod.retention_root(project_root) / "published" / "f0-fake"
        self._write_manifest(run_dir, [
            {"unit_id": "shipwright-x", "base": "plugins/shipwright-x",
             "report_path": "reports/never-written.xml", "outcome": "pass"},
        ])
        code, _out, err = _run(project_root, "r1")
        assert code == mod.EXIT_ERROR
        assert "does not exist" in err

    def test_an_entry_missing_base_is_refused(self, tmp_path):
        """Code review: main() indexes `e["base"]` unguarded once past
        validation — an entry with `unit_id`/`outcome` but no `base` must be
        refused HERE with a named field, not reach that indexing as an
        uncaught KeyError (the same malformed-input class External-Code-Review
        findings #3/#4 fixed in the sibling comparator/drift-check tools)."""
        project_root = _one_plugin_project(tmp_path)
        run_dir = mod.retention_root(project_root) / "published" / "f0-fake"
        self._write_manifest(run_dir, [
            {"unit_id": "shipwright-x", "report_path": None, "outcome": "pass"},
        ])
        code, _out, err = _run(project_root, "r1")
        assert code == mod.EXIT_ERROR
        assert "malformed unit entry" in err


class TestCompletenessAndGreenness:
    def test_unit_set_mismatch_against_live_discovery_is_refused(self, tmp_path):
        project_root = _one_plugin_project(tmp_path)
        # Retained run covers a DIFFERENT unit than the one now discovered.
        _publish_green_run(project_root, "r1", unit_name="shipwright-stale")
        code, _out, err = _run(project_root, "r1")
        assert code == mod.EXIT_ERROR
        assert "does not match the units discovered" in err

    def test_a_non_pass_outcome_is_refused(self, tmp_path):
        project_root = _one_plugin_project(tmp_path)
        retention = Retention(project_root=project_root, run_id="r1")
        unit = Unit(id="shipwright-x", cwd="plugins/shipwright-x", target="tests")
        report = tmp_path / "r.xml"
        report.write_text("<testsuites/>", encoding="utf-8")
        retention.record(unit, report, "test_failure")
        retention.publish()

        code, _out, err = _run(project_root, "r1")
        assert code == mod.EXIT_ERROR
        assert "not fully green" in err

    def test_a_missing_report_is_refused(self, tmp_path):
        project_root = _one_plugin_project(tmp_path)
        retention = Retention(project_root=project_root, run_id="r1")
        unit = Unit(id="shipwright-x", cwd="plugins/shipwright-x", target="tests")
        never_written = tmp_path / "never.xml"
        retention.record(unit, never_written, "pass")  # outcome pass, but no report file
        retention.publish()

        code, _out, err = _run(project_root, "r1")
        assert code == mod.EXIT_ERROR
        assert "no retained report" in err


class TestCliSmoke:
    def test_real_subprocess_invocation_imports_and_starts_cleanly(self):
        """Guards the sys.path bug class this file's own module comment
        documents: a prior draft's `from lib import evidence_drop` only
        worked under pytest's own collection-time sys.path side effect and
        crashed immediately (`ModuleNotFoundError: No module named 'lib'`)
        as a real `uv run` invocation. A missing run_id is expected to
        refuse cleanly (exit 2); what matters is that it reaches that
        refusal at all, rather than dying on import."""
        result = subprocess.run(
            ["uv", "run", "shared/scripts/tools/stage_f0_evidence.py",
             "--run-id", "nonexistent-run", "--head-commit", "deadbeef"],
            cwd=_REPO_ROOT, capture_output=True, text=True, timeout=60,
        )
        assert "ModuleNotFoundError" not in result.stderr
        assert result.returncode == mod.EXIT_ERROR
        assert "no published F0 retention run found" in result.stderr
