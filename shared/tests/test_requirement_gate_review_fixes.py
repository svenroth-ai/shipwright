"""U6 review fixes: the requirement-gate bypasses the PR #845 review found.

Each test pins one bypass: an FR list that only looks non-empty, an omitted
intent at F5b, a trunk with no shared history, a missing git binary inside a
repository, a project in a subdirectory, directory names under runtime roots,
runtime prompts labelled ``docs``, a code contradicting its label, a shape
widened by the diff itself, and F11's reading of a recorded ``none``.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from lib import change_type_diff
from lib.change_type_diff import change_type_diff_error, iterate_diff
from lib.change_type_paths import SHAPE_GENERIC, SHAPE_SHIPWRIGHT_MONOREPO, unclassified_paths
from lib.reason_codes import family_codes
from lib.requirement_impact_git import _GitUnavailable, changed_paths
from lib.spec_impact_gate import spec_impact_gate_error, stamp_intent_from_history

_GIT_ENV_ARGS = ["-c", "user.email=u6@example.invalid", "-c", "user.name=u6", "-c", "commit.gpgsign=false"]
_RUN = "iterate-2026-10-08-u6-review-probe"


def _git(root, *args, input_text=None) -> str:
    return subprocess.run(["git", "-C", str(root), *_GIT_ENV_ARGS, *args], check=True,
                          capture_output=True, text=True, input=input_text).stdout.strip()


def _write(root, rel, text="x\n"):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _repo(root, files):
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    for rel in files:
        _write(root, rel)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "checkout", "-q", "-b", "iterate/u6")
    return root


def _event(change_type, **fields):
    return {"type": "work_completed", "source": "iterate", "intent": "change",
            "change_type": change_type, "none_reason": "probe", **fields}


def _seed_entry(root, kind):
    (root / "shipwright_run_config.json").write_text(json.dumps(
        {"iterate_history": [{"run_id": _RUN, "complexity": "small", "type": kind}]}), encoding="utf-8")


# --- 1. an FR list that only looks non-empty ---------------------------------

@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("frs", [[""], [" "], "FR-01.01", ()])
def test_a_hollow_fr_list_does_not_answer_the_spec_impact(frs):
    for key in ("affected_frs", "new_frs"):
        err = spec_impact_gate_error({"type": "work_completed", "source": "iterate", "intent": "bug", key: frs})
        assert err is not None and err["error"] == "spec_impact_unclassified"


# --- 2. F5b takes the intent from the run's own entry ------------------------

@pytest.mark.covers("FR-01.11")
def test_f5b_stamps_the_intent_so_omitting_it_does_not_skip_the_rule(tmp_path):
    from tools import finalize_iterate

    _seed_entry(tmp_path, "bug")
    with pytest.raises(finalize_iterate.FinalizeGateError) as caught:
        finalize_iterate._record_event(tmp_path, "", _RUN, "probe",
                                       {"change_type": "tooling", "none_reason": "ci flake"})
    assert caught.value.code == "spec_impact_unclassified"


@pytest.mark.covers("FR-01.11")
def test_f5b_refuses_an_intent_contradicting_the_entry(tmp_path):
    from tools import finalize_iterate

    _seed_entry(tmp_path, "bug")
    with pytest.raises(finalize_iterate.FinalizeGateError) as caught:
        finalize_iterate._record_event(tmp_path, "", _RUN, "probe", {"intent": "feature", "affected_frs": ["FR-01.01"]})
    assert caught.value.code == "spec_impact_intent_mismatch"


@pytest.mark.covers("FR-01.11")
def test_stamping_leaves_an_event_alone_without_an_entry_and_accepts_a_matching_intent(tmp_path):
    event = {"adr_id": _RUN}
    assert stamp_intent_from_history(event, tmp_path) is None and "intent" not in event
    _seed_entry(tmp_path, "change")
    event = {"adr_id": _RUN, "intent": "CHANGE"}
    assert stamp_intent_from_history(event, tmp_path) is None and event["intent"] == "CHANGE"
    event = {"adr_id": _RUN}
    assert stamp_intent_from_history(event, tmp_path) is None and event["intent"] == "change"


# --- 3. a trunk name that resolves but shares no history ---------------------

@pytest.mark.covers("FR-01.11")
def test_an_orphaned_remote_trunk_refuses_instead_of_falling_back_to_local_main(tmp_path):
    root = _repo(tmp_path, ["src/app.ts", "README.md"])
    orphan = _git(root, "commit-tree", _git(root, "mktree", input_text=""), "-m", "orphan")
    _git(root, "update-ref", "refs/remotes/origin/main", orphan)
    _write(root, "src/app.ts", "changed\n")
    _git(root, "commit", "-qam", "runtime change")
    _git(root, "branch", "-f", "main", "HEAD")  # local trunk AT head would hide the commit
    err = change_type_diff_error(_event("docs"), root, "test")
    assert err is not None and err["error"] == "change_type_diff_unavailable"
    assert "origin/main" in err["detail"]


# --- 4. git binary missing ----------------------------------------------------

def _no_git(*_args, **_kwargs):
    raise _GitUnavailable("git: not found")


@pytest.mark.covers("FR-01.11")
def test_a_missing_git_binary_inside_a_repository_refuses(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    (tmp_path / "proj").mkdir()
    monkeypatch.setattr(change_type_diff, "_is_repo", _no_git)
    err = change_type_diff_error(_event("docs"), tmp_path / "proj", "test")
    assert err is not None and err["error"] == "change_type_diff_unavailable"


@pytest.mark.covers("FR-01.11")
def test_a_missing_git_binary_outside_any_repository_only_warns(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(change_type_diff, "_is_repo", _no_git)
    assert iterate_diff(tmp_path) is None
    assert change_type_diff_error(_event("docs"), tmp_path, "test") is None
    assert "NOT checked against the diff" in capsys.readouterr().err


# --- 5. a project in a subdirectory of a larger repository -------------------

@pytest.mark.covers("FR-01.11")
def test_an_untracked_runtime_file_in_a_subdirectory_project_is_seen(tmp_path):
    _repo(tmp_path, ["proj/README.md", "proj/src/app.ts", "other/x.txt"])
    proj = tmp_path / "proj"
    _write(proj, "src/new_route.ts")
    _write(proj, ".shipwright/planning/01-x/spec.md")
    assert "src/new_route.ts" in iterate_diff(proj)["paths"]
    err = change_type_diff_error(_event("docs"), proj, "test")
    assert err is not None and err["error"] == "change_type_not_covered_by_diff"
    assert "src/new_route.ts" in err["detail"] and "proj/" not in err["detail"]
    assert ".shipwright/planning/01-x/spec.md" in changed_paths(proj, worktree=True)["changed"]


# --- 6. directory names prove nothing under a runtime root; prompts are code --

@pytest.mark.covers("FR-01.11")
def test_runtime_roots_win_over_directory_name_globs():
    assert unclassified_paths(["src/app/docs/page.tsx"], "docs", SHAPE_GENERIC) == ["src/app/docs/page.tsx"]
    assert unclassified_paths(["src/components/sbomPanel.tsx"], "compliance", SHAPE_GENERIC) == [
        "src/components/sbomPanel.tsx"]
    assert unclassified_paths(["app/e2e/helpers.ts", "server/tests/seed.ts"], "tooling", SHAPE_GENERIC) == [
        "app/e2e/helpers.ts", "server/tests/seed.ts"]
    covered = ["src/docs/notes.md", "src/app/Board.test.tsx", "app/e2e/board.spec.ts", "src/README.md",
               "docs/src/example.py", "e2e/fixtures/seed.ts"]
    assert unclassified_paths(covered, "docs", SHAPE_GENERIC) == []


@pytest.mark.covers("FR-01.11")
def test_monorepo_runtime_prompts_are_not_docs_but_stay_tooling():
    prompts = ["plugins/shipwright-iterate/skills/iterate/SKILL.md",
               "plugins/shipwright-build/agents/code-reviewer.md",
               "shared/prompts/code_reviewer.md", "shared/constitution.md"]
    assert unclassified_paths(prompts, "docs", SHAPE_SHIPWRIGHT_MONOREPO) == sorted(prompts)
    assert unclassified_paths(prompts, "tooling", SHAPE_SHIPWRIGHT_MONOREPO) == []
    assert unclassified_paths(["docs/guide.md", "shared/glossary.md"], "docs", SHAPE_SHIPWRIGHT_MONOREPO) == []


# --- 7. a *-only code must agree with its label -------------------------------

def _none_event(code, change_type):
    return _event(change_type, spec_impact="none", spec_impact_justification="probe",
                  spec_impact_reason_code=code)


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("code,change_type", [
    ("docs-only", "tooling"), ("tooling-only", "docs"), ("infra-only", "compliance"), ("compliance-only", "infra"),
])
def test_a_label_code_contradicting_the_change_type_is_refused(code, change_type):
    err = spec_impact_gate_error(_none_event(code, change_type))
    assert err is not None and err["error"] == "spec_impact_reason_code_contradicts_change_type"


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("code,change_type", [
    ("docs-only", "docs"), ("tooling-only", "tooling"), ("infra-only", "infra"),
    ("compliance-only", "compliance"), ("tests-only", "docs"), ("behavior-preserving", "infra"),
    ("restores-specified-behavior", "tooling"), ("docs-only", None),
])
def test_a_consistent_or_label_free_code_passes(code, change_type):
    event = _none_event(code, change_type)
    if change_type is None:
        del event["change_type"]
    assert spec_impact_gate_error(event) is None
    assert "compliance-only" in family_codes("spec_impact_none")


# --- 8. the shape comes from the fork point, not the working tree ------------

@pytest.mark.covers("FR-01.11")
def test_adding_the_monorepo_markers_in_the_diff_does_not_widen_the_labels(tmp_path):
    root = _repo(tmp_path, ["src/app.ts", "README.md"])
    _write(root, ".claude-plugin/marketplace.json", "{}")
    _write(root, "shared/scripts/lib/runtime.py")
    err = change_type_diff_error(_event("tooling"), root, "test")
    assert err is not None and "shared/scripts/lib/runtime.py" in err["detail"]
    assert "project shape generic" in err["detail"]


@pytest.mark.covers("FR-01.11")
def test_markers_present_at_the_fork_point_give_the_monorepo_shape(tmp_path):
    root = _repo(tmp_path, [".claude-plugin/marketplace.json", "shared/scripts/lib/x.py"])
    _write(root, "shared/scripts/lib/x.py", "changed\n")
    assert change_type_diff_error(_event("tooling"), root, "test") is None


# --- 9. F11 reads a recorded none the way the write gate does ----------------

def _f11(tmp_path, entry_type, **event_fields):
    from tools.verifiers.iterate_checks import check_spec_impact_recorded

    (tmp_path / "shipwright_run_config.json").write_text(json.dumps(
        {"iterate_history": [{"run_id": "r1", "complexity": "small", "type": entry_type}]}), encoding="utf-8")
    event = {"type": "work_completed", "source": "iterate", "commit": "abc1234", "adr_id": "r1", **event_fields}
    (tmp_path / "shipwright_events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
    return check_spec_impact_recorded(tmp_path, "r1", "abc1234")


@pytest.mark.covers("FR-01.11")
def test_f11_reads_the_intent_case_insensitively_and_names_bug(tmp_path):
    result = _f11(tmp_path, "BUG", spec_impact="none")
    assert result.ok is False and not result.is_skipped and result.severity == "error"
    assert "bug" in result.name


@pytest.mark.covers("FR-01.11")
def test_f11_warns_when_a_justified_none_carries_no_closed_code(tmp_path):
    result = _f11(tmp_path, "change", spec_impact="none", spec_impact_justification="refactor")
    assert result.ok is False and result.severity == "warning"


@pytest.mark.covers("FR-01.11")
def test_f11_fails_a_justification_that_is_not_one_line(tmp_path):
    result = _f11(tmp_path, "change", spec_impact="none", spec_impact_justification="a" + chr(10) + "b",
                  spec_impact_reason_code="behavior-preserving")
    assert result.ok is False and result.severity == "error"
