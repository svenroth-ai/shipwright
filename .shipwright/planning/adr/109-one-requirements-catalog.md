# ADR-109 — One requirements catalog, stated once, with explicit deep-link anchors

**Status:** accepted
**Date:** 2026-07-19
**Run:** `iterate-2026-07-19-requirements-merge-catalog`
**Campaign:** `2026-07-18-requirements-catalog`, sub-iterate **S6** (the migration)
**Supersedes in part:** the per-requirement `Refined by <run_id>` convention

---

## Context

Two independent defects met in the same file.

**The requirements had absorbed the changelog.**
`.shipwright/planning/01-adopted/spec.md` was 417 lines for 15 requirements.
FR-01.11 carried six `Refined by <run_id>` prose blocks and FR-01.14 five —
roughly 145 lines for a single requirement. `shared/fr-authoring.md` §6 already
files change history under commits, the changelog and `shipwright_events.jsonl`,
so every one of those lines was a second copy of something that lived elsewhere
and could go stale independently.

**Every deep link into the catalog was broken, silently.**
`rtm_generator._make_anchor` emits `#fr-0101`. The heading reads
`### FR-01.01 — /shipwright-run`, which github-slugger turns into
`fr-0101--shipwright-run`. The consuming viewer matches anchors **exactly**. So
all fifteen links resolved to nothing, scrolled nowhere, and reported no error —
a silent failure of precisely the kind this campaign exists to remove.

## Decision

1. **Compact in place.** The catalog stays at
   `.shipwright/planning/01-adopted/spec.md`. Descriptions and acceptance
   criteria are rewritten in plain business language; requirement text carries
   no run id, no ADR number and no file path. All fifteen ids, priorities,
   `Basis` values and `Layers` cells survive unchanged in value.
2. **Change history leaves the requirement.** *Which changes touched this
   requirement* becomes a query over the append-only event log. *Why it is
   shaped this way* stays in the planning document that produced it. Both are
   pointed at once, from a closing navigation section, never per requirement.
3. **Anchors are emitted explicitly** — `<a id="fr-01NN"></a>` before each
   requirement heading — and never left to slug generation.
4. **FV-2 flips at the two sites where the verdict was actually false**, and the
   two sites resolve differently. **D-layer** stops claiming coverage over an
   empty set and reports a state-naming `skip`, which does not affect the exit
   code. **D2 reports a `fail`** when no requirement is readable and a recorded
   change still names one — every such reference is unresolvable, which is the
   maximally-red state its old guard made unreachable. That failure **does** feed
   the exit code; see *Consequences*.
5. **Group I check I4 dedupes requirement ids globally**, not per document.

## Rationale

**The catalog must not move** (campaign SPEC §6.1). A requirements file placed
directly under `.shipwright/planning/` matches none of the `is_dir()` walks in
the toolchain. Zero requirements reads as pass-or-skip nearly everywhere, so the
requirements control plane would go dark **while reporting green**; at the same
time `_is_planning_spec` requires a path ending `/spec.md` under a split, so
every feature/change iterate would fail finalization, and the FR gate rejects the
only escape. Deadlock. Keeping the conventional path costs nothing.

**Explicit anchors are the strictly stronger condition.** An explicitly defined
anchor satisfies exact matching *whatever* the consumer's slug algorithm turns
out to do, so the guarantee does not rest on our reading of a cross-repo
consumer being correct.

**`skip` for D-layer, `fail` for D2 — and the difference is the point.** A
project with no requirements yet is a real and legitimate state, the first-run
path, so a check that merely *examined nothing* must not redden it. That is
D-layer: what FV-2 names there is the false *claim*, not the absence of a block,
and the fix removes the claim. Probed rather than assumed — the report renders
skip and pass with different markers and the skip names the state, so the two are
distinguishable to a reader, while the exit code is untouched.

