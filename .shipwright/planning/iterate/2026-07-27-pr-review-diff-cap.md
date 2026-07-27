# Iterate: PR-Review diff cap — raise, cut at a file boundary, name what went unreviewed

- **Run ID:** `iterate-2026-07-27-pr-review-diff-cap`
- **Intent:** CHANGE
- **Complexity:** medium (`prior_source: history`, n=20; scope keyword said `trivial`)
- **Spec Impact:** **NONE** — the Tier-3 PR review gate is CI/delivery machinery
  (B4.5 automerge), not a product requirement. No `spec.md` in
  `.shipwright/planning/*/` mentions the gate, Tier-3, or its diff-size
  behaviour (verified by grep), so there is no requirement text to update.

## Problem

The Tier-3 `PR Review` required check cannot review a large change. It cuts the
diff at `MAX_DIFF_CHARS = 200_000` with a bare `diff[:max_chars]` slice and then
fails closed, because a partial review must never let a big diff bypass the gate
by size.

Three separate defects sit on top of each other:

1. **The cap is stale.** It predates the current context window. The review model
   is `anthropic/claude-sonnet-4.6` via OpenRouter; querying OpenRouter's model
   list returns `context_length=1000000`, `max_completion_tokens=128000`. At
   200,000 characters the reviewer uses ~50k tokens — 5% of what it can hold.
2. **The cut lands mid-hunk.** A naked character slice ends the diff wherever the
   200,000th byte falls, so the reviewer's last file is syntactically broken. It
   is asked to judge a fragment it cannot parse.
3. **The failure says the wrong thing.** The gate reports *"Diff truncated at
   200,000 characters"* — a fact about bytes. What a human needs is *which files
   nobody looked at*.

