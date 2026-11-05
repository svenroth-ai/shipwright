"""Design, autonomous run (e2e run 22): approved package links pass the standalone gate,
and a brief requirement no mockup shows is built from the brief -- neither is asked.
The rule logic is tested in-process in shared/tests/test_autonomous_rules.py."""

import json
import sys
from pathlib import Path

import pytest

from tests.test_check_design_gates import _problems, run_gates

pytestmark = pytest.mark.covers("FR-01.04/AC06")

ROOT = Path(__file__).resolve().parent.parent
LINK = '<a href="https://www.reddit.com/r/x/comments/1">Open thread</a>'


def _package_sha256(bdir: Path) -> str:
    shared = str(ROOT.parent.parent / "shared" / "scripts")
    sys.path.append(shared)
    try:
        from shared_lib_loader import load_shared_lib
        return load_shared_lib("brief_package", prefer_private=True).package_sha256(bdir)
    finally:
        sys.path.remove(shared)


def _package(root: Path) -> str:
    """An approved package whose own mockup carries LINK; returns its hash (run_config records it)."""
    bdir = root / "brief"
    (bdir / "mockups").mkdir(parents=True)
    files = {"brief.md": "# Board\n", "scope.md": "# Scope\n", "visual-guidelines.md": "# Visual\n",
             "mockups/01-board.html": f"<html><body>{LINK}</body></html>\n",
             "screen-map.json": json.dumps({"screens": [{"id": "board", "mockup": "01-board.html"}]}),
             "brief.json": json.dumps({
                 "version": 2, "profile": "vite-hono", "deploy_target": "none", "autonomy": "autonomous",
                 "ux_shape": "classic", "source_class": "synthetic", "scope": "scope.md",
                 "design_system": "visual-guidelines.md", "brief_dir": "brief", "env_preflight": [],
                 "allow_parallel_builders": False, "ui_host": "web"})}
    for rel, text in files.items():
        (bdir / rel).write_text(text, encoding="utf-8")
    return _package_sha256(bdir)


def _project(tmp_path: Path, cfg: dict) -> Path:
    designs = tmp_path / ".shipwright" / "designs"
    for d in ("screens", "flows", "uploads"):
        (designs / d).mkdir(parents=True)
    (designs / "brief-package-applied.json").write_text("{}", encoding="utf-8")
    (designs / "uploads" / "01-board.html").write_text(f"<html><body>{LINK}</body></html>", encoding="utf-8")
    (designs / "screens" / "01-board.html").write_text(
        f'<html><body>{LINK}<img src="https://cdn.example/x.png"></body></html>', encoding="utf-8")
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return tmp_path


def test_autonomous_gate_keeps_approved_links_and_still_fails_a_loaded_asset(tmp_path):
    sha = _package(tmp_path)
    root = _project(tmp_path, {"autonomy": "guided", "brief_dir": "brief", "brief_package": {"package_sha256": sha}})
    code, out = run_gates(root, "standalone")
    gate = next(g for g in out["gates"] if g["gate"] == "standalone")
    assert code == 1
    assert gate["kept_approved_links"] == ["screens/01-board.html: approved package link "
                                           "https://www.reddit.com/r/x/comments/1"]
    assert "package_unverified" not in gate
    assert _problems(out, "standalone") == ["screens/01-board.html: external reference https://cdn.example/x.png"]


def test_a_package_changed_after_approval_keeps_nothing_and_says_why(tmp_path):
    sha = _package(tmp_path)
    (tmp_path / "brief" / "scope.md").write_text("# Scope, edited after approval\n", encoding="utf-8")
    root = _project(tmp_path, {"autonomy": "autonomous", "brief_dir": "brief", "brief_package": {"package_sha256": sha}})
    code, out = run_gates(root, "standalone")
    gate = next(g for g in out["gates"] if g["gate"] == "standalone")
    assert code == 1 and "kept_approved_links" not in gate
    assert "hash_mismatch" in gate["package_unverified"] and len(_problems(out, "standalone")) == 2


def test_interactive_gate_is_unchanged(tmp_path):
    root = _project(tmp_path, {"autonomy": "guided"})
    code, out = run_gates(root, "standalone")
    assert code == 1
    assert len(_problems(out, "standalone")) == 2
    assert "kept_approved_links" not in next(g for g in out["gates"] if g["gate"] == "standalone")


def _flat(rel: str) -> str:
    return " ".join((ROOT / rel).read_text(encoding="utf-8").split())


def test_upload_mode_states_both_rules_and_keeps_the_interactive_questions():
    u = _flat("skills/design/references/upload-mode.md")
    assert "--kind approved-links --phase Design" in u and "`kept_approved_links`" in u
    assert "--kind brief-wins --phase Design" in u and "screens stay as approved" in u
    assert "build from the brief, fix and re-approve the package, or drop it" in u
    s = _flat("skills/design/SKILL.md")
    assert "record both with `record_autonomous_decision.py`, never ask" in s
    b = _flat("skills/design/references/brief-compose.md")
    assert "an autonomous run's gate keeps it (`kept_approved_links`" in b
