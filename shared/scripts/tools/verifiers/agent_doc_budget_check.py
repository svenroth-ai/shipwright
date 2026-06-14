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
    ``## Learnings``) may exceed ``ENTRY_MAX_CHARS``. Only NEW/anchor-changed
    entries block (forward-only vs the git base), so a legacy over-budget entry
    the author didn't touch never fails a later iterate. Fail-soft SKIP when no
    git base is resolvable (clone without a remote, detached state).
    """
    name = "agent-doc entry budget (one-line pointers)"
    try:
        from lib.agent_doc_budget import ENTRY_MAX_CHARS
        from tools.check_agent_doc_budget import find_violations
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
        return CheckResult(name, True, f"all new entries <= {ENTRY_MAX_CHARS} chars")

    shown = "; ".join(f"{f} '{h}': {m}" for f, h, m in violations[:5])
    more = "" if len(violations) <= 5 else f" (+{len(violations) - 5} more)"
    plural = "y" if len(violations) == 1 else "ies"
    return CheckResult(
        name, False,
        f"{len(violations)} over-budget NEW entr{plural} — keep each a one-line "
        f"'what + ADR pointer'; move detail to the ADR / .shipwright/planning/adr/ "
        f"(references/F2.md, reflection.md): {shown}{more}",
    )
