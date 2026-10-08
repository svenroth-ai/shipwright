"""U6: a no-FR ``change_type`` is checked against the diff, per project shape.

Diff = merge-base with the trunk to the working tree, untracked files included
(F5b records the event before F6 commits). Mixed diffs, renames, deletions,
unknown paths, a monorepo-shaped and a WebUI-shaped project are each pinned.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from lib.change_type_diff import change_type_diff_error, iterate_diff
from lib.change_type_paths import (
    SHAPE_GENERIC, SHAPE_SHIPWRIGHT_MONOREPO, detect_shape, unclassified_paths,
)
from lib.fr_gates import run_fr_gates

_GIT_ENV_ARGS = ["-c", "user.email=u6@example.invalid", "-c", "user.name=u6", "-c", "commit.gpgsign=false"]


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *_GIT_ENV_ARGS, *args], check=True, capture_output=True)


def _write(root, rel, text="x\n"):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _repo(tmp_path, files, *, branch="main"):
    """A repo with ``files`` committed on ``branch``, then a feature branch checked out."""
    _git(tmp_path, "init", "-q", "-b", branch)
    for rel in files:
        _write(tmp_path, rel)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "checkout", "-q", "-b", "iterate/u6")
    return tmp_path


def _event(change_type, **fields):
    return {"type": "work_completed", "source": "iterate", "intent": "change",
            "change_type": change_type, "none_reason": "probe", **fields}


_WEBUI = ["src/components/Board.tsx", "server/routes.ts", "scripts/build.mjs",
          "e2e/board.spec.ts", "package.json", "README.md"]
_MONO = ["shared/scripts/lib/thing.py", "plugins/shipwright-x/scripts/tool.py",
         "scripts/verify_local.py", ".claude-plugin/marketplace.json", "README.md"]


# --- the pure classification -------------------------------------------------

@pytest.mark.covers("FR-01.11/AC03")
def test_webui_shape_keeps_runtime_code_outside_every_label():
    runtime = ["src/components/Board.tsx", "server/routes.ts", "app/main.py"]
    for change_type in ("docs", "tooling", "infra", "compliance"):
        assert unclassified_paths(runtime, change_type, SHAPE_GENERIC) == sorted(runtime)


@pytest.mark.covers("FR-01.11/AC03")
def test_webui_shape_labels_cover_their_own_paths_plus_docs_tests_and_records():
    common = ["docs/guide.md", "e2e/board.spec.ts", "src/components/Board.test.tsx",
              ".shipwright/agent_docs/iterates/x.json", "shipwright_events.jsonl"]
    assert unclassified_paths(common + ["scripts/build.mjs", "vitest.config.ts"], "tooling", SHAPE_GENERIC) == []
    assert unclassified_paths(common + [".github/workflows/ci.yml", "package.json"], "infra", SHAPE_GENERIC) == []
    assert unclassified_paths(common + ["SECURITY.md", ".gitleaks.toml"], "compliance", SHAPE_GENERIC) == []
    assert unclassified_paths(["docs/a.md", "README.md"], "docs", SHAPE_GENERIC) == []
    assert unclassified_paths(["scripts/build.mjs", "e2e/a.spec.ts"], "docs", SHAPE_GENERIC) == [
        "scripts/build.mjs"]


@pytest.mark.covers("FR-01.11/AC03")
def test_monorepo_shape_tooling_and_infra_are_the_shared_and_top_level_scripts():
    paths = ["shared/scripts/lib/x.py", "scripts/verify_local.py",
             "plugins/shipwright-iterate/skills/iterate/SKILL.md", ".github/workflows/ci.yml"]
    assert unclassified_paths(paths, "tooling", SHAPE_SHIPWRIGHT_MONOREPO) == []
    assert unclassified_paths(paths, "infra", SHAPE_SHIPWRIGHT_MONOREPO) == []
    assert unclassified_paths(["shared/scripts/lib/x.py"], "tooling", SHAPE_GENERIC) == ["shared/scripts/lib/x.py"]
    assert unclassified_paths(["shared/scripts/lib/x.py"], "docs", SHAPE_SHIPWRIGHT_MONOREPO) == [
        "shared/scripts/lib/x.py"]


@pytest.mark.covers("FR-01.11/AC03")
def test_executable_mdx_pages_are_not_docs_but_nested_docs_trees_are():
    assert unclassified_paths(["src/app/page.mdx"], "docs", SHAPE_GENERIC) == ["src/app/page.mdx"]
    assert unclassified_paths(["packages/ui/docs/guide.txt"], "docs", SHAPE_GENERIC) == []


@pytest.mark.covers("FR-01.11/AC03")
def test_unknown_paths_are_refused_and_reported_once():
    assert unclassified_paths(["weird/blob.bin", "./weird/blob.bin", "weird\\blob.bin"], "tooling",
                              SHAPE_GENERIC) == ["weird/blob.bin"]


@pytest.mark.covers("FR-01.11/AC03")
def test_shape_detection(tmp_path):
    assert detect_shape(tmp_path) == SHAPE_GENERIC
    _write(tmp_path, ".claude-plugin/marketplace.json", "{}")
    (tmp_path / "shared" / "scripts").mkdir(parents=True)
    assert detect_shape(tmp_path) == SHAPE_SHIPWRIGHT_MONOREPO


# --- against a real git diff -------------------------------------------------

@pytest.mark.covers("FR-01.11/AC03")
def test_mixed_webui_diff_under_docs_is_refused_naming_only_the_uncovered_paths(tmp_path):
    root = _repo(tmp_path, _WEBUI)
    _write(root, "src/components/Board.tsx", "changed\n")
    _write(root, "docs/new-page.md")  # untracked, covered
    err = change_type_diff_error(_event("docs"), root, "test")
    assert err is not None and err["error"] == "change_type_not_covered_by_diff"
    assert "src/components/Board.tsx" in err["detail"] and "docs/new-page.md" not in err["detail"]


@pytest.mark.covers("FR-01.11/AC03")
def test_an_untracked_runtime_file_is_seen(tmp_path):
    root = _repo(tmp_path, _WEBUI)
    _write(root, "server/new_endpoint.ts")
    assert "server/new_endpoint.ts" in iterate_diff(root)["paths"]
    assert change_type_diff_error(_event("tooling"), root, "test")["error"] == "change_type_not_covered_by_diff"


@pytest.mark.covers("FR-01.11/AC03")
def test_committed_branch_work_is_measured_from_the_fork_point(tmp_path):
    root = _repo(tmp_path, _WEBUI)
    _write(root, "server/routes.ts", "changed\n")
    _git(root, "commit", "-qam", "runtime change")
    assert "server/routes.ts" in change_type_diff_error(_event("infra"), root, "test")["detail"]


@pytest.mark.covers("FR-01.11/AC03")
def test_a_rename_out_of_runtime_code_is_judged_on_both_sides(tmp_path):
    root = _repo(tmp_path, _WEBUI)
    (root / "docs").mkdir()
    _git(root, "mv", "src/components/Board.tsx", "docs/Board.md")
    assert "docs/Board.md" in iterate_diff(root)["paths"]
    err = change_type_diff_error(_event("docs"), root, "test")
    assert err is not None and "src/components/Board.tsx" in err["detail"]


@pytest.mark.covers("FR-01.11/AC03")
def test_a_covered_webui_tooling_change_passes(tmp_path):
    root = _repo(tmp_path, _WEBUI)
    _write(root, "scripts/build.mjs", "changed\n")
    _write(root, "e2e/new.spec.ts")
    assert change_type_diff_error(_event("tooling"), root, "test") is None


@pytest.mark.covers("FR-01.11/AC03")
def test_a_monorepo_tooling_change_to_shared_scripts_passes(tmp_path):
    root = _repo(tmp_path, _MONO)
    _write(root, "shared/scripts/lib/thing.py", "changed\n")
    _write(root, "scripts/verify_local.py", "changed\n")
    assert change_type_diff_error(_event("tooling"), root, "test") is None


@pytest.mark.covers("FR-01.11/AC03")
def test_an_event_naming_an_fr_is_not_using_the_exemption(tmp_path):
    root = _repo(tmp_path, _WEBUI)
    _write(root, "src/components/Board.tsx", "changed\n")
    assert change_type_diff_error(_event("docs", affected_frs=["FR-01.01"]), root, "test") is None


@pytest.mark.covers("FR-01.11/AC03")
def test_not_a_git_repo_warns_and_allows(tmp_path, capsys):
    assert change_type_diff_error(_event("docs"), tmp_path, "test") is None
    assert "NOT checked against the diff" in capsys.readouterr().err


@pytest.mark.covers("FR-01.11/AC03")
def test_no_trunk_ref_fails_closed(tmp_path):
    root = _repo(tmp_path, _WEBUI, branch="develop")
    err = change_type_diff_error(_event("docs"), root, "test")
    assert err is not None and err["error"] == "change_type_diff_unavailable"


@pytest.mark.covers("FR-01.11/AC03")
def test_run_fr_gates_reaches_the_change_type_arm(tmp_path):
    root = _repo(tmp_path, _WEBUI)
    _write(root, "server/routes.ts", "changed\n")
    event = _event("tooling", spec_impact="none", spec_impact_justification="probe",
                   spec_impact_reason_code="tooling-only")
    err = run_fr_gates(event, root, "test")
    assert err is not None and err["error"] == "change_type_not_covered_by_diff"


@pytest.mark.covers("FR-01.11/AC03")
def test_a_project_config_cannot_widen_a_label(tmp_path):
    # No per-project override key exists (architecture review): a glob in the
    # run config changes nothing, so a change cannot exempt itself through it.
    root = _repo(tmp_path, _WEBUI)
    _write(root, "shipwright_run_config.json", json.dumps({"change_type_paths": {"tooling": ["server/**"]}}))
    _write(root, "server/routes.ts", "changed")
    err = change_type_diff_error(_event("tooling"), root, "test")
    assert err is not None and "server/routes.ts" in err["detail"]


@pytest.mark.covers("FR-01.11/AC03")
def test_a_local_main_advanced_to_head_does_not_hide_committed_work(tmp_path):
    root = _repo(tmp_path, _WEBUI)
    fork = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()
    _git(root, "update-ref", "refs/remotes/origin/main", fork)
    _write(root, "server/routes.ts", "changed")
    _git(root, "commit", "-qam", "runtime change")
    _git(root, "branch", "-f", "main", "HEAD")  # local trunk now AT head
    err = change_type_diff_error(_event("infra"), root, "test")
    assert err is not None and "server/routes.ts" in err["detail"] and "origin/main" in err["detail"]
