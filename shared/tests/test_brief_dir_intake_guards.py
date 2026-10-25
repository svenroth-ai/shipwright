"""Regression guards from the B2 plan review: routing never touches free text, resume never fails
open, run_config can not drift from the approved brief (campaign brief-driven-run, B2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))

from _brief_dir_helpers import build_package, write_config  # noqa: E402
import brief_dir_intake as bdi  # noqa: E402
import brief_intake  # noqa: E402


@pytest.mark.covers("FR-01.01")
def test_long_free_text_and_trailing_slash_text_stay_descriptions(tmp_path):
    long = "A booking tool for my yoga studio " * 20  # > 255 bytes, no slash
    assert brief_intake.intake(long, str(tmp_path), package=True)["brief"]["description"].startswith("A booking")
    url = "see https://example.com/"
    assert brief_intake.intake(url, str(tmp_path), package=True)["has_brief"] is True
    assert "source" not in brief_intake.intake(url, str(tmp_path), package=True)


@pytest.mark.covers("FR-01.01")
def test_a_directory_name_is_a_description_unless_the_caller_opts_in(tmp_path):
    (tmp_path / "docs").mkdir()
    assert brief_intake.intake("docs", str(tmp_path))["brief"]["description"] == "docs"  # adopt's default
    with pytest.raises(Exception) as exc:
        brief_intake.intake("docs", str(tmp_path), package=True)
    assert type(exc.value).__name__ == "BriefRefused" and exc.value.code == "invalid_package"


@pytest.mark.covers("FR-01.01")
def test_a_recorded_brief_dir_without_a_record_is_refused(tmp_path):
    build_package(tmp_path)
    cfg = write_config(tmp_path)
    stored = json.loads(cfg.read_text())
    stored["brief_dir"] = "brief"  # the record block was dropped
    cfg.write_text(json.dumps(stored))
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.verify_run_config(tmp_path)
    assert exc.value.code == "missing_record"
    stored["brief_package"] = {"package_sha256": "not-a-hash", "approved_by": "human:sven"}
    cfg.write_text(json.dumps(stored))
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.verify_run_config(tmp_path)
    assert exc.value.code == "missing_record"


@pytest.mark.covers("FR-01.01")
def test_run_config_cannot_drift_from_the_approved_brief(tmp_path):
    build_package(tmp_path, autonomy="guided")
    cfg = write_config(tmp_path)
    stored = json.loads(cfg.read_text())
    stored["autonomy"] = "autonomous"
    cfg.write_text(json.dumps(stored))
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.record(tmp_path, "brief")
    assert exc.value.code == "config_mismatch"
    stored["autonomy"] = "guided"
    cfg.write_text(json.dumps(stored))
    bdi.record(tmp_path, "brief")
    stored = json.loads(cfg.read_text())
    stored["profile"] = "supabase-nextjs"
    cfg.write_text(json.dumps(stored))
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.verify_run_config(tmp_path)
    assert exc.value.code == "config_mismatch"


@pytest.mark.covers("FR-01.01")
def test_a_different_directory_never_replaces_a_recorded_package(tmp_path):
    build_package(tmp_path)
    build_package(tmp_path, name="other", brief_dir="other")
    write_config(tmp_path)
    bdi.record(tmp_path, "brief")
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.record(tmp_path, "other")
    assert exc.value.code == "brief_dir_conflict"
    assert json.loads((tmp_path / bdi.CONFIG_NAME).read_text())["brief_dir"] == "brief"


@pytest.mark.covers("FR-01.01")
def test_a_directory_with_spaces_in_its_name_still_routes_to_the_package(tmp_path):
    build_package(tmp_path, name="my brief", brief_dir="my brief")
    assert brief_intake.intake("my brief", str(tmp_path), package=True)["brief_dir"] == "my brief"
    assert brief_intake.intake("my brief", str(tmp_path))["has_brief"] is True  # opt-in: adopt's default unchanged


@pytest.mark.covers("FR-01.01")
def test_cli_verify_refuses_a_missing_run_config(tmp_path):
    import subprocess
    out = subprocess.run([sys.executable, str(Path(bdi.__file__)), "verify", "--project-root", str(tmp_path)],
                         capture_output=True, text=True)
    assert out.returncode == 3 and json.loads(out.stdout)["code"] == "no_run_config"


@pytest.mark.covers("FR-01.01")
def test_record_refuses_when_the_stored_record_block_was_dropped(tmp_path):
    build_package(tmp_path)
    cfg = write_config(tmp_path)
    stored = json.loads(cfg.read_text())
    stored["brief_dir"] = "brief"  # brief_package missing: the baseline is gone
    cfg.write_text(json.dumps(stored))
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.record(tmp_path, "brief")
    assert exc.value.code == "missing_record"


@pytest.mark.covers("FR-01.01")
def test_fixture_prefix_is_matched_case_and_space_insensitively(monkeypatch):
    monkeypatch.delenv(bdi.FIXTURE_ENV, raising=False)
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.check_approval({"approved_by": " Fixture:demo", "approved_at": "2026-10-25"}, {})
    assert exc.value.code == "fixture_approval_refused"


@pytest.mark.covers("FR-01.01")
def test_a_package_next_to_a_run_without_one_is_a_warning_not_a_refusal(tmp_path):
    build_package(tmp_path)
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    out = bdi.verify_run_config(tmp_path)
    assert out["package"] is False and "brief/brief.json" in out["warnings"][0]