D2 is a different question and gets a different answer. It does not merely
examine nothing: it holds concrete references that **cannot resolve**. Reporting
that as "nothing to check" was the falsity, and the honest verdict is a failure.
So D2 does affect the exit code, deliberately, and the trigger is narrow — no
readable requirement **and** a recorded change naming one. With no such
reference, D2 still skips, so the first-run path stays green.

## Alternatives rejected

| Alternative | Why not |
|---|---|
| **Bump the bloat baseline** to fit the FV-2 guard (external review, Gemini, HIGH) | Ratcheting `current` upward is a contract violation (Group H audit H3). The reviewer also misread the extraction as 298 lines out of `group_d.py`; it is ~40 lines out of `_group_d_traceability.py`, along a seam that already existed — `refine_d1_covered` refines a *set* while its siblings render *findings*. Fixed by a coherent extraction instead. |
| **Register an artifact-migration allowlist entry** (both reviewers, HIGH) | The acceptance criterion anticipated the catalog quoting legacy-looking paths. It quotes none — compaction removed them — so an exemption would license exactly what this step forbids. Resolved with a *test* asserting the catalog sits under the registered, `migrated` `planning` entry, rather than with a waiver or a passing lint. |
| **Inline anchors in the table row** instead of 15 headings (Gemini, LOW) | Would leave two anchor conventions, since seven requirements genuinely have detail sections. The real risk the reviewers pointed at — 15 extra headings becoming a second parsed representation — is now pinned by reading the catalog through the production parser. |
| **Flip Group I and D-orphan too** | Attempted; it broke two unrelated pins and showed they are a different situation. Group I is detective-only and S5 already made its skip name which of six states produced it. D-orphan's sentence over an empty set is *true*, not vacuous: had any test carried an `@FR` tag, every one would be absent-FR and would land in `orphans`. |
| **Escalate the empty-set skip to a hard fail** (Gemini, MEDIUM) | **Rejected for D-LAYER, and this row originally read as if it covered both sites — it did not.** For D-layer the rejection stands: it examined nothing, so failing would be a false red on every project before its first requirements run, and promoting these checks to hard is out of scope for the campaign (SPEC §8). For D2 the reviewer's point was correct and is what shipped: D2 does not merely examine nothing, it holds references that cannot resolve, so it fails. Recording this as a blanket rejection while the diff implemented half of it is exactly the ADR-vs-code drift the review round caught elsewhere in this document. |
| **Per-requirement reference links to each planning document** (Gemini, LOW) | Reintroduces per-requirement provenance, which is exactly what produced the 145-line requirement. |

## Consequences

- All fifteen deep links resolve, proven **end to end** (matrix → relative link →
  file on disk → anchor defined there) for every link, not a representative one.
- **TWO externally visible breaks**, both documented in
  `docs/migrations/requirements-catalog-merge.md`:
  1. A downstream repo whose several requirement documents legally reuse ID
     numbers now fails I4.
  2. **D2's flip is a new block.** A project with zero readable requirements
     AND at least one event carrying `affected_frs` now exits non-zero, and the
     dashboard renders `FAIL — drift found`. `any_fail` is
     `any(f.status == "fail")` with no `source` filter and no detective-only
     exemption, so a failing Group-D finding drives the exit code like any
     other.

  > **Corrected in review.** This ADR, the changelog drop and the migration
  > guide all originally said *"the audit exit code is unchanged … without a new
  > block"*. That was wrong, and it was wrong in the three places an operator
  > actually reads, while this run's own `frozen_bugs` note said plainly *"Zero
  > spec FRs plus an FR-referencing event now FAILs"*. The internal record was
  > honest and the shipped documents were not — which is the same defect class
  > this campaign exists to remove, committed by the change that removes it.
  >
  > The claim came from over-generalising the D-LAYER decision. D-layer really
  > does resolve to a non-blocking skip; D2 does not, and I carried the
  > sentence across both without re-checking the branch I had just written.
  >
  > **The first correction was itself incomplete, and that is the more useful
  > lesson.** It added this note to *Consequences* while leaving the wrong text
  > standing in *Decision* (item 4), in *Rationale*, and in the rejected-
  > alternatives table — where "escalate the empty set to a hard fail" was
  > listed as REJECTED while the diff implemented it for D2. So the document
  > asserted and retracted the same claim, and a reader who stopped at the two
  > sections an ADR exists to be read for got the retracted answer. Appending a
  > correction is not correcting; all four sites now agree, and the pin below
  > covers all three artifacts rather than only the guide, which is why it
  > caught nothing the first time.
