"""Group F — ADR structural integrity (plan v7 Option Z) + documentation
hygiene (Iterate C.2 / ADR-060).

F1-F3 are preventive-reruns of iterate-12 common.py verifiers
(sequential IDs, valid status, supersession refs).

F4-F7 are detective-only documentation-hygiene checks added by Iterate
C.2:

- F4 — ADR bloat. ADRs > 60 lines without a ``spec_ref`` link are
  candidates for refactor into a `.shipwright/planning/adr/<NNN>-…`
  long-form spec file (mirrors the A.3 / B.0+ pattern).
- F5 — Architecture drift (content reconciliation). Every decision-drop
  declaring ``architecture_impact ∈ {component, data-flow, convention}``
  must have its ``run_id`` documented in ``architecture.md``; any that
  don't are flagged. Shares the oracle with the F11
  ``check_architecture_documented`` finalize gate via
  ``lib.architecture_doc``. (Replaced the prior ``git log``/marker oracle,
  which never fired on the gitignored decision-drops —
  iterate-2026-06-06-arch-drift-detector.)
- F6 — CLAUDE.md size. CLAUDE.md > 200 lines is a sign that per-
  iterate detail is leaking into the file (webui hit this at 270;
  Phase 0e refactored it down via ADR-spec-folder extraction).
- F7 — CLAUDE.md iterate-annotation leak. Regex-counted occurrences
  of ``Iterate <X> (ADR-NN)`` > 5 indicate inline iterate-detail
  belongs in `.shipwright/planning/adr/<NNN>-…` files instead.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from scripts.audit.audit_adapters import (
    SOURCE_DETECTIVE_ONLY,
    SOURCE_PREVENTIVE_RERUN,
    Finding,
    check_result_to_finding,
    import_iterate12_checks,
    load_shared_lib,
)


_CHECK_TO_ID: tuple[tuple[str, str, str], ...] = (
    ("check_adr_ids_sequential", "F1", "ADR IDs unique + sequential"),
    ("check_adr_status_valid", "F2", "ADR Status in valid enum"),
    ("check_adr_supersession_exists", "F3", "Superseded ADRs reference a replacement"),
)


# ---------------------------------------------------------------------------
# F4-F7 thresholds (Iterate C.2 / ADR-060)
# ---------------------------------------------------------------------------

_ADR_BLOAT_LINE_CAP = 60
_CLAUDE_MD_LINE_CAP = 200
_CLAUDE_MD_ITERATE_REF_CAP = 5

# Match the compact-format ADR header `### ADR-NNN: Title`. The verbose
# old format (`## ADR-NNN | date | ...`) is also detected — only the
# compact form has clean line-counted bodies (ADR-bloat detection
# specifically targets the compact form per the plan).
_ADR_HEADER_RE = re.compile(r"^### ADR-(\d+):\s*.+$", re.MULTILINE)

# Match "Iterate X.Y (ADR-NN)" / "Iterate B0" / similar inline annotations.
_ITERATE_REF_RE = re.compile(r"Iterate [0-9A-Z][0-9A-Z.]*(?:\s*\(?ADR-[0-9]+\)?)?")


# ---------------------------------------------------------------------------
# F4 — ADR bloat
# ---------------------------------------------------------------------------


def _check_f4(project_root: Path) -> tuple[str, str, str, list[str]]:
    """Return ``(status, severity, detail, evidence)`` for ADR-bloat.

    Reads ``.shipwright/agent_docs/decision_log.md``, locates each
    compact-format ADR section, counts the lines between consecutive
    `### ADR-N` headers, and flags ADRs whose body exceeds
    ``_ADR_BLOAT_LINE_CAP`` AND that don't carry a
    ``- **Details:** [...](...)`` link to a long-form ADR spec file.
    """
    log = project_root / ".shipwright" / "agent_docs" / "decision_log.md"
    if not log.exists():
        return "skip", "LOW", "decision_log.md not present", []
    try:
        content = log.read_text(encoding="utf-8")
    except OSError as exc:
        return "skip", "LOW", f"decision_log.md unreadable: {exc}", []

    lines = content.splitlines()
    # Walk the line list once, building (adr_id, body_lines) per section.
    sections: list[tuple[str, list[str]]] = []
    current_id: str | None = None
    current_body: list[str] = []
    for line in lines:
        m = _ADR_HEADER_RE.match(line)
        if m:
            if current_id is not None:
                sections.append((current_id, current_body))
            current_id = f"ADR-{m.group(1)}"
            current_body = []
        elif current_id is not None:
            current_body.append(line)
    if current_id is not None:
        sections.append((current_id, current_body))

    bloated: list[tuple[str, int]] = []
    for adr_id, body in sections:
        if len(body) <= _ADR_BLOAT_LINE_CAP:
            continue
        # ``spec_ref`` aggregates render as ``- **Details:** [<text>](<url>)``
        # with the URL pointing at ``.../planning/adr/<NNN>-<slug>.md``.
        # Reviewer-flagged OpenAI-M1: a bare "**Details:**" mention
        # without a real link target is not a valid spec_ref. Match
        # the full link shape via `_DETAILS_LINK_RE` instead of
        # substring-poking individual lines.
        body_text = "\n".join(body)
        if not _DETAILS_LINK_RE.search(body_text):
            bloated.append((adr_id, len(body)))

    if not bloated:
        return "pass", "MEDIUM", "no bloated ADRs without spec_ref", []
    bloated.sort(key=lambda x: -x[1])
    head = ", ".join(f"{adr} ({n} lines)" for adr, n in bloated[:5])
    if len(bloated) > 5:
        head += f", … (+{len(bloated) - 5})"
    detail = (
        f"{len(bloated)} ADR(s) exceed {_ADR_BLOAT_LINE_CAP} lines without a "
        f"spec_ref link — refactor each into "
        f".shipwright/planning/adr/<NNN>-<slug>.md and link via "
        f"--spec-ref. Heaviest: {head}."
    )
    evidence = [f"{adr}: {n} lines" for adr, n in bloated]
    return "fail", "MEDIUM", detail, evidence


# ---------------------------------------------------------------------------
# F5 — Architecture drift
# ---------------------------------------------------------------------------


# Recognize the `**Details:** [...](...)` link rendered by
# aggregate_decisions.py for an ADR's `spec_ref`. The URL part
# (`(...)`) is what F4 cares about; mere text mention of "Details"
# without an actual link doesn't count. The regex matches the
# relative path `../planning/adr/...` the aggregator emits from a
# 2-deep decision_log.md location.
_DETAILS_LINK_RE = re.compile(
    r"\*\*Details:\*\*\s*\[[^\]]*\]\(\S*planning/adr/[^)]+\)",  # artifact-path-canon: legacy
    re.IGNORECASE,
)


def _check_f5(project_root: Path) -> tuple[str, str, str, list[str]]:
    """Return F5 status — architecture.md *content* vs arch-impact drops.

    Reconciles every decision-drop declaring ``architecture_impact ∈
    {component, data-flow, convention}`` against the TEXT of
    ``architecture.md``: each such drop's ``run_id`` MUST appear there (the
    contract F2 prescribes). This is the same content oracle the
    ``test_architecture_md_reflects_arch_impact`` drift test uses, shared via
    ``lib.architecture_doc`` so the detective and the F11 finalize gate
    (``check_architecture_documented``) cannot diverge.

    Worktree-aware: decision-drops are gitignored staging that live in the MAIN
    repo, so the drops dir is resolved via
    ``events_log.resolve_main_repo_root``; ``architecture.md`` is tracked, so it
    is read from ``project_root`` (the same file in a worktree and the main
    tree). In a clean CI checkout the drops dir is absent → ``skip`` — F5 is a
    local/worktree detective; the authoritative prevention is the F11
    ``check_architecture_documented`` gate (decision-drops never reach CI).

    Event-ownership scoped: only drops whose ``run_id`` is in this tree's
    committed ``shipwright_events.jsonl`` (``events_log.finalized_run_ids``) are
    reconciled. A cross-branch campaign sibling's drop bleeds into the shared
    main-rooted drops dir but its target-doc entry lands only on the sibling's
    own unmerged branch — without scoping it false-flags drift on every other
    branch. Fail-open when no event log exists (ownership unknowable).

    Drift states:
    - drops dir absent → skip
    - drop not owned by this tree (run_id absent from a present events.jsonl) →
      excluded from reconciliation
    - corrupt drop JSON → fail (a malformed drop must not hide drift)
    - no arch-impact (and no unknown-impact) drops → pass
    - architecture.md missing/unreadable while arch-impact drops exist → fail
    - any arch-impact run_id absent from architecture.md → fail (lists them)
    - unknown (non-canonical, non-none) impact value → fail (blind-spot guard)
    - else → pass

    Replaces the prior ``git log <marker>..HEAD`` oracle, which could never fire
    on the gitignored drops (they are never committed, so the diff was always
    empty) — iterate-2026-06-06-arch-drift-detector. The adopt-side marker
    producer is untouched; F5 no longer gates on the marker.
    """
    archdoc = load_shared_lib("architecture_doc")
    events_log = load_shared_lib("events_log")

    main_root = events_log.resolve_main_repo_root(project_root)
    base = Path(main_root) if main_root is not None else Path(project_root)
    drops_dir = base / ".shipwright" / "agent_docs" / "decision-drops"

    if not drops_dir.is_dir():
        return "skip", "LOW", "no decision-drops dir", []

    records, corrupt = archdoc.scan_drops(drops_dir)
    if corrupt:
        head = ", ".join(corrupt[:3]) + ("…" if len(corrupt) > 3 else "")
        return (
            "fail",
            "MEDIUM",
            f"{len(corrupt)} decision-drop(s) failed to parse — cannot reliably "
            f"assess architecture drift. Fix or remove: {head}.",
            corrupt,
        )

    # Scope to drops OWNED by this tree's lineage (run_id in this tree's committed
    # events.jsonl) so cross-branch campaign sibling drops — which bleed through
    # the shared main-rooted decision-drops dir but whose target-doc entry lives
    # only on the sibling's own unmerged branch — aren't flagged as drift here.
    # Fail-open when no event log exists (ownership unknowable): keeps the
    # clean-checkout / hermetic behavior, and is never weaker than whole-set.
    owned = events_log.finalized_run_ids(project_root)
    if owned is not None:
        records = archdoc.records_in_run_set(records, owned)

    arch_drops = archdoc.arch_impact_records(records)
    unknown = archdoc.unknown_impact_records(records)
    if not arch_drops and not unknown:
        return "pass", "MEDIUM", "no architecture-impact drops to reconcile", []

    # Route each impact to its target doc via IMPACT_TARGETS (convention →
    # conventions.md; component/data-flow → architecture.md), checking both docs.
    texts = archdoc.read_target_texts(project_root / ".shipwright" / "agent_docs")
    missing = archdoc.missing_entries(records, texts)
    if missing or unknown:
        evidence = [
            f"{r.drop_file} run_id={r.run_id} impact={r.impact} "
            f"target={archdoc.IMPACT_TARGETS[r.impact][0]}"
            for r in missing
        ]
        evidence += [f"{r.drop_file} unknown-impact={r.impact!r}" for r in unknown]
        parts: list[str] = []
        if missing:
            head = ", ".join(r.run_id for r in missing[:3])
            if len(missing) > 3:
                head += f", … (+{len(missing) - 3})"
            parts.append(
                f"{len(missing)} arch-impact drop(s) not documented in their "
                "target doc — add a one-line bullet (convention → conventions.md "
                "'## Convention Updates'; component/data-flow → architecture.md "
                f"'## Architecture Updates') naming each run_id + what changed: {head}"
            )
        if unknown:
            uhead = ", ".join(f"{r.run_id}={r.impact!r}" for r in unknown[:3])
            parts.append(
                f"{len(unknown)} drop(s) with an unrecognized architecture_impact "
                f"(expected component|data-flow|convention|none): {uhead}"
            )
        return "fail", "MEDIUM", " | ".join(parts), evidence

    return (
        "pass",
        "MEDIUM",
        f"all {len(arch_drops)} arch-impact drop(s) documented in their target doc",
        [],
    )


# ---------------------------------------------------------------------------
# F6 / F7 — CLAUDE.md hygiene
# ---------------------------------------------------------------------------


def _check_f6(project_root: Path) -> tuple[str, str, str, list[str]]:
    """CLAUDE.md > _CLAUDE_MD_LINE_CAP lines."""
    claude_md = project_root / "CLAUDE.md"
    if not claude_md.exists():
        return "skip", "LOW", "CLAUDE.md not present", []
    try:
        line_count = sum(1 for _ in claude_md.open("r", encoding="utf-8"))
    except OSError as exc:
        return "skip", "LOW", f"CLAUDE.md unreadable: {exc}", []
    if line_count <= _CLAUDE_MD_LINE_CAP:
        return "pass", "MEDIUM", f"CLAUDE.md is {line_count} lines (≤ {_CLAUDE_MD_LINE_CAP})", []
    return (
        "fail",
        "MEDIUM",
        f"CLAUDE.md is {line_count} lines, exceeds the {_CLAUDE_MD_LINE_CAP}-line "
        f"hygiene cap — consider moving per-iterate detail into "
        f".shipwright/planning/adr/<NNN>-<slug>.md spec files.",
        [f"line_count={line_count}"],
    )


def _check_f7(project_root: Path) -> tuple[str, str, str, list[str]]:
    """CLAUDE.md inline iterate-annotation count > _CLAUDE_MD_ITERATE_REF_CAP."""
    claude_md = project_root / "CLAUDE.md"
    if not claude_md.exists():
        return "skip", "LOW", "CLAUDE.md not present", []
    try:
        content = claude_md.read_text(encoding="utf-8")
    except OSError as exc:
        return "skip", "LOW", f"CLAUDE.md unreadable: {exc}", []
    matches = _ITERATE_REF_RE.findall(content)
    n = len(matches)
    if n <= _CLAUDE_MD_ITERATE_REF_CAP:
        return "pass", "MEDIUM", f"{n} inline iterate references (≤ {_CLAUDE_MD_ITERATE_REF_CAP})", []
    sample = matches[:3]
    return (
        "fail",
        "MEDIUM",
        f"{n} inline 'Iterate X (ADR-NN)' references in CLAUDE.md exceed the "
        f"{_CLAUDE_MD_ITERATE_REF_CAP}-reference cap — move per-iterate detail "
        f"into .shipwright/planning/adr/<NNN>-<slug>.md spec files. "
        f"Sample: {sample}.",
        # Reviewer-flagged code-review-M2: evidence carries the FULL
        # match list (not just the detail's top-3 sample), so the
        # audit report shows every offending reference.
        matches,
    )


# ---------------------------------------------------------------------------
# Group entry point
# ---------------------------------------------------------------------------


def _detective_finding(
    check_id: str,
    name: str,
    fn,
    project_root: Path,
) -> Finding:
    """Adapter: turn one of the F4-F7 check helpers into a Finding."""
    try:
        status, severity, detail, evidence = fn(project_root)
    except Exception as exc:  # noqa: BLE001
        return Finding(
            group="F", check_id=check_id, name=name,
            severity="HIGH", source=SOURCE_DETECTIVE_ONLY, status="fail",
            detail=f"check raised {type(exc).__name__}: {exc}",
        )
    return Finding(
        group="F", check_id=check_id, name=name,
        severity=severity, source=SOURCE_DETECTIVE_ONLY, status=status,
        detail=detail, evidence=evidence,
    )


def run(
    project_root: Path,
    _config: dict[str, Any] | None,
    _data: Any,
) -> list[Finding]:
    checks = import_iterate12_checks()
    findings: list[Finding] = []

    for fn_name, check_id, human_name in _CHECK_TO_ID:
        fn = checks[fn_name]
        try:
            result = fn(project_root)
        except Exception as exc:  # noqa: BLE001
            findings.append(Finding(
                group="F", check_id=check_id, name=human_name,
                severity="HIGH", source=SOURCE_PREVENTIVE_RERUN, status="fail",
                detail=f"check raised {type(exc).__name__}: {exc}",
            ))
            continue
        finding = check_result_to_finding(
            result, group="F", check_id=check_id,
            source=SOURCE_PREVENTIVE_RERUN,
            # F1 (gap) is most actionable via a manual ADR fix, not iterate.
            suggested_iterate_cmd=None,
        )
        finding.name = human_name
        findings.append(finding)

    # Iterate C.2 detective-only additions.
    findings.append(_detective_finding(
        "F4", "ADR bloat (> 60 lines without spec_ref)", _check_f4, project_root,
    ))
    findings.append(_detective_finding(
        "F5", "Architecture marker vs arch-impact drops", _check_f5, project_root,
    ))
    findings.append(_detective_finding(
        "F6", "CLAUDE.md size hygiene", _check_f6, project_root,
    ))
    findings.append(_detective_finding(
        "F7", "CLAUDE.md inline iterate-annotation leak", _check_f7, project_root,
    ))

    return findings
