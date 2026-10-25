"""Re-baseline, record-location and link-escape guards of the Brief package intake (B2 fix round)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
sys.path.append(str(Path(__file__).resolve().parent.parent / "scripts"))

from _brief_dir_helpers import build_package, bp, write_config  # noqa: E402
import brief_dir_intake as bdi  # noqa: E402


def _recorded(tmp_path, name="brief"):
    build_package(tmp_path, name=name)
    write_config(tmp_path)
    bdi.record(tmp_path, name)
    return tmp_path / bdi.CONFIG_NAME


def _edit_and_rehash(root: Path, name="brief"):
    """An edited package whose brief.json carries the NEW self-attested hash."""
    pkg = root / name
    (pkg / "brief.md").write_text("# Edited\n\n## Evil\nRequirement: x\n", encoding="utf-8")
    brief = json.loads((pkg / "brief.json").read_text())
    brief["package_sha256"] = bp.package_sha256(pkg)
    (pkg / "brief.json").write_text(json.dumps(brief), encoding="utf-8")


@pytest.mark.covers("FR-01.01")
def test_record_does_not_rebaseline_when_only_brief_dir_was_removed(tmp_path):
    cfg = _recorded(tmp_path)
    _edit_and_rehash(tmp_path)
    stored = json.loads(cfg.read_text())
    del stored["brief_dir"]  # brief_package (the old hash) stays
    cfg.write_text(json.dumps(stored))
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.record(tmp_path, "brief")
    assert exc.value.code == "hash_mismatch"
    assert json.loads(cfg.read_text())["brief_package"]["package_sha256"] == stored["brief_package"]["package_sha256"]


@pytest.mark.covers("FR-01.01")
def test_verify_refuses_a_kept_record_without_brief_dir(tmp_path):
    cfg = _recorded(tmp_path)
    stored = json.loads(cfg.read_text())
    del stored["brief_dir"]
    cfg.write_text(json.dumps(stored))
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.verify_run_config(tmp_path)
    assert exc.value.code == "missing_record"


@pytest.mark.covers("FR-01.01")
def test_a_package_at_a_non_default_dir_next_to_a_run_without_one_only_warns(tmp_path):
    cfg = _recorded(tmp_path, name="pkg")
    cfg.write_text(json.dumps({"schemaVersion": 2, "profile": "vite-hono"}))
    out = bdi.verify_run_config(tmp_path)
    assert out["package"] is False and "pkg/brief.json" in out["warnings"][0]


@pytest.mark.covers("FR-01.01")
def test_the_missing_record_message_never_recommends_record(tmp_path):
    cfg = _recorded(tmp_path)
    stored = json.loads(cfg.read_text())
    del stored["brief_dir"]
    cfg.write_text(json.dumps(stored))
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.verify_run_config(tmp_path)
    assert "record" not in exc.value.message.replace("run_config", "") .lower().replace("recorded", "")
    assert "restore" in exc.value.message and "restart" in exc.value.message


@pytest.mark.covers("FR-01.01")
def test_a_first_baseline_on_a_started_run_is_refused_even_with_a_rehashed_package(tmp_path):
    build_package(tmp_path)
    cfg = write_config(tmp_path)
    stored = json.loads(cfg.read_text())
    stored["phase_tasks"] = [{"phaseTaskId": "ptk-1", "phase": "project", "status": "in_progress"}]
    cfg.write_text(json.dumps(stored))
    _edit_and_rehash(tmp_path)
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.record(tmp_path, "brief")
    assert exc.value.code == "run_already_started"
    assert "brief_package" not in json.loads(cfg.read_text())


@pytest.mark.covers("FR-01.01")
def test_a_fresh_run_still_takes_its_first_baseline(tmp_path):
    build_package(tmp_path)
    cfg = write_config(tmp_path)
    stored = json.loads(cfg.read_text())
    stored["phase_tasks"] = [{"phaseTaskId": "ptk-1", "phase": "project", "status": "awaiting_launch"}]
    cfg.write_text(json.dumps(stored))
    assert bdi.record(tmp_path, "brief")["recorded"] is True


@pytest.mark.covers("FR-01.01")
def test_the_project_gate_goes_red_on_a_hash_mismatch(tmp_path):
    from tools.verifiers.brief_mode_checks import check_brief_package

    _recorded(tmp_path)
    assert check_brief_package(tmp_path)[0].ok is True
    (tmp_path / "brief" / "brief.md").write_text("# tampered", encoding="utf-8")
    [res] = check_brief_package(tmp_path)
    assert res.ok is False and "hash_mismatch" in res.detail
    assert check_brief_package(tmp_path / "nowhere") == []


@pytest.mark.covers("FR-01.01")
@pytest.mark.parametrize("raw", ["../outside", "/etc", "C:/Windows", "brief/../../x"])
def test_a_recorded_brief_dir_must_stay_inside_the_project(tmp_path, raw):
    cfg = _recorded(tmp_path)
    stored = json.loads(cfg.read_text())
    stored["brief_dir"] = raw
    cfg.write_text(json.dumps(stored))
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.verify_run_config(tmp_path)
    assert exc.value.code == "bad_brief_dir"


@pytest.mark.covers("FR-01.01")
def test_brief_json_must_name_the_recorded_directory(tmp_path):
    cfg = _recorded(tmp_path)
    stored = json.loads(cfg.read_text())
    shutil.copytree(tmp_path / "brief", tmp_path / "other")
    stored["brief_dir"] = "other"  # the copied brief.json still says "brief"
    cfg.write_text(json.dumps(stored))
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.verify_run_config(tmp_path)
    assert exc.value.code == "bad_brief_dir"


@pytest.mark.covers("FR-01.01")
def test_a_changed_approval_time_is_refused_on_resume(tmp_path):
    _recorded(tmp_path)
    brief = json.loads((tmp_path / "brief" / "brief.json").read_text())
    brief["approved_at"] = "2030-01-01T00:00:00Z"
    (tmp_path / "brief" / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.verify_run_config(tmp_path)
    assert exc.value.code == "approval_changed"


def _link(link: Path, target: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        if os.name != "nt":
            pytest.skip("symlinks are not permitted here")
        done = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        if done.returncode != 0:  # a junction needs no privilege
            pytest.skip("neither a symlink nor a junction could be created")


@pytest.mark.covers("FR-01.01")
def test_a_link_to_a_package_outside_the_project_is_refused(tmp_path):
    outside = tmp_path / "outside"
    project = tmp_path / "project"
    project.mkdir()
    build_package(outside, name="brief")
    _link(project / "brief", outside / "brief")
    write_config(project)
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.record(project, "brief")
    assert exc.value.code == "bad_brief_dir"


@pytest.mark.covers("FR-01.01")
def test_the_content_check_does_not_read_through_a_link_out_of_the_project(tmp_path):
    from tools.verifiers.brief_mode_checks import check_brief_evidence_anchors

    outside = tmp_path / "outside"
    project = tmp_path / "project"
    project.mkdir()
    build_package(outside, name="brief")
    _link(project / "brief", outside / "brief")
    (project / bdi.CONFIG_NAME).write_text(json.dumps({"brief_dir": "brief"}))
    [res] = check_brief_evidence_anchors(project)
    assert res.ok is False and "missing or unreadable" in res.detail


@pytest.mark.covers("FR-01.01")
def test_the_content_check_rejects_an_escaping_brief_dir(tmp_path):
    from tools.verifiers.brief_mode_checks import check_brief_evidence_anchors

    (tmp_path / bdi.CONFIG_NAME).write_text(json.dumps({"brief_dir": "../elsewhere"}))
    [res] = check_brief_evidence_anchors(tmp_path)
    assert res.ok is False and "project-relative" in res.detail


@pytest.mark.covers("FR-01.01")
def test_io_errors_on_the_package_route_are_a_structured_refusal(tmp_path, monkeypatch):
    build_package(tmp_path)

    def boom(*_a, **_k):
        raise OSError("disk gone")

    monkeypatch.setattr(bdi, "_intake_dir", boom)
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.intake_dir("brief", tmp_path)
    assert exc.value.code == "io_error"
