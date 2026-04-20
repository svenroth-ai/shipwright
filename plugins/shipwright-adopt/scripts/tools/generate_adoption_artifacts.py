#!/usr/bin/env python3
"""CLI: consume snapshot.json + enrichment.json → write all Adopt artifacts.

This is the deterministic artifact-production step. It:
  1. Reads .shipwright/adopt/snapshot.json (Layer-1)
  2. Reads .shipwright/adopt/enrichment.json (Layer-2, if present)
  3. Writes CLAUDE.md + agent_docs/* + planning/<split>/spec.md
  4. Writes all 6 shipwright_*_config.json in safe order
  5. Seeds shipwright_events.jsonl (adopted + optional backfill)
  6. Installs .claude/settings.json UserPromptSubmit hook
  7. Generates e2e/flows/adopted-baseline.spec.ts from routes.json (if present)

Layer-3 review and compliance seeding are separate tools.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _load_lib() -> None:
    lib_dir = Path(__file__).resolve().parent.parent / "lib"
    sys.path.insert(0, str(lib_dir))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _pick(enrichment: dict[str, Any], key: str, fallback: str) -> str:
    val = enrichment.get(key)
    if isinstance(val, str) and val.strip():
        return val
    return fallback


def _current_commit(project_root: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return r.stdout.strip() or None
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def _render_ascii_diagram_fallback(snapshot: dict[str, Any]) -> str:
    """Deterministic fallback when Layer-2 didn't provide a diagram."""
    layers = snapshot.get("folders", {}).get("layers", [])
    primary_language = snapshot.get("stack", {}).get("primary_language", "?")
    lines = [
        "```",
        f"  {snapshot.get('project_root', 'project').rsplit('/', 1)[-1]}  ({primary_language})",
        "",
    ]
    for layer in layers:
        lines.append(f"  [{layer['name']}]")
        for path in layer["paths"][:5]:
            lines.append(f"    - {path}")
    lines.append("```")
    return "\n".join(lines)


def _extract_qr(snapshot: dict[str, Any]) -> list[str]:
    qr: list[str] = []
    ci = snapshot.get("ci_pipeline", {}).get("provider")
    if ci:
        qr.append(f"CI pipeline ({ci}) must pass on pull requests.")
    conv = snapshot.get("conventions", {})
    if conv.get("linter"):
        qr.append(f"Code passes {conv['linter']} without warnings.")
    if conv.get("tsconfig_strict"):
        qr.append("TypeScript strict mode is enforced.")
    return qr


def _extract_constraints(snapshot: dict[str, Any]) -> list[str]:
    constraints: list[str] = []
    runtime = snapshot.get("stack", {}).get("runtime", {})
    for k, v in runtime.items():
        constraints.append(f"{k.capitalize()} version: {v}")
    return constraints