- **D-layer's** half is non-blocking as stated: it resolves to a skip, and skip
  does not feed the exit code.
- `frozen_bugs.STILL_FROZEN` is now empty: with FV-2 flipped, the golden corpus
  stops being a freeze of known-wrong behaviour and becomes a plain regression
  baseline. A surprising cell is now a defect to investigate, not a frozen bug to
  respect.

## Honest limits

- The **consumer's exact-match behaviour** is measured, not re-verifiable from
  this repo. Mitigated by choosing the strictly stronger local condition (see
  Rationale), which holds whatever the consumer's slug algorithm does. It is not
  carried in the ledger as an *untestable behaviour*: it is a **premise** of this
  change rather than something this change delivers, and it belongs to another
  repository's code.
- **The FR-coherence report about this catalog is knowingly wrong.**
  `compute_fr_coherence` calls a requirement coherent when its `### FR-…` heading
  carries `**Description:**` and `**Acceptance Criteria:**` labelled blocks. This
  catalog states each description in the *table* and each criterion as a `- (E)`
  bullet, so all fifteen report as missing both — including the eight that gained
  real criteria here. Pre-S6 the same file produced seven such entries, so the
  merge roughly **doubled** a false statement inside the campaign whose thesis is
  removing them. Adding the labels would duplicate every description fifteen
  times; renaming the headings would degrade the document to dodge a parser, and
  the deep links land on those headings. The correct fix — teach the check that a
  heading whose id is also a table row is a *detail section*, not a definition —
  is a behaviour change to a shared verifier every adopted repo consumes and
  needs its own baseline. S1/S5 are Tier-2 WARN and gate nothing. The exact count
  is pinned in `test_requirements_catalog_parsers.py`, so the deferral expires
  loudly rather than quietly.
- **Closed in review, recorded because it shipped open:** whether the
  traceability *collector* short-circuits before classifying tags when it finds
  no requirements — the one falsifier of the argument for leaving D-orphan
  unflipped. It does not. `test_links.build_manifest` walks every test file
  unconditionally and every `@FR` hit falls to `fr_absent` / `confirmed_orphan`,
  so over an empty set `orphans` is necessarily non-empty. Now a probe rather
  than a paragraph:
  `test_group_d_empty_set_verdicts.py::test_zero_requirements_plus_a_tagged_test_yields_a_nonempty_orphan_list`.
- A **folded row's** anchor degradation (`fr-0107-folded--fr-0105-health-check`)
  is not probed, because this repo has no fold map and the matrix emits no folded
  link. The end-to-end loop would cover one the moment it appears.

## External review

Both legs substantive — **Gemini's leg was not degenerate**, breaking the
four-run pattern recorded on S2–S5. Eleven findings (Gemini 5, GPT 6): two
changed the implementation (the FR-table-reader assertion, the I4 regression
tests), one was resolved with a test instead of the suggested change (the
artifact-migration entry), one was **accepted for D2 and rejected for D-layer**
(the empty-set escalation — see the alternatives table; this ADR originally
recorded it as a blanket rejection while the diff implemented half of it), and
the rest are dispositioned above.

The internal **code review** that followed found more, and the two that matter
are recorded where they happened rather than only here: the first correction of
the exit-code claim was itself incomplete (see *Consequences*), and
`_group_d_empty_state` re-derived a classification its own docstring told it to
read from Group I, reporting a fully-retired spec as an empty table (see the
module docstring and
`test_group_d_empty_state_diagnosis.py::test_an_all_retired_spec_is_not_reported_as_an_empty_or_broken_table`).
