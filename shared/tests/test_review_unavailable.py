"""U10: an adapter-backed review closed ``unavailable`` must show the adapter's error.

``unavailable`` claims the reviewer could not run. For ``plan`` and
``external_code`` — the passes ``external_review.py`` produces — F11's
review-record check now asks for the adapter's own captured failure (its stdout
envelope, or its stderr when it died before printing JSON), read from the commit
when the record is committed. A passing check still names every pass that did not
run, so the gap is loud.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.review_record import REVIEW_TYPES, make_entry, new_record, upsert_review, write_record  # noqa: E402
from lib.review_unavailable import artifact_paths, artifact_problem  # noqa: E402
from tools.verifiers.review_record_check import check_review_record  # noqa: E402

RUN = "iterate-2026-10-08-unavailable"
WHY = "the phase matrix does not run this pass at this complexity"
STAMP = {"capture": {"run_id": RUN, "at": "2026-10-08T00:00:00+00:00"}}  # what external_review.py --run-id writes
FAILED = json.dumps({"review_schema": 2, "success": False, "error": "no provider answered", "mode": "code", **STAMP})
DEGRADED = json.dumps({"review_schema": 2, "success": False, "degraded": True, "mode": "code", **STAMP,
                       "degraded_reason": "provider=openrouter but 0/2 reviews succeeded", "reviews": {}})
SUCCEEDED = json.dumps({"review_schema": 2, "success": True, "degraded": False, "mode": "code", "reviews": {}})
CAMPAIGN_BRANCH = "iterate/campaign-2026-10-07-finalization-claims-hardening--U10"


def _reader(files: dict[str, str | bytes]):
    def read(rel: str) -> bytes | None:
        value = files.get(rel)
        return value.encode("utf-8") if isinstance(value, str) else value
    return read


def _capture(raw: str | bytes | None = None, err: str | bytes | None = None,
             review_type: str = "external_code") -> dict:
    raw_rel, err_rel = artifact_paths(RUN, review_type)
    return {k: v for k, v in ((raw_rel, raw), (err_rel, err)) if v is not None}


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize(("raw", "err", "ok"), [
    (FAILED, None, True),                    # the adapter's own failure envelope
    (DEGRADED, None, True),                  # keys present, no reviewer answered
    ("", "error: Failed to spawn: uv", True),  # `uv run` died before any JSON
    (None, "Traceback (most recent call last)", False),  # stderr counts only beside an existing raw file
    (SUCCEEDED, "warning: slow provider", False),  # the review DID run: stderr cannot rescue the claim
    ("calling provider...", None, False),    # stray non-JSON stdout alone proves nothing
    ("", "   \n", False),                    # whitespace is not a capture
    (None, None, False),                     # nothing captured at all
    # Boundary probes (confidence calibration): the decoder must not misread the reply.
    (SUCCEEDED.encode("utf-16"), "warn", False),   # PowerShell 5.1 `>` writes UTF-16 with a BOM
    (FAILED.encode("utf-16"), None, True),
    (SUCCEEDED + "\nnote: done", "warn", False),  # stray text after a successful reply
    ("hi\r\n" + SUCCEEDED, "warn", False),       # stray text (CRLF) before it
    ("hi\r\n" + FAILED, None, True),
    (SUCCEEDED[:10], "killed", True),             # truncated reply: stderr is the evidence
])
def test_the_capture_decides_whether_unavailable_is_backed(raw, err, ok):
    problem, _ = artifact_problem(RUN, "external_code", _reader(_capture(raw, err)))
    assert (problem is None) is ok, problem


def _project(tmp_path: Path, complexity: str = "small", branch: str = "iterate/x", spec: str | None = None) -> Path:
    d = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{RUN}.json").write_text(json.dumps({
        "run_id": RUN, "type": "change", "complexity": complexity, "branch": branch, "spec": spec,
        "tests_passed": True, "date": "2026-10-08T00:00:00+00:00"}), encoding="utf-8")
    return tmp_path


def _record(root: Path, overrides: dict[str, str | None]) -> None:
    """`self` completed; every other type closed with a code; ``overrides`` maps type → code."""
    record = new_record(RUN)
    for review_type in REVIEW_TYPES:
        if review_type == "self":
            entry = make_entry("self", "completed", recorded_by="self-review")
        else:
            entry = make_entry(review_type, "not_run", disposition=WHY)
            code = overrides.get(review_type, "diff-below-threshold")
            if code is not None:
                entry["reason_code"] = code
        record = upsert_review(record, entry, force=True)
    write_record(root, RUN, record)


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


@pytest.mark.covers("FR-01.11")
def test_gate_refuses_an_external_pass_closed_unavailable_without_a_capture(tmp_path):
    root = _project(tmp_path)
    _record(root, {"external_code": "unavailable"})
    result = check_review_record(root, RUN)
    assert result.ok is False
    assert "`external_code`" in result.detail and "captured error" in result.detail


@pytest.mark.covers("FR-01.11")
def test_gate_accepts_a_captured_failure_and_still_says_the_review_did_not_run(tmp_path):
    root = _project(tmp_path)
    _record(root, {"external_code": "unavailable", "plan": "unavailable"})
    _write(root, {**_capture(FAILED), **_capture("", "uv: command failed", "plan")})
    result = check_review_record(root, RUN)
    assert result.ok is True, result.detail
    assert "did NOT run (unavailable): plan, external_code" in result.detail


@pytest.mark.covers("FR-01.11")
def test_gate_leaves_unavailable_on_an_internal_pass_to_its_own_rules(tmp_path):
    """No adapter, nothing to capture: the internal rows keep their pre-U10 semantics."""
    root = _project(tmp_path)
    _record(root, {"code": "unavailable"})
    result = check_review_record(root, RUN)
    assert result.ok is True, result.detail
    assert "did NOT run (unavailable): code" in result.detail


@pytest.mark.covers("FR-01.11")
def test_gate_refuses_a_bare_not_run_on_the_external_pass(tmp_path):
    root = _project(tmp_path)
    _record(root, {"external_code": None})
    result = check_review_record(root, RUN)
    assert result.ok is False and "external_code" in result.detail and "reason_code" in result.detail


@pytest.mark.covers("FR-01.11")
def test_a_retry_that_succeeded_overwrites_the_failure_and_refuses_the_claim(tmp_path):
    """Both redirects truncate per call, so the artifact speaks for the LAST attempt."""
    root = _project(tmp_path)
    _record(root, {"external_code": "unavailable"})
    _write(root, _capture(FAILED))
    assert check_review_record(root, RUN).ok is True
    _write(root, _capture(SUCCEEDED))  # the retry's `>` truncated the failure away
    result = check_review_record(root, RUN)
    assert result.ok is False and "not a failure envelope" in result.detail


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize(("code", "ok"), [
    ("delegated-to-orchestrator", True),   # campaign runner: 3f-bis promotes `code` before any merge
    ("user-opt-out", False),               # nobody will run it: the medium floor still refuses
])
def test_medium_floor_waits_for_the_delegated_cascade_only_when_external_was_unavailable(tmp_path, code, ok):
    root = _project(tmp_path, "medium", branch=CAMPAIGN_BRANCH)
    _record(root, {"external_code": "unavailable", "code": code})
    _write(root, _capture(FAILED))
    result = check_review_record(root, RUN)
    assert result.ok is ok, result.detail
    assert ok or "no code review ran" in result.detail


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize(("branch", "spec", "ok"), [
    ("iterate/some-feature", None, False),  # not a campaign: nobody runs 3f-bis, the floor fails
    ("iterate/campaign-runner-architecture-review", None, False),  # campaign-ish name, no `--U<n>`
    ("iterate/x", ".shipwright/planning/iterate/campaigns/c/sub-iterates/U2-x.md", True),
    (CAMPAIGN_BRANCH, None, True),
])
def test_floor_relaxation_needs_campaign_evidence_on_the_entry(tmp_path, branch, spec, ok):
    root = _project(tmp_path, "medium", branch=branch, spec=spec)
    _record(root, {"external_code": "unavailable", "code": "delegated-to-orchestrator"})
    _write(root, _capture(FAILED))
    result = check_review_record(root, RUN)
    assert result.ok is ok, result.detail
    assert ok or "no code review ran" in result.detail


@pytest.mark.covers("FR-01.11")
def test_medium_floor_still_refuses_delegated_code_when_external_was_merely_skipped(tmp_path):
    root = _project(tmp_path, "medium", branch=CAMPAIGN_BRANCH)
    _record(root, {"external_code": "missing-keys", "code": "delegated-to-orchestrator"})
    result = check_review_record(root, RUN)
    assert result.ok is False and "no code review ran" in result.detail


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _commit_all(root: Path, *paths: str) -> str:
    _git(root, "add", *paths)
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c")
    return _git(root, "rev-parse", "HEAD")


@pytest.mark.covers("FR-01.11")
def test_gate_reads_the_capture_from_the_commit_not_the_working_tree(tmp_path):
    """A capture left out of the commit never ships, so it proves nothing — even if it is on disk."""
    root = _project(tmp_path)
    _git(root, "init", "-q")
    _record(root, {"external_code": "unavailable"})
    _write(root, _capture(FAILED))
    head = _commit_all(root, f".shipwright/planning/iterate/{RUN}/reviews.json")
    missing = check_review_record(root, RUN, head)
    assert missing.ok is False and f"in commit {head[:8]}" in missing.detail
    head = _commit_all(root, artifact_paths(RUN, "external_code")[0])
    assert check_review_record(root, RUN, head).ok is True


@pytest.mark.covers("FR-01.11")
def test_committed_bytes_win_over_a_different_working_tree_copy(tmp_path):
    root = _project(tmp_path)
    _git(root, "init", "-q")
    _record(root, {"external_code": "unavailable"})
    _write(root, _capture(SUCCEEDED))
    head = _commit_all(root, ".shipwright")
    _write(root, _capture(FAILED))  # rewritten afterwards, never committed
    result = check_review_record(root, RUN, head)
    assert result.ok is False and "not a failure envelope" in result.detail
