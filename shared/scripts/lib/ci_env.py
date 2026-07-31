"""Is this process running in CI? The one answer, in one place.

A NEUTRAL LEAF, deliberately — same rationale as :mod:`lib.sweep_text` and
:mod:`lib.jsonl_records`. The predicate had FOUR byte-identical copies
(``gitattributes_selfheal``, ``gitignore_selfheal``, ``reconcile_triage``,
``sweep_outbox``), and the triage routing decision needed a fifth. Four copies of
three lines is cheap; four copies that must agree about *which environments count
as CI* is a correctness question, because they gate whether an automatic commit
fires. (The audit that found this counted three — it was four.)

**Stdlib only, and it must stay that way.** ``triage.py`` reaches shared lib modules
through ``shared_lib_loader.load_shared_lib``, whose by-file-location fallback is
documented as *"only safe for lib modules with no intra-package imports"*. A
``from lib.sibling import …`` here would break that fallback in exactly the ADR-045
collision it exists to survive.
"""

from __future__ import annotations

import os

__all__ = ["CI_TRUTHY", "ci_active"]

#: Truthy spellings of ``$CI``. GitHub Actions sets ``CI=true``; the others are the
#: spellings other runners use. Compared case-insensitively after stripping.
CI_TRUTHY = frozenset({"1", "true", "yes", "on"})


def ci_active() -> bool:
    """True when ``$CI`` is set to a truthy value.

    Two distinct consumers, worth stating together because they pull in opposite
    directions and both are correct:

    * The self-heal / reconcile / sweep paths use it to NOT auto-commit under CI
      unless explicitly opted in — a build agent must not push commits nobody asked
      for.
    * ``triage.should_route_to_outbox`` uses it to route a finding to the TRACKED
      store rather than the outbox (``trg-6af8dc72``). A GitHub runner satisfies
      both of that function's other conditions — the checkout has an ``origin``, and
      a push or scheduled build sits ON the default branch — so a card filed from CI
      landed in the gitignored outbox and died with the runner's filesystem. The
      tracked log is at least a file a job can commit and ``git status`` can show;
      the outbox can reach nobody by construction. This was not merely latent: the
      derived-snapshot refresh's failure-card path was wholly inert this way, and
      passed its tests only because their fixtures have no ``origin``.

      It makes the card *committable*, which is not the same as *delivered* — a CI
      job that never commits still discards it. That is the honest limit of this
      fix; closing it means a job that commits or uploads the log.
    """
    return os.environ.get("CI", "").strip().lower() in CI_TRUTHY
