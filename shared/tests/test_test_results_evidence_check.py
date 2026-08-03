"""F11 enforcement for immutable per-run test-result evidence."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import tools.verifiers.test_results_evidence_check as evidence_check
from lib.iterate_test_results import EvidenceError
from tools.verifiers.test_results_evidence_check import (
    check_test_results_evidence,
)


RUN_ID = "iterate-2026-08-03-f11-evidence"
_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _raw(run_id: str = RUN_ID) -> bytes:
    return json.dumps({"iterate_latest": {"run_id": run_id}}, indent=2).encode()


def _target(root):
    path = root / ".shipwright/agent_docs/iterates" / f"{RUN_ID}.test-results.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _commit(root, *paths: str) -> str:
    subprocess.run(["git", "-C", str(root), "add", *paths], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "test: evidence"],
        env=_GIT_ENV, check=True, capture_output=True,
    )
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()


def test_missing_or_foreign_working_evidence_fails(tmp_path):
    assert check_test_results_evidence(tmp_path, RUN_ID).ok is False
    _target(tmp_path).write_bytes(_raw("iterate-2026-08-03-foreign"))
    result = check_test_results_evidence(tmp_path, RUN_ID)
    assert result.ok is False
    assert "belongs to" in result.detail


def test_valid_evidence_committed_with_the_run_passes(git_origin_repo):
    root, _ = git_origin_repo
    _target(root).write_bytes(_raw())
    commit = _commit(root, ".shipwright/agent_docs/iterates")
    result = check_test_results_evidence(root, RUN_ID, commit)
    assert result.ok is True
    assert "committed" in result.detail


def test_valid_but_uncommitted_evidence_fails_f6_gate(git_origin_repo):
    root, _ = git_origin_repo
    _target(root).write_bytes(_raw())
    commit = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    result = check_test_results_evidence(root, RUN_ID, commit)
    assert result.ok is False
    assert "F6 must stage" in result.detail


def test_canonical_path_construction_error_fails_instead_of_legacy_skip(
    tmp_path, monkeypatch
):
    def unsafe_path(*_args, **_kwargs):
        raise EvidenceError("evidence path contains a symlink/reparse point")

    monkeypatch.setattr(evidence_check, "evidence_file_for", unsafe_path)

    result = check_test_results_evidence(tmp_path, RUN_ID)

    assert result.ok is False
    assert result.severity != "SKIPPED"
    assert "unsafe evidence path" in result.detail


def test_windows_reparse_evidence_target_fails_before_read(tmp_path, monkeypatch):
    target = _target(tmp_path)
    target.write_bytes(_raw())
    real_lstat = Path.lstat

    def lstat_with_reparse(path):
        if path == target:
            return SimpleNamespace(
                st_mode=stat.S_IFREG,
                st_file_attributes=getattr(
                    stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
                ),
            )
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", lstat_with_reparse)

    result = check_test_results_evidence(tmp_path, RUN_ID)

    assert result.ok is False
    assert "unsafe evidence path" in result.detail
    assert "symlink/reparse" in result.detail


def test_crlf_evidence_commits_as_exact_bytes_with_autocrlf(git_origin_repo):
    root, _ = git_origin_repo
    attributes = "/.shipwright/agent_docs/iterates/*.test-results.json -text -diff\n"
    (root / ".gitattributes").write_text(attributes, encoding="utf-8")
    raw = _raw().replace(b"\n", b"\r\n") + b"\r\n"
    _target(root).write_bytes(raw)
    subprocess.run(
        ["git", "-C", str(root), "config", "core.autocrlf", "true"], check=True
    )

    subprocess.run(
        ["git", "-C", str(root), "add", ".gitattributes", ".shipwright/agent_docs/iterates"],
        check=True,
    )
    whitespace = subprocess.run(
        ["git", "-C", str(root), "diff", "--cached", "--check"],
        capture_output=True,
        text=True,
    )
    assert whitespace.returncode == 0, whitespace.stdout + whitespace.stderr
    commit = _commit(root, ".gitattributes", ".shipwright/agent_docs/iterates")
    blob = subprocess.check_output(
        [
            "git", "-C", str(root), "show",
            f"{commit}:.shipwright/agent_docs/iterates/{RUN_ID}.test-results.json",
        ]
    )

    assert blob == raw
    assert check_test_results_evidence(root, RUN_ID, commit).ok is True
