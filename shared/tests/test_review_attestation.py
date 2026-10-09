"""3f-bis may skip its re-review only on rows it can verify against git.

Covers the runner's ``--verdict`` / ``--reviewed-commit`` row fields, the schema
guard on them, and ``review_attested.py`` (``lib.review_attestation``): attested
only for a ``pass`` at a ``reviewed_commit`` that is current -- the merged head
adds nothing but non-code artifacts.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _review_cli_harness import RUN_ID, make_project, run_tool  # noqa: E402

TOOL = str(Path(__file__).resolve().parents[1] / "scripts" / "tools" / "review_attested.py")
pytestmark = pytest.mark.covers("FR-01.11")

SPEC_REPLY = json.dumps({"stage": "spec", "verdict": "pass", "spec_citations": []})
CODE_REPLY = json.dumps({"section": "x", "review": []})


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                           *args], capture_output=True, text=True, check=True).stdout.strip()


def _commit(repo: Path, rel: str, text: str) -> str:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", f"change {rel}")
    return _git(repo, "rev-parse", "HEAD")


def _record(project: Path, review_type: str, reply: str, *flags: str) -> None:
    payload = project.parent / "payloads" / f"{review_type}_review_reply.json"
    payload.parent.mkdir(exist_ok=True)
    payload.write_text(reply, encoding="utf-8")
    rc, out = run_tool(project, "record", "--review-type", review_type, "--status", "completed",
                       "--from", f"{review_type}-reviewer", "--payload-file", str(payload),
                       "--recorded-by", f"{review_type}-reviewer", *flags)
    assert rc == 0, out


def _seal(project: Path, head: str) -> str:
    """Commit any unsealed record (the runner's F6 does) and resolve ``HEAD``."""
    if not (project / ".git").exists():
        return head
    if _git(project, "status", "--porcelain"):
        _git(project, "add", "-A")
        _git(project, "commit", "-qm", "seal review record")
    return _git(project, "rev-parse", "HEAD") if head == "HEAD" else head


def _attested(project: Path, head: str) -> dict:
    head = _seal(project, head)
    out = subprocess.run([sys.executable, TOOL, "--project-root", str(project), "--run-id", RUN_ID,
                          "--head", head, "--diff-lines", "40"], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@pytest.fixture
def unit(tmp_path: Path):
    project = make_project(tmp_path / "repo")
    _git(project, "init", "-q")
    reviewed = _commit(project, "src/app.py", "x = 1\n")
    rc, out = run_tool(project, "init")
    assert rc == 0, out
    return project, reviewed


def _record_passing_cascade(project: Path, commit: str) -> None:
    flags = ("--verdict", "pass", "--reviewed-commit", commit)
    _record(project, "spec", SPEC_REPLY, *flags)
    _record(project, "code", CODE_REPLY, *flags)
    rc, out = run_tool(project, "record", "--review-type", "doubt", "--status", "not_applicable",
                       "--reason-code", "diff-below-threshold", "--disposition",
                       "Stage 3 is conditional and did not trigger for this diff")
    assert rc == 0, out


def test_attested_when_only_artifacts_changed_after_the_review(unit):
    project, reviewed = unit
    _record_passing_cascade(project, reviewed)
    head = _commit(project, ".shipwright/planning/iterate/x/notes.md", "n\n")
    head = _commit(project, "CHANGELOG-unreleased.d/fixed/x.md", "- x\n")
    assert _attested(project, head)["attested"] is True


def test_not_attested_when_code_changed_after_the_review(unit):
    project, reviewed = unit
    _record_passing_cascade(project, reviewed)
    head = _commit(project, "src/app.py", "x = 2\n")
    result = _attested(project, head)
    assert result["attested"] is False and "src/app.py" in result["reason"]


def test_not_attested_for_a_legacy_row_without_the_pair(unit):
    project, reviewed = unit
    _record(project, "spec", SPEC_REPLY)
    _record(project, "code", CODE_REPLY)
    result = _attested(project, "HEAD")
    assert result["attested"] is False and "not a completed pass" in result["reason"]


def test_not_attested_for_a_commit_that_is_not_an_ancestor(unit):
    project, reviewed = unit
    _git(project, "checkout", "-q", "-b", "other")
    other = _commit(project, "src/other.py", "y = 1\n")
    _git(project, "checkout", "-q", "-")
    _record_passing_cascade(project, other)
    result = _attested(project, "HEAD")
    assert result["attested"] is False and "not an ancestor" in result["reason"]


def test_not_attested_for_a_garbage_head_or_missing_record(tmp_path):
    project = make_project(tmp_path / "repo")
    assert _attested(project, "not-a-sha")["attested"] is False
    assert _attested(project, "a" * 40)["attested"] is False


def test_schema_rejects_a_short_sha_and_a_completed_reject(unit):
    project, reviewed = unit
    for flags in (("--reviewed-commit", "abc123"), ("--verdict", "reject")):
        rc, out = run_tool(project, "record", "--review-type", "spec", "--status", "completed",
                           "--recorded-by", "spec-reviewer", *flags)
        assert rc != 0, out


def test_3f_bis_and_the_runner_are_wired_to_the_attestation():
    iterate = Path(__file__).resolve().parents[2] / "plugins" / "shipwright-iterate"
    mode = (iterate / "skills/iterate/references/campaign-mode.md").read_text(encoding="utf-8")
    runner = (iterate / "agents/sub-iterate-runner.md").read_text(encoding="utf-8")
    ref = (iterate / "skills/iterate/references/campaign-step-3-7-internal-reviews.md"
           ).read_text(encoding="utf-8")
    # 3f-bis lowers `fires` in exactly one place, and only behind the verified answer ...
    att = [ln for ln in mode.splitlines() if "review_attested.py" in ln and "jq -r .attested" in ln]
    lowering = [ln for ln in mode.splitlines() if ln.strip().endswith('echo 0 > "$run_dir/fires"')]
    assert len(att) == 1 and "--diff-lines" in att[0]
    assert len(lowering) == 1 and '[ "$was" = 1 ]' in lowering[0] and '[ "$att" = true ]' in lowering[0]
    # ... after the mechanical 100-line floor and the fires write have had their say ...
    assert (mode.index('[ "$diff_lines" -gt 100 ] && fires=1')
            < mode.index('echo "$fires" > "$run_dir/fires"') < mode.index("review_attested.py\" --project-root"))
    # ... and the runner records the pair that answer needs.
    assert "--verdict pass --reviewed-commit" in runner and "--verdict pass --reviewed-commit" in ref


def test_the_documented_row_commands_have_no_literal_backslash_n():
    """A literal ``\n`` in the copied command became a stray positional argument."""
    iterate = Path(__file__).resolve().parents[2] / "plugins" / "shipwright-iterate"
    text = (iterate / "skills/iterate/references/iteration-reviews.md").read_text(encoding="utf-8")
    assert not [ln for ln in text.splitlines() if "--model-tier" in ln and chr(92) + "n" in ln]


def test_a_rename_of_reviewed_code_into_an_artifact_path_is_not_attested(unit):
    project, reviewed = unit
    _record_passing_cascade(project, reviewed)
    _git(project, "add", "-A")
    _git(project, "mv", "src/app.py", ".shipwright/moved.py")
    _git(project, "commit", "-qm", "move code into an artifact path")
    result = _attested(project, _git(project, "rev-parse", "HEAD"))
    assert result["attested"] is False and "src/app.py" in result["reason"]


def _attested_at(project: Path, head: str, lines: int) -> dict:
    head = _seal(project, head)
    out = subprocess.run([sys.executable, TOOL, "--project-root", str(project), "--run-id", RUN_ID,
                          "--head", head, "--diff-lines", str(lines)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_doubt_must_have_completed_when_the_diff_is_over_the_floor(unit):
    project, reviewed = unit
    _record_passing_cascade(project, reviewed)
    assert _attested_at(project, "HEAD", 40)["attested"] is True
    big = _attested_at(project, "HEAD", 400)
    assert big["attested"] is False and "doubt" in big["reason"]
    unknown = subprocess.run([sys.executable, TOOL, "--project-root", str(project), "--run-id", RUN_ID,
                              "--head", _seal(project, "HEAD")], capture_output=True, text=True, check=True).stdout
    assert json.loads(unknown)["attested"] is False, "an unknown size is not small"


def test_a_completed_doubt_pass_is_attested_and_a_stale_one_is_not(unit):
    project, reviewed = unit
    flags = ("--verdict", "pass", "--reviewed-commit", reviewed)
    _record(project, "spec", SPEC_REPLY, *flags)
    _record(project, "code", CODE_REPLY, *flags)
    _record(project, "doubt", json.dumps({"stage": "doubt", "gating": "advisory-must-address",
                                          "trigger": "io-boundary", "doubts": []}), *flags)
    assert _attested_at(project, "HEAD", 400)["attested"] is True
    head = _commit(project, "src/app.py", "x = 3\n")
    stale = _attested_at(project, head, 400)
    assert stale["attested"] is False and "src/app.py" in stale["reason"]


def test_a_completed_doubt_recorded_by_someone_else_is_not_attested(unit):
    project, reviewed = unit
    flags = ("--verdict", "pass", "--reviewed-commit", reviewed)
    _record(project, "spec", SPEC_REPLY, *flags)
    _record(project, "code", CODE_REPLY, *flags)
    payload = project.parent / "payloads" / "doubt_review_reply.json"
    payload.write_text(json.dumps({"stage": "doubt", "gating": "advisory-must-address",
                                   "trigger": "io-boundary", "doubts": []}), encoding="utf-8")
    rc, out = run_tool(project, "record", "--review-type", "doubt", "--status", "completed",
                       "--from", "doubt-reviewer", "--payload-file", str(payload),
                       "--recorded-by", "someone-else", *flags)
    assert rc == 0, out
    assert "doubt was not recorded from doubt-reviewer" in _attested_at(project, "HEAD", 400)["reason"]


def test_a_row_recorded_by_someone_else_is_not_attested(unit):
    project, reviewed = unit
    flags = ("--verdict", "pass", "--reviewed-commit", reviewed)
    _record(project, "spec", SPEC_REPLY, *flags)
    payload = project.parent / "payloads" / "code_review_reply.json"
    payload.write_text(CODE_REPLY, encoding="utf-8")
    rc, out = run_tool(project, "record", "--review-type", "code", "--status", "completed",
                       "--from", "code-reviewer", "--payload-file", str(payload),
                       "--recorded-by", "someone-else", *flags)
    assert rc == 0, out
    assert "was not recorded from code-reviewer" in _attested_at(project, "HEAD", 10)["reason"]


def test_a_row_written_after_the_last_commit_is_not_attested(unit):
    project, reviewed = unit
    _git(project, "add", "-A")
    _git(project, "commit", "-qm", "record skeleton")
    head = _git(project, "rev-parse", "HEAD")
    _record_passing_cascade(project, reviewed)  # written, never committed
    result = json.loads(subprocess.run(
        [sys.executable, TOOL, "--project-root", str(project), "--run-id", RUN_ID, "--head", head,
         "--diff-lines", "40"], capture_output=True, text=True, check=True).stdout)
    assert result["attested"] is False and "not a completed pass" in result["reason"]


def test_a_script_or_gate_input_under_the_artifact_tree_counts_as_code(unit):
    project, reviewed = unit
    _record_passing_cascade(project, reviewed)
    for rel in (".shipwright/planning/iterate/x/run.py", ".shipwright/planning/adr/y-bloat-exception.md"):
        head = _commit(project, rel, "x\n")
        result = _attested(project, head)
        assert result["attested"] is False and rel in result["reason"], rel


def test_a_pass_row_carrying_a_high_finding_is_not_attested(unit):
    project, reviewed = unit
    flags = ("--verdict", "pass", "--reviewed-commit", reviewed)
    _record(project, "spec", SPEC_REPLY, *flags)
    high = json.dumps({"section": "x", "review": [{"severity": "high", "category": "correctness",
                       "file": "a.py", "line": 1, "finding": "boom", "suggestion": "fix"}]})
    _record(project, "code", high, *flags)
    result = _attested(project, "HEAD")
    assert result["attested"] is False and "high-severity" in result["reason"]
