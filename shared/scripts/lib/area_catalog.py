"""Canonical producer and matcher for Shipwright's project area catalog."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
CATALOG_RELATIVE_PATH = Path(".shipwright/agent_docs/area_catalog.json")
_EXCLUDED_PARTS = {".git", ".worktrees", "node_modules", "__pycache__", ".venv"}
_FR_RE = re.compile(r"\bFR-[A-Z0-9]+(?:\.[A-Z0-9]+)+\b", re.IGNORECASE)
_CODE_RE = re.compile(r"`([^`\r\n]+)`")
_PATH_SUFFIXES = {
    ".c", ".css", ".go", ".html", ".js", ".json", ".jsx", ".md",
    ".py", ".rs", ".sql", ".ts", ".tsx", ".vue", ".yaml", ".yml",
}


def normalize_path(value: str) -> str:
    """Return a safe repository-relative POSIX path."""
    text = str(value).replace("\\", "/").strip()
    if text.startswith("/") or re.match(r"^[A-Za-z]:/", text):
        return ""
    while text.startswith("./"):
        text = text[2:]
    text = text.rstrip("/")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        return ""
    return "/".join(parts)


def catalog_path(project_root: Path | str) -> Path:
    return Path(project_root) / CATALOG_RELATIVE_PATH


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "root"


def _inventory(project_root: Path) -> list[str]:
    paths: list[str] = []
    for candidate in project_root.rglob("*"):
        try:
            rel = candidate.relative_to(project_root)
        except ValueError:
            continue
        if candidate.is_dir() or any(part in _EXCLUDED_PARTS for part in rel.parts):
            continue
        if rel.parts and rel.parts[0] == ".shipwright":
            continue
        norm = normalize_path(rel.as_posix())
        if norm:
            paths.append(norm)
    return sorted(set(paths))


def path_fingerprint(project_root: Path | str) -> str:
    payload = "\n".join(_inventory(Path(project_root))).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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


def _normalise_area(area: dict[str, Any]) -> dict[str, Any]:
    area_id = _slug(str(area.get("id", "root")))
    patterns = sorted({p for raw in area.get("path_patterns", []) if (p := normalize_path(raw))})
    return {
        "cross_cutting_tags": sorted({str(v) for v in area.get("cross_cutting_tags", []) if v}),
        "id": area_id,
        "path_patterns": patterns,
        "planned_paths": sorted({p for raw in area.get("planned_paths", []) if (p := normalize_path(raw))}),
        "priority": int(area.get("priority", 0)),
        "realized_paths": sorted({p for raw in area.get("realized_paths", []) if (p := normalize_path(raw))}),
        "requirements": sorted({str(v).upper() for v in area.get("requirements", []) if v}),
        "source": str(area.get("source", "deterministic")),
        "status": str(area.get("status", "active")),
    }


def validate_catalog(payload: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["catalog is not a JSON object"]
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    areas = payload.get("areas")
    if not isinstance(areas, list):
        errors.append("areas must be a list")
        return errors
    ids: set[str] = set()
    for position, area in enumerate(areas):
        if not isinstance(area, dict) or not isinstance(area.get("id"), str):
            errors.append(f"areas[{position}] has no string id")
            continue
        if area["id"] in ids:
            errors.append(f"duplicate area id: {area['id']}")
        ids.add(area["id"])
        if not isinstance(area.get("path_patterns"), list):
            errors.append(f"area {area['id']} path_patterns must be a list")
    return errors


def load_catalog(project_root: Path | str) -> tuple[dict[str, Any] | None, str]:
    path = catalog_path(project_root)
    if not path.exists():
        return None, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, "malformed"
    if validate_catalog(payload):
        return None, "invalid"
    current = payload.get("path_fingerprint") == path_fingerprint(project_root)
    return payload, "current" if current else "stale"


def _merge_areas(existing: Iterable[dict[str, Any]], additions: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {area["id"]: _normalise_area(area) for area in existing}
    for raw in additions:
        area = _normalise_area(raw)
        prior = merged.get(area["id"])
        if prior:
            for key in ("cross_cutting_tags", "path_patterns", "planned_paths", "realized_paths", "requirements"):
                area[key] = sorted(set(prior[key]) | set(area[key]))
            area["priority"] = max(prior["priority"], area["priority"])
        merged[area["id"]] = area
    return [merged[key] for key in sorted(merged)]


def write_catalog(project_root: Path | str, areas: Iterable[dict[str, Any]], source: str) -> dict[str, Any]:
    root = Path(project_root)
    existing, _ = load_catalog(root)
    previous = existing.get("areas", []) if existing else []
    payload = {
        "areas": _merge_areas(previous, areas),
        "catalogue_version": int(existing.get("catalogue_version", 0) if existing else 0) + 1,
        "path_fingerprint": path_fingerprint(root),
        "producer": "shared/scripts/tools/area_catalog.py",
        "schema_version": SCHEMA_VERSION,
        "sources": sorted(set((existing or {}).get("sources", [])) | {source}),
    }
    _atomic_json(catalog_path(root), payload)
    return payload


def _looks_like_path(value: str) -> bool:
    if any(char.isspace() for char in value) or any(char in value for char in "{}<>"):
        return False
    value = normalize_path(value)
    return bool(value) and ("/" in value or Path(value).suffix.lower() in _PATH_SUFFIXES)


def seed_greenfield(project_root: Path | str, source: str = "project") -> dict[str, Any]:
    root = Path(project_root)
    areas: list[dict[str, Any]] = []
    planning = root / ".shipwright/planning"
    for split in sorted(p for p in planning.glob("*") if p.is_dir() and p.name != "iterate"):
        texts: list[str] = []
        for doc in sorted(split.rglob("*.md")):
            try:
                texts.append(doc.read_text(encoding="utf-8"))
            except OSError:
                continue
        joined = "\n".join(texts)
        planned = sorted({normalize_path(v) for v in _CODE_RE.findall(joined) if _looks_like_path(v)})
        patterns = planned or [f"**/{_slug(split.name)}*/**"]
        areas.append({"id": split.name, "path_patterns": patterns, "planned_paths": planned,
                      "requirements": _FR_RE.findall(joined), "source": "planned"})
    architecture = root / ".shipwright/agent_docs/architecture.md"
    if architecture.exists():
        text = architecture.read_text(encoding="utf-8", errors="replace")
        planned = sorted({normalize_path(v) for v in _CODE_RE.findall(text) if _looks_like_path(v)})
        if planned:
            areas.append({"id": "architecture", "path_patterns": planned, "planned_paths": planned,
                          "cross_cutting_tags": ["architecture"], "priority": -10, "source": "planned"})
    return write_catalog(root, areas, source)


def _workspace_paths(root: Path) -> set[str]:
    result: set[str] = set()
    package = root / "package.json"
    if package.exists():
        try:
            value = json.loads(package.read_text(encoding="utf-8")).get("workspaces", [])
            members = value.get("packages", []) if isinstance(value, dict) else value
            for member in members:
                if not isinstance(member, str):
                    continue
                normal = normalize_path(member)
                if any(ch in normal for ch in "*[?"):
                    result.update(
                        candidate.relative_to(root).as_posix()
                        for candidate in root.glob(normal)
                        if candidate.is_dir()
                    )
                else:
                    result.add(normal)
        except (OSError, json.JSONDecodeError):
            pass
    return {v for v in result if v}


def seed_brownfield(project_root: Path | str, source: str = "adopt") -> dict[str, Any]:
    root = Path(project_root)
    paths = _inventory(root)
    boundaries = {p.split("/", 1)[0] for p in paths if "/" in p}
    boundaries.update(_workspace_paths(root))
    for path in paths:
        parts = path.split("/")
        for marker in ("features", "modules", "packages", "apps", "services", "plugins"):
            if marker in parts and parts.index(marker) + 1 < len(parts):
                boundaries.add("/".join(parts[: parts.index(marker) + 2]))
    areas = [{"id": boundary, "path_patterns": [f"{boundary}/**"],
              "realized_paths": [], "source": "deterministic"} for boundary in sorted(boundaries)]
    root_files = [p for p in paths if "/" not in p]
    if root_files:
        areas.append({"id": "root", "path_patterns": root_files, "realized_paths": [],
                      "cross_cutting_tags": ["repository"], "priority": -100, "source": "deterministic"})
    return write_catalog(root, areas, source)


def _static_prefix(pattern: str) -> str:
    cut = min([pattern.find(ch) for ch in "*[?" if ch in pattern] or [len(pattern)])
    return pattern[:cut].rstrip("/")


def match_area(catalog: dict[str, Any] | None, path: str) -> tuple[str | None, str]:
    norm = normalize_path(path)
    matches: list[tuple[int, int, int, str]] = []
    for area in (catalog or {}).get("areas", []):
        for pattern in area.get("path_patterns", []):
            exact = int(not any(ch in pattern for ch in "*[?") and norm == pattern)
            if exact or fnmatch.fnmatchcase(norm, pattern):
                matches.append((exact, len(_static_prefix(pattern)), int(area.get("priority", 0)), area["id"]))
    if not matches:
        return None, "unmapped"
    winner = sorted(matches, key=lambda item: (-item[0], -item[1], -item[2], item[3]))[0]
    return winner[3], "exact" if winner[0] else "pattern"


def refresh_paths(project_root: Path | str, paths: Iterable[str], source: str, provisional: bool = True) -> dict[str, Any]:
    root = Path(project_root)
    catalog, state = load_catalog(root)
    if catalog is None:
        catalog = seed_brownfield(root, source=f"{source}:bootstrap")
    additions: list[dict[str, Any]] = []
    unmapped: list[str] = []
    realized: dict[str, list[str]] = {}
    for raw in paths:
        path = normalize_path(raw)
        if not path:
            continue
        area_id, _ = match_area(catalog, path)
        if area_id:
            realized.setdefault(area_id, []).append(path)
        else:
            unmapped.append(path)
            if provisional:
                parts = path.split("/")
                boundary = (
                    "/".join(parts[:2])
                    if parts[0] in {"apps", "packages", "plugins", "services"} and len(parts) > 2
                    else parts[0]
                )
                additions.append({"id": boundary, "path_patterns": [f"{boundary}/**" if boundary != "root" else path],
                                  "realized_paths": [path] if (root / path).exists() else [],
                                  "planned_paths": [] if (root / path).exists() else [path],
                                  "source": "provisional"})
    additions.extend({"id": area_id, "realized_paths": values} for area_id, values in realized.items())
    updated = write_catalog(root, additions, source)
    return {"catalog_state_before": state, "catalog_path": str(catalog_path(root)),
            "mapped_paths": sorted({p for values in realized.values() for p in values}),
            "provisional_area_ids": sorted({_normalise_area(a)["id"] for a in additions if a.get("source") == "provisional"}),
            "unmapped_paths": sorted(set(unmapped)), "catalogue_version": updated["catalogue_version"]}
