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

from lib.architecture_doc import (  # noqa: E402
    arch_impact_records,
    missing_entries,
    records_in_run_set,
    scan_drops,
)
from lib.events_log import finalized_run_ids, resolve_main_repo_root  # noqa: E402


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


def _conv_md_text() -> str:
    return (_project_root() / ".shipwright" / "agent_docs" / "conventions.md").read_text(
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


def _discovery_sanity(drops_dir: Path) -> tuple[str, str]:
    """Classify the decision-drops discovery state for the sanity gate.

    Returns ``(disposition, reason)`` where ``disposition`` is:

    - ``"skip"`` — the dir is ABSENT (clean checkout / CI runner — drops are
      gitignored) OR present but holds ZERO drop files (all aggregated into
      ADRs + cleared at the last ``/shipwright-changelog`` release — a
      legitimate post-release dev state, NOT a resolution misfire).
    - ``"ok"`` — the dir holds ≥1 drop file, so the resolver found real content
      and discovery works. The arch-impact SUBSET may legitimately be empty and
      is deliberately NOT required (that was the old, born-fragile assertion
      that false-FAILed every post-release dev tree).
    """
    if not drops_dir.is_dir():
        return ("skip", f"decision-drops/ absent under {drops_dir} — clean "
                        "checkout (drops are gitignored); nothing to sanity-check")
    all_drops = sorted(drops_dir.glob("*.json"))
    if not all_drops:
        return ("skip", f"decision-drops/ present but empty under {drops_dir} — "
                        "drops are aggregated into ADRs + cleared at each "
                        "release, so a post-release dev tree legitimately has "
                        "none; the arch-impact subset being empty is NOT a misfire")
    return ("ok", f"resolver found {len(all_drops)} drop file(s) under {drops_dir}")


def test_every_arch_impact_drop_has_architecture_md_entry():
    """For every decision-drop that flagged an architecture-impact, the run_id
    must appear in its TARGET doc — routed via the shared oracle
    (``lib.architecture_doc.IMPACT_TARGETS``): ``convention`` →
    ``conventions.md ## Convention Updates``; ``component`` / ``data-flow`` →
    ``architecture.md ## Architecture Updates`` (convention keeps a transitional
    fallback to architecture.md for the un-migrated backlog). Without this, an
    iterate can pass the F3 architecture-impact flag without documenting the
    state change — silent drift. Delegating to the oracle keeps this test, the
    F11 gate, and the Group-F detective from diverging.

    Event-ownership scoped: only drops whose ``run_id`` is in this tree's
    committed ``shipwright_events.jsonl`` are checked (``finalized_run_ids``).
    A cross-branch campaign sibling's drop accumulates in the shared main-rooted
    ``decision-drops`` dir, but its target-doc entry lives only on the sibling's
    own unmerged branch — without scoping it reads as drift on every other
    branch. Fail-open: with no event log (ownership unknowable, e.g. a CI runner)
    the whole set is checked, never weaker than before."""
    drops_dir = _main_repo_root() / ".shipwright" / "agent_docs" / "decision-drops"
    records, _corrupt = scan_drops(drops_dir)

    owned = finalized_run_ids(_project_root())
    if owned is not None:
        records = records_in_run_set(records, owned)

    if not arch_impact_records(records):
        pytest.skip("no owned architecture-impact decision-drops to verify")

    texts = {"architecture.md": _arch_md_text(), "conventions.md": _conv_md_text()}
    missing = missing_entries(records, texts)
    if missing:
        lines = ["target doc does not mention the following arch-impact drops:"]
        for r in missing:
            lines.append(f"  - {r.drop_file} run_id={r.run_id} impact={r.impact}")
        lines.append(
            "Add a one-line bullet naming the run_id under the impact's target "
            "section (convention → conventions.md '## Convention Updates'; "
            "component/data-flow → architecture.md '## Architecture Updates'). "
            "Routing SSoT: lib.architecture_doc.IMPACT_TARGETS."
        )
        pytest.fail("\n".join(lines))


def test_arch_impact_drops_found_at_all():
    """Sanity check — the discovery path resolves the REAL decision-drops dir.

    Guards the main assertion from silently no-opping when ``_main_repo_root()``
    misfires and the dir comes back empty. Two non-misfire states are SKIPPED
    (not failed): the dir absent (clean checkout / CI — drops are gitignored)
    and the dir present-but-empty (all drops aggregated into ADRs + cleared at
    the last ``/shipwright-changelog`` release). Classification lives in
    ``_discovery_sanity`` so it's unit-tested hermetically below.

    Earlier this asserted the arch-impact SUBSET was non-empty, which false-
    FAILed every post-release dev tree (dir present, only non-arch drops left):
    iterate-2026-05-31-ci-shared-tests skip + iterate-2026-06-07-finalization-
    tooling-hardening robustness fix."""
    drops_dir = _main_repo_root() / ".shipwright" / "agent_docs" / "decision-drops"
    disposition, _reason = _discovery_sanity(drops_dir)
    if disposition == "skip":
        pytest.skip(_reason)
    # 'ok' → the resolver found real drop file(s), so discovery works. The
    # arch-impact SUBSET may legitimately be empty (post-release, or simply no
    # recent iterate declared a component/data-flow/convention impact) — assert
    # the subset invariant, NOT that it is non-empty (the old, born-fragile
    # claim that false-FAILed every post-release dev tree).
    arch_drops = _arch_impact_drops()
    all_drops = sorted(drops_dir.glob("*.json"))
    assert len(arch_drops) <= len(all_drops)


# --- hermetic unit tests for the discovery-sanity classifier ----------------

def test_discovery_sanity_skips_when_dir_absent(tmp_path):
    assert _discovery_sanity(tmp_path / "nope")[0] == "skip"


def test_discovery_sanity_skips_when_present_but_empty(tmp_path):
    # All drops aggregated into ADRs + cleared at the last release — a
    # legitimate post-release dev state, not a resolution misfire.
    d = tmp_path / "decision-drops"
    d.mkdir()
    assert _discovery_sanity(d)[0] == "skip"


def test_discovery_sanity_ok_when_present_with_nonarch_drop(tmp_path):
    # THE regression: dir present holding only a non-arch-impact drop
    # (architecture_impact=none). This used to FALSELY FAIL the sanity gate;
    # discovery clearly works (a file was found), so it must be 'ok'.
    d = tmp_path / "decision-drops"
    d.mkdir()
    (d / "drop1.json").write_text(
        json.dumps({"run_id": "r", "architecture_impact": "none"}),
        encoding="utf-8",
    )
    assert _discovery_sanity(d)[0] == "ok"
