"""WP9 (2026-06-10 deep audit) — triage_gc hardening: F30 + F19.

F30: ``triage_gc.MACHINE_REASONS`` was missing ``phaseQualityRefreshed`` (the
phase-quality ``_triage_bundle`` emits it on every signature change) → that
per-run dismissal churn was never GC'd. Same decoupled-SSoT miss the
``complianceRefreshed`` fix already closed. Includes a registry-driven
forward+reverse-drift meta-test so the SSoT can't silently drift again.

F19: the GC plan was computed OUTSIDE the lock; ``apply_gc`` dropped every line
for a planned id — including a status flip appended between plan and apply
(TOCTOU → lost operator decision). ``apply_gc`` now recomputes under the lock
and intersects with the caller's plan.

Lives in its own module (separate from ``test_triage_gc.py``) to keep both
files under the bloat LOC guideline — these are new WP9 cases, not edits to the
grandfathered suite.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent / "scripts" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import triage  # noqa: E402
import triage_gc  # noqa: E402


def _add(root: Path, *, title: str, dedup: str) -> str:
    return triage.append_triage_item(
        root, source="sbom", severity="low", kind="compliance",
        title=title, detail="d", dedup_key=dedup,
    )


def _dismiss(root: Path, item_id: str, *, by: str, reason: str) -> None:
    triage.mark_status(root, item_id, new_status="dismissed", by=by, reason=reason)


# --------------------------------------------------------------------------
# F30 — phaseQualityRefreshed is machine-churn and must be GC-able
# --------------------------------------------------------------------------

def test_phasequality_refreshed_machine_churn_dropped(tmp_path: Path):
    """The phaseQuality producer emits BOTH ``phaseQualityResolved`` (all fails
    cleared) AND ``phaseQualityRefreshed`` (stale-signature rollup superseded by
    a fresh signature — ``phase_quality/_triage_bundle`` ~L268). Identical
    decoupled-SSoT miss to the ``complianceRefreshed`` fix: the refresh token was
    absent from MACHINE_REASONS, so this pure machine-churn accumulated as kept
    noise."""
    resolved = _add(tmp_path, title="resolved", dedup="kpr")
    _dismiss(tmp_path, resolved, by="phaseQualityBacklog", reason="phaseQualityResolved")
    refreshed = _add(tmp_path, title="refreshed", dedup="kpf")
    _dismiss(tmp_path, refreshed, by="phaseQualityBacklog", reason="phaseQualityRefreshed")
    human = _add(tmp_path, title="h", dedup="khp")
    _dismiss(tmp_path, human, by="user", reason="phaseQualityRefreshed")  # human → kept
    assert triage_gc.plan_gc(tmp_path)["drop_ids"] == {resolved, refreshed}


# --------------------------------------------------------------------------
# Forward+reverse-drift meta-test — SOURCE-DERIVED SSoT (no hand-copied list)
# --------------------------------------------------------------------------
#
# The producer recurring auto-resolve vocabulary is the ``*Resolved``/
# ``*Refreshed`` dismissal-reason literals each background producer emits. We
# DERIVE it from producer source instead of hand-copying: a hand-copied list
# silently drifts — the previous one had become a tautology equal to
# MACHINE_REASONS, hiding BOTH a missing token (``prChecksResolved``, emitted by
# github_triage's PR-CI resolver but absent from MACHINE_REASONS) AND an orphan
# token (``auditResolved``, in MACHINE_REASONS with no live emitter).
#
# Scope: only the RECURRING ``*Resolved``/``*Refreshed`` family is the GC
# vocabulary. Terminal/one-shot lifecycle markers deliberately NOT named
# ``*Resolved`` — github_triage's ``prMerged``/``prClosed`` (once per PR) and
# ``schemaMigration`` (one-shot legacy migration), compliance's
# ``supersededByBacklog`` — are real audit history, not churn, and are correctly
# outside this set (the scan never sees them; MACHINE_REASONS never carries them).

_REPO_ROOT = Path(__file__).resolve().parents[2]  # shared/tests/<f>.py → repo root
_TOKEN_RE = re.compile(r"""['"]([a-z][A-Za-z0-9]*(?:Resolved|Refreshed))['"]""")

# Tokens deliberately retained in MACHINE_REASONS though NO producer emits them
# today — GC must still collapse any historical/buffered dismissal carrying them
# (removing one would silently NARROW GC). Each entry is an EXPLICIT, documented
# legacy retention.
LEGACY_RETAINED_TOKENS = frozenset({
    "auditResolved",  # audit now routes through complianceBacklog; pre-bundle / outbox-buffered dismissals stay GC-able
})


