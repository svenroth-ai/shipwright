"""The documented recovery after a re-approved Brief package, inside a real git repository (B3a)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))

from _brief_dir_helpers import bdi, bp, write_config  # noqa: E402
from test_brief_design_checks import TOOL, _apply, _project  # noqa: E402
from tools.verifiers.brief_design_checks import check_brief_design_applied  # noqa: E402

GATES = TOOL.parent / "check-design-gates.py"
GUIDELINES = "# Visual\n\n## Colours\nblue\n\n## Typography\nInter\n\n## Spacing\n8px\n"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not available")


def _git(root: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)
    return out.stdout


def _reapprove(root: Path) -> None:
    """A re-approved package and a restarted run (a fresh run_config records the new hash)."""
    pkg = root / "brief"
    brief = json.loads((pkg / "brief.json").read_text(encoding="utf-8"))
    brief["package_sha256"] = bp.package_sha256(pkg)
    (pkg / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    write_config(root)
    bdi.record(root, "brief")


def _gate(root: Path, name: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(GATES), "--project-root", str(root), "--gate", name], capture_output=True, text=True)


def _superseded_project(tmp_path: Path) -> tuple[Path, str]:
    """Committed first apply, then a re-approved package whose mockup (same name) changed; the tool's refusal
    is read, and the operator's step 1 (the rename) is done. Returns the project and the old hash8."""
    root = _project(tmp_path)
    (root / "brief" / "visual-guidelines.md").write_text(GUIDELINES, encoding="utf-8")
    _reapprove(root)
    _apply(root)
    (root / ".shipwright" / "designs" / "design-feedback-round1.md").write_text("# Round 1\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.org")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "first apply")
    (root / "brief" / "mockups" / "01-notes.html").write_text("<!doctype html><html><body>Notes v2</body></html>\n", encoding="utf-8")
    _reapprove(root)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "re-approved package")
    proc = subprocess.run([sys.executable, str(TOOL), "--project-root", str(root)], capture_output=True, text=True)
    issue = json.loads(proc.stdout)["issues"][0]
    assert proc.returncode == 1 and issue["code"] == "package_changed_since_apply" and "operator" in issue["message"]
    old = issue["old_hash8"]
    (root / ".shipwright" / "designs").rename(root / ".shipwright" / f"designs.superseded-{old}")  # step 1: rename, not delete
    return root, old


@pytest.mark.covers("FR-01.04")
def test_the_documented_recovery_ends_green_in_git(tmp_path):
    root, old = _superseded_project(tmp_path)
    _git(root, "add", "-A", ".shipwright/designs", f".shipwright/designs.superseded-{old}")  # step 2: commit the move
    _git(root, "commit", "-q", "-m", "supersede the old designs")
    _apply(root)  # step 3: the tool FIRST
    superseded = root / ".shipwright" / f"designs.superseded-{old}"
    shutil.copy(superseded / "design-feedback-round1.md", root / ".shipwright" / "designs" / "design-feedback-round1.md")  # step 4
    assert " M .shipwright/designs/uploads/01-notes.html" not in _git(root, "status", "--porcelain")
    assert not check_brief_design_applied(root)[0].is_failure
    for name in ("uploads", "all"):
        done = _gate(root, name)
        assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.covers("FR-01.04")
def test_without_the_commit_step_the_uploads_gate_is_red(tmp_path):
    root, _old = _superseded_project(tmp_path)
    _apply(root)  # step 2 skipped: the same-named upload now differs from the committed one
    assert " M .shipwright/designs/uploads/01-notes.html" in _git(root, "status", "--porcelain")
    assert _gate(root, "uploads").returncode != 0


@pytest.mark.covers("FR-01.04")
def test_a_malformed_run_config_of_a_non_brief_project_gives_no_result(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text("{ not json", encoding="utf-8")
    assert check_brief_design_applied(tmp_path) == []
    (tmp_path / "shipwright_run_config.json").write_text('{ "brief_dir": ', encoding="utf-8")
    assert check_brief_design_applied(tmp_path)[0].is_failure
