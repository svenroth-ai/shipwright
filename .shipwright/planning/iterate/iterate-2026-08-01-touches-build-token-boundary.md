# Iterate Spec: touches-build-token-boundary

- **Run ID:** iterate-2026-08-01-touches-build-token-boundary
- **Type:** bug
- **Complexity:** small
- **Status:** draft

> Written although `small` does not buy an iterate spec. The trigger asked for
> the trade-off below to be stated in the spec, so the spec exists to carry it.

## Goal

Make the two surfaces of the **one** `touches_build` taxonomy entry agree on
what counts as naming a build input. The message-keyword surface matched a bare
substring for every JS entry, so `my-package.json` and `package.json.bak` raised
the flag from a prompt while the diff-driven detector deliberately refuses
exactly those.

## Root cause

`iterate-2026-07-31-it5-classification-calibration` (#506) added token guards to
the Python patterns *it was introducing* — an external review had found that a
bare `\b` is not a filename boundary, because `.` satisfies it. The pre-existing
JS patterns, which never carried any guard, were not retrofitted in that change
and no test looked at them. Result: one entry, two matching rules.

Measured before the fix: for **21 of 21** JS entries in
`TOUCHES_BUILD_FILE_PATTERNS` a disagreeing string exists (`my-package.json`,
`package.json.bak`, `next.config.ts.bak`, …); over the 15 hand-written probe
strings used for the first measurement, 15 of 15 disagreed.

**Two populations, so "0 disagree now" needs its scope stated.** "After" is
measured over the two probe families this change is about — `my-{name}` and
`{name}.bak` — for every tuple entry, plus the named cases. It is *not* a claim
that no string exists on which the surfaces differ, and this change knowingly
creates one class of those: the trailing-punctuation relaxation makes
`pyproject.toml.` (and seven siblings) fire from a message, while
`touches_build_files(["pyproject.toml."])` is `False`. That is the intended
prose-vs-path distinction — a diff never contains a path ending in a sentence
period — but it is a literal-token divergence and is listed here rather than
left for the next reader to discover.

The same change also wrote a comment in `risk_detectors.py` asserting that "the
two surfaces agree on whole-filename matching … asserted, not assumed", citing a
test that covers only the Python half. The claim was true of the half it was
written next to and false of the entry as a whole.

## The trade-off (why this is worth doing anyway)

**This fix NARROWS classification, which is the less-safe direction for a gate.**
Over-firing costs a spurious `small` floor plus a review trigger — never a missed
one. That is why the finding was filed `low`, and the argument has to clear that
bar rather than assume it.

It clears it for two reasons:

1. **The diff surface already returns `False` for these strings**, pinned by
   `test_touches_build_files_does_not_match_partial_basename`. The narrowing does
   not invent a new judgement; it propagates one this repo already made and
   defends with a test.
2. **Two halves of one entry disagreeing is the worse bug.** Which verdict a
   change gets depends on which surface happened to see it — Stage 1 reads the
   message, Step 3.4 and the F11 verifiers read the diff. A flag whose meaning
   depends on the observer cannot be reasoned about, and the disagreement grows
   silently with every entry added to one half.

**What the narrowing costs, stated exactly.** An earlier version of this section
claimed "the true-positive set is unchanged". That was false, and the Stage-3
doubt pass refuted it with a case the run had already dismissed once: under an
intermediate `(?![\w-])` guard, `a package.json-only bump` — which fired before
this change — raised **nothing at all**, losing the `small` floor, the
performance layer and (per `iteration-reviews.md`, "When Self-Review is
Sufficient") the full-code-review trigger. A gate standing down on a real
dependency change is precisely the unsafe direction this spec sets as its bar.

The guard was corrected rather than the claim: `-` is out of the trailing class
(`(?!\w)(?!\.\w)`), so hyphen compounds fire again. What the change now costs is
bounded and enumerated:

- **Lost:** nothing that fired before and names a build input.
  `test_every_detector_entry_also_fires_from_a_message` asserts the per-entry
  half; `test_a_build_input_in_a_hyphen_compound_still_fires` and
  `test_a_build_input_ending_a_sentence_still_fires` assert the two positions a
  single end-of-string probe cannot reach.
- **Also lost, deliberately:** `touches_build` on the five bare config stems.
  Those prompts still raise `touches_middleware` — same `small` floor, same
  mandatory review — so what actually goes is the `performance_test_layer`
  enforcement, which is correct for a string that names no build file.
- **Gained (safe direction):** sentence-final and hyphen-compound references
  now fire where the shipped Python guard suppressed them, and the
  `requirements*.txt` family now matches the same alphabet on both surfaces.

**"Parity" here means whole-filename matching, not an exhaustive enumeration.**
The config families are written `next\.config\.\w+` — *an* extension, not the
specific literals the tuple carries. Those sets differ per family with no
evident rule (`next` {js,ts,mjs,cjs}, `vite` {js,ts,mjs}, `rollup` {js,ts,mjs},
`tailwind` {js,ts}, `webpack` {js,ts}), which is itself the argument against
enumerating them here: the message surface would inherit five accidental-looking
allowlists and drift from them silently. So `next.config.foo` still fires from a
message where the diff surface would not. That residue is strictly
pre-existing — the replaced `next\.config\.` matched it and much more. Written
down so nobody later reads "the two surfaces agree" as stronger than it is.

**One narrowing was found and refused.** Copying the shipped guard verbatim would
have used the symmetric `(?![\w.-])`, which rejects *any* following `.` —
including sentence punctuation. Measured on the shipped Python half:

```
'add a dependency to pyproject.toml.'  -> False     # trailing period
'add a dependency to pyproject.toml'   -> True
```

That is a false **negative** on a risk gate — the unsafe direction — and
extending it to `package.json` would have spread it to the most common build
file there is. The trailing guard is therefore `(?!\w)(?!\.\w)`: it rejects a
directly appended token (`setup.python`) and a further extension
(`package.json.bak`), and leaves everything else — sentence punctuation, a
compound hyphen, a comma, a backtick — alone. This *widens* the shipped Python
behaviour. Doing it in this change rather than deferring it is deliberate: it is
the same guard token, and shipping the narrowing without it would have knowingly
introduced the false negative.

The intermediate `(?![\w-])` — which kept `-` in the class — is what Stage 3
refuted, because it answered the identical question the opposite way for `-` as
for `.`. Both are now resolved by one rule: **a following character either
continues the name or extends it, or else it is prose.**

## Acceptance Criteria

- [x] AC-1 — For every entry in `TOUCHES_BUILD_FILE_PATTERNS` (+ each glob
      family instance), `my-{name}` raises `touches_build` on **neither**
      surface.
- [x] AC-2 — For every such entry, `{name}.bak` raises it on **neither** surface.
- [x] AC-3 — For every such entry, the plain name still raises it on **both**
      surfaces (no true positive lost).
- [x] AC-4 — For every such entry, a message ending `… {name}.` still raises it
      (a trailing period is punctuation, not an extension).
- [x] AC-5 — Every pattern in the entry carries the **whole** constructed guard
      (leading *and* trailing), so a message-only pattern with no tuple
      counterpart cannot skip either half.
- [x] AC-6 — The config families **require** an extension, matching the diff
      surface's extensioned literals: `next.config.ts` fires on both surfaces,
      bare `next.config` fires on **neither**, `next.configuration` does not
      fire, `my-next.config.ts` does not fire.
- [x] AC-7 — The deliberate case asymmetry between the surfaces is preserved and
      pinned as a decision, not left to be "fixed" by the next reader.
- [x] AC-8 — For every such entry, a hyphen compound (`… {name}-only bump`)
      still raises it. A `-` is prose, exactly as a trailing `.` is; answering
      that question differently for the two characters is what cost a real true
      positive.
- [x] AC-9 — The `requirements*.txt` family accepts the same alphabet on both
      surfaces, including characters outside `[\w.-]` (`requirements#.txt`),
      since the diff side matches it with an fnmatch `*`.

## Spec Impact

- **Classification:** none
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** a defect fix inside one risk-classifier's regex
  surface. No FR describes `touches_build` matching semantics — the sync config
  maps none of the touched files, and no `spec.md` names the flag. The
  documented trigger *paths* (SKILL.md Risk Taxonomy row, `docs/guide.md`) are
  unchanged; only the substring-vs-token rule for matching them changed, and
  both docs are drift-pinned to the unchanged detector tuple.

## Stage-1 review findings (spec-reviewer, REJECT → fixed → re-reviewed)

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | high | An **undeclared widening**: writing the config families `next\.config(\.\w+)?` made five bare stems (`next.config`, `vite.config`, …) raise the flag from a message, where the replaced `next\.config\.` did not — and where the diff surface returns `False`. In a change whose thesis is parity, that created a new message trigger with **no diff-surface counterpart**. The draft defended itself with a premise about the old regex I never executed. | **accepted-and-fixed.** Verified the premise at code first (`re.search(r"next\.config\.", "edit next.config")` → `None`), then fixed at the root: the families now require an extension (`next\.config\.\w+`), rather than amending the prose to legalise the widening. AC-6 rewritten; the false claim removed from the test docstring and replaced with the measurement. Pinned by `test_a_bare_config_stem_fires_on_neither_surface` (mutation N1 → caught). |
| 2 | medium | The structural guard test asserted only `p.startswith(lead)`, so a future message-only pattern like `(?<![\w.-])cargo\.toml` would pass while still firing on `cargo.toml.bak` — the same defect one half over. | **accepted-and-fixed.** The test now asserts the whole constructed shape, both ends. Mutation N3 injects exactly that pattern and is caught by this test alone. |
| 3 | medium | `.shipwright/agent_docs/conventions.md:54` recorded the symmetric `(?![\w.-])` as standing guidance — the guard this run measured as producing a false negative. Left standing, the decision memory instructs the next agent to reintroduce the bug. | **accepted-and-fixed.** A superseding learning was added in the file's established `SUPERSEDES …` form, naming the split guard and the measurement. `check_agent_doc_budget.py` → OK. |
| 4 | low | The new test module's docstring said "15 JS build inputs" (the size of the hand-written named-case list) where the tuple's JS half is 21. | **accepted-and-fixed.** Corrected to name `TOUCHES_BUILD_FILE_PATTERNS` explicitly. |

Re-review of the corrected diff cleared findings 1-4 and raised two more, both of
the same class — an artifact claiming more than it holds:

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 5 | reject | Ledger row 7b cited `test_an_extensioned_config_file_fires_on_both_surfaces`, but the test asserted only the message surface. `CONFIG_STEMS` is a *literal* list precisely so it does not shrink when the tuple does — and half-covering wasted that: `vite.config.ts` could have been deleted from the tuple with nothing in the file failing while the message surface kept firing. | **accepted-and-fixed.** The test now asserts `touches_build_files([f"{stem}.ts"]) is True` as well, so its name and its body agree. |
| 6 | reject | `self-review.json`, which ships in this diff and which Stage 2 reads, still certified the **rejected** implementation: it named `test_a_bare_config_stem_still_fires` (a test that exists nowhere, whose name asserts what AC-6 now forbids), quoted round-1 mutation numbers as the change's evidence, and carried stale counts (152 cases / 248 + 242 lines vs. the real 157 / 282 + 248). | **accepted-and-fixed.** Rewritten against the shipped code and re-recorded with `--force` (the tool's documented path for a genuinely wrong record). Both mutation rounds are now reported, and every count was re-measured rather than copied. |
| 7 | low | The superseding learning in `conventions.md` pointed at "the 2026-07-31 `` entry" — an empty code span. The `\b` had been eaten by a Bash heredoc (a known escape-mangling failure in this environment), and ~18 entries share that date. | **accepted-and-fixed.** The target is now named in words ("the 2026-07-31 filename-boundary entry"), which no escaping can destroy. |

A third round then PASSed with three non-blocking accuracy nits (a 21-vs-12
noun mismatch in the new `conventions.md` line, an incomplete per-family
extension enumeration, and a per-entry-vs-per-classification slip in the
self-review's performance note) — all fixed rather than shipped, since they are
the same class as findings 5 and 6.

## Stage-2 review findings (code-reviewer)

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 8 | medium | **A latent bug in the fix itself.** `_filename_token` interpolated its argument ungrouped, and `\|` binds looser than the surrounding lookarounds — so `_filename_token(r"gemfile\|gemfile\.lock")` would compile with the trailing guard on one branch and the leading guard on the other, reintroducing *both* defects the helper exists to prevent. The structural test could not see it: the string still starts and ends with the guards. An alternation is the obvious way to write the Rust/Go/Ruby entries `risk_detectors` names as the deliberate next additions. | **accepted-and-fixed.** Confirmed at code first (`my-gemfile.lock` → `True`, structural check → green). The argument is now wrapped `(?:{name})`; the structural test's expected affixes include the group; and `test_the_helper_groups_its_argument` pins it behaviourally on the alternation shape. Mutation P1 → caught by 4 tests. |
| 9 | medium | `touches_middleware` carries an unguarded `next\.config`, so for the five config families the observable classification outcome is unchanged and the message/diff disagreement survives under another flag name — while the spec's Out-of-Scope rationale ("those entries match English keywords, not filenames") was false for all three entries it named. | **accepted; rationale corrected, residue pinned, narrowing declined.** The false claim is replaced with the measurement. Guarding `touches_middleware` is still declined, on a reason that survives: it is message-only, so there is no second surface to agree with. `test_a_refused_config_stem_still_raises_touches_middleware` makes the residue a recorded decision. |
| 10 | low | A trailing `-` is ambiguous for the same reason a trailing `.` is (`package.json-only`), and got none of the analysis the `.` case got. | **accepted-and-measured; no code change.** Measured: `package.json-only` and `package.json-old` are `False` on **both** surfaces — so cross-surface parity, the property this change is about, holds. The residue the reviewer describes is between a message's phrasing and the diff it refers to, which no guard can close. Keeping `-` strict is also the parity-consistent choice, since the diff surface refuses `package.json-old`. |
| 11 | low | The new module re-implemented four assertions that already exist in two sibling test files, and nothing stated which file owns what. | **partially accepted.** A "Division of labour" block now names all four files and their subjects. The suggested deletion of `test_python_input_fires_on_both_surfaces` from a sibling drift file is **declined**: removing tests from a file unrelated to this defect is a refactor wearing a fix label, and the redundancy is cheap insurance in the direction of more coverage. |
| 12 | low | Review-process narration (the rejected draft) shipped three times in source comments and test docstrings, which the spec already carries — against this repo's own "a record of finished work is deleted" rule. | **accepted-and-fixed.** Trimmed in `risk_taxonomy.py`, `risk_detectors.py` and the test docstrings to the load-bearing sentence. That trim, plus the split below, is what kept both test modules under the 300-line limit. |

## Stage-3 review findings (doubt-reviewer) + external cascade

The adversarial pass raised 8 doubts, refuting 7. It had no shell, so every
verdict was traced by hand and flagged as needing a probe — each was verified
before being accepted.

| # | Sev | Doubt | Disposition |
|---|---|---|---|
| 13 | **high** | **The narrowing lost a real true positive.** `a package.json-only bump` fired `touches_build` before this change and raised **nothing** after it — no `small` floor, no performance layer, and no full-code-review trigger. My Stage-2 disposition had dismissed this exact case with the wrong argument ("parity holds, because `touches_build_files(['package.json-only'])` is `False`") — comparing a prose token against the diff surface, when the diff of such a change contains `package.json`, on which it returns `True`. The same diff answered the identical question ("is this character part of the filename or the sentence?") one way for `.` and the other for `-`. | **accepted-and-fixed.** Verified first (`before=True`, `now=[]`). `-` removed from the trailing class: `(?!\w)(?!\.\w)`. Hyphen compounds fire again; `package.json-old` also fires, which is over-firing — the direction this spec's own tie-breaker prefers. Pinned by `test_a_build_input_in_a_hyphen_compound_still_fires` (29 params × 2). Mutation Q1 (reinstate the hyphen rejection) → caught by **30** tests, having been caught by **zero**. |
| 14 | medium | "0 untested-testable" was false: the trailing-hyphen decision, taken in this diff, had no test and no ledger row — while the two other declined-narrowing decisions each got both. And no mutation probed it. | **accepted-and-fixed.** The decision changed *and* is now pinned behaviourally; ledger row added; mutation Q1 added to the round-4 set. |
| 15 | medium | `self-review.json` certified the pre-Stage-2 implementation again — "157 cases" against the shipped 164 (exactly the two tests Stage 2 added), "the new test file 282" where the split produced two files, stale line counts, and no mention of the non-capturing group. Independently found by the external reviewer. | **accepted-and-fixed.** Root cause is ordering: I recorded the self-review before the later stages changed the code. It is now regenerated **last**, after every code change, and the numbers re-measured rather than carried. |
| 16 | medium | "The observable classification outcome is unchanged" for the config families is false at code: `touches_build` enforces `performance_test_layer`, `touches_middleware` does not. | **accepted-and-fixed.** Claim corrected in the spec, the disposition and the test docstring; the test now asserts the enforcement difference instead of implying it away. |
| 17 | low | The `21 of 21` and `15/15` before-measurements use different populations, and the change creates 8 new literal-token divergences (`pyproject.toml.` fires from a message, not from a diff) that the residue paragraph did not list. | **accepted-and-fixed.** Both populations are now named in Root Cause, and the punctuation divergence is listed with its rationale. |
| 18 | low | `reviews.json` records the spec gate with `findings_count: 0` although Stage 1 rejected twice and raised 7 findings across rounds. | **accepted-and-fixed.** The round-3 citations are recorded in the machine-readable payload and the row re-recorded, so the record reflects the review that happened. |
| 19 | low | `test_a_config_stem_is_not_matched_inside_a_longer_word`'s docstring overcredited it — its first assertion also passes under the reverted draft. | **accepted-and-fixed.** Docstring now says which guard refuses which case, and which test actually pins the required dot. |
| — | none | C3 (the extension half of the trailing guard) **SURVIVED** the disproof attempt: `package.json.bak`, `next.config.js.bak`, `pipfile.locked`, `requirements-dev.txt.bak`, `setup.pyc`, `package.json5` all correctly refused, including through every backtracking path. | no action |

**External cascade** (`external_review.py --mode code`, 2 providers, not
degraded): gemini `approve`; openai `revise` with one medium neither internal
stage found —

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 20 | medium | **The glob family used different alphabets on the two surfaces.** The diff side matches `requirements*.txt` with `fnmatch`, whose `*` accepts any character; the message side used `requirements[\w.-]*\.txt`. Verified: `requirements#.txt`, `requirements+extra.txt` and `requirements@dev.txt` were `diff=True, message=False` — the run's own defect class, one alphabet over. The derived tests could not see it, because `_GLOB_INSTANCES` substituted exactly one fill, which happened to be inside the narrow class. | **accepted-and-fixed.** Fragment widened to `requirements[^\s/\\]*\.txt` (whitespace and separators still excluded, so it cannot run across a sentence or swallow a directory — verified against the existing prose false-positive guards). `test_the_glob_family_accepts_the_same_alphabet_on_both_surfaces` varies the fill across 8 values, four of them outside `[\w.-]`. |
| 21 | low | Same stale-`self-review.json` finding as #15. | fixed, as above |

**File split (300-line rule).** The parity module crossed 300 lines while these
findings were being addressed. It is now two modules along the seam the
docstring already described: `test_touches_build_surface_parity.py` (285 lines)
asserts agreement between the surfaces entry by entry;
`test_touches_build_guard_construction.py` (156 lines) covers how the guard is
built and the two limits this change declares.

## Out of Scope

- **Making the message surface case-sensitive.** The surfaces also disagree on
  case: the diff half is `fnmatchcase` by decision (a gate must not depend on
  the developer's OS), the message half lowercases the whole prompt for *every*
  flag in the taxonomy. Aligning that would be a narrowing in the unsafe
  direction for a divergence that costs nothing — a human writing "Package.json"
  in a sentence means the file. Pinned as intended in
  `test_the_two_surfaces_deliberately_disagree_on_case` rather than changed.
- **Other taxonomy entries — including `touches_middleware`, which carries an
  unguarded `next\.config` and therefore mutes this narrowing in practice.**
  Measured: `detect_risk_flags("rename my-next.config.ts")` still returns
  `touches_middleware`, so for the five config families the *observable*
  classification outcome — `small` floor plus mandatory review — is unchanged
  by this diff. It narrows `touches_build`; it does not make those prompts
  classify as unremarkable, and the ledger must not be read as claiming so.
  (An earlier draft of this section asserted these entries "match English
  keywords, not filenames". That is false and was corrected: `touches_auth`
  carries `middleware\.ts` and `supabase/.*auth`, `touches_public_api` carries
  `route\.ts`.) They are still out of scope, for a reason that survives the
  correction: each is a **message-only** flag with no diff-driven counterpart,
  so there is no second surface to agree with and thus no parity argument for
  narrowing it — and over-firing there is the safe direction. Pinned as a
  recorded decision by `test_a_refused_config_stem_still_raises_touches_middleware`,
  so guarding `next\.config` later is a choice made with the residue in view.
- Adding build inputs for ecosystems nobody has measured here (Rust/Go/Ruby/PHP)
  — deliberately absent, per the detector's own comment.

## Affected Boundaries

n/a — no serialized format is produced or consumed by this change. `is_io_boundary_change`
returns `False` for the changed file set; the diff is regex literals, a helper,
comments and tests.

## Confidence Calibration

- **Boundaries touched:** none (see above).

- **Empirical probes run:**
  - Cross-surface disagreement table over 15 realistic partial filenames, before
    the fix — **15/15 disagreed** (message `True`, diff `False`). After the fix,
    **0/15**.
  - Trailing-period probe on the *shipped* Python guards — `pyproject.toml.`,
    `uv.lock.`, `requirements.txt.`, `setup.cfg.` all returned `False`. This is
    what redirected the fix away from copying the guard verbatim.
  - Prior-regex premise check, run **because Stage 1 disputed it**:
    `re.search(r"next\.config\.", "edit next.config …")` → `None`, and
    `touches_build_files(["next.config"])` → `False`. Both refuted the draft's
    justification and redirected the fix.
  - Mutation probes, round 1 (six, against the first implementation): caught by
    40/39/23/29/1/5 tests. The `1` result is what exposed that the config-family
    shape rested on a single test — the thread Stage 1 then pulled.
  - Trailing-hyphen probe (Stage-2 finding 10): `package.json-only` and
    `package.json-old` are `False` on BOTH surfaces — cross-surface parity
    holds; the guard's two halves were each measured, not just the `.` half.
  - Alternation probe (Stage-2 finding 8), run before fixing: an ungrouped
    `gemfile|gemfile\.lock` matched `my-gemfile.lock` and `gemfile.bak`, while
    the structural token-guard check stayed green — confirming both the bug and
    the test's blind spot.
  - Mutation probes, round 2 (six, against the first corrected implementation):
    reinstate the optional extension **(the exact draft Stage 1 rejected)**,
    drop the required dot, add a message-only pattern carrying the leading guard
    only, drop the trailing extension guard, revert to the symmetric guard,
    unguard one JS entry → caught by **1 / 11 / 1 / 40 / 35 / 5** tests. All six
    caught; `risk_taxonomy.py` restored byte-identical after each.
  - Mutation probes, round 3 (seven, against the final implementation, run
    across both test modules): ungroup the helper argument, reinstate the
    optional config extension, drop the trailing extension guard, revert to the
    symmetric guard, unguard one JS entry, add a message-only pattern carrying
    the leading guard only, drop the leading lookbehind → caught by
    **4 / 2 / 42 / 35 / 5 / 1 / 42** tests. All seven caught;
    `risk_taxonomy.py` restored byte-identical after each.
  - Hyphen-regression probe (Stage-3 finding 13), run before accepting it:
    `a package.json-only bump` → fired under the pre-change bare pattern,
    `risk_flags=[]` under the intermediate guard. Confirmed the false negative
    rather than trusting the report, which had no shell.
  - Glob-alphabet probe (external finding 20): `requirements#.txt`,
    `requirements+extra.txt`, `requirements@dev.txt` measured `diff=True,
    message=False` before the fix, and the candidate fragment was checked
    against the existing prose false-positive guards before being applied.
  - Mutation probes, round 4 (seven, against the final implementation):
    reinstate the hyphen rejection, ungroup the helper argument, drop the
    extension guard, revert to the symmetric guard, drop the leading
    lookbehind, make the config extension optional, unguard one JS entry →
    caught by **30 / 4 / 42 / 64 / 42 / 2 / 5** tests. All seven caught;
    `risk_taxonomy.py` restored byte-identical after each.
  - Full plugin suite: 898 passed, 4 skipped (201 in the two new modules).
    Integration: 439 passed, 7 deselected. `uvx ruff@0.15.15 check .`: clean.

- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | A prefixed token (`my-{name}`) fires on neither surface, for every detector entry | tested | `test_a_prefixed_build_input_fires_on_neither_surface` — 29 params PASSED |
  | 2 | A suffixed token (`{name}.bak`) fires on neither surface, for every detector entry | tested | `test_a_suffixed_build_input_fires_on_neither_surface` — 29 params PASSED |
  | 3 | The 15 named JS partial tokens from the finding do not fire | tested | `test_named_js_partial_tokens_do_not_fire` — 15 params PASSED |
  | 4 | Every detector entry still fires from a message (no true positive lost) | tested | `test_every_detector_entry_also_fires_from_a_message` — 29 params PASSED |
  | 5 | A build input ending a sentence still fires | tested | `test_a_build_input_ending_a_sentence_still_fires` — 29 params PASSED |
  | 6 | Path separators, backticks and trailing punctuation still fire | tested | `test_ordinary_prose_around_a_build_input_still_fires` — 6 params PASSED |
  | 7 | A bare config stem (`next.config`) fires on neither surface | tested | `test_a_bare_config_stem_fires_on_neither_surface` — 5 params PASSED |
  | 7b | An extensioned config file still fires on both surfaces, incl. sentence-final | tested | `test_an_extensioned_config_file_fires_on_both_surfaces` — 5 params PASSED; asserts `touches_build_files` **and** the message surface, so the literal `CONFIG_STEMS` list guards both halves against a tuple shrink |
  | 8 | A config stem is not matched inside a longer word (`next.configuration`) | tested | `test_a_config_stem_is_not_matched_inside_a_longer_word` — 5 params PASSED |
  | 9 | Every message pattern carries the WHOLE constructed guard, both ends | tested | `test_every_message_pattern_is_token_guarded` PASSED; mutation N3 (leading guard only) caught by this test alone |
  | 10 | The case asymmetry between surfaces is preserved | tested | `test_the_two_surfaces_deliberately_disagree_on_case` — 3 params PASSED |
  | 11 | The derived parameter set holds literal filenames, not un-instantiated globs | tested | `test_glob_instances_are_literal_filenames` PASSED |
  | 12 | The `risk_detectors.py` parity comment now describes the whole entry, and `conventions.md`'s guard guidance is superseded rather than left to reinstate the bug | untestable | requires-manual-visual-judgment — prose claims about scope and decision memory; the properties they assert are pinned by rows 1-5 and 9, and `check_agent_doc_budget.py` passes |
  | 13 | An alternation in a name fragment cannot escape the guards (`_filename_token` groups its argument) | tested | `test_the_helper_groups_its_argument` — 5 params PASSED; mutation P1 (ungroup) caught by 4 tests |
  | 14 | A config stem this change refuses for `touches_build` still raises `touches_middleware` — same floor and review, but NOT the performance layer | tested | `test_a_refused_config_stem_still_raises_touches_middleware` — 2 params PASSED; asserts the enforcement difference, not just flag membership |
  | 15 | A build input inside a hyphen compound (`package.json-only`) still fires | tested | `test_a_build_input_in_a_hyphen_compound_still_fires` — 29 params PASSED; mutation Q1 caught by 30 tests (previously 0) |
  | 16 | The `requirements*.txt` family accepts the same alphabet on both surfaces, incl. characters outside `[\w.-]` | tested | `test_the_glob_family_accepts_the_same_alphabet_on_both_surfaces` — 8 fills PASSED, 4 outside the old class |

  0 untested-testable.

- **Confidence-pattern check:**
  - *Asymptote (depth):* yes, three times — so the extra probes were run rather
    than the confidence trusted. (1) The trailing-period probe overturned the
    obvious fix (copy the shipped guard verbatim). (2) Re-reading the ledger
    surfaced behaviour no test pinned; the mutation probe then showed that
    mutation had **zero** coverage. (3) Stage-1 review rejected the fix that had
    already passed my own self-review and 152 green tests, on a premise about
    the prior regex I had asserted without executing. Each was found by probing
    or by an independent reader — none by re-reading my own diff, which is the
    pattern this section exists to distrust.
  - *Coverage (breadth):* 17 rows, 16 `tested`, 1 `untestable` with a
    closed-vocabulary reason code, 0 untested-testable. The derived rows are
    keyed on the detector's own SSoT tuple rather than a hand-written list, so a
    build input added tomorrow inherits rows 1-5 without anyone remembering.
  - *Integration composition:* n/a — `is_cross_component_change` returns `False`
    for this diff (verified at Quick Scout and re-verified at Step 3.4).
