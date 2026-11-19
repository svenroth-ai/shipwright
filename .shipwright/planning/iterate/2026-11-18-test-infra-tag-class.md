# Iterate Spec: test-infra-tag-class

- **Run ID:** iterate-2026-11-18-test-infra-tag-class
- **Type:** feature
- **Complexity:** medium (classifier said `small`; raised on positive evidence: the change edits a merge-blocking gate every iterate passes, and the operator asked for the full plan-review cascade)
- **Status:** implemented

## Goal
The F11 test-tag gate knows two kinds of test: one that proves a requirement, and one pytest does not collect. A test of the
test harness itself is neither, so it carries a stand-in requirement tag that inflates requirement coverage. Give the gate a
third, honest class - a test declared as infrastructure that proves no requirement - without opening a loophole.

## Acceptance Criteria
- [x] AC55 (FR-01.11) Given a Python test carries exactly `@pytest.mark.covers_none("tooling")` or `("infra")` (on the function, its
  class or a module/class `pytestmark`), lives in a file named **exactly** in the infrastructure-test catalog **as it stood at the
  merge-base**, and carries no `covers` tag anywhere, when the change is finished, then the gate counts it as infrastructure instead
  of flagging it as an untagged test; it never counts toward requirement coverage; and the gate message reports how many tests
  were classed this way.
- [x] Judged in full, not only when the gate would have flagged the test: every test in a changed file whose head carries any
  `covers_none` is checked (label, catalog, no `covers`, siblings). Any violation is a hard `bad-infra-class` finding: label other
  than `tooling`/`infra`, a non-literal or extra argument, a file outside the base catalog, a `covers` mark anywhere in reach
  (function, class, class/module `pytestmark` in any assignment form, `mark.covers` alias), or same-name siblings that do not
  ALL carry the same valid marker.
- [x] The catalog holds exact file paths only (no wildcard, no `..`, no backslash, no absolute path); the loader treats a
  malformed or invalid catalog at base as empty plus a WARNING naming the file, an absent one (`""`) as empty silently, and an
  unreadable one (`None`) as "cannot enforce". A CI test validates the head catalog (valid, every entry an existing test file).
- [x] A catalog change in the same diff does not license the tests of that diff (only the base catalog counts); the gate prints a
  WARNING whenever the catalog differs between base and head; the catalog is a CODEOWNERS-guarded path.
- [x] A test tagged at base (same id, or moved to another file with the same normalised body) that now carries a valid
  `covers_none` is a stand-in correction: accepted only when its path is in the base catalog at BOTH sides and every
  requirement/criterion it was tagged with at base still has another linked test at head; each correction prints a WARNING naming
  the dropped tag. Otherwise `bad-infra-class`. A tagged test that merely loses its tag stays `tag-removed`.
- [x] Adding or removing exactly `pytest.mark.covers_none` on an existing test is not a body edit (the digest ignores that exact
  shape only; any other `*.covers_none` decorator still counts), and `covers_none` labels are never read as requirement ids.
- [x] Infra resolution runs before the per-test exemption loop; infra-classed tests are left out of the `touched` denominator of
  the exemption share and counted separately.
- [x] The marker is registered wherever `covers` is registered (root and plugin `pyproject.toml`, consumer templates if any),
  so strict-marker runs stay green.
- [x] Python tests only. A TS/JS test cannot carry the marker; it stays untagged and is flagged as before.

