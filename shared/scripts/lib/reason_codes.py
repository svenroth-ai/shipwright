"""The closed reason-code vocabulary, one set per check family.

A gate that lets the agent explain itself in free text has no gate: "skipped"
is how an unreviewed change is laundered into a passing run. Wherever a check
accepts an exemption, a ``not_run`` or an ``untestable`` answer, the answer
must be a *code* from the family that check owns, so a verifier can refuse
anything else and a report can count it.

One module, importable by every verifier and by ``record_review_pass.py``
(both sit under ``shared/scripts``), so a family has exactly one definition.
Adding a code is a one-line diff here plus its documentation; adding a family
is one more key. The sets are frozen: nothing mutates the vocabulary at run
time.

Families
--------
``untestable``     structural reasons a behaviour cannot be tested; mirrored in
                   ``references/confidence-anti-patterns.md`` (reverse-drift
                   test: ``shared/tests/test_untestable_vocab_doc_sync.py``).
``review_not_run`` why a review pass closed ``not_run`` / ``not_applicable``.
``test_exemption`` why a newly added test carries no requirement tag.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

__all__ = ["EXEMPTION_FAMILIES", "REASON_CODES", "TRIVIAL_AUTO", "family_codes", "reason_code_error"]

REASON_CODES: Mapping[str, frozenset[str]] = MappingProxyType({
    "untestable": frozenset({
        "requires-prod-credential",                    # real prod secret absent from CI
        "requires-external-nondeterministic-service",  # live 3rd-party, non-deterministic output
        "requires-physical-device",                    # hardware/peripheral not in CI
        "requires-manual-visual-judgment",             # human visual/aesthetic call
        "requires-interactive-tty",                    # interactive terminal/login the harness can't drive
        "covered-by-existing-test",                    # already pinned by a named pre-existing test
    }),
    "review_not_run": frozenset({
        "unavailable",                 # the reviewer could not run (adapter error captured)
        "trivial-auto",                # trivial complexity: closed with the one default row
        "delegated-to-orchestrator",   # a campaign runner has no Agent tool; 3f-bis runs it
        "diff-below-threshold",        # no risk flag and the diff is under the size trigger
        "complexity-below-threshold",  # complexity below the pass's trigger
        "user-opt-out",                # the operator declined the pass
        "config-disabled",             # external_review.feedback_iterations is 0
        "missing-keys",                # no provider key configured
        "no-spawn-site",               # nothing in this context can spawn the pass (campaign internal arms)
    }),
    "test_exemption": frozenset({
        "fixture-or-helper",    # a function the collector does not collect as a test
        "mechanical-refactor",  # body diff limited to renamed identifiers
    }),
})

#: The ONE default a trivial run closes every pass it did not run with (and its ledger).
TRIVIAL_AUTO = "trivial-auto"

#: Families whose answers are EXEMPTIONS (recorded in the F5c `exemptions` block). A review
#: closed not_run and an untestable behaviour are answers, not exemptions.
EXEMPTION_FAMILIES: frozenset[str] = frozenset({"test_exemption"})


def family_codes(family: str) -> frozenset[str]:
    """The closed set for ``family``; ``KeyError`` for an unknown family."""
    return REASON_CODES[family]


def reason_code_error(family: str, code: object, *, where: str = "reason_code") -> str | None:
    """``None`` when ``code`` is in ``family``'s vocabulary, else why not."""
    if family not in REASON_CODES:
        return f"{where}: unknown reason-code family {family!r} (known: {sorted(REASON_CODES)})"
    if not isinstance(code, str) or code not in REASON_CODES[family]:
        return f"{where} {code!r} is not in the closed {family} vocabulary {sorted(REASON_CODES[family])}"
    return None
