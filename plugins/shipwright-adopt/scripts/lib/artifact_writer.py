"""Write CLAUDE.md, agent_docs/*, .shipwright/planning/<split>/spec.md for adopted projects.

Slot-filling uses shared/templates/ exactly as shipwright-project does —
zero structural divergence from greenfield-generated docs.

Pre-existing user files (CLAUDE.md, agent_docs/decision_log.md, etc.) are
NEVER silently overwritten — see `preserve_existing.py` for the policy.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Importable both via package-relative path (when called from generate_adoption_artifacts.py
# which adds scripts/lib to sys.path) and via direct test imports (`from lib.preserve_existing
# import ...`). Add the parent's parent (scripts/) so `lib.preserve_existing` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.preserve_existing import (  # noqa: E402
    SUGGESTED_CLAUDE_REL,
    is_loadbearing_claude_md,
    merge_decision_log,
    preserve_if_exists,
    record_preservation_action,
)


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _fmt_stack_line(stack_group: dict[str, str]) -> str:
    if not stack_group:
        return "—"
    return ", ".join(sorted(stack_group.keys()))


def _render_claude_md(
    *,
    project_name: str,
    profile: str,
    stack: dict[str, Any],
    commands: dict[str, str | None],
    product_description: str,
) -> str:
    runtime = _fmt_stack_line(stack.get("runtime", {}))
    frontend = _fmt_stack_line(stack.get("frontend", {}))
    backend = _fmt_stack_line(stack.get("backend", {}))
    database = _fmt_stack_line(stack.get("database", {}))
    auth = _fmt_stack_line(stack.get("auth", {}))
    build_cmd = commands.get("build") or "—"
    test_cmd = commands.get("test") or "—"
    dev_cmd = commands.get("dev") or "—"
    return f"""# {project_name}

## WHAT
{product_description}

## Stack
- **Runtime**: {runtime}
- **Frontend**: {frontend}
- **Backend**: {backend}
- **Database**: {database}
- **Auth**: {auth}
- **Profile**: `{profile}`

## HOW

### Development
```bash
{dev_cmd}
```

### Build
```bash
{build_cmd}
```

### Test
```bash
{test_cmd}
```

## Ongoing Changes
This project was adopted into Shipwright on {_utc_today()}. Prior code history is preserved.
Use `/shipwright-iterate` for all future changes. Do NOT use `/shipwright-project`, `/shipwright-plan`, or `/shipwright-build` directly on this repo.

See `agent_docs/decision_log.md` ADR-0001 for the adoption decision.
"""


def _render_architecture_md(
    *,
    project_name: str,
    stack: dict[str, Any],
    layers: list[dict[str, Any]],
    architecture_diagram: str,
    data_flow_description: str,
    profile_name: str,
) -> str:
    runtime = _fmt_stack_line(stack.get("runtime", {}))
    frontend = _fmt_stack_line(stack.get("frontend", {}))
    backend = _fmt_stack_line(stack.get("backend", {}))
    database = _fmt_stack_line(stack.get("database", {}))
    auth = _fmt_stack_line(stack.get("auth", {}))
    layers_block = ""
    for layer in layers:
        paths_fmt = ", ".join(f"`{p}`" for p in layer["paths"])
        layers_block += f"- **{layer['name']}**: {paths_fmt}\n"
    if not layers_block:
        layers_block = "_No layers detected._\n"
    return f"""# Architecture — {project_name}

## System Overview

{architecture_diagram}

## Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Frontend | {frontend} | — |
| Backend | {backend} | — |
| Database | {database} | — |
| Auth | {auth} | — |
| Runtime | {runtime} | — |

## Layers Detected

{layers_block}

## Key Architecture Decisions

See `decision_log.md` for detailed ADRs. Profile-level decisions (stack, auth pattern, DB strategy, folder structure) are defined by the stack profile (`{profile_name}`).

## Data Flow

{data_flow_description}
"""


def _render_conventions_md(
    *,
    project_name: str,
    conventions: dict[str, Any],
    conventions_prose: str,
) -> str:
    linter = conventions.get("linter") or "_none detected_"
    formatter = conventions.get("formatter") or "_none detected_"
    ts_strict = "yes" if conventions.get("tsconfig_strict") else "no"
    ec = conventions.get("editorconfig") or {}
    ec_line = ", ".join(f"{k}={v}" for k, v in ec.items()) if ec else "_none_"
    return f"""# Conventions — {project_name}

