"""CLI tests for resolve_gate_policy.py (SS2).

The lib (lib.gate_policy) is covered by shared/tests/test_gate_policy.py; here we
prove the thin CLI wiring: mode precedence, JSON shapes, unknown-gate exit code,
--phase/--list, --render-doc.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure shared scripts are importable (mirrors test_record_event.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # shared/

from scripts.tools.resolve_gate_policy import main  # noqa: E402


def _run(capsys, argv):
    rc = main(argv)
    out = capsys.readouterr()
    return rc, out.out, out.err


def test_gate_single_session_hard_stop(capsys):
    rc, out, _ = _run(capsys, ["--gate", "deploy.prod-deploy-confirm", "--mode", "single_session"])
    assert rc == 0
    data = json.loads(out)
    assert data["effective_policy"] == "hard-stop"
    assert data["should_stop"] is True
    assert data["default_answer"] is None


def test_gate_single_session_auto_default(capsys):
    rc, out, _ = _run(capsys, ["--gate", "project.interview", "--mode", "single_session"])
    assert rc == 0
    data = json.loads(out)
    assert data["effective_policy"] == "auto-default"
    assert data["should_stop"] is False
    assert data["default_answer"]


def test_gate_multi_session_is_interactive(capsys):
    rc, out, _ = _run(capsys, ["--gate", "project.interview", "--mode", "multi_session"])
    assert rc == 0
    assert json.loads(out)["effective_policy"] == "interactive"


def test_unknown_gate_safe_fallback(capsys):
    """An unknown gate resolves to interactive (ask the human) + a stderr warning,
    exit 0 — never a crash that could loop an LLM subagent."""
    rc, out, err = _run(capsys, ["--gate", "deploy.nope", "--mode", "single_session"])
    assert rc == 0
    data = json.loads(out)
    assert data["effective_policy"] == "interactive"
    assert data["should_stop"] is True
    assert data["unknown_gate"] is True
    assert "unknown gate id" in err.lower()


def test_phase_list(capsys):
    rc, out, _ = _run(capsys, ["--phase", "deploy", "--list", "--mode", "single_session"])
    assert rc == 0
    data = json.loads(out)
    assert data["mode"] == "single_session"
    assert data["gates"], "expected deploy gates"
    assert all(g["phase"] == "deploy" for g in data["gates"])
    # The PROD danger family is present and hard-stops.
    by_id = {g["gate_id"]: g for g in data["gates"]}
    assert by_id["deploy.prod-deploy-confirm"]["effective_policy"] == "hard-stop"


def test_render_doc(capsys):
    rc, out, _ = _run(capsys, ["--render-doc"])
    assert rc == 0
    assert out.startswith("# Single-Session Phase-Gate Catalog")
    assert "deploy.prod-deploy-confirm" in out


def test_env_mode_is_respected(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("SHIPWRIGHT_RUN_MODE", "single_session")
    rc, out, _ = _run(capsys, ["--gate", "project.interview", "--project-root", str(tmp_path)])
    assert rc == 0
    assert json.loads(out)["effective_policy"] == "auto-default"


def test_project_root_run_config_mode(capsys, monkeypatch, tmp_path):
    monkeypatch.delenv("SHIPWRIGHT_RUN_MODE", raising=False)
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"schemaVersion": 2, "mode": "single_session"}), encoding="utf-8"
    )
    rc, out, _ = _run(capsys, ["--gate", "design.preview-approval", "--project-root", str(tmp_path)])
    assert rc == 0
    assert json.loads(out)["effective_policy"] == "orchestrator-approve"


def test_render_doc_output_writes_utf8_lf_file(capsys, tmp_path):
    out = tmp_path / "gate-catalog.md"
    rc, stdout, _ = _run(capsys, ["--render-doc", "--output", str(out)])
    assert rc == 0
    assert stdout == ""  # written to file, not stdout
    raw = out.read_bytes()
    assert b"\r\n" not in raw  # LF only
    assert all(c < 128 for c in raw)  # pure ASCII
    assert raw.decode("utf-8").startswith("# Single-Session Phase-Gate Catalog")


def test_requires_an_action(capsys):
    with pytest.raises(SystemExit):
        main([])
