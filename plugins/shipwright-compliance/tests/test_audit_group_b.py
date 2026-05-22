"""Group B tests (plan v7 Option Z, Step 5) — Sub-Iterate B.

Group B — Config ↔ Config ↔ Event-log coherence:

- B1 (detective, HIGH): project_config.splits[].status="complete" must have
  ≥1 section recorded in plan_config.
- B2 (detective, HIGH): every section recorded in plan_config has a section
  file on disk under .shipwright/planning/<split>/sections/.
- B3 (preventive-rerun, HIGH): test files declared by completed sections
  exist — reuses iterate-12 ``check_build_test_files_exist``.
- B4 (detective, HIGH): every project split with status="complete" has a
  ``split_completed`` event in shipwright_events.jsonl.
- B5 (detective, HIGH): every ``phase_completed`` event has at least one
  matching entry in ``completed_phase_task_ids[]``.
- B6 (preventive-rerun, HIGH): section commit SHAs are reachable in git —
  reuses iterate-12 ``check_commit_sha_in_git``.
- B7 (detective, MEDIUM): every commit on the default branch since the
  last release tag has at least one matching event with that commit.
  Retention rules:
    - Rule A: ignore merge commits
    - Rule B: ignore CI-bot authors
    - Rule C: ignore commits whose entire diff stays within
      ``b7_exclusions.exclude_path_prefixes``
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_b  # noqa: E402
from scripts.audit.audit_adapters import (  # noqa: E402
    SOURCE_DETECTIVE_ONLY,
    SOURCE_PREVENTIVE_RERUN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")


def _events(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _default_config() -> dict:
    return {
        "b7_exclusions": {
            "exclude_merge_commits": True,
            "exclude_authors": ["dependabot[bot]", "github-actions[bot]"],
            "exclude_path_prefixes": ["Spec/", "docs/"],
            "last_release_tag_pattern": "v*",
        },
        "retention": {"rule_a": True, "rule_b": True, "rule_c": True},
    }


# ---------------------------------------------------------------------------
# B1 — splits with status=complete must have sections recorded
# ---------------------------------------------------------------------------


def test_b1_passes_when_complete_split_has_sections(tmp_path):
    _write(tmp_path / "shipwright_project_config.json", json.dumps({
        "splits": [{"name": "01-foo", "status": "complete"}],
    }))
    _write(tmp_path / "shipwright_plan_config.json", json.dumps({
        "splits": {"01-foo": {"status": "complete", "sections": 3}},
    }))
    findings = group_b.run(tmp_path, _default_config(), None)
    b1 = next(f for f in findings if f.check_id == "B1")
    assert b1.status == "pass", b1.detail
    assert b1.source == SOURCE_DETECTIVE_ONLY


def test_b1_flags_complete_split_without_sections(tmp_path):
    _write(tmp_path / "shipwright_project_config.json", json.dumps({
        "splits": [{"name": "01-foo", "status": "complete"}],
    }))
    _write(tmp_path / "shipwright_plan_config.json", json.dumps({
        "splits": {"01-foo": {"status": "complete", "sections": 0}},
    }))
    findings = group_b.run(tmp_path, _default_config(), None)
    b1 = next(f for f in findings if f.check_id == "B1")
    assert b1.status == "fail"
    assert b1.severity == "HIGH"
    assert "01-foo" in b1.detail


def test_b1_flags_complete_split_missing_from_plan_config(tmp_path):
    _write(tmp_path / "shipwright_project_config.json", json.dumps({
        "splits": [{"name": "02-bar", "status": "complete"}],
    }))
    _write(tmp_path / "shipwright_plan_config.json", json.dumps({"splits": {}}))
    findings = group_b.run(tmp_path, _default_config(), None)
    b1 = next(f for f in findings if f.check_id == "B1")
    assert b1.status == "fail"
    assert "02-bar" in b1.detail


def test_b1_skips_when_no_project_config(tmp_path):
    findings = group_b.run(tmp_path, _default_config(), None)
    b1 = next(f for f in findings if f.check_id == "B1")
    assert b1.status == "skip"


def test_b1_treats_negative_int_sections_as_zero(tmp_path):
    """Defensive: a malformed ``sections: -1`` must NOT silently pass B1."""
    _write(tmp_path / "shipwright_project_config.json", json.dumps({
        "splits": [{"name": "01-foo", "status": "complete"}],
    }))
    _write(tmp_path / "shipwright_plan_config.json", json.dumps({
        "splits": {"01-foo": {"sections": -1}},
    }))
    findings = group_b.run(tmp_path, _default_config(), None)
    b1 = next(f for f in findings if f.check_id == "B1")
    assert b1.status == "fail"
    assert "01-foo" in b1.detail


def test_b1_handles_adopted_section_list_shape(tmp_path):
    """Adopted projects use ``sections: []`` (list, not int)."""
    _write(tmp_path / "shipwright_project_config.json", json.dumps({
        "splits": [{"name": "01-adopted", "status": "complete"}],
    }))
    _write(tmp_path / "shipwright_plan_config.json", json.dumps({
        "splits": {"01-adopted": {"status": "complete", "sections": []}},
    }))
    findings = group_b.run(tmp_path, _default_config(), None)
    b1 = next(f for f in findings if f.check_id == "B1")
    # Empty section list on a complete split is an inconsistency.
    assert b1.status == "fail"


# ---------------------------------------------------------------------------
# B2 — plan_config sections → section files on disk
# ---------------------------------------------------------------------------


def test_b2_passes_when_every_recorded_section_has_a_file(tmp_path):
    _write(tmp_path / "shipwright_plan_config.json", json.dumps({
        "splits": {
            "01-foo": {
                "sections": [
                    {"id": "01-init", "name": "Init"},
                    {"id": "02-tests", "name": "Tests"},
                ],
            },
        },
    }))
    _write(tmp_path / ".shipwright" / "planning" / "01-foo" / "sections" / "01-init.md", "Init\n")
    _write(tmp_path / ".shipwright" / "planning" / "01-foo" / "sections" / "02-tests.md", "Tests\n")

    findings = group_b.run(tmp_path, _default_config(), None)
    b2 = next(f for f in findings if f.check_id == "B2")
    assert b2.status == "pass", b2.detail


def test_b2_flags_missing_section_file(tmp_path):
    _write(tmp_path / "shipwright_plan_config.json", json.dumps({
        "splits": {
            "01-foo": {
                "sections": [{"id": "01-init", "name": "Init"}],
            },
        },
    }))
    findings = group_b.run(tmp_path, _default_config(), None)
    b2 = next(f for f in findings if f.check_id == "B2")
    assert b2.status == "fail"
    assert b2.severity == "HIGH"
    assert "01-init" in b2.detail


def test_b2_skips_when_no_plan_config(tmp_path):
    findings = group_b.run(tmp_path, _default_config(), None)
    b2 = next(f for f in findings if f.check_id == "B2")
    assert b2.status == "skip"


def test_b2_handles_glob_metacharacters_in_section_id(tmp_path):
    """Section IDs with ``[`` or ``*`` get glob-escaped so the file
    lookup matches the literal name, not a glob expansion."""
    _write(tmp_path / "shipwright_plan_config.json", json.dumps({
        "splits": {
            "01-foo": {"sections": [{"id": "weird[name]", "name": "Edge"}]},
        },
    }))
    _write(tmp_path / ".shipwright" / "planning" / "01-foo" / "sections" / "weird[name].md", "x\n")
    findings = group_b.run(tmp_path, _default_config(), None)
    b2 = next(f for f in findings if f.check_id == "B2")
    assert b2.status == "pass", b2.detail


def test_b2_skips_when_sections_are_int_count_not_list(tmp_path):
    """Aiportal-shape: ``sections: 8`` (count) doesn't list ids — nothing
    to verify on disk. Skip rather than fail."""
    _write(tmp_path / "shipwright_plan_config.json", json.dumps({
        "splits": {"01-foo": {"sections": 8}},
    }))
    findings = group_b.run(tmp_path, _default_config(), None)
    b2 = next(f for f in findings if f.check_id == "B2")
    assert b2.status == "skip"


# ---------------------------------------------------------------------------
# B3 + B6 — preventive re-run wrappers (tests use fake checks via monkeypatch)
# ---------------------------------------------------------------------------


class _FakeCheck:
    def __init__(self, name, ok, severity="error", detail=""):
        self.name = name
        self.ok = ok
        self.severity = severity
        self.detail = detail


def _patch_iterate12(monkeypatch, mapping):
    """Replace ``import_iterate12_checks`` on group_b with a stub mapping."""
    def _fake():
        return mapping
    monkeypatch.setattr(group_b, "import_iterate12_checks", _fake)


def _passing_iterate12_dict():
    return {
        "check_build_test_files_exist": lambda _r: _FakeCheck(
            "check_build_test_files_exist", ok=True),
        "check_commit_sha_in_git": lambda _r: _FakeCheck(
            "check_commit_sha_in_git", ok=True),
    }


def test_b3_passes_when_iterate12_checker_passes(monkeypatch, tmp_path):
    _patch_iterate12(monkeypatch, _passing_iterate12_dict())
    findings = group_b.run(tmp_path, _default_config(), None)
    b3 = next(f for f in findings if f.check_id == "B3")
    assert b3.status == "pass"
    assert b3.source == SOURCE_PREVENTIVE_RERUN


def test_b3_surfaces_iterate12_failure(monkeypatch, tmp_path):
    mapping = _passing_iterate12_dict()
    mapping["check_build_test_files_exist"] = lambda _r: _FakeCheck(
        "check_build_test_files_exist", ok=False,
        detail="missing test file: src/foo.test.ts",
    )
    _patch_iterate12(monkeypatch, mapping)
    findings = group_b.run(tmp_path, _default_config(), None)
    b3 = next(f for f in findings if f.check_id == "B3")
    assert b3.status == "fail"
    assert "missing test file" in b3.detail


def test_b6_passes_when_iterate12_checker_passes(monkeypatch, tmp_path):
    _patch_iterate12(monkeypatch, _passing_iterate12_dict())
    findings = group_b.run(tmp_path, _default_config(), None)
    b6 = next(f for f in findings if f.check_id == "B6")
    assert b6.status == "pass"
    assert b6.source == SOURCE_PREVENTIVE_RERUN


def test_b6_surfaces_iterate12_failure(monkeypatch, tmp_path):
    mapping = _passing_iterate12_dict()
    mapping["check_commit_sha_in_git"] = lambda _r: _FakeCheck(
        "check_commit_sha_in_git", ok=False,
        detail="commit deadbeef not reachable",
    )
    _patch_iterate12(monkeypatch, mapping)
    findings = group_b.run(tmp_path, _default_config(), None)
    b6 = next(f for f in findings if f.check_id == "B6")
    assert b6.status == "fail"
    assert "deadbeef" in b6.detail


def test_b3_b6_isolate_check_crashes(monkeypatch, tmp_path):
    """One iterate-12 check crashing must not drop the rest of Group B."""
    mapping = _passing_iterate12_dict()
    def boom(_r):
        raise RuntimeError("verifier exploded")
    mapping["check_build_test_files_exist"] = boom
    _patch_iterate12(monkeypatch, mapping)
    findings = group_b.run(tmp_path, _default_config(), None)
    b3 = next(f for f in findings if f.check_id == "B3")
    b6 = next(f for f in findings if f.check_id == "B6")
    assert b3.status == "fail"
    assert "RuntimeError" in b3.detail
    assert b6.status == "pass"  # B6 still runs


# ---------------------------------------------------------------------------
# B4 — completed splits must have split_completed events
# ---------------------------------------------------------------------------


def test_b4_passes_when_every_complete_split_has_event(tmp_path):
    _write(tmp_path / "shipwright_project_config.json", json.dumps({
        "splits": [{"name": "01-foo", "status": "complete"}],
    }))
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "split_completed", "ts": "2026-04-01T00:00:00+00:00",
         "split": "01-foo"},
    ])
    findings = group_b.run(tmp_path, _default_config(), None)
    b4 = next(f for f in findings if f.check_id == "B4")
    assert b4.status == "pass"


def test_b4_flags_complete_split_without_split_completed_event(tmp_path):
    _write(tmp_path / "shipwright_project_config.json", json.dumps({
        "splits": [{"name": "01-foo", "status": "complete"}],
    }))
    _events(tmp_path / "shipwright_events.jsonl", [])
    findings = group_b.run(tmp_path, _default_config(), None)
    b4 = next(f for f in findings if f.check_id == "B4")
    assert b4.status == "fail"
    assert b4.severity == "HIGH"
    assert "01-foo" in b4.detail


def test_b4_skips_when_no_events_jsonl(tmp_path):
    _write(tmp_path / "shipwright_project_config.json", json.dumps({
        "splits": [{"name": "01-foo", "status": "complete"}],
    }))
    findings = group_b.run(tmp_path, _default_config(), None)
    b4 = next(f for f in findings if f.check_id == "B4")
    assert b4.status == "skip"


def test_b4_skips_when_no_complete_splits(tmp_path):
    _write(tmp_path / "shipwright_project_config.json", json.dumps({
        "splits": [{"name": "01-foo", "status": "in_progress"}],
    }))
    _events(tmp_path / "shipwright_events.jsonl", [])
    findings = group_b.run(tmp_path, _default_config(), None)
    b4 = next(f for f in findings if f.check_id == "B4")
    assert b4.status == "skip"


# ---------------------------------------------------------------------------
# B5 — phase_completed events ↔ completed_phase_task_ids
# ---------------------------------------------------------------------------


def test_b5_passes_when_every_phase_completed_event_has_matching_task(tmp_path):
    _write(tmp_path / "shipwright_run_config.json", json.dumps({
        "schemaVersion": 2,
        "phase_tasks": [{"id": "build:01", "phase": "build"}],
        "completed_phase_task_ids": ["build:01"],
    }))
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "phase_completed", "ts": "2026-04-01T00:00:00+00:00",
         "phase": "build"},
    ])
    findings = group_b.run(tmp_path, _default_config(), None)
    b5 = next(f for f in findings if f.check_id == "B5")
    assert b5.status == "pass"


def test_b5_flags_phase_completed_event_without_corresponding_task(tmp_path):
    _write(tmp_path / "shipwright_run_config.json", json.dumps({
        "schemaVersion": 2,
        "phase_tasks": [{"id": "build:01", "phase": "build"}],
        "completed_phase_task_ids": [],
    }))
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "phase_completed", "ts": "2026-04-01T00:00:00+00:00",
         "phase": "build"},
    ])
    findings = group_b.run(tmp_path, _default_config(), None)
    b5 = next(f for f in findings if f.check_id == "B5")
    assert b5.status == "fail"
    assert b5.severity == "HIGH"
    assert "build" in b5.detail


def test_b5_skips_when_run_config_pre_v2(tmp_path):
    """Schema v1 doesn't have phase_tasks — skip rather than fail."""
    _write(tmp_path / "shipwright_run_config.json", json.dumps({"status": "complete"}))
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "phase_completed", "ts": "2026-04-01T00:00:00+00:00",
         "phase": "build"},
    ])
    findings = group_b.run(tmp_path, _default_config(), None)
    b5 = next(f for f in findings if f.check_id == "B5")
    assert b5.status == "skip"


