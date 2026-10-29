"""write_run_config.py --brief-dir: the Brief package is verified before anything is written,
its profile wins over detection, and brief_dir survives for a resume (campaign brief-driven-run, B2)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from write_run_config import main

_LIB = Path(__file__).resolve().parents[3] / "shared" / "scripts" / "lib" / "brief_dir_intake.py"
_spec = importlib.util.spec_from_file_location("_wrc_test_bdi", _LIB)
bdi = importlib.util.module_from_spec(_spec)
sys.modules["_wrc_test_bdi"] = bdi
_spec.loader.exec_module(bdi)
bp = bdi._lib("brief_package")


_BRIEF_MD = """# App

## Capture note
Requirement: A user can add a note with a title and a body.
- Outcome: a saved note appears in the list
- Fit criterion: a note added with a title is listed within one second
- Purpose: keep ideas from getting lost
- Boundaries: plain text only
- Failure: an empty title is refused
- Glossary: n/a: no new term
- Rationale: n/a: simplest flow
- Out of scope: sharing
"""


def _package(project: Path, approved_by: str | None = "human:sven", md: str = _BRIEF_MD) -> Path:
    dest = project / "brief"
    (dest / "mockups").mkdir(parents=True)
    files = {"brief.md": md, "scope.md": "s\n", "visual-guidelines.md": "v\n",
             "mockups/01.html": "<html></html>\n",
             "screen-map.json": json.dumps({"screens": [{"id": "n", "mockup": "01.html"}]})}
    for rel, text in files.items():
        (dest / rel).write_text(text, encoding="utf-8")
    brief = {"version": 2, "profile": "vite-hono", "deploy_target": "none", "autonomy": "guided",
             "ux_shape": "classic", "source_class": "synthetic", "scope": "scope.md",
             "design_system": "visual-guidelines.md", "brief_dir": "brief", "env_preflight": [],
             "allow_parallel_builders": False, "ui_host": "web"}
    if approved_by:
        brief.update(approved_by=approved_by, approved_at="2026-10-25")
    (dest / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    brief["package_sha256"] = bp.package_sha256(dest)
    (dest / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    return dest


def _run(project: Path, *extra: str) -> int:
    old, sys.argv = sys.argv, ["write_run_config.py", "--project-root", str(project), *extra]
    try:
        return main()
    finally:
        sys.argv = old


@pytest.mark.covers("FR-01.02")
def test_brief_profile_wins_and_brief_dir_is_stored(tmp_path):
    _package(tmp_path)
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"next": "15"}}))  # would detect supabase
    assert _run(tmp_path, "--brief-dir", "brief") == 0
    cfg = json.loads((tmp_path / "shipwright_run_config.json").read_text())
    assert cfg["profile"] == "vite-hono" and cfg["brief_dir"] == "brief"
    assert len(cfg["brief_package"]["package_sha256"]) == 64
    assert bdi.verify_run_config(tmp_path)["verified"] is True


@pytest.mark.covers("FR-01.02")
def test_thin_visual_guidelines_warn_but_do_not_block(tmp_path, capsys):
    _package(tmp_path)  # visual-guidelines.md is "v": no kit tokens at all
    assert _run(tmp_path, "--brief-dir", "brief") == 0
    err = capsys.readouterr().err
    assert "WARNING: visual-guidelines.md declares 0 of the" in err
    assert (tmp_path / "shipwright_run_config.json").is_file()


@pytest.mark.covers("FR-01.02")
def test_refused_package_writes_no_config(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv(bdi.FIXTURE_ENV, raising=False)
    _package(tmp_path, approved_by="fixture:demo")
    assert _run(tmp_path, "--brief-dir", "brief") == 5
    assert "fixture_approval_refused" in capsys.readouterr().err
    assert not (tmp_path / "shipwright_run_config.json").exists()


@pytest.mark.covers("FR-01.02")
def test_thin_brief_is_refused_at_intake_not_in_the_project_phase(tmp_path, capsys):
    """F6: the Project content check runs when the package is taken in; nothing is written."""
    _package(tmp_path, md=_BRIEF_MD.replace("- Purpose: keep ideas from getting lost\n", "- Purpose:\n"))
    assert _run(tmp_path, "--brief-dir", "brief") == 5
    err = capsys.readouterr().err
    assert "invalid_content" in err and "Capture note: empty_dimension: dimension 'purpose' has no text" in err
    assert not (tmp_path / "shipwright_run_config.json").exists()


@pytest.mark.covers("FR-01.02")
def test_bad_brief_dir_exits_5(tmp_path):
    assert _run(tmp_path, "--brief-dir", "missing", "--profile", "vite-hono") == 5
    assert not (tmp_path / "shipwright_run_config.json").exists()


@pytest.mark.covers("FR-01.02")
def test_without_brief_dir_nothing_changes(tmp_path):
    assert _run(tmp_path, "--profile", "vite-hono") == 0
    cfg = json.loads((tmp_path / "shipwright_run_config.json").read_text())
    assert "brief_dir" not in cfg and "brief_package" not in cfg


@pytest.mark.covers("FR-01.02")
def test_explicit_profile_cannot_override_the_approved_brief(tmp_path):
    _package(tmp_path)
    assert _run(tmp_path, "--brief-dir", "brief", "--profile", "supabase-nextjs") == 5
    assert not (tmp_path / "shipwright_run_config.json").exists()
    assert _run(tmp_path, "--brief-dir", "brief", "--profile", "vite-hono") == 0


@pytest.mark.covers("FR-01.02")
def test_a_lock_timeout_while_recording_leaves_no_config_behind(tmp_path, monkeypatch):
    import write_run_config as wrc

    _package(tmp_path)
    mod = wrc._load_brief_dir_intake()

    def boom(*_a, **_k):
        raise mod._lib("file_lock").LockTimeout("held")

    monkeypatch.setattr(mod, "record", boom)
    monkeypatch.setattr(wrc, "_load_brief_dir_intake", lambda: mod)
    assert _run(tmp_path, "--brief-dir", "brief") == 5
    assert not (tmp_path / "shipwright_run_config.json").exists()
