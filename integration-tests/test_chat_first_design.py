"""B3b acceptance: the chat-first fixture package (social engagement desk) passes A1's dry harness, and
Design takes it in a REAL git repo (so the boundary gate reads real git state): mockups byte-identical in
uploads/, every chat-only capability on a pane-state screen with its minted FR, one flow mockup per golden
path, and every design gate (boundary included) plus the design verifier checks green."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import _brief_harness as h

_REPO = Path(__file__).resolve().parents[1]
_CHECKS = _REPO / "plugins" / "shipwright-design" / "scripts" / "checks"
FIXTURE = _REPO / "integration-tests" / "fixtures" / "social-engagement"
NAMES = ("Fetch new matches", "View the board", "Show a thread", "Draft a reply",
         "Mark a thread as posted", "Set keywords")
SPEC = ("| ID | Area | Name | Priority | Requirement |\n|---|---|---|---|---|\n"
        + "".join(f"| FR-01.{i:02d} | Desk | {n} | Must | The system SHALL {n.lower()} |\n" for i, n in enumerate(NAMES, 1)))


def _bdi():
    spec = importlib.util.spec_from_file_location("_it_b3b_bdi", _REPO / "shared" / "scripts" / "lib" / "brief_dir_intake.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(script: str, project: Path, *extra: str):
    env = {**os.environ, "SHIPWRIGHT_ACCEPT_FIXTURE_APPROVAL": "1"}
    proc = subprocess.run([sys.executable, str(_CHECKS / script), "--project-root", str(project), *extra],
                          capture_output=True, text=True, encoding="utf-8", env=env)
    return proc.returncode, json.loads(proc.stdout)


def _git(project: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(project), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                   check=True, capture_output=True)


@pytest.mark.covers("FR-01.04")
def test_fixture_passes_the_dry_harness(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_ACCEPT_FIXTURE_APPROVAL", "1")
    project = h.prepare_scratch_project(tmp_path / "proj", FIXTURE)
    report = h.run_harness(project, fixture="social-engagement", report_path=tmp_path / "report.json")
    assert report["outcome"] == "dry-ok", report
    assert report["autonomy"] == "guided"
    assert report["fixture_approval"] == {"approved_by": "fixture:social-engagement", "accepted_via_env": True}


@pytest.mark.covers("FR-01.04")
def test_design_takes_the_chat_first_fixture_and_every_gate_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_ACCEPT_FIXTURE_APPROVAL", "1")
    project = h.prepare_scratch_project(tmp_path / "proj", FIXTURE)
    (project / "shipwright_run_config.json").write_text(json.dumps({"profile": "chat-first-json"}), encoding="utf-8")
    _bdi().record(project, "brief")
    spec_dir = project / ".shipwright" / "planning" / "01-desk"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(SPEC, encoding="utf-8")
    _git(project, "init", "-q")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "baseline")

    code, out = _run("apply-brief-package.py", project)
    assert code == 0 and out["ok"], out
    assert (out["ux_shape"], out["ui_host"]) == ("chat-first", "served-pane")
    assert out["flows"] == ["flows/01-triage-a-thread.html", "flows/02-tune-the-keywords.html"]
    assert out["unmapped_frs"] == []

    designs = project / ".shipwright" / "designs"
    for mock in sorted((FIXTURE / "mockups").glob("*.html")):
        assert (designs / "uploads" / mock.name).read_bytes() == mock.read_bytes()
    fetch = (designs / "screens" / "01-board-new.html").read_text(encoding="utf-8")
    assert "<!-- Requirements: FR-01.01, FR-01.02 -->" in fetch
    assert "nav-item" not in fetch and "topnav-link" not in fetch
    flow = (designs / "flows" / "01-triage-a-thread.html").read_text(encoding="utf-8")
    assert "draft a reply for thread 1" in flow and "thread-posted" in flow

    code, gates = _run("check-design-gates.py", project, "--gate", "all")
    assert code == 0, [g for g in gates["gates"] if not g["ok"]]
    assert [g["gate"] for g in gates["gates"]] == [
        "fr-coverage", "tokens", "flows", "chrome", "standalone", "uploads", "iteration", "boundary"]

    sys.path.insert(0, str(_REPO / "shared" / "scripts"))
    try:
        from tools.verifiers.brief_chat_checks import check_brief_chat_first_applied
        from tools.verifiers.brief_design_checks import check_brief_design_applied
        results = check_brief_design_applied(project) + check_brief_chat_first_applied(project)
    finally:
        sys.path.remove(str(_REPO / "shared" / "scripts"))
    assert [(r.name, r.ok) for r in results] == [("brief_design_applied", True), ("brief_chat_first_applied", True)], results
