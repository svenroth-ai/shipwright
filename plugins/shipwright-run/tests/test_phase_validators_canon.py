"""The canon bridge never swallows a degraded run (campaign A3): an absent verifier
package or a missing run id is an inform note, a broken package or an explicitly empty
run id is ask-level — all with ``kind: canon_degraded``."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_LIB = _REPO_ROOT / "plugins" / "shipwright-run" / "scripts" / "lib"
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

_spec = importlib.util.spec_from_file_location("phase_validators_canon_entry", _LIB / "phase_validators.py")
_pv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pv)

# importable by bare name once phase_validators has put its lib dir on sys.path
import phase_validators_canon as canon  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.01/AC01")


def _hide_verifiers(monkeypatch):
    """Make ``tools.verifiers`` unlocatable, including submodules an earlier test cached."""
    for name in [m for m in sys.modules if m == "tools.verifiers" or m.startswith("tools.verifiers.")]:
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setitem(sys.modules, "tools.verifiers", None)


def test_absent_canon_package_is_a_visible_degraded_note(tmp_path, monkeypatch):
    _hide_verifiers(monkeypatch)
    issues: list[dict] = []
    canon._run_canon_checks("plan", tmp_path, issues, run_id="r3")
    assert len(issues) == 1
    assert issues[0]["severity"] == "inform" and issues[0]["kind"] == "canon_degraded"
    assert issues[0]["message"].startswith(f"{canon.DEGRADED_PREFIX} plan: canon verifiers are not importable")


def test_broken_canon_module_import_is_ask_level(tmp_path, monkeypatch):
    """The package is locatable, so a submodule that fails to import is broken, not absent."""
    monkeypatch.setitem(sys.modules, "tools.verifiers.plan_checks", None)
    issues: list[dict] = []
    canon._run_canon_checks("plan", tmp_path, issues, run_id="r3")
    assert [(i["severity"], i["kind"]) for i in issues] == [("ask", "canon_degraded")]
    assert "a canon verifier failed to import" in issues[0]["message"]


def test_explicit_empty_run_id_is_ask_level(tmp_path):
    issues: list[dict] = []
    canon._run_canon_checks("plan", tmp_path, issues, run_id="  ")
    assert [(i["severity"], i["kind"]) for i in issues] == [("ask", "canon_degraded")]
    assert "empty run id" in issues[0]["message"]


def test_degraded_note_reaches_the_gate_consumer(tmp_path, monkeypatch):
    """run_phase_gate (the v1 path's consumer, A4's v2 seam) keeps the note as inform."""
    _hide_verifiers(monkeypatch)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    from orchestrator_pkg.validation_record import run_phase_gate

    ask, inform, checked = run_phase_gate(tmp_path, "changelog")
    assert checked and ask == []
    assert [i.get("kind") for i in inform] == ["canon_degraded"]


def _stub_plan_checks(monkeypatch, seen: list):
    from tools.verifiers import plan_checks

    def stub(_root, *, run_id):
        seen.append(run_id)
        return []

    monkeypatch.setattr(plan_checks, "run_plan_checks", stub)


def test_explicit_run_id_beats_the_environment(tmp_path, monkeypatch):
    seen: list = []
    _stub_plan_checks(monkeypatch, seen)
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "from-env")
    issues: list[dict] = []
    canon._run_canon_checks("plan", tmp_path, issues, run_id="explicit")
    assert seen == ["explicit"] and issues == []


def test_missing_run_id_is_a_visible_degraded_note(tmp_path, monkeypatch):
    seen: list = []
    _stub_plan_checks(monkeypatch, seen)
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)
    issues: list[dict] = []
    canon._run_canon_checks("plan", tmp_path, issues)
    assert seen == [""]
    assert [i["kind"] for i in issues] == ["canon_degraded"]
    assert "phase_history[plan] was not checked" in issues[0]["message"]


def test_an_unlocatable_verifier_package_reads_as_absent(monkeypatch):
    def boom(_name):
        raise ValueError("tools.verifiers.__spec__ is None")

    monkeypatch.setattr(canon.importlib.util, "find_spec", boom)
    assert canon._verifiers_present() is False
