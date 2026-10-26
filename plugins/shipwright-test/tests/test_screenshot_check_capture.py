"""screenshot_check._capture: the Playwright hand-off, with the node subprocess replaced (module object patched)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
import screenshot_check as sc  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.06")


@pytest.fixture
def root(tmp_path):
    (tmp_path / "e2e" / "screenshots" / "screenshot-check").mkdir(parents=True)
    return tmp_path


def fake_run(stdout="", stderr="", raises=None):
    def run(cmd, **kw):
        if raises:
            raise raises
        run.cmd = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr=stderr)
    return run


def test_successful_capture_returns_none_and_passes_viewport(root, monkeypatch):
    run = fake_run(json.dumps({"ok": True, "captured": ["a"], "errors": []}))
    monkeypatch.setattr(sc.shutil, "which", lambda name: "node")
    monkeypatch.setattr(sc.subprocess, "run", run)
    assert sc._capture(root, [{"url": "u", "out": "o"}], 5) is None
    assert run.cmd[0] == "node" and run.cmd[-4:] == ["--width", "1280", "--height", "800"]
    assert json.loads((root / "e2e" / "screenshots" / "screenshot-check" / "jobs.json").read_text(encoding="utf-8")) == [{"url": "u", "out": "o"}]


def test_capture_errors_are_reported_by_file(root, monkeypatch):
    out = {"ok": False, "captured": [], "errors": [{"out": "x/built/01.png", "error": "HTTP 404 for http://h/x"}]}
    monkeypatch.setattr(sc.shutil, "which", lambda name: "node")
    monkeypatch.setattr(sc.subprocess, "run", fake_run(json.dumps(out)))
    assert sc._capture(root, [], 5) == "01.png: HTTP 404 for http://h/x"


def test_not_ok_without_error_list_still_fails(root, monkeypatch):
    monkeypatch.setattr(sc.shutil, "which", lambda name: "node")
    monkeypatch.setattr(sc.subprocess, "run", fake_run(json.dumps({"ok": False})))
    assert sc._capture(root, [], 5) == "capture failed"


@pytest.mark.parametrize("stdout", ["", "not json"])
def test_unreadable_capture_output_is_a_reason(root, monkeypatch, stdout):
    monkeypatch.setattr(sc.shutil, "which", lambda name: "node")
    monkeypatch.setattr(sc.subprocess, "run", fake_run(stdout, stderr="boom"))
    assert "unreadable" in sc._capture(root, [], 5)


def test_missing_node_and_timeout_are_reasons(root, monkeypatch):
    monkeypatch.setattr(sc.shutil, "which", lambda name: None)
    assert "node is not on PATH" in sc._capture(root, [], 5)
    monkeypatch.setattr(sc.shutil, "which", lambda name: "node")
    monkeypatch.setattr(sc.subprocess, "run", fake_run(raises=subprocess.TimeoutExpired("node", 5)))
    assert "did not run" in sc._capture(root, [], 5)