def test_b5_skips_when_no_phase_completed_events(tmp_path):
    _write(tmp_path / "shipwright_run_config.json", json.dumps({
        "schemaVersion": 2,
        "phase_tasks": [{"id": "build:01", "phase": "build"}],
        "completed_phase_task_ids": ["build:01"],
    }))
    _events(tmp_path / "shipwright_events.jsonl", [])
    findings = group_b.run(tmp_path, _default_config(), None)
    b5 = next(f for f in findings if f.check_id == "B5")
    assert b5.status == "skip"


# ---------------------------------------------------------------------------
# B7 — Reverse git scan with retention rules
# ---------------------------------------------------------------------------


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email",
                    "test@example.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name",
                    "Test User"], check=True, capture_output=True)


def _git_commit(repo: Path, files: dict[str, str], msg: str,
                author: str | None = None) -> str:
    """Commit *files* with *msg*. Returns the commit SHA."""
    for path, content in files.items():
        full = repo / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True,
                   capture_output=True)
    env = None
    if author:
        env = {
            "GIT_AUTHOR_NAME": author,
            "GIT_AUTHOR_EMAIL": f"{author}@example.com",
            "GIT_COMMITTER_NAME": author,
            "GIT_COMMITTER_EMAIL": f"{author}@example.com",
            "PATH": os.environ.get("PATH", ""),
        }
    subprocess.run(["git", "-C", str(repo), "commit", "-m", msg], check=True,
                   capture_output=True, env=env)
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                         check=True, capture_output=True, text=True).stdout.strip()
    return sha


