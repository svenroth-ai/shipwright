"""F11 provenance and commit-delivery checks for the one-time evidence backfill."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess

import pytest

from tools.verifiers.test_results_backfill_check import (
    BACKFILL_MANIFEST_REL,
    _is_modified_snapshot_status,
    check_test_results_backfill,
)


CURRENT_RUN = "iterate-2026-08-03-f11-backfill"
RECOVERED_RUN = "iterate-2026-08-01-recovered"
RECOVERED_REL = (
    f".shipwright/agent_docs/iterates/{RECOVERED_RUN}.test-results.json"
)
SUMMARY_REL = f".shipwright/agent_docs/iterates/{RECOVERED_RUN}.json"
_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        env=_GIT_ENV,
        check=True,
        capture_output=True,
        text=True,
    )


def _commit(root, *paths: str) -> str:
    _git(root, "add", *paths)
    _git(root, "commit", "-m", "test: backfill provenance")
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _recovered() -> bytes:
    return json.dumps({"iterate_latest": {"run_id": RECOVERED_RUN}}).encode()


def _write_artifact_and_summary(root, *, summary: bool = True) -> bytes:
    raw = _recovered()
    artifact = root / RECOVERED_REL
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(raw)
    if summary:
        (root / SUMMARY_REL).write_text(
            json.dumps({"run_id": RECOVERED_RUN}), encoding="utf-8"
        )
    return raw


def _manifest(raw: bytes, source: str) -> dict:
    return {
        "schema_version": 1,
        "backfill_run_id": CURRENT_RUN,
        "policy": "test",
        "recovered": [{
            "run_id": RECOVERED_RUN,
            "source": source,
            "artifact": RECOVERED_REL,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }],
        "unavailable": [],
    }


def _write_manifest(root, manifest: dict) -> None:
    (root / BACKFILL_MANIFEST_REL).write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def _seed_commit_source(root, raw: bytes, *, with_summary: bool = True) -> str:
    (root / "shipwright_test_results.json").write_bytes(raw)
    paths = ["shipwright_test_results.json"]
    if with_summary:
        paths.append(SUMMARY_REL)
    return _commit(root, *paths)


def test_backfill_gate_accepts_exact_commit_source_and_preexisting_summary(
    git_origin_repo,
):
    root, _ = git_origin_repo
    raw = _write_artifact_and_summary(root)
    source_commit = _seed_commit_source(root, raw)
    _write_manifest(
        root, _manifest(raw, f"commit:{source_commit}:shipwright_test_results.json")
    )
    backfill_commit = _commit(root, BACKFILL_MANIFEST_REL, RECOVERED_REL)

    result = check_test_results_backfill(root, CURRENT_RUN, backfill_commit)

    assert result.ok is True
    assert "committed with provenance" in result.detail


def test_backfill_gate_accepts_text_normalized_worktree_summary(git_origin_repo):
    root, _ = git_origin_repo
    raw = _write_artifact_and_summary(root)
    (root / SUMMARY_REL).write_text(
        json.dumps({"run_id": RECOVERED_RUN}, indent=2) + "\n", encoding="utf-8"
    )
    source_commit = _seed_commit_source(root, raw)
    _write_manifest(
        root, _manifest(raw, f"commit:{source_commit}:shipwright_test_results.json")
    )
    backfill_commit = _commit(root, BACKFILL_MANIFEST_REL, RECOVERED_REL)
    committed = (root / SUMMARY_REL).read_bytes()
    normalized = committed.replace(b"\r\n", b"\n")
    (root / SUMMARY_REL).write_bytes(normalized.replace(b"\n", b"\r\n"))

    result = check_test_results_backfill(root, CURRENT_RUN, backfill_commit)

    assert result.ok is True
    assert "committed with provenance" in result.detail


def test_backfill_gate_rejects_every_non_eol_worktree_summary_change(
    git_origin_repo,
):
    root, _ = git_origin_repo
    raw = _write_artifact_and_summary(root)
    committed_doc = {"run_id": RECOVERED_RUN, "verified": True}
    (root / SUMMARY_REL).write_text(json.dumps(committed_doc), encoding="utf-8")
    source_commit = _seed_commit_source(root, raw)
    _write_manifest(
        root, _manifest(raw, f"commit:{source_commit}:shipwright_test_results.json")
    )
    backfill_commit = _commit(root, BACKFILL_MANIFEST_REL, RECOVERED_REL)

    mutations = (
        json.dumps({"run_id": RECOVERED_RUN, "verified": 1}).encode(),
        (
            f'{{"run_id": "{RECOVERED_RUN}", "verified": true, '
            '"verified": true}'
        ).encode(),
        (json.dumps(committed_doc, indent=2) + "\n").encode(),
    )
    for working in mutations:
        (root / SUMMARY_REL).write_bytes(working)

        result = check_test_results_backfill(root, CURRENT_RUN, backfill_commit)

        assert result.ok is False
        assert "working durable summary differs" in result.detail


def test_backfill_gate_fails_when_recovered_artifact_is_left_uncommitted(
    git_origin_repo,
):
    root, _ = git_origin_repo
    raw = _write_artifact_and_summary(root)
    source_commit = _seed_commit_source(root, raw)
    _write_manifest(
        root, _manifest(raw, f"commit:{source_commit}:shipwright_test_results.json")
    )
    backfill_commit = _commit(root, BACKFILL_MANIFEST_REL)

    result = check_test_results_backfill(root, CURRENT_RUN, backfill_commit)

    assert result.ok is False
    assert "artifact absent or changed" in result.detail


def test_backfill_gate_rejects_summary_invented_in_backfill_commit(git_origin_repo):
    root, _ = git_origin_repo
    raw = _write_artifact_and_summary(root)
    source_commit = _seed_commit_source(root, raw, with_summary=False)
    _write_manifest(
        root, _manifest(raw, f"commit:{source_commit}:shipwright_test_results.json")
    )
    backfill_commit = _commit(
        root, BACKFILL_MANIFEST_REL, RECOVERED_REL, SUMMARY_REL
    )

    result = check_test_results_backfill(root, CURRENT_RUN, backfill_commit)

    assert result.ok is False
    assert "did not pre-exist" in result.detail


def test_backfill_gate_rejects_changed_preexisting_summary(git_origin_repo):
    root, _ = git_origin_repo
    raw = _write_artifact_and_summary(root)
    source_commit = _seed_commit_source(root, raw)
    (root / SUMMARY_REL).write_text(
        json.dumps({"run_id": RECOVERED_RUN, "changed": True}), encoding="utf-8"
    )
    _write_manifest(
        root, _manifest(raw, f"commit:{source_commit}:shipwright_test_results.json")
    )
    backfill_commit = _commit(
        root, BACKFILL_MANIFEST_REL, RECOVERED_REL, SUMMARY_REL
    )

    result = check_test_results_backfill(root, CURRENT_RUN, backfill_commit)

    assert result.ok is False
    assert "summary changed" in result.detail


def test_backfill_gate_rejects_tree_object_as_commit_source(git_origin_repo):
    root, _ = git_origin_repo
    raw = _write_artifact_and_summary(root)
    source_commit = _seed_commit_source(root, raw)
    tree = _git(root, "rev-parse", f"{source_commit}^{{tree}}").stdout.strip()
    _write_manifest(
        root, _manifest(raw, f"commit:{tree}:shipwright_test_results.json")
    )

    result = check_test_results_backfill(root, CURRENT_RUN)

    assert result.ok is False
    assert "source is not a commit" in result.detail


def test_backfill_gate_rejects_unreachable_commit_source(git_origin_repo):
    root, _ = git_origin_repo
    raw = _write_artifact_and_summary(root)
    source_commit = _seed_commit_source(root, raw)
    tree = _git(root, "rev-parse", f"{source_commit}^{{tree}}").stdout.strip()
    dangling = _git(root, "commit-tree", tree, "-m", "dangling").stdout.strip()
    _write_manifest(
        root, _manifest(raw, f"commit:{dangling}:shipwright_test_results.json")
    )

    result = check_test_results_backfill(root, CURRENT_RUN)

    assert result.ok is False
    assert "not reachable" in result.detail


def test_backfill_gate_rejects_reachable_commit_with_inherited_snapshot(
    git_origin_repo,
):
    root, _ = git_origin_repo
    raw = _write_artifact_and_summary(root)
    _seed_commit_source(root, raw)
    (root / "marker.txt").write_text("descendant", encoding="utf-8")
    descendant = _commit(root, "marker.txt")
    _write_manifest(
        root, _manifest(raw, f"commit:{descendant}:shipwright_test_results.json")
    )

    result = check_test_results_backfill(root, CURRENT_RUN)

    assert result.ok is False
    assert "inherited unchanged" in result.detail


def test_backfill_gate_accepts_root_commit_that_introduces_snapshot(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    raw = _write_artifact_and_summary(root)
    (root / "shipwright_test_results.json").write_bytes(raw)
    source = _commit(root, "shipwright_test_results.json", SUMMARY_REL)
    _write_manifest(root, _manifest(raw, f"commit:{source}:shipwright_test_results.json"))

    result = check_test_results_backfill(root, CURRENT_RUN)

    assert result.ok is True


def test_backfill_gate_rejects_declared_but_unavailable_parent(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-b", "main")
    raw = _write_artifact_and_summary(source)
    (source / "shipwright_test_results.json").write_bytes(raw)
    _commit(source, "shipwright_test_results.json", SUMMARY_REL)
    (source / "marker.txt").write_text("descendant", encoding="utf-8")
    descendant = _commit(source, "marker.txt")

    shallow = tmp_path / "shallow"
    _git(tmp_path, "clone", "--depth", "1", source.resolve().as_uri(), str(shallow))
    artifact = shallow / RECOVERED_REL
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(raw)
    _write_manifest(
        shallow, _manifest(raw, f"commit:{descendant}:shipwright_test_results.json")
    )

    result = check_test_results_backfill(shallow, CURRENT_RUN)

    assert result.ok is False
    assert "parent commit is unavailable" in result.detail


def test_backfill_gate_rejects_attributed_artifact_without_summary(tmp_path):
    raw = _write_artifact_and_summary(tmp_path, summary=False)
    _write_manifest(
        tmp_path,
        _manifest(raw, "commit:12345678:shipwright_test_results.json"),
    )

    result = check_test_results_backfill(tmp_path, CURRENT_RUN)

    assert result.ok is False
    assert "source blob" in result.detail or "durable summary missing" in result.detail


def test_clean_inherited_worktree_snapshot_is_rejected(git_origin_repo):
    root, _ = git_origin_repo
    raw = _write_artifact_and_summary(root)
    (root / "shipwright_test_results.json").write_bytes(raw)
    source_commit = _commit(root, "shipwright_test_results.json", SUMMARY_REL)
    source = f"worktree:{root.name}@{source_commit[:8]} (M shipwright_test_results.json)"
    _write_manifest(root, _manifest(raw, source))

    result = check_test_results_backfill(root, CURRENT_RUN)

    assert result.ok is False
    assert "not run-written dirty" in result.detail


@pytest.mark.parametrize("xy", [" M", "M ", "MM"])
def test_only_tracked_modified_worktree_statuses_are_admissible(xy):
    assert _is_modified_snapshot_status(f"{xy} shipwright_test_results.json\n") is True


@pytest.mark.parametrize("xy", ["A ", " A", "D ", " D", "R ", "UU", "??"])
def test_non_modified_worktree_statuses_are_rejected(xy):
    assert _is_modified_snapshot_status(f"{xy} shipwright_test_results.json\n") is False


def test_multiple_status_records_are_rejected():
    assert _is_modified_snapshot_status(
        " M shipwright_test_results.json\n M another.json\n"
    ) is False
