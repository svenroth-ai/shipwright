"""``release.py sync``: Steps 5.3 to 5.5 in one call (unit P4).

The event fold (never blocks, always exit 0), then the published-package manifests (Step 5.4), then the compliance evidence
documents (Step 5.5). Each is the tool the prose ran, with the same flags. Manifests and evidence stop the release when their
status is not ``ok`` (the prose said "anything else - stop, do not tag"); the pathspecs they return are kept in the run state,
so ``commit-and-tag`` reads them there and the model never copies them (the same fact decided once, A6).

Stop 3 (FINDINGS D23): the compliance run of Step 5.5 records a ``grade_snapshot`` event (an untracked drop file under the
``drops`` layout, a change to a tracked ``shipwright_events.jsonl`` under ``legacy``). The event files it wrote are found by
comparing their bytes before and after the call and are kept as ``events_pathspec``, so Step 6 commits them with the release
instead of leaving them for the release audit to refuse. The window is the call itself: any event file written while it runs
(a concurrent hook's drop included) is the release's; under ``drops`` one written before or after it is not, and Step 6 names
it as unrelated. Under ``legacy`` the unit is the whole log, so lines appended to it around the call go with the release.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import release_event, release_paths, release_runstate
from .release_runner import Recorder, uv_script

MANIFEST_RESULT = ".shipwright/runtime/manifest_sync_result.json"


def event_files(root: Path) -> dict[str, str]:
    """Every event file by content hash (the legacy log and each drop file), relative posix paths."""
    log, drops = release_event.record_paths()  # the two event homes, named once
    found = [root / log, *sorted((root / drops).glob("*.jsonl"))]
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in found if p.is_file()}


def written_events(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """The event files that are new or changed: what the call in between wrote (D23)."""
    return sorted(path for path, digest in after.items() if before.get(path) != digest)


def _json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def sync(rec: Recorder, plugin_root: Path, *, version: str) -> tuple[int, dict[str, Any]]:
    shared, root = release_paths.shared_root(plugin_root), rec.cwd
    tools = shared / "scripts/tools"
    fold = rec.run("fold-events", uv_script(tools / "fold_events_for_release.py", "--project-root", str(root)))
    out: dict[str, Any] = {"version": version, "fold": {"status": _json(fold.stdout).get("status", "failed"), "exit": fold.exit}}
    manifests = rec.run("sync", uv_script(tools / "sync_release_manifests.py", "--project-root", ".", "--version", version, "--stage",
                                          "--result-file", MANIFEST_RESULT))
    info = _json(manifests.stdout)
    out["manifests"] = {"status": info.get("status", "failed"), "version": info.get("version"), "pathspec": info.get("manifest_pathspec", [])}
    if manifests.exit != 0 or info.get("status") != "ok":
        return manifests.exit or 1, {**out, "status": "failed", "reason": "manifest_sync_failed", "commands": rec.as_json()}
    events_before = event_files(root)
    evidence = rec.run("evidence", uv_script(tools / "refresh_compliance_docs.py", "--project-root", str(root), "--stage",
                                             "--release", f"v{version}"))
    written = written_events(events_before, event_files(root))
    info = _json(evidence.stdout)
    out["evidence"] = {"status": info.get("status", "failed"), "pathspec": info.get("evidence_pathspec", [])}
    if evidence.exit != 0 or info.get("status") != "ok":
        return evidence.exit or 1, {**out, "status": "failed", "reason": "evidence_refresh_failed", "commands": rec.as_json()}
    kept = (release_runstate.stored(root, version) or {}).get("events_pathspec", [])  # a second sync keeps what the first one wrote
    out["events"] = {"pathspec": sorted({*kept, *written})}
    release_runstate.patch(root, version, manifest_pathspec=out["manifests"]["pathspec"], evidence_pathspec=out["evidence"]["pathspec"],
                           events_pathspec=out["events"]["pathspec"])
    return 0, {**out, "status": "ok", "commands": rec.as_json()}
