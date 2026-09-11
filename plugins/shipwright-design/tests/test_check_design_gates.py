"""The in-session design gates — FR-01.04's mechanisable criteria, as a command."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = str(
    Path(__file__).resolve().parent.parent / "scripts" / "checks" / "check-design-gates.py"
)

GOOD_GUIDELINES = (
    "# Visual Guidelines\n\n"
    "## Typography\n- Primary font: Inter\n\n"
    "## Colors\n| Role | Value |\n|---|---|\n| Background | #fff |\n\n"
    "## Spacing & Layout\n- Base unit: 4px\n"
)


def run_gates(project_root: Path, gate: str = "all", round_path: Path | None = None) -> tuple[int, dict]:
    cmd = [sys.executable, SCRIPT, "--project-root", str(project_root), "--gate", gate]
    if round_path is not None:
        cmd += ["--round", str(round_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    try:
        return proc.returncode, json.loads(proc.stdout)
    except json.JSONDecodeError:  # pragma: no cover - diagnostic path
        raise AssertionError(f"non-JSON stdout: {proc.stdout!r} / {proc.stderr!r}")


def _problems(out: dict, gate: str) -> list[str]:
    return next(g for g in out["gates"] if g["gate"] == gate)["problems"]


@pytest.fixture
def project(tmp_path):
    """A design session whose every gate passes."""
    root = tmp_path
    designs = root / ".shipwright" / "designs"
    (designs / "screens").mkdir(parents=True)
    (designs / "flows").mkdir()
    (designs / "uploads").mkdir()

    (root / ".shipwright" / "planning" / "01-auth").mkdir(parents=True)
    (root / ".shipwright" / "planning" / "01-auth" / "spec.md").write_text(
        "| ID | Requirement | Priority |\n| FR-01.01 | User can log in | Must |\n",
        encoding="utf-8",
    )
    (designs / "screens" / "01-login.html").write_text(
        "<!-- Requirements: FR-01.01 -->\n<html><body>Login</body></html>", encoding="utf-8"
    )
    (designs / "design-manifest.md").write_text(
        "# Design Manifest\n\n## Screens\n\n"
        "| # | Screen | File | Status | Linked FRs |\n|---|---|---|---|---|\n"
        "| 01 | login | screens/01-login.html | complete | FR-01.01 |\n",
        encoding="utf-8",
    )
    (designs / "visual-guidelines.md").write_text(GOOD_GUIDELINES, encoding="utf-8")
    return root


def test_a_clean_project_passes_every_gate(project):
    code, out = run_gates(project)
    assert code == 0, out
    assert out["success"] is True


def test_a_missing_project_root_is_a_usage_error(tmp_path):
    code, out = run_gates(tmp_path / "nope")
    assert code == 2
    assert out["error"] == "project_root_not_found"


# --- fr-coverage (#1 / #4) --------------------------------------------------


def test_an_orphan_fr_fails_fr_coverage(project):
    (project / ".shipwright" / "planning" / "01-auth" / "spec.md").write_text(
        "| ID | Requirement | Priority |\n"
        "| FR-01.01 | User can log in | Must |\n"
        "| FR-01.02 | Export data | Must |\n",
        encoding="utf-8",
    )
    code, out = run_gates(project, "fr-coverage")
    assert code == 1
    assert any("FR-01.02" in p for p in _problems(out, "fr-coverage"))


def test_a_missing_screen_file_fails_fr_coverage(project):
    (project / ".shipwright" / "designs" / "screens" / "01-login.html").unlink()
    code, out = run_gates(project, "fr-coverage")
    assert code == 1


# --- tokens (#2) -------------------------------------------------------------


def test_missing_visual_guidelines_fails_tokens(project):
    (project / ".shipwright" / "designs" / "visual-guidelines.md").unlink()
    code, out = run_gates(project, "tokens")
    assert code == 1
    assert "does not exist" in _problems(out, "tokens")[0]


# --- flows (#3) --------------------------------------------------------------


def test_multi_screen_with_no_flow_fails(project):
    (project / ".shipwright" / "designs" / "screens" / "02-dashboard.html").write_text(
        "<!-- Requirements: FR-01.01 -->\n<html></html>", encoding="utf-8"
    )
    code, out = run_gates(project, "flows")
    assert code == 1
    assert "0 flows" in _problems(out, "flows")[0]


def test_multi_screen_with_a_flow_passes(project):
    (project / ".shipwright" / "designs" / "screens" / "02-dashboard.html").write_text(
        "<!-- Requirements: FR-01.01 -->\n<html></html>", encoding="utf-8"
    )
    (project / ".shipwright" / "designs" / "flows" / "onboarding.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    assert run_gates(project, "flows")[0] == 0


# --- chrome (#5) --------------------------------------------------------------


def test_no_chrome_definition_is_a_no_op_when_no_screen_uses_nav(project):
    assert run_gates(project, "chrome")[0] == 0


def test_no_chrome_definition_fails_when_a_screen_uses_nav_markup(project):
    """External code review, iterate-2026-09-11-e1-checks-plan-design's high
    finding: absence of chrome-definition.md was accepted unconditionally,
    letting a project with real shared nav skip defining it entirely."""
    (project / ".shipwright" / "designs" / "screens" / "01-login.html").write_text(
        '<!-- Requirements: FR-01.01 -->\n'
        '<aside><a href="02-x.html" class="nav-item active">X</a></aside>',
        encoding="utf-8",
    )
    code, out = run_gates(project, "chrome")
    assert code == 1
    assert any("01-login.html" in p for p in _problems(out, "chrome"))


def test_a_screen_diverging_from_chrome_fails(project):
    (project / ".shipwright" / "designs" / "chrome-definition.md").write_text(
        '<aside class="sidebar"><a href="02-x.html" class="nav-item active">X</a></aside>',
        encoding="utf-8",
    )
    (project / ".shipwright" / "designs" / "screens" / "01-login.html").write_text(
        '<!-- Requirements: FR-01.01 -->\n'
        '<aside class="sidebar"><a href="99-improvised.html" class="nav-item active">Y</a></aside>',
        encoding="utf-8",
    )
    code, out = run_gates(project, "chrome")
    assert code == 1
    assert "01-login.html" in _problems(out, "chrome")[0]


# --- standalone (#6) -----------------------------------------------------------


def test_an_external_script_reference_fails(project):
    (project / ".shipwright" / "designs" / "screens" / "01-login.html").write_text(
        '<!-- Requirements: FR-01.01 -->\n<script src="https://cdn.example.com/x.js"></script>',
        encoding="utf-8",
    )
    code, out = run_gates(project, "standalone")
    assert code == 1
    assert _problems(out, "standalone") == ["screens/01-login.html: external reference https://cdn.example.com/x.js"]


def test_an_allowed_font_cdn_reference_passes(project):
    (project / ".shipwright" / "designs" / "screens" / "01-login.html").write_text(
        '<!-- Requirements: FR-01.01 -->\n<link href="https://fonts.googleapis.com/css?family=Inter">',
        encoding="utf-8",
    )
    assert run_gates(project, "standalone")[0] == 0


# --- uploads (#8) --------------------------------------------------------------


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


def _git_init(project):
    _git(project, "init", "-q")
    _git(project, "config", "user.email", "test@test.invalid")
    _git(project, "config", "user.name", "Test")


def test_uploads_passes_without_git(project):
    assert run_gates(project, "uploads")[0] == 0


def test_a_modified_upload_fails(project):
    _git_init(project)
    upload = project / ".shipwright" / "designs" / "uploads" / "brand.md"
    upload.write_text("x\n", encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "add upload")
    upload.write_text("changed\n", encoding="utf-8")
    code, out = run_gates(project, "uploads")
    assert code == 1
    assert "brand.md" in _problems(out, "uploads")[0]


# --- iteration (#9) --------------------------------------------------------


ROUND_FILE = (
    "# Design Feedback — Round 1\n\n"
    "## 01-auth\n\n"
    "### #1 Login — CHANGES\n\n"
    "**File:** screens/01-login.html  \n"
    "**FRs:** FR-01.01\n\n---\n\n"
)


# round-related regression tests (usage error, all-gate exemption) live in
# test_check_design_gates_tier3_review.py — kept out of this file's budget.


def test_a_flagged_screen_left_untouched_fails(project, tmp_path):
    _git_init(project)
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "init")
    round_path = tmp_path / "design-feedback-round1.md"
    round_path.write_text(ROUND_FILE, encoding="utf-8")
    code, out = run_gates(project, "iteration", round_path=round_path)
    assert code == 1
    assert "01-login.html" in _problems(out, "iteration")[0]


def test_a_flagged_screen_actually_touched_passes(project, tmp_path):
    _git_init(project)
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "init")
    (project / ".shipwright" / "designs" / "screens" / "01-login.html").write_text(
        "<!-- Requirements: FR-01.01 -->\n<html>revised</html>", encoding="utf-8"
    )
    round_path = tmp_path / "design-feedback-round1.md"
    round_path.write_text(ROUND_FILE, encoding="utf-8")
    assert run_gates(project, "iteration", round_path=round_path)[0] == 0


# --- boundary (#11) --------------------------------------------------------


def test_boundary_passes_without_git(project):
    assert run_gates(project, "boundary")[0] == 0


def test_boundary_fails_on_a_production_path(project):
    _git_init(project)
    src = project / "src"
    src.mkdir()
    (src / "app.py").write_text("print('hi')\n", encoding="utf-8")
    code, out = run_gates(project, "boundary")
    assert code == 1
    assert any("src/app.py" in p for p in _problems(out, "boundary"))


def test_the_shared_verifier_import_resolves_after_the_own_lib_loader_runs(project):
    """ADR-045 regression (external plan review, e1-checks-plan-design): the
    module-level ``from tools.verifiers.design_checks import ...`` in
    check-design-gates.py must resolve the SHARED ``lib`` package (for
    ``lib.adr_headers`` etc.), not this plugin's own — verified by actually
    running the fr-coverage gate, which only succeeds if that import chain
    is intact end to end (not just import-without-crashing)."""
    code, out = run_gates(project, "fr-coverage")
    assert code == 0, out


def test_the_cli_is_independent_of_the_caller_s_working_directory(project, tmp_path):
    """External plan review flagged that review-loop.md invokes this CLI as
    part of an operator-facing workflow — confirm it does not silently rely
    on an inherited cwd (every path argument is explicit, and boundary_gate
    uses ``git -C``, not the process cwd)."""
    unrelated_cwd = tmp_path / "somewhere-else"
    unrelated_cwd.mkdir()
    cmd = [sys.executable, SCRIPT, "--project-root", str(project), "--gate", "tokens"]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=str(unrelated_cwd))
    assert proc.returncode == 0, proc.stderr


def test_gate_selection_runs_only_what_was_asked_for(project):
    assert [g["gate"] for g in run_gates(project, "tokens")[1]["gates"]] == ["tokens"]
    assert [g["gate"] for g in run_gates(project, "all")[1]["gates"]] == [
        "fr-coverage", "tokens", "flows", "chrome", "standalone",
        "uploads", "iteration", "boundary",
    ]
