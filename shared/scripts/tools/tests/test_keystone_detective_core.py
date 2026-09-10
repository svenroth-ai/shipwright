"""THE KEYSTONE GATE's post-merge DETECTIVE arm (ruling Q5) —
``_keystone_detective_core``, the classification/short-circuit half.

Design: ``.shipwright/planning/iterate/2026-09-10-keystone-detective-arm.md``.
Covers AC-D1, AC-D2, AC-D3, AC-D4, AC-D5, AC-D10, AC-D12, AC-D13 — everything
driven by the two resolvers' own status before (or instead of) recomputing
greenness. The greenness/composition half (AC-D6..D9, AC-D11) is in
``test_keystone_detective_greenness.py`` — split at 300 LOC, same discipline
`_keystone_ac_digest_never_silent.py` used to buy back headroom from its
sibling.

Both cross-commit resolvers (`resolve_ci_verification`,
`resolve_execution_evidence`) are MOCKED here — they are frozen, already-
reviewed modules with their own test suites, and this module's job is the
composition around them, not re-proving their own contracts. Everything
git-facing (first-parent resolution, the committed manifests) uses a REAL
repo, the same discipline `test_keystone_ac_digest.py` uses for the
preventive gate's own git-facing half — mocking the reader would test the
mock.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

from verifiers import _keystone_detective_core as dc  # noqa: E402
from verifiers._keystone_base_manifest import ReadError  # noqa: E402

from _keystone_repo import (  # noqa: E402
    git, make_repo, make_evidence as _evidence, make_verification as _verification,
    repo_with_ac01_edit as _repo_with_ac01_edit,
)


def _boom(*_args, **_kwargs):
    raise AssertionError("resolve_execution_evidence must not be called here")


# --------------------------------------------------------------------------
# AC-D1 — no_qualifying_run
#
# AC-D13's "only a pull_request-event run exists" scenario is NOT
# independently re-tested at this module's boundary (external code review
# round 2, glm, medium — the original test here mocked
# `resolve_ci_verification` to return `no_record` with a different `detail`
# string, which is functionally identical to AC-D1's test once the resolver
# is mocked away: `classify_commit` does not branch on WHY verification
# returned `no_record`, only THAT it did, so no code path here distinguishes
# the two). The event-type filtering itself already has its own dedicated
# test at the resolver boundary:
# `shared/tests/test_ci_provenance.py::test_no_record_when_only_pull_request_runs_exist`.
# --------------------------------------------------------------------------

def test_no_record_classifies_as_no_qualifying_run(tmp_path, monkeypatch):
    """AC-D1: `resolve_ci_verification` -> `no_record` classifies as
    `no_qualifying_run`, never conflated with `run_not_verified` — regardless
    of the underlying reason (AC-D13; see the note above)."""
    root, base_sha, head_sha = _repo_with_ac01_edit(tmp_path)
    monkeypatch.setattr(dc, "resolve_ci_verification", lambda *a, **kw: _verification("no_record"))
    monkeypatch.setattr(dc, "resolve_execution_evidence", _boom)

    result = dc.classify_commit(head_sha, project_root=root)

    assert result.outcome == dc.NO_QUALIFYING_RUN
    assert result.parent == base_sha


# --------------------------------------------------------------------------
# AC-D2 / AC-D3 / AC-D10 — run_not_verified, verification_query_failed,
# and the short-circuit that never asks the execution-evidence question
# --------------------------------------------------------------------------

def test_not_verified_classifies_as_run_not_verified(tmp_path, monkeypatch):
    """AC-D2, and AC-D10's short-circuit for this branch."""
    root, base_sha, head_sha = _repo_with_ac01_edit(tmp_path)
    monkeypatch.setattr(dc, "resolve_ci_verification", lambda *a, **kw: _verification("not_verified", run_id=7))
    monkeypatch.setattr(dc, "resolve_execution_evidence", _boom)

    result = dc.classify_commit(head_sha, project_root=root)

    assert result.outcome == dc.RUN_NOT_VERIFIED
    assert result.run_id == 7


