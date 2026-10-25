"""The documented recovery after a re-approved Brief package, inside a real git repository (B3a)."""

from __future__ import annotations

import json
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


def _git(root: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)
    return out.stdout


def _reapprove(root: Path) -> None:
    """Edit nothing but the hash: a re-approved package and a restarted run (fresh run_config)."""
    pkg = root / "brief"
    brief = json.loads((pkg / "brief.json").read_text(encoding="utf-8"))
    brief["package_sha256"] = bp.package_sha256(pkg)
    (pkg / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    write_config(root)
    bdi.record(root, "brief")


@pytest.mark.covers("FR-01.04")
def test_the_recovery_ends_green_in_git_with_a_changed_mockup_of_the_same_name(tmp_path):
    root = _project(tmp_path)
    (root / "brief" / "visual-guidelines.md").write_text(GUIDELINES, encoding="utf-8")
    _reapprove(root)
    _apply(root)
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
    old = json.loads(proc.stdout)["issues"][0]
    assert proc.returncode == 1 and old["code"] == "package_changed_since_apply" and "operator" in old["message"]
    designs = root / ".shipwright" / "designs"
    designs.rename(root / ".shipwright" / ("designs.superseded-" + old["message"].split("(")[1][:8]))  # rename, not delete
    _apply(root)
    assert " M .shipwright/designs/uploads/01-notes.html" in _git(root, "status", "--porcelain")
    assert not check_brief_design_applied(root)[0].is_failure
    gates = subprocess.run([sys.executable, str(GATES), "--project-root", str(root), "--gate", "uploads"], capture_output=True, text=True)
    assert gates.returncode == 0, gates.stdout + gates.stderr
    everything = subprocess.run([sys.executable, str(GATES), "--project-root", str(root), "--gate", "all"], capture_output=True, text=True)
    assert everything.returncode == 0, everything.stdout + everything.stderr


@pytest.mark.covers("FR-01.04")
def test_a_modified_upload_stays_red_when_the_marker_does_not_account_for_it(tmp_path):
    root = _project(tmp_path)
    _apply(root)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.org")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "first apply")
    (root / ".shipwright" / "designs" / "uploads" / "01-notes.html").write_text("tampered", encoding="utf-8")
    gates = subprocess.run([sys.executable, str(GATES), "--project-root", str(root), "--gate", "uploads"], capture_output=True, text=True)
    assert gates.returncode != 0


@pytest.mark.covers("FR-01.04")
def test_the_upload_accounting_uses_the_packages_text_rule(tmp_path):
    acct = bdi._lib("brief_upload_accounting")

    assert acct._SNIFF_BYTES == bdi._lib("brief_package_manifest")._SNIFF_BYTES
    assert acct.accounted_by_applied_package(tmp_path, tmp_path / "x.html") is False  # no run_config at all


@pytest.mark.covers("FR-01.04")
def test_a_malformed_run_config_of_a_non_brief_project_gives_no_result(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text("{ not json", encoding="utf-8")
    assert check_brief_design_applied(tmp_path) == []
    (tmp_path / "shipwright_run_config.json").write_text('{ "brief_dir": ', encoding="utf-8")
    assert check_brief_design_applied(tmp_path)[0].is_failure