def _emitted_recurring_dismiss_tokens() -> set[str]:
    """Source-derived producer recurring auto-resolve tokens.

    Scans every producer ``*.py`` under ``shared/`` and ``plugins/`` for
    ``*Resolved``/``*Refreshed`` STRING-LITERAL reasons, excluding the test trees
    (any ``tests/`` directory) and ``triage_gc.py`` itself (the consumer that
    defines MACHINE_REASONS). Adding a token in a producer auto-updates this
    expectation — no hand edit.

    Exclusion is DIRECTORY-based (``tests`` path component), NOT filename-prefix:
    several producer modules are legitimately named ``test_*`` (e.g. the
    compliance ``test_evidence.py`` producer that emits ``testEvidenceResolved``,
    ``test_runner.py``, ``test_hygiene.py``) and must be scanned. Real pytest
    files all live under a ``tests/`` directory in this repo.
    """
    tokens: set[str] = set()
    for root_name in ("shared", "plugins"):
        root = _REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for py in root.rglob("*.py"):
            if "tests" in py.parts or py.name == "triage_gc.py":
                continue
            tokens.update(_TOKEN_RE.findall(py.read_text(encoding="utf-8", errors="replace")))
    return tokens


def test_source_derivation_finds_known_anchor_tokens():
    """Vacuous-green guard: if the scan resolves the wrong root or reads nothing,
    the drift guards below would pass trivially on an empty set. Pin a few
    always-present producer tokens so a broken scan fails LOUDLY here instead."""
    emitted = _emitted_recurring_dismiss_tokens()
    for anchor in ("sbomResolved", "driftResolved", "complianceResolved", "prChecksResolved"):
        assert anchor in emitted, (
            f"source scan did not find {anchor!r} — derivation broken "
            f"(found {len(emitted)} tokens); the drift guards below would be vacuous"
        )


def test_machine_reasons_covers_every_producer_recurring_token():
    """Forward-drift guard: every recurring producer auto-resolve token IN SOURCE
    MUST be in MACHINE_REASONS, else that producer's per-run churn is never GC'd
    (the F30 / complianceRefreshed / prChecksResolved failure mode)."""
    missing = _emitted_recurring_dismiss_tokens() - triage_gc.MACHINE_REASONS
    assert not missing, (
        f"producer recurring dismiss tokens not in MACHINE_REASONS: {sorted(missing)} "
        "— add them or the per-run churn accumulates unbounded in tracked history"
    )


def test_machine_reasons_has_no_unknown_tokens():
    """Reverse-drift guard (source-derived): MACHINE_REASONS must not carry a
    token no producer emits AND not on the explicit legacy allowlist (a stale
    token GC's nothing and hides drift in the other direction)."""
    unknown = (
        triage_gc.MACHINE_REASONS
        - _emitted_recurring_dismiss_tokens()
        - LEGACY_RETAINED_TOKENS
    )
    assert not unknown, (
        f"MACHINE_REASONS carries tokens no producer emits: {sorted(unknown)} "
        "— remove them, fix the emitter, or add a documented LEGACY_RETAINED_TOKENS entry"
    )


def test_legacy_retained_tokens_have_no_live_emitter():
    """A legacy-allowlist entry must be a genuine orphan: if it gains a live
    emitter it belongs to the derived set and the allowlist entry is stale noise
    that would mask future reverse-drift."""
    live = LEGACY_RETAINED_TOKENS & _emitted_recurring_dismiss_tokens()
    assert not live, (
        f"LEGACY_RETAINED_TOKENS entries that DO have a live emitter: {sorted(live)} "
        "— drop them from the allowlist; the source scan already covers them"
    )


def test_machine_reasons_pins_refresh_and_prchecks_tokens():
    """Pin the specific tokens a careless MACHINE_REASONS edit could silently
    drop: phaseQualityRefreshed (F30) and prChecksResolved (a1-6 follow-up)."""
    assert "phaseQualityRefreshed" in triage_gc.MACHINE_REASONS
    assert "prChecksResolved" in triage_gc.MACHINE_REASONS


def test_prchecks_resolved_github_dismissal_is_machine_churn(tmp_path: Path):
    """Behavioral: a github_triage PR-CI auto-dismiss (by=githubImporter,
    reason=prChecksResolved — a tracked PR's failing checks went green) is
    recurring machine-churn and must be GC-able. It was missing from
    MACHINE_REASONS; the hand-copied meta-test hid the gap. A human reusing the
    token is still kept (predicate needs BOTH a machine dismisser AND token)."""
    pr = _add(tmp_path, title="gh-pr-ci:42 checks failing", dedup="gh-pr-ci:42")
    _dismiss(tmp_path, pr, by="githubImporter", reason="prChecksResolved")
    human = _add(tmp_path, title="h", dedup="kh")
    _dismiss(tmp_path, human, by="user", reason="prChecksResolved")  # human → kept
    assert triage_gc.plan_gc(tmp_path)["drop_ids"] == {pr}


# --------------------------------------------------------------------------
# F19 — TOCTOU: a status flip appended between plan and apply must survive.
# --------------------------------------------------------------------------

