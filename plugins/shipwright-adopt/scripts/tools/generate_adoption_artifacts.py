#!/usr/bin/env python3
"""CLI: consume snapshot.json + enrichment.json → write all Adopt artifacts.

This is the deterministic artifact-production step. It:
  1. Reads .shipwright/adopt/snapshot.json (Layer-1)
  2. Reads .shipwright/adopt/enrichment.json (Layer-2, if present)
  3. Writes CLAUDE.md + .shipwright/agent_docs/* + .shipwright/planning/<split>/spec.md
  4. Writes all 6 shipwright_*_config.json in safe order
  5. Seeds shipwright_events.jsonl (adopted + optional backfill)
  6. (No-op slot — suggest_iterate UserPromptSubmit hook is plugin-
     registered in plugins/shipwright-iterate/hooks/hooks.json since
     iterate-20260505-plugin-hook-registration; no per-project install.)
  7. Generates e2e/flows/adopted-baseline.spec.ts from routes.json (if present)

Layer-3 review and compliance seeding are separate tools.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def _load_lib() -> None:
    lib_dir = Path(__file__).resolve().parent.parent / "lib"
    sys.path.insert(0, str(lib_dir))


def _scaffold_env_local(project_root: Path) -> dict[str, Any]:
    """Invoke ``shared/scripts/validate_env.init_env_file`` for this project.

    Returns the rich result dict from ``init_env_file`` (action, path,
    vars, framework_keys, missing_keys, …) — caller stores it under
    ``results["env_local"]``. On import failure (corrupted shared
    tree), returns an action=skipped record rather than crashing the
    whole adopt run; subsequent steps continue.
    """
    # Repo layout:
    #   plugins/shipwright-adopt/scripts/tools/generate_adoption_artifacts.py
    #   ↑[0]tools  ↑[1]scripts  ↑[2]shipwright-adopt  ↑[3]plugins  ↑[4]repo-root
    repo_root = Path(__file__).resolve().parents[4]
    profile_dir = repo_root / "shared" / "profiles"

    # Make `shared.scripts.validate_env` importable. We add the repo root so
    # the existing test-suite import path (`from shared.scripts.validate_env
    # import ...`) keeps working in the same process.
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    try:
        from shared.scripts.validate_env import init_env_file  # type: ignore
    except ImportError as exc:
        return {
            "action": "skipped",
            "reason": "validate_env_import_failed",
            "error": str(exc),
            "path": str(project_root / ".env.local"),
        }

    return init_env_file(
        project_root,
        "all",
        profile_dir,
        include_framework=True,
    )


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


# Fix 3a: Test-file detection. Source_file paths matching these patterns are
# tests, not features. Filter them out of the FR list — Fix 5 mines them as
# acceptance criteria for sibling FRs instead.
_TEST_PATH_RE = re.compile(
    r"(^|/)("
    r"__tests__|__mocks__|tests?"
    r")(/|$)|"
    r"(^|/)(conftest|test_[^/]+)\.py$|"
    r"\.(test|spec)\.(ts|tsx|js|jsx|mjs|cjs|py)$"
)


def _is_test_path(source_file: str) -> bool:
    """True if the path looks like a test/mock/fixture rather than a feature."""
    if not source_file or source_file == "—":
        return False
    return bool(_TEST_PATH_RE.search(source_file.replace("\\", "/")))


def _normalize_route(route: str) -> str:
    """Trailing-slash normalization for dedup. `/about/` and `/about` are the
    same route. The empty string and `/` collapse to `/`."""
    if not route:
        return ""
    if route == "/":
        return "/"
    return route.rstrip("/")


# Fix 4: see-also cross-links to existing user-facing docs.
_GUIDE_FILENAMES: tuple[str, ...] = (
    "guide.md", "manual.md", "usage.md", "getting-started.md", "handbook.md",
)
_GUIDE_MIN_LINES = 100  # threshold for "non-trivial enough to link"


def _discover_user_facing_docs(project_root: Path) -> list[str]:
    """Return relative paths of user-facing docs worth linking from
    architecture.md. Always includes README.md when present; includes
    `docs/<name>.md` only when the file exceeds _GUIDE_MIN_LINES."""
    found: list[str] = []
    readme = project_root / "README.md"
    if readme.is_file():
        found.append("README.md")
    docs = project_root / "docs"
    if docs.is_dir():
        for name in _GUIDE_FILENAMES:
            cand = docs / name
            if not cand.is_file():
                continue
            try:
                line_count = sum(1 for _ in cand.open("r", encoding="utf-8", errors="ignore"))
            except OSError:
                continue
            if line_count >= _GUIDE_MIN_LINES:
                found.append(f"docs/{name}")
    return found


def _discover_changelog(project_root: Path) -> str | None:
    """Return `CHANGELOG.md` if present at project root, else None."""
    if (project_root / "CHANGELOG.md").is_file():
        return "CHANGELOG.md"
    return None


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
    # suggest_iterate hook is plugin-owned (registered in
    # plugins/shipwright-iterate/hooks/hooks.json under UserPromptSubmit);
    # no project-level installation is performed here.
    from e2e_baseline_generator import write_baseline_spec  # type: ignore
    from enrichment_schema import (  # type: ignore
        EnrichmentValidationError,
        validate_enrichment_file,
    )
    from enrichment_fallback import build_fallback_enrichment  # type: ignore
    from gitignore_check import check_paths_against_gitignore  # type: ignore
    from visual_docs_generator import generate_visual_docs  # type: ignore
    from prior_art_harvester import (  # type: ignore
        harvest_conventions, harvest_decision_log,
    )
    from test_acceptance_miner import mine_acceptance_criteria  # type: ignore
    from known_issues_inventory import write_known_issues_inventory  # type: ignore

    snapshot = _read_json(snapshot_path)
    routes = []
    if routes_path.exists():
        try:
            routes = json.loads(routes_path.read_text(encoding="utf-8"))
            if not isinstance(routes, list):
                routes = []
        except json.JSONDecodeError:
            routes = []

    # Enrichment loading (4.4): when present, validate strictly. When
    # missing, use a deterministic fallback that's clearly labeled — no
    # silent degradation to "snapshot+routes only" with hallucinated TBDs.
    enrichment_meta: dict[str, Any] = {}
    if enrichment_path.exists():
        try:
            enrichment = validate_enrichment_file(enrichment_path)
            enrichment_meta = {"source": "validated", "path": str(enrichment_path)}
        except EnrichmentValidationError as e:
            # Fail loud — don't pretend Layer-2 succeeded when it didn't.
            raise SystemExit(
                f"ERROR: enrichment.json at {enrichment_path} failed schema validation: {e}\n"
                f"  Re-run Layer-2 enrichment OR delete the file to use the fallback.\n"
            ) from e
    else:
        enrichment = build_fallback_enrichment(snapshot, routes)
        enrichment_meta = {"source": "fallback"}

    project_name = project_root.name
    profile = profile_override or snapshot.get("profile", {}).get("matched", "generic")
    scope = scope_override or "full_app"
    commit_sha = _current_commit(project_root)
    commands = snapshot.get("commands", {})
    stack = snapshot.get("stack", {})

    # Features: ADDITIVE union of AST + crawl (4.2). The previous code
    # silently dropped AST features whenever routes existed — meaning a
    # 20-route Hono backend got reduced to whatever the Vite SPA crawl
    # found (often 5 frontend pages). Now: union by route key, both
    # origins recorded, no duplicates.
    #
    # Fix 3a: filter test files out of AST features — they're not
    # functional requirements. Fix 5 mines them as ACs separately.
    ast_features = [
        f for f in (snapshot.get("features", []) or [])
        if not _is_test_path(f.get("source_file", ""))
    ]
    crawl_routes = routes or []

    merged_features: list[dict[str, Any]] = []
    seen_routes: set[str] = set()  # normalized route keys

    def _enrichment_match(route_key: str) -> dict[str, Any]:
        norm = _normalize_route(route_key)
        for e in enrichment.get("features", []):
            cand = e.get("route") or e.get("url", "")
            if _normalize_route(cand) == norm:
                return e
        return {}

    def _record_ac(feat: dict[str, Any], enrich: dict[str, Any]) -> None:
        """Fix 3b: pass through a real `acceptance_draft` as ACs. The
        sentinel "TBD" placeholder stays a placeholder. Fix 5 (test-AC
        miner) populates this list later when enrichment is empty.
        """
        feat["acceptance_draft"] = enrich.get("acceptance_draft") or "TBD"
        draft = (enrich.get("acceptance_draft") or "").strip()
        if draft and draft.lower() != "tbd":
            feat["acceptance_criteria"] = [draft]
            feat["acceptance_source"] = "enrichment"
        else:
            feat["acceptance_criteria"] = []
            feat["acceptance_source"] = ""

    # Crawl routes first — they typically have richer metadata (titles,
    # screenshots) that adopt's downstream consumers (E2E generator,
    # design extraction) rely on.
    for route in crawl_routes:
        url = route.get("url", "")
        norm = _normalize_route(url)
        if not norm or norm in seen_routes:
            continue
        seen_routes.add(norm)
        ast_match = next(
            (f for f in ast_features if _normalize_route(f.get("route", "")) == norm),
            {},
        )
        enrich = _enrichment_match(url)
        origin = "ast+crawl" if ast_match else "crawl"
        feat = {
            "route": url,
            "url": url,
            "source_file": ast_match.get("source_file") or route.get("source_file", "—"),
            "label": enrich.get("label") or route.get("title") or url,
            # Prefer the enrichment description (richest source).
            "description": enrich.get("description") or "TBD — refine via /shipwright-iterate",
            "origin": origin,
        }
        _record_ac(feat, enrich)
        merged_features.append(feat)

    # AST features that crawl didn't see (typically backend API routes
    # not reachable from the SPA's link graph). Without this loop the
    # adopt spec.md missed every API FR.
    for ast_f in ast_features:
        route_key = ast_f.get("route", "")
        norm = _normalize_route(route_key)
        if not norm or norm in seen_routes:
            continue
        seen_routes.add(norm)
        enrich = _enrichment_match(route_key)
        feat = {
            "route": route_key,
            "url": route_key,
            "source_file": ast_f.get("source_file", "—"),
            "label": enrich.get("label") or route_key,
            "description": enrich.get("description") or "TBD — refine via /shipwright-iterate",
            "framework": ast_f.get("framework"),
            "method": ast_f.get("method"),
            "origin": "ast",
        }
        _record_ac(feat, enrich)
        merged_features.append(feat)

    # Assign FR IDs after the union is known — preserves the 1..N sequence
    # the spec template expects.
    for i, feat in enumerate(merged_features, start=1):
        feat["fr_id"] = f"FR-01.{i:02d}"

    # Fix 5: mine sibling test files for ACs when enrichment didn't supply
    # any. Enrichment > tests > "TBD" — never overwrite a non-empty
    # enrichment AC. The miner is silent when no sibling test exists.
    for feat in merged_features:
        if feat.get("acceptance_criteria"):
            continue
        mined = mine_acceptance_criteria(project_root, feat.get("source_file", ""))
        if mined:
            feat["acceptance_criteria"] = mined
            feat["acceptance_source"] = "tests"

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

    # Prior-art harvest (Fix 2). Best-effort: when a recognized source exists,
    # the harvested content is appended to decision_log.md / conventions.md
    # with attribution. Absence is silent — fall back to today's behavior.
    # The conventions harvest is passed snapshot.excludes[] so harvested
    # CONTRIBUTING.md sections that reference excluded or absent paths
    # (e.g. `cd webui/client` after webui moved to a separate repo) get
    # `<!-- adopt-drift: ... -->` markers instead of silently inheriting
    # the drift (Iterate 2 Sub-2A).
    harvested_decisions_result = harvest_decision_log(project_root)
    harvested_conventions_result = harvest_conventions(
        project_root, excludes=nested_excluded,
    )
    user_facing_docs = _discover_user_facing_docs(project_root)
    changelog_link = _discover_changelog(project_root)
    harvested_decisions = (
        (harvested_decisions_result.content, harvested_decisions_result.source_path)
        if harvested_decisions_result is not None
        else None
    )
    harvested_conventions_t = (
        (harvested_conventions_result.content, harvested_conventions_result.source_path)
        if harvested_conventions_result is not None
        else None
    )

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
        harvested_decisions=harvested_decisions,
        harvested_conventions=harvested_conventions_t,
        user_facing_docs=user_facing_docs or None,
        changelog_link=changelog_link,
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

    # Step E.5 — .env.local scaffold. Runs AFTER write_all so
    # shipwright_run_config.json exists (validate_env reads `profile`
    # from it). Idempotent: never overwrites an existing .env.local;
    # the first run creates the file, subsequent runs append missing
    # keys only. Framework keys (OPENROUTER/GEMINI/OPENAI) are merged
    # in regardless of profile so external review keys land in every
    # adopted repo. The result rides on results["env_local"] which
    # the SKILL.md Step H banner renders.
    results["env_local"] = _scaffold_env_local(project_root)
    if results["env_local"].get("path") and Path(results["env_local"]["path"]).exists():
        # Track .env.local as a written artifact so the gitignore_report
        # below catches it. (.env.local is gitignored by design — it
        # SHOULD show up in the gitignored list, that's the safety
        # invariant, and the user already opted in to "keep going" via
        # the existing majority_gitignored prompt above.)
        results["written"].append(results["env_local"]["path"])

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

    # Hook is plugin-owned (registered in plugins/shipwright-iterate/hooks/hooks.json);
    # no per-project install. Result key kept so that any external tool that
    # introspects the JSON output keeps working — but reduced to a minimal
    # shape that fails LOUDLY (KeyError on legacy fields) for any caller
    # branching on the old installer schema, instead of silently mis-reading.
    results["hook_install"] = {
        "plugin_owned": True,
        "note": (
            "suggest_iterate UserPromptSubmit hook is registered in "
            "plugins/shipwright-iterate/hooks/hooks.json since "
            "iterate-20260505-plugin-hook-registration; no per-project install."
        ),
    }

    # E2E baseline (if routes.json present)
    if routes:
        spec_path = write_baseline_spec(project_root, routes)
        results["written"].append(str(spec_path))
        results["e2e_baseline_generated"] = True
    else:
        results["e2e_baseline_generated"] = False

    # Step E.13 — Security CI scaffold. Adopt is the entry point for
    # brownfield repos, so a missing .github/workflows/security.yml is the
    # default state — the scaffolder writes the dormant template. Existing
    # files (prior shipwright workflow, hand-rolled CodeQL, anything else)
    # are preserved bit-for-bit. See docs/security-ci-setup.md for activation
    # guidance and the convention lock at shared/scripts/lib/security_workflow.py.
    from security_workflow_scaffolder import scaffold_security_workflow  # type: ignore
    security_ci_result = scaffold_security_workflow(project_root)
    results["security_ci"] = security_ci_result
    if security_ci_result["wrote"]:
        results["written"].append(security_ci_result["path"])

    # Step E.13b — Gitleaks allowlist scaffold (companion to security.yml,
    # which runs `gitleaks detect --no-git` with no `--config` → auto-loads a
    # root `.gitleaks.toml`). Without it the sidekiq-secret rule false-matches
    # `cafebabe:deadbeef` and reddens every adopted repo's first scan (leadwright
    # 2026-06-07). Never-overwrite. SSoT: shared/scripts/lib/security_workflow.py.
    from gitleaks_config_scaffolder import scaffold_gitleaks_config  # type: ignore
    gitleaks_config_result = scaffold_gitleaks_config(project_root)
    results["gitleaks_config"] = gitleaks_config_result
    if gitleaks_config_result["wrote"]:
        results["written"].append(gitleaks_config_result["path"])

    # Step E.14 — CI workflow scaffold (profile-aware). Adopt picks the
    # right CI template per stack profile (vite-hono, supabase-nextjs,
    # python-plugin-monorepo) and lands a cross-platform-matrix template
    # at .github/workflows/ci.yml. Closes the gap that the shipwright-webui
    # v0.8.5 regression exposed: hand-written CI without a Windows runner
    # silently hid path-portability bugs.
    #
    # Profile name comes from snapshot.profile.matched (set by adopt's
    # stack detection earlier in the pipeline). Distinct reason codes
    # surface profile-detection failures upstream rather than masking
    # them as "no template available".
    from ci_workflow_scaffolder import scaffold_ci_workflow  # type: ignore
    profile_name = (snapshot.get("profile") or {}).get("matched")
    ci_result = scaffold_ci_workflow(project_root, profile_name=profile_name)
    results["ci_workflow"] = ci_result
    if ci_result["wrote"]:
        results["written"].append(ci_result["path"])

    # Step E.15 — Claude-Review workflow scaffold. Independent Claude Code
    # review-in-a-different-session pass on PRs — Anthropic Architect
    # Certification best practice (commit `8aac61d`). Profile-agnostic;
    # single template lands at .github/workflows/claude-review.yml. Not
    # dormant: fires on pull_request by design — that's the workflow's
    # entire purpose.
    from claude_review_workflow_scaffolder import (  # type: ignore
        scaffold_claude_review_workflow,
    )
    claude_review_result = scaffold_claude_review_workflow(project_root)
    results["claude_review_workflow"] = claude_review_result
    if claude_review_result["wrote"]:
        results["written"].append(claude_review_result["path"])

    # Tier 5 — Visual frontend documentation. Opt-in via signal: any
    # frontend hint in the snapshot (multi-service frontend service, or
    # frontend.* in stack). Backend-only profiles get wrote_docs=false
    # without writing anything to .shipwright/agent_docs/visual/.
    #
    # Frontend-root resolution priority (matches multi-service spec):
    #   1. `primary: true` service with a `root` field
    #   2. Service named frontend / client / web
    #   3. project_root (single-service or no signal)
    multi = (snapshot.get("stack") or {}).get("multi_service") or {}
    fe_root: Path = project_root
    if multi.get("detected"):
        services = multi.get("services") or []
        primary = next(
            (s for s in services if s.get("primary") and s.get("root")),
            None,
        )
        if primary is None:
            primary = next(
                (
                    s for s in services
                    if (s.get("name") or "").lower() in ("frontend", "client", "web")
                    and s.get("root")
                ),
                None,
            )
        if primary is not None and primary.get("root"):
            fe_root = project_root / primary["root"]
    visual_result = generate_visual_docs(project_root, frontend_root=fe_root)
    results["visual_docs"] = {
        "wrote_docs": visual_result["wrote_docs"],
        "component_count": visual_result["component_count"],
        "screenshots_persisted": visual_result["screenshots_persisted"],
        "frontend_root": str(fe_root),
    }
    if visual_result["wrote_docs"]:
        results["written"].append(str(visual_result["design_tokens"]))
        results["written"].append(str(visual_result["component_inventory"]))
        results["written"].append(str(visual_result["visual_guidelines"]))

    # Fix 6: pre-compute the TODO/FIXME inventory. /shipwright-iterate users
    # grep for these markers as their first step after onboarding — emit a
    # pre-grouped file even when zero markers are found, so operators
    # don't wonder if the scan ran.
    known_issues_result = write_known_issues_inventory(project_root)
    results["known_issues"] = {
        "total": known_issues_result["total"],
        "by_marker": known_issues_result["by_marker"],
        "truncated": known_issues_result["truncated"],
    }
    results["written"].append(str(known_issues_result["path"]))

    # 4.1 — Gitignore awareness. After all writes, check which output paths
    # would be excluded by the project's .gitignore. The SKILL.md handoff
    # surfaces this so the user doesn't discover it only at git status.
    rel_outputs = []
    for written in results["written"]:
        try:
            rel = str(Path(written).resolve().relative_to(project_root))
            rel_outputs.append(rel.replace("\\", "/"))
        except ValueError:
            continue  # outside project root — shouldn't happen but safe to skip
    gitignore_report = check_paths_against_gitignore(project_root, rel_outputs)
    results["gitignore_report"] = gitignore_report
    results["enrichment"] = enrichment_meta

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