## Spec Impact
- **Classification:** modify
- **MODIFY:** FR-01.11 - new AC55 (FOLD: the gate is FR-01.11's AC41/AC42/AC51; this completes it)
- **NONE justification:** n/a

## Out of Scope
- Retagging the changelog harness tests (they keep their stand-in tags until a follow-up uses the new marker; the changelog skill is untouched).
- WSL / Linux local-run documentation (operator is installing WSL; point 1 of the request is skipped).
- TS/JS support for the marker.
- Counting infrastructure tests in the F12 / PR-body exemption line (`exemption_summary.py` reads only the F5c block); the count is in the F11 gate message.
- Teaching the traceability collector a new "infrastructure" bucket: downstream reports keep listing these tests as untagged. Accepted: coverage is computed from tagged tests, so an untagged infra test can never inflate it; the infra count is visible in the gate message.
- A detective audit for `covers_none` tests that fall out of a later-narrowed catalog: the class is judged only when a test is touched (ratchet semantics), accepted.

## Design Notes
- No new vocabulary: labels are the FR-gate's existing `tooling`/`infra` (`lib.fr_classification.CHANGE_TYPE_VALUES`), per test instead of per run.
- Catalog: `shared/config/infra_test_paths.json`, a list of exact repo-relative file paths, read at the merge-base via the gate's `read(path, "base")`. Seed: the six existing testkit meta-test files in `shared/tests/` (`test_gh_stub.py`, `test_golden_driver_freeze.py`, `test_golden_trace.py`, `test_promise_hash.py`, `test_promise_hash_hardening.py`, `test_release_scratch.py`). No wildcards anywhere, so a future file can never pre-approve itself; adding a harness test file means adding its exact path in an earlier merge, and the failure message says so.
- Granting is strict (literal `pytest.mark.covers_none("<label>")`), contradiction detection is loose (any `.covers` attribute in reach) - missing a form is only safe in the granting direction.
- Why not option D (give the harness its own requirement): the requirement catalog is the product's promises; a harness "requirement" would count harness tests as requirement coverage and put a non-product capability into the spec, permanently, which is the same inflation in a tidier form. Kept for the case of a harness that is itself a user-visible capability.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| test source (`covers_none` marker) | `_tag_binding_py.py` marker parser -> `_tag_binding_core.evaluate` | Python AST |
| `shared/config/infra_test_paths.json` (read at merge-base) | `tag_binding_gate.py` loader | JSON list of exact paths |

## Confidence Calibration
- **Boundaries touched:** marker AST parse (`covers_none`, `pytestmark` in every assignment form); catalog JSON read at the merge-base through the gate's `read(path, "base")`; the head and base traceability manifests (units per test).
- **Empirical probes run:** `read(<absent path>, "base")` returns `""` (read from `spec_text_at`, and exercised through real git in `test_without_a_catalog_at_base_the_absent_file_is_the_silent_empty_case`); unreadable catalog (`None`) exercised by monkeypatching the reader in a real-git gate run; a parametrised sweep of marker forms (alias, helper alias, keyword, extra argument, variable label, destructured and conditional `pytestmark`) against the parser.
- **Test Completeness Ledger:** 18 behaviours, all `tested` (evidence in the F5c entry); no untestable row.
- **Confidence-pattern check:** the earlier plan reviews found loopholes by thought experiment; the code reviews found four more by running forms (rename plus edit of a stand-in, a re-added test beside a module marker, a destructured `pytestmark`, an unrelated retirement refusing an untouched infra test). Each is now a test. Residual: the shared merge-base resolver (inherited by every F11 gate) and an exact-path catalog entry for a real test in a reviewed PR (CODEOWNERS only).

## Verification (medium+)
- **Surface:** cli
- **Runner command:** `uv run pytest shared/tests/test_tag_binding_infra_class.py -q` (one root) plus scratch-git gate integration tests
- **Evidence path:** `.shipwright/agent_docs/iterates/iterate-2026-11-18-test-infra-tag-class.test-results.json`

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** high
- **Summary:** Core idea sound (base catalog, infra never feeds coverage, digest ignores the marker); as first planned it had real loopholes (open-ended globs, unbounded catalog widening, same-name siblings, moving a tagged test, quiet coverage loss, contradictory catalog-read handling).
- **Findings:**
  - security/high - seed globs approve future files: fixed (exact paths only, no wildcards, `shared/testkit/**` dropped).
  - security/high - base read only delays a widening: fixed (loader validation + CI test on head catalog + CODEOWNERS line + base-vs-head WARNING). Residual: an exact-path entry for a real test still needs a human at review; disclosed.
  - security/high - same-name siblings: fixed (every sibling must carry the same valid marker).
  - security/medium - moving a tagged test escapes `tag-removed`: fixed (digest match against base-tagged vanished tests, treated as correction).
  - security/medium - relaxation can silently drop an AC's last test: fixed (other linked test required; WARNING names the dropped tag).
  - correctness/medium - "both markers" rule could never fire: fixed (full pass over every test in a changed file carrying `covers_none`).
  - correctness/medium - parser covers fewer forms than pytest: fixed (strict grant, loose contradiction detection, tests per form).
  - architecture/medium - catalog-read contradiction / deadlock: fixed (`""` empty, `None` cannot enforce, malformed = empty + WARNING, CI validator).
  - correctness/low - `_is_covers` too broad for `covers_none`: fixed (exact shape only; `_covers()` untouched).
  - architecture/low - order and counting: fixed (infra before exemptions, out of the share denominator).
  - completeness/low - consumer-hint path, backslashes: fixed (hint only when a catalog exists at base; normalise before match; templates checked).
  - completeness/medium - missing tests/docs: fixed (test list expanded; guide Ch. 8 and gate catalog checked).
- **Known limitations:** an exact-path catalog entry naming a real requirement test is possible in a reviewed PR; guarded by CODEOWNERS only.
- **Status:** 12 fixed, 1 disclosed, 0 declined

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** Approve option B (source-declared marker + base catalog); close three gaps before build.
- **Findings:**
  - smallest-option/medium - why not D: answered in Design Notes (fixed).
  - security/medium - two-step widening and name-pattern seeds: fixed (exact paths; catalog CODEOWNERS-guarded; base-vs-head WARNING).
  - completeness/medium - other consumers still see "untagged": disclosed in Out of Scope with the reason (coverage cannot be inflated by an untagged test).
  - completeness/low - catalog narrowed later: disclosed (judged on touch, ratchet).
  - complexity-cost/low - two-merge friction: accepted; the failure message names the next step (fixed).
- **Known limitations:** downstream reports still list infra tests as untagged; no audit of out-of-catalog markers.
- **Status:** 3 fixed, 2 disclosed, 0 declined (verdict: approve)

## External Plan Review (GPT via codex, GLM via openrouter)
- **Verdicts:** openai=revise, glm=approve
- **Findings (all accepted-and-fixed in mini-plan rev 3, except as noted):**
  - openai/medium - digest filter contradicted the "exact shape only" criterion: fixed (only `pytest.mark.covers_none` skipped; alias is a body edit and never grantable).
  - openai/medium - valid corrections and untouched infra tests not counted consistently: fixed (every validated infra test counted and left out of `touched`).
  - openai/medium - `pytestmark = requirement_marks` hides a `covers` mark: fixed (non-literal `pytestmark` values refuse the grant).
  - glm/medium - bootstrap: catalog absent at this diff's base: fixed (no seed file is touched in this run; retag is a follow-up merge).
  - glm/low x5 - module-level `covers_none` absorbs later tests (disclosed + documented), moved-tagged-test outside catalog test (added), `read()` absent-vs-None (verified empirically at build), enumerate registration sites (build checklist), goldens pinning the share line (checked at build).

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-11-18-test-infra-tag-class/architecture_brief.md`
- **Verdicts:** glm=revise · openai=approve
- **Smallest thing that would do (per reviewers):** openai: as proposed (marker + exact-path catalog); glm: option A, a third per-test exemption code.
- **Findings:** glm/high simpler-alternative (option A) - rejected-with-reason; glm/medium catalog ownership burden - accepted-as-cost (failure message names the next step); glm/low proportionality - noted.
- **Reconciliation:** the plan had rejected option A because a self-reported code cannot be cross-checked against where the test lives (the objection an earlier review round already raised against `fixture-or-helper`), and the operator's explicit constraint is "no loophole". Asked the operator in plain words; **operator decision 2026-11-18: keep marker + exact-path catalog.** GLM's cost argument stands as the price of that choice and is recorded here. If per-campaign volume stays near ~9 tests, the catalog friction is the thing to revisit.

## Spec / Code / Doubt Reviews (subagents, Opus)
- **Spec review:** rejected once - the gate dropped its warnings whenever it failed (catalog differs, malformed catalog, correction drops stand-in tag). Fixed: warnings are part of the failure message; gate-level tests assert it. Also fixed: untested contradiction forms, `covers_none` never read as a requirement id; `conventions.md` is written through a convention drop, not by hand.
- **Code review:** approve with fixes. Fixed: a renamed-and-edited stand-in slipped the correction rule (now `_refuse_quiet_loss`); a manifest-linked test is never infrastructure (defence beyond the parser); fixture trees cannot keep a requirement; move matching prefers the same name and is used up. AC55 wording corrected for the module-level marker.
- **Doubt review:** the core claim held. Fixed: an untouched, already honoured infra test is not refused for an unrelated retirement; a test added beside a module-level marker needs its own marker; a repo test requires every committed `covers_none` file to be in the catalog. Disclosed: the merge-base resolver can fall back to the branch upstream when `origin/HEAD` is unset (shared by every F11 gate).

## External Code Review (GPT via codex, GLM via openrouter)
- **Verdicts:** openai=revise, glm=approve.
- openai/medium - destructured or conditional `pytestmark` hid a `covers` mark: fixed (such a form refuses the grant).
- openai/medium - an unreadable base catalog continued silently: fixed (the gate stops with `cannot enforce`).
- openai/medium - the head-catalog check accepted any `.py` path: fixed (entries must be test files; production modules refused).
- glm/low - the correction warning survived a demotion: fixed (retracted). glm/low - sibling reason masked by the module-marker reason, and one case asserted only at parser level: noted / one case routed through `evaluate`. glm/low - catalog not seeded here: disclosed, follow-up merge.
