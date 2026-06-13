"""Shared helpers for the modular verifier package.

Contains:

1. ``CheckResult`` dataclass + ``Severity`` enum shared by every
   ``*_checks.py`` module.
2. File readers for the cross-artifact sync invariants that every phase
   verifies: ``shipwright_run_config.json``, ``shipwright_events.jsonl``,
   ``.shipwright/agent_docs/decision_log.md``, ``CHANGELOG.md``.
3. Generic C1-C5 "Minimum Phase Completion Canon" checks. Iterate 12.1+
   phase check modules call these with the phase name; the checks own
   the lookup logic so plugins don't each re-implement "is there a
   phase_completed event for <phase>" differently.
4. ADR integrity helpers (F1/F2/F3 from the shipwright-check plan) for
   phases whose canon includes an ADR step.

All functions are pure (read-only). Writes live in the ``append_*.py``
helpers.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable

# Add shared/scripts to path for lib imports when this module is loaded
# via its own subpackage (verify_phase.py does the same bootstrap).
import sys
_SHARED_SCRIPTS = Path(__file__).resolve().parent.parent.parent
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.drift_parsers import (  # noqa: E402
    ADR_VALID_STATUSES,
    ADRHeader,
    extract_adr_id_number,
    find_duplicate_adr_ids,
    find_gaps_in_adr_ids,
    parse_adr_headers,
)


# Canonical home of the agent_docs artifact set, relative to project_root.
# Mirrors agent_docs entry in shared/scripts/lib/artifact_migrations.py.
_AGENT_DOCS_DIRNAME = ".shipwright/agent_docs"


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    ERROR = "error"        # hard fail, blocks exit 0
    WARNING = "warning"    # informational, not blocking unless --strict
    SKIPPED = "skipped"    # explicit skip — neither pass nor fail

    def __str__(self) -> str:  # keep JSON-friendly string round-trip
        return self.value


@dataclass
class CheckResult:
    """One verifier finding.

    ``ok`` is tri-state:

    - ``True``  — check ran and passed
    - ``False`` — check ran and failed (severity decides whether it blocks)
    - ``None``  — check was deliberately skipped (severity ``SKIPPED``)

    The ``None`` case exists so ``verify_phase.py --phase all`` can
    surface "runtime stub" without counting it as pass OR fail.
    """

    name: str
    ok: bool | None
    detail: str = ""
    severity: str = Severity.ERROR.value

    @property
    def is_skipped(self) -> bool:
        return self.ok is None or self.severity == Severity.SKIPPED.value

    @property
    def is_failure(self) -> bool:
        return self.ok is False and self.severity != Severity.SKIPPED.value


def run_checks(
    name: str,
    fns: list[Callable[..., CheckResult]],
    project_root: Path,
    **kwargs: Any,
) -> list[CheckResult]:
    """Run a list of check functions with a uniform signature.

    Every check function is expected to accept ``project_root`` as its
    first positional argument plus any phase-specific kwargs (run_id,
    commit_hash, phase, ...). Failures inside a check function bubble up
    as ``error``-severity ``CheckResult`` so one broken check doesn't
    mask the rest of the suite.
    """
    results: list[CheckResult] = []
    for fn in fns:
        try:
            results.append(fn(project_root, **kwargs))
        except Exception as exc:  # noqa: BLE001 — surface, don't crash
            results.append(CheckResult(
                name=f"{name}:{fn.__name__}",
                ok=False,
                detail=f"check raised {type(exc).__name__}: {exc}",
                severity=Severity.ERROR.value,
            ))
    return results


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

def read_run_config(project_root: Path) -> dict[str, Any]:
    """Return the parsed ``shipwright_run_config.json`` or an empty dict.

    A missing or malformed file yields ``{}`` — individual checks decide
    how to flag that (usually with a ``missing shipwright_run_config.json``
    error).
    """
    path = project_root / "shipwright_run_config.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def read_events_jsonl(project_root: Path) -> list[dict[str, Any]]:
    """Return all valid JSON-object lines from ``shipwright_events.jsonl``.

    Malformed lines are silently skipped. Callers that need strict
    validation should use ``shared/scripts/tools/validate_event_log.py``.
    """
    path = project_root / "shipwright_events.jsonl"  # G5 (iterate-2026-06-13-shc-read-events): NOT unified with record_event/lib.config read_events — verifiers read this LITERAL path (no resolve_events_path worktree redirect) + stay silent (errors=ignore) so corruption surfaces as a CheckResult, not a warning.
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    for raw in content.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def read_decision_log(project_root: Path) -> str:
    """Return the raw text of ``.shipwright/agent_docs/decision_log.md`` or ``""``."""
    path = project_root / _AGENT_DOCS_DIRNAME / "decision_log.md"
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def find_changelog(project_root: Path) -> Path | None:
    """Return the CHANGELOG.md path (project_root or its parent), or None.

    Shipwright monorepos put CHANGELOG.md at the repo root with target
    projects living one level down (e.g. ``webui/``). Standalone projects
    keep CHANGELOG.md next to their run_config. Try both.
    """
    for candidate in (project_root / "CHANGELOG.md", project_root.parent / "CHANGELOG.md"):
        if candidate.exists():
            return candidate
    return None


def get_latest_phase_completed_event(
    events: Iterable[dict[str, Any]],
    phase: str,
) -> dict[str, Any] | None:
    """Return the most recent ``phase_completed`` event for ``phase``.

    Matches both of the two shapes that Shipwright emits today:

    - ``{"type": "phase_completed", "phase": "build", ...}``
    - ``{"type": "phase_completed", "source": "build", ...}``

    Iterate 12 standardises on the ``phase`` field going forward; the
    ``source`` fallback is kept so historical event logs still match.
    """
    latest: dict[str, Any] | None = None
    for event in events:
        if event.get("type") != "phase_completed":
            continue
        if event.get("phase") != phase and event.get("source") != phase:
            continue
        if latest is None or event.get("timestamp", "") > latest.get("timestamp", ""):
            latest = event
    return latest


# ---------------------------------------------------------------------------
# Generic C1-C5 canon checks
# ---------------------------------------------------------------------------
#
# The "Minimum Phase Completion Canon" is the 5-step invariant every
# decision-taking Shipwright phase should satisfy (see
# `docs/hooks-and-pipeline.md` and plan purrfect-snuggling-sunrise.md).
#
# C1: record_event phase_completed
# C2: update_build_dashboard for the phase
# C3: session_handoff regenerated with reason
# C4: decision_log has a new ADR tied to this run (phase-dependent)
# C5: CHANGELOG [Unreleased] has a new bullet (phase-dependent)
#
# Phase-specific modules call these with the phase name; skip criteria
# (e.g. C4 is skipped for test/changelog/deploy) are enforced by the
# caller, not here.


# Terminal phase_history outcomes that satisfy C1. A phase recorded in
# shipwright_run_config.json::phase_history[<phase>] with any of these has
# reached a terminal state: /shipwright-adopt writes ``adopted`` (and
# ``adopted-skipped`` for a phase with nothing to run); /shipwright-changelog
# writes ``tagged``. ``completed`` is accepted as a generic terminal outcome
# for forward-compatibility — no phase emits it today (orchestrated phases
# write phase-specific outcomes AND a ``phase_completed`` event, so they
# already satisfy C1 via the event path; this phase_history fallback only
# changes the result for adopt-onboarded and changelog phases).
_C1_TERMINAL_PHASE_HISTORY_OUTCOMES: frozenset[str] = frozenset({
    "adopted", "adopted-skipped", "completed", "tagged",
})


def _phase_history_terminal_outcome(project_root: Path, phase: str) -> str | None:
    """Return a terminal ``phase_history[phase]`` outcome, or ``None``.

    Reads ``shipwright_run_config.json::phase_history[<phase>]`` and
    returns the first entry's ``outcome`` when it is terminal (see
    ``_C1_TERMINAL_PHASE_HISTORY_OUTCOMES``). ``None`` when run config is
    missing/malformed, the bucket is absent, or no entry is terminal.
    """
    history = read_run_config(project_root).get("phase_history")
    if not isinstance(history, dict):
        return None
    entries = history.get(phase)
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        outcome = entry.get("outcome")
        if (isinstance(outcome, str)
                and outcome.strip().lower() in _C1_TERMINAL_PHASE_HISTORY_OUTCOMES):
            return outcome
    return None


def check_c1_phase_event_recorded(project_root: Path, phase: str) -> CheckResult:
    """C1 — the phase recorded a completion signal.

    Primary evidence is a ``phase_completed`` event in
    ``shipwright_events.jsonl``. Three fallbacks recognise completion
    conventions the original strict check predates:

    - **iterate** records ``work_completed`` (per-change), never
      ``phase_completed`` — a ``work_completed`` event with
      ``source == "iterate"`` satisfies C1.
    - **iterate** ADRs land as JSON decision-drops until
      ``/shipwright-changelog`` aggregation — a pending drop under
      ``.shipwright/agent_docs/decision-drops/`` satisfies C1 (mirrors the
      ``check_c4_decision_log_has_phase_adr`` iterate special-case).
    - **adopt** records its onboarded phases in
      ``shipwright_run_config.json::phase_history[<phase>]`` with a
      terminal ``outcome`` instead of emitting an event. The
      ``phase_history`` fallback is not phase-gated — a terminal
      ``phase_history`` entry satisfies C1 for any phase — but in
      practice it only changes the result for adopt-onboarded phases
      (``adopted`` / ``adopted-skipped``) and ``changelog`` (``tagged``):
      orchestrated phases write a ``phase_completed`` event and pass via
      the primary path. Reachable even when ``shipwright_events.jsonl``
      is empty or absent — the normal state of a freshly-adopted project.
    """
    name = f"C1 record_event phase_completed[{phase}]"
    events = read_events_jsonl(project_root)

    hit = get_latest_phase_completed_event(events, phase)
    if hit is not None:
        return CheckResult(name, True, f"found event @ {hit.get('timestamp', '?')}")

    # Iterate fallback: work_completed event, or a pending decision-drop.
    if phase == "iterate":
        wc = next(
            (e for e in events
             if e.get("type") == "work_completed"
             and e.get("source") == "iterate"),
            None,
        )
        if wc is not None:
            stamp = wc.get("ts") or wc.get("timestamp") or "?"
            return CheckResult(
                name, True,
                f"work_completed[source=iterate] event @ {stamp}",
            )
        drop_dir = project_root / _AGENT_DOCS_DIRNAME / "decision-drops"
        if drop_dir.is_dir():
            drops = [
                p for p in drop_dir.glob("*.json")
                if not p.name.startswith("_")
            ]
            if drops:
                return CheckResult(
                    name, True,
                    f"{len(drops)} decision-drop(s) pending aggregation",
                )

    # phase_history fallback (any phase) — adopt/changelog record a terminal
    # outcome here instead of emitting a phase_completed event.
    terminal = _phase_history_terminal_outcome(project_root, phase)
    if terminal is not None:
        return CheckResult(
            name, True,
            f"phase_history[{phase}] entry with terminal outcome={terminal!r}",
        )

    if not events:
        return CheckResult(
            name, False,
            f"no phase_completed event for phase={phase} "
            "(shipwright_events.jsonl empty or missing; "
            "no terminal phase_history entry)",
        )
    return CheckResult(
        name, False,
        f"no phase_completed event for phase={phase} "
        "(no work_completed / decision-drop / phase_history evidence)",
    )


def check_c2_dashboard_reflects_phase(project_root: Path, phase: str) -> CheckResult:
    name = f"C2 build_dashboard mentions {phase}"
    dashboard = project_root / _AGENT_DOCS_DIRNAME / "build_dashboard.md"
    if not dashboard.exists():
        return CheckResult(name, False, "build_dashboard.md missing")
    try:
        content = dashboard.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return CheckResult(name, False, f"read error: {e}")
    # Look for a phase marker — update_build_dashboard.py writes either an
    # explicit phase bullet or a section with the phase name. Substring is
    # coarse but robust across dashboard template variations.
    if phase.lower() not in content.lower():
        return CheckResult(
            name,
            False,
            f"no mention of '{phase}' in build_dashboard.md",
            severity=Severity.WARNING.value,
        )
    return CheckResult(name, True, f"'{phase}' found in build_dashboard.md")


def check_c3_session_handoff_fresh_after_phase(
    project_root: Path,
    phase: str,
    max_age_seconds: int = 600,
) -> CheckResult:
    """C3 — session_handoff.md was regenerated recently.

    ``phase`` is accepted for API uniformity with C1/C2/C4/C5 but is not
    used for matching: session_handoff is a single file without per-phase
    markers. Iterate 12.1+ callers that want stronger checks can use
    ``read_run_config(...).get("phase_history", {}).get(phase, [])`` to
    compare against the canonical ``phase_completed`` timestamp.
    """
    del phase  # not used today; kept for API symmetry
    name = "C3 session_handoff.md fresh"
    handoff = project_root / _AGENT_DOCS_DIRNAME / "session_handoff.md"
    if not handoff.exists():
        return CheckResult(
            name, False, "session_handoff.md missing",
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


def check_c4_decision_log_has_phase_adr(
    project_root: Path,
    phase: str,
    min_new_adrs: int = 1,
) -> CheckResult:
    """C4 — decision_log.md contains at least one ADR mentioning the phase.

    This is a coarse check by design: ADR titles vary across plugins, so
    we substring-match the phase name inside the body region of every
    parsed ADR header. Phase-specific modules can override with a
    stricter pattern.
    """
    name = f"C4 decision_log has {phase} ADR"
    phase_lc = phase.lower()

    # Iterate decision-drop pattern (H): F3 writes the ADR as a JSON drop
    # under decision-drops/ keyed by run_id; the sequential ADR-NNN lands in
    # decision_log.md only at /shipwright-changelog aggregation. A pending
    # drop satisfies C4 — the decision was taken and recorded.
    if phase_lc == "iterate":
        drop_dir = project_root / ".shipwright" / "agent_docs" / "decision-drops"
        if drop_dir.is_dir():
            drops = [
                p for p in drop_dir.glob("*.json")
                if not p.name.startswith("_")
            ]
            if drops:
                return CheckResult(
                    name, True,
                    f"{len(drops)} decision-drop(s) pending aggregation",
                )

    log = read_decision_log(project_root)
    if not log:
        return CheckResult(name, False, "decision_log.md missing or empty")

    headers = parse_adr_headers(log)
    if not headers:
        return CheckResult(name, False, "no ADR headers parsed")

    hits = [
        h for h in headers
        if phase_lc in h.title.lower()
    ]
    if len(hits) < min_new_adrs:
        return CheckResult(
            name, False,
            f"found {len(hits)} ADR(s) referencing '{phase}', need >= {min_new_adrs}",
        )
    return CheckResult(name, True, f"{len(hits)} ADR(s) referencing '{phase}'")


def check_phase_history_has_run(
    project_root: Path,
    phase: str,
    run_id: str,
) -> CheckResult:
    """Verify ``shipwright_run_config.json::phase_history[<phase>]``
    contains an entry with the given ``run_id``.

    Iterate 12.1 wires this into every phase-specific verifier module
    so a failed ``append_phase_history.py`` call surfaces immediately
    instead of silently leaving a gap in the audit trail. The
    ``run_id`` match is exact — callers must pass the same id they
    used at write time.
    """
    name = f"phase_history[{phase}] has run_id"
    if not run_id:
        return CheckResult(
            name,
            True,
            "skipped (no --run-id supplied)",
        )
    data = read_run_config(project_root)
    if not data:
        return CheckResult(name, False, "shipwright_run_config.json missing or malformed")
    history = data.get("phase_history")
    if not isinstance(history, dict):
        return CheckResult(name, False, "phase_history field missing")
    bucket = history.get(phase)
    if not isinstance(bucket, list):
        return CheckResult(name, False, f"phase_history[{phase}] missing")
    if any(entry.get("run_id") == run_id for entry in bucket):
        return CheckResult(name, True, f"run_id={run_id} present in {phase} history")
    return CheckResult(
        name,
        False,
        f"run_id={run_id} not in phase_history[{phase}] ({len(bucket)} entries)",
    )


def check_c5_changelog_unreleased_has_phase_entry(
    project_root: Path,
    phase: str,
    category: str = "Added",
) -> CheckResult:
    """C5 — the phase recorded a changelog entry.

    Primary evidence is a bullet in ``CHANGELOG.md``'s ``## [Unreleased]``
    → ``### <category>`` sub-section (the legacy inline model — the
    ``append_changelog_entry.py`` helper deduplicates).

    **Drop-directory fallback.** Projects on the ``write_changelog_drop.py``
    / ``aggregate_changelog.py`` model keep ``[Unreleased]`` empty between
    releases and stage each entry as a
    ``CHANGELOG-unreleased.d/<category>/<run_id>_NNN.md`` file. When the
    inline category sub-section is missing or carries no bullets, C5 also
    counts staged drop files. The count is **category-agnostic**: a
    bug-only iterate writes only a ``Fixed/`` drop, so requiring a drop in
    the caller's nominal category (``Added`` for the iterate phase) would
    re-introduce the very false-negative this fallback removes. ``≥ 1``
    drop file → PASS.

    The phase name is accepted for API symmetry but not matched — the
    canon only requires that *some* entry exists.
    """
    del phase  # accepted for API symmetry
    name = f"C5 CHANGELOG [Unreleased] has {category} entry"

    inline = _check_inline_unreleased_category(project_root, name, category)
    if inline.ok:
        return inline

    # Drop-directory model — [Unreleased] stays empty between releases.
    drop_count = _count_changelog_drop_files(project_root)
    if drop_count > 0:
        return CheckResult(
            name, True,
            f"{drop_count} changelog drop file(s) staged under "
            f"CHANGELOG-unreleased.d/ (inline [Unreleased]/{category}: "
            f"{inline.detail})",
        )
    return inline


def _check_inline_unreleased_category(
    project_root: Path,
    name: str,
    category: str,
) -> CheckResult:
    """Inspect the inline ``[Unreleased]`` → ``### <category>`` bullets.

    Returns a passing ``CheckResult`` when the sub-section carries ≥ 1
    bullet, otherwise a failing ``CheckResult`` whose detail (and
    severity) names the specific gap — no CHANGELOG, no ``[Unreleased]``,
    no sub-section, or no bullets. C5 falls back to the drop directory on
    failure.
    """
    changelog = find_changelog(project_root)
    if changelog is None:
        return CheckResult(name, False, "CHANGELOG.md not found",
                           severity=Severity.WARNING.value)
    try:
        content = changelog.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return CheckResult(name, False, f"read error: {e}")
    unreleased = _extract_unreleased_section(content)
    if unreleased is None:
        return CheckResult(name, False, "no [Unreleased] section found")
    category_body = _extract_category_section(unreleased, category)
    if category_body is None:
        return CheckResult(
            name, False, f"[Unreleased]/{category} sub-section missing",
        )
    bullets = len(re.findall(r"^\s*-\s+", category_body, re.MULTILINE))
    if bullets == 0:
        return CheckResult(name, False, f"[Unreleased]/{category} has no bullets")
    return CheckResult(name, True, f"{bullets} bullet(s) in [Unreleased]/{category}")


def _count_changelog_drop_files(project_root: Path) -> int:
    """Count staged Keep-a-Changelog drop files under ``CHANGELOG-unreleased.d/``.

    The drop-directory model (``write_changelog_drop.py``) stages each
    entry as a ``CHANGELOG-unreleased.d/<category>/<run_id>_NNN.md`` file;
    ``aggregate_changelog.py`` folds them into a versioned section at
    release time. Counts ``*.md`` files exactly one level deep —
    ``<category>/<file>.md`` — across every category sub-dir
    (category-agnostic), excluding ``.gitkeep`` placeholders. The
    single-level ``*/*.md`` glob matches the ``write_changelog_drop.py``
    layout exactly and ignores any stray top-level or deeply-nested
    ``.md`` file. Mirrors ``find_changelog``'s monorepo dual-location
    probe (``project_root`` then its parent).
    """
    for base in (
        project_root / "CHANGELOG-unreleased.d",
        project_root.parent / "CHANGELOG-unreleased.d",
    ):
        if base.is_dir():
            return sum(
                1 for p in base.glob("*/*.md")
                if p.is_file() and p.name != ".gitkeep"
            )
    return 0


