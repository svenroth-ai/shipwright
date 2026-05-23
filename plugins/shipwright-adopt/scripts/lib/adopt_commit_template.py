"""Adopt Step H commit message builder.

Builds the conventional commit message for the brownfield-onboarding
commit created by ``/shipwright-adopt`` Step H. Iterate-2026-05-23
introduces a ``Run-ID: adopt-<YYYY-MM-DD>-<repo-name>`` trailer so the
snapshot-provenance audit (``audit_staleness.find_snapshot_commit``)
recognizes the adopt commit as a valid compliance baseline.

Pure-function — no filesystem I/O beyond reading the project_root path
to derive the repo name. Date is injected via a small seam
(``_utc_today``) so tests can pin it.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path


_REPO_SAN_RE = re.compile(r"[^a-z0-9]+")


def _utc_today() -> datetime:
    """Return today's UTC ``datetime``. Test seam — patch in tests for
    deterministic output."""
    return datetime.now(timezone.utc)


def _sanitize_repo_name(project_root: Path) -> str:
    """Derive a kebab-case, ASCII-safe repo name from ``project_root``.

    Lowercases, replaces any non-``[a-z0-9]`` run with ``-``, trims
    leading/trailing hyphens. Returns ``"repo"`` as a fallback when
    sanitization wipes the string (pathological inputs like ``/tmp/!!!``).
    """
    raw = project_root.name.lower()
    safe = _REPO_SAN_RE.sub("-", raw).strip("-")
    return safe or "repo"


def _build_run_id(project_root: Path) -> str:
    """Compose ``adopt-<YYYY-MM-DD>-<repo>`` for the commit trailer."""
    today = _utc_today().strftime("%Y-%m-%d")
    repo = _sanitize_repo_name(project_root)
    return f"adopt-{today}-{repo}"


def build_adopt_commit_message(
    *,
    project_root: Path,
    profile: str,
    scope: str,
    inferred_fr_count: int,
) -> str:
    """Return the full commit message Step H should pass to ``git commit -m``.

    Args:
        project_root: Adopted repo root — used to derive the repo segment
            of the ``Run-ID:`` trailer.
        profile: Matched stack profile (e.g., ``python-cli``).
        scope: Adoption scope (e.g., ``full_app``, ``library``, ``cli``).
        inferred_fr_count: Number of FRs the adopt enrichment inferred
            from the existing codebase.

    Returns:
        Multi-line conventional-commit string ending with the
        ``Run-ID: adopt-<date>-<repo>`` trailer (no trailing newline —
        ``git commit -m`` adds its own).
    """
    run_id = _build_run_id(project_root)
    return (
        "chore(shipwright): adopt repository into Shipwright SDLC\n"
        "\n"
        f"Adopted via /shipwright-adopt using profile={profile}, scope={scope}.\n"
        f"Inferred {inferred_fr_count} functional requirements from existing codebase.\n"
        "Seeded compliance artifacts (SBOM, change-history, RTM skeleton).\n"
        "Test evidence starts collecting from next /shipwright-test run.\n"
        "\n"
        "See .shipwright/agent_docs/decision_log.md for the adoption ADR\n"
        "(id is `max(existing) + 1`, 3-digit zero-padded — ADR-001 on greenfield).\n"
        "\n"
        f"Run-ID: {run_id}"
    )
