"""Append a decision entry to .shipwright/agent_docs/decision_log.md.

Auto-numbers entries sequentially and auto-dates with today's date.
Never overwrites existing entries — always appends.
Compact ADR format: one H3 per entry, bullet points for fields.

Usage (from target project root):
    uv run <path>/write_decision_log.py --section "Build — 01-auth" --commit abc1234 \
        --context "Code review found session-based auth" \
        --decision "Keep JWT, refresh 7 days" \
        --consequences "Stateless for scaling" \
        --rejected "Session cookies, OAuth-only" \
        --title "JWT over Session Auth"
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path


def get_next_adr_number(content: str) -> int:
    """Extract the highest ADR number and return next."""
    numbers = re.findall(r"### ADR-(\d+)", content)
    if not numbers:
        # Also check old format for backwards compatibility
        numbers = re.findall(r"## ADR-(\d+)", content)
    if not numbers:
        return 1
    return max(int(n) for n in numbers) + 1


def _truncate_title(text: str, max_len: int = 60) -> str:
    """Truncate text to max_len, adding ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3].rsplit(" ", 1)[0] + "..."


# ADR length budget — see shipwright-iterate SKILL.md F3.
# decision_log.md is always-loaded Layer-1 context, so every verbose ADR field
# shows up in the context window of every future iterate run. 500 chars is
# ~1-3 sentences — enough to be self-contained without bloating the budget.
# Single-user-repo policy (Iterate A.3): NEW ADR fields are hard-rejected at
# write time; existing bloated entries are left alone (no retroactive rewrite).
ADR_FIELD_MAX_CHARS = 500

# Canonical ADR-spec folder for the long-form details that don't fit the 500
# char per-field budget. ``spec_ref`` in a decision-drop points into this
# folder. Aggregator renders the link verbatim and rebuilds INDEX.md.
ADR_SPEC_FOLDER = ".shipwright/planning/adr"
ADR_SPEC_FOLDER_HINT = (
    f"{ADR_SPEC_FOLDER}/<NNN>-<slug>.md (flat, one file per ADR, "
    "ADR-number prefix gives collision protection)"
)


class FieldLengthError(ValueError):
    """Raised when an ADR field exceeds ``ADR_FIELD_MAX_CHARS`` at write time.

    Iterate A.3 promotes the prior advisory warning to a hard reject for new
    drops. The error message includes the spec-folder hint so the operator
    knows where to move overflowed prose.
    """

# Header written when decision_log.md does not yet exist. Shared with
# aggregate_decisions.py so the iterate decision-drop path and the direct
# append path emit the identical header.
DECISION_LOG_HEADER = (
    "# Decision Log\n\n"
    "> Project-specific decisions only. Profile-level decisions are "
    "implicit in the stack profile.\n"
)


def check_field_length(field_name: str, value: str, max_chars: int = ADR_FIELD_MAX_CHARS) -> str | None:
    """Return a warning string if `value` exceeds the budget, else None.

    Pure helper, no side effects. Used by `collect_length_warnings` to build
    the full list of warnings and by tests to assert per-field behavior.
    """
    if not value:
        return None
    if len(value) <= max_chars:
        return None
    return (
        f"ADR --{field_name} field is {len(value)} chars "
        f"(budget: {max_chars}). Move the long-form prose into "
        f"{ADR_SPEC_FOLDER_HINT} and reference it via --spec-ref."
    )


def enforce_field_length_limits(
    *,
    context: str = "",
    decision: str = "",
    consequences: str = "",
    rationale: str = "",
    rejected: str = "",
    max_chars: int = ADR_FIELD_MAX_CHARS,
) -> None:
    """Raise ``FieldLengthError`` if any field exceeds the budget.

    Hard-reject for new drops (Iterate A.3). Existing logs are not touched —
    only callers of this function are the live write paths (CLI append and
    the iterate decision-drop writer). The exception message lists every
    offender so the operator does not need to re-run after each fix.
    """
    offenders = collect_length_warnings(
        context=context, decision=decision, consequences=consequences,
        rationale=rationale, rejected=rejected, max_chars=max_chars,
    )
    if not offenders:
        return
    bullet = "\n  - ".join(offenders)
    raise FieldLengthError(
        "ADR field(s) over the "
        f"{max_chars}-char budget — move the long-form prose into "
        f"{ADR_SPEC_FOLDER_HINT} and reference it via --spec-ref:\n"
        f"  - {bullet}"
    )