def test_verification_error_classifies_as_verification_query_failed(tmp_path, monkeypatch):
    """AC-D3, and AC-D10's short-circuit for this branch: an unresolved
    verification must never proceed to ask the execution-evidence question."""
    root, base_sha, head_sha = _repo_with_ac01_edit(tmp_path)
    monkeypatch.setattr(dc, "resolve_ci_verification", lambda *a, **kw: _verification("error", "gh timed out"))
    monkeypatch.setattr(dc, "resolve_execution_evidence", _boom)

    result = dc.classify_commit(head_sha, project_root=root)

    assert result.outcome == dc.VERIFICATION_QUERY_FAILED
    assert "timed out" in result.detail


# --------------------------------------------------------------------------
# AC-D4 / AC-D5 — execution evidence unavailable / query failed
# --------------------------------------------------------------------------

def test_execution_evidence_unavailable(tmp_path, monkeypatch):
    root, base_sha, head_sha = _repo_with_ac01_edit(tmp_path)
    monkeypatch.setattr(dc, "resolve_ci_verification", lambda *a, **kw: _verification("verified", run_id=9))
    monkeypatch.setattr(dc, "resolve_execution_evidence", lambda *a, **kw: _evidence("unavailable", run_id=9))

    result = dc.classify_commit(head_sha, project_root=root)

    assert result.outcome == dc.EXECUTION_EVIDENCE_UNAVAILABLE
    assert result.run_id == 9


def test_execution_evidence_query_failed(tmp_path, monkeypatch):
    root, base_sha, head_sha = _repo_with_ac01_edit(tmp_path)
    monkeypatch.setattr(dc, "resolve_ci_verification", lambda *a, **kw: _verification("verified", run_id=9))
    monkeypatch.setattr(
        dc, "resolve_execution_evidence",
        lambda *a, **kw: _evidence("error", detail="content-binding mismatch", run_id=9),
    )

    result = dc.classify_commit(head_sha, project_root=root)

    assert result.outcome == dc.EXECUTION_EVIDENCE_QUERY_FAILED
    assert "content-binding" in result.detail


# --------------------------------------------------------------------------
# AC-D12 — no caller-supplied parent; root commits raise
# --------------------------------------------------------------------------

def test_classify_commit_takes_no_parent_argument_and_resolves_it_internally(tmp_path, monkeypatch):
    """AC-D12 (part 1): the first parent is resolved internally, closing the
    mismatched/malicious-pair risk a caller-supplied `parent` would permit."""
    root, base_sha, head_sha = _repo_with_ac01_edit(tmp_path)
    monkeypatch.setattr(dc, "resolve_ci_verification", lambda *a, **kw: _verification("no_record"))
    monkeypatch.setattr(dc, "resolve_execution_evidence", _boom)

    result = dc.classify_commit(head_sha, project_root=root)

    assert result.parent == base_sha
    # The signature itself is the contract: `classify_commit(commit, *,
    # project_root)` takes no `parent` parameter at all, so there is no way
    # for a caller to pass a mismatched one.
    assert "parent" not in inspect.signature(dc.classify_commit).parameters


def test_a_root_commit_raises_read_error(tmp_path):
    """AC-D12 (part 2): a root commit has no parent to diff against."""
    root = make_repo(tmp_path)
    root_sha = git("rev-parse", "HEAD", cwd=root)

    with pytest.raises(ReadError):
        dc.classify_commit(root_sha, project_root=root)


# --------------------------------------------------------------------------
# AC-D14 — commit is canonicalized to a full SHA before any resolver call
# --------------------------------------------------------------------------