def _git_tag(repo: Path, tag: str) -> None:
    subprocess.run(["git", "-C", str(repo), "tag", tag], check=True,
                   capture_output=True)


def test_b7_passes_when_every_post_release_commit_has_an_event(tmp_path):
    _git_init(tmp_path)
    sha0 = _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    sha1 = _git_commit(tmp_path, {"a.txt": "v2"}, "feat: thing")

    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "commit": sha1},
    ])
    findings = group_b.run(tmp_path, _default_config(), None)
    b7 = next(f for f in findings if f.check_id == "B7")
    assert b7.status == "pass", b7.detail


def test_b7_flags_uncovered_commit(tmp_path):
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    sha1 = _git_commit(tmp_path, {"a.txt": "v2"}, "feat: untracked")

    _events(tmp_path / "shipwright_events.jsonl", [])
    findings = group_b.run(tmp_path, _default_config(), None)
    b7 = next(f for f in findings if f.check_id == "B7")
    assert b7.status == "fail"
    assert b7.severity == "MEDIUM"
    assert sha1[:8] in b7.detail


def test_b7_excludes_ci_bot_authors(tmp_path):
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    _git_commit(tmp_path, {"deps.txt": "x"}, "chore: bump deps",
                author="dependabot[bot]")

    _events(tmp_path / "shipwright_events.jsonl", [])
    findings = group_b.run(tmp_path, _default_config(), None)
    b7 = next(f for f in findings if f.check_id == "B7")
    assert b7.status == "pass", b7.detail