## Linter / Formatter

- **Linter**: {linter}
- **Formatter**: {formatter}
- **TypeScript strict**: {ts_strict}
- **.editorconfig**: {ec_line}

## Project-specific rules

{conventions_prose}

## Commit messages

- Use Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- Scopes should reflect module boundaries (e.g., `feat(auth): ...`)

## Files

- Keep files under 300 lines; split larger modules.
- Tests live alongside implementation with `.test.*` / `_test.*` suffix OR in a `tests/` directory — whichever is consistent with the rest of the codebase.
"""


def _render_decision_log(
    *,
    project_name: str,
    profile: str,
    scope: str,
    commit_sha: str | None,
    features_count: int,
    retroactive_adrs: list[dict[str, Any]],
) -> str:
    today = _utc_today()
    commit = commit_sha or "HEAD"
    header = f"""# Decision Log — {project_name}

## ADR-0001: Adopt this repository into the Shipwright SDLC

- **Status**: accepted
- **Date**: {today}
- **Commit**: `{commit}`

### Context

This repository existed with {features_count} detected feature(s) and substantive git history before /shipwright-adopt ran. The goal is to bring it under the Shipwright SDLC (CLAUDE.md + agent_docs + .shipwright/planning/ + compliance/ + configs) without disrupting the existing codebase.

### Decision

Adopted into Shipwright using profile `{profile}` and scope `{scope}`. Retroactively marked `completed_steps = ["project", "plan", "build", "test"]` so that `/shipwright-iterate` and downstream skills (`/shipwright-compliance`, `/shipwright-test`) work as on a natively-built project.

### Consequences

- Future changes MUST go through `/shipwright-iterate` (not `/shipwright-project`/`/shipwright-plan`/`/shipwright-build`).
- Compliance reports (RTM, SBOM, change-history) are seeded; test-evidence starts collecting from the first `/shipwright-test` run.
- Any existing E2E baseline auto-generated by Adopt (under `e2e/flows/adopted-baseline.spec.ts`) is a regression guard, not a substitute for real acceptance tests.

### Rejected alternatives

- Manual `/shipwright-project` init: would lose git history and force re-description of existing code.
- No adoption (ad-hoc `/shipwright-iterate`): would mean missing configs, no compliance reports, and the audit pipeline would silently no-op.

---
"""
    body = header
    for idx, adr in enumerate(retroactive_adrs, start=2):
        sha = adr.get("sha", "")
        subject = adr.get("subject", "(no subject)")
        context = adr.get("context", "—")
        decision = adr.get("decision", "—")
        consequences = adr.get("consequences", "—")
        body += f"""
## ADR-{idx:04d}: {subject}

- **Status**: accepted (retroactive, llm-inferred)
- **Commit**: `{sha}`

### Context
{context}

### Decision
{decision}

### Consequences
{consequences}

---
"""
    return body


def _render_build_dashboard(
    *,
    project_name: str,
    profile: str,
    scope: str,
    features_count: int,
    commits_total: int,
    contributors_total: int,
    nested_excluded: list[str],
    loc_by_layer: dict[str, int],
) -> str:
    loc_block = ""
    for layer, loc in sorted(loc_by_layer.items()):
        loc_block += f"- **{layer}**: {loc:,} LOC\n"
    if not loc_block:
        loc_block = "_No layers tallied._\n"
    excluded_block = ", ".join(f"`{p}`" for p in nested_excluded) if nested_excluded else "_none_"
    return f"""# Build Dashboard — {project_name}

## Adoption Snapshot

- **Date**: {_utc_today()}
- **Profile**: `{profile}`
- **Scope**: `{scope}`
- **Features detected**: {features_count}
- **Git commits (total)**: {commits_total}
- **Contributors (total)**: {contributors_total}
- **Excluded nested projects**: {excluded_block}

## LOC by Layer

{loc_block}

## Pipeline Status

