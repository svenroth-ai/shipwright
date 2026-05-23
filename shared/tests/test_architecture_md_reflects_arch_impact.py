"""Drift-protection: architecture.md mentions every iterate that flagged
``architecture-impact`` in its decision-drop.

This test catches the failure mode that surfaced in iterate-2026-05-23-
verifier-drift-remediation: an iterate passes ``--architecture-impact
convention`` (or ``component`` / ``data-flow``) to ``write_decision_drop.py``
but never actually adds a corresponding entry to
``.shipwright/agent_docs/architecture.md``. SKILL.md F2 prescribes BOTH —
update architecture.md AND flag the drop — and the drop alone with no
markdown trace is silent drift.

Worktree-aware: decision-drops live in the main repo (gitignored), so the
test resolves the main-repo root via ``events_log.resolve_main_repo_root``
to enumerate the drops, then reads ``architecture.md`` from the test's
own project root (which is the same in both worktree and main-repo runs
because architecture.md is tracked).

Test pinned via simple substring match on the run-id (or the eventual
ADR-NNN, when the drop has been aggregated). This is intentionally lax —
the convention is "the run_id appears anywhere in architecture.md",
typically under the ``## Architecture Updates`` bulleted list. Stricter
section-anchoring is left to a follow-up if drift recurs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))

from lib.events_log import resolve_main_repo_root  # noqa: E402


def _project_root() -> Path:
    """The shipwright dev repo root. From CI / worktree / main-repo runs,
    architecture.md and decision-drops both live under the main repo —
    architecture.md is tracked (visible in worktree), decision-drops are
    gitignored (only in main)."""
    here = Path(__file__).resolve()
    # shared/tests/test_X.py → walk up to repo root (= 2 levels above shared/)
    return here.parents[2]


def _main_repo_root() -> Path:
    pr = _project_root()
    resolved = resolve_main_repo_root(pr)
    return resolved if resolved is not None else pr


def _arch_md_text() -> str:
    return (_project_root() / ".shipwright" / "agent_docs" / "architecture.md").read_text(
        encoding="utf-8", errors="ignore"
    )


_REAL_IMPACTS = frozenset({"component", "data-flow", "convention"})


def _arch_impact_drops() -> list[dict]:
    """Enumerate decision-drops that declared a real architecture-impact.

    ``write_decision_drop.py`` defaults ``architecture_impact = "none"`` for
    every drop, even when no ``--architecture-impact`` flag was passed.
    Only ``component`` / ``data-flow`` / ``convention`` represent an actual
    architectural change requiring an architecture.md entry; ``none`` is
    the no-op default and is filtered out here."""
    drops_dir = _main_repo_root() / ".shipwright" / "agent_docs" / "decision-drops"
    if not drops_dir.is_dir():
        return []
    out: list[dict] = []
    for fp in sorted(drops_dir.glob("*.json")):
        try:
            payload = json.loads(fp.read_text(encoding="utf-8", errors="ignore"))
        except json.JSONDecodeError:
            continue
        impact_raw = (payload.get("architecture_impact") or payload.get("architectureImpact") or "")
        impact = impact_raw.strip().lower() if isinstance(impact_raw, str) else ""
        if impact not in _REAL_IMPACTS:
            continue
        out.append({
            "run_id": payload.get("run_id") or payload.get("runId") or "",
            "impact": impact,
            "drop_file": fp.name,
        })
    return out


def test_every_arch_impact_drop_has_architecture_md_entry():
    """For every decision-drop that flagged an architecture-impact, the
    run_id must appear in architecture.md. Without this, an iterate can
    pass the F3 architecture-impact flag without actually documenting the
    state change — silent drift."""
    drops = _arch_impact_drops()
    if not drops:
        pytest.skip("no architecture-impact decision-drops to verify")

    arch = _arch_md_text()
    missing: list[dict] = []
    for d in drops:
        run_id = d["run_id"]
        if not run_id:
            continue
        if run_id in arch:
            continue
        missing.append(d)

    if missing:
        lines = ["architecture.md does not mention the following arch-impact drops:"]
        for m in missing:
            lines.append(f"  - {m['drop_file']} run_id={m['run_id']} impact={m['impact']}")
        lines.append(
            "Add a bullet under '## Architecture Updates' in "
            ".shipwright/agent_docs/architecture.md naming the run_id and the "
            "convention/component/data-flow that changed."
        )
        pytest.fail("\n".join(lines))


def test_arch_impact_drops_found_at_all():
    """Sanity check — the discovery path actually finds drops in the repo.
    Without this, the main assertion silently no-ops on a repo where the
    main-repo resolution misfires and the decision-drops dir comes back
    empty."""
    drops = _arch_impact_drops()
    # The repo has carried multiple arch-impact decision-drops since
    # iterate-2026-05-03; an empty list means we're looking at the wrong
    # directory or the resolution helper is broken.
    assert drops, (
        f"no arch-impact drops discovered under "
        f"{_main_repo_root() / '.shipwright/agent_docs/decision-drops'} — "
        "main-repo resolution may be broken"
    )
