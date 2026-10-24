"""Brief-driven run harness, dry mode (campaign brief-driven-run, A1)."""

from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path

import pytest

import _brief_harness as h

PINNED_FIXTURE_1_SHA256 = "0a5a534ac2d264dcb780a5a91ab79255bda620d5db3779c85e8c1b1a0e87a87e"


def test_fixture_1_is_accepted_by_the_library(tmp_path):
    from lib import brief_package
    pkg = h.build_fixture_1(tmp_path / "pkg")
    assert brief_package.validate_layout(pkg) == []
    assert brief_package.verify_hash(pkg) == (True, "")


def test_fixture_hash_is_line_ending_independent(tmp_path):
    from lib import brief_package
    a = h.build_fixture_1(tmp_path / "lf")
    b = h.build_fixture_1(tmp_path / "crlf", crlf=True)
    assert brief_package.package_sha256(a) == brief_package.package_sha256(b)
    assert brief_package.verify_hash(b) == (True, "")


def test_fixture_1_is_classic_bundled_with_no_deploy(tmp_path):
    brief = json.loads((h.build_fixture_1(tmp_path / "p") / "brief.json").read_text())
    assert (brief["profile"], brief["deploy_target"], brief["ux_shape"]) == ("vite-hono", "none", "classic")
    assert brief["approved_by"].startswith("fixture:")
    assert brief["env_preflight"] == []


def test_dry_run_passes_makes_no_model_call_and_no_subprocess(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("dry mode must not start a process")
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)  # an SDK/HTTP model call needs a socket
    monkeypatch.setattr(socket, "create_connection", boom)
    project = h.prepare_scratch_project(tmp_path / "proj", h.build_fixture_1(tmp_path / "pkg"))
    report = h.run_harness(project, report_path=tmp_path / "out" / "report.json")
    assert report["outcome"] == "dry-ok" and report["spend"]["model_calls"] == 0
    assert report["stop_point"] is None
    on_disk = json.loads((tmp_path / "out" / "report.json").read_text())
    assert on_disk == report and h.validate_report(on_disk) == []


def test_dry_run_reports_a_planted_defect(tmp_path):
    project = h.prepare_scratch_project(tmp_path / "proj", h.build_fixture_1(tmp_path / "pkg"))
    (project / "brief" / "scope.md").unlink()
    report = h.run_harness(project)
    assert report["outcome"] == "dry-failed"
    assert report["package"]["valid"] is False
    assert any(i["code"] == "missing_file" for i in report["package"]["issues"])


def test_dry_run_reports_a_tampered_consent_field(tmp_path):
    project = h.prepare_scratch_project(tmp_path / "proj", h.build_fixture_1(tmp_path / "pkg"))
    f = project / "brief" / "brief.json"
    data = json.loads(f.read_text())
    data["allow_parallel_builders"] = True
    f.write_text(json.dumps(data))
    report = h.run_harness(project)
    assert report["outcome"] == "dry-failed"
    assert [s["name"] for s in report["stages"] if s["status"] == "failed"] == ["hash"]


def test_live_mode_is_refused(tmp_path):
    with pytest.raises(NotImplementedError):
        h.run_harness(tmp_path, mode="live")


def test_report_schema_is_pinned():
    assert h.REPORT_SCHEMA_VERSION == 1
    assert h.REPORT_KEYS == (
        "schema_version", "mode", "fixture", "autonomy", "started_at", "finished_at",
        "package", "fixture_approval", "stages", "gates_auto_approved", "escalations", "spend",
        "outcome", "stop_point",
    )
    assert h.APPROVAL_KEYS == ("approved_by", "accepted_via_env")
    assert (h.PACKAGE_KEYS, h.SPEND_KEYS, h.STAGE_KEYS) == (
        ("sha256", "valid", "issues"), ("model_calls", "usd"), ("name", "status", "detail"))
    assert h.OUTCOMES == ("dry-ok", "dry-failed", "complete", "escalated", "failed")