_UNRELEASED_RE = re.compile(
    r"## \[Unreleased\][^\n]*\n(.*?)(?=\n## \[|\Z)",
    re.DOTALL,
)


def _extract_unreleased_section(changelog_content: str) -> str | None:
    m = _UNRELEASED_RE.search(changelog_content)
    return m.group(1) if m else None


def _extract_category_section(unreleased_body: str, category: str) -> str | None:
    pattern = re.compile(
        rf"### {re.escape(category)}[^\n]*\n(.*?)(?=\n### |\Z)",
        re.DOTALL,
    )
    m = pattern.search(unreleased_body)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# ADR integrity helpers (F1/F2/F3 from shipwright-check plan)
# ---------------------------------------------------------------------------

def check_adr_ids_sequential(project_root: Path) -> CheckResult:
    """F1 — every ADR id is parseable and no duplicates exist.

    Gaps in the sequence are reported but as WARNING-severity (sometimes
    numbers are intentionally reserved across branches).
    """
    name = "F1 ADR ids sequential"
    log = read_decision_log(project_root)
    if not log:
        return CheckResult(
            name, False, "decision_log.md missing or empty",
            severity=Severity.WARNING.value,
        )
    headers = parse_adr_headers(log)
    if not headers:
        return CheckResult(
            name, False, "no ADR headers parsed",
            severity=Severity.WARNING.value,
        )

    unparseable = [h.id for h in headers if extract_adr_id_number(h.id) is None]
    if unparseable:
        return CheckResult(name, False, f"unparseable ADR ids: {unparseable}")
    dupes = find_duplicate_adr_ids(headers)
    if dupes:
        return CheckResult(name, False, f"duplicate ADR ids: {dupes}")

    gaps = find_gaps_in_adr_ids(headers)
    if gaps:
        return CheckResult(
            name, True,
            f"{len(headers)} ADRs, gaps in sequence: {gaps}",
            severity=Severity.WARNING.value,
        )
    return CheckResult(name, True, f"{len(headers)} ADRs, no duplicates, no gaps")


