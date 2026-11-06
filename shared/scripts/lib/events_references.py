"""Reference-based guard data for the event log (issue 978, campaign S3, kill criterion 2).

Every NON-TEST file under ``plugins/``, ``shared/``, ``docs/`` and ``scripts/`` that
mentions the legacy event-log name ``shipwright_events.jsonl`` or one of its aliases
(``EVENT_FILE``, ``EVENTS_LOG``, ``EVENT_LOG_NAME``, ``resolve_events_path`` ...) must
appear in :data:`REGISTRY` with a TAG saying what it does with it. An unregistered file
is an unclassified occurrence and fails ``shared/tests/test_events_reference_guard.py``;
so does a registered file that no longer mentions the name (a migrated file must leave
the registry, it must not rot there).

The tags, and the structural rule each carries:

``R`` reader      reads events; must go through the assembling reader (one of
                  :data:`READER_MARKERS`), so it sees archive and drop files too.
``C`` classifier  decides whether a PATH is bookkeeping / churn / generated / uncounted;
                  must list ALL three folders (:data:`FOLDERS`) or use ``EVENT_FOLDERS``.
``L`` lister      reports that the log exists; must look at the drops folder.
``W`` writer      writes events or the log file. S4 owns these (writers stay dormant).
``S`` ssot        the resolver / reader / layout modules themselves.
``M`` marker      the name only labels something (an artifact list, an argument default).
``P`` prose       prompts, docs, docstrings, messages and templates that name the file.

Aliases: a module-level name bound to the literal may only be one of
:data:`KNOWN_ALIASES`, and an import may not rename one (``import X as Y`` would hide it).

Stdlib only; the registry is data, the scan lives in :func:`scan`.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path, PurePosixPath

from .events_log import EVENT_FILE, EVENT_FOLDERS

KNOWN_ALIASES = frozenset({"EVENT_FILE", "EVENTS_LOG", "EVENT_LOG_NAME", "_EVENT_FILE"})
RESOLVERS = ("resolve_events_path", "_resolve_events_path")
#: Module-level names BUILT FROM the log name (a tuple/path holding it). Their importers are scanned too.
#: The distinctive ones, whose importers/users are scanned for too (the rest are generic names such as
#: ``CONFIG_FILES`` that other modules reuse for unrelated sets, so they are only allowed as targets).
TRACKED_DERIVED = frozenset({"UNION_PATHS", "APPEND_ONLY_INPUTS"})
DERIVED_ALIASES = frozenset({
    "UNION_PATHS", "APPEND_ONLY_INPUTS", "PRODUCER_STATE", "CONFIG_FILES", "CHURN_ALLOWLIST",
    "CONFIG_MARKERS", "MANAGED_MARKER_PATHS", "UNCOUNTED_FILES", "FRAMEWORK_BOOKKEEPING",
    "_BOOKKEEPING", "_GENERATED_BASENAMES", "_SKIP_REVIEW_CANONICAL_BASENAME_PATHS",
    "_MAIN_TREE_WRITE_EXEMPT", "_EXISTING_ARTIFACT_CANDIDATES",
})
FOLDERS = EVENT_FOLDERS
READER_MARKERS = (
    "events_read", "read_events_assembled", "read_events_at", "event_lines_at", "events_text",
    "finalized_run_ids", "iter_event_lines", "source_stats", "has_event_folders", "validate_event_folders",
)  # a call/import of the assembling reader; a bare folder name or a generic word is NOT enough
CLASSIFIER_MARKERS = ("EVENT_FOLDERS", "is_event_folder_path")

TOKEN = re.compile(
    r"shipwright_events\.jsonl|\b(?:" + "|".join(sorted(KNOWN_ALIASES | TRACKED_DERIVED | set(RESOLVERS))) + r")\b")
SCAN_ROOTS = ("plugins", "shared", "docs", "scripts", ".github")
SCAN_SUFFIXES = frozenset({".py", ".md", ".json", ".sh", ".yml", ".yaml", ".template", ".ts", ".js", ".mjs",
                           ".toml", ".txt", ".ps1", ".cmd"})
SKIP_PARTS = frozenset({"tests", "node_modules", "fixtures", "testkit", "__pycache__", ".venv"})

REGISTRY: dict[str, tuple[str, ...]] = {
    "R": (
        "plugins/shipwright-adopt/scripts/checks/validate_adoption.py",
        "plugins/shipwright-compliance/scripts/audit/_events_read.py",
        "plugins/shipwright-compliance/scripts/audit/group_b.py",
        "plugins/shipwright-compliance/scripts/audit/group_d.py",
        "plugins/shipwright-compliance/scripts/lib/collectors/change_history.py",
        "plugins/shipwright-grade/scripts/lib/routing.py",
        "plugins/shipwright-test/scripts/tools/boundary_coverage_report.py",
        "shared/scripts/lib/_fr_history_events.py",
        "shared/scripts/lib/config.py",
        "shared/scripts/lib/event_context_index.py",
        "shared/scripts/lib/phase_quality/_run_id_resolve.py",
        "shared/scripts/tools/replay_baseline_lock.py",
        "shared/scripts/tools/resolve_churn_conflicts.py",
        "shared/scripts/tools/verifiers/adopt_compliance.py",
        "shared/scripts/tools/verifiers/common.py",
        "shared/scripts/tools/verifiers/iterate_checks.py",
    ),
    "C": (
        "shared/scripts/tools/compliance_input_state.py",
        "plugins/shipwright-security/scripts/lib/pr_review_generated.py",
        "plugins/shipwright-security/scripts/lib/pr_review_skip_safety.py",
        "shared/scripts/lib/change_type_paths.py",
        "shared/scripts/lib/churn_merge.py",
        "shared/scripts/lib/gitattributes_union.py",
        "shared/scripts/lib/gitignore_selfheal.py",
        "shared/scripts/lib/project_root.py",
        "shared/scripts/lib/review_diff_threshold.py",
        "shared/scripts/lib/section_file_list.py",
        "shared/scripts/lib/worktree_isolation.py",
    ),
    "L": (
        "plugins/shipwright-compliance/scripts/lib/compliance_report.py",
        "plugins/shipwright-grade/scripts/lib/authoritative.py",
    ),
    # Writers and finalization: S4 migrates these; each entry leaves this list with its unit.
    "W": (
        "plugins/shipwright-adopt/scripts/lib/event_seeder.py",
        "plugins/shipwright-adopt/scripts/tools/generate_adoption_artifacts.py",
        "shared/scripts/tools/commit_event_followup.py",
        "shared/scripts/tools/convert_configs_to_events.py",
        "shared/scripts/tools/record_event.py",
        "shared/scripts/tools/validate_event_log.py",
    ),
    "S": (
        "shared/scripts/lib/events_layout.py",
        "shared/scripts/lib/events_log.py",
        "shared/scripts/lib/events_read.py",
        "shared/scripts/lib/events_references.py",
    ),
    "M": (
        "plugins/shipwright-adopt/scripts/checks/setup_adopt.py",
        "shared/scripts/lib/gitattributes_selfheal.py",
        "plugins/shipwright-adopt/scripts/lib/dry_run_reporter.py",
        "plugins/shipwright-compliance/scripts/lib/collectors/__init__.py",
        "plugins/shipwright-compliance/scripts/lib/data_collector.py",
        "plugins/shipwright-iterate/scripts/tools/campaign_progress.py",
        "shared/scripts/lib/campaign_status_io.py",
        "shared/scripts/lib/event_context_query.py",
        "shared/scripts/tools/events_replay_gate.py",
        "shared/scripts/tools/measure_baseline.py",
    ),
    "P": (
        "docs/guide.md", "docs/hooks-and-pipeline.md", "docs/migrations/requirements-catalog-merge.md",
        "docs/token-cost-controllable.md",
        "plugins/shipwright-adopt/scripts/lib/gitattributes_scaffolder.py",
        "plugins/shipwright-adopt/skills/adopt/references/step-e-artifact-generation.md",
        "plugins/shipwright-adopt/skills/adopt/references/step-h-validate-commit-handoff.md",
        "plugins/shipwright-changelog/skills/changelog/SKILL.md",
        "plugins/shipwright-changelog/skills/changelog/references/compliance-evidence.md",
        "plugins/shipwright-compliance/scripts/audit/_group_d_promise.py",
        "plugins/shipwright-compliance/scripts/audit/group_f.py",
        "plugins/shipwright-compliance/scripts/audit/group_i.py",
        "plugins/shipwright-compliance/scripts/lib/_control_block.py",
        "plugins/shipwright-compliance/scripts/lib/_grade_snapshot.py",
        "plugins/shipwright-deploy/skills/deploy/references/rollback-discipline.md",
        "plugins/shipwright-grade/skills/grade/SKILL.md",
        "plugins/shipwright-iterate/agents/sub-iterate-runner.md",
        "plugins/shipwright-iterate/skills/iterate/SKILL.md",
        "plugins/shipwright-iterate/skills/iterate/references/F11.md",
        "plugins/shipwright-iterate/skills/iterate/references/F5b.md",
        "plugins/shipwright-iterate/skills/iterate/references/F5c.md",
        "plugins/shipwright-iterate/skills/iterate/references/F6.5.md",
        "plugins/shipwright-iterate/skills/iterate/references/F6.md",
        "plugins/shipwright-iterate/skills/iterate/references/F7b.md",
        "plugins/shipwright-iterate/skills/iterate/references/artifact-ownership.md",
        "plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md",
        "plugins/shipwright-iterate/skills/iterate/references/context-loading.md",
        "plugins/shipwright-iterate/skills/iterate/references/iterate-timings.md",
        "plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md",
        "plugins/shipwright-iterate/skills/iterate/references/mid-flight-escalation.md",
        "plugins/shipwright-run/scripts/lib/orchestrator_pkg/events.py",
        "plugins/shipwright-run/scripts/lib/orchestrator_pkg/single_session_cli.py",
        "plugins/shipwright-run/scripts/lib/single_session/observability.py",
        "plugins/shipwright-run/skills/run/references/single-session-loop.md",
        "plugins/shipwright-test/skills/test/SKILL.md",
        "plugins/shipwright-test/skills/test/references/step-3.95-boundary-coverage.md",
        "shared/contracts/compliance.py", "shared/fr-authoring.md", "shared/glossary.md",
        "shared/schemas/triage_item.schema.json", "shared/scripts/grade_snapshot_shape.py",
        "shared/scripts/inline_suppression_scan.py", "shared/scripts/lib/architecture_doc.py",
        "shared/scripts/lib/compliance_refresh.py", "shared/scripts/lib/derived_snapshots.py",
        "shared/scripts/lib/fr_change_history.py", "shared/scripts/lib/iterate_throughput_render.py",
        "shared/scripts/lib/jsonl_records.py", "shared/scripts/lib/phase_history.py",
        "shared/scripts/lib/triage_integrity.py", "shared/scripts/source_state_capture.py",
        "shared/scripts/tools/append_iterate_entry.py", "shared/scripts/tools/append_phase_history.py",
        "shared/scripts/tools/iterate_throughput_report.py", "shared/scripts/tools/verifiers/_entry_details.py",
        "shared/scripts/tools/verifiers/build_checks.py", "shared/scripts/tools/verifiers/build_compliance.py",
        "shared/scripts/tools/verifiers/deploy_compliance.py", "shared/scripts/tools/verifiers/handoff_phase_canon.py",
        "shared/scripts/tools/verifiers/iterate_compliance.py", "shared/scripts/tools/verifiers/security_compliance.py",
        "shared/scripts/tools/write_decision_drop.py", "shared/scripts/tree_lineage.py",
        "shared/templates/gitattributes-union.template", "shared/templates/shipwright-gitignore.template",
    ),
}
TAG_OF: dict[str, str] = {path: tag for tag, paths in REGISTRY.items() for path in paths}


def scannable(rel: str) -> bool:
    p = PurePosixPath(rel)
    in_scope = bool(p.parts) and (p.parts[0] in SCAN_ROOTS or len(p.parts) == 1)  # repo-root files too
    return (in_scope and p.suffix in SCAN_SUFFIXES
            and not (SKIP_PARTS & set(p.parts)) and not p.name.startswith("test_") and p.name not in ("conftest.py", "CHANGELOG.md"))  # the changelog is history, not a dependency


def tracked_files(repo: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(repo), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                         capture_output=True, text=True, check=True, timeout=60).stdout
    return [rel for rel in out.split("\0") if rel and scannable(rel)]


def scan(repo: Path) -> dict[str, str]:
    """``{relative path: text}`` of every scannable file that mentions the log or an alias."""
    found: dict[str, str] = {}
    for rel in tracked_files(repo):
        try:
            text = (repo / rel).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue  # deleted in the working tree but still in the index
        if TOKEN.search(text):
            found[rel] = text
    return found


def alias_problems(rel: str, text: str) -> list[str]:
    """Module-level aliases of the literal outside :data:`KNOWN_ALIASES`, and renaming imports."""
    if not rel.endswith(".py"):
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [f"{rel}: not parseable, aliases cannot be tracked"]
    problems: list[str] = []
    names = KNOWN_ALIASES | set(RESOLVERS)
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            value = node.value
            bound = any((isinstance(n, ast.Constant) and n.value == EVENT_FILE)
                        or (isinstance(n, ast.Name) and n.id in names)
                        or (isinstance(n, ast.Attribute) and n.attr in names)
                        for n in ast.walk(value))
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if bound and isinstance(target, ast.Name) and target.id not in KNOWN_ALIASES | DERIVED_ALIASES:
                    problems.append(f"{rel}: `{target.id}` aliases the event log; "
                                    "register it in KNOWN_ALIASES / DERIVED_ALIASES or use the resolver")
        if isinstance(node, ast.ImportFrom):
            problems += [f"{rel}: `{a.name} as {a.asname}` renames an event-log alias"
                         for a in node.names if a.asname and a.name in names]
    return problems


def check(repo: Path, tag_of: dict[str, str] | None = None) -> list[str]:
    """Every violation of the guard (empty = KC2 holds). ``tag_of`` overrides the registry (tests)."""
    tag_of = TAG_OF if tag_of is None else tag_of
    found, problems = scan(repo), []
    for rel, text in sorted(found.items()):
        tag = tag_of.get(rel)
        if tag is None:
            problems.append(f"UNCLASSIFIED: {rel} mentions the event log; add it to REGISTRY with a tag")
            continue
        if tag == "R" and not any(m in text for m in READER_MARKERS):
            problems.append(f"{rel}: tagged reader but never uses the assembling reader ({READER_MARKERS[:3]} ...)")
        if tag == "C" and not (all(f in text for f in FOLDERS) or any(m in text for m in CLASSIFIER_MARKERS)):
            problems.append(f"{rel}: tagged classifier but does not list all three folders {FOLDERS}")
        if tag == "L" and FOLDERS[0] not in text:
            problems.append(f"{rel}: tagged lister but never looks at {FOLDERS[0]}")
        problems += alias_problems(rel, text)
    problems += [f"STALE: {rel} is registered ({tag}) but no longer mentions the event log; remove it"
                 for rel, tag in sorted(tag_of.items()) if rel not in found]
    return problems