def generate(
    project_root: Path,
    *,
    snapshot_path: Path,
    enrichment_path: Path,
    routes_path: Path,
    split_name: str,
    plugin_version: str,
    scope_override: str | None,
    profile_override: str | None,
    write_sync: bool,
    backfill_events: bool,
) -> dict[str, Any]:
    _load_lib()
    from config_writer import write_all  # type: ignore
    from artifact_writer import write_agent_docs, write_claude_md, write_spec  # type: ignore
    from event_seeder import seed_adopted_event, seed_backfill_events  # type: ignore
    from hook_installer import install_suggest_iterate_hook  # type: ignore
    from e2e_baseline_generator import write_baseline_spec  # type: ignore

    snapshot = _read_json(snapshot_path)
    enrichment = _read_json(enrichment_path)
    routes = []
    if routes_path.exists():
        try:
            routes = json.loads(routes_path.read_text(encoding="utf-8"))
            if not isinstance(routes, list):
                routes = []
        except json.JSONDecodeError:
            routes = []

    project_name = project_root.name
    profile = profile_override or snapshot.get("profile", {}).get("matched", "generic")
    scope = scope_override or "full_app"
    commit_sha = _current_commit(project_root)
    commands = snapshot.get("commands", {})
    stack = snapshot.get("stack", {})

    # Features: prefer Playwright routes (enriched) over AST
    features = snapshot.get("features", [])
    ast_features_map = {f.get("route", ""): f for f in features}

    merged_features: list[dict[str, Any]] = []
    if routes:
        for i, route in enumerate(routes, start=1):
            fr_id = f"FR-01.{i:02d}"
            url = route.get("url", "")
            ast_match = ast_features_map.get(url, {})
            enrichment_match = next(
                (e for e in enrichment.get("features", []) if e.get("route") == url or e.get("url") == url),
                {},
            )
            merged_features.append({
                "fr_id": fr_id,
                "route": url,
                "url": url,
                "source_file": ast_match.get("source_file") or route.get("source_file", "—"),
                "label": enrichment_match.get("label") or route.get("title") or url,
                "description": enrichment_match.get("description") or "TBD — refine via /shipwright-iterate",
                "acceptance_draft": enrichment_match.get("acceptance_draft") or "TBD",
            })
    else:
        for i, f in enumerate(features, start=1):
            f = dict(f)
            f["fr_id"] = f.get("fr_id") or f"FR-01.{i:02d}"
            enrichment_match = next(
                (e for e in enrichment.get("features", []) if e.get("route") == f.get("route")),
                {},
            )
            f["label"] = enrichment_match.get("label") or f.get("route", "?")
            f["description"] = enrichment_match.get("description") or "TBD — refine via /shipwright-iterate"
            f["acceptance_draft"] = enrichment_match.get("acceptance_draft") or "TBD"
            merged_features.append(f)

    product_description = _pick(
        enrichment, "product_description",
        fallback=(
            f"{project_name} — adopted into Shipwright. "
            f"Primary language: {stack.get('primary_language', '?')}. "
            "Refine this abstract via /shipwright-iterate."
        ),
    )
    conventions_prose = _pick(enrichment, "conventions_prose",
        fallback="Conventions inferred deterministically from linter/formatter configs. Refine manually for project-specific rules.",
    )
    architecture_prose = _pick(enrichment, "architecture_prose",
        fallback="Data flow: inferred from folder layers. Refine via /shipwright-iterate.",
    )
    architecture_diagram = enrichment.get("architecture_diagram") or _render_ascii_diagram_fallback(snapshot)

    nested_excluded = snapshot.get("excludes", [])
    git = snapshot.get("git", {})
    layers = snapshot.get("folders", {}).get("layers", [])
    loc_by_layer = snapshot.get("folders", {}).get("loc_by_layer", {})
    qr = _extract_qr(snapshot)
    constraints = _extract_constraints(snapshot)

    results: dict[str, Any] = {"written": []}

    # Artifacts
    p = write_claude_md(
        project_root, project_name=project_name, profile=profile, stack=stack,
        commands=commands, product_description=product_description,
    )
    results["written"].append(str(p))
    for p in write_agent_docs(
        project_root,
        project_name=project_name, profile=profile, scope=scope,
        stack=stack, layers=layers, loc_by_layer=loc_by_layer,
        architecture_diagram=architecture_diagram,
        data_flow_description=architecture_prose,
        conventions=snapshot.get("conventions", {}),
        conventions_prose=conventions_prose,
        features_count=len(merged_features),
        commits_total=git.get("commits_total", 0),
        contributors_total=git.get("contributors_total", 0),
        nested_excluded=nested_excluded,
        commit_sha=commit_sha,
        retroactive_adrs=enrichment.get("adrs", []),
    ):
        results["written"].append(str(p))
    p = write_spec(
        project_root,
        project_name=project_name, split_name=split_name,
        product_description=product_description,
        features=merged_features, qr_items=qr, constraints=constraints,
    )
    results["written"].append(str(p))

    # Configs (run_config LAST — see config_writer.write_all)
    for p in write_all(
        project_root,
        scope=scope, profile=profile, split_name=split_name,
        plugin_version=plugin_version,
        dev_url=None,  # stays None for adopted until first /shipwright-iterate
        test_cmd=commands.get("test"),
        commit_sha=commit_sha,
        features_inferred=len(merged_features),
        nested_excluded=nested_excluded,
        fr_count=len(merged_features), qr_count=len(qr),
        write_sync=write_sync,
    ):
        results["written"].append(str(p))

    # Events
    events_path = project_root / "shipwright_events.jsonl"
    seed_adopted_event(
        events_path,
        profile=profile, scope=scope,
        features_inferred=len(merged_features),
        nested_excluded=nested_excluded,
        plugin_version=plugin_version,
        commit_sha=commit_sha,
    )
    if backfill_events:
        seed_backfill_events(events_path, git.get("major_refactor_commits", []))
    results["written"].append(str(events_path))

    # Hook
    settings = project_root / ".claude" / "settings.json"
    hook_result = install_suggest_iterate_hook(settings)
    results["hook_install"] = hook_result

    # E2E baseline (if routes.json present)
    if routes:
        spec_path = write_baseline_spec(project_root, routes)
        results["written"].append(str(spec_path))
        results["e2e_baseline_generated"] = True
    else:
        results["e2e_baseline_generated"] = False

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate /shipwright-adopt artifacts")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--snapshot", type=Path, default=None)
    parser.add_argument("--enrichment", type=Path, default=None)
    parser.add_argument("--routes", type=Path, default=None)
    parser.add_argument("--split-name", type=str, default="01-adopted")
    parser.add_argument("--plugin-version", type=str, default="0.1.0")
    parser.add_argument("--scope", type=str, choices=["full_app", "library", "cli"], default=None)
    parser.add_argument("--profile", type=str, default=None)
    parser.add_argument("--no-sync", action="store_true")
    parser.add_argument("--no-backfill-events", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        print(f"ERROR: not a directory: {project_root}", file=sys.stderr)
        return 1

    snap = args.snapshot or (project_root / ".shipwright" / "adopt" / "snapshot.json")
    enrich = args.enrichment or (project_root / ".shipwright" / "adopt" / "enrichment.json")
    routes = args.routes or (project_root / ".shipwright" / "adopt" / "routes.json")

    if not snap.exists():
        print(f"ERROR: snapshot not found at {snap}. Run analyze_codebase.py first.", file=sys.stderr)
        return 2

    results = generate(
        project_root,
        snapshot_path=snap, enrichment_path=enrich, routes_path=routes,
        split_name=args.split_name, plugin_version=args.plugin_version,
        scope_override=args.scope, profile_override=args.profile,
        write_sync=not args.no_sync,
        backfill_events=not args.no_backfill_events,
    )
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