def collect_length_warnings(
    *,
    context: str,
    decision: str,
    consequences: str,
    rationale: str,
    rejected: str,
    max_chars: int = ADR_FIELD_MAX_CHARS,
) -> list[str]:
    """Return non-empty warning strings for every field over the budget.

    Order matches the field names so humans can locate them in the CLI call.
    """
    warnings: list[str] = []
    for name, value in (
        ("context", context),
        ("decision", decision),
        ("consequences", consequences),
        ("rationale", rationale),
        ("rejected", rejected),
    ):
        warning = check_field_length(name, value, max_chars=max_chars)
        if warning is not None:
            warnings.append(warning)
    return warnings


def _format_spec_ref_link(spec_ref: str) -> str:
    """Render the **Details:** bullet for an ADR with a spec-folder companion.

    ``spec_ref`` is the path provided by the operator (relative to project
    root). The decision_log.md sits at ``.shipwright/agent_docs/``, so the
    rendered link is computed relative to that location (``../planning/...``)
    when the spec lives under ``.shipwright/``. Any other path is rendered
    verbatim so the operator can opt into a different convention without
    silent rewrites.
    """
    s = spec_ref.strip().replace("\\", "/")
    if not s:
        return ""
    label = s.rsplit("/", 1)[-1] or s
    href: str
    if s.startswith(".shipwright/"):
        # decision_log.md → .shipwright/planning/adr/foo.md is "../planning/adr/foo.md"
        href = "../" + s[len(".shipwright/"):]
    else:
        href = s
    return f"- **Details:** [{label}]({href})"


def format_entry(
    number: int,
    section_ref: str,
    commit_hash: str,
    context: str,
    decision: str,
    consequences: str,
    rejected: str = "",
    title: str = "",
    rationale: str = "",
    entry_date: str | None = None,
    run_id: str = "",
    spec_ref: str = "",
) -> str:
    """Format a single ADR entry in compact format.

    ``entry_date`` overrides the date stamp — ``aggregate_decisions.py`` passes
    the drop's authoring date so an ADR aggregated weeks later still carries
    the date it was decided. ``run_id``, when given, adds a ``Run-ID:`` line:
    the iterate decision-drop pattern keys ADRs by run_id, and the finalization
    verifier resolves run_id ↔ ADR-NNN through that line.
    """
    today = entry_date or date.today().isoformat()
    display_title = title or _truncate_title(decision)

    lines = [
        "",
        "---",
        "",
        f"### ADR-{number:03d}: {display_title}",
        f"- **Date:** {today}",
        f"- **Section:** {section_ref}",
    ]
    if run_id:
        lines.append(f"- **Run-ID:** {run_id}")
    lines += [
        f"- **Context:** {context}",
        f"- **Decision:** {decision}",
        f"- **Commit:** {commit_hash}",
    ]

    if rationale:
        lines.append(f"- **Rationale:** {rationale}")

    if consequences:
        lines.append(f"- **Consequences:** {consequences}")

    if rejected:
        lines.append(f"- **Rejected:** {rejected}")

    spec_line = _format_spec_ref_link(spec_ref)
    if spec_line:
        lines.append(spec_line)

    lines.append("")
    return "\n".join(lines)


def _append_architecture_update(
    project_root: Path,
    adr_number: int,
    impact_type: str,
    summary: str,
    entry_date: str | None = None,
) -> str | None:
    """Append an update note to architecture.md or conventions.md.

    Returns the target filename if updated, None otherwise.
    """
    if impact_type in ("component", "data-flow"):
        target = project_root / ".shipwright" / "agent_docs" / "architecture.md"
        section_header = "## Architecture Updates"
    elif impact_type == "convention":
        target = project_root / ".shipwright" / "agent_docs" / "conventions.md"
        section_header = "## Convention Updates"
    else:
        return None

    if not target.exists():
        return None

    content = target.read_text(encoding="utf-8")
    if section_header not in content:
        content = content.rstrip() + f"\n\n{section_header}\n"

    today = entry_date or date.today().isoformat()
    # rstrip first so a file ending in "\n" doesn't add a blank line per bullet.
    content = content.rstrip("\n") + f"\n- **ADR-{adr_number:03d}** ({today}): {summary}\n"
    target.write_text(content, encoding="utf-8")
    return target.name


