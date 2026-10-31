"""``affected_acs``: the rule (lib), the F11 claim check, and the replay."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from lib.affected_acs_gate import declaration_present, is_runtime_path, requires_declaration
from tools.affected_acs_replay import replay
from tools.verifiers import _finalization_claims as claims
from tools.verifiers.affected_acs_check import CHECK_NAME, check_affected_acs_declared

_RUN = "iterate-2026-10-31-acs-probe"


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("path,expected", [
    ("plugins/shipwright-iterate/scripts/lib/x.py", True),
    ("shared/scripts/lib/x.py", True),
    ("plugins/shipwright-iterate/skills/iterate/SKILL.md", True),
    ("shared/scripts/tests/test_x.py", False),
    ("plugins/shipwright-test/skills/test/SKILL.md", True),
    ("plugins/shipwright-test/scripts/lib/test_runner.py", True),
    ("shared/scripts/test_hygiene.py", True),
    ("shared/tests/test_x.py", False),
    ("plugins/shipwright-build/tests/conftest.py", False),
    ("shared/docs/notes.md", False),
    ("docs/guide.md", False),
    (".shipwright/planning/x.md", False),
    ("shared\\scripts\\lib\\x.py", True),
    (None, False),
])
def test_runtime_path_classification(path, expected):
    assert is_runtime_path(path) is expected


@pytest.mark.covers("FR-01.11")
def test_declaration_is_presence_only():
    assert declaration_present({"affected_acs": [{"ac": "FR-01.11.AC01"}]})
    assert declaration_present({"affected_acs": ["anything at all"]})
    assert declaration_present({"catalog_gap": True, "catalog_gap_fr": "FR-01.11"})
    assert not declaration_present({"affected_acs": []})
    assert not declaration_present({"catalog_gap": True})
    assert not declaration_present({"catalog_gap": False, "catalog_gap_fr": "FR-01.11"})
    assert not declaration_present({})
    assert not declaration_present(None)


@pytest.mark.covers("FR-01.11")
def test_requires_declaration_needs_intent_and_runtime_path():
    runtime = ["shared/scripts/lib/x.py"]
    assert requires_declaration({"intent": "bug"}, runtime)
    assert not requires_declaration({"intent": "docs"}, runtime)
    assert not requires_declaration({"intent": "feature"}, ["docs/guide.md"])
    assert not requires_declaration({}, runtime)


def _seed(root: Path, **event) -> None:
    evt = {"type": "work_completed", "source": "iterate", "commit": "", "adr_id": _RUN, **event}
    (root / "shipwright_events.jsonl").write_text(json.dumps(evt) + "\n", encoding="utf-8")


@pytest.mark.covers("FR-01.11", "FR-01.11/AC47")
def test_check_fails_when_runtime_touched_and_field_absent(tmp_path):
    _seed(tmp_path, intent="change", spec_impact="none", changed_files=["shared/scripts/lib/x.py"])
    result = check_affected_acs_declared(tmp_path, _RUN, "")
    assert result.name == CHECK_NAME and result.ok is False and result.severity == "warning"
    assert "affected_acs" in result.detail and "catalog_gap" in result.detail


@pytest.mark.covers("FR-01.11", "FR-01.11/AC47")
def test_check_passes_with_declaration_whatever_the_content(tmp_path):
    _seed(tmp_path, intent="change", changed_files=["shared/scripts/lib/x.py"],
          affected_acs=[{"ac": "not even an id", "why": ""}])
    assert check_affected_acs_declared(tmp_path, _RUN, "").ok is True


@pytest.mark.covers("FR-01.11")
def test_check_passes_with_catalog_gap(tmp_path):
    _seed(tmp_path, intent="feature", changed_files=["plugins/a/b.py"], catalog_gap=True, catalog_gap_fr="FR-01.11",
          catalog_gap_acs=["FR-01.11.AC47"])
    assert check_affected_acs_declared(tmp_path, _RUN, "").ok is True


@pytest.mark.covers("FR-01.11")
def test_gap_closed_by_ac_or_closed_reason_only():
    from lib.affected_acs_gate import gap_closed
    assert gap_closed({"affected_acs": [{"ac": "x"}]})  # no gap declared: nothing to close
    assert gap_closed({"catalog_gap": True, "catalog_gap_fr": "FR-01.11", "catalog_gap_acs": ["FR-01.11.AC47"]})
    assert gap_closed({"catalog_gap": True, "catalog_gap_fr": "FR-01.11", "catalog_gap_reason": "how-only"})
    assert gap_closed({"catalog_gap": True, "catalog_gap_reason": " How-Only "})
    assert not gap_closed({"catalog_gap": True, "catalog_gap_fr": "FR-01.11"})
    assert not gap_closed({"catalog_gap": True, "catalog_gap_acs": []})
    assert not gap_closed({"catalog_gap": True, "catalog_gap_reason": "because"})
    assert gap_closed(None)  # not an event: nothing to close


@pytest.mark.covers("FR-01.11", "FR-01.11/AC48")
def test_open_gap_is_a_strict_exempt_warning_naming_both_repairs(tmp_path):
    _seed(tmp_path, intent="feature", changed_files=["plugins/a/b.py"], catalog_gap=True, catalog_gap_fr="FR-01.11")
    result = check_affected_acs_declared(tmp_path, _RUN, "")
    assert result.ok is False and result.severity == "warning" and result.strict_exempt is True
    assert "catalog_gap_acs" in result.detail and "how-only" in result.detail
    _seed(tmp_path, intent="feature", changed_files=["plugins/a/b.py"], catalog_gap=True, catalog_gap_fr="FR-01.11",
          catalog_gap_reason="how-only")
    assert check_affected_acs_declared(tmp_path, _RUN, "").ok is True


@pytest.mark.covers("FR-01.11")
def test_check_skips_docs_only_other_intent_and_missing_event(tmp_path):
    _seed(tmp_path, intent="change", changed_files=["docs/guide.md"])
    assert check_affected_acs_declared(tmp_path, _RUN, "").severity == "skipped"
    _seed(tmp_path, intent="docs", changed_files=["shared/scripts/lib/x.py"])
    assert check_affected_acs_declared(tmp_path, _RUN, "").severity == "skipped"
    assert check_affected_acs_declared(tmp_path, "iterate-other", "").severity == "skipped"


@pytest.mark.covers("FR-01.11")
def test_check_is_blind_not_clean_without_any_path_view(tmp_path):
    _seed(tmp_path, intent="change")
    result = check_affected_acs_declared(tmp_path, _RUN, "")
    assert result.ok is True and result.severity == "skipped" and "BLIND" in result.detail


@pytest.mark.covers("FR-01.11")
def test_check_is_registered():
    assert check_affected_acs_declared in claims.CLAIM_CHECKS


@pytest.mark.covers("FR-01.11")
def test_replay_counts_required_declared_and_missing():
    events = [
        {"type": "work_completed", "source": "iterate", "intent": "change", "adr_id": "a", "changed_files": ["shared/scripts/x.py"]},
        {"type": "work_completed", "source": "iterate", "intent": "bug", "adr_id": "b", "changed_files": ["plugins/p/x.py"], "affected_acs": ["x"]},
        {"type": "work_completed", "source": "iterate", "intent": "change", "adr_id": "c", "changed_files": ["docs/guide.md"]},
        {"type": "work_completed", "source": "build", "intent": "change", "adr_id": "d", "changed_files": ["shared/scripts/x.py"]},
    ]
    got = replay(events, 100)
    assert (got["window"], got["required"], got["declared"], got["missing"]) == (3, 2, 1, 1)
    assert got["missing_run_ids"] == ["a"] and got["conclusive"] is True
    assert replay(events, 1)["window"] == 1


@pytest.mark.covers("FR-01.11")
def test_replay_without_path_data_is_inconclusive_not_clean():
    events = [{"type": "work_completed", "source": "iterate", "intent": "change", "adr_id": "x"}]
    got = replay(events, 100)
    assert got["required"] == 0 and got["unknown_paths"] == 1 and got["conclusive"] is False


@pytest.mark.covers("FR-01.11")
def test_check_ignores_non_iterate_events(tmp_path):
    _seed(tmp_path, source="build", intent="change", changed_files=["shared/scripts/lib/x.py"])
    assert check_affected_acs_declared(tmp_path, _RUN, "").severity == "skipped"


@pytest.mark.covers("FR-01.11")
def test_empty_git_view_does_not_hide_runtime_paths_listed_on_the_event(tmp_path, monkeypatch):
    from tools.verifiers import affected_acs_check as mod
    monkeypatch.setattr(mod, "git_context", lambda root: "work_tree")
    monkeypatch.setattr(mod, "_iterate_changed_paths", lambda root, commit: [])
    _seed(tmp_path, intent="change", changed_files=["shared/scripts/lib/x.py"])
    assert check_affected_acs_declared(tmp_path, _RUN, "").ok is False


@pytest.mark.covers("FR-01.11")
def test_replay_uses_the_git_supplied_paths_for_events_without_a_path_list():
    events = [{"type": "work_completed", "source": "iterate", "intent": "change", "adr_id": "x"}]
    got = replay(events, 100, paths_for=lambda rid: ["shared/scripts/lib/a.py"] if rid == "x" else None)
    assert got["required"] == 1 and got["missing"] == 1 and got["conclusive"] is True
    assert replay(events, 100, paths_for=lambda rid: None)["conclusive"] is False


@pytest.mark.covers("FR-01.11")
def test_git_view_showing_runtime_paths_fails_even_when_event_lists_docs_only(tmp_path, monkeypatch):
    from tools.verifiers import affected_acs_check as mod
    monkeypatch.setattr(mod, "git_context", lambda root: "work_tree")
    monkeypatch.setattr(mod, "_iterate_changed_paths", lambda root, commit: ["plugins/x/scripts/lib/y.py"])
    _seed(tmp_path, intent="change", changed_files=["docs/guide.md"])
    assert check_affected_acs_declared(tmp_path, _RUN, "").ok is False


@pytest.mark.covers("FR-01.11")
def test_blind_git_view_falls_back_to_event_paths(tmp_path, monkeypatch):
    from tools.verifiers import affected_acs_check as mod
    monkeypatch.setattr(mod, "git_context", lambda root: "work_tree")
    monkeypatch.setattr(mod, "_iterate_changed_paths", lambda root, commit: None)
    _seed(tmp_path, intent="change", changed_files=["shared/scripts/lib/x.py"])
    assert check_affected_acs_declared(tmp_path, _RUN, "").ok is False


@pytest.mark.covers("FR-01.11")
def test_git_error_fails_closed_unless_the_event_already_decides(tmp_path, monkeypatch):
    from tools.verifiers import affected_acs_check as mod
    monkeypatch.setattr(mod, "git_context", lambda root: "git_error")
    _seed(tmp_path, intent="change")
    result = check_affected_acs_declared(tmp_path, _RUN, "")
    assert result.ok is False and result.severity == "warning" and "git could not answer" in result.detail


@pytest.mark.covers("FR-01.11")
def test_missing_declaration_is_a_strict_exempt_warning_and_present_one_passes(tmp_path):
    _seed(tmp_path, intent="change", changed_files=["shared/scripts/lib/x.py"])
    missing = check_affected_acs_declared(tmp_path, _RUN, "")
    assert missing.severity == "warning" and missing.strict_exempt is True and missing.ok is False
    _seed(tmp_path, intent="change", changed_files=["shared/scripts/lib/x.py"],
          affected_acs=[{"ac": "FR-01.03.AC05", "disposition": "checked-unchanged", "why": "x"}])
    present = check_affected_acs_declared(tmp_path, _RUN, "")
    assert present.ok is True and present.severity != "warning"


@pytest.mark.covers("FR-01.11")
def test_replay_main_prints_counts_from_an_events_file(tmp_path, monkeypatch, capsys):
    from tools import affected_acs_replay as mod
    _seed(tmp_path, intent="change", changed_files=["shared/scripts/lib/x.py"])
    monkeypatch.setattr(sys, "argv", ["affected_acs_replay.py", "--project-root", str(tmp_path), "--window", "5"])
    assert mod.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["required"] == 1 and out["missing"] == 1 and out["conclusive"] is True


@pytest.mark.covers("FR-01.11")
def test_git_paths_for_run_reads_run_id_commits(tmp_path, monkeypatch):
    from tools import affected_acs_replay as mod

    def fake_run(cmd, **kwargs):
        out = "sha1\nsha2\n" if "log" in cmd else ("b.py\na.py\n" if cmd[-1] == "sha1" else "a.py\n")
        return types.SimpleNamespace(stdout=out)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    assert mod.git_paths_for_run(tmp_path, "run-1") == ["a.py", "b.py"]
    assert mod.git_paths_for_run(tmp_path, "") is None
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: types.SimpleNamespace(stdout=""))
    assert mod.git_paths_for_run(tmp_path, "run-1") is None

    def boom(*a, **k):
        raise OSError("no git")

    monkeypatch.setattr(mod.subprocess, "run", boom)
    assert mod.git_paths_for_run(tmp_path, "run-1") is None
