"""F0 evidence retention (iterate-2026-08-26-r1b-ci-manifest-regen-gate, AC2).

Covers: per-unit base derivation agrees with `suite_root_plan.base_for_root`;
retry-supersedes-initial via same-destination overwrite; a missing report is
recorded with `report_path: null` rather than silently dropped; publish is
atomic (nothing lands under `published/` until every unit is recorded); and
pruning keeps only the newest RETAINED_RUNS published runs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.suite_retention as mod  # noqa: E402
from scripts.tools.suite_units import Unit  # noqa: E402


def _project_root(tmp_path: Path) -> Path:
    # A non-git tmp dir: resolve_main_repo_root falls back to project_root
    # itself, which is exactly what a plain (non-worktree) test wants.
    root = tmp_path / "project"
    root.mkdir()
    return root


def _plugin_unit(name: str = "shipwright-x") -> Unit:
    return Unit(id=name, cwd=f"plugins/{name}", target="tests")


def _shared_unit() -> Unit:
    return Unit(id="shared/tests", cwd=".", target="shared/tests")


def test_unit_base_of_a_plugin_unit(tmp_path):
    project_root = _project_root(tmp_path)
    assert mod.unit_base(project_root, _plugin_unit("shipwright-x")) == "plugins/shipwright-x"


def test_unit_base_of_a_shared_unit_is_empty(tmp_path):
    project_root = _project_root(tmp_path)
    assert mod.unit_base(project_root, _shared_unit()) == ""


def test_retention_root_falls_back_to_project_root_outside_git(tmp_path):
    project_root = _project_root(tmp_path)
    assert mod.retention_root(project_root) == project_root / ".shipwright" / "runs" / "f0-evidence"


class TestRecordAndPublish:
    def test_publish_writes_a_manifest_with_base_report_path_and_outcome(self, tmp_path):
        project_root = _project_root(tmp_path)
        retention = mod.Retention(project_root=project_root, run_id="r1")
        unit = _plugin_unit()
        report = tmp_path / "r.xml"
        report.write_text("<testsuites/>", encoding="utf-8")

        retention.record(unit, report, "pass")
        published = retention.publish()

        assert published is not None
        manifest = json.loads((published / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["run_id"] == "r1"
        assert manifest["units"] == [{
            "unit_id": "shipwright-x",
            "base": "plugins/shipwright-x",
            "report_path": "reports/shipwright-x.xml",
            "outcome": "pass",
        }]
        assert (published / "reports" / "shipwright-x.xml").read_text(encoding="utf-8") == (
            "<testsuites/>"
        )

    def test_retry_report_supersedes_the_initial_one(self, tmp_path):
        project_root = _project_root(tmp_path)
        retention = mod.Retention(project_root=project_root, run_id="r1")
        unit = _plugin_unit()
        initial = tmp_path / "initial.xml"
        initial.write_text("<testsuites><initial/></testsuites>", encoding="utf-8")
        retry = tmp_path / "retry.xml"
        retry.write_text("<testsuites><retry/></testsuites>", encoding="utf-8")

        retention.record(unit, initial, "test_failure")
        retention.record(unit, retry, "pass")  # the authoritative serial retry
        published = retention.publish()

        manifest = json.loads((published / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["units"] == [{
            "unit_id": "shipwright-x",
            "base": "plugins/shipwright-x",
            "report_path": "reports/shipwright-x.xml",
            "outcome": "pass",
        }]
        assert "<retry/>" in (published / "reports" / "shipwright-x.xml").read_text(encoding="utf-8")

    def test_a_missing_report_is_recorded_with_null_report_path(self, tmp_path):
        project_root = _project_root(tmp_path)
        retention = mod.Retention(project_root=project_root, run_id="r1")
        unit = _plugin_unit()
        never_written = tmp_path / "never.xml"

        retention.record(unit, never_written, "infra")
        published = retention.publish()

        manifest = json.loads((published / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["units"] == [{
            "unit_id": "shipwright-x",
            "base": "plugins/shipwright-x",
            "report_path": None,
            "outcome": "infra",
        }]

    def test_publish_with_nothing_recorded_returns_none(self, tmp_path):
        project_root = _project_root(tmp_path)
        retention = mod.Retention(project_root=project_root, run_id="r1")
        assert retention.publish() is None

    def test_publish_is_atomic_nothing_under_published_until_the_end(self, tmp_path):
        project_root = _project_root(tmp_path)
        retention = mod.Retention(project_root=project_root, run_id="r1")
        unit = _plugin_unit()
        report = tmp_path / "r.xml"
        report.write_text("<testsuites/>", encoding="utf-8")
        retention.record(unit, report, "pass")

        published_root = mod.retention_root(project_root) / "published"
        assert not published_root.exists()  # nothing published yet — still pending

        retention.publish()
        assert published_root.is_dir()
        assert not retention._pending_dir.exists()  # renamed away, not copied


class TestPruning:
    def test_only_the_newest_retained_runs_count_survive(self, tmp_path):
        project_root = _project_root(tmp_path)
        for i in range(mod.RETAINED_RUNS + 3):
            retention = mod.Retention(project_root=project_root, run_id=f"r{i}")
            unit = _plugin_unit()
            report = tmp_path / f"r{i}.xml"
            report.write_text("<testsuites/>", encoding="utf-8")
            retention.record(unit, report, "pass")
            retention.publish()

        published_root = mod.retention_root(project_root) / "published"
        remaining = list(published_root.iterdir())
        assert len(remaining) == mod.RETAINED_RUNS
