"""F11 delivery and provenance gate for the one-time test-results backfill."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from lib.iterate_entry import RUN_ID_STRICT, entry_file_for
from lib.iterate_test_results import (
    EvidenceError,
    evidence_file_for,
    read_current_evidence,
    validate_evidence_bytes,
)

from .common import CheckResult, Severity
from .git_blob_read import GitReadError, committed_bytes_reader
from .git_helpers import _run_git, git_context


BACKFILL_MANIFEST_REL = (
    ".shipwright/agent_docs/iterates/test-results-backfill-manifest.json"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_SOURCE = re.compile(
    r"^commit:([0-9a-f]{8,40}):shipwright_test_results\.json(?: \(.+\))?$"
)
_WORKTREE_SOURCE = re.compile(
    r"^worktree:([^@()\s]+)@([0-9a-f]{8,40}) \(M shipwright_test_results\.json\)$"
)


def _work_tree_refusal(name: str, artifact_label: str) -> CheckResult:
    """Shared git-fault refusal for ``check_test_results_evidence`` /
    ``check_test_results_backfill``: identical wording except which artifact it
    declines to certify as committed. Callers pass their own already-computed
    ``git_context()`` result — this does not call it itself, so each module's
    own ``git_context`` monkeypatch (ADR-045) still governs its own tests."""
    return CheckResult(
        name, False,
        "git could not answer whether this is a work tree — common causes: a "
        "wedged index.lock, a stalled filesystem, a `safe.directory` / dubious-"
        "ownership refusal, or git missing from PATH. Run `git -C <project> "
        "rev-parse --is-inside-work-tree` to see git's own message. Refusing to "
        f"certify {artifact_label} as committed.",
    )


class BackfillError(RuntimeError):
    """A manifest row cannot be certified."""


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackfillError(f"invalid {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise BackfillError(f"{label} must be an object")
    return value


def _worktree_map(root: Path) -> dict[str, tuple[Path, str]]:
    rc, out, _ = _run_git(root, "worktree", "list", "--porcelain")
    if rc != 0:
        raise BackfillError("cannot enumerate source worktrees")
    found: dict[str, tuple[Path, str]] = {}
    path: Path | None = None
    head = ""
    for line in (*out.splitlines(), ""):
        if line.startswith("worktree "):
            path = Path(line.removeprefix("worktree ").strip())
            head = ""
        elif line.startswith("HEAD "):
            head = line.removeprefix("HEAD ").strip()
        elif not line and path is not None:
            found[path.name] = (path, head)
            path = None
    return found


def _reachable_commit(root: Path, revision: str, run_id: str) -> str:
    rc, out, _ = _run_git(root, "rev-parse", "--verify", f"{revision}^{{commit}}")
    if rc != 0 or not out.strip():
        raise BackfillError(f"{run_id} source is not a commit")
    commit = out.strip()
    rc, refs, _ = _run_git(
        root, "for-each-ref", f"--contains={commit}", "--format=%(refname)"
    )
    if rc != 0 or not refs.strip():
        raise BackfillError(f"{run_id} source commit is not reachable from a ref")
    return commit


def _is_modified_snapshot_status(status: str) -> bool:
    """Accept only one ordinary tracked-file modification, staged or unstaged."""
    lines = status.splitlines()
    if len(lines) != 1 or len(lines[0]) < 4:
        return False
    xy, path = lines[0][:2], lines[0][3:]
    return xy in {" M", "M ", "MM"} and path == "shipwright_test_results.json"


def _validate_source(
    root: Path,
    source: Any,
    run_id: str,
    artifact: bytes,
    worktrees: dict[str, tuple[Path, str]],
) -> None:
    if not isinstance(source, str):
        raise BackfillError(f"{run_id} has no auditable source")
    commit_match = _COMMIT_SOURCE.fullmatch(source)
    if commit_match:
        commit = _reachable_commit(root, commit_match.group(1), run_id)
        candidate = committed_bytes_reader(root, commit)("shipwright_test_results.json")
        if candidate is None:
            raise BackfillError(f"{run_id} source blob is absent")
        rc, commit_text, _ = _run_git(root, "cat-file", "-p", commit)
        if rc != 0:
            raise BackfillError(f"{run_id} source commit cannot be inspected")
        parents = [line[7:] for line in commit_text.splitlines() if line.startswith("parent ")]
        if parents:
            rc, parent, _ = _run_git(
                root, "rev-parse", "--verify", f"{parents[0]}^{{commit}}"
            )
            if rc != 0:
                raise BackfillError(f"{run_id} source parent commit is unavailable")
            inherited = committed_bytes_reader(root, parent.strip())(
                "shipwright_test_results.json"
            )
            if inherited == candidate:
                raise BackfillError(f"{run_id} source blob is inherited unchanged")
        validate_evidence_bytes(candidate, run_id)
        if candidate != artifact:
            raise BackfillError(f"{run_id} differs from its source Git blob")
        return
    worktree_match = _WORKTREE_SOURCE.fullmatch(source)
    if not worktree_match:
        raise BackfillError(f"{run_id} has malformed source provenance")
    name, expected_head = worktree_match.groups()
    if name not in worktrees:
        raise BackfillError(f"{run_id} source worktree is unavailable")
    worktree, head = worktrees[name]
    if not head.startswith(expected_head):
        raise BackfillError(f"{run_id} source worktree HEAD changed")
    rc, status, _ = _run_git(
        worktree, "status", "--porcelain=v1", "--", "shipwright_test_results.json"
    )
    if rc != 0 or not _is_modified_snapshot_status(status):
        raise BackfillError(f"{run_id} source worktree snapshot is not run-written dirty")
    candidate = read_current_evidence(worktree, run_id)
    if candidate != artifact:
        raise BackfillError(f"{run_id} differs from its source worktree bytes")


def _validate_summary(raw: bytes, run_id: str, label: str) -> None:
    doc = _json_object(raw, label)
    if doc.get("run_id") != run_id:
        raise BackfillError(f"{label} run mismatch")


def check_test_results_backfill(
    project_root: Path, run_id: str, commit_hash: str = ""
) -> CheckResult:
    """Verify current-run manifest, sources, pre-existing summaries, and blobs."""
    name = "immutable test-results backfill committed"
    root = Path(project_root).resolve()
    manifest_path = root / BACKFILL_MANIFEST_REL
    if manifest_path.is_symlink():
        return CheckResult(name, False, "backfill manifest is a symlink")
    if not manifest_path.exists():
        return CheckResult(
            name, True, "not applicable (no backfill manifest)",
            severity=Severity.SKIPPED.value,
        )
    if not manifest_path.is_file():
        return CheckResult(name, False, "backfill manifest is not a regular file")
    try:
        manifest_raw = manifest_path.read_bytes()
        manifest = _json_object(manifest_raw, "backfill manifest")
        if manifest.get("backfill_run_id") != run_id:
            return CheckResult(
                name, True, "not applicable (manifest belongs to another run)",
                severity=Severity.SKIPPED.value,
            )
        if manifest.get("schema_version") != 1:
            raise BackfillError("unsupported backfill manifest schema")
        rows = manifest.get("recovered")
        unavailable = manifest.get("unavailable")
        if not isinstance(rows, list) or not rows:
            raise BackfillError("current-run recovered list is empty")
        if not isinstance(unavailable, list):
            raise BackfillError("backfill unavailable list is missing")
        worktrees = _worktree_map(root) if any(
            isinstance(row, dict) and str(row.get("source", "")).startswith("worktree:")
            for row in rows
        ) else {}

        seen: set[str] = set()
        working: dict[str, bytes] = {}
        summaries: dict[str, tuple[str, bytes]] = {}
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise BackfillError(f"recovered[{index}] is not an object")
            recovered_run = row.get("run_id")
            target = evidence_file_for(root, recovered_run)
            rel = target.relative_to(root).as_posix()
            if row.get("artifact") != rel or recovered_run in seen:
                raise BackfillError(f"recovered[{index}] identity is invalid")
            seen.add(recovered_run)
            expected_size, expected_hash = row.get("bytes"), row.get("sha256")
            if not isinstance(expected_size, int) or expected_size < 0:
                raise BackfillError(f"recovered[{index}] has invalid byte count")
            if not isinstance(expected_hash, str) or not _SHA256.fullmatch(expected_hash):
                raise BackfillError(f"recovered[{index}] has invalid sha256")
            if target.is_symlink() or not target.is_file():
                raise BackfillError(f"missing recovered artifact: {rel}")
            artifact = target.read_bytes()
            validate_evidence_bytes(artifact, recovered_run)
            if len(artifact) != expected_size or hashlib.sha256(artifact).hexdigest() != expected_hash:
                raise BackfillError(f"manifest hash/size mismatch: {rel}")
            working[rel] = artifact
            summary = entry_file_for(root, recovered_run)
            summary_rel = summary.relative_to(root).as_posix()
            if summary.is_symlink() or not summary.is_file():
                raise BackfillError(f"durable summary missing: {summary_rel}")
            summary_bytes = summary.read_bytes()
            _validate_summary(summary_bytes, recovered_run, summary_rel)
            summaries[summary_rel] = recovered_run, summary_bytes
            _validate_source(root, row.get("source"), recovered_run, artifact, worktrees)

        for index, row in enumerate(unavailable):
            if not isinstance(row, dict):
                raise BackfillError(f"unavailable[{index}] is not an object")
            missing_run, reason = row.get("run_id"), row.get("reason")
            if (
                not isinstance(missing_run, str)
                or RUN_ID_STRICT.fullmatch(missing_run) is None
                or missing_run in seen
                or not isinstance(reason, str)
                or not reason.strip()
            ):
                raise BackfillError(f"unavailable[{index}] is invalid")
            seen.add(missing_run)
    except (BackfillError, EvidenceError, GitReadError, OSError) as exc:
        return CheckResult(name, False, str(exc))

    if not commit_hash:
        return CheckResult(
            name, True,
            f"{len(rows)} backfill artifacts and sources valid; commit skipped "
            "(no --commit supplied)",
            severity=Severity.SKIPPED.value,
        )
    # Tri-state, not "did git exit 0": a broken binary / `safe.directory` refusal /
    # permission failure / wedged index.lock all return non-zero from INSIDE a real
    # repo, and reading that as "not a repo" would green-SKIP this ERROR gate on an
    # infra fault. Only a DEFINITIVE non-git answer stands it down.
    ctx = git_context(root)
    if ctx == "not_git":
        return CheckResult(
            name, True,
            f"{len(rows)} backfill artifacts and sources valid; commit skipped "
            "(not a git work tree)",
            severity=Severity.SKIPPED.value,
        )
    if ctx != "work_tree":
        return _work_tree_refusal(name, "the backfill manifest")
    reader = committed_bytes_reader(root, commit_hash)
    parent_reader = committed_bytes_reader(root, f"{commit_hash}^")
    try:
        committed_manifest = reader(BACKFILL_MANIFEST_REL)
        if committed_manifest is None or _json_object(committed_manifest, "committed manifest") != manifest:
            raise BackfillError("committed backfill manifest is absent or differs")
        for rel, artifact in working.items():
            if reader(rel) != artifact:
                raise BackfillError(f"recovered artifact absent or changed in commit: {rel}")
        for rel, (expected_run, working_summary) in summaries.items():
            committed_summary = reader(rel)
            prior_summary = parent_reader(rel)
            if prior_summary is None:
                raise BackfillError(f"summary did not pre-exist backfill commit: {rel}")
            _validate_summary(prior_summary, expected_run, f"pre-existing {rel}")
            if committed_summary != prior_summary:
                raise BackfillError(f"durable summary changed in backfill commit: {rel}")
            if committed_summary.replace(b"\r\n", b"\n") != working_summary.replace(
                b"\r\n", b"\n"
            ):
                raise BackfillError(f"working durable summary differs from commit: {rel}")
    except (BackfillError, GitReadError) as exc:
        return CheckResult(name, False, str(exc))
    return CheckResult(name, True, f"{len(rows)} backfill artifacts committed with provenance")


__all__ = ["BACKFILL_MANIFEST_REL", "check_test_results_backfill"]
