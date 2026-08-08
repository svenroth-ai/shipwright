"""Drift protection for the GC vocabulary — ``triage_gc.MACHINE_REASONS``.

Split out of ``test_triage_wp9_gc.py`` (which was at the 300-line guideline) when
the vocabulary itself moved from ``tools/triage_gc.py`` to ``lib/triage_gc_core.py``
and the source scan's filename-based self-exclusion stopped covering it — the
definition then counted as a live emitter and the legacy-orphan guard failed. That
is the exact drift these tests exist to catch, one level up, so they get their own
module rather than another round of comment-shaving.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent / "scripts" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import triage_gc  # noqa: E402


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
    "f05Resolved",    # F0.5 triage producer removed (iterate-2026-06-13-triage-not-current-work); historical/buffered f0.5 dismissals stay GC-able
})


def _emitted_recurring_dismiss_tokens() -> set[str]:
    """Source-derived producer recurring auto-resolve tokens.

    Scans every producer ``*.py`` under ``shared/`` and ``plugins/`` for
    ``*Resolved``/``*Refreshed`` STRING-LITERAL reasons, excluding the test trees
    (any ``tests/`` directory) and the module that DEFINES ``MACHINE_REASONS`` —
    resolved from the module object, NOT spelled as a filename, because the
    vocabulary moved to ``lib/triage_gc_core.py`` and a name-based exclusion then
    let the definition count itself as a live emitter. Adding a token in a producer
    auto-updates this expectation — no hand edit.

    Exclusion is DIRECTORY-based (``tests`` path component), NOT filename-prefix:
    several producer modules are legitimately named ``test_*`` (e.g. the
    compliance ``test_evidence.py`` producer that emits ``testEvidenceResolved``,
    ``test_runner.py``, ``test_hygiene.py``) and must be scanned. Real pytest
    files all live under a ``tests/`` directory in this repo.

    A file must also MENTION triage to be a producer
    (iterate-2026-07-27-name-the-blocker): ``lib/pr_blockers.py`` reads GitHub's
    ``isResolved`` field while touching no triage, yet matched — and would have
    put a GitHub field name into the GC vocabulary. Narrowed to the guard's own
    subject, checked not assumed (all eight token-bearing producers name triage,
    the non-producer did not); the anchor test below fails loudly if this ever
    hides a real producer.
    """
    # The module that DEFINES MACHINE_REASONS/is_machine_churn (resolved via
    # is_machine_churn.__module__, not triage_gc.plan_gc.__module__ — the two
    # split apart in iterate-2026-08-08-triage-amend-event when the policy
    # vocabulary moved to lib/triage_gc_policy.py but plan_gc stayed in
    # lib/triage_gc_core.py), the engine module (plan_gc's home), and the CLI
    # that re-exports both — all resolved, so a future move relocates the
    # exclusion with it rather than needing a hand edit here.
    vocab_defining = {
        Path(sys.modules[triage_gc.is_machine_churn.__module__].__file__).resolve(),
        Path(sys.modules[triage_gc.plan_gc.__module__].__file__).resolve(),
        Path(triage_gc.__file__).resolve(),
    }
    tokens: set[str] = set()
    for root_name in ("shared", "plugins"):
        root = _REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for py in root.rglob("*.py"):
            if "tests" in py.parts or py.resolve() in vocab_defining:
                continue
            text = py.read_text(encoding="utf-8", errors="replace")
            if "triage" not in text.lower():
                continue
            tokens.update(_TOKEN_RE.findall(text))
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