| Phase | Status |
|-------|--------|
| project | adopted |
| design | not run |
| plan | adopted |
| build | adopted |
| test | adopted (no evidence yet — will populate from next /shipwright-test run) |
| changelog | not run |
| deploy | not run |
| compliance | seeded |
"""


def _render_spec_md(
    *,
    project_name: str,
    split_name: str,
    product_description: str,
    features: list[dict[str, Any]],
    qr_items: list[str],
    constraints: list[str],
) -> str:
    today = _utc_today()
    fr_table_rows = ""
    for f in features:
        fr_id = f.get("fr_id", "FR-01.?")
        label = f.get("label", f.get("route", "?"))
        desc = f.get("description", "TBD — refine via /shipwright-iterate")
        source = f.get("source_file", f.get("url", "—"))
        fr_table_rows += f"| {fr_id} | {label} | Must | {desc} | `{source}` |\n"
    if not fr_table_rows:
        fr_table_rows = "| FR-01.01 | _no features detected_ | May | Edit manually after adoption | — |\n"
    qr_block = ""
    for idx, qr in enumerate(qr_items, start=1):
        qr_block += f"- **QR-{idx:02d}**: {qr}\n"
    if not qr_block:
        qr_block = "_No quality requirements inferred._\n"
    constraint_block = ""
    for idx, c in enumerate(constraints, start=1):
        constraint_block += f"- **C-{idx:02d}**: {c}\n"
    if not constraint_block:
        constraint_block = "_No constraints inferred._\n"
    return f"""# Specification — {project_name} / {split_name}

_Generated by /shipwright-adopt on {today}. Refine via /shipwright-iterate._

## Abstract

{product_description}

## Functional Requirements

| ID | Name | Priority | Description | Source |
|----|------|----------|-------------|--------|
{fr_table_rows}

## Quality Requirements

{qr_block}

## Constraints

{constraint_block}

## Acceptance Criteria

Acceptance criteria per FR are placeholders (`TBD`) — refine them with explicit behavior expectations as features evolve via `/shipwright-iterate`.

