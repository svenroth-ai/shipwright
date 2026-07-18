"""Signal cascade + confidence policy for the backfill engine (traceability TT6).

Pure adjudication: given one enumerated :class:`TestRecord` and the requirement
context, run the deterministic-first cascade (Spec §7 / §11-R1) and return a
:class:`Resolution` — the tags to auto-write, the advisory proposals for the
report, and any orphan classification.

BINDING confidence policy (Spec §11-R1, fixed + documented):

* Auto-write requires a **deterministic** signal that names exactly ONE live FR:
  a canonical ``FR-XX.YY`` token in the path (``path_fr_token``), a filename
  ``NN-`` prefix whose split holds exactly one active FR (``unique_split``), or an
  introducing commit whose ``affected_frs`` is exactly one active FR
  (``unique_commit``). Each clears ``AUTO_WRITE_THRESHOLD`` (0.90).
* **Title similarity and the LLM leg may NEVER auto-write alone** — they are
  capped below the threshold (0.70 / 0.60) and only ever produce report
  proposals (or corroborate a deterministic candidate). This is the §11-R1 rule
  that a heuristic verdict needs deterministic corroboration.
* Tie-break (documented): higher confidence → more corroborating signals →
  lexicographically smaller FR id. Two deterministic signals naming DIFFERENT
  FRs is a ``conflict`` — nothing is auto-written; both go to the report.
* Multi-FR: two DISTINCT deterministic FRs on one test is treated as the
  ``conflict`` above (surfaced, never a guessed write); a single deterministic
  FR with corroborating heuristic signals writes that one FR. Ambiguous/heuristic
  candidates stay advisory.
* ``unique_split`` (a bare ``NN-`` filename prefix) is a Shipwright-split
  convention — but ``NN-`` is ALSO the near-universal Playwright/Cypress
  execution-ORDER convention on brownfield repos. So it auto-writes ONLY when the
  caller asserts ``split_convention`` (adopt/retrofit default it False); otherwise
  it degrades to an advisory proposal, never false coverage in the TT1 manifest.

Orphan categories (Spec §11-R4) — never brand every unmapped test stale:

* ``confirmed_orphan`` — an explicit tag → a removed/absent FR.
* ``possible_orphan`` — untagged, but the strongest heuristic match is a removed
  FR and no active FR matches.
* ``unmapped`` — untagged with no signal at all (informational, not an accusation).
"""

from __future__ import annotations

from dataclasses import dataclass, field

AUTO_WRITE_THRESHOLD = 0.90
LLM_CAP = 0.60             # the LLM leg can never reach the auto-write floor either
_CONF = {"path_fr_token": 0.98, "unique_split": 0.95, "unique_commit": 0.90}
_DETERMINISTIC = frozenset(_CONF)

# The fuzzy title-similarity leg lives in its own module; re-exported here because
# callers (and __all__) have always imported these names from backfill_signals.
try:  # flat import off shared/scripts/lib on sys.path (tool + tests).
    from _backfill_title_sim import TITLE_CAP, TITLE_MIN, jaccard, title_scores, tokenize
    from _backfill_fold import resolve_tag as _fold_resolve_tag
except ImportError:  # loaded as a package (lib.backfill_signals).
    from ._backfill_title_sim import (  # type: ignore
        TITLE_CAP, TITLE_MIN, jaccard, title_scores, tokenize,
    )
    from ._backfill_fold import resolve_tag as _fold_resolve_tag  # type: ignore


def split_of_fr(fr_id: str) -> str:
    """``FR-05.01`` → ``05`` (the split id)."""
    return fr_id[3:5]


@dataclass
class Candidate:
    fr: str
    confidence: float
    signals: list[str] = field(default_factory=list)

    @property
    def deterministic(self) -> bool:
        return any(s in _DETERMINISTIC for s in self.signals)


@dataclass
class Resolution:
    test_id: str
    auto_write: list[Candidate] = field(default_factory=list)
    proposals: list[Candidate] = field(default_factory=list)
    orphans: list[dict] = field(default_factory=list)   # confirmed / possible / unmapped
    honoured: list[str] = field(default_factory=list)   # existing active tags (idempotent)
    conflict: bool = False


