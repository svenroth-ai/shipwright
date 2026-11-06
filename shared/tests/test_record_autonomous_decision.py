"""tools/record_autonomous_decision.py in-process: each e2e-run-22 rule records instead of asking."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))
from _brief_dir_helpers import bp, build_package  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.05/AC05")

_TOOL = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "record_autonomous_decision.py"
_spec = importlib.util.spec_from_file_location("_record_autonomous_decision", _TOOL)
rad = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rad)

UPLOAD = '<html><body><a href="https://www.reddit.com/r/x/comments/1">Open thread</a></body></html>'


def _project(root: Path, **cfg) -> Path:
    cfg = cfg or {"autonomy": "guided", "brief_package": {"sha": "x"}, "brief_dir": "brief",
                  "profile": "skill-companion-app"}
    (root / "shipwright_run_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    (root / "brief").mkdir(exist_ok=True)
    (root / "brief" / "brief.md").write_text("The cap is shown: posted today <n>/5.\n", encoding="utf-8")
    return root


def _verified_package(root: Path) -> Path:
    """An approved package whose own mockup carries the link; run_config records its hash."""
    bdir = build_package(root)
    (bdir / "mockups" / "02-board.html").write_text(UPLOAD, encoding="utf-8")
    cfg = {"autonomy": "autonomous", "brief_dir": "brief", "brief_package": {"package_sha256": bp.package_sha256(bdir)}}
    (root / "shipwright_run_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    designs = root / ".shipwright" / "designs"
    for d in ("screens", "uploads"):
        (designs / d).mkdir(parents=True, exist_ok=True)
    (designs / "brief-package-applied.json").write_text("{}", encoding="utf-8")
    return bdir


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@example.com", "-c", "user.name=t",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)


def _repo_with_build_baseline(root: Path, monkeypatch) -> Path:
    """A committed project whose Build section 01-a recorded its phase-start baseline."""
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "run-a")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    assert rad.pbb.record(root, rad.pbb.BUILD_BASELINE_REL, "01-a") == "written"
    return root


def _run(root: Path, *args: str, capsys=None) -> tuple[dict, int]:
    code = rad.main(["--project-root", str(root), *args])
    return json.loads(capsys.readouterr().out), code


def _log(root: Path) -> str:
    return (root / ".shipwright" / "agent_docs" / "decision_log.md").read_text(encoding="utf-8")


def test_an_interactive_run_records_nothing_and_asks(tmp_path, capsys):
    _project(tmp_path, autonomy="guided")
    out, code = _run(tmp_path, "--kind", "dev-tooling", "--command", "npm install", capsys=capsys)
    assert (code, out["action"], out["autonomous"]) == (1, "ask", False)
    assert not (tmp_path / ".shipwright").exists()


def test_approved_links_are_logged_once(tmp_path, capsys):
    _verified_package(tmp_path)
    designs = tmp_path / ".shipwright" / "designs"
    assert _run(tmp_path, "--kind", "approved-links", capsys=capsys)[0]["action"] == "nothing"
    (designs / "screens" / "01-board.html").write_text(UPLOAD, encoding="utf-8")
    out, code = _run(tmp_path, "--kind", "approved-links", "--phase", "Design", capsys=capsys)
    assert (code, out["action"]) == (0, "recorded") and out["adr"].startswith("ADR-")
    assert out["kept"] == ["screens/01-board.html: approved package link https://www.reddit.com/r/x/comments/1"]
    assert rad.LINKS_TITLE in _log(tmp_path)
    assert _run(tmp_path, "--kind", "approved-links", capsys=capsys)[0]["action"] == "already_recorded"


def test_approved_links_from_a_changed_package_are_a_question(tmp_path, capsys):
    bdir = _verified_package(tmp_path)
    (tmp_path / ".shipwright" / "designs" / "screens" / "01-board.html").write_text(UPLOAD, encoding="utf-8")
    (bdir / "mockups" / "02-board.html").write_text(UPLOAD + "<p>edited after approval</p>", encoding="utf-8")
    out, code = _run(tmp_path, "--kind", "approved-links", capsys=capsys)
    assert (code, out["action"]) == (1, "ask") and "hash_mismatch" in out["why"]
    assert out["problems"] == ["screens/01-board.html: external reference https://www.reddit.com/r/x/comments/1"]


def test_brief_wins_needs_a_real_brief_quote_and_writes_a_known_difference(tmp_path, capsys):
    _project(tmp_path)
    out, code = _run(tmp_path, "--kind", "brief-wins", "--what", "the day's count", "--brief-quote",
                     "the cap is hidden: posted today", capsys=capsys)
    assert (code, out["action"]) == (1, "ask")
    out, code = _run(tmp_path, "--kind", "brief-wins", "--what", "the day's count", "--brief-quote",
                     "the cap is shown: posted today", "--fr", "FR-01.03", "--screens", "screens 01-06", capsys=capsys)
    assert (code, out["action"], out["kd"]) == (0, "recorded", "KD-01")
    kd = (tmp_path / ".shipwright" / "designs" / "known-differences.md").read_text(encoding="utf-8")
    assert "FR-01.03" in kd and "Build adds it from the brief" in kd
    assert "Brief wins" in _log(tmp_path)
    again, code = _run(tmp_path, "--kind", "brief-wins", "--what", "the day's count", "--brief-quote",
                       "the cap is shown: posted today", capsys=capsys)
    assert (code, again["action"]) == (0, "already_recorded")
    assert _run(tmp_path, "--kind", "brief-wins", capsys=capsys)[1] == 2


def test_hard_constraint_needs_measurements(tmp_path, capsys):
    _project(tmp_path)
    base = ["--kind", "hard-constraint", "--what", "header band", "--keep", "controls add no height",
            "--yields", "mode and count shown at 945-1069px"]
    assert _run(tmp_path, *base, "--measurements", "about the middle", capsys=capsys)[0]["action"] == "ask"
    out, code = _run(tmp_path, *base, "--measurements", "955-985px neither, 1025px count", capsys=capsys)
    assert (code, out["kd"]) == (0, "KD-01")
    assert _run(tmp_path, *base, "--measurements", "955px", capsys=capsys)[0]["action"] == "already_recorded"
    assert _run(tmp_path, "--kind", "hard-constraint", capsys=capsys)[1] == 2


DEV = ["--kind", "dev-tooling", "--phase", "Build", "--scope", "01-a"]


def test_dev_tooling_installs_only_what_is_declared(tmp_path, capsys, monkeypatch):
    _project(tmp_path)
    (tmp_path / "package.json").write_text('{"devDependencies": {"vitest": "1"}}', encoding="utf-8")
    _repo_with_build_baseline(tmp_path, monkeypatch)
    # Playwright comes from the stack profile (skill-companion-app's e2e framework)
    out, code = _run(tmp_path, *DEV, "--command", "npm install --ignore-scripts",
                     "--command", "npx playwright install chromium", capsys=capsys)
    assert (code, out["action"]) == (0, "recorded"), out
    assert "Declared dev tooling installed" in _log(tmp_path) and "--ignore-scripts" in _log(tmp_path)
    out, code = _run(tmp_path, *DEV, "--command", "npm install --ignore-scripts left-pad", capsys=capsys)
    assert (code, out["action"]) == (1, "ask") and out["verdicts"][0]["allowed"] is False
    out, code = _run(tmp_path, *DEV, "--command", "npm install", capsys=capsys)
    assert (code, out["action"]) == (1, "ask") and "--ignore-scripts" in out["verdicts"][0]["why"]
    assert _run(tmp_path, "--kind", "dev-tooling", capsys=capsys)[1] == 2


def test_a_manifest_edited_in_the_phase_cannot_authorise_its_install(tmp_path, capsys, monkeypatch):
    _project(tmp_path)
    (tmp_path / "package.json").write_text('{"devDependencies": {"vitest": "1"}}', encoding="utf-8")
    _repo_with_build_baseline(tmp_path, monkeypatch)
    (tmp_path / "package.json").write_text('{"devDependencies": {"vitest": "1", "evil": "1"}}', encoding="utf-8")
    out, code = _run(tmp_path, *DEV, "--command", "npm install --ignore-scripts evil", capsys=capsys)
    assert (code, out["action"]) == (1, "ask") and "changed since the phase started: package.json" in out["why"]


@pytest.mark.parametrize("extra", [["--scope", "02-b"], ["--phase", "Test"], []])
def test_no_phase_start_baseline_is_a_question(tmp_path, capsys, monkeypatch, extra):
    _project(tmp_path)
    (tmp_path / "package.json").write_text('{"devDependencies": {"vitest": "1"}}', encoding="utf-8")
    _repo_with_build_baseline(tmp_path, monkeypatch)
    args = ["--kind", "dev-tooling", "--phase", "Build", *extra, "--command", "npm ci --ignore-scripts"]
    out, code = _run(tmp_path, *args, capsys=capsys)
    assert (code, out["action"]) == (1, "ask") and "no phase-start baseline" in out["why"]


def test_an_unknown_profile_fails_loud_instead_of_narrowing_silently(tmp_path, capsys):
    _project(tmp_path, brief_package={"a": 1}, profile="no-such-profile")
    out, code = _run(tmp_path, "--kind", "dev-tooling", "--command", "npx playwright install chromium", capsys=capsys)
    assert code == 2 and "stack profile cannot be resolved" in out["error"]


def test_no_readable_run_config_means_no_profile(tmp_path):
    assert rad._profile(tmp_path) is None
    (tmp_path / "shipwright_run_config.json").write_text("{not json", encoding="utf-8")
    assert rad._profile(tmp_path) is None
    (tmp_path / "shipwright_run_config.json").write_text('{"profile": 7}', encoding="utf-8")
    assert rad._profile(tmp_path) is None


def test_a_failed_log_write_is_exit_2(tmp_path, capsys, monkeypatch):
    _project(tmp_path)
    monkeypatch.setattr(rad, "_log", lambda *a, **k: None)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    _repo_with_build_baseline(tmp_path, monkeypatch)
    assert _run(tmp_path, *DEV, "--command", "uv sync", capsys=capsys)[1] == 2
    assert _run(tmp_path, "--kind", "brief-wins", "--what", "x", "--brief-quote", "the cap is shown: posted today",
                capsys=capsys)[1] == 2
    assert _run(tmp_path, "--kind", "hard-constraint", "--what", "x", "--keep", "a", "--yields", "b",
                "--measurements", "900px", capsys=capsys)[1] == 2
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    _verified_package(pkg)
    (pkg / ".shipwright" / "designs" / "screens" / "a.html").write_text(UPLOAD, encoding="utf-8")
    assert _run(pkg, "--kind", "approved-links", capsys=capsys)[1] == 2
    assert rad.main(["--project-root", str(tmp_path / "nope"), "--kind", "dev-tooling"]) == 2