def test_b7_excludes_docs_only_commits(tmp_path):
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    _git_commit(tmp_path, {"docs/intro.md": "hi"}, "docs: add intro")

    _events(tmp_path / "shipwright_events.jsonl", [])
    findings = group_b.run(tmp_path, _default_config(), None)
    b7 = next(f for f in findings if f.check_id == "B7")
    assert b7.status == "pass", b7.detail


def test_b7_does_not_exclude_mixed_docs_and_code_commits(tmp_path):
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    sha1 = _git_commit(tmp_path,
                       {"docs/intro.md": "hi", "src/foo.ts": "x"},
                       "feat: mixed")

    _events(tmp_path / "shipwright_events.jsonl", [])
    findings = group_b.run(tmp_path, _default_config(), None)
    b7 = next(f for f in findings if f.check_id == "B7")
    assert b7.status == "fail"
    assert sha1[:8] in b7.detail


def test_b7_matches_abbreviated_sha_in_event_log(tmp_path):
    """Hand-edited event logs sometimes record abbreviated SHAs (8-12
    hex chars). B7 should accept those as matches, not flood the
    finding with every commit reported as uncovered."""
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    full_sha = _git_commit(tmp_path, {"a.txt": "v2"}, "feat: thing")
    abbrev = full_sha[:10]
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "commit": abbrev},
    ])
    findings = group_b.run(tmp_path, _default_config(), None)
    b7 = next(f for f in findings if f.check_id == "B7")
    assert b7.status == "pass", b7.detail