@dataclass
class Ctx:
    """Requirement context shared across every test resolution."""

    frs_by_id: dict            # fr_id -> FR
    active_ids: set
    removed_ids: set
    split_index: dict          # "NN" -> [active fr ids]
    commit_frs: dict           # rel_path -> [fr ids]
    adjudicator: object | None = None
    use_llm: bool = False
    split_convention: bool = False   # trust a bare NN- filename as a split id
    fold_map: object | None = None   # merged ## FR-Fold-Map (folded id -> survivor)

    def resolve_tag(self, fr: str) -> tuple[str | None, str | None]:
        """``(survivor, terminal)`` for a tagged id. ``survivor`` None ⇒ rescues nothing.

        Delegates to the SHARED ``fr_fold_map.resolve_fold`` rather than re-deriving the
        walk, so this engine and the compliance collector can never disagree about what a
        folded tag means (pinned by a cross-consumer test). ``terminal`` — the id the walk
        stopped at — lets the caller name an unrescued tag honestly: a chain ending at a
        RETIRED FR is ``fr_removed``, not ``fr_absent``. Rule order (active → removed →
        walk) lives in ``_backfill_fold.resolve_tag``."""
        return _fold_resolve_tag(fr, active_ids=self.active_ids,
                                 removed_ids=self.removed_ids, fold_map=self.fold_map)


def build_ctx(frs, *, commit_frs=None, adjudicator=None, use_llm=False,
              split_convention=False, fold_map=None) -> Ctx:
    frs_by_id = {fr.id: fr for fr in frs}
    active = {fr.id for fr in frs if fr.status == "active"}
    removed = {fr.id for fr in frs if fr.status == "removed"}
    split_index: dict[str, list[str]] = {}
    for fid in active:
        split_index.setdefault(split_of_fr(fid), []).append(fid)
    return Ctx(frs_by_id, active, removed, split_index, commit_frs or {},
               adjudicator, use_llm, split_convention, fold_map)


def _merge(cands: dict[str, Candidate], fr: str, conf: float, signal: str) -> None:
    c = cands.get(fr)
    if c is None:
        cands[fr] = Candidate(fr=fr, confidence=conf, signals=[signal])
    else:
        c.confidence = max(c.confidence, conf)
        if signal not in c.signals:
            c.signals.append(signal)


def _title_scores(record, ctx: Ctx, only_ids: set) -> list[tuple[str, float]]:
    return title_scores(record.name, ctx.frs_by_id, only_ids)


def _run_llm(record, ctx: Ctx, candidate_ids: list[str]) -> Candidate | None:
    """Invoke the injected adjudicator on the R4-bounded payload (advisory only).

    The path + title are secret-scrubbed before they leave the process (§11-R4
    "redact secrets": a free-form TS/JS ``it('…')`` title can embed a token)."""
    if not (ctx.use_llm and ctx.adjudicator is not None):
        return None
    from backfill_llm import redact_secrets  # local: keep the network leg out of import
    payload = {
        "test_path": redact_secrets(record.rel_path),
        "test_title": redact_secrets(record.name),
        "candidate_frs": [c for c in candidate_ids if c in ctx.active_ids][:32],
    }
    try:
        resp = ctx.adjudicator.adjudicate(payload)
    except Exception:
        return None
    fr = resp.get("proposed_fr")
    if not fr or fr not in ctx.active_ids:
        return None
    conf = min(float(resp.get("confidence", 0.0) or 0.0), LLM_CAP)
    return Candidate(fr=fr, confidence=conf, signals=["llm"])


def _dead_reason(ctx: Ctx, fr: str) -> str:
    """Why a candidate FR is not live: removed (in ``## Removed``) vs absent."""
    return "fr_removed" if fr in ctx.removed_ids else "fr_absent"


