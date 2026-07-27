# Mini-Plan: triage defer from the terminal + failing-check detail cap

- **Run ID:** iterate-2026-07-27-triage-defer-ci-cap
- **Spec:** `2026-07-27-triage-defer-ci-cap.md`

## Chosen approach

**One shared helper per surface pair, contract frozen where another repo reads it.**

1. `shared/scripts/tools/triage_promote.py` — extract the body that `dismiss()`
   already implements (store-exists check → resolve item → reject any status
   other than `triage` → `mark_status`) into a private
   `_decide_from_triage(project_root, item_id, new_status, reason, by)`.
   `dismiss()` becomes a two-line call through it, unchanged in signature,
   defaults, exception types and return shape. Add `defer()` beside it:
   `new_status="snoozed"`, reason required and run through the existing
   `sanitize_reason` (≤500 chars, rejects empty/whitespace-only/control
   characters). Its `by` **default** is `"manualDefer"`, mirroring
   `dismiss(by="manualDismiss")` — that default is for direct library callers
   only; the CLI passes `by="cli"` explicitly, as it already does for promote
   and dismiss, which is what AC-1 requires.

2. `shared/scripts/tools/triage_cli.py` — `_cmd_dismiss` and a new `_cmd_defer`
   both dispatch through one `_status_flip(fn, args, verb)` that owns the
   three `except` arms and the stderr line. Register the `defer` subcommand
   with a positional id and a required `--reason`, worded the same way
   `dismiss` is.

3. `triage_cli.py` listing — `_cmd_list` partitions the resolved items into
   `status == "triage"` (open) and `status == "snoozed"` (deferred). The open
   block renders exactly as today. The deferred block prints under its own
   header with a count and each item's reason, via a compact
   `_format_deferred()` that omits the launch-payload fence. `--json` keeps
   filtering to open items only.

4. `shared/scripts/github_triage/mappers.py` — rename
   `_PR_CI_DETAIL_MAX_LEN` → `_DETAIL_MAX_LEN`, add `_cap_detail(text)`
   holding the existing `[: cap - 1] + "…"` rule, and call it from both
   `ci_action_unit` and `pr_ci_action_unit`.

5. Docs — `shared/glossary.md` (*Defer (Snooze)* currently asserts
   `triage_cli.py has none`), `docs/guide.md` (two command lists),
   `docs/security-ci-setup.md` (operator actions list).

**Order:** tests first per AC (red), then 1 → 2 → 3 → 4, docs last.

## Alternative considered — and why not

**Copy `dismiss` into `defer` verbatim and show deferred items only behind a
`--status` flag.**

Cheaper to review line-by-line and it touches no existing function, so nothing
already-working can regress. Rejected on two counts. The duplication is the
smaller one: two guard clauses that must be edited in lockstep forever, and
~55 added lines that push `triage_cli.py` past the 300-line budget the
constitution sets, buying a bloat-baseline entry for no behavioural gain. The
larger one is the flag. The card asks that "the terminal listing distinguish
deferred from open"; behind an opt-out flag the default listing distinguishes
nothing — a deferred item looks exactly like a dismissed one, i.e. gone. Since
neither surface can un-defer, an operator who defers from the terminal would
have no terminal-side way to see the item again. Visible-by-default in a
separate section is what makes the third decision usable rather than a
trapdoor.

## External plan review — dispositions

GPT and Gemini, both succeeded, `--mode iterate`. Eight findings; every one
answered.

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | high (both) | `by="manualDefer"` contradicts AC-1's "recorded as `cli`" | **Not a defect — plan wording was.** `manualDefer` is the *library default* for direct callers, exactly mirroring `dismiss(by="manualDismiss")`; the CLI passes `by="cli"` explicitly, as it already does for promote/dismiss. Step 1 below now says so. Pinned by a test asserting `statusBy == "cli"` |
| 2 | med (both) | `--reason ""` / `"   "` may slip past argparse | **Already rejected** — `sanitize_reason` → `_sanitize_single_line` strips then raises on empty. Verified by reading, not assumed; now pinned by its own test case (AC-2 widened) |
| 3 | med | the `dismiss()` extraction could regress persistence behaviour | **Accepted.** Direct extraction, identical check order and `mark_status` call; helper kept to exactly its two callers (`promote` keeps its own body rather than growing a `promoted_task_id` parameter). Existing `test_triage_promote.py` stays untouched as the regression net |
| 4 | med | deferred reasons/titles may carry control characters this CLI did not write | **Accepted — real gap.** `_format_deferred` strips both through the same `strip_control_chars` the open block uses. New AC-5b |
| 5 | low | deferred-section ordering and empty-state undefined | **Accepted.** Header only when non-empty; resolved-item order, same as open. Four rendering cases tested: open-only, deferred-only, mixed, neither |
| 6 | med | the campaign-ledger status update was claimed but unplanned | **Accepted, resolved the other way** — the ledger is a dated walk record shared by sibling cards; delivery is recorded via the `trg-813d2305` dismissal + ADR + changelog drop. Spec section "Where delivery is recorded" |
| 7 | low | `_cap_detail` must not touch a detail of exactly the cap length | **Accepted.** Guarded form; 1023 / 1024 / 1025 boundary tests on both mappers. AC-8 sharpened |
| 8 | low | the frozen `--json` contract deserves its own regression test | **Accepted.** A test asserts the array is open-only *with a snoozed item present*, and that `pendingDelivery` survives |

