"""Validate and install immutable per-run iterate test-result bytes."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

from .atomic_write import _fsync_parent_dir, durable_read_bytes
from .iterate_entry import RUN_ID_STRICT, iterates_dir


RESULTS_FILENAME = "shipwright_test_results.json"
EVIDENCE_SUFFIX = ".test-results.json"


class EvidenceError(RuntimeError):
    """The current snapshot cannot safely become immutable evidence."""


def _is_link_or_reparse(path: Path, metadata: Any | None = None) -> bool:
    """Detect POSIX symlinks and Windows reparse points without following them."""
    info = path.lstat() if metadata is None else metadata
    attrs = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(info.st_mode) or bool(attrs & reparse_flag)


def _file_identity(metadata: Any) -> tuple[Any, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        getattr(metadata, "st_mtime_ns", None),
    )


def _read_stable_regular_bytes(source: Path, metadata: Any) -> bytes:
    """Read without following links where supported; otherwise detect replacement."""
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if nofollow:
        flags = os.O_RDONLY | nofollow | getattr(os, "O_BINARY", 0)
        try:
            descriptor = os.open(source, flags)
        except OSError as exc:
            raise EvidenceError(f"cannot open stable {RESULTS_FILENAME}: {exc}") from exc
        try:
            opened = os.fstat(descriptor)
            if _is_link_or_reparse(source, opened) or not stat.S_ISREG(opened.st_mode):
                raise EvidenceError(
                    f"{RESULTS_FILENAME} changed to a non-regular file while opening"
                )
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                raw = handle.read()
            after_read = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        try:
            after_path = source.lstat()
        except OSError as exc:
            raise EvidenceError(f"{RESULTS_FILENAME} changed while reading: {exc}") from exc
        if not (
            _file_identity(metadata)
            == _file_identity(opened)
            == _file_identity(after_read)
            == _file_identity(after_path)
        ):
            raise EvidenceError(f"{RESULTS_FILENAME} changed while reading")
        return raw

    try:
        raw = durable_read_bytes(source)
        after = source.lstat()
    except OSError as exc:
        raise EvidenceError(f"cannot read {RESULTS_FILENAME}: {exc}") from exc
    if (
        _is_link_or_reparse(source, after)
        or not stat.S_ISREG(after.st_mode)
        or _file_identity(after) != _file_identity(metadata)
    ):
        raise EvidenceError(f"{RESULTS_FILENAME} changed while reading")
    return raw


def _canonical_run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or RUN_ID_STRICT.fullmatch(run_id) is None:
        raise EvidenceError(f"noncanonical run_id: {run_id!r}")
    return run_id


def evidence_file_for(project_root: Path, run_id: str) -> Path:
    """Collision-free evidence path derived only from a canonical invocation ID."""
    canonical = _canonical_run_id(run_id)
    project = Path(project_root).resolve()
    root = iterates_dir(project)
    target = root / f"{canonical}{EVIDENCE_SUFFIX}"
    try:
        target.relative_to(project)
    except ValueError as exc:  # defense in depth behind RUN_ID_STRICT
        raise EvidenceError("evidence target escapes the project root") from exc
    current = project
    for part in target.relative_to(project).parts:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise EvidenceError(f"cannot inspect evidence path component: {exc}") from exc
        if _is_link_or_reparse(current, metadata):
            raise EvidenceError(f"evidence path contains a symlink/reparse point: {current}")
    return target


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise EvidenceError(f"duplicate JSON key: {key!r}")
        out[key] = value
    return out


def _reject_nonstandard_constant(value: str) -> Any:
    raise EvidenceError(f"non-standard JSON constant: {value}")


def validate_evidence_bytes(raw: bytes, run_id: str) -> dict[str, Any]:
    """Validate attribution without changing the byte buffer that will be stored."""
    canonical = _canonical_run_id(run_id)
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise EvidenceError("test-results snapshot is not valid UTF-8") from exc
    try:
        doc = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonstandard_constant,
        )
    except EvidenceError:
        raise
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"malformed JSON in test-results snapshot: {exc}") from exc
    if not isinstance(doc, dict):
        raise EvidenceError("test-results snapshot must be a top-level JSON object")
    latest = doc.get("iterate_latest")
    if not isinstance(latest, dict):
        raise EvidenceError("iterate_latest must be an object")
    owner = latest.get("run_id")
    if not isinstance(owner, str):
        raise EvidenceError("iterate_latest.run_id must be a string")
    if owner != canonical:
        raise EvidenceError(
            f"test-results snapshot belongs to {owner!r}, not current run {canonical!r}"
        )
    return doc


def read_current_evidence(project_root: Path, run_id: str) -> bytes:
    """Read and validate the current root snapshot exactly once as raw bytes."""
    source = Path(project_root).resolve() / RESULTS_FILENAME
    try:
        metadata = source.lstat()
    except FileNotFoundError:
        raise EvidenceError(f"missing {RESULTS_FILENAME}")
    except OSError as exc:
        raise EvidenceError(f"cannot inspect {RESULTS_FILENAME}: {exc}") from exc
    if _is_link_or_reparse(source, metadata) or not stat.S_ISREG(metadata.st_mode):
        raise EvidenceError(
            f"{RESULTS_FILENAME} must be a regular non-symlink/reparse file"
        )
    raw = _read_stable_regular_bytes(source, metadata)
    validate_evidence_bytes(raw, run_id)
    return raw


def _existing_evidence_matches(target: Path, raw: bytes, run_id: str) -> bool | None:
    """Return True for identical existing bytes, None when absent; reject all else."""
    try:
        metadata = target.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise EvidenceError(f"cannot inspect existing immutable evidence: {exc}") from exc
    if _is_link_or_reparse(target, metadata) or not stat.S_ISREG(metadata.st_mode):
        raise EvidenceError(f"immutable evidence target is not a regular file: {target}")
    existing = _read_stable_regular_bytes(target, metadata)
    if existing != raw:
        raise EvidenceError(
            f"immutable evidence collision for {run_id}: existing bytes differ"
        )
    return True


def _durable_create_no_replace(target: Path, raw: bytes) -> None:
    """Publish complete bytes atomically without ever replacing a winner.

    A same-directory hard link is the portable no-replace commit point: both names
    address the already-fsynced inode, and ``os.link`` fails when ``target`` exists.
    Removing the private name afterwards cannot affect the published bytes.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=target.name + ".", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, target)
    finally:
        with suppress(OSError):
            os.unlink(temporary)
    _fsync_parent_dir(target.parent)