def check_adr_status_valid(project_root: Path) -> CheckResult:
    """F2 — every ADR with a ``**Status:**`` bullet uses a recognised value."""
    name = "F2 ADR status values valid"
    log = read_decision_log(project_root)
    if not log:
        return CheckResult(
            name, False, "decision_log.md missing or empty",
            severity=Severity.WARNING.value,
        )
    headers = parse_adr_headers(log)
    bad: list[str] = []
    for h in headers:
        if h.status is None:
            continue
        if h.status not in ADR_VALID_STATUSES:
            bad.append(f"{h.id}={h.status!r}")
    if bad:
        return CheckResult(name, False, f"invalid statuses: {bad}")
    return CheckResult(name, True, f"{len(headers)} ADRs, all statuses valid-or-unstated")


def check_adr_supersession_exists(project_root: Path) -> CheckResult:
    """F3 — every ``**Supersedes:** ADR-NNN`` reference points to an ADR
    that actually exists in the decision log."""
    name = "F3 ADR supersession targets exist"
    log = read_decision_log(project_root)
    if not log:
        return CheckResult(
            name, False, "decision_log.md missing or empty",
            severity=Severity.WARNING.value,
        )
    headers: list[ADRHeader] = parse_adr_headers(log)
    known: set[str] = {h.id for h in headers}
    dangling: list[str] = []
    for h in headers:
        for ref in h.supersedes:
            if ref not in known:
                dangling.append(f"{h.id} -> {ref}")
    if dangling:
        return CheckResult(name, False, f"dangling supersession refs: {dangling}")
    return CheckResult(
        name, True,
        f"{sum(len(h.supersedes) for h in headers)} supersession ref(s), all resolved",
    )