def test_a_mutable_ref_is_canonicalized_to_a_full_sha_before_any_resolver_call(tmp_path, monkeypatch):
    """AC-D14: a caller passing a mutable ref (branch name, `HEAD`) gets the
    SAME resolved commit used for the parent lookup, the resolvers, and the
    manifest reads -- closing the window where the ref could move between
    calls (external plan review, openai, medium)."""
    root, base_sha, head_sha = _repo_with_ac01_edit(tmp_path)
    seen_commits = []

    def _capture(commit, **_kw):
        seen_commits.append(commit)
        return _verification("no_record")

    monkeypatch.setattr(dc, "resolve_ci_verification", _capture)
    monkeypatch.setattr(dc, "resolve_execution_evidence", _boom)

    result = dc.classify_commit("HEAD", project_root=root)

    assert result.commit == head_sha
    assert seen_commits == [head_sha]


def test_an_unresolvable_commit_raises_read_error(tmp_path):
    """AC-D14 (part 2): a garbage ref fails canonicalization up front, before
    parent resolution or any network call."""
    root = make_repo(tmp_path)

    with pytest.raises(ReadError):
        dc.classify_commit("not-a-real-ref-at-all", project_root=root)


def test_the_canonical_sha_reaches_execution_evidence_and_both_manifest_reads(tmp_path, monkeypatch):
    """AC-D14 (part 3): the first test above only proves the short-circuit's
    `resolve_ci_verification` call gets the canonical SHA — this proves the
    SAME canonical value (not the caller's original ref) also reaches
    `resolve_execution_evidence` and both `read_base_manifest` calls, by
    driving a caller-supplied mutable ref all the way to the `verified` path
    (external code review round 2, openai, low)."""
    root, base_sha, head_sha = _repo_with_ac01_edit(tmp_path)
    seen_manifest_shas = []
    seen_evidence_commits = []

    def _capture_manifest(_root, sha):
        seen_manifest_shas.append(sha)
        return {}, ""

    def _capture_evidence(commit, **_kw):
        seen_evidence_commits.append(commit)
        return _evidence("unavailable", run_id=1)

    monkeypatch.setattr(dc, "resolve_ci_verification", lambda *a, **kw: _verification("verified", run_id=1))
    monkeypatch.setattr(dc, "read_base_manifest", _capture_manifest)
    monkeypatch.setattr(dc, "resolve_execution_evidence", _capture_evidence)

    result = dc.classify_commit("HEAD", project_root=root)

    assert result.commit == head_sha
    assert seen_evidence_commits == [head_sha]
    assert seen_manifest_shas == [head_sha, base_sha]


# --------------------------------------------------------------------------
# AC-D15 — either resolver returning a status outside its own documented
# contract fails closed rather than being silently treated as the "next"
# branch
# --------------------------------------------------------------------------

def test_an_unrecognized_verification_status_raises_read_error(tmp_path, monkeypatch):
    """AC-D15 (part 1): a status string outside `resolve_ci_verification`'s
    own four-way contract must not silently fall through to the `verified`
    branch."""
    root, base_sha, head_sha = _repo_with_ac01_edit(tmp_path)
    monkeypatch.setattr(dc, "resolve_ci_verification", lambda *a, **kw: _verification("something_new"))
    monkeypatch.setattr(dc, "resolve_execution_evidence", _boom)

    with pytest.raises(ReadError):
        dc.classify_commit(head_sha, project_root=root)


def test_an_unrecognized_evidence_status_raises_read_error(tmp_path, monkeypatch):
    """AC-D15 (part 2): a status string outside `resolve_execution_evidence`'s
    own three-way contract must not silently fall through to the `confirmed`
    branch."""
    root, base_sha, head_sha = _repo_with_ac01_edit(tmp_path)
    monkeypatch.setattr(dc, "resolve_ci_verification", lambda *a, **kw: _verification("verified", run_id=9))
    monkeypatch.setattr(dc, "resolve_execution_evidence", lambda *a, **kw: _evidence("something_new", run_id=9))

    with pytest.raises(ReadError):
        dc.classify_commit(head_sha, project_root=root)
