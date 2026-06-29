"""Staleness banner for the detective ``audit-report.md`` (F4).

The detective audit (``run_audit.py``, invoked only by ``/shipwright-compliance``)
is the sole producer of ``.shipwright/compliance/audit-report.md``. Routine
compliance regens after a pipeline phase (``update_compliance.py --phase <name>``)
refresh the dashboard / RTM / SBOM / test-evidence / change-history but do NOT
re-run the audit, so the on-disk report can silently show month-old findings that
are already resolved.

This module stamps an idempotent, HTML-comment-delimited staleness banner into
the report during those routine regens. The banner is keyed ONLY to the audit's
own ``Generated:`` timestamp (already in the file), so re-stamping is byte-stable
— a repeated regen hits the ``new_text == text`` no-op and writes nothing. That
matters because the report is gitignored in this monorepo but *tracked* in some
adopted repos (e.g. shipwright-webui); a per-call timestamp would otherwise churn
that tracked file on every finalize. ``run_audit.py`` rewrites the file from
scratch each run, so a fresh audit naturally clears the banner.

Distinct from the similarly-named :mod:`scripts.audit.audit_staleness`, which
*checks* whether tracked compliance docs match their last finalize snapshot
(Group E, ``DOC_REGISTRY``). This module only *writes* a one-off banner into the
(non-registry) audit-report.md. Stdlib-only so ``update_compliance`` can import
it without pulling in the audit machinery (whose ``audit_adapters`` import
performs ``sys.path`` surgery).
"""

from __future__ import annotations

import re
from pathlib import Path

AUDIT_REPORT_REL = ".shipwright/compliance/audit-report.md"

_MARKER_START = "<!-- shipwright:audit-staleness:start -->"
_MARKER_END = "<!-- shipwright:audit-staleness:end -->"
# Match an existing banner (markers + body, DOTALL) so a re-stamp replaces it.
_MARKER_BLOCK_RE = re.compile(
    re.escape(_MARKER_START) + r".*?" + re.escape(_MARKER_END),
    re.DOTALL,
)
_GENERATED_RE = re.compile(r"(?m)^Generated:\s*(.+?)\s*$")
_BLANK_RUN_RE = re.compile(r"\n{3,}")


def _banner(audit_ts: str) -> str:
    when = f"generated {audit_ts}" if audit_ts else "from a previous run"
    return (
        f"{_MARKER_START}\n"
        f"> ⚠️ **Possibly stale — re-run `/shipwright-compliance`.** This detective "
        f"audit was {when}; routine compliance regens refresh the dashboard but do "
        f"**not** re-run the audit, so the findings below may already be resolved. "
        f"Compare the `Generated:` line above with the dashboard's.\n"
        f"{_MARKER_END}"
    )


def mark_audit_report_stale(project_root: Path) -> dict:
    """Stamp a staleness banner into ``audit-report.md`` after a routine regen.

    Idempotent and byte-stable: the banner is keyed only to the audit's own
    ``Generated:`` timestamp, so a repeated regen rewrites nothing (``stamped``
    is ``False`` with ``reason="unchanged"``). Noop when the report is absent.
    Returns a small status dict for the caller's JSON output.
    """
    project_root = Path(project_root)
    path = project_root / AUDIT_REPORT_REL
    if not path.is_file():
        return {"stamped": False, "reason": "absent"}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"stamped": False, "reason": f"read_error: {exc}"}

    # Drop any prior banner, then collapse the blank run it leaves behind so the
    # text returns to its canonical pre-banner shape (keeps re-stamps stable).
    cleaned = _BLANK_RUN_RE.sub("\n\n", _MARKER_BLOCK_RE.sub("", text))

    m = _GENERATED_RE.search(cleaned)
    audit_ts = m.group(1) if m else ""
    banner = _banner(audit_ts)

    lines = cleaned.splitlines()
    # Insert after the contiguous header block (``Generated:`` + optional
    # ``Project:``). Fall back to just after the H1 title (or the very top) for an
    # unexpected report shape.
    insert_at = 1 if lines and lines[0].startswith("#") else 0
    for i, line in enumerate(lines):
        if line.startswith("Generated:"):
            insert_at = i + 1
            if insert_at < len(lines) and lines[insert_at].startswith("Project:"):
                insert_at += 1
            break

    new_lines = lines[:insert_at] + ["", banner] + lines[insert_at:]
    new_text = _BLANK_RUN_RE.sub("\n\n", "\n".join(new_lines))
    if text.endswith("\n") and not new_text.endswith("\n"):
        new_text += "\n"

    if new_text == text:
        return {"stamped": False, "reason": "unchanged"}
    try:
        path.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        return {"stamped": False, "reason": f"write_error: {exc}"}
    return {"stamped": True, "audit_generated": audit_ts or None}


__all__ = ["mark_audit_report_stale", "AUDIT_REPORT_REL"]
