#!/usr/bin/env python3
"""Post-generation canon-lite validation for /shipwright-adopt.

Runs after all artifacts are written. Verifies:
  - 5 required config JSONs exist + valid JSON (sync_config optional)
  - .shipwright/agent_docs/{architecture, conventions, decision_log, build_dashboard}.md exist
  - .shipwright/planning/*/spec.md exists and has >= 1 FR-NN.MM reference
  - shipwright_events.jsonl has exactly 1 "adopted" event
  - .shipwright/adopt/review.md exists (skip-reason is acceptable)

The .claude/settings.json UserPromptSubmit hook check was retired
2026-05-05 (iterate-20260505-plugin-hook-registration) — the hook is
now plugin-owned (plugins/shipwright-iterate/hooks/hooks.json).

Exit 0 on success, non-zero with error list otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def _discovery():
    # Shared planning walk, loaded by FILE LOCATION under a sentinel name so no
    # ambiguous ``lib``/``scripts`` package is ever bound (ADR-045). Lazy: this
    # script is also loaded standalone, where sys.path holds neither tree.
    mod = sys.modules.get("_shipwright_planning_discovery")
    if mod is None:
        import importlib.util
        path = Path(__file__).resolve().parents[4] / "shared/scripts/lib/planning_discovery.py"
        spec = importlib.util.spec_from_file_location("_shipwright_planning_discovery", path)
        sys.modules["_shipwright_planning_discovery"] = mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


def _jsonl_records():
    # Shared record-boundary reader, loaded by FILE LOCATION under a sentinel name
    # so the plugin-local ``lib`` is never shadowed (ADR-045) — same shape as
    # ``_discovery()``. Registered in ``sys.modules`` BEFORE ``exec_module`` because
    # ``jsonl_records`` defines ``@dataclass`` types and stdlib ``dataclasses``
    # resolves ``cls.__module__`` through ``sys.modules`` at class-creation time.
    # Consumer-specific sentinel (NOT a bare shared name): two plugins loading the
    # SSoT under one process must not collide on a single sys.modules key, where a
    # different checkout's copy could win (external review, OpenAI #2).
    mod = sys.modules.get("_shipwright_adopt_jsonl_records")
    if mod is None:
        import importlib.util
        path = Path(__file__).resolve().parents[4] / "shared/scripts/lib/jsonl_records.py"
        spec = importlib.util.spec_from_file_location("_shipwright_adopt_jsonl_records", path)
        sys.modules["_shipwright_adopt_jsonl_records"] = mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


REQUIRED_CONFIGS = [
    "shipwright_run_config.json",
    "shipwright_project_config.json",
    "shipwright_plan_config.json",
    "shipwright_build_config.json",
    "shipwright_compliance_config.json",
]

REQUIRED_AGENT_DOCS = [
    ".shipwright/agent_docs/architecture.md",
    ".shipwright/agent_docs/conventions.md",
    ".shipwright/agent_docs/decision_log.md",
    ".shipwright/agent_docs/build_dashboard.md",
]


def _validate_configs(project_root: Path) -> list[str]:
    errors: list[str] = []
    for name in REQUIRED_CONFIGS:
        p = project_root / name
        if not p.exists():
            errors.append(f"missing: {name}")
            continue
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"invalid JSON: {name} ({e.msg})")
    return errors


def _validate_agent_docs(project_root: Path) -> list[str]:
    errors: list[str] = []
    for name in REQUIRED_AGENT_DOCS:
        if not (project_root / name).exists():
            errors.append(f"missing: {name}")
    return errors


def _validate_spec(project_root: Path) -> list[str]:
    errors: list[str] = []
    planning = project_root / ".shipwright" / "planning"
    if not planning.is_dir():
        return ["missing: .shipwright/planning/ directory"]
    # sort=False: which spec gets validated is filesystem-iteration-order
    # dependent. Pinned by ``test_unsorted_walk_tracks_enumeration_order``;
    # adding a sort would be a behaviour change, not a cleanup.
    specs = list(_discovery().iter_spec_files(planning, recursive=True, sort=False))
    if not specs:
        return ["missing: .shipwright/planning/<split>/spec.md (no spec found)"]
    spec = specs[0]
    content = spec.read_text(encoding="utf-8", errors="ignore")
    if not re.search(r"\bFR-\d+\.\d+\b", content):
        errors.append(f"spec.md has no FR-NN.MM reference: {spec.relative_to(project_root).as_posix()}")
    return errors


def _validate_events(project_root: Path) -> list[str]:
    events_path = project_root / "shipwright_events.jsonl"
    if not events_path.exists():
        return ["missing: shipwright_events.jsonl"]
    # Record-boundary recovery via the shared SSoT (see _jsonl_records): an
    # 'adopted' event second on a merge=union concatenated line previously read as
    # absent (iterate-2026-07-20-events-record-boundary-remainder). Only JSON
    # objects are returned, so a bare scalar line no longer crashes .get().
    adopted_count = sum(
        1 for ev in _jsonl_records().read_jsonl_records(events_path).records
        if ev.get("type") == "adopted"
    )
    if adopted_count == 0:
        return ["shipwright_events.jsonl: no 'adopted' event found"]
    if adopted_count > 1:
        return [f"shipwright_events.jsonl: expected exactly 1 'adopted' event, found {adopted_count}"]
    return []


# _validate_hook retired 2026-05-05 (iterate-20260505-plugin-hook-registration):
# the suggest_iterate UserPromptSubmit hook is now plugin-owned (registered
# in plugins/shipwright-iterate/hooks/hooks.json). Claude Code surfaces
# disabled-plugin state at session start; an adopt-side validation would
# only drift.


#: Artifacts that make the handed-over repository honest about itself
#: (FR-01.13, trg-1aa5a8ab). Hard errors, not warnings — without them Step H
#: hands over a derived catalogue that reads as confirmed. Each message names
#: the step that writes the file, so an older adopted repo re-validating is
#: told what to run rather than merely that something is missing.
#:
_HONESTY_ARTIFACTS = (
    (".shipwright/adopt/derived-catalogue.json",
     "Step E (generate_adoption_artifacts.py)"),
    ("shipwright_known_failures.json",
     "Step E.18 (record_inherited_baseline.py)"),
)


def _derived_catalogue_doc():
    """adopt's ``derived_catalogue_doc``, loaded BY FILE LOCATION under a sentinel
    so no ambiguous ``lib`` package is ever bound (ADR-045) — same shape as
    ``_discovery`` / ``_jsonl_records`` above."""
    mod = sys.modules.get("_shipwright_adopt_derived_catalogue_doc")
    if mod is None:
        import importlib.util
        lib = Path(__file__).resolve().parent.parent / "lib"
        if str(lib) not in sys.path:
            sys.path.insert(0, str(lib))
        path = lib / "derived_catalogue_doc.py"
        spec = importlib.util.spec_from_file_location(
            "_shipwright_adopt_derived_catalogue_doc", path)
        sys.modules["_shipwright_adopt_derived_catalogue_doc"] = mod = (
            importlib.util.module_from_spec(spec))
        spec.loader.exec_module(mod)
    return mod


def _validate_honesty_artifacts(project_root: Path) -> list[str]:
    errors = [
        f"missing: {rel} — written by {step}; re-run it"
        for rel, step in _HONESTY_ARTIFACTS
        if not (project_root / rel).exists()
    ]
    if errors:
        return errors
    # Present is not the same as trustworthy. The count in this file is what the
    # handover publishes, so validation PARSES it through the fail-closed reader
    # rather than checking it exists — otherwise a forged or half-written
    # catalogue sails past the one gate meant to stop it (external code review).
    dcd = _derived_catalogue_doc()
    try:
        dcd.read_summary(project_root)
    except dcd.CatalogueDocumentError as exc:
        errors.append(
            f"unusable: {_HONESTY_ARTIFACTS[0][0]} — {exc}; "
            "re-run Step E (generate_adoption_artifacts.py)"
        )
    return errors


def _validate_review(project_root: Path) -> list[str]:
    review = project_root / ".shipwright" / "adopt" / "review.md"
    if not review.exists():
        return ["missing: .shipwright/adopt/review.md (should document review OR skip-reason)"]
    return []


def _hollow_adr_detection():
    """trg-6b59524b hollow-ADR detector, loaded BY FILE LOCATION (ADR-045).

    Guards mirror ``lib/shared_loader.py`` (missing-file -> named
    ``ImportError``, not a bare ``FileNotFoundError``; pop the sentinel on a
    failing exec so a half-initialised module is never memoised) — this
    loader can't reuse that helper directly since it targets a plugin-local
    path, not `shared/` (doubt-reviewer, round 4)."""
    mod = sys.modules.get("_shipwright_adopt_hollow_adr_detection")
    if mod is not None:
        return mod
    import importlib.util
    path = Path(__file__).resolve().parent.parent / "lib" / "hollow_adr_detection.py"
    if not path.is_file():
        raise ImportError(f"adopt lib helper not found at {path}")
    spec = importlib.util.spec_from_file_location(
        "_shipwright_adopt_hollow_adr_detection", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_shipwright_adopt_hollow_adr_detection"] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop("_shipwright_adopt_hollow_adr_detection", None)
        raise
    return mod


def validate(project_root: Path) -> dict:
    """Run hard + soft validation. Returns `{errors: [...], warnings: [...]}`."""
    errors: list[str] = []
    errors.extend(_validate_configs(project_root))
    errors.extend(_validate_agent_docs(project_root))
    errors.extend(_validate_spec(project_root))
    errors.extend(_validate_events(project_root))
    errors.extend(_validate_review(project_root))
    errors.extend(_validate_honesty_artifacts(project_root))

    warnings: list[str] = []
    warnings.extend(_hollow_adr_detection().soft_check_decision_log_density(project_root))
    warnings.extend(_hollow_adr_detection().soft_check_adr_seed_folder(project_root))

    return {"errors": errors, "warnings": warnings}


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
    from cli_paths import unquoted_path
    parser = argparse.ArgumentParser(description="Post-generation validation for /shipwright-adopt")
    parser.add_argument("--project-root", required=True, type=unquoted_path)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    result = validate(project_root)
    errors = result["errors"]
    warnings = result["warnings"]
    if errors:
        print(json.dumps({"ok": False, "errors": errors, "warnings": warnings}, indent=2))
        return 1
    print(json.dumps({"ok": True, "errors": [], "warnings": warnings}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