**Measured this session.** PR #447 carried 812,610 characters raw; the
generated-artifact filter removed 37 files (42%), leaving 467,591 — still 2.3×
the cap. Four review rounds had already run and the fourth still found a real
bug, yet the gate could not see the change. It was split into three PRs (#456,
#457, #458) to get it merged.

## Decision

| # | Change | Value |
|---|---|---|
| 1 | Raise the cap | `MAX_DIFF_CHARS = 1_000_000` **characters** |
| 2 | Cut at a `diff --git` boundary | every file in the reviewed diff is complete |
| 3 | Name the unreviewed files | to the model (PR meta) and to humans (comment) |

**On the value.** 1,000,000 characters ≈ 250k tokens ≈ a quarter of the window,
and a factor 2 over the largest diff ever measured here. At $3/1M input that is
~$0.75 for a worst-case review. 2,000,000 was considered and rejected: it buys
reserve the data does not call for, and a diff past 1,000,000 characters is a
split candidate — there, failing closed is the correct answer, not a false alarm.

**The unit is characters, not tokens.** Entering "500,000" for 500k tokens would
raise the cap by 2.5×, not 10×.

## Acceptance Criteria

- **AC1** — A diff up to 1,000,000 characters (after the generated-artifact
  filter) is reviewed in full instead of failing closed.
- **AC2** — When the diff is over the cap **and at least one whole file section
  fits**, every file section in the reviewed diff is complete: the reviewed diff
  does not end mid-hunk. AC6 is the one named exception.
- **AC3** — When the diff is over the cap, the affected files are named to the
  model (PR meta) and to humans (PR comment), and the two cases are
  distinguished: **omitted** (no content reviewed) vs **partially included**
  (content supplied as context, not reviewed in full).
- **AC4** — The gate fails closed on an incomplete review. The signal is
  authoritative and independent of the path list: a diff whose files could not be
  identified at all still fails closed. The file list is explanatory metadata,
  never the pass/fail predicate.
- **AC5** — A diff with no parseable `diff --git` header still truncates, still
  fails closed, and says plainly that the affected files could not be identified.
  A parse surprise never blanks the review nor silently passes it.
- **AC6** — A single file section larger than the whole cap still produces a
  non-empty reviewed diff, and that file is reported as **partially included** —
  never as reviewed.
- **AC7** — The reviewed diff is never longer than the cap, for **any** input,
  including a diff whose preamble alone exceeds it.

## Affected Boundaries

- `plugins/shipwright-security/scripts/lib/pr_review_diff_filter.py` — the diff
  parsing cluster. Gains the boundary-aware truncation.
- `plugins/shipwright-security/scripts/lib/pr_review_lib.py` — owns the cap
  constant and the comment rendering. `truncate_diff` changes contract (tuple →
  record) and the comment gains the two file lists.
- `plugins/shipwright-security/scripts/tools/pr_review.py` — the caller. Passes
  the unreviewed list through to meta / comment / stderr.
- **CI trust boundary: untouched.** `.github/workflows/pr-review-run.yml` invokes
  the script with no size flag, so no workflow file is in the diff and
  `touches_ci_supplychain` stays clear.

## Out of scope (deliberate)

- **The WebUI's vendored copy.** `shipwright-webui` runs its own vendored
  `pr_review`; a monorepo change does not reach it. That needs a separate webui
  iterate and must not be edited from here.
- **Chunking the diff across several LLM calls.** Considered and deferred
  (YAGNI). After the raise, a PR would have to be twice the largest work unit
  ever measured to truncate at all. A hand-run naive chunking attempt this
  session produced systematically bogus findings — a docs-only chunk reported
  "the implementation is missing" four times, because the implementation was in
  another chunk. Doing it properly needs a shared context header per chunk. No
  triage item: we watch, and revisit if the new cap is ever hit.

## Size constraints (checked before planning)

No `pr_review*` file has a `shipwright_bloat_baseline.json` entry, so every one
is under the 300-line limit with no grandfathering. Headroom is tight in two
places and drives where the code goes:

| File | Lines | Headroom |
|---|---|---|
| `scripts/tools/pr_review.py` | 294 | **6** |
| `tests/test_pr_review_script.py` | 291 | **9** |
| `tests/test_pr_review_lib.py` | 233 | 67 |
| `scripts/lib/pr_review_lib.py` | 208 | 92 |
| `tests/test_pr_review_filter.py` | 153 | 147 |
| `scripts/lib/pr_review_diff_filter.py` | 128 | 172 |

New logic therefore lands in `pr_review_diff_filter.py` and new tests in
`test_pr_review_filter.py`. The caller change stays within its 6 lines.

## Known landmine (verified before build)

`tests/test_pr_review_filter.py::test_filtering_lets_a_big_diff_fit_under_cap`
builds a fixed ~360,000-character fixture (`"+x\n" * 120_000`) and asserts
`len(diff) > MAX_DIFF_CHARS`. Raising the cap makes that assertion false. The
fixture must derive its size from the constant instead of hard-coding it.
The three `TestTruncation` cases in `test_pr_review_lib.py` unpack a 2-tuple and
must follow the new arity. Every other test references the constant symbolically.

## Mini-Plan

### Shape

`pr_review_diff_filter.py` already owns the `diff --git` boundary: the regex,
`_section_paths()`, and an inline splitter inside `filter_generated_paths()`.
Step 1 extracts that splitter into `_split_sections(diff) -> (preamble, sections)`
and re-uses it from both callers, so the definition of "a file boundary" is
single-sourced. Then:

```python
@dataclass(frozen=True)
class ReviewedDiff:
    text: str                  # what the model sees; ALWAYS <= max_chars (AC7)
    incomplete: bool           # AUTHORITATIVE fail-closed signal (AC4)
    omitted: tuple[str, ...]   # files with no content in `text`
    partial: tuple[str, ...]   # files present but cut (AC6 only)

truncate_diff_at_boundary(diff, max_chars) -> ReviewedDiff
    # in pr_review_diff_filter.py — max_chars REQUIRED (no import of the constant)

truncate_diff(diff, max_chars=MAX_DIFF_CHARS) -> ReviewedDiff
    # in pr_review_lib.py — thin wrapper keeping the public name + the default
```

A record rather than a widening tuple: the caller reads `.incomplete` for the
gate and the two lists for the message, so no call site can silently pick up the
wrong positional element as the contract grows.

Algorithm — four branches, each ending under the cap:

```
len(diff) <= max_chars          -> whole diff, incomplete=False
no parseable `diff --git`       -> diff[:max_chars], incomplete=True, no paths   (AC5)
preamble alone >= max_chars     -> preamble[:max_chars], every path omitted      (AC7)
otherwise                       -> preamble + every section that fits the
                                   remaining budget, in order; paths of the
                                   rest -> omitted                          (AC2)
   ...and only if NO section fit -> (preamble + first section)[:max_chars],
                                   that file -> partial                     (AC6)
```

**Classification invariant.** Every section ends up in exactly one state —
*fully included*, *omitted*, or *partial*. **At most one section is ever
partial**, and only when not a single section fits; otherwise `partial` is empty.
So a 2 MB file sitting next to a 100-byte file yields: small file reviewed in
full, big file `omitted`, nothing `partial`. That is D2 doing its job — reviewing
whole files beats handing over a fragment — and it means AC6 is reachable only
for a diff whose *every* section is over-cap. Both reviewers flagged this as
ambiguous in round 1's wording; the behaviour was always intended, the sentence
was not precise.

**Paths that cannot be parsed.** `_section_paths()` returns nothing for header
forms it does not recognise (Git quotes paths containing spaces or non-ASCII).
An omitted section like that would silently not appear in the list. The count of
dropped sections is therefore tracked separately, and any shortfall is reported
as "+N file(s) whose path could not be identified" — an under-reported list must
never read as a complete one. `incomplete` is unaffected either way.

**`incomplete` is `True` in every branch past the first**, by construction, not
by inspecting the path lists. That is the whole point: a malformed oversized diff
yields no paths at all and must still fail closed.

### Design decisions, each with the option not taken

**D1 — the logic lives in `pr_review_diff_filter.py`, not `pr_review_lib.py`.**
That module is already "the diff-parsing cluster"; putting boundary truncation
anywhere else splits one piece of knowledge across two files. The constant stays
in `pr_review_lib`, and the filter function takes `max_chars` as a required
argument, so the existing dependency direction (lib → filter) is preserved and no
import cycle appears.
*Alternative:* keep truncation in `pr_review_lib` and import `_section_paths`
from the filter. Rejected — it inverts the dependency and leaves the boundary
definition in two places.

**D2 — a section that does not fit is skipped, not treated as a stop signal.**
The walk continues, so smaller files after a huge one still get reviewed.
*Alternative:* stop at the first overflow, making the reviewed diff a true prefix
of the real one. Simpler to describe, but reviews strictly less. Rejected because
the honesty of this design comes from **naming** what was dropped, not from the
kept part being contiguous — once the dropped files are listed, reviewing more of
the rest is a free win.

**D3 — a single file bigger than the whole cap still yields a non-empty diff,
and is labelled `partial`, not `omitted`.** If not even the first section fits,
fall back to a character-truncated copy of it. This is the *one* place the diff
ends mid-hunk, so it is called out in AC2, tracked in its own list, and described
to both the model and the reader as context supplied — never as a file reviewed.
*Alternative:* return an empty diff. Rejected — it spends an LLM call on nothing
and invites a hallucinated verdict on an empty input, while the gate fails closed
in both designs. Giving the reviewer the first megabyte of the offending file is
strictly more useful than giving it nothing.

**D5 — `incomplete` is the fail-closed predicate; the path lists are only
explanation.** The gate asks one question: *did we see the whole change?* That is
answered by construction in the truncation branch, never by testing whether the
lists are non-empty. Three inputs make the difference concrete: a malformed
oversized diff (no paths discoverable), an oversized preamble, and a future
parser defect — under a list-driven predicate each one reads as "nothing was
dropped" and **passes a gate it should fail**.
*Alternative:* derive the gate from `omitted or partial`, which reads more
directly. Rejected — it fails open exactly where the parser is least trustworthy.

**D4 — `truncate_diff` returns a record instead of a tuple, and does not gain a
sibling.** This is a contract change, not a widening of arity: positional
unpacking stops working entirely, which is the point — a caller that still says
`a, b = truncate_diff(...)` fails loudly instead of quietly binding the wrong
element. Consumers are located by grep across the repo, not from memory. Nothing
outside this plugin imports it (the WebUI vendors its own copy).
*Alternative:* add `truncate_diff_v2` and leave the old one. Rejected — that is
precisely how the old byte-slice would survive by accident and get called from
somewhere later.

### Steps

1. `_split_sections()` extracted in `pr_review_diff_filter.py`;
   `filter_generated_paths` re-pointed at it. **No behaviour change** — the
   existing filter tests must stay green untouched.
2. `ReviewedDiff` + `truncate_diff_at_boundary()` added there; `__all__` updated.
3. `pr_review_lib.py`: cap → `1_000_000`; `truncate_diff` becomes the defaulted
   wrapper; `render_comment` names omitted and partial files separately.
4. `build_pr_meta` gains the same two lists so the **model** is told what it is
   not seeing — the transparency rule the generated-file exclusion already
   follows. Both renderers reuse the existing bounded, code-formatted style
   (10 shown + "(+N more)" for humans, 30 for the model) so a PR-controlled path
   cannot inject prose into either surface.
5. `pr_review.py`: read `.incomplete` for the gate, pass the lists to meta,
   comment and stderr (≤6 lines — the file sits at 294 of 300).
6. Tests, per surface:
   - `test_pr_review_filter.py` — splitter extraction is behaviour-preserving
     (incl. a rename); boundary / omitted / partial / no-header / oversized-
     preamble / cap-invariant cases; the three mixed-size cases (over-cap first
     file followed by a fitting small one; near-cap preamble with several
     sections; partial plus further omitted); an unparseable-header omission is
     disclosed as a count; `max_chars <= 0` raises. The 360k fixture derives
     from the constant.
   - `test_pr_review_lib.py` — `TestTruncation` moved to the record;
     `build_pr_meta` carries both lists, labelled and bounded, to the model;
     `render_comment` renders both and sanitises a hostile path (backtick,
     newline, instruction-shaped text).
   - `test_pr_review_script.py` — one end-to-end case: an oversized parseable
     diff exits non-zero and the posted comment names the omitted file. Written
     compactly; the file has 9 lines of headroom.

### What could go wrong

- **A malformed oversized diff passing the gate.** The failure mode the plan
  originally had. Fixed by D5 and pinned by an explicit no-header test.
- **Silent arity break at a call site.** Mitigated by the record (named fields)
  plus the end-to-end script test.
- **A cap raise that makes an over-cap test unreachable.** Already identified —
  the 360k fixture, now derived from the constant.
- **Character-to-token ratio.** The cap is characters; the budget is tokens.
  Code diffs run ~3.5–4 chars/token, so 1,000,000 chars ≈ 250–285k tokens
  against a 1,000,000-token window — roughly 4× margin, and even a pathological
  2 chars/token stays inside. Prompt + meta overhead is a few thousand tokens.
  Not defended in code: a provider-side context rejection already surfaces as an
  OpenRouter exception → `EXIT_ERROR` → red required check, which is fail-closed.
  Documented rather than engineered, deliberately.
- **Cost.** Worst case ~$0.75/review vs ~$0.15 today, and only on PRs that would
  previously have failed the gate outright.

### External plan review — round 1 (GPT `revise`, Gemini cut off)

`gpt-5.6-terra` returned `revise` with 8 findings; `gemini-3.1-pro-preview` was
truncated by the provider (`finish_reason=length`) and so counts as
`unavailable`. Its surviving fragment independently raised the same AC2/D3
contradiction as GPT's #2, which is corroboration, not a second opinion.

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | high | No-header fallback undefined; over-cap diff could return unchanged and read as fully reviewed | **Adopted** — explicit branch, AC5, D5 |
| 2 | high | AC2 vs D3 contradiction; partial file must not read as boundary-safe | **Adopted** — AC2 scoped, `partial` list split out, AC6 reworded |
| 3 | high | Path list is not a sufficient safety predicate | **Adopted** — D5, `incomplete` is authoritative |
| 4 | med | Oversized preamble can blow the budget | **Adopted** — own branch + AC7 invariant |
| 5 | med | Splitter needs stress tests (quoted paths, renames, `diff --git` inside a hunk) | **Partially adopted** — rename + extraction-equivalence tests added. A `diff --git` line *inside* a hunk cannot false-match: every content line in a unified diff carries a `+`/`-`/space prefix, so a bare header at column 0 is always a real header. Behaviour is also unchanged by an extraction. |
| 6 | med | PR-controlled paths flow into an LLM prompt and a PR comment | **Adopted** — reuse the existing bounded, code-formatted rendering |
| 7 | med | Char→token ratio and prompt overhead not guaranteed to fit | **Documented, not engineered** — see the margin above; a context rejection already fails closed |
| 8 | low | Test the propagation at each boundary, not only the splitter | **Adopted** — per-surface test list in step 6 |

### External plan review — round 2 (GPT `revise`, Gemini cut off again)

No high-severity findings left. Gemini was truncated a second time, and again its
fragment independently raised GPT's top finding — the mixed-size classification —
which is why that one is treated as confirmed rather than as one model's opinion.

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | med | Mixed-size sections: `omitted` vs `partial` under-specified | **Adopted** — classification invariant stated above; three tests added |
| 2 | med | Nothing proves the labelled, bounded lists reach the **model** | **Adopted** — `build_pr_meta` unit test |
| 3 | med | `_section_paths` untested on quoted / non-ASCII / space-bearing headers | **Adopted in reduced form** — unparseable omissions are counted and disclosed rather than silently dropped from the list. **Not** rewriting `_section_paths`: it is pre-existing, already governs the exclusion decision, and changing it would alter what gets filtered. Out of scope for this iterate. |
| 4 | med | Code-formatting alone is not injection defence for untrusted paths | **Adopted in reduced form** — one shared sanitiser strips control characters, newlines and backticks, applied to the **existing** excluded-file list as well; the model-facing field is labelled untrusted data. Not adopting a canonical JSON encoding. |
| 5 | low | Plan calls it an arity change; it is a tuple→record contract change | **Adopted** — wording fixed below; every consumer located by grep, not by memory |
| 6 | low | `max_chars` domain unstated | **Adopted** — `ValueError` on `max_chars <= 0`, one test |

**Stopping here.** `feedback_iterations` is 1; this was round 2. The verdict is
still `revise`, but every remaining finding is medium or low and each is either
adopted above or refused with a reason. A third round would be diminishing
returns against a plan whose high-severity findings are all closed.

## Confidence Calibration

- **Boundaries touched:** the unified-diff parse boundary (`_split_sections`,
  now shared by the generated-artifact filter and the size cap); the
  `truncate_diff` contract (tuple → record); three untrusted-input sinks that
  receive PR-controlled file names (LLM prompt, PR comment, CI stderr). The CI
  trust boundary is NOT touched — no `.github/**` file is in the diff.

- **Empirical probes run:**
  - *Does the raise actually fix the case it was built for?* PR #447 measured
    **467,591 chars** after filtering. Under the old cap: truncated. Under the
    new cap: reviewed whole. The three-way split this session would not have
    been needed.
  - *Is the extraction really behaviour-preserving?* Ran the 15 pre-existing
    filter tests **unchanged, before touching anything else** — all green. That
    is evidence, not an assertion.
  - *What does the model actually accept?* Queried OpenRouter's live model list:
    `anthropic/claude-sonnet-4.6` reports `context_length=1000000`,
    `max_completion_tokens=128000`. The cap is ~25% of that.
  - *Does an oversized diff behave?* Fed a real 2,879,024-char range through the
    pipeline: 110 generated files dropped, **165 remaining files named** as
    omitted, `partial=0`, output landing exactly at the cap (~250k tokens).
  - *Does this iterate's own change fit?* 61,116 chars — reviewed whole.

- **Test Completeness Ledger** — 19 behaviours, **0 testable-but-untested**:

  | # | Behaviour | Disposition | Evidence |
  |---|---|---|---|
  | 1 | The cap covers the largest real diff measured | tested | `test_the_cap_still_covers_the_largest_real_diff_measured` — the only test that fails if the cap is lowered back |
  | 2 | A diff under the cap is returned untouched | tested | `test_a_diff_under_the_cap_is_untouched`, `test_exactly_at_the_cap_is_not_truncated` |
  | 3 | Kept sections are always whole | tested | `test_every_kept_section_is_whole_and_the_rest_are_named` |
  | 4 | An over-budget section is skipped, later fitting ones still reviewed | tested | `test_a_huge_file_is_omitted_while_a_small_neighbour_is_reviewed_whole` |
  | 5 | `partial` only when no section fits at all | tested | `test_only_when_no_section_fits_is_one_supplied_in_part` |
  | 6 | At most one section is ever partial | tested | `test_at_most_one_section_is_ever_partial` |
  | 7 | No parseable header → still fails closed, no invented paths | tested | `test_a_diff_with_no_parseable_header_still_fails_closed` |
  | 8 | Oversized preamble respects the cap | tested | `test_an_oversized_preamble_still_respects_the_cap` |
  | 9 | Output never exceeds the cap, any input | tested | `test_the_reviewed_diff_never_exceeds_the_cap` (4 cap sizes) |
  | 10 | An omission with an unparseable path is counted, not dropped | tested | `test_an_omission_whose_path_cannot_be_parsed_is_counted_not_dropped` |
  | 11 | A *partial* file with an unparseable header is disclosed too | tested | `test_a_partial_file_whose_own_header_is_unparseable_is_still_disclosed` — regression from external code review |
  | 12 | A rename reports both ends | tested | `test_a_rename_reports_both_ends_when_omitted` |
  | 13 | Non-positive cap rejected | tested | `test_a_non_positive_cap_is_rejected` |
  | 14 | The comment names omitted and partial separately | tested | `test_the_comment_names_what_went_unreviewed` |
  | 15 | Unnameable files disclosed to humans | tested | `test_files_that_could_not_be_named_are_disclosed_not_hidden`, `test_no_parseable_header_says_so_rather_than_implying_nothing_was_lost` |
  | 16 | The model is told what it is not seeing, bounded + labelled untrusted | tested | `test_the_model_is_told_which_files_the_cap_left_out`, `..._are_untrusted`, `..._bounded_and_sanitised`, `test_unnameable_omissions_reach_the_model_too` |
  | 17 | A hostile path cannot break out of comment or stderr | tested | `test_a_hostile_path_cannot_break_out_of_the_comment`, `test_an_oversized_diff_names_the_unreviewed_file_in_every_sink` (ANSI escape) |
  | 18 | The tuple→record change fails loudly at a stale call site | tested | `test_the_record_cannot_be_unpacked_like_the_old_tuple` |
  | 19 | A live OpenRouter review of a ~1M-char diff | **untestable** | `requires-external-nondeterministic-service` — needs a real provider call on a real oversized PR. The size arithmetic and the context limit are both pinned deterministically above; the live leg is what the gate itself exercises in CI. |

  `enumeration_basis`: 7 ACs, 7 covered.

- **Confidence-pattern check:**
  - *Asymptote (depth).* Two external plan rounds then one external code round.
    Round 1 returned three high-severity findings, all design defects — including
    a genuine gate bypass (a malformed oversized diff reading as fully reviewed).
    Round 2 returned no highs. The code round returned two mediums, both real
    bugs, both now fixed with regression tests. Severity fell monotonically
    across rounds, which is the shape of an approaching asymptote rather than a
    stream that was never sampled.
  - *Coverage (breadth).* Every AC has a test; every sink that receives untrusted
    input has a sanitisation test; every degenerate branch has its own case.
  - *Integration composition.* `cross_component` does **not** apply — the diff
    touches no merge/churn resolver, hook, phase validator or campaign path, so
    no integration-composition behaviour is owed. Verified against
    `CROSS_COMPONENT_FILE_PATTERNS`, not assumed.
