"""Write CLAUDE.md, .shipwright/agent_docs/*, .shipwright/planning/<split>/spec.md for adopted projects.

Slot-filling uses shared/templates/ exactly as shipwright-project does —
zero structural divergence from greenfield-generated docs.

Pre-existing user files (CLAUDE.md, .shipwright/agent_docs/decision_log.md, etc.) are
NEVER silently overwritten — see `preserve_existing.py` for the policy.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

AGENT_DOCS_DIR = ".shipwright/agent_docs"
LEGACY_AGENT_DOCS_DIRNAME = "agent_docs"

# Importable both via package-relative path (when called from generate_adoption_artifacts.py
# which adds scripts/lib to sys.path) and via direct test imports (`from lib.preserve_existing
# import ...`). Add the parent's parent (scripts/) so `lib.preserve_existing` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.preserve_existing import (  # noqa: E402
    merge_decision_log,
    parse_max_adr_id,
    preserve_if_exists,
    record_preservation_action,
)
from lib.render_helpers import _fmt_stack_line, _utc_today  # noqa: E402
# `write_claude_md` lives with the render it writes (claude_md_renderer); this
# module re-exports both so existing importers keep working, the same way
# `write_spec` / `_render_spec_md` are re-exported from `spec_document` below.
from lib.claude_md_renderer import (  # noqa: E402,F401
    _render_claude_md,
    write_claude_md,
)
# The planning spec lives in `spec_document` (this module is grandfathered at
# its bloat ceiling, the same reason `spec_table` was split out). Re-exported so
# existing callers keep importing `write_spec` / `_render_spec_md` from here.
from lib.spec_document import _render_spec_md, write_spec  # noqa: E402,F401
# ADR-spec-folder seeding lives in `adr_seeding` — same bloat-ceiling reason as
# the two splits above (this module hit its own ceiling adding it). Re-exported
# so existing importers/tests keep using these names from `artifact_writer`.
from lib.adr_seeding import (  # noqa: E402,F401
    ADR_SPEC_FOLDER,
    _adoption_adr_fields,
    _derive_commit_subject,
    _max_seeded_adr_number,
    _refresh_adr_index,
    _resolve_retroactive_adrs,
    _seed_adr_spec_folder,
)


# Adopt's output canon: ADR ids are 3-digit zero-padded. We refuse to
# serialise a 4-digit id even if the counter says so (Shipwright never
# expected that, and the downstream parsers in shared/scripts/lib/
# drift_parsers.py + group_g.py treat 4-digit ids as a smell). If a
# real project ever reaches >999 ADRs, that's a Shipwright-wide
# convention upgrade, not a silent serialisation choice in adopt.
ADR_OUTPUT_MAX_NUMBER = 999

# Architecture-marker format. The marker lives on line 2 of architecture.md
# (after the H1 title) and lets the Iterate-C drift detector compare the
# last-sync SHA against new ADRs with `architecture_impact ∈ {component,
# data-flow}` since that commit. Bump ``v=`` whenever the marker grammar
# changes; parsers stay tolerant of older versions ("v=1 / no marker"
# behaves as "no last_sync recorded").
ARCHITECTURE_MARKER_VERSION = 2
NO_ARCHITECTURE_SYNC = "no-sync-recorded"
_ARCHITECTURE_MARKER_RE = re.compile(
    r"<!--\s*shipwright:architecture\s+v=(?P<version>\d+)\s+last-sync=(?P<sha>\S+)\s*-->"
)
_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


def render_architecture_marker(commit_sha: str | None) -> str:
    """Render the architecture drift-detection HTML comment marker."""
    if commit_sha and _COMMIT_SHA_RE.match(commit_sha):
        last_sync = commit_sha
    else:
        last_sync = NO_ARCHITECTURE_SYNC
    return (
        f"<!-- shipwright:architecture v={ARCHITECTURE_MARKER_VERSION} "
        f"last-sync={last_sync} -->"
    )


def parse_architecture_marker(content: str) -> dict[str, str] | None:
    """Parse the architecture marker out of architecture.md content.

    Returns ``None`` when no marker is present (pre-marker era — drift
    detector should treat this as "no last_sync known"). A marker with
    an invalid SHA is normalised to ``NO_ARCHITECTURE_SYNC`` so callers
    can rely on the sha being either a real commit or that sentinel.
    """
    match = _ARCHITECTURE_MARKER_RE.search(content)
    if not match:
        return None
    sha = match.group("sha")
    if sha != NO_ARCHITECTURE_SYNC and not _COMMIT_SHA_RE.match(sha):
        sha = NO_ARCHITECTURE_SYNC
    return {"version": match.group("version"), "last_sync": sha}


def _next_adr_start_number(project_root: Path) -> int:
    """Pick the next free ADR id for adopt's adoption + retroactive entries:
    ``max(decision_log.md's highest id, ADR_SPEC_FOLDER's highest seeded
    number) + 1`` — the folder side keeps a Step E re-run from reissuing (and
    duplicating) a number it already seeded, even if decision_log.md is
    behind. Returns 1 (ADR-001) when nothing existing is found.
    """
    log_max = 0
    log_path = project_root / AGENT_DOCS_DIR / "decision_log.md"
    if log_path.is_file():
        try:
            log_max = parse_max_adr_id(log_path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            log_max = 0
    max_id = max(log_max, _max_seeded_adr_number(project_root))
    return max_id + 1 if max_id > 0 else 1


def _render_architecture_md(
    *,
    project_name: str,
    stack: dict[str, Any],
    layers: list[dict[str, Any]],
    architecture_diagram: str,
    data_flow_description: str,
    profile_name: str,
    see_also_links: list[str] | None = None,
    commit_sha: str | None = None,
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
    see_also = ""
    if see_also_links:
        bullets = "\n".join(f"- [`{link}`](../../{link})" for link in see_also_links)
        see_also = (
            "\n## See also\n\n"
            "_Existing user-facing documentation discovered by /shipwright-adopt._\n\n"
            + bullets + "\n"
        )
    marker = render_architecture_marker(commit_sha)
    return f"""# Architecture — {project_name}
{marker}

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
{see_also}"""


def _render_conventions_md(
    *,
    project_name: str,
    conventions: dict[str, Any],
    conventions_prose: str,
    harvested_conventions: tuple[str, str] | None = None,
) -> str:
    """Render conventions.md.

    `harvested_conventions` is an optional `(content, source_path)` tuple
    produced by `prior_art_harvester.harvest_conventions`. When present,
    the harvested content is appended verbatim after the auto-detected
    block with an attribution header. No merging — the auto-section is
    short and the imported section is rich; concatenation keeps both
    visible without the risk of silent edits.
    """
    linter = conventions.get("linter") or "_none detected_"
    formatter = conventions.get("formatter") or "_none detected_"
    ts_strict = "yes" if conventions.get("tsconfig_strict") else "no"
    ec = conventions.get("editorconfig") or {}
    ec_line = ", ".join(f"{k}={v}" for k, v in ec.items()) if ec else "_none_"

    base = f"""# Conventions — {project_name}

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
    if harvested_conventions is not None:
        content, source = harvested_conventions
        base += (
            f"\n---\n\n## Imported from `{source}`\n\n"
            f"_Copied verbatim by /shipwright-adopt during onboarding. "
            f"Edit in place; future adopt re-runs back this file up to "
            f"`.shipwright/adopt/backups/`._\n\n"
            f"{content.strip()}\n"
        )
    return base