def resolve_test(record, ctx: Ctx) -> Resolution:
    """Run the cascade for a single test and classify the outcome."""
    res = Resolution(test_id=record.test_id)

    # Signal (a): explicit existing tags. Honour live ones; NEVER re-write
    # (idempotent). A tag naming a FOLDED id is honoured as coverage of its surviving
    # FR (``## FR-Fold-Map``) rather than branded a confirmed orphan — otherwise a spec
    # taxonomy fold would make the engine both report false orphans AND propose a
    # redundant re-tag of a test that is already correctly labelled. Only a tag that
    # rescues nothing becomes its own confirmed orphan, so TT7/TT8 triage still sees
    # every genuinely dead one — even on a mixed live/dead or multi-dead test.
    if record.is_tagged:
        for fr in record.existing_frs:
            survivor, terminal = ctx.resolve_tag(fr)
            if survivor is None:
                # Name it by what the tag points AT: a chain ending at a retired FR is
                # `fr_removed`, not the misleading `fr_absent` the folded id implies.
                res.orphans.append({
                    "category": "confirmed_orphan", "tagged_fr": fr,
                    "reason": _dead_reason(ctx, terminal or fr)})
            elif survivor not in res.honoured:
                res.honoured.append(survivor)
        return res

    # Untagged: run the deterministic-first cascade. Candidates against a LIVE FR
    # go in ``cands``; a signal that resolves ONLY to a removed/absent FR is kept
    # in ``dead`` so the test surfaces as a possible orphan, not ``unmapped``.
    cands: dict[str, Candidate] = {}
    dead: dict[str, Candidate] = {}

    def _live_or_dead(fr: str, conf: float, signal: str) -> None:
        _merge(cands if fr in ctx.active_ids else dead, fr, conf, signal)

    from backfill_scan import path_fr_tokens, split_of_path  # local: avoid a load-time import cycle
    # (b) path FR token — exact. A token to a removed/absent FR is a dead signal.
    for tok in path_fr_tokens(record.rel_path):
        _live_or_dead(tok, _CONF["path_fr_token"], "path_fr_token")

    # (b) split prefix — a unique split auto-writes ONLY when the caller asserts
    # the repo follows the Shipwright split convention; otherwise it is advisory
    # (a bare NN- is the Playwright/Cypress execution-order convention too).
    split = split_of_path(record.rel_path)
    if split and split in ctx.split_index:
        members = ctx.split_index[split]
        if len(members) == 1 and ctx.split_convention:
            _merge(cands, members[0], _CONF["unique_split"], "unique_split")
        elif len(members) == 1:
            _merge(cands, members[0], 0.55, "split_prefix")   # advisory (no convention asserted)
        else:
            for fid in members:
                _merge(cands, fid, 0.40, "split_set")

    # (d) introducing commit — unique commit auto-writes; multi is advisory. A
    # commit whose only FRs are removed/absent is a dead signal.
    commit_frs = ctx.commit_frs.get(record.rel_path, [])
    commit_active = [f for f in commit_frs if f in ctx.active_ids]
    if len(commit_active) == 1:
        _merge(cands, commit_active[0], _CONF["unique_commit"], "unique_commit")
    elif len(commit_active) > 1:
        for fid in commit_active:
            _merge(cands, fid, 0.40, "commit_set")
    else:
        for fid in commit_frs:              # only dead commit FRs remain
            _merge(dead, fid, _CONF["unique_commit"], "commit")

    # (c) title similarity — advisory (capped); against live AND removed FRs.
    active_scores = _title_scores(record, ctx, ctx.active_ids)
    for fid, sim in active_scores:
        _merge(cands, fid, sim, "title_similarity")
    for fid, sim in _title_scores(record, ctx, ctx.removed_ids):
        _merge(dead, fid, sim, "title_similarity")

    # (e) LLM adjudication of the residue — advisory only.
    if not any(c.deterministic for c in cands.values()):
        llm = _run_llm(record, ctx, [fid for fid, _ in active_scores] or sorted(ctx.active_ids))
        if llm is not None:
            _merge(cands, llm.fr, llm.confidence, "llm")

    return _classify(record, ctx, cands, dead)


def _classify(record, ctx: Ctx, cands: dict, dead: dict) -> Resolution:
    res = Resolution(test_id=record.test_id)
    det_frs = {c.fr for c in cands.values() if c.deterministic}

    if len(det_frs) > 1:
        # Two deterministic signals disagree — never guess; surface the conflict.
        res.conflict = True
        res.proposals = sorted(cands.values(), key=lambda c: (-c.confidence, c.fr))
        return res

    for c in cands.values():
        if c.deterministic and c.confidence >= AUTO_WRITE_THRESHOLD:
            res.auto_write.append(c)
        else:
            res.proposals.append(c)
    res.auto_write.sort(key=lambda c: c.fr)
    res.proposals.sort(key=lambda c: (-c.confidence, c.fr))

    if not cands:
        # No signal against any ACTIVE FR. If a signal pointed at a removed/absent
        # FR → a *possible* orphan (a review candidate). Otherwise truly unmapped —
        # never a stale-feature accusation (§11-R4).
        if dead:
            # Documented tie-break: highest confidence, then SMALLEST FR id.
            best = min(dead.values(), key=lambda c: (-c.confidence, c.fr))
            res.orphans.append({
                "category": "possible_orphan", "candidate_fr": best.fr,
                "reason": _dead_reason(ctx, best.fr),
                "signals": best.signals, "confidence": round(best.confidence, 3),
            })
        else:
            res.orphans.append({"category": "unmapped"})
    return res


__all__ = [
    "AUTO_WRITE_THRESHOLD", "TITLE_MIN", "TITLE_CAP", "LLM_CAP",
    "Candidate", "Resolution", "Ctx", "build_ctx", "resolve_test",
    "tokenize", "jaccard", "split_of_fr",
]
