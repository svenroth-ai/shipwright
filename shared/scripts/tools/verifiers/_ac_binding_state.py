"""Shared AC-binding STATE reader for both P3.7 feeder checks (campaign
``req3-04c-ac-identity-wave2``, sub-iterate P3.7). Design:
``.shipwright/planning/iterate/2026-09-10-p3-7-feeder-checks.md``.

SPEC §8 E2 names two feeder checks, ASYMMETRIC BY DESIGN:

* **(a) "AC without a test"** — anti-ratcheted, because there IS a legacy
  backlog (P3.6 measured 259 of 268 minted ACs unbound). See
  ``check_ac_coverage_ratchet.py``.
* **(b) "a test whose AC vanished"** — HARD from day one, because there is
  no legacy backlog for THIS predicate: nothing has ever validated that a
  ``@covers`` tag's AC id still exists. See ``check_orphan_ac_binding.py``.

Both checks start from the SAME two facts about the current (HEAD) state —
which ACs are currently minted in the spec, and which ACs the regenerated
manifest currently records a binding for — so this module computes both
once, pure, over already-read text (the caller decides HOW to read each
spec path: a worktree disk read for the state-only checks, or a git-blob
read via ``spec_text_at`` for anything that also needs a base commit).

Reuses, never reimplements: ``lib.ac_identity.read_all`` (P3.1's minted-
criteria reader — the same one ``_keystone_ac_digest``/``_keystone_criteria``
use) and ``_keystone_links.links_for`` (P3.6's manifest link counter). No
second parser, no second link walk.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib import ac_identity  # noqa: E402

from ._keystone_base_manifest import ReadError  # noqa: E402  (re-exported: one import site)
from ._keystone_links import links_for  # noqa: E402


def active_requirements(manifest: dict) -> list[dict]:
    """Active requirement nodes only — same scope ``_keystone_links.links_for``
    already commits to (a retired FR's ACs are nobody's to bind or orphan)."""
    return [
        node for node in (manifest.get("requirements") or {}).values()
        if isinstance(node, dict) and node.get("status") == "active"
    ]


def spec_path_by_fr(manifest: dict) -> dict[str, str]:
    """Active display id -> its ``spec_path``, as the manifest names it."""
    out: dict[str, str] = {}
    for node in active_requirements(manifest):
        fr_id, spec_path = node.get("id"), node.get("spec_path")
        if isinstance(fr_id, str) and isinstance(spec_path, str) and spec_path:
            out[fr_id] = spec_path
    return out


@dataclass
class BindingState:
    minted: set[tuple[str, str]] = field(default_factory=set)   # every currently-minted AC
    #: minted AND the manifest carries >=1 link — TAG-DERIVED, never execution-derived
    #: (external plan review, glm, low): ``links_for`` returns every link the collector
    #: FILED for this AC regardless of that link's own ``status``/``executed`` value, so a
    #: test that is tagged but FAILED or was SKIPPED this run still counts as bound here.
    #: "Bound" answers "does a binding exist", not "did it pass" — greenness is P3.6's own
    #: gate's question, never this one's. Pinned by
    #: ``test_a_bound_ac_with_a_failed_or_skipped_link_is_still_bound_not_unbound``.
    bound: set[tuple[str, str]] = field(default_factory=set)
    unbound: set[tuple[str, str]] = field(default_factory=set)  # minted AND 0 manifest links
    #: A ``@covers`` tag the manifest currently binds under an AC id that is
    #: NOT in ``minted`` for that FR — "a test whose AC vanished" (arm 1 of
    #: the orphan-test detector, SPEC §8 E2(b)). Catches (ii) outright
    #: deletion and (iii) id rotation directly; see
    #: ``check_orphan_ac_binding.py``'s module docstring for why a SECOND,
    #: base-vs-head arm is needed for (i) the two-PR unbind sequence, which
    #: this state-only reader cannot see (nothing here changes across it).
    orphaned: set[tuple[str, str]] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)


def read_binding_state(spec_text_by_path: dict[str, str | None], manifest: dict) -> BindingState:
    """Pure. ``spec_text_by_path`` maps every ``spec_path_by_fr(manifest)``
    value to its text — the SAME three-way answer ``_layer_coverage_ac
    .spec_text_at`` already returns: ``str`` (real content), ``""`` (the path
    is genuinely ABSENT at this commit — a spec removed or renamed away), or
    ``None`` (the read itself failed: a real git/IO fault). Both callers
    (feeder a's worktree read, feeder b's ``spec_text_at`` read) map their own
    read failures the same way (external code review, openai, HIGH — an
    earlier version of this reader could not tell "genuinely absent" from
    "could not be read" apart and silently EXCLUDED both, which made the
    HARD, no-baseline orphan check fail OPEN on exactly the input it exists
    to catch: a spec file deleted at head still has stale bindings that
    SHOULD read as orphaned, not as "excluded, nothing to see").

    * ``""`` (genuinely absent) proceeds as ZERO minted criteria for that
      FR, with a WARNING — matching ``_keystone_ac_digest.ac_change_set``'s
      OWN precedent for a named ``spec_path`` that resolves to no content
      ("proceed with a trivially-empty change set AND a warning"). Any AC
      the manifest still binds under that FR correctly surfaces as
      ``orphaned`` (there are now zero minted ids to match against).
    * An active FR with NO ``spec_path`` recorded at all (``spec_path_by_fr``
      never enters it into ``spec_text_by_path``, so it has no read outcome
      to react to) is EXCLUDED entirely, with a WARNING — the opposite verdict
      from the ``""`` case above (which proceeds as zero minted criteria and
      so still catches an orphaned binding; this case catches nothing at all,
      for either feeder, because there is no criteria text to compare
      against). For a real producer this is currently unreachable (every
      manifest-generated FR sets ``spec_path``), but the reader does not
      assume that — it is "excluded, not misreported" the same way the other
      branches are, never a silent skip.
    * ``None`` (a genuine read fault) or untrustworthy markers
      (``ac_identity.AcIdentityError`` — malformed/duplicate) at this text
      RAISE :class:`ReadError` — matching P3.6's own HEAD-side treatment
      (``_keystone_criteria.ac_criteria_digests`` raises for the identical
      condition). Both this module's callers read ONLY head-equivalent text
      (feeder a's "right now", feeder b arm 1's head_sha) — there is no
      base-side leniency case here to be lenient about, unlike P3.6's own
      base/head asymmetry.
    """
    state = BindingState()
    fr_paths = spec_path_by_fr(manifest)
    minted_by_fr: dict[str, set[str]] = {}

    for fr_id, spec_path in fr_paths.items():
        text = spec_text_by_path.get(spec_path)
        if text is None:
            raise ReadError(f"{fr_id}: spec_path {spec_path!r} could not be read")
        if text == "":
            state.warnings.append(
                f"{fr_id}: spec_path {spec_path!r} resolved to no content; treated as zero "
                "minted criteria (proceed, not excluded) — any AC still bound under this FR "
                "correctly reads as orphaned."
            )
        try:
            items = ac_identity.read_all(text).get(fr_id, [])
        except ac_identity.AcIdentityError as exc:
            raise ReadError(
                f"{fr_id}: acceptance-criteria markers in {spec_path!r} are not trustworthy "
                f"({exc})"
            ) from exc
        ac_ids = {ac_id for ac_id, _criterion in items if ac_id is not None}
        minted_by_fr[fr_id] = ac_ids
        for ac_id in ac_ids:
            key = (fr_id, ac_id)
            state.minted.add(key)
            (state.bound if links_for(manifest, fr_id, ac_id) else state.unbound).add(key)

    for node in active_requirements(manifest):
        fr_id = node.get("id")
        if not isinstance(fr_id, str) or fr_id not in minted_by_fr:
            if isinstance(fr_id, str):
                acs = node.get("acs")
                binding_count = len(acs) if isinstance(acs, dict) else 0
                state.warnings.append(
                    f"{fr_id}: no spec_path recorded for this requirement in the manifest; "
                    f"excluded from this run entirely — its minted ACs are absent from "
                    f"'unbound' (feeder a) and its {binding_count} AC binding(s) are absent "
                    "from the orphan check (feeder b), never misreported as unbound/orphaned."
                )
            continue
        acs = node.get("acs")
        if not isinstance(acs, dict):
            continue
        for ac_id in acs:
            if not isinstance(ac_id, str) or ac_id in minted_by_fr[fr_id]:
                continue
            if links_for(manifest, fr_id, ac_id):  # count, never node presence — links_for's own convention
                state.orphaned.add((fr_id, ac_id))

    return state


__all__ = ["BindingState", "active_requirements", "read_binding_state", "spec_path_by_fr"]