def append_decision(
    project_root: str | Path,
    section_ref: str,
    commit_hash: str,
    context: str,
    decision: str,
    consequences: str,
    rejected: str = "",
    title: str = "",
    rationale: str = "",
    status: str = "Accepted",  # kept for backwards compat, not used in compact format
    architecture_impact: str = "none",  # "component" | "data-flow" | "convention" | "none"
    entry_date: str | None = None,
    run_id: str = "",
    spec_ref: str = "",
) -> int:
    """Append a decision entry to the decision log. Returns the ADR number.

    Hard-rejects new ADRs whose fields exceed ``ADR_FIELD_MAX_CHARS`` (Iterate
    A.3 — single-user repo, no staged rollout). Move long-form prose into the
    ADR spec folder and pass ``spec_ref``.
    """
    enforce_field_length_limits(
        context=context, decision=decision, consequences=consequences,
        rationale=rationale, rejected=rejected,
    )

    project_root = Path(project_root)
    log_path = project_root / ".shipwright" / "agent_docs" / "decision_log.md"

    # Ensure .shipwright/agent_docs/ exists
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing or create header
    if log_path.exists():
        content = log_path.read_text(encoding="utf-8")
    else:
        content = DECISION_LOG_HEADER

    number = get_next_adr_number(content)
    entry = format_entry(
        number, section_ref, commit_hash, context, decision, consequences,
        rejected, title, rationale, entry_date=entry_date, run_id=run_id,
        spec_ref=spec_ref,
    )
    content += entry

    log_path.write_text(content, encoding="utf-8")

    # Append architecture/convention update if applicable
    if architecture_impact != "none":
        summary = title or _truncate_title(decision)
        _append_architecture_update(project_root, number, architecture_impact, summary)

    return number


def main() -> None:
    """CLI entry point."""
    import os

    parser = argparse.ArgumentParser(description="Append a decision to the decision log")
    parser.add_argument("--project-root", default=None, help="Project root directory (default: CWD)")
    parser.add_argument("--section", required=True, help="Section reference (e.g. 'Build — 01-auth')")
    parser.add_argument("--commit", required=True, help="Commit hash")
    parser.add_argument("--context", required=True, help="Context/background for the decision")
    parser.add_argument("--decision", required=True, help="The decision made")
    parser.add_argument("--consequences", required=True, help="Consequences of the decision")
    parser.add_argument("--rejected", default="", help="Rejected alternatives")
    parser.add_argument("--title", default="", help="Short title for the ADR entry (default: truncated decision)")
    parser.add_argument("--rationale", default="", help="Rationale (if different from consequences)")
    parser.add_argument("--status", default="Accepted", help="Status (kept for backwards compat)")
    parser.add_argument("--architecture-impact", default="none",
                        choices=["component", "data-flow", "convention", "none"],
                        help="If not 'none', appends update to architecture.md or conventions.md")
    parser.add_argument(
        "--spec-ref",
        default="",
        help=(
            "Optional path to long-form ADR spec under "
            f"{ADR_SPEC_FOLDER}/<NNN>-<slug>.md. Rendered as a "
            "`**Details:** [...]` bullet in the ADR row. Required when a "
            "field would otherwise exceed the 500-char budget."
        ),
    )
    args = parser.parse_args()

    project_root = Path(args.project_root) if args.project_root else Path(os.getcwd())

    try:
        number = append_decision(
            project_root,
            section_ref=args.section,
            commit_hash=args.commit,
            context=args.context,
            decision=args.decision,
            consequences=args.consequences,
            rejected=args.rejected,
            title=args.title,
            rationale=args.rationale,
            status=args.status,
            architecture_impact=args.architecture_impact,
            spec_ref=args.spec_ref,
        )
    except FieldLengthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
    print(f"ADR-{number:03d} appended to .shipwright/agent_docs/decision_log.md")


if __name__ == "__main__":
    main()
