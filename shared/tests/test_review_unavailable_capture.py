"""U10 hardening: what counts as the adapter's captured failure, and what does not.

An envelope must carry the adapter's ``review_schema``, say why it failed
(``error`` / ``degraded_reason``) and name a ``mode`` the pass runs; stderr
counts only beside an existing raw file; a symlinked capture is refused in the
working tree and in a commit; a reply whose every leg was ``skipped`` is not
"the review could not run". The last test builds the capture from the REAL
producers instead of hand-written JSON.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_SCRIPTS / "tools"))

from test_hygiene import is_ci  # noqa: E402
from lib.external_review_degraded import finalize_review_output  # noqa: E402
from lib.review_record import REVIEW_TYPES, make_entry, new_record, upsert_review, write_record  # noqa: E402
from lib.review_unavailable import artifact_paths, artifact_problem, worktree_reader  # noqa: E402
from tools.verifiers.review_record_check import check_review_record  # noqa: E402

RUN = "iterate-2026-10-08-capture"


STAMP = {"run_id": RUN, "at": "2026-10-08T00:00:00+00:00"}  # what external_review.py --run-id writes


def _env(**fields) -> str:
    return json.dumps({"review_schema": 2, "success": False, "error": "boom", "mode": "code",
                       "capture": STAMP, **fields})


def _problem(raw: str | None, err: str | None = None, review_type: str = "external_code") -> str | None:
    raw_rel, err_rel = artifact_paths(RUN, review_type)
    files = {raw_rel: raw, err_rel: err}
    return artifact_problem(RUN, review_type, lambda rel: None if files.get(rel) is None
                            else files[rel].encode("utf-8"))[0]


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize(("raw", "err", "review_type", "needle"), [
    (json.dumps({"success": False}), "uv: failed", "external_code", "review_schema"),  # bare: not the adapter's
    (_env(review_schema=1), None, "external_code", "review_schema"),
    (_env(error=""), None, "external_code", "names no failure"),
    (_env(error=None), None, "external_code", "names no failure"),
    (_env(mode=None), None, "external_code", "--mode None"),           # no provenance
    (_env(mode="architecture"), None, "external_code", "--mode architecture"),
    (_env(), None, "plan", "--mode code"),                              # a code envelope cannot back `plan`
    (_env(capture=None), None, "external_code", "no capture stamp"),     # typed by hand / predates the stamp
    (_env(capture={"run_id": "iterate-2026-10-08-other", "at": STAMP["at"]}), None, "external_code",
     "no capture stamp"),                                                # copied from another run's directory
    (_env(capture={"run_id": RUN, "at": "yesterday"}), None, "external_code", "no capture stamp"),
    (_env(capture={"run_id": RUN}), None, "external_code", "no capture stamp"),
    (None, "Traceback (most recent call last)", "external_code", "no captured adapter error"),
])
def test_capture_is_refused_unless_it_is_this_pass_s_adapter_failure(raw, err, review_type, needle):
    problem = _problem(raw, err, review_type)
    assert problem and needle in problem, problem


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize(("raw", "review_type"), [
    (_env(), "external_code"),
    (_env(mode="iterate"), "plan"),
    (_env(mode="plan"), "plan"),
    (_env(error=None, degraded=True, degraded_reason="0/2 reviews succeeded"), "external_code"),
])
def test_capture_is_accepted_when_it_is_this_pass_s_adapter_failure(raw, review_type):
    assert _problem(raw, None, review_type) is None


@pytest.mark.covers("FR-01.11")
def test_a_reply_whose_every_leg_was_skipped_is_missing_keys_not_unavailable():
    skipped = json.dumps({"review_schema": 2, "success": True, "degraded": False, "mode": "code",
                          "reviews_succeeded": 0, "reviews": {
                              "glm": {"status": "skipped", "reason": "No OPENROUTER_API_KEY set"},
                              "openai": {"status": "skipped", "reason": "No OPENAI_API_KEY set"}}})
    problem = _problem(skipped, "warning: no keys")
    assert problem and "`skipped`" in problem and "missing-keys" in problem, problem


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as exc:
        if is_ci():
            pytest.fail(f"symlinks must work on CI ({exc})", pytrace=False)
        pytest.skip(f"this platform cannot create symlinks here ({exc})")


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("which", ["raw", "stderr"])
def test_a_symlinked_capture_in_the_working_tree_is_refused(tmp_path, which):
    raw_rel, err_rel = artifact_paths(RUN, "external_code")
    elsewhere = tmp_path / "elsewhere.txt"
    elsewhere.write_text(_env() if which == "raw" else "Traceback: boom", encoding="utf-8")
    (tmp_path / raw_rel).parent.mkdir(parents=True)
    if which == "raw":
        _symlink_or_skip(tmp_path / raw_rel, elsewhere)
    else:
        (tmp_path / raw_rel).write_text("", encoding="utf-8")
        _symlink_or_skip(tmp_path / err_rel, elsewhere)
    problem, _ = artifact_problem(RUN, "external_code", worktree_reader(tmp_path))
    assert problem and "symlink" in problem, problem


def _git(root: Path, *args: str, stdin: str | None = None) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                          text=True, input=stdin).stdout.strip()


@pytest.mark.covers("FR-01.11")
def test_a_symlinked_capture_in_the_commit_is_refused(tmp_path):
    """A fabricated tree: mode 120000 needs no filesystem symlink support."""
    iterates = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    iterates.mkdir(parents=True)
    (iterates / f"{RUN}.json").write_text(json.dumps({
        "run_id": RUN, "type": "change", "complexity": "small", "branch": "iterate/x",
        "tests_passed": True, "date": "2026-10-08T00:00:00+00:00"}), encoding="utf-8")
    record = new_record(RUN)
    for review_type in REVIEW_TYPES:
        if review_type == "self":
            entry = make_entry("self", "completed", recorded_by="self-review")
        else:
            entry = make_entry(review_type, "not_run", disposition="not at this complexity")
            entry["reason_code"] = "unavailable" if review_type == "external_code" else "diff-below-threshold"
        record = upsert_review(record, entry, force=True)
    write_record(tmp_path, RUN, record)
    raw_rel, err_rel = artifact_paths(RUN, "external_code")
    (tmp_path / raw_rel).write_text("", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".shipwright")
    oid = _git(tmp_path, "hash-object", "-w", "--stdin", stdin="../../../../elsewhere.txt")
    _git(tmp_path, "update-index", "--add", "--cacheinfo", f"120000,{oid},{err_rel}")
    _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c")
    head = _git(tmp_path, "rev-parse", "HEAD")
    result = check_review_record(tmp_path, RUN, head)
    assert result.ok is False and "not a regular file" in result.detail, result.detail


@pytest.mark.covers("FR-01.11")
def test_captures_built_by_the_real_producers(monkeypatch, capsys, tmp_path):
    """``finalize_review_output`` (all legs errored) and ``main()``'s ``_fail_envelope`` both back
    the claim; a ``finalize_review_output`` success refuses it."""
    import external_review

    failed, _ = finalize_review_output("openrouter", {
        "glm": {"status": "error", "reason": "401"}, "openai": {"status": "error", "reason": "timeout"}})
    succeeded, _ = finalize_review_output("openrouter", {"glm": {"status": "success", "feedback": "ok"}})
    for output in (failed, succeeded):
        output["mode"] = "code"  # main() merges driver_record (which carries `--mode`) into every envelope
        output["capture"] = STAMP  # ... and the capture stamp
    assert _problem(json.dumps(failed)) is None
    assert "not a failure envelope" in (_problem(json.dumps(succeeded)) or "")

    spec = tmp_path / "spec.md"
    spec.write_text("# Spec", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["external_review.py", "--mode", "code", "--diff-file",
                                     str(tmp_path / "absent.diff"), "--spec-file", str(spec),
                                     "--plugin-root", str(tmp_path), "--run-id", RUN, "--driver", "claude"])
    assert external_review.main() == 1
    assert _problem(capsys.readouterr().out) is None
