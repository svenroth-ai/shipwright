"""Disposable, deterministic index derived from ``shipwright_events.jsonl``."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .area_catalog import SCHEMA_VERSION as CATALOG_SCHEMA_VERSION
from .area_catalog import load_catalog, match_area, normalize_path
from .commit_trailers import build_run_id_commit_map, resolve_base_ref
from .event_context_coverage import aggregate_field_coverage

INDEX_SCHEMA_VERSION = 3
INDEX_RELATIVE_PATH = Path(".shipwright/runtime/events-context-index.json")
#: The five selection keys this index exists to make rankable — see
#: iterate-2026-08-07-events-context-backfill-keys.
PROVENANCE_FIELDS = ("commit", "changed_files", "area_ids", "affected_frs", "supersedes_event_id")
EVENT_LOG_NAME = "shipwright_events.jsonl"
MAX_INDEX_STRING = 500
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x1b]")
_SECRET_RE = re.compile(
    r"(?i)(?P<label>api[_-]?key|token|secret|password)(?P<sep>\s*[:=]\s*)(?P<value>[^\s,;]+)"
)


def index_path(project_root: Path | str) -> Path:
    return Path(project_root) / INDEX_RELATIVE_PATH


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def sanitize_text(value: Any, limit: int | None = MAX_INDEX_STRING) -> tuple[str, bool]:
    text = _CONTROL_RE.sub("", str(value)).replace("\r\n", "\n").replace("\r", "\n")
    text = _SECRET_RE.sub(lambda match: f"{match.group('label')}{match.group('sep')}[REDACTED]", text)
    truncated = limit is not None and len(text) > limit
    return (text[:limit] if limit is not None else text), truncated


def _sanitize_full_value(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_text(value, None)[0]
    if isinstance(value, list):
        return [_sanitize_full_value(item) for item in value]
    if isinstance(value, dict):
        return {sanitize_text(key, 160)[0]: _sanitize_full_value(item) for key, item in value.items()}
    return value


def load_full_events(project_root: Path | str) -> list[dict[str, Any]]:
    """Return every valid raw event as redacted, control-safe untrusted data."""
    path = Path(project_root) / EVENT_LOG_NAME
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    with path.open("rb") as handle:
        for sequence, raw in enumerate(handle, start=1):
            try:
                event = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                continue
            if isinstance(event, dict):
                record = _sanitize_full_value(event)
                record["_shipwright_source_sequence"] = sequence
                records.append(record)
    return records


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item.get("path", "")) if isinstance(item, dict) else str(item) for item in value]
    return []


def _summary(event: dict[str, Any]) -> tuple[str, bool]:
    for key in ("description", "summary", "message", "reason"):
        if event.get(key):
            return sanitize_text(event[key])
    return "", False


def _tags(event_type: str, paths: list[str]) -> list[str]:
    tags: set[str] = set()
    joined = " ".join(paths).lower()
    for tag, needles in {
        "ci": (".github/", "ci"),
    "compliance": ("compliance",),  # artifact-path-canon: legacy -- event tag, not a path
        "governance": ("constitution", "decision", "policy"),
        "release": ("deploy", "release", "changelog"),
        "security": ("security", "auth", "rls", "secret"),
    }.items():
        if any(needle in joined or needle in event_type.lower() for needle in needles):
            tags.add(tag)
    return sorted(tags)


def _event_entry(event: dict[str, Any], sequence: int, line_hash: str,
                 catalog: dict[str, Any] | None,
                 commit_map: dict[str, Any]) -> dict[str, Any]:
    provenance: dict[str, str] = {}

    run_id, _ = sanitize_text(event.get("run_id") or event.get("adr_id") or "", 160)
    backfill = commit_map.get(run_id) if run_id else None

    declared_commit, _ = sanitize_text(event.get("commit") or event.get("commit_sha") or "", 160)
    if declared_commit:
        commit = declared_commit
        provenance["commit"] = "declared"
    elif backfill:
        commit, _ = sanitize_text(backfill["sha"], 160)
        provenance["commit"] = "derived"
    else:
        commit = ""
        provenance["commit"] = "unavailable"

    declared_raw_paths = _strings(event.get("changed_files"))
    changed_files_truncated = False
    if declared_raw_paths:
        raw_paths = declared_raw_paths
        provenance["changed_files"] = "declared"
    elif backfill:
        raw_paths = backfill["changed_files"]
        changed_files_truncated = backfill["changed_files_truncated"]
        provenance["changed_files"] = "derived"
    else:
        raw_paths = []
        provenance["changed_files"] = "unavailable"
    paths = sorted({p for raw in raw_paths if (p := normalize_path(raw))})

    area_methods = [match_area(catalog, path) for path in paths]
    areas = sorted({area for area, _ in area_methods if area})
    provenance["area_ids"] = "derived" if paths else "unavailable"

    summary, summary_truncated = _summary(event)
    event_type, _ = sanitize_text(event.get("type", event.get("event_type", "unknown")), 80)
    explicit_id = event.get("event_id") or event.get("id")
    event_id, _ = sanitize_text(explicit_id or f"line-{sequence}-{line_hash[:12]}", 160)

    affected_frs = sorted({value.upper() for value in _strings(event.get("affected_frs")) if value})
    has_change_type = bool(str(event.get("change_type") or "").strip())
    provenance["affected_frs"] = "declared" if (affected_frs or has_change_type) else "unavailable"

    relation = event.get("amends") or event.get("amended_event_id") or event.get("supersedes")
    relation_text, _ = sanitize_text(relation or "", 160)
    provenance["supersedes_event_id"] = "declared" if relation_text else "unavailable"

    tree, _ = sanitize_text(event.get("tree") or event.get("tree_sha") or "", 160)
    return {
        "affected_frs": affected_frs,
        "area_ids": areas,
        "changed_files": paths,
        "changed_files_truncated": changed_files_truncated,
        "commit": commit,
        "event_id": event_id,
        "event_type": event_type,
        "global_tags": _tags(event_type, paths),
        "provenance": provenance,
        "run_id": run_id,
        "sequence": sequence,
        "source_line_hash": line_hash,
        "summary": summary,
        "summary_truncated": summary_truncated,
        "supersedes_event_id": relation_text,
        "tree": tree,
    }


def event_log_stats(project_root: Path | str) -> dict[str, Any]:
    path = Path(project_root) / EVENT_LOG_NAME
    if not path.exists():
        return {"bytes": 0, "count": 0, "estimated_tokens": 0, "fingerprint": "missing"}
    digest = hashlib.sha256()
    count = 0
    size = 0
    try:
        with path.open("rb") as handle:
            for raw in handle:
                digest.update(raw)
                size += len(raw)
                if raw.strip():
                    count += 1
    except OSError:
        return {"bytes": 0, "count": 0, "estimated_tokens": 0, "fingerprint": "unreadable"}
    return {"bytes": size, "count": count, "estimated_tokens": (size + 3) // 4,
            "fingerprint": digest.hexdigest()}


def build_index(project_root: Path | str, *, persist: bool = True) -> dict[str, Any]:
    root = Path(project_root)
    log_path = root / EVENT_LOG_NAME
    catalog, catalog_state = load_catalog(root)
    stats = event_log_stats(root)
    base_ref_pin = resolve_base_ref(root)
    commit_scan = build_run_id_commit_map(root, base_ref_pin)
    commit_map = commit_scan["map"]
    entries: list[dict[str, Any]] = []
    invalid_lines = 0
    if log_path.exists():
        with log_path.open("rb") as handle:
            for sequence, raw in enumerate(handle, start=1):
                if not raw.strip():
                    continue
                line_hash = hashlib.sha256(raw).hexdigest()
                try:
                    decoded = json.loads(raw.decode("utf-8"))
                except (UnicodeError, json.JSONDecodeError):
                    invalid_lines += 1
                    continue
                if not isinstance(decoded, dict):
                    invalid_lines += 1
                    continue
                entries.append(_event_entry(decoded, sequence, line_hash, catalog, commit_map))
    coverage_summary = aggregate_field_coverage(entries, PROVENANCE_FIELDS)
    payload = {
        "catalog_state": catalog_state,
        "catalogue_schema_version": CATALOG_SCHEMA_VERSION,
        "catalogue_version": int((catalog or {}).get("catalogue_version", 0)),
        "coverage": {
            "commit_map": {
                "base_ref_used": commit_scan["base_ref_used"],
                "commits_scanned": commit_scan["commits_scanned"],
                "resolved_sha": commit_scan["resolved_sha"],
                "status": commit_scan["status"],
            },
            "fields": coverage_summary["fields"],
            "missing_work_completed": coverage_summary["missing_work_completed"],
        },
        "entries": entries,
        "event_log_bytes": stats["bytes"],
        "event_log_fingerprint": stats["fingerprint"],
        "index_schema_version": INDEX_SCHEMA_VERSION,
        "invalid_lines": invalid_lines,
        "source_artifact": EVENT_LOG_NAME,
        "source_event_count": stats["count"],
    }
    if persist:
        _atomic_json(index_path(root), payload)
    return payload


def load_or_rebuild_index(project_root: Path | str) -> tuple[dict[str, Any], str]:
    root = Path(project_root)
    path = index_path(root)
    stats = event_log_stats(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        required = {"affected_frs", "area_ids", "changed_files", "commit", "event_id", "event_type",
                    "global_tags", "provenance", "sequence", "source_line_hash", "summary", "tree"}
        entries = payload.get("entries")
        valid = (
            payload.get("index_schema_version") == INDEX_SCHEMA_VERSION
            and payload.get("event_log_fingerprint") == stats["fingerprint"]
            and "coverage" in payload
            and isinstance(entries, list)
            and all(isinstance(entry, dict) and required.issubset(entry) for entry in entries)
        )
        if valid:
            catalog, state = load_catalog(root)
            if payload.get("catalogue_version") == int((catalog or {}).get("catalogue_version", 0)):
                # The event-log fingerprint alone does not prove the index is
                # current: git history is a third input the commit backfill
                # reads, and it can advance (a commit carrying a Run-ID:
                # trailer lands) with no event appended at all — e.g. F5b
                # writes `work_completed` before F6 creates the commit that
                # would resolve it. Re-resolving the base ref is one cheap
                # `rev-parse` (not a history walk); only a mismatch pays for
                # the real rebuild (code review, iterate-2026-08-07-events-
                # context-backfill-keys).
                cached_commit_map = payload.get("coverage", {}).get("commit_map", {})
                current_pin = resolve_base_ref(root)
                current_sha = current_pin[1] if current_pin else None
                if current_sha == cached_commit_map.get("resolved_sha"):
                    payload["catalog_state"] = state
                    return payload, "cache"
    except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
        pass
    return build_index(root), "rebuild"
