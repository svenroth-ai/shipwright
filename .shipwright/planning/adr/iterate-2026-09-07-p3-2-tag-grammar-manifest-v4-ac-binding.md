# ADR: AC-scoped @covers tag grammar + test-traceability manifest v4

**Run-ID:** iterate-2026-09-07-p3-2-tag-grammar-manifest-v4
**Campaign:** req3-04c-ac-identity-wave2, sub-iterate p3.2 (tag-grammar-manifest-v4)

## Correction (2026-09-07, after PR #686's Stage-1 REJECT)

Everything below this note describes AC#3 as it read when this sub-iterate was
first built: **"the shipwright-webui reader accepts v4"**, verified by two
empirical round-trip probes against the WebUI's `readTraceabilityIndex`
(see Confidence Calibration below). That framing was WRONG and the Stage-1
spec-reviewer correctly REJECTED on it: a monorepo sub-iterate cannot commit
into the separate `shipwright-webui` repository, and the campaign SPEC itself
self-contradicted on whether this unit owned that work at all. The operator
resolved this: the WebUI reader is owned by sub-iterate `w3` of a *separate*
campaign (`req3-06-mechanics-webui`, card `trg-a2017e6f`), and AC#3 was
reworded to the narrower, in-repo-verifiable claim this unit actually owes the
WebUI — **a wire-format guarantee, not an implementation**: "the v4 manifest
stays readable by a v3-shaped consumer — additive nodes only, no field
removed or retyped, verified against a frozen v3 fixture." A new AC#4 was
added: "no change is attempted in the shipwright-webui repository."