def install_immutable_evidence(
    project_root: Path, run_id: str, raw: bytes
) -> tuple[Path, bool]:
    """Install exact bytes once; identical retries no-op, collisions fail closed."""
    validate_evidence_bytes(raw, run_id)
    target = evidence_file_for(project_root, run_id)
    if _existing_evidence_matches(target, raw, run_id):
        return target, False
    target.parent.mkdir(parents=True, exist_ok=True)
    # Re-walk after creating parents so a raced-in reparse point cannot be accepted.
    target = evidence_file_for(project_root, run_id)
    if _existing_evidence_matches(target, raw, run_id):
        return target, False
    try:
        _durable_create_no_replace(target, raw)
    except FileExistsError:
        # Another installer won the only atomic create. It is a valid retry only
        # when the winner published exactly our bytes.
        target = evidence_file_for(project_root, run_id)
        if _existing_evidence_matches(target, raw, run_id):
            return target, False
        raise EvidenceError(f"immutable evidence winner vanished for {run_id}")
    except OSError as exc:
        raise EvidenceError(f"cannot install immutable evidence: {exc}") from exc
    target = evidence_file_for(project_root, run_id)
    if not _existing_evidence_matches(target, raw, run_id):
        raise EvidenceError(f"immutable evidence vanished after install for {run_id}")
    return target, True


def install_current_evidence(project_root: Path, run_id: str) -> tuple[Path, bool]:
    """Capture the current root snapshot and install its exact bytes."""
    return install_immutable_evidence(
        project_root, run_id, read_current_evidence(project_root, run_id)
    )


__all__ = [
    "EVIDENCE_SUFFIX",
    "EvidenceError",
    "evidence_file_for",
    "install_current_evidence",
    "install_immutable_evidence",
    "read_current_evidence",
    "validate_evidence_bytes",
]
