"""F11 verifier check: repo-agnostic agent-doc canonical SHAPE.

Companion to ``agent_doc_budget_check`` (length). Reuses the shared SSoT
(``lib.agent_doc_shape``) + the forward-only git-base diff in
``tools.check_agent_doc_shape`` so "every dated changelog bullet is
``- **<run_id|ADR-NNN>** (date): <Impact> — <sentence>. → <pointer>``" enforces
at finalize in EVERY repo (adopted repos via the plugin cache). Only
NEW/anchor-changed entries block (forward-only vs the git base).
Origin: iterate-2026-07-17-arch-doc-refresh-harden.
"""

from __future__ import annotations

from pathlib import Path

from .common import CheckResult, Severity


def check_agent_doc_shape(
    project_root: Path, run_id: str = "", commit_hash: str = "",
) -> CheckResult:
    """No NEW/anchor-changed dated bullet under ``## Architecture Updates`` /
    ``## Convention Updates`` may deviate from the canonical
    ``- **<run_id|ADR-NNN>** (YYYY-MM-DD): <Impact> — <sentence>. → <pointer>``
    form (Campaign / sub_iterate / free-text anchors and a missing Impact
    separator / arrow pointer are rejected). Forward-only vs the git base, so a
    legacy non-canonical entry the author didn't touch never fails a later
    iterate. ``## Learnings`` (date-first grammar) is out of scope. Fail-soft
    SKIP when no git base is resolvable (clone without a remote, detached state).
    """
    name = "agent-doc entry shape (canonical anchors)"
    try:
        from tools.check_agent_doc_shape import find_violations
    except Exception as exc:  # noqa: BLE001 — never crash finalize on an import slip
        return CheckResult(
            name, True, f"skipped (import error: {exc})", severity=Severity.SKIPPED.value,
        )

    violations, base = find_violations(project_root)
    if base is None:
        return CheckResult(
            name, True, "skipped (no git base resolvable)", severity=Severity.SKIPPED.value,
        )
    if not violations:
        return CheckResult(name, True, "all new changelog bullets canonical")

    shown = "; ".join(f"{f} '{h}': {m}" for f, h, m in violations[:5])
    more = "" if len(violations) <= 5 else f" (+{len(violations) - 5} more)"
    plural = "y" if len(violations) == 1 else "ies"
    return CheckResult(
        name, False,
        f"{len(violations)} non-canonical agent-doc entr{plural} — each dated changelog "
        f"bullet must be '- **<run_id|ADR-NNN>** (date): <Impact> — <sentence>. → "
        f"<pointer>' (references/F2.md): {shown}{more}",
    )
