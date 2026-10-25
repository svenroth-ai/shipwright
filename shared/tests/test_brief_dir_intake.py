"""Brief intake from a package directory: read, override, persist, verify, refuse
(campaign brief-driven-run, B2; BRIEF D1-D2)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))

from _brief_dir_helpers import build_package, write_config  # noqa: E402
import brief_dir_intake as bdi  # noqa: E402
import brief_intake  # noqa: E402

LIB = Path(brief_intake.__file__).resolve()
NO_ENV: dict[str, str] = {}
FIXTURE_ENV = {bdi.FIXTURE_ENV: "1"}


@pytest.mark.covers("FR-01.01")
def test_directory_package_is_read_and_brief_fields_override_derived_values(tmp_path):
    build_package(tmp_path, profile="supabase-nextjs", deploy_target="jelastic-dev", autonomy="autonomous")
    out = brief_intake.intake("brief", str(tmp_path), package=True)
    assert out["has_brief"] and out["source"] == "package" and out["brief_dir"] == "brief"
    assert (out["profile"], out["deploy_target"], out["autonomy"]) == ("supabase-nextjs", "jelastic-dev", "autonomous")
    assert "A tiny notes app" in out["brief"]["description"]
    assert out["remaining_questions"] == [] and "autonomy" in out["answered"]


@pytest.mark.covers("FR-01.01")
def test_trailing_slash_and_absolute_path_name_the_same_package(tmp_path):
    build_package(tmp_path)
    assert brief_intake.intake("brief/", str(tmp_path), package=True)["brief_dir"] == "brief"
    assert brief_intake.intake(str(tmp_path / "brief"), str(tmp_path), package=True)["brief_dir"] == "brief"


@pytest.mark.covers("FR-01.01")
def test_file_and_payload_routes_keep_their_behaviour(tmp_path):
    f = tmp_path / "wizard.json"
    f.write_text(json.dumps({"description": "x", "persistence": "yes", "run_location": "web"}))
    assert brief_intake.intake(str(f))["profile"] == "supabase-nextjs"
    assert brief_intake.intake('{"description": "a", "persistence": "no"}')["profile"] == "vite-hono"
    assert brief_intake.intake(None)["has_brief"] is False
    assert brief_intake.intake("a plain sentence about an app")["brief"]["description"].startswith("a plain")


@pytest.mark.covers("FR-01.01")
def test_bad_brief_dir_fails_loudly(tmp_path):
    with pytest.raises(Exception) as exc:  # brief_intake loads its own copy of the sibling module
        brief_intake.intake("nowhere/", str(tmp_path), package=True)
    assert type(exc.value).__name__ == "BriefRefused" and exc.value.code == "bad_brief_dir"
    out = subprocess.run([sys.executable, str(LIB), "--brief", "nowhere/", "--project-root", str(tmp_path)],
                         capture_output=True, text=True)
    assert out.returncode == 3 and json.loads(out.stdout)["code"] == "bad_brief_dir"


@pytest.mark.covers("FR-01.01")
def test_package_outside_the_project_and_wrong_declared_dir_are_refused(tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    build_package(other)
    project = tmp_path / "proj"
    project.mkdir()
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.intake_dir(str(other / "brief"), project)
    assert exc.value.code == "bad_brief_dir"
    build_package(project, name="brief", brief_dir="somewhere-else")
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.intake_dir("brief", project)
    assert exc.value.code == "bad_brief_dir"


@pytest.mark.covers("FR-01.01")
def test_brief_dir_is_persisted_and_survives_a_resume(tmp_path):
    build_package(tmp_path)
    cfg = write_config(tmp_path)
    rec = bdi.record(tmp_path, "brief")
    stored = json.loads(cfg.read_text(encoding="utf-8"))
    assert stored["brief_dir"] == "brief" and stored["brief_package"]["package_sha256"] == rec["package_sha256"]
    assert stored["profile"] == "vite-hono"  # the rest of the config is untouched
    assert bdi.verify_run_config(tmp_path)["verified"] is True
    assert bdi.verify_run_config(tmp_path / "no-config-here") == {"package": False}


@pytest.mark.covers("FR-01.01")
def test_a_second_record_never_rebaselines_an_edited_package(tmp_path):
    pkg = build_package(tmp_path)
    write_config(tmp_path)
    first = bdi.record(tmp_path, "brief")
    brief = json.loads((pkg / "brief.json").read_text())
    (pkg / "scope.md").write_text("# Scope\n\nIn: more.\n", encoding="utf-8")
    brief["package_sha256"] = bdi._lib("brief_package").package_sha256(pkg)  # edited yet internally valid
    (pkg / "brief.json").write_text(json.dumps(brief))
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.record(tmp_path, "brief")
    assert exc.value.code == "hash_mismatch"
    stored = json.loads((tmp_path / bdi.CONFIG_NAME).read_text())
    assert stored["brief_package"]["package_sha256"] == first["package_sha256"]


@pytest.mark.covers("FR-01.01")
def test_record_needs_a_run_config_first(tmp_path):
    build_package(tmp_path)
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.record(tmp_path, "brief")
    assert exc.value.code == "no_run_config"


@pytest.mark.covers("FR-01.01")
def test_hash_mismatch_is_refused_at_intake_and_on_every_resume(tmp_path):
    pkg = build_package(tmp_path)
    write_config(tmp_path)
    bdi.record(tmp_path, "brief")
    (pkg / "scope.md").write_text("# Scope\n\nIn: everything.\n", encoding="utf-8")
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.verify_run_config(tmp_path)
    assert exc.value.code == "hash_mismatch"
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.intake_dir("brief", tmp_path)
    assert exc.value.code == "hash_mismatch"


@pytest.mark.covers("FR-01.01")
def test_rewriting_brief_json_and_its_hash_does_not_pass_a_resume(tmp_path):
    pkg = build_package(tmp_path)
    write_config(tmp_path)
    bdi.record(tmp_path, "brief")
    forged = json.loads((pkg / "brief.json").read_text())
    forged["autonomy"] = "autonomous"
    (pkg / "brief.json").write_text(json.dumps(forged))
    forged["package_sha256"] = bdi._lib("brief_package").package_sha256(pkg)
    (pkg / "brief.json").write_text(json.dumps(forged))
    with pytest.raises(bdi.BriefRefused) as exc:  # the recorded hash is held outside the package
        bdi.verify_run_config(tmp_path)
    assert exc.value.code == "hash_mismatch"


@pytest.mark.covers("FR-01.01")
def test_a_changed_approver_invalidates_the_recorded_approval(tmp_path):
    pkg = build_package(tmp_path)
    write_config(tmp_path)
    bdi.record(tmp_path, "brief")
    data = json.loads((pkg / "brief.json").read_text())
    data["approved_by"] = "human:someone-else"  # outside the hash by design
    (pkg / "brief.json").write_text(json.dumps(data))
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.verify_run_config(tmp_path)
    assert exc.value.code == "approval_changed"


@pytest.mark.covers("FR-01.01")
def test_missing_approval_is_refused(tmp_path):
    build_package(tmp_path, approved_by=None)
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.intake_dir("brief", tmp_path)
    assert exc.value.code == "missing_approval"


@pytest.mark.covers("FR-01.01")
def test_fixture_approval_needs_the_operator_switch_and_is_recorded(tmp_path):
    build_package(tmp_path, approved_by="fixture:synthetic-1")
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.intake_dir("brief", tmp_path, env=NO_ENV)
    assert exc.value.code == "fixture_approval_refused"
    out = bdi.intake_dir("brief", tmp_path, env=FIXTURE_ENV)
    assert out["package"]["fixture_approval_accepted"] is True
    write_config(tmp_path)
    assert bdi.record(tmp_path, "brief", env=FIXTURE_ENV)["fixture_approval_accepted"] is True
    stored = json.loads((tmp_path / bdi.CONFIG_NAME).read_text())
    assert stored["brief_package"]["fixture_approval_accepted"] is True
    with pytest.raises(bdi.BriefRefused):  # a resume without the switch is refused again
        bdi.verify_run_config(tmp_path, env=NO_ENV)


@pytest.mark.covers("FR-01.01")
def test_an_empty_fixture_id_is_not_an_approval(tmp_path):
    build_package(tmp_path, approved_by="fixture:")
    with pytest.raises(bdi.BriefRefused) as exc:
        bdi.intake_dir("brief", tmp_path, env=FIXTURE_ENV)
    assert exc.value.code == "missing_approval"


@pytest.mark.covers("FR-01.01")
def test_cli_verify_and_record_exit_codes(tmp_path):
    pkg = build_package(tmp_path)
    write_config(tmp_path)
    script = str(Path(bdi.__file__))
    run = lambda *a: subprocess.run([sys.executable, script, *a, "--project-root", str(tmp_path)],  # noqa: E731
                                    capture_output=True, text=True)
    assert run("record", "--brief-dir", "brief").returncode == 0
    assert run("verify").returncode == 0
    (pkg / "scope.md").write_text("changed\n", encoding="utf-8")
    bad = run("verify")
    assert bad.returncode == 3 and json.loads(bad.stdout)["code"] == "hash_mismatch"
