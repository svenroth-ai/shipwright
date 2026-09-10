# Dynamic discovery of requirement-elicitation citing docs

## Context

`shared/tests/test_requirement_elicitation_refs.py`'s `CITING_DOCS` was a
hardcoded 4-tuple of doc paths that must cite
`shared/requirement-elicitation.md`. FR-01.16 AC09 requires that which
capabilities elicit requirements from a human "is established by looking for
them, not by consulting a list someone must remember to extend" — a 5th
elicitation surface added without also editing this test's tuple would ship
uncited, and nothing would fail.

Precedent research (mandated before writing code, per iterate SKILL.md Step
6's Registry-driven SSoT meta-test rule): the established forward/reverse
discovery shape lives in
`plugins/shipwright-iterate/tests/test_touches_build_python_inputs_sync.py`
(sibling: `shared/tests/test_fr_authoring_refs.py`, itself still a
hardcoded-enumeration guard, deliberately unchanged here). Followed that
pattern rather than inventing a new mechanism.

## Decision

Replaced `CITING_DOCS` with
`discover_elicitation_reference_docs(root: Path) -> tuple[Path, ...]`
(`shared/tests/_elicitation_discovery.py`, a new test-only helper module),
which globs `plugins/*/skills/*/references/*.md` and keeps every doc
containing the literal substring `"recommended answer"` — verified
(precedent research, grep against all 190 `references/*.md` files in the
repo) to appear in exactly the 4 currently-known citing docs
(`interview-protocol.md`, `step-c-interview.md`, `path-a-feature.md`,
`path-b-change.md`) and nowhere else; each carries the phrase inside the
Pocock-style "one question at a time, each with a recommended answer"
grilling-rule blockquote, a genuine positive signal the doc governs
human-facing elicitation.

Split into three files to stay under the 300-LOC bloat-baseline cap:
`_elicitation_discovery.py` (marker + `discover_elicitation_reference_docs` +
`doc_cites_the_module`), `test_requirement_elicitation_refs.py` (forward
direction only, unchanged behavior), `test_requirement_elicitation_discovery.py`
(new — reverse direction, now parametrized over the discovery function, plus
the AC1/AC2/AC3 proof tests and the pre-existing
`test_project_interview_protocol_wires_the_context_producer`).

## Consequences

A doc added under any plugin's `references/` dir that carries the marker is
reverse-checked for the citation automatically, without editing this test
file. The marker itself (`"recommended answer"`) remains a natural-language
phrase, not a repo-owned structural marker (e.g. an HTML comment) — see
External-Plan-Review-Findings below for why that hardening was rejected for
this sub-iterate specifically (it would require editing
`plugins/shipwright-adopt/skills/adopt/references/step-c-interview.md`, out
of scope). A vacuous or partially-regressed discovery result now fails loudly
(`test_discovery_finds_at_least_the_known_citing_docs`) rather than silently
passing.

## Rationale

Producer/consumer split (helper module vs. test files) keeps the LOC cap
without duplicating the discovery logic across the two test files that both
need it (the reverse citation-check parametrize list and the dynamic/negative
proof tests). `doc_cites_the_module()` is shared between the real
parametrized reverse check and the enforcement-proof test specifically so the
proof exercises the SAME function, not a re-derived assertion that could
silently diverge.

## Rejected alternatives

- Keying discovery on the `"requirement-elicitation.md"` citation string
  itself — rejected per the spec's explicit AC3: that IS what the reverse
  check already asserts; using it to build the file list too would collapse
  discovery and the citation check into one, making the reverse check unable
  to ever fail on a missing citation.
- Exact-set equality for the AC1 regression pin (`discovered == known-4`) —
  rejected (external plan-review, round 1, OpenAI medium finding #2): would
  fail the moment a legitimate 5th surface is added, reintroducing exactly
  the "remember to extend a list" burden AC09 exists to remove. Replaced with
  a subset check (`known-4 ⊆ discovered`) plus an explicit non-empty guard.
- A repo-owned structural marker (HTML comment / front-matter field) instead
  of the prose phrase — see External-Plan-Review-Findings, round 1, GLM/OpenAI
  medium findings, rejected-with-reason (scope boundary on
  `plugins/shipwright-adopt/`).

## External-Plan-Review-Findings (Step 3.5, round 1)

Both GLM and OpenAI returned `revise` on the mini-plan.

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | GLM+OpenAI | medium | `"recommended answer"` is a natural-language phrase, not a repo-owned structural marker — fragile to a future paraphrase (false negative) or an unrelated doc's incidental prose (false positive) | rejected-with-reason — a dedicated marker would require editing all 4 current docs, including `plugins/shipwright-adopt/skills/adopt/references/step-c-interview.md`, which this sub-iterate may only READ, never write (explicit scope boundary). Editing only the other 3 would be inconsistent and leave the adopt surface's fragility unaddressed anyway. Documented as a known, scope-bounded limitation in `_elicitation_discovery.py`'s module docstring; the vacuous-pass guard (finding 3 below) mitigates the worst-case failure mode |
| 2 | GLM | low | Glob layout (`plugins/*/skills/*/references/*.md`) hardcodes a directory depth; plan didn't confirm all 4 known docs actually match it | rejected-with-reason — already verified during precedent research (`grep -rl "recommended answer" plugins/*/skills/*/references/*.md` returned exactly the 4 known paths); no code change needed, the property already holds |
| 3 | GLM | low | Vacuous-pass hazard: an empty or partially-regressed discovery result could silently pass the regression pin | accepted-and-fixed — `test_discovery_finds_at_least_the_known_citing_docs` now asserts `DISCOVERED_ELICITATION_DOCS` is non-empty AND that the known-4 set is a subset, so both a total vacuous pass and a partial regression fail loudly |
| 4 | GLM | low | 3-way file split (helper + 2 test files) is near the over-production threshold for one test's mechanics | rejected-with-reason — the split is LOC-cap-forced, not stylistic; the pre-split single file crossed 300 lines twice during authoring (confirmed by the repo's own bloat-guideline hook) |
| 5 | GLM | low | No note that `test_fr_authoring_refs.py`'s own `CITING_DOCS` remains a separate, still-hardcoded enumeration | accepted-and-fixed — one-line comment added next to `KNOWN_CITING_DOCS` noting the asymmetry is intentional (different SSoT guard, out of scope here) |
| 6 | OpenAI | medium | Exact-set equality (`discovered == known-4`) reintroduces the "remember to extend a list" burden for a legitimate 5th surface | accepted-and-fixed — see Rejected alternatives above; switched to a subset check |
| 7 | OpenAI | medium | The dynamic-discovery proof test only shows the helper RETURNS a fixture path — it doesn't prove a discovered-but-uncited doc is actually caught by the reverse-check enforcement | accepted-and-fixed — extracted `doc_cites_the_module()` into the shared helper module (now used by both the real parametrized reverse check and a new `test_a_discovered_but_uncited_fixture_doc_fails_the_reverse_check`, which discovers a marked-but-uncited fixture doc and asserts `doc_cites_the_module()` reports it as failing) |
| 8 | OpenAI | low | Discovery should return a deterministically sorted tuple restricted to regular files | rejected-with-reason — already implemented (`path.is_file()` filter + `tuple(sorted(matches))`); no change needed |

**Verdicts:** round 1 GLM revise / OpenAI revise — both addressed above (2
accepted-and-fixed each carrying real behavior changes: the subset-check
regression pin and the enforcement-proof test; 1 shared marker-hardening
finding rejected-with-reason on a hard scope boundary; the remaining low
findings either already satisfied or a cheap doc-comment addition).

## External-Code-Review-Findings (Step 3.7, round 2)

Ran against the working-tree diff (HEAD → staged changes, pre-commit). GLM
returned `approve`; OpenAI returned `revise`, repeating round 1's marker
finding.

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | GLM + OpenAI | medium | Same marker-fragility finding as plan-review round 1 (finding #1) | rejected-with-reason — same disposition as round 1; GLM's own spec-compliance checklist in this round confirms all 4 ACs are independently met despite the deviation |
| 2 | GLM | low | No test proves discovery over the REAL repo finds no doc outside the known 4 today (a marker false-positive) — the round-1 subset check alone cannot catch an unrelated doc being incorrectly swept in | accepted-and-fixed — added `test_discovery_has_no_unexpected_extra_matches_today`, a snapshot check distinct from the AC1 subset check: it is expected to need a `KNOWN_CITING_DOCS` update when a legitimate 5th surface is intentionally added (that friction is deliberate — it forces a human to confirm a new match is real, not a marker false-positive), but fails today if discovery finds anything beyond the known 4 |
| 3 | GLM | low | The AC2 dynamic-discovery proof's `REPO_ROOT`-independence from CWD is unverified but "negligible" per the reviewer's own assessment | no action — reviewer explicitly stated no suggestion was required |
| 4 | GLM | low | `doc_cites_the_module()` has no `UnicodeDecodeError` handling, asymmetric with `discover_elicitation_reference_docs()`'s own handling (not a live bug today, since only already-UTF-8-validated discovered paths reach it) | accepted-and-fixed — added the same try/except, returning `False` (never raises) on a non-UTF-8 file, for symmetry and defense-in-depth against future callers |

**Verdict:** GLM approve, OpenAI revise (same marker finding, same disposition
as plan-review round 1). Both real low-severity findings fixed; no behavior
regression.

## Self-Review

1. **Spec Compliance** — pass. AC1 (`test_discovery_finds_at_least_the_known_citing_docs`), AC2 (`test_discovery_is_dynamic_a_new_reference_doc_is_picked_up`, plus `test_a_discovered_but_uncited_fixture_doc_fails_the_reverse_check` proving enforcement, not just discovery), AC3 (`test_discovery_signal_is_not_the_reverse_citation_string`), AC4 (all pre-existing forward assertions in `test_requirement_elicitation_refs.py` and the pre-existing `test_project_interview_protocol_wires_the_context_producer` unchanged and passing).
2. **Error Handling** — pass. `discover_elicitation_reference_docs()` and `doc_cites_the_module()` both tolerate a non-UTF-8 file without crashing (symmetric, per round-2 code-review fix).
3. **Security Basics** — pass (N/A-adjacent). Test-only change, no user input, no secrets, no new I/O boundary beyond reading local `.md` files already in the repo.
4. **Test Quality** — pass. 34 tests total across the two files; discovery-mechanism proof uses real `tmp_path` fixtures (no mocking of the discovery boundary itself, per the runner contract); negative/enforcement/false-positive cases all covered, not just the happy path.
5. **Performance Basics** — pass. Glob over ~190 `references/*.md` files, read once each; no N+1, no unbounded recursion (non-recursive glob pattern, single directory depth).
6. **Naming & Structure** — pass. `discover_elicitation_reference_docs` / `doc_cites_the_module` names state exactly what each returns; 3-file split (helper + forward test + reverse/discovery test) each independently under the 300-LOC cap.
7. **Affected Boundaries (ADR-024)** — N/A, justified. No serialized-format producer/consumer boundary is touched — this is test infrastructure reading Markdown prose files that are not a wire format between two components; there is no round-trip to probe (nothing writes the `references/*.md` docs programmatically, and nothing downstream deserializes discovery's output — it only drives `pytest.mark.parametrize`).

## Confidence Calibration

Not triggered — effective complexity is `medium` (not upgraded) and no
`touches_io_boundary` risk flag was raised by Step 3.4's diff-driven
re-check (`risk_flags: []`). Self-Review (above) is the only review pass
this criterion requires; skipped per the runner contract's own stated
trigger conditions.

## F2 — no structural impact

No new route, component, schema, service, write-surface, read-surface, or
convention. `discover_elicitation_reference_docs()` is test-only tooling
consumed by exactly one caller (the sibling reverse-direction test file);
`architecture.md` is unchanged.

## F3a — reflection

Gotcha, recorded in `.shipwright/agent_docs/conventions.md` under
`## Learnings`: on this campaign's continuing shared branch, a prior
sub-iterate's PR merges to `origin/main` via a GitHub squash/rebase-merge,
minting a NEW commit SHA there even though content is identical to the local
branch's own commits — `git merge-base(origin/main, HEAD)` then lands
*before* those local commits, so `diff_risk_recheck.py --base-ref origin/main`
diffs from that stale point and inflates `diff_loc`/`changed_file_count` with
already-merged sibling content (P4.2's grill-trace-gate files showed up as
"P4.3's diff" on the first attempt: 43 files / 4310 LOC instead of the real
3 files / 351 LOC). Fix: omit `--base-ref` (its documented default is
fork-point(HEAD, HEAD) = HEAD) on a continuing shared branch; confirm safety
first with `git diff --stat HEAD origin/main` (empty output means
content-identical, so HEAD is the correct base).

## Campaign-mode note

Built in campaign mode (interleaved-serial, shared branch). Spec, code, and
doubt review rows are recorded `not_run` / `delegated_to_orchestrator` per
this campaign's contract — the orchestrator runs that cascade at 3f-bis
before merge, not this runner.