def _render_decision_log(
    *,
    project_name: str,
    profile: str,
    scope: str,
    commit_sha: str | None,
    features_count: int,
    retroactive_adrs: list[dict[str, Any]],
    harvested_decisions: tuple[str, str] | None = None,
    start_adr_number: int = 1,
    today: str | None = None,
) -> str:
    """Render decision_log.md.

    `start_adr_number` is the numeric id assigned to the adoption ADR.
    Defaults to 1 (greenfield). When an existing decision_log.md is
    present, callers compute ``max + 1`` via ``_next_adr_start_number``
    and pass it here so adopt does not silently collide with already-
    written user ADRs.

    Output canon is 3-digit zero-padded — adopt refuses to serialise a
    4-digit id even if the counter exceeds 999 (``ADR_OUTPUT_MAX_NUMBER``);
    an overflow raises ``ValueError`` so the operator audits the existing
    log rather than silently inherit non-canonical ids.

    `harvested_decisions` is an optional `(content, source_path)` tuple
    produced by `prior_art_harvester.harvest_decision_log`. When present,
    the harvested content is appended verbatim AFTER the adopt adoption +
    retroactive ADRs, with an attribution header. The harvested entries
    keep their original numbering — adopt's "Adopted into Shipwright SDLC"
    entry is the *latest* in the log, with the prior art preserved
    underneath it.
    """
    if start_adr_number < 1:
        raise ValueError(
            f"start_adr_number must be >= 1, got {start_adr_number}",
        )
    last_id = start_adr_number + len(retroactive_adrs)
    if last_id > ADR_OUTPUT_MAX_NUMBER:
        raise ValueError(
            f"adopt would render an ADR id beyond {ADR_OUTPUT_MAX_NUMBER:03d} "
            f"(start={start_adr_number}, retroactive={len(retroactive_adrs)}, "
            f"last={last_id}). Audit BOTH decision_log.md AND {ADR_SPEC_FOLDER}/ "
            f"for non-canonical ADR ids — canon is 3-digit zero-padded.",
        )
    today = today or _utc_today()
    commit = commit_sha or "HEAD"
    fields = _adoption_adr_fields(features_count=features_count, profile=profile, scope=scope)
    harvest_note = (
        f"\n_This log was bootstrapped from existing prior art at "
        f"`{harvested_decisions[1]}` — see the **Imported decisions** "
        f"section below for the verbatim contents._\n"
        if harvested_decisions is not None
        else ""
    )
    # ADR heading is H3 to match Shipwright's compact-form canon
    # (`shared/scripts/tools/write_decision_log.py` and the H3 form
    # parsed by `shared/scripts/lib/adr_headers.py:parse_adr_headers`).
    # Sub-sections move to H4 to preserve hierarchy under the H3 ADR.
    header = f"""# Decision Log — {project_name}
{harvest_note}
### ADR-{start_adr_number:03d}: Adopt this repository into the Shipwright SDLC

- **Status**: accepted
- **Date**: {today}
- **Commit**: `{commit}`

#### Context

{fields["context"]}

#### Decision

{fields["decision"]}

#### Consequences

{fields["consequences"]}

#### Rejected alternatives

{fields["rejected"]}

---
"""
    body = header
    for idx, adr in enumerate(retroactive_adrs, start=start_adr_number + 1):
        # "unknown" matches _seed_adr_spec_folder's fallback for the same
        # legal case (subject present, sha absent) so the two copies of
        # this ADR never disagree about what they know.
        sha = adr.get("sha") or "unknown"
        subject = adr.get("subject", "(no subject)")
        context = adr.get("context", "—")
        decision = adr.get("decision", "—")
        consequences = adr.get("consequences", "—")
        body += f"""
### ADR-{idx:03d}: {subject}

- **Status**: accepted (retroactive, llm-inferred)
- **Commit**: `{sha}`

#### Context
{context}

#### Decision
{decision}

#### Consequences
{consequences}

---
"""
    if harvested_decisions is not None:
        content, source = harvested_decisions
        body += (
            f"\n## Imported decisions (verbatim from `{source}`)\n\n"
            f"_Copied during /shipwright-adopt onboarding. Original ADR numbering "
            f"and ordering preserved. Future decisions land above this section — "
            f"their canonical spec home is `{ADR_SPEC_FOLDER}/` (see "
            f"`{ADR_SPEC_FOLDER}/INDEX.md`) — never within it._\n\n"
            f"{content.strip()}\n"
        )
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
    changelog_link: str | None = None,
) -> str:
    loc_block = ""
    for layer, loc in sorted(loc_by_layer.items()):
        loc_block += f"- **{layer}**: {loc:,} LOC\n"
    if not loc_block:
        loc_block = "_No layers tallied._\n"
    excluded_block = ", ".join(f"`{p}`" for p in nested_excluded) if nested_excluded else "_none_"
    changelog_block = ""
    if changelog_link:
        changelog_block = (
            "\n## See also\n\n"
            f"- [`{changelog_link}`](../../{changelog_link}) — release history "
            "(future entries via /shipwright-changelog).\n"
        )
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
{changelog_block}"""



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
    harvested_decisions: tuple[str, str] | None = None,
    harvested_conventions: tuple[str, str] | None = None,
    user_facing_docs: list[str] | None = None,
    changelog_link: str | None = None,
) -> list[Path]:
    """Write the four agent_docs artifacts, plus adopt's own seed of the
    canonical ADR-spec folder, with preservation guardrails.

    architecture.md / conventions.md / build_dashboard.md are backed up to
    `.preserved` before being overwritten. decision_log.md uses
    `merge_decision_log` so any existing user ADRs survive verbatim.
    `.shipwright/planning/adr/` is seeded with the same adoption ADR (and
    any retroactive ADRs) decision_log.md carries inline — see
    `_seed_adr_spec_folder` for why both copies exist."""
    # Fail closed BEFORE any write (trg-6b59524b) — a retry after a raise must
    # not overwrite architecture.md/conventions.md's OWN backups with adopt's
    # already-written output (preserve_if_exists replaces the prior backup).
    retroactive_adrs = _resolve_retroactive_adrs(project_root, retroactive_adrs)

    agent_docs = project_root / AGENT_DOCS_DIR
    agent_docs.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    today = _utc_today()

    # architecture.md — backup + overwrite
    arch_rel = f"{AGENT_DOCS_DIR}/architecture.md"
    arch = agent_docs / "architecture.md"
    arch_backup = preserve_if_exists(project_root, arch_rel)
    arch.write_text(_render_architecture_md(
        project_name=project_name, stack=stack, layers=layers,
        architecture_diagram=architecture_diagram,
        data_flow_description=data_flow_description, profile_name=profile,
        see_also_links=user_facing_docs,
        commit_sha=commit_sha,
    ), encoding="utf-8")
    record_preservation_action(
        project_root,
        file=arch_rel,
        action=("overwritten_with_backup" if arch_backup else "written_fresh"),
        backup_path=arch_backup,
    )
    paths.append(arch)

    # conventions.md — backup + overwrite
    conv_rel = f"{AGENT_DOCS_DIR}/conventions.md"
    conv = agent_docs / "conventions.md"
    conv_backup = preserve_if_exists(project_root, conv_rel)
    conv.write_text(_render_conventions_md(
        project_name=project_name, conventions=conventions,
        conventions_prose=conventions_prose,
        harvested_conventions=harvested_conventions,
    ), encoding="utf-8")
    record_preservation_action(
        project_root,
        file=conv_rel,
        action=("overwritten_with_backup" if conv_backup else "written_fresh"),
        backup_path=conv_backup,
    )
    paths.append(conv)

    # decision_log.md — backup + merge (preserves historical ADRs verbatim)
    #
    # Pick the next free ADR id BEFORE rendering so the adoption ADR
    # never collides with already-written user ADRs. With an existing
    # log of e.g. ADR-001..ADR-058 the adoption ADR becomes ADR-059
    # (and any retroactive ADRs continue from ADR-060). Without an
    # existing log adoption is ADR-001 as before.
    dec_rel = f"{AGENT_DOCS_DIR}/decision_log.md"
    dec = agent_docs / "decision_log.md"
    start_adr = _next_adr_start_number(project_root)
    new_log = _render_decision_log(
        project_name=project_name, profile=profile, scope=scope,
        commit_sha=commit_sha, features_count=features_count,
        retroactive_adrs=retroactive_adrs,
        harvested_decisions=harvested_decisions,
        start_adr_number=start_adr,
        today=today,
    )
    dec_backup = preserve_if_exists(project_root, dec_rel)
    if dec.exists():
        merged_content, info = merge_decision_log(
            new_log, dec, adoption_adr_id=start_adr,
        )
        dec.write_text(merged_content, encoding="utf-8")
        record_preservation_action(
            project_root,
            file=dec_rel,
            action=info["action"],
            backup_path=dec_backup,
            note=f"existing_adrs={info['existing_adrs']}",
        )
    else:
        dec.write_text(new_log, encoding="utf-8")
        record_preservation_action(
            project_root,
            file=dec_rel,
            action="written_fresh",
            backup_path=None,
        )
    paths.append(dec)

    # .shipwright/planning/adr/ — seed with adopt's own minted ADRs (the
    # adoption ADR + retroactive ADRs), using the SAME start_adr /
    # retroactive_adrs the decision_log.md entry above just rendered, so
    # numbering never disagrees between the two copies (trg-50efc4c8).
    seeded = _seed_adr_spec_folder(
        project_root,
        start_adr_number=start_adr,
        today=today,
        commit_sha=commit_sha,
        adoption_fields=_adoption_adr_fields(
            features_count=features_count, profile=profile, scope=scope,
        ),
        retroactive_adrs=retroactive_adrs,
    )
    paths.extend(seeded)
    index_warning = _refresh_adr_index(project_root)
    if index_warning:
        print(f"WARNING: {index_warning}", file=sys.stderr)
    else:
        # A success writes a real file — feed it into `paths` so the
        # gitignore check (reads results["written"]) sees it too (doubt-reviewer, round 4).
        paths.append(project_root / ADR_SPEC_FOLDER / "INDEX.md")

    # build_dashboard.md — backup + overwrite (transient state, regenerated each run)
    dash_rel = f"{AGENT_DOCS_DIR}/build_dashboard.md"
    dash = agent_docs / "build_dashboard.md"
    dash_backup = preserve_if_exists(project_root, dash_rel)
    dash.write_text(_render_build_dashboard(
        project_name=project_name, profile=profile, scope=scope,
        features_count=features_count, commits_total=commits_total,
        contributors_total=contributors_total, nested_excluded=nested_excluded,
        loc_by_layer=loc_by_layer,
        changelog_link=changelog_link,
    ), encoding="utf-8")
    record_preservation_action(
        project_root,
        file=dash_rel,
        action=("overwritten_with_backup" if dash_backup else "written_fresh"),
        backup_path=dash_backup,
    )
    paths.append(dash)

    return paths