### Round 2 (re-run against the revised plan, stdout saved as the review record)

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 9 | med | a deferral written by the Command Center may carry **no** reason — its route makes `reason` optional — so the formatter must not assume one | **Accepted — real gap, and the round's best find.** Verified in the WebUI's `parseDismissSnoozeBody`: `reason` defaults to `null`. `_format_deferred` renders an explicit `(no reason recorded)` rather than `None`, tested with a reason-less snoozed record |
| 10 | med | the new block also prints `severity`, `kind`, `source`, `dedupKey` — sanitising only title and reason leaves the same injection path open | **Accepted.** Every string interpolated into the listing goes through one `_s()` safe-display call. This also covers the four header fields in the **open** block, which were unsanitised before; splitting the function's fields into safe and unsafe halves would be indefensible, and the change is invisible for well-formed data |
| 11 | med | pin that `dismiss` keeps its exit codes, wording and "writes nothing on rejection" across the `_status_flip` extraction | **Accepted.** Existing dismiss cases stay; added assertions that the stored record is unchanged after a rejected call |
| 12 | low | `sanitize_reason`'s exception must be in the CLI's exit-2 mapping, else a traceback and exit 1 | **Verified, not assumed** — it raises `ValueError`, which `_status_flip` maps to exit 2, the same arm `dismiss` already used. Pinned by a whitespace-only-reason subprocess test |
| 13 | med (Gemini) | `_cap_detail(None)` would raise `TypeError` | **Declined.** Both call sites build `detail` locally as an f-string; the helper is module-private with exactly those two callers, so the branch is unreachable. A guard here would be dead code, and dead defensive branches are how a real `None` later goes unnoticed instead of crashing loudly |

## External code review — dispositions

`--mode code` against the real diff, run twice: once on the first
implementation, once on the fixed one.

**Pass 1.** Gemini: ship-as-is. GPT, one medium that was correct and the best
find of the whole run:

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 14 | med | `safe_display` delegated to the payload sanitizer, which **keeps `\n` and `\t` by design** — so a stored title or reason containing a newline forges extra rows in a line-oriented listing. Output spoofing, not escape execution, and AC-5b did not actually hold | **Accepted — real defect.** Fixed at the policy source rather than locally: `tty_sanitize.strip_control_chars_inline` is a sibling of the payload sanitizer, so the two cannot drift. Every scalar field uses it; only the launch payload keeps its line breaks |
| 15 | low | the AC-5b test used ESC/BEL — precisely the characters the payload sanitizer *does* strip — so the implementation could pass while the injection stood | **Accepted, and this is why the defect survived the first test pass.** Added a test that plants `- trg-fake…` behind a newline in both a title and a reason and asserts no rendered line *starts* a forged row |

**Pass 2** (on the fixed diff). GPT: ship-with-fixes, one low. Gemini's reply
**came back truncated** at 523 characters — cut off just after quoting
`format_item`'s field block and saying "there is a BUG here", with the bug
itself never stated. Recorded as truncated rather than as a clean pass, and
the quoted block was re-read by hand rather than waved through:

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 16 | low | the cap boundary was pinned for the failing-check mapper only; a regression flipping the proposed-change mapper to `>=` would pass everything | **Accepted.** 1023/1024/1025 boundary cases added for `pr_ci_action_unit` too |
| 17 | — | Gemini's unstated "bug" in `format_item`'s field block | **Inspected by hand; one defensible issue found and fixed.** `source` was being sanitized *before* it drove the `elif source == "github"` placeholder branch — a display rule silently deciding control flow. Now the stored value drives the branch and only the printed copy is sanitized. Whether this is what Gemini saw is unknowable from a truncated reply; it is a real smell either way |

## Risks

| Risk | Mitigation |
|---|---|
| Widening `list --json` would break the Command Center's byte-for-byte parity fixture in a *different repo* | AC-6 pins the JSON path to open-only; the deferred section is human-output only |
| Refactoring `dismiss()` silently changes its behaviour | Signature, defaults, exception types and return dict kept identical; the existing `test_triage_promote.py` suite is the regression net and must stay green untouched |
| Renaming `_PR_CI_DETAIL_MAX_LEN` breaks an importer | Verified: no other module or test references it |
| A deferred item becomes unreachable from the CLI | Accepted and matches the Command Center exactly (`statusFlipRoute` also requires `status === "triage"`); recorded under Out of Scope, not silently |