The auto-generated E2E baseline at `e2e/flows/adopted-baseline.spec.ts` (if Playwright crawl succeeded) covers mechanical rendering / visibility checks, not semantic behavior.
"""


def write_claude_md(
    project_root: Path,
    *,
    project_name: str,
    profile: str,
    stack: dict[str, Any],
    commands: dict[str, str | None],
    product_description: str,
) -> Path:
    """Write CLAUDE.md with load-bearing-content protection.

    If an existing CLAUDE.md is larger than the load-bearing threshold
    (~1 KB), it's preserved untouched and the adopt-generated content
    is written to `.shipwright/adopt/CLAUDE.md.adopt-suggested` instead.
    Smaller existing files are backed up to `.preserved` and then
    overwritten. The returned path is the file that actually received
    the new content (either the real CLAUDE.md or the suggested side-file).
    """
    content = _render_claude_md(
        project_name=project_name, profile=profile, stack=stack,
        commands=commands, product_description=product_description,
    )
    path = project_root / "CLAUDE.md"
    backup = preserve_if_exists(project_root, "CLAUDE.md")
    if path.exists() and is_loadbearing_claude_md(path):
        suggested = project_root / SUGGESTED_CLAUDE_REL
        suggested.parent.mkdir(parents=True, exist_ok=True)
        suggested.write_text(content, encoding="utf-8")
        record_preservation_action(
            project_root,
            file="CLAUDE.md",
            action="skipped_loadbearing",
            backup_path=backup,
            note=f"existing CLAUDE.md > {is_loadbearing_claude_md.__defaults__[0] if is_loadbearing_claude_md.__defaults__ else 1024} bytes; adopt suggestion at {SUGGESTED_CLAUDE_REL}",
        )
        return suggested
    path.write_text(content, encoding="utf-8")
    record_preservation_action(
        project_root,
        file="CLAUDE.md",
        action=("overwritten_with_backup" if backup else "written_fresh"),
        backup_path=backup,
    )
    return path


def write_agent_docs(
    project_root: Path,
    *,
    project_name: str,
    profile: str,
    scope: str,
    stack: dict[str, Any],
    layers: list[dict[str, Any]],
    loc_by_layer: dict[str, int],
    architecture_diagram: str,
    data_flow_description: str,
    conventions: dict[str, Any],
    conventions_prose: str,
    features_count: int,
    commits_total: int,
    contributors_total: int,
    nested_excluded: list[str],
    commit_sha: str | None,
    retroactive_adrs: list[dict[str, Any]],
) -> list[Path]:
    """Write the four agent_docs artifacts with preservation guardrails.

    architecture.md / conventions.md / build_dashboard.md are backed up to
    `.preserved` before being overwritten. decision_log.md uses
    `merge_decision_log` so any existing user ADRs survive verbatim.
    """
    agent_docs = project_root / "agent_docs"
    agent_docs.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    # architecture.md — backup + overwrite
    arch = agent_docs / "architecture.md"
    arch_backup = preserve_if_exists(project_root, "agent_docs/architecture.md")
    arch.write_text(_render_architecture_md(
        project_name=project_name, stack=stack, layers=layers,
        architecture_diagram=architecture_diagram,
        data_flow_description=data_flow_description, profile_name=profile,
    ), encoding="utf-8")
    record_preservation_action(
        project_root,
        file="agent_docs/architecture.md",
        action=("overwritten_with_backup" if arch_backup else "written_fresh"),
        backup_path=arch_backup,
    )
    paths.append(arch)

    # conventions.md — backup + overwrite
    conv = agent_docs / "conventions.md"
    conv_backup = preserve_if_exists(project_root, "agent_docs/conventions.md")
    conv.write_text(_render_conventions_md(
        project_name=project_name, conventions=conventions,
        conventions_prose=conventions_prose,
    ), encoding="utf-8")
    record_preservation_action(
        project_root,
        file="agent_docs/conventions.md",
        action=("overwritten_with_backup" if conv_backup else "written_fresh"),
        backup_path=conv_backup,
    )
    paths.append(conv)

    # decision_log.md — backup + merge (preserves historical ADRs verbatim)
    dec = agent_docs / "decision_log.md"
    new_log = _render_decision_log(
        project_name=project_name, profile=profile, scope=scope,
        commit_sha=commit_sha, features_count=features_count,
        retroactive_adrs=retroactive_adrs,
    )
    dec_backup = preserve_if_exists(project_root, "agent_docs/decision_log.md")
    if dec.exists():
        merged_content, info = merge_decision_log(new_log, dec)
        dec.write_text(merged_content, encoding="utf-8")
        record_preservation_action(
            project_root,
            file="agent_docs/decision_log.md",
            action=info["action"],
            backup_path=dec_backup,
            note=f"existing_adrs={info['existing_adrs']}",
        )
    else:
        dec.write_text(new_log, encoding="utf-8")
        record_preservation_action(
            project_root,
            file="agent_docs/decision_log.md",
            action="written_fresh",
            backup_path=None,
        )
    paths.append(dec)

    # build_dashboard.md — backup + overwrite (transient state, regenerated each run)
    dash = agent_docs / "build_dashboard.md"
    dash_backup = preserve_if_exists(project_root, "agent_docs/build_dashboard.md")
    dash.write_text(_render_build_dashboard(
        project_name=project_name, profile=profile, scope=scope,
        features_count=features_count, commits_total=commits_total,
        contributors_total=contributors_total, nested_excluded=nested_excluded,
        loc_by_layer=loc_by_layer,
    ), encoding="utf-8")
    record_preservation_action(
        project_root,
        file="agent_docs/build_dashboard.md",
        action=("overwritten_with_backup" if dash_backup else "written_fresh"),
        backup_path=dash_backup,
    )
    paths.append(dash)

    return paths


def write_spec(
    project_root: Path,
    *,
    project_name: str,
    split_name: str,
    product_description: str,
    features: list[dict[str, Any]],
    qr_items: list[str],
    constraints: list[str],
) -> Path:
    split_dir = project_root / ".shipwright" / "planning" / split_name
    split_dir.mkdir(parents=True, exist_ok=True)
    spec = split_dir / "spec.md"
    spec.write_text(_render_spec_md(
        project_name=project_name, split_name=split_name,
        product_description=product_description, features=features,
        qr_items=qr_items, constraints=constraints,
    ), encoding="utf-8")
    return spec