def test_b7_rejects_abbreviated_sha_shorter_than_7_chars(tmp_path):
    """Prefixes shorter than 7 hex chars are too ambiguous and must be
    rejected to prevent false-positive matches."""
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    full_sha = _git_commit(tmp_path, {"a.txt": "v2"}, "feat: thing")
    too_short = full_sha[:6]
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "commit": too_short},
    ])
    findings = group_b.run(tmp_path, _default_config(), None)
    b7 = next(f for f in findings if f.check_id == "B7")
    assert b7.status == "fail"


def test_b7_skips_when_no_release_tag_present(tmp_path):
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    findings = group_b.run(tmp_path, _default_config(), None)
    b7 = next(f for f in findings if f.check_id == "B7")
    assert b7.status == "skip"
    assert "release tag" in b7.detail.lower()


def test_b7_skips_when_not_a_git_repo(tmp_path):
    findings = group_b.run(tmp_path, _default_config(), None)
    b7 = next(f for f in findings if f.check_id == "B7")
    assert b7.status == "skip"


def test_b7_disabling_rule_b_re_includes_dependabot_commits(tmp_path):
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    sha1 = _git_commit(tmp_path, {"deps.txt": "x"}, "chore: bump deps",
                       author="dependabot[bot]")
    _events(tmp_path / "shipwright_events.jsonl", [])

    config = _default_config()
    config["retention"]["rule_b"] = False
    findings = group_b.run(tmp_path, config, None)
    b7 = next(f for f in findings if f.check_id == "B7")
    assert b7.status == "fail"
    assert sha1[:8] in b7.detail


# ---------------------------------------------------------------------------
# End-to-end through the detector + registry
# ---------------------------------------------------------------------------


def test_registry_wires_b_alongside_a_c_d_f(tmp_path):
    from scripts.audit import audit_detector
    from scripts.audit._registry import register_all
    register_all()
    registered = set(audit_detector.registered_groups().keys())
    # Sub-Iterate C wired E + G; the registry now covers all of A..G.
    assert registered == {"A", "B", "C", "D", "E", "F", "G"}


def test_group_b_findings_include_correct_sources(monkeypatch, tmp_path):
    """B1/B2/B4/B5/B7 = detective-only; B3/B6 = preventive-rerun."""
    _patch_iterate12(monkeypatch, _passing_iterate12_dict())
    findings = group_b.run(tmp_path, _default_config(), None)
    by_id = {f.check_id: f for f in findings}
    for cid in ("B1", "B2", "B4", "B5", "B7"):
        assert by_id[cid].source == SOURCE_DETECTIVE_ONLY, cid
    for cid in ("B3", "B6"):
        assert by_id[cid].source == SOURCE_PREVENTIVE_RERUN, cid
