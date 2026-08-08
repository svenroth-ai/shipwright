"""ADVISORY model-tier floor note — split from :mod:`review_record_floor`.

Same seam that module was itself split from :mod:`review_record_check` on:
this is a genuinely separate question ("did the tier meet an operator's bar")
from the substance predicates next door ("did a review happen at all"), and
keeping it apart keeps both files under the repo's 300-line source cap.

Unlike every predicate in ``review_record_floor``, this one never returns a
:class:`CheckResult` — only a string appended to the PASSING result (the
same shape as ``substitution_note``). A model-tier floor is a complement, not
a gate: the BRIEF this feature implements is explicit the floor "takes no
freedom from anyone", and a verifier able to fail a run over another team's
cost/tier choice would take exactly the freedom the BRIEF's REJECTED section
already ruled out taking via frontmatter pins.
"""

from __future__ import annotations

from pathlib import Path

from lib.model_tier_config import RANK, load_model_config  # noqa: E402
from lib.review_record_core import entry_for  # noqa: E402

#: The internal-cascade types a `review`-role floor can meaningfully judge.
#: `external_code` is excluded — it is a non-Claude LLM call, not an
#: Agent-tool spawn, so it carries no `model_tier` in the same sense.
_REVIEW_ROLE_TYPES = ("spec", "code", "doubt")


def model_tier_note(record: dict, project_root: Path) -> str:
    """ADVISORY note for a review-role pass below a configured floor.

    Converts the BRIEF's "silent downgrade" into a loud one, opt-in: with no
    ``floors.review`` configured in ``shipwright_model_config.json`` this is a
    silent no-op.

    Four outcomes per completed internal-cascade row (`spec`/`code`/`doubt`):

    * ``model_tier`` absent (key never written) — FLAGGED, distinctly, as
      "no recorded tier". `check_review_record` reads exactly one record —
      the run currently being finalized — never a historical one, so this is
      never "an old record from before the field existed" in practice; it is
      this run's own pass, this run's own operator-configured floor, and a
      forgotten ``--model-tier`` flag. Staying silent here would make the
      floor's central case evadable by omitting one unenforced flag, which
      defeats the loud-not-blocking complement the floor exists to be.
    * ``model_tier`` present but not a string — SILENT. Can only happen via a
      hand-edited or pre-fix legacy file (the schema now type-checks this
      field at write time); there is nothing honest to say about a value that
      cannot be trusted into a message.
    * ``model_tier == "inherit"`` — flagged. This is the exact case the BRIEF
      exists for: the pass explicitly deferred to the session's tier, so
      whether it met the floor is genuinely unknown, and that not-knowing is
      what should be loud once an operator has said they care.
    * a ranked tier below the floor — flagged with both values named.
    """
    floor = (load_model_config(project_root).get("floors") or {}).get("review")
    if not floor:
        return ""
    floor_rank = RANK[floor]

    flagged: list[str] = []
    for review_type in _REVIEW_ROLE_TYPES:
        entry = entry_for(record, review_type)
        if str(entry.get("status", "")) != "completed":
            continue
        tier = entry.get("model_tier")
        if tier is None:
            flagged.append(f"{review_type} has no recorded tier (floor {floor} not confirmed)")
            continue
        if not isinstance(tier, str):
            continue  # malformed (pre-fix/hand-edited record) — never trusted into a comparison
        if tier == "inherit":
            flagged.append(f"{review_type} ran under session-inherit (tier not confirmed)")
        elif tier not in RANK:
            flagged.append(f"{review_type} ran on an unrecognized tier (floor {floor} not confirmed)")
        elif RANK[tier] < floor_rank:
            flagged.append(f"{review_type} ran on {tier} (below configured floor {floor})")

    if not flagged:
        return ""
    return f" — NOTE: model-tier floor 'review: {floor}' not confirmed for: " + "; ".join(flagged)