def test_report_validation_rejects_drift(tmp_path):
    project = h.prepare_scratch_project(tmp_path / "proj", h.build_fixture_1(tmp_path / "pkg"))
    good = h.run_harness(project)
    assert h.validate_report(good) == []
    for mutate in (
        lambda r: r.pop("spend"),
        lambda r: r.update(extra=1),
        lambda r: r.update(outcome="great"),
        lambda r: r.update(stop_point="step 3"),  # a dry run never records one
        lambda r: r.update(stop_point=3),
        lambda r: r["fixture_approval"].update(accepted_via_env="yes"),
        lambda r: r["package"].update(valid="yes"),
        lambda r: r["package"].update(issues=None),
        lambda r: r["spend"].update(usd="unknown"),
        lambda r: r["stages"][0].update(detail=[]),
        lambda r: r.update(started_at=5),
        lambda r: r["spend"].update(model_calls="0"),
        lambda r: r["stages"].append({"name": "x"}),
    ):
        bad = json.loads(json.dumps(good))
        mutate(bad)
        assert h.validate_report(bad), bad
        with pytest.raises(ValueError):
            h.write_report(bad, tmp_path / "nope.json")
    assert not (tmp_path / "nope.json").exists()


def test_cli_dry_mode_writes_a_conforming_report(tmp_path):
    assert h.main(["--report", str(tmp_path / "r.json")]) == 0
    assert h.validate_report(json.loads((tmp_path / "r.json").read_text())) == []
    assert h.main(["--mode", "live", "--report", str(tmp_path / "r2.json")]) == 2


def test_fixture_1_hash_is_pinned_so_drift_is_a_visible_change(tmp_path):
    from lib import brief_package
    sha = brief_package.package_sha256(h.build_fixture_1(tmp_path / "pkg"))
    assert sha == PINNED_FIXTURE_1_SHA256


def test_scratch_project_never_follows_symlinks(tmp_path, monkeypatch):
    pkg = h.build_fixture_1(tmp_path / "pkg")
    (pkg / "leak.md").write_text("secret")
    real = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == "leak.md" or real(self))
    project = h.prepare_scratch_project(tmp_path / "proj", pkg)
    assert not (project / "brief" / "leak.md").exists()


def test_a_live_report_may_carry_the_operators_stop_point(tmp_path):
    project = h.prepare_scratch_project(tmp_path / "proj", h.build_fixture_1(tmp_path / "pkg"))
    report = h.run_harness(project)
    live = {**report, "mode": "live", "outcome": "escalated", "stop_point": "design.preview-approval"}
    assert h.validate_report(live) == []


def test_fixture_approval_acceptance_is_recorded(tmp_path, monkeypatch):
    project = h.prepare_scratch_project(tmp_path / "proj", h.build_fixture_1(tmp_path / "pkg"))
    monkeypatch.delenv(h.FIXTURE_APPROVAL_ENV, raising=False)
    off = h.run_harness(project)["fixture_approval"]
    monkeypatch.setenv(h.FIXTURE_APPROVAL_ENV, "1")
    on = h.run_harness(project)["fixture_approval"]
    assert off == {"approved_by": "fixture:synthetic-1", "accepted_via_env": False}
    assert on == {"approved_by": "fixture:synthetic-1", "accepted_via_env": True}


def test_scratch_project_refuses_a_dirty_target(tmp_path):
    pkg = h.build_fixture_1(tmp_path / "pkg")
    project = h.prepare_scratch_project(tmp_path / "proj", pkg)
    with pytest.raises(FileExistsError):
        h.prepare_scratch_project(project, pkg)


def test_an_unreadable_packaged_file_gives_a_failure_report_not_a_crash(tmp_path, monkeypatch):
    project = h.prepare_scratch_project(tmp_path / "proj", h.build_fixture_1(tmp_path / "pkg"))
    real = Path.read_bytes

    def deny(self):
        if self.name == "01-notes.html":
            raise PermissionError("denied")
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", deny)
    report = h.run_harness(project, report_path=tmp_path / "r.json")
    assert report["outcome"] == "dry-failed"
    assert any(i["code"] == "unreadable_file" for i in report["package"]["issues"])
