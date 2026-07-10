"""F11 verifier check: repo-agnostic agent-doc entry budget.

Extracted from ``iterate_checks.py`` (kept under its bloat baseline) — mirrors
the ``integration_coverage.py`` split. The check reuses the shared SSoT
(``lib.agent_doc_budget``) and the forward-only git-base diff in
``tools.check_agent_doc_budget`` so the "one line per entry, <= 600 chars" rule
enforces at finalize in EVERY repo, including adopted repos via the plugin
cache. Origin: iterate-2026-06-14-agent-doc-entry-budget-gate.
"""

from __future__ import annotations

from pathlib import Path

from .common import CheckResult, Severity


def check_agent_doc_budget(
    project_root: Path, run_id: str = "", commit_hash: str = "",
) -> CheckResult:
    """No NEW/changed entry under the three always-loaded agent-doc append
    sections (``## Architecture Updates`` / ``## Convention Updates`` /
    ``## Learnings``) may exceed ``ENTRY_MAX_CHARS``, and CLAUDE.md may not
    net-grow by more than ``CLAUDE_MD_MAX_NEW_LINES`` (only when it exists both
    at base and worktree; ``SHIPWRIGHT_CLAUDE_MD_GROWTH_OK=1`` skips just the
    growth rule, surfaced as a note on the SUCCESS message — never a
    violation). Only NEW/anchor-changed entries block (forward-only vs the git
    base), so a legacy over-budget entry the author didn't touch never fails a
    later iterate. Fail-soft SKIP when no git base is resolvable (clone without
    a remote, detached state).
    """
    name = "agent-doc entry budget (one-line pointers)"
    try:
        from lib.agent_doc_budget import ENTRY_MAX_CHARS
        from tools.check_agent_doc_budget import (
            GROWTH_OK_ENV,
            claude_md_growth_overridden,
            find_violations,
        )
    except Exception as exc:  # noqa: BLE001 — never crash finalize on an import slip
        return CheckResult(
            name, True, f"skipped (import error: {exc})", severity=Severity.SKIPPED.value,
        )

    growth_overridden = claude_md_growth_overridden()
    violations, base = find_violations(project_root, check_claude_md=not growth_overridden)
    if base is None:
        return CheckResult(
            name, True, "skipped (no git base resolvable)", severity=Severity.SKIPPED.value,
        )
    if not violations:
        growth_part = (
            f"CLAUDE.md growth check skipped ({GROWTH_OK_ENV}=1)"
            if growth_overridden else "CLAUDE.md growth ok"
        )
        return CheckResult(
            name, True, f"all new entries <= {ENTRY_MAX_CHARS} chars; {growth_part}",
        )

    shown = "; ".join(f"{f} '{h}': {m}" for f, h, m in violations[:5])
    more = "" if len(violations) <= 5 else f" (+{len(violations) - 5} more)"
    plural = "" if len(violations) == 1 else "s"
    return CheckResult(
        name, False,
        f"{len(violations)} agent-doc budget violation{plural} — keep each entry "
        f"a one-line 'what + ADR pointer' and CLAUDE.md a terse invariant index; "
        f"move detail to the ADR / .shipwright/planning/adr/ "
        f"(references/F2.md, reflection.md): {shown}{more}",
    )