The two round-trip probes described below are **historical** — they answered
a question ("does the WebUI reader crash or drop data on v4?") that is no
longer this unit's acceptance criterion, and they are not test-locked (an
external, unreproducible manual check). The CURRENT evidence for the
corrected AC#3 is `plugins/shipwright-compliance/tests/test_traceability_contract.py::TestTheGate::test_v4_stays_additive_over_the_frozen_v3_shape`
— a real pytest assertion that diffs the live v4 contract's skeleton against
the frozen `contracts/test-traceability-3.0.json` fixture and asserts nothing
was removed or retyped. AC#4 is satisfied trivially: this diff never touches
a `shipwright-webui` path (confirmed by Stage-2/Stage-3 review). The rest of
this ADR (grammar design, manifest shape, version lockstep, rejected
alternatives #1-#3) is unaffected by the correction and stands as originally
decided.

## Context

P3.1 (PR #683) minted tool-assigned `[ACnn]` markers for FR acceptance
criteria (`lib.ac_identity`) but left the library dormant — no consumer read
an AC id yet. P3.2's spec asks for exactly three things: (1) a
`@pytest.mark.covers("FR-01.11/AC07")` tag form where a bare `FR-01.11` stays
valid so the ~1,243 existing tags in both repos keep working; (2)
`test-traceability.json`'s `schema_version` and `requirement_model.py`'s
`MODEL_VERSION` bump together (frozen, `additionalProperties:false`,
churn-allowlisted contract); (3) the shipwright-webui reader accepts v4.

## Decision

Extend `lib.fr_tag_grammar.parse_python`'s `pytest_marker` form to accept an
optional `/ACnn` suffix, resolved by a new `canonical_fr_ac()` helper
(extracted to `lib._fr_ac_token` to respect the 300-LOC bloat baseline,
mirroring the P3.1 `_ac_markers.py` split). A malformed suffix invalidates
the WHOLE tag (fail-closed, `reason=non_canonical_ac_id`) rather than
degrading to a bare-FR hit. The manifest gains, additively (D9 pattern —
omitted when empty, same shape as `resolved_from`/`fold_map`): a per-requirement
`acs` map (`{"AC07": {"tests": {...}, "coverage": {...}}}`) and an optional
`ac_id` on each `testLink`. `schema_version` 3→4 and `requirement_model.py`'s
`MODEL_VERSION` 3→4 move together, enforced by an existing lock-step test.
`acs` is added to `compare_traceability_manifest.py`'s execution-derived key
set — never gates structural drift, same as `tests`/`coverage`. Swept the
whole `plugins/shipwright-compliance` + `shared` tree for
`schema_version`/`MODEL_VERSION` consumers of THIS contract specifically
(not unrelated event-context/triage schemas) and bumped two more that would
otherwise fail-closed-SKIP forever against a real v4 manifest:
`_group_d_manifest.py` and `_rtm_layer_columns.py`. Bumped the frozen contract
gate (`traceability_contract_support.py` + a newly generated, actually-run
`contracts/test-traceability-4.0.json` fixture; the v3.0 fixture is untouched).
AC#3 is verified empirically, not by touching the separate shipwright-webui
repo: two real round-trip probes against the actual built
`readTraceabilityIndex` (a hand-crafted v4 example manifest, and a manifest
produced by this repo's own `build_manifest()` against AC-tagged pytest
tests) both returned `status: "ok"` with the reader's existing fail-soft
unsupported-version path (logs once, does not crash or drop the file).

## Consequences

Every future `@covers` tag MAY additionally name an AC without breaking any
of the ~1,243 existing bare-FR tags (empirically confirmed: zero existing
tags in either repo already use a `/` suffix that the new fail-closed rule
would newly reject). The manifest's wire shape grows additively; a consumer
that never reads `acs`/`ac_id` is unaffected. `F5b`'s `update_compliance.py
--phase iterate` regenerates the actual committed
`.shipwright/compliance/test-traceability.json` to schema_version 4 as part
of this sub-iterate's own finalization (verified below), so this repo's own
Group-D/RTM audits do not regress to SKIP/`—` in the gap between merge and a
later regen. AC-existence validation (that a tagged `ACnn` was actually
minted for that FR) is explicitly deferred — see Rejected alternatives.

## Rationale

D9 (no content hash) carries forward unchanged from P3.1: AC ids are
tool-minted ordinals, never a fingerprint of criterion wording. The additive,
omitted-when-empty shape for `acs` avoids re-litigating the frozen contract's
`additionalProperties:false` posture — every existing manifest without an
AC-scoped tag is byte-identical in this respect. Fail-closed suffix
validation (never a silent partial match) matches the existing behavior of
`fr_tag_grammar`'s bare-FR token rule.

## Rejected alternatives

1. New separate `@covers_ac` marker form — doubles the tag surface migration
   burden for zero benefit; the spec explicitly asked for a suffix on the
   existing form.
2. Content-hash-keyed AC binding — rejected per D9 (P3.1 precedent).
3. Validating AC *existence* against the P3.1 minted registry inside this
   grammar (raised as HIGH/MEDIUM by BOTH external plan review and BOTH
   external code review reviewers, twice each) — deliberately deferred to
   P3.4 ("every added tag names an AC id that exists" is that sub-iterate's
   own acceptance criterion) and P3.6, the keystone gate (baseline
   `ac_id`→tests, git-diff driven, blocks on an unbound/invalid AC). Doing it
   here would preempt those sub-iterates' own ACs. The risk window is small:
   this grammar version is not yet the emitter of any production tag until
   P3.4 backfills. Documented as a known, non-silent limitation in
   `fr_tag_grammar.py`'s module docstring, not an oversight.
4. Actually modifying the separate `shipwright-webui` repository to parse
   `acs`/`ac_id` — out of scope for this sub-iterate (different git
   repo/PR); AC#3's "accepts v4" is read as "does not crash or drop the file
   on an unsupported-but-well-formed newer version" (the reader's own
   existing fail-soft contract-version design), not as "renders AC-level
   detail" — narrower than a first reading might suggest, called out
   explicitly here because both external reviewers pushed back on this
   exact point twice.

## External Plan Review Findings (Step 3.5, Branch A — both openai and glm, verdict: revise)

| # | Source | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | high | AC existence/ownership not validated against the FR it's tagged on | rejected-with-reason: scope — deferred to P3.4/P3.6 (see Rejected Alternatives #3); documented in `fr_tag_grammar.py`'s docstring |
| 2 | openai | medium | WebUI only "accepts" v4 through its fail-soft unsupported-version path, not real parsing | accepted-and-fixed: AC#3's claim explicitly narrowed and justified in this ADR (Rejected Alternatives #4); verified empirically via 2 round-trip probes |
| 3 | openai | medium | Schema must explicitly permit `acs`/`testLink.ac_id` given `additionalProperties:false` | rejected-with-reason: already implemented — `traceability_schema.json` gained both properties in this diff; `test_every_documented_field_is_on_the_wire` proves both are on the LIVE wire, not just the frozen fixture |
| 4 | openai | low | Link cardinality/dedup for multi-AC or bare+AC tags on one test unspecified & untested | accepted-and-fixed: added `test_bare_and_ac_scoped_tags_on_the_same_test_merge_not_duplicate` |
| 5 | glm | medium | Well-formed but nonexistent AC ids silently produce coverage | rejected-with-reason: same scope deferral as #1 |
| 6 | glm | medium | v4 frozen fixture might not exercise the new fields (could stay empty) | rejected-with-reason: already guarded — `LOAD_BEARING` explicitly names the `acs`/`ac_id` wire paths and the live-contract test would fail on an empty `acs` |
| 7 | glm | low | WebUI compat verified manually only, no regression lock in this repo | accepted (documented): probe manifests + expected `status:"ok"` outputs recorded in this ADR's Confidence Calibration section; a live cross-repo executable test is not added here since shipwright-webui is not a dependency of this repo |
| 8 | glm | low | No sweep confirming no existing tag already uses a `/` suffix | accepted-and-fixed: grepped both repos for `covers("FR-\d+\.\d+/` — zero matches outside this diff's own new tests |
| 9 | glm | low | AC-level roll-up semantics (parent-inclusive vs AC-only) ambiguous | accepted-and-fixed: same regression test as #4 empirically pins parent-inclusive roll-up (dedup, not double-count) |

## External Code Review Findings (Step 3.7 item 2 — both openai and glm, verdict: revise)

| # | Source | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | high | No WebUI reader change/test in the diff for AC#3 | accepted (documented): same narrowed AC#3 reading as plan-review #2/#4; not a code defect in THIS repo |
| 2 | openai | medium | Parent-level dedup keyed only on `(id, tag_source)` silently keeps ONE ac_id when a test names two ACs of the same FR in one decorator, discarding the other at the parent | **accepted-and-fixed** — real bug, fixed in `_test_links_requirements.py::file_hit`: on an ac_id mismatch at the parent, DROP `ac_id` there (ambiguous, singular field) rather than guess; each AC's own bucket is unaffected. New regression test `test_two_different_acs_on_the_same_test_do_not_pick_one_at_the_parent` |
| 3 | glm | medium | AC existence never validated (same as plan review) | rejected-with-reason: same scope deferral, restated with more force by the reviewer — decision unchanged (see Rejected Alternatives #3) |
| 4 | glm | medium | `test_acs_are_sorted_by_ac_number_not_lexically`'s AC07/AC09 fixture sorts identically under lexical and numeric order — vacuous for its stated purpose | **accepted-and-fixed** — fixture changed to AC99/AC100 (genuinely diverges: lexically `"AC100" < "AC99"`, numerically 99 < 100), plus an explicit `sorted(...) != list(...)` self-check so the fixture cannot silently regress back to non-divergent again |
| 5 | glm | medium | Committed `.shipwright/compliance/test-traceability.json` not regenerated to v4 in the diff-so-far, while `_group_d_manifest.py`/`_rtm_layer_columns.py` now require v4 | accepted (procedural): `finalize_iterate.py` (F5b) calls `update_compliance.py --phase iterate`, which regenerates this exact file via the `test_links` collector, as part of this sub-iterate's own finalization — confirmed post-F5b (see F5b step below) |
| 6 | glm | low | TS/JS `@covers` forms silently drop a `/ACnn` suffix with no `invalid_tags` signal | rejected-with-reason: already documented as a known, non-silent (in the docstring) scope cut — TS/JS AC binding was not asked for by this spec |
| 7 | glm | — (positive) | bare-FR back-compat, MODEL_VERSION lockstep, and the v4 fixture's non-empty `acs` are called out as correctly done | no action — acknowledged |

## Confidence Calibration (Self-Review item 7 — Affected Boundaries, ADR-024)

Producer: `plugins/shipwright-compliance/scripts/lib/collectors/test_links.py`
(`build_manifest`). Consumers identified: (a) in-repo Group-D/RTM audits
(`_group_d_manifest.py`, `_rtm_layer_columns.py`); (b) the frozen contract
gate (`test_traceability_contract.py`); (c) the cross-repo shipwright-webui
reader (`readTraceabilityIndex` / `contract-version.ts`).

Round-trip probes run against consumer (c), the one outside this repo's own
test suite:

1. **Probe 1** — a hand-crafted v4 example manifest (mirroring
   `traceability_schema.example.json`) written to a scratch project root,
   read via the real, already-built `readTraceabilityIndex`. Result:
   `status: "ok"`, one fail-soft "unsupported schema_version" warning logged,
   no crash, no data loss beyond the reader's existing (pre-v4) behavior of
   not rendering unknown fields. Finding: none.
2. **Probe 2** — a manifest produced by this repo's actual `build_manifest()`
   collector against two real pytest tests carrying `FR-XX.YY/ACnn` tags
   (one enabled+pass, one enabled+not_run), read the same way. Result:
   `status: "ok"`, `caseCount: 2`, same fail-soft warning, no crash. Finding:
   none.

Two consecutive no-finding probes against the same boundary — asymptote
reached per `references/confidence-anti-patterns.md`. No further probe
needed against consumer (c). Edge case not probed: a webui-side type/schema
tightening that would reject an unknown `additionalProperties`-style field
inside `acs`/`testLink` — not applicable here, since (per glm's own plan-
review finding #7 above) the reader's fail-soft path is a coarse
whole-document version check, not per-field schema validation; the webui
repo's own test suite is the correct place to probe that, not this one.

## F5b verification (procedural fix, code-review finding #5)

After F5b's `finalize_iterate.py --phase iterate` ran,
`.shipwright/compliance/test-traceability.json`'s `schema_version` was
re-read and confirmed to be `4`, resolving the code-review finding that the
committed manifest lagged the version-4 consumers in the diff.
