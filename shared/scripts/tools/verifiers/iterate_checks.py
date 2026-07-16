"""Iterate-phase verifier checks.

Migrated 1:1 from ``shared/scripts/tools/verify_iterate_finalization.py``
during iterate 12.0 (ADR-027). Behaviour and severity levels are
unchanged — the 18 pre-existing tests in
``shared/tests/test_verify_iterate_finalization.py`` must stay green
without modification. The pre-12.0 script survives as a thin wrapper
that re-exports these symbols so any downstream caller importing
``tools.verify_iterate_finalization`` keeps working.

Dual-mode reads
---------------
Since the iterate_history file-per-iterate refactor, every read of the
iterate entry store goes through ``lib.iterate_entry.read_iterate_entries``
(merged legacy-array + per-file directory). Partial migrations no longer
hide entries; a brand-new project with only ``.shipwright/agent_docs/iterates/``
files and no legacy array is fully supported.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.architecture_doc import (  # noqa: E402
    IMPACT_TARGETS,
    NULL_IMPACTS,
    REAL_IMPACTS,
    corrupt_for_run,
    missing_entries,
    read_target_texts,
    records_for_run,
    scan_drops,
)
from lib.events_log import resolve_events_path, resolve_main_repo_root  # noqa: E402
from lib.iterate_entry import (  # noqa: E402
    find_entry_by_run_id,
    read_iterate_entries,
    sanitize_run_id_for_filename,
)

from .agent_doc_budget_check import check_agent_doc_budget  # noqa: E402,F401 — re-exported
from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import _commit_changed_paths, _git_available, _run_git  # noqa: E402
from .integration_coverage import check_integration_coverage  # noqa: E402
# Re-exported so the drift-pin test ``test_cross_component_patterns_sync`` keeps
# resolving ``ic._CROSS_COMPONENT_PATTERNS`` / ``ic._is_cross_component`` after
# the integration-coverage gate moved to its own module.
from .integration_coverage import (  # noqa: E402, F401 — re-exported surface
    _CROSS_COMPONENT_PATTERNS,
    _is_cross_component,
)
# The two enforcing traceability F11 gates (TT5) + the extracted migration check,
# re-exported from their historical home (`iterate_checks`).
from ._migration_check import check_migration_quarantine_empty  # noqa: E402, F401
from .layer_coverage import check_cross_layer_coverage, check_removal_coverage  # noqa: E402, F401


# ---------------------------------------------------------------------------
# Test Completeness vocabulary (iterate-2026-05-30-test-completeness-gate)
# ---------------------------------------------------------------------------
#
# The closed set of *structural*, falsifiable reasons a behavior may be left
# UNTESTABLE. "Could-test-but-didn't" is NOT in this set — that escape hatch
# is the whole point of the gate. SSoT: this frozenset is mirrored in
# ``plugins/shipwright-iterate/skills/iterate/references/confidence-anti-patterns.md``
# and a reverse-drift test
# (``shared/tests/test_untestable_vocab_doc_sync.py``)
# asserts the doc lists exactly these codes.

UNTESTABLE_REASON_CODES: frozenset[str] = frozenset({
    "requires-prod-credential",                    # real prod secret absent from CI
    "requires-external-nondeterministic-service",  # live 3rd-party, non-deterministic output
    "requires-physical-device",                    # hardware/peripheral not in CI
    "requires-manual-visual-judgment",             # human visual/aesthetic call
    "requires-interactive-tty",                    # interactive terminal/login the harness can't drive
    "covered-by-existing-test",                    # already pinned by a named pre-existing test
})

# Completeness is enforced at these complexities; trivial is auto-n/a.
_COMPLETENESS_ENFORCED_COMPLEXITIES: frozenset[str] = frozenset({"small", "medium", "large"})
# The only two honest dispositions for a behavior. Any other value (e.g.
# "deferred", "untested", "acceptable") IS the escape hatch and fails.
_COMPLETENESS_VALID_DISPOSITIONS: frozenset[str] = frozenset({"tested", "untestable"})


# ---------------------------------------------------------------------------
# Individual checks (iterate-specific — do NOT use the generic C1-C5 helpers)
# ---------------------------------------------------------------------------

def check_iterate_history_has_run_id(project_root: Path, run_id: str) -> CheckResult:
    """F5c check — the iterate run appended itself to the entry store.

    Reads from the merged legacy array + ``.shipwright/agent_docs/iterates/`` directory.
    Passes if either source contains the run_id.
    """
    name = "iterate_history has run_id"
    entries = read_iterate_entries(project_root)
    if any(entry.get("run_id") == run_id for entry in entries):
        return CheckResult(name, True, f"run_id={run_id} present")
    return CheckResult(
        name,
        False,
        f"run_id={run_id} not in iterate history ({len(entries)} entries)",
    )


def check_events_has_commit(
    project_root: Path,
    commit_hash: str,
    run_id: str = "",
) -> CheckResult:
    """F7 check — record_event wrote the iterate's work_completed event.

    Resolution priority (since iterate-2026-05-23-verifier-multi-commit-aware):

    1. **By run_id** (primary). The F7 event records ``adr_id == run_id``;
       finding such an event is sufficient evidence that F7 ran. This handles
       multi-commit iterates where the F7 event references the F6 commit but
       HEAD has advanced (e.g. a follow-up fix commit on the iterate branch).
    2. **By commit_hash** (fallback / back-compat). Pre-multi-commit-aware
       call sites passed only the commit; this path stays for them. Matches
       on substring containment in the JSONL — same as the original
       implementation.

    Per-tree, PR-committed model
    ----------------------------
    Since iterate-2026-05-29-events-jsonl-worktree-commit the event log is a
    per-tree, version-controlled artifact: ``resolve_events_path`` returns the
    worktree-local copy and F6 commits it, so it ships through the iterate PR.
    This check therefore has two layers:

    1. **Presence** in the working copy — the event was recorded (F5b).
    2. **AC4 — committed.** When the log is *tracked*, the event MUST also be in
       a COMMIT (the HEAD blob), not merely the working copy. An event present
       only in the working tree means F6 forgot to ``git add`` it and it would
       never reach the PR — that is the bug this check guards against. For
       *untracked / gitignored* logs the committed-assertion is skipped and
       working-copy presence is sufficient (unchanged for those repos).
    """
    name = "events.jsonl has commit"
    events = resolve_events_path(project_root)
    if not events.exists():
        return CheckResult(name, False, f"missing {events.name}")

    # --- Layer 1: presence in the working copy -----------------------------
    # Primary path — look up by run_id (the iterate identity, stable across
    # multi-commit iterates and rebases).
    present_detail: str | None = None
    if run_id:
        evt = _find_work_event_by_run_id(project_root, run_id)
        if evt is not None:
            evt_commit = str(evt.get("commit", "") or "")
            present_detail = (
                f"run_id={run_id} -> event with commit={evt_commit[:8]} found"
                if evt_commit
                else f"run_id={run_id} -> event found (no commit field — "
                     "shipped with commit='' placeholder)"
            )
    if present_detail is None:
        # Fallback — commit-hash substring search.
        content = events.read_text(encoding="utf-8", errors="ignore")
        if commit_hash and commit_hash in content:
            present_detail = f"commit={commit_hash[:8]} found"
        else:
            detail = f"commit={commit_hash[:8]} not found"
            if run_id:
                detail += f" (and no work_completed event found for run_id={run_id})"
            return CheckResult(name, False, detail)

    # --- Layer 2 (AC4): when tracked, the event must be in a COMMIT --------
    committed = _event_committed_in_head(project_root, events, commit_hash, run_id)
    if committed is False:
        return CheckResult(
            name, False,
            f"{present_detail}, but it is NOT in any commit (HEAD blob) — F6 "
            "must `git add shipwright_events.jsonl` so the event ships in the "
            "iterate PR (it currently lives only in the working copy)",
        )
    if committed is True:
        return CheckResult(name, True, f"{present_detail}; committed in HEAD")
    # committed is None — untracked / gitignored / git unavailable: the
    # committed-assertion does not apply, working-copy presence is sufficient.
    return CheckResult(name, True, present_detail)


def _committed_blob_has_event(content: str, commit_hash: str, run_id: str) -> bool:
    """True iff ``content`` (a committed events.jsonl blob) carries a matching
    ``work_completed`` event — by ``adr_id == run_id`` (primary) or
    ``commit == commit_hash`` (fallback)."""
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(evt, dict) or evt.get("type") != "work_completed":
            continue
        if run_id and evt.get("adr_id") == run_id:
            return True
        if commit_hash and str(evt.get("commit", "") or "") == commit_hash:
            return True
    return False


def _event_committed_in_head(
    project_root: Path,
    events: Path,
    commit_hash: str,
    run_id: str,
) -> bool | None:
    """Tri-state AC4 helper — is the work_completed event in a COMMIT?

    Returns:
      * ``True``  — ``events`` is tracked AND the committed HEAD version
        contains a matching work_completed event.
      * ``False`` — ``events`` is tracked but the HEAD version does NOT
        contain it (F6 forgot to stage the append; or it's added-but-uncommitted).
      * ``None``  — ``events`` is untracked / gitignored, or git is unavailable
        — the committed-assertion does not apply (working-copy presence
        suffices; mirrors gitignored-log repos).

    Origin: iterate-2026-05-29-events-jsonl-worktree-commit.
    """
    # `git ls-files --error-unmatch` doubles as the tracked? probe AND yields
    # the repo-root-relative path for `git show HEAD:<path>`.
    rc, full_name, _ = _run_git(
        project_root, "ls-files", "--full-name", "--error-unmatch", "--", events.name
    )
    if rc != 0:
        return None  # untracked / gitignored / not a git repo
    rel = (full_name.strip().splitlines() or [events.name])[0].strip() or events.name
    rc, committed, _ = _run_git(project_root, "show", f"HEAD:{rel}")
    if rc != 0:
        # Tracked in the index but absent from HEAD (newly added, never
        # committed; or the repo has no commits yet) → not in a commit.
        return False
    return _committed_blob_has_event(committed, commit_hash, run_id)


def check_adr_in_iterate_history(project_root: Path, run_id: str) -> CheckResult:
    """F3 + F5c consistency — the entry for ``run_id`` carries an ``adr`` field
    that resolves to a real ADR.

    Two ADR-identity shapes are accepted:

    - ``ADR-NNN`` — a numbered ADR; must be a heading in ``decision_log.md``
      (the direct-append path used by non-iterate phases).
    - a run-id — the iterate decision-drop pattern (H). Pre-aggregation the
      ADR lives as a JSON drop under ``decision-drops/``; post-aggregation it
      has been folded into ``decision_log.md`` with a ``Run-ID:`` line.

    Entry lookup goes through the merged reader so new-format projects
    without any legacy array still resolve cleanly.
    """
    name = "ADR recorded + present"
    entry = find_entry_by_run_id(project_root, run_id)
    if not entry:
        return CheckResult(name, False, f"run_id={run_id} not in iterate history")
    adr_id = entry.get("adr")
    if not adr_id:
        return CheckResult(name, False, f"iterate_history[{run_id}].adr missing")

    log = project_root / ".shipwright" / "agent_docs" / "decision_log.md"
    log_content = (
        log.read_text(encoding="utf-8", errors="ignore") if log.exists() else ""
    )

    # Run-id ADR identity — the H decision-drop pattern. fullmatch (not
    # match) so a run-id that merely starts with "adr-" is not misread as a
    # numbered ADR.
    if not re.fullmatch(r"(?i)ADR-\d+", adr_id.strip()):
        # Worktree-aware: iterate F3 writes the decision-drop next to the
        # MAIN repo (write_decision_drop.drop_dir), but this verifier runs
        # at F11 with project_root = the iterate worktree. Resolve the drop
        # dir against the main repo, or the pending-drop branch never
        # matches and a freshly-written ADR is reported missing.
        drop_root = resolve_main_repo_root(project_root) or project_root
        drop_dir = drop_root / ".shipwright" / "agent_docs" / "decision-drops"
        if drop_dir.is_dir():
            safe = sanitize_run_id_for_filename(adr_id)
            if any(p.name.startswith(f"{safe}_") for p in drop_dir.glob("*.json")):
                return CheckResult(
                    name, True, f"{adr_id}: decision-drop pending aggregation"
                )
        if log_content and re.search(
            rf"\*\*Run-ID:\*\*\s*{re.escape(adr_id)}\b", log_content
        ):
            return CheckResult(
                name, True, f"{adr_id}: ADR aggregated into decision_log.md"
            )
        return CheckResult(
            name, False, f"{adr_id}: no decision-drop and not in decision_log.md"
        )

    # Numbered ADR — heading must be present in decision_log.md.
    if not log.exists():
        return CheckResult(name, False, f"missing {log.name}")
    if re.search(rf"### {re.escape(adr_id)}[: ]", log_content):
        return CheckResult(name, True, f"{adr_id} present in decision_log.md")
    return CheckResult(name, False, f"{adr_id} NOT found in decision_log.md")


def _find_changelog_drop_files(
    base_dir: Path,
    run_id: str | None,
) -> list[Path]:
    """Return drop files in ``CHANGELOG-unreleased.d/<category>/`` matching
    ``run_id`` (if given), else all non-``.gitkeep`` ``.md`` files. The
    drop-directory layout is owned by ``write_changelog_drop.py`` and
    aggregated into ``CHANGELOG.md`` at release time.
    """
    drop_root = base_dir / "CHANGELOG-unreleased.d"
    if not drop_root.is_dir():
        return []
    pattern = f"{run_id}_*.md" if run_id else "*.md"
    found: list[Path] = []
    for category_dir in sorted(p for p in drop_root.iterdir() if p.is_dir()):
        for f in category_dir.glob(pattern):
            if f.name == ".gitkeep":
                continue
            found.append(f)
    return found


def check_changelog_unreleased(
    project_root: Path,
    run_id: str | None = None,
) -> CheckResult:
    """F4 check — the iterate's changelog entry exists.

    Recognizes both the legacy ``CHANGELOG.md [Unreleased]`` model and
    the drop-directory model introduced by ``aggregate_changelog.py``:
    entries land in ``CHANGELOG-unreleased.d/<category>/<run_id>_NNN.md``
    between releases and are merged into the dated section at release time.

    Pass conditions (any of):
      1. A drop file matching ``run_id`` exists (when ``run_id`` is given).
      2. Any non-``.gitkeep`` drop file exists (when ``run_id`` omitted —
         legacy callers).
      3. ``CHANGELOG.md [Unreleased]`` has at least one bullet
         (pre-drop-dir behaviour, kept for backward compat).
    """
    name = "CHANGELOG.md [Unreleased] has entries"

    # Drop-dir layout sits next to CHANGELOG.md, which lives at project_root
    # for standalone projects and at project_root.parent for monorepo-nested
    # ones (e.g. webui). Probe both bases.
    drop_bases = [project_root, project_root.parent]
    for base in drop_bases:
        drop_files = _find_changelog_drop_files(base, run_id)
        if drop_files:
            label = f"run_id={run_id}" if run_id else "any iterate"
            return CheckResult(
                name, True,
                f"{len(drop_files)} drop file(s) in CHANGELOG-unreleased.d for {label}",
            )

    # Fallback: legacy CHANGELOG.md [Unreleased] check
    candidates = [project_root / "CHANGELOG.md", project_root.parent / "CHANGELOG.md"]
    changelog = next((c for c in candidates if c.exists()), None)
    if not changelog:
        return CheckResult(
            name,
            False,
            f"CHANGELOG.md not found in {project_root} or its parent",
            severity=Severity.WARNING.value,
        )
    content = changelog.read_text(encoding="utf-8", errors="ignore")

    match = re.search(
        r"## \[Unreleased\][^\n]*\n(.*?)(?=\n## \[|\Z)",
        content,
        re.DOTALL,
    )
    if not match:
        return CheckResult(name, False, "no [Unreleased] section found")
    section = match.group(1)
    bullet_count = len(re.findall(r"^\s*-\s+", section, re.MULTILINE))
    if bullet_count == 0:
        return CheckResult(name, False, "[Unreleased] has no bullets")
    return CheckResult(name, True, f"{bullet_count} bullets in [Unreleased]")


def check_session_handoff_fresh(
    project_root: Path,
    max_age_seconds: int = 600,
) -> CheckResult:
    """F11 check — ``session_handoff.md`` was regenerated recently.

    Warning-level because handoff is advisory, not load-bearing.
    """
    name = "session_handoff.md fresh"
    handoff = project_root / ".shipwright" / "agent_docs" / "session_handoff.md"
    if not handoff.exists():
        return CheckResult(
            name,
            False,
            "session_handoff.md missing",
            severity=Severity.WARNING.value,
        )
    age = time.time() - handoff.stat().st_mtime
    if age <= max_age_seconds:
        return CheckResult(name, True, f"mtime age {int(age)}s")
    return CheckResult(
        name,
        False,
        f"stale: mtime age {int(age)}s > {max_age_seconds}s",
        severity=Severity.WARNING.value,
    )


# ---------------------------------------------------------------------------
# C2 check — build_dashboard.md reflects the iterate run (Canon spec gap)
# ---------------------------------------------------------------------------

def check_build_dashboard_has_run_id(
    project_root: Path,
    run_id: str,
    commit_hash: str | None = None,
) -> CheckResult:
    """C2 check — ``build_dashboard.md`` reflects the current iterate run.

    The dashboard is rendered by ``finalize_iterate.py`` (F5b) via
    ``update_build_dashboard.py``. F5b runs BEFORE the F6 commit and the
    F7 event, so the dashboard at F11-verify time structurally cannot
    contain the new commit SHA. F5b therefore embeds the iterate
    ``run_id`` in the dashboard header (``| Run: {run_id}``) as the
    deterministic, timing-independent marker. The check accepts either:

      1. the ``run_id`` literal in the dashboard — the canonical signal,
         embedded by F5b (see ``update_build_dashboard.generate_dashboard``).
      2. the short SHA prefix of ``commit_hash`` — for build-phase
         dashboards and post-F7 re-renders where the commit predates the
         render.

    Either match is sufficient — both signal that the iterate row landed.
    """
    name = "build_dashboard has run_id"
    dashboard = project_root / ".shipwright" / "agent_docs" / "build_dashboard.md"
    if not dashboard.exists():
        return CheckResult(
            name, False, "build_dashboard.md missing",
            severity=Severity.WARNING.value,
        )
    content = dashboard.read_text(encoding="utf-8", errors="ignore")
    if run_id and run_id in content:
        return CheckResult(name, True, f"run_id={run_id} present")
    if commit_hash:
        short_sha = commit_hash[:7]
        if short_sha and short_sha in content:
            return CheckResult(
                name, True,
                f"commit={short_sha} present (run_id={run_id} not embedded)",
            )
    return CheckResult(
        name, False,
        f"run_id={run_id} not found in build_dashboard.md",
        severity=Severity.WARNING.value,
    )


# ---------------------------------------------------------------------------
# Cross-artifact warnings (non-canon — advisory only)
# ---------------------------------------------------------------------------

def check_compliance_reflects_run_id(
    project_root: Path,
    run_id: str,
) -> CheckResult:
    """Non-canon warning: compliance dashboard should reference the run."""
    name = "compliance reflects run_id"
    dashboard = project_root / ".shipwright" / "compliance" / "dashboard.md"
    if not dashboard.exists():
        return CheckResult(
            name, False, ".shipwright/compliance/dashboard.md missing",
            severity=Severity.WARNING.value,
        )
    content = dashboard.read_text(encoding="utf-8", errors="ignore")
    iterate_count = len(read_iterate_entries(project_root))
    if str(iterate_count) in content or run_id in content:
        return CheckResult(name, True, "compliance reflects iterate count/run_id")
    return CheckResult(
        name, False,
        f".shipwright/compliance/dashboard.md may be stale (run_id={run_id} not found)",
        severity=Severity.WARNING.value,
    )


def _freshness_mtime_reference(project_root: Path, run_id: str) -> float | None:
    """Pick a freshness reference mtime for a given run_id.

    Prefer the per-iterate entry file (added by the file-per-iterate
    refactor) because it's created at finalize time and doesn't churn with
    unrelated config mutations. Fall back to ``shipwright_run_config.json``
    for legacy projects that still carry the array.
    """
    from lib.iterate_entry import entry_file_for

    entry_path = entry_file_for(project_root, run_id)
    if entry_path.exists():
        return entry_path.stat().st_mtime
    cfg = project_root / "shipwright_run_config.json"
    if cfg.exists():
        return cfg.stat().st_mtime
    return None


def check_conventions_reviewed(
    project_root: Path,
    run_id: str,
) -> CheckResult:
    """Non-canon warning: conventions.md may need update after feature iterates."""
    name = "conventions.md reviewed"
    entry = find_entry_by_run_id(project_root, run_id)
    if not entry:
        return CheckResult(name, None, "run_id not in history", severity=Severity.SKIPPED.value)

    intent = entry.get("intent", entry.get("type", ""))
    if intent in ("bug", "fix"):
        return CheckResult(name, True, f"intent={intent}, conventions update unlikely")

    conv = project_root / ".shipwright" / "agent_docs" / "conventions.md"
    if not conv.exists():
        return CheckResult(
            name, False, "conventions.md missing",
            severity=Severity.WARNING.value,
        )

    reference_mtime = _freshness_mtime_reference(project_root, run_id)
    if reference_mtime is None:
        return CheckResult(name, None, "no iterate entry file or run_config", severity=Severity.SKIPPED.value)
    if conv.stat().st_mtime >= reference_mtime:
        return CheckResult(name, True, "conventions.md is fresh")

    return CheckResult(
        name, False,
        f"conventions.md may need update (intent={intent}, conventions older than iterate entry)",
        severity=Severity.WARNING.value,
    )


def check_surface_verification(project_root: Path, run_id: str) -> CheckResult:
    """F0.5 audit — ``shipwright_test_results.json.iterate_latest`` carries a
    well-formed ``surface_verification`` block.

    The post-commit second layer behind the production-time gate in
    ``shared/scripts/surface_verification.py``. Skipped at trivial/small
    complexity (the gate's safety floor enforces those at the prose level).
    Severity ERROR — fails ``--strict`` and default both.

    Fail-closed conditions (mirror of SKILL.md F0.5):

    1. medium+ iterate but no ``surface_verification`` block (silent regression).
    2. ``surface != "none"`` and ``tests_run == 0`` (greedy-filter trap).
    3. ``surface != "none"`` and ``exit_code != 0`` (runner failed after retries).
    4. ``surface == "none"`` with empty / missing ``justification``.

    A missing or malformed ``shipwright_test_results.json`` at medium+ is
    itself a failure — the F5 step is mandatory and produces the file.
    """
    name = "F0.5 surface_verification block valid"

    entry = find_entry_by_run_id(project_root, run_id)
    complexity = (entry or {}).get("complexity", "")
    if complexity not in ("medium", "large"):
        return CheckResult(
            name, True,
            f"skipped (complexity={complexity or 'unknown'})",
            severity=Severity.SKIPPED.value,
        )

    results_path = project_root / "shipwright_test_results.json"
    if not results_path.exists():
        return CheckResult(
            name, False,
            "shipwright_test_results.json missing — F5 did not run",
        )
    try:
        results = json.loads(results_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return CheckResult(
            name, False,
            f"shipwright_test_results.json malformed: {exc}",
        )

    iterate_latest = (results or {}).get("iterate_latest", {})
    block = iterate_latest.get("surface_verification") if isinstance(iterate_latest, dict) else None
    if not isinstance(block, dict):
        return CheckResult(
            name, False,
            "iterate_latest.surface_verification missing for medium+ iterate",
        )

    surface = block.get("surface")
    if surface not in ("web", "cli", "api", "none"):
        return CheckResult(
            name, False,
            f"surface={surface!r} not one of web/cli/api/none",
        )

    if surface == "none":
        justification = (block.get("justification") or "").strip()
        if not justification:
            return CheckResult(
                name, False,
                "surface=none requires non-empty justification",
            )
        return CheckResult(
            name, True,
            f"surface=none, justification recorded ({len(justification)} chars)",
        )

    exit_code = block.get("exit_code")
    tests_run = block.get("tests_run")
    if not isinstance(tests_run, int) or tests_run <= 0:
        return CheckResult(
            name, False,
            f"surface={surface}, tests_run={tests_run!r} (must be > 0)",
        )
    if exit_code != 0:
        return CheckResult(
            name, False,
            f"surface={surface}, exit_code={exit_code!r} (runner failed after retries)",
        )
    return CheckResult(
        name, True,
        f"surface={surface}, tests_run={tests_run}, exit_code=0",
    )


# ---------------------------------------------------------------------------
# Test Completeness gate — "testable ⇒ tested"
# (iterate-2026-05-30-test-completeness-gate)
# ---------------------------------------------------------------------------

def check_test_completeness_ledger(project_root: Path, run_id: str) -> CheckResult:
    """Test Completeness gate — every behavior the diff introduces is either
    ``tested`` (with evidence) or ``untestable`` (with a closed-vocabulary
    structural reason). The "could-test-but-didn't" escape hatch is abolished,
    so the question *"did you empirically test everything testable?"* becomes
    structurally self-answering and the operator never has to ask.

    Reads ``shipwright_test_results.json.iterate_latest.test_completeness``
    (written at F5, the same producer step that writes ``surface_verification``).
    Enforced at small / medium / large; SKIPped at trivial (auto n/a) and when
    the run_id is absent. Severity ERROR — fails ``--strict`` and default both;
    a non-zero F11 verifier STOPs the run before the PR.

    Fail-closed conditions:

    1. small+ iterate but no results file / no ``test_completeness`` block
       (F5 didn't populate it).
    2. malformed results JSON.
    3. ``status`` not in {``complete``, ``n/a``}.
    4. ``status == "n/a"`` without a non-empty ``justification``.
    5. ``status == "complete"`` with an empty ``behaviors`` list.
    6. any behavior ``disposition`` outside {``tested``, ``untestable``} — the
       escape hatch.
    7. any ``untestable`` behavior whose ``reason_code`` is outside
       ``UNTESTABLE_REASON_CODES``.
    8. any ``tested`` behavior citing no ``evidence``.
    9. ``counts.untested_testable`` missing or > 0 (declared testable-but-untested).
    10. ``enumeration_basis`` reports more ``acs`` than ``covered_acs``
        (under-enumeration guard — stops a vacuous pass via a short list).
    """
    name = "test completeness ledger"

    entry = find_entry_by_run_id(project_root, run_id)
    if not entry:
        return CheckResult(
            name, True, f"skipped (run_id={run_id} not in history)",
            severity=Severity.SKIPPED.value,
        )
    complexity = str(entry.get("complexity", "")).lower()
    if complexity == "trivial":
        return CheckResult(
            name, True, "skipped (complexity=trivial — completeness n/a)",
            severity=Severity.SKIPPED.value,
        )
    if complexity not in _COMPLETENESS_ENFORCED_COMPLEXITIES:
        return CheckResult(
            name, True, f"skipped (complexity={complexity or 'unknown'})",
            severity=Severity.SKIPPED.value,
        )

    results_path = project_root / "shipwright_test_results.json"
    if not results_path.exists():
        return CheckResult(
            name, False,
            "shipwright_test_results.json missing — F5 did not write the "
            "test_completeness ledger",
        )
    try:
        results = json.loads(results_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        return CheckResult(name, False, f"shipwright_test_results.json malformed: {exc}")
    if not isinstance(results, dict):
        return CheckResult(
            name, False, "shipwright_test_results.json is not a JSON object",
        )

    iterate_latest = results.get("iterate_latest", {})
    block = iterate_latest.get("test_completeness") if isinstance(iterate_latest, dict) else None
    if not isinstance(block, dict):
        return CheckResult(
            name, False,
            f"iterate_latest.test_completeness missing for a {complexity} "
            "iterate — populate the ledger at F5",
        )

    status = str(block.get("status", "")).lower()
    if status not in ("complete", "n/a"):
        return CheckResult(
            name, False,
            f"test_completeness.status={status!r} not one of complete / n/a",
        )

    if status == "n/a":
        # n/a is the "no testable behavior" claim. It is honest only for
        # genuinely behaviorless changes — which, by definition, are not
        # medium/large. Forbidding it at medium+ closes the residual escape
        # hatch (a real feature self-classifying n/a to skip enumeration).
        if complexity in ("medium", "large"):
            return CheckResult(
                name, False,
                f"status=n/a is not allowed at {complexity} complexity — a "
                f"{complexity} iterate has testable behavior by definition. "
                "Enumerate it (status=complete), or re-classify the iterate as "
                "small if the change is genuinely behaviorless",
            )
        justification = str(block.get("justification", "")).strip()
        if not justification:
            return CheckResult(
                name, False,
                "status=n/a requires a justification (e.g. 'markdown-only "
                "edit; no executable behavior changed')",
            )
        return CheckResult(
            name, True, f"n/a, justified ({len(justification)} chars)",
        )

    # status == "complete" --------------------------------------------------
    behaviors = block.get("behaviors")
    if not isinstance(behaviors, list) or not behaviors:
        return CheckResult(
            name, False,
            "status=complete but no behaviors enumerated — a small+ iterate "
            "that changed behavior must list at least one testable behavior",
        )

    for i, beh in enumerate(behaviors):
        if not isinstance(beh, dict):
            return CheckResult(name, False, f"behavior[{i}] is not an object")
        label = str(beh.get("behavior", f"#{i}"))
        disposition = str(beh.get("disposition", "")).lower()
        if disposition not in _COMPLETENESS_VALID_DISPOSITIONS:
            return CheckResult(
                name, False,
                f"behavior {label!r} has disposition={disposition!r} — only "
                "'tested' or 'untestable' are allowed. The "
                "'could-test-but-didn't' escape hatch is not permitted: test "
                "it, or classify it untestable with a structural reason_code",
            )
        if disposition == "untestable":
            reason_code = str(beh.get("reason_code", "")).strip()
            if reason_code not in UNTESTABLE_REASON_CODES:
                return CheckResult(
                    name, False,
                    f"behavior {label!r} untestable with reason_code="
                    f"{reason_code!r}, not in the closed vocabulary "
                    f"{sorted(UNTESTABLE_REASON_CODES)}",
                )
        elif not str(beh.get("evidence", "")).strip():
            return CheckResult(
                name, False,
                f"behavior {label!r} is 'tested' but cites no evidence — name "
                "the test + result",
            )

    counts = block.get("counts") if isinstance(block.get("counts"), dict) else {}
    untested_testable = counts.get("untested_testable", None)
    # NB: bool is a subclass of int — `untested_testable: false` must NOT
    # satisfy the "must be int == 0" contract.
    if (isinstance(untested_testable, bool)
            or not isinstance(untested_testable, int)
            or untested_testable > 0):
        return CheckResult(
            name, False,
            f"counts.untested_testable={untested_testable!r} — every testable "
            "behavior must be tested (target 0)",
        )

    basis = block.get("enumeration_basis")
    if isinstance(basis, dict):
        acs, covered = basis.get("acs"), basis.get("covered_acs")
        if isinstance(acs, int) and isinstance(covered, int) and acs > covered:
            return CheckResult(
                name, False,
                f"enumeration gap: {acs} acceptance criteria, only {covered} "
                "covered by ledger rows — enumerate the remainder",
            )

    tested = sum(
        1 for beh in behaviors if str(beh.get("disposition", "")).lower() == "tested"
    )
    untestable = len(behaviors) - tested
    return CheckResult(
        name, True,
        f"complete: {tested} tested, {untestable} untestable (valid reason), "
        "0 untested-testable",
    )


# ---------------------------------------------------------------------------
# Spec-impact gate — a FEATURE/CHANGE iterate must change the spec or
# explicitly justify why not (iterate-2026-05-16-spec-impact-gate)
# ---------------------------------------------------------------------------

def _is_planning_spec(path: str) -> bool:
    """True for a ``.shipwright/planning/<split>/spec.md`` path (any separator)."""
    norm = path.replace("\\", "/")
    return norm.startswith(".shipwright/planning/") and norm.endswith("/spec.md")


def _find_work_event_by_commit(project_root: Path, commit_hash: str) -> dict | None:
    """Return the ``work_completed`` event for ``commit_hash``, or None.

    Reads the per-tree log via ``resolve_events_path`` — the same
    worktree-local copy the F5b producer wrote (and F6 committed).
    """
    if not commit_hash:
        return None
    events_path = resolve_events_path(project_root)
    if not events_path.exists():
        return None
    for line in events_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if evt.get("type") == "work_completed" and evt.get("commit") == commit_hash:
            return evt
    return None


def _find_work_event_by_run_id(project_root: Path, run_id: str) -> dict | None:
    """Return the ``work_completed`` event for ``run_id``, or None.

    The F7 step records ``adr_id == run_id`` on the iterate's work_completed
    event (per SKILL.md F7). This lookup is the *iterate-identity* path —
    stable across multi-commit iterates and rebases, where the event's
    ``commit`` field may reference a non-tip commit on the iterate branch.

    When multiple events match (a re-recorded F7 or two iterates colliding
    on a run_id — pathological), the **last** match wins. The event log is
    append-only and chronologically ordered, so the most-recent record is
    the live one.

    Reads the per-tree log via ``resolve_events_path`` — the same
    worktree-local copy the F5b producer wrote (and F6 committed).
    """
    if not run_id:
        return None
    events_path = resolve_events_path(project_root)
    if not events_path.exists():
        return None
    matched: dict | None = None
    for line in events_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if evt.get("type") != "work_completed":
            continue
        if evt.get("adr_id") == run_id:
            matched = evt
    return matched


def check_spec_impact_recorded(
    project_root: Path,
    run_id: str,
    commit_hash: str,
) -> CheckResult:
    """Spec-impact gate — a FEATURE/CHANGE iterate must change the spec or
    explicitly record ``spec_impact=none`` with a justification.

    Two sources of truth, checked in order:

    1. The F7 ``work_completed`` event's ``spec_impact`` classification.
       ``none`` + a justification (``spec_impact_justification`` OR the FR-gate's
       equivalent ``none_reason``) → PASS; ``none`` without one → FAIL.
    2. Otherwise (``add``/``modify``/``remove`` or a legacy event with no
       ``spec_impact``): the commit MUST have touched a
       ``.shipwright/planning/**/spec.md`` file. If it did → PASS, else FAIL.

    BUG iterates, intent-less entries, and runs whose entry is absent are
    SKIPPED — a bug fix need not touch the spec. Git-unavailable is SKIPPED.
    Severity ERROR on failure (blocks default exit and ``--strict``).
    Origin: iterate-2026-05-16-spec-impact-gate.
    """
    name = "spec impact recorded (feature/change)"

    entry = find_entry_by_run_id(project_root, run_id)
    if not entry:
        return CheckResult(
            name, True, f"skipped (run_id={run_id} not in history)",
            severity=Severity.SKIPPED.value,
        )
    intent = entry.get("intent", entry.get("type", ""))
    if intent not in ("feature", "change"):
        return CheckResult(
            name, True, f"skipped (intent={intent or 'unknown'})",
            severity=Severity.SKIPPED.value,
        )

    # Look up the F7 event by run_id first (primary, iterate-identity); fall
    # back to commit_hash for legacy single-commit iterates whose F7 event
    # carries no adr_id. This is what makes multi-commit iterates work — the
    # caller passes HEAD as commit_hash, but the event references the F6
    # commit (earlier on the branch).
    event = _find_work_event_by_run_id(project_root, run_id)
    if event is None:
        event = _find_work_event_by_commit(project_root, commit_hash)
    # The commit the event references — used downstream for the spec.md
    # path check. Defaults to the caller-supplied commit_hash when no event
    # was found (matches the original behavior).
    event_commit = str((event or {}).get("commit", "") or "") or commit_hash
    spec_impact = str((event or {}).get("spec_impact", "")).lower()

    if spec_impact == "none":
        # `spec_impact_justification` and the FR-gate's `none_reason` are the
        # same semantic field ("why spec_impact=none"); the FR-gate already
        # REQUIRES none_reason for a none-impact event, and it is the only field
        # finalize_iterate's --event-extras-json documents. Accept either so a
        # caller that recorded only none_reason isn't falsely failed.
        event_d = event or {}
        justification = str(
            event_d.get("spec_impact_justification")
            or event_d.get("none_reason")
            or ""
        ).strip()
        if justification:
            return CheckResult(
                name, True,
                f"spec_impact=none, justified ({len(justification)} chars)",
            )
        return CheckResult(
            name, False,
            "spec_impact=none recorded WITHOUT a justification — a "
            "feature/change iterate claiming no spec impact must justify it",
        )

    # spec_impact add|modify|remove, or a legacy event with no spec_impact:
    # the F7-referenced commit itself must have touched a planning spec.md.
    if not _git_available(project_root):
        return CheckResult(
            name, True, "skipped (git unavailable — cannot inspect commit)",
            severity=Severity.SKIPPED.value,
        )
    changed = _commit_changed_paths(project_root, event_commit)
    if changed is None:
        return CheckResult(
            name, True,
            f"skipped (could not read commit {event_commit[:8]})",
            severity=Severity.SKIPPED.value,
        )
    spec_files = [p for p in changed if _is_planning_spec(p)]
    if spec_files:
        return CheckResult(
            name, True,
            f"spec_impact={spec_impact or 'unrecorded'}; commit touched "
            f"{len(spec_files)} planning spec.md file(s)",
        )
    return CheckResult(
        name, False,
        f"intent={intent} iterate but commit {event_commit[:8]} touched no "
        ".shipwright/planning/**/spec.md and recorded no spec_impact=none — "
        "classify the spec impact (ADD/MODIFY/REMOVE) or record "
        "spec_impact=none with a justification",
    )


def check_architecture_documented(project_root: Path, run_id: str) -> CheckResult:
    """Canon/blocking F11 gate: an iterate whose decision-drop declares
    ``architecture_impact ∈ {component, data-flow, convention}`` MUST document
    its ``run_id`` in ``architecture.md`` (the F2 contract). Replaces the dead,
    mtime-only ``check_architecture_reviewed`` and shares the reconciliation
    oracle (``lib.architecture_doc``) with the F5 detective so the two cannot
    diverge. Worktree-aware: gitignored drops resolved via
    ``resolve_main_repo_root``, tracked ``architecture.md`` read from
    ``project_root``. SKIP when no drop yet or impact none; FAIL on a
    corrupt/unrecognized-impact drop, a missing architecture.md, or a real
    impact whose run_id is absent. Origin: iterate-2026-06-06-arch-drift-detector.
    """
    name = "architecture documented (arch-impact iterate)"

    main_root = resolve_main_repo_root(project_root)
    base = Path(main_root) if main_root is not None else Path(project_root)
    drops_dir = base / ".shipwright" / "agent_docs" / "decision-drops"

    records, corrupt = scan_drops(drops_dir)
    run_corrupt = corrupt_for_run(corrupt, run_id)
    if run_corrupt:
        return CheckResult(
            name, False,
            f"decision-drop for {run_id} failed to parse ({', '.join(run_corrupt)}) "
            "— fix the drop JSON before finalize",
        )

    run_records = records_for_run(records, run_id)
    if not run_records:
        return CheckResult(
            name, True, f"skipped (no decision-drop for {run_id})",
            severity=Severity.SKIPPED.value,
        )

    impacts = {r.impact for r in run_records}
    unknown = sorted(i for i in impacts if i not in REAL_IMPACTS and i not in NULL_IMPACTS)
    if unknown:
        return CheckResult(
            name, False,
            f"{run_id} decision-drop has an unrecognized architecture_impact "
            f"{unknown} (expected component|data-flow|convention|none)",
        )
    real = sorted(impacts & REAL_IMPACTS)
    if not real:
        return CheckResult(
            name, True, f"skipped (architecture_impact=none for {run_id})",
            severity=Severity.SKIPPED.value,
        )

    # Route each impact to its target doc via IMPACT_TARGETS (convention →
    # conventions.md; component/data-flow → architecture.md), checking both docs.
    texts = read_target_texts(Path(project_root) / ".shipwright" / "agent_docs")
    missing = missing_entries(run_records, texts)
    if not missing:
        return CheckResult(
            name, True, f"{run_id} documented (impact={real})"
        )

    where = "; ".join(
        f"{r.impact} → '{IMPACT_TARGETS[r.impact][1]}' in {IMPACT_TARGETS[r.impact][0]}"
        for r in missing
    )
    return CheckResult(
        name, False,
        f"{run_id} declares architecture_impact={real} but is NOT documented in "
        f"its target doc(s) ({where}) — add a one-line bullet naming {run_id} + "
        "what changed (or set architecture_impact=none if it was over-flagged)",
    )


# Orchestrator (kept for backwards compat with verify_iterate_finalization.py).
def run_all_checks(
    project_root: Path,
    run_id: str,
    commit_hash: str = "",
) -> list[CheckResult]:
    """Run the full iterate check list and return results in stable order."""
    return [
        check_iterate_history_has_run_id(project_root, run_id),
        check_events_has_commit(project_root, commit_hash, run_id=run_id) if commit_hash or run_id else CheckResult(
            "events.jsonl has commit", True, "skipped (no --commit or --run-id supplied)"
        ),
        check_adr_in_iterate_history(project_root, run_id),
        check_changelog_unreleased(project_root, run_id=run_id),
        check_session_handoff_fresh(project_root),
        check_build_dashboard_has_run_id(project_root, run_id, commit_hash=commit_hash or None),
        check_surface_verification(project_root, run_id),
        check_test_completeness_ledger(project_root, run_id),
        check_spec_impact_recorded(project_root, run_id, commit_hash) if commit_hash else CheckResult(
            "spec impact recorded (feature/change)", True,
            "skipped (no --commit supplied)", severity=Severity.SKIPPED.value,
        ),
        check_architecture_documented(project_root, run_id),
        check_integration_coverage(project_root, run_id, commit_hash),
        check_removal_coverage(project_root, run_id, commit_hash),
        check_cross_layer_coverage(project_root, run_id, commit_hash),
        check_agent_doc_budget(project_root, run_id, commit_hash),
    ]