def test_apply_recomputes_plan_under_lock_preserving_concurrent_reopen(tmp_path: Path):
    """A status flip appended BETWEEN plan and apply must survive ``apply_gc``.

    Repro: ``plan_gc`` marks item ``m`` droppable (machine-churn dismissed).
    Before ``apply_gc`` runs, the WebUI / a producer re-opens ``m`` (status →
    ``triage``). The stale ``drop_ids`` would delete every line for ``m`` —
    including the fresh re-open — wiping the operator decision. The fix
    recomputes under the lock, so a no-longer-machine-churn item is NOT dropped.
    """
    m = _add(tmp_path, title="m", dedup="k1")
    _dismiss(tmp_path, m, by="auditDetector", reason="auditResolved")
    keep_dropped = _add(tmp_path, title="still-churn", dedup="k2")
    _dismiss(tmp_path, keep_dropped, by="sbomGenerator", reason="sbomResolved")

    stale_plan = triage_gc.plan_gc(tmp_path)
    assert stale_plan["drop_ids"] == {m, keep_dropped}

    # CONCURRENT re-open of m between plan and apply (operator/WebUI decision).
    triage.mark_status(tmp_path, m, new_status="triage", by="user",
                       reason="re-opened: actually a real finding")

    triage_gc.apply_gc(tmp_path, stale_plan["drop_ids"])

    survivors = {i["id"]: i for i in triage.read_all_items(tmp_path)}
    assert m in survivors, "F19 TOCTOU: concurrent re-open was dropped by apply_gc"
    assert survivors[m]["status"] == "triage"
    assert keep_dropped not in survivors


def test_apply_does_not_drop_item_churned_after_the_consented_plan(tmp_path: Path):
    """Consent-surface guard: apply drops the INTERSECTION of the fresh plan and
    the caller's planned ids — never MORE than the dry-run report announced.

    An item that becomes machine-churn AFTER the operator saw the plan was never
    in the report they consented to, so apply must NOT silently drop it (it is
    GC'd on the NEXT run, when it appears in a fresh report)."""
    m = _add(tmp_path, title="m", dedup="k1")
    stale_plan = triage_gc.plan_gc(tmp_path)
    assert stale_plan["drop_ids"] == set()
    _dismiss(tmp_path, m, by="auditDetector", reason="auditResolved")
    triage_gc.apply_gc(tmp_path, stale_plan["drop_ids"])
    survivors = {i["id"] for i in triage.read_all_items(tmp_path)}
    assert m in survivors
    assert triage_gc.plan_gc(tmp_path)["drop_ids"] == {m}


# --------------------------------------------------------------------------
# F19 follow-up — the under-lock recompute is UNION-residence aware: a re-open
# routed to the gitignored OUTBOX (idle-main-with-origin) must also survive.
# --------------------------------------------------------------------------

def test_apply_honors_outbox_routed_reopen(tmp_path: Path, monkeypatch):
    """A concurrent re-open ROUTED TO THE OUTBOX must survive ``apply_gc``.

    a1-6/F19 recomputed the droppable set under the lock but read the TRACKED
    store only. On idle-main-with-origin a re-open routes (``mark_status`` →
    ``should_route_to_outbox``) to the gitignored outbox, invisible to a
    tracked-only recompute — so the item was still dropped and its outbox status
    orphaned (its tracked ``append`` gone → ``read_all_items`` skips the status
    as an unknown id). The recompute is now union-residence aware (tracked ∪
    outbox, last-status-wins), so the outbox re-open flips the item out of the
    effective drop set even though the tracked-only REPORT still lists it as
    droppable (the report stays an upper bound; the tracked file is still the
    only file rewritten).
    """
    m = _add(tmp_path, title="m", dedup="k1")
    _dismiss(tmp_path, m, by="auditDetector", reason="auditResolved")

    # Tracked-only report (what the operator consents to) still sees m droppable.
    stale_plan = triage_gc.plan_gc(tmp_path)
    assert stale_plan["drop_ids"] == {m}

    # CONCURRENT re-open ROUTED TO THE OUTBOX: force the derived write target so
    # mark_status appends the status to the gitignored outbox, exactly as it
    # would on idle main with a delivery path.
    monkeypatch.setattr(triage, "should_route_to_outbox", lambda *_a, **_k: True)
    triage.mark_status(tmp_path, m, new_status="triage", by="user",
                       reason="re-opened via webui on idle main")
    monkeypatch.undo()

    # Precondition: the re-open really landed in the outbox, not the tracked log.
    assert "re-opened via webui" in triage._outbox_path(tmp_path).read_text(encoding="utf-8")
    assert "re-opened via webui" not in triage._triage_path(tmp_path).read_text(encoding="utf-8")

    triage_gc.apply_gc(tmp_path, stale_plan["drop_ids"])

    # Union view shows m re-opened → NOT dropped; its tracked append remains
    # (no orphaned outbox status).
    survivors = {i["id"]: i for i in triage.read_all_items(tmp_path)}
    assert m in survivors, \
        "outbox-routed re-open was dropped by apply_gc (union-residence regression)"
    assert survivors[m]["status"] == "triage"
    assert m in triage._triage_path(tmp_path).read_text(encoding="utf-8"), \
        "tracked append for m was wrongly dropped"