# ---------------------------------------------------------------------------
# Formatter (shared by verify_phase CLI and the thin
# verify_iterate_finalization.py wrapper)
# ---------------------------------------------------------------------------

@dataclass
class ReportSummary:
    errors: int = 0
    warnings: int = 0
    passes: int = 0
    skipped: int = 0
    results: list[CheckResult] = field(default_factory=list)


def summarise(results: list[CheckResult]) -> ReportSummary:
    summary = ReportSummary(results=list(results))
    for r in results:
        if r.is_skipped:
            summary.skipped += 1
        elif r.ok:
            summary.passes += 1
        elif r.severity == Severity.WARNING.value:
            summary.warnings += 1
        else:
            summary.errors += 1
    return summary


def format_report(title: str, results: list[CheckResult]) -> str:
    summary = summarise(results)
    lines = [
        "================================================================================",
        f"SHIPWRIGHT VERIFIER: {title}",
        "================================================================================",
    ]
    for r in results:
        if r.is_skipped:
            icon = "[90mSKIP[0m"
        elif r.ok:
            icon = "[32m OK [0m"
        elif r.severity == Severity.WARNING.value:
            icon = "[33mWARN[0m"
        else:
            icon = "[31mFAIL[0m"
        lines.append(f"  {icon}  {r.name:<48}  {r.detail}")
    lines.append("--------------------------------------------------------------------------------")
    lines.append(
        f"  {summary.passes} ok, {summary.warnings} warning(s), "
        f"{summary.errors} error(s), {summary.skipped} skipped"
    )
    lines.append("================================================================================")
    return "\n".join(lines)
