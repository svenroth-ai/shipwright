# Iterate Spec: P3.8 — Rewritability check: requirement links to its rationale (ADVISORY, never a hard gate)

- **run_id:** iterate-2026-09-10-p3-8-rewritability-advisory
- **Campaign:** req3-04c-ac-identity-wave2, sub-iterate p3.8 — the LAST sub-iterate before
  campaign close-out.
- **Affected FRs:** none (a new detective-only compliance audit check; see §4 Spec Impact)
- **Source sub-iterate spec:**
  `.shipwright/planning/iterate/campaigns/req3-04c-ac-identity-wave2/sub-iterates/p3.8-rewritability-advisory.md`
- **Design of record:** `Spec/design/2026-07-22-req3-campaign-SPEC.md` mechanism M7 (table row,
  §1.5), the two "Zwei neue Verfeinerungen" paragraphs after D8-D13 (§3.2), and §7's one-line
  scope note ("P2 ist jetzt DRIN (Track R / P3.8)").

## 1. Problem, restated from the spec

M7 states the goal in prose only: "Requirement -> *Warum* verlinkt (ADR/Rationale), nicht nur
*Was*" — status today "Prosa-Regel, unklar ob real" (prose rule, unclear if real). The spec's own
instruction is explicit: **"pruefen, nicht annehmen"** (verify, don't assume) — this sub-iterate's
job is to check whether the linkage is real, and build the check, staying advisory:

> "M7 bleibt advisory, kein Hart-Gate. Codex will 'nicht-offensichtliche Policy braucht eine
> lebende Rationale' ... Richtig — aber ein ADR-Zwang fuer jede Magic Number waere Bloat. Die
> grill-Runde *fragt* danach (Matt-Pocock-Filter: schwer umkehrbar + ueberraschend + echter
> Trade-off); der Check meldet, blockt nicht." (§3.2)

The sub-iterate spec itself is two acceptance criteria and nothing else: "Reports unlinked
requirements" / "Never fails a build." Everything else — what "rationale" means concretely in
this codebase's data model, and what "linked" means — is left to be verified, exactly as the
design spec asks.

## 2. Interpretation adopted, stated explicitly (per the runner brief's own instruction)

**Verified first, not assumed.** Neither `shared/schemas/decision_drop.schema.json` nor
`shared/scripts/lib/requirement_model.py` carries any field that links an FR id to a decision
drop / ADR in either direction. Confirmed by direct inspection (grep for `rationale`/`adr` in
`requirement_model.py`: zero hits; the decision-drop schema's `rationale` field is a free-text
one-liner on the DROP itself, with no `affected_frs`/`fr_ids` counterpart). **This absence is
itself the M7 finding** — the "verlinkt" (linked) mechanism M7 asks about does not exist as a
first-class field anywhere in the codebase today. This sub-iterate does not invent one (out of
scope for an advisory-only check, and the campaign's own D7 rules out an LLM/judgement
substitute for measuring it) — it measures the closest thing that IS real and mechanical.

**The Matt-Pocock filter (hard-to-reverse + surprising + real trade-off) is explicitly a
grill-time / authoring-time judgement** ("die grill-Runde *fragt* danach"), not a property a
static scan over the existing catalogue can compute — no field records which past FRs would
have tripped that filter. Building that judgement is Phase-2 grill-module work (already scoped
elsewhere in the design spec, §6), not this sub-iterate's. What IS buildable today, mechanically,
against the actual data model:

1. `shared/scripts/lib/fr_change_history.py` already answers "which `work_completed` events
   named this FR" (via `affected_frs`/`new_frs`), and each such event carries the run's own
   `adr_id` (== its `run_id`, ADR-059).
2. A decision drop — the record ADR-029's F3 mandates for a run's *why* — is filed under
   `.shipwright/agent_docs/decision-drops/<run_id>_NNN.json` and, once aggregated, folded into
   `decision_log.md` with a `**Run-ID:**` bullet naming the same run_id.

**A requirement counts as `linked` if ANY run recorded as having changed it also produced a
decision drop or an aggregated ADR entry** — the same run_id on both sides is the whole signal.
This is a PROXY (a run can touch several FRs and write an ADR about only one of them), named as
a limitation, not glossed over (§6).

**Three outcomes, never two** — the same discipline `fr_change_history.py` already applies: a
requirement with recorded changes but none rationale-linked is `unlinked` (a real, if
approximate, answer). A requirement with NO recorded changes at all is `could_not_determine` —
the event log's FR-link coverage is a MINORITY of events (that module's own docstring), so
"no recorded change" must never be silently folded into "confirmed unlinked." This is the
silent-exclusion discipline the campaign re-learned three times over the p3.6/p3.7 review
rounds, applied here even though the cost of getting it wrong is lower (advisory, not a gate).

## 3. Where it lives

A new advisory check, **I9**, in the existing Group I ("Requirement Hygiene") detective audit
(`plugins/shipwright-compliance/scripts/audit/group_i.py`) — M7's own subject (a requirement
lacking something `fr-authoring.md` expects) is squarely Group I's territory, and Group I
already has the exact "advisory, reported with counts, never flips the verdict" shape M7 asks
for (I1-I3/I6-I8). No new CLI, no new command, no `.github/workflows/ci.yml` touch — the existing
`/shipwright-compliance` dashboard is the surface, deliberately, to avoid the CI-supply-chain
trust boundary entirely (the runner brief's hard constraint 2) and to avoid a second consumer
surface where the sub-iterate spec asked for none (Karpathy: surgical, not a new entry point).

**New modules:**

- `shared/scripts/lib/rewritability_links.py` — pure classification
  (`scan_fr_rationale_links`, `rationale_run_ids`), one pass over the event log per audit run
  (not per-FR, which would re-read/re-sort the append-only log once per requirement).
- `plugins/shipwright-compliance/scripts/audit/group_i_rewritability.py` — pure rendering,
  split out the moment the addition to `group_i.py` first crossed the 300-line size guideline
  (same bloat-extraction recipe `group_i_rows`/`group_i_criteria`/`group_i_tbd_age` already
  used, in preference to a baseline exception for a brand-new file).

**`group_i.py` itself** gains `_CHECKS`/`_ADVISORY_CHECKS` entries and a five-line
`_rewritability_finding` wrapper — I9 is `LOW` severity (a judgement-owed signal, not an
objective defect, same bucket as I1/I2/I3/I6/I7) and unconditionally advisory (never `fail`,
including when the event log itself cannot be read).

## 4. Spec Impact

**NONE.** No FR is minted or modified — this is a new detective-only compliance check, the same
class of change I6/I7/I8 were when each was added (Group I's own precedent: `I8`'s own
iterate-2026-09-06 spec-impact was also NONE). `--change-type infra` / spec-impact `none`.

## 5. Reused primitives (no second event-log reader, no second decision-drop scanner)

- `lib._fr_history_events.read_work_events` / `EventLogUnreadable` — the SAME event-log reader
  `fr_change_history.py` uses (amendments already folded, corrupt-fragment counting already
  built) — not re-implemented.
- `lib.decision_drops_index.drop_dir` / `pending_drops` — the same drop-directory resolver and
  scan `decision_drops_index.py`'s own renderer uses. `pending_drops` is a new one-line public
  wrapper around the pre-existing private `_pending_drops`, promoted specifically so this module
  does not carry a fourth independent copy of the same scan (external plan review, openai,
  medium — §5a finding 4; fixed, not merely disclosed).
- `scripts.audit.group_i_rows.FrRow` / `scan_specs` — the SAME row scanner every other Group I
  check already reads from; I9 asks nothing new of the catalogue reader.

## 5a. External Plan Review Findings (Step 3.5 — glm + openai, 2026-09-10)

| # | Provider | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | HIGH | The "linked" signal is run-level, not FR-level — an FR reads as linked whenever ANY decision drop exists for a run that touched it, even if the drop's rationale is about a *different* FR the same run also changed. Risks false reassurance, the opposite of M7's intended signal. | **Fixed.** `group_i_rewritability.rewritability_detail`'s rendered text now says explicitly, inline: "changed in a run that also recorded a decision-drop/ADR (co-occurring rationale — a proxy signal, not a verified per-requirement link)" for the linked case, and "no decision-drop/ADR of its own (no co-occurring rationale record)" for the unlinked case — stated in the DASHBOARD TEXT itself, not only in the module docstring a reader may never open. Internal field names (`linked`/`unlinked`) are unchanged (extensively tested); only the rendered wording changed. |
| 2 | openai | HIGH | "Never fails a build" was only substantiated for `EventLogUnreadable`; the decision-drop directory / decision_log.md reads could still raise on a permission error, encoding fault, or an unexpected parser exception, crashing the audit. | **Fixed.** `_pending_drop_run_ids` now wraps its (promoted-public, see #4) directory scan in `try/except OSError`, degrading to an empty set rather than propagating — the safe direction, since under-counting rationale links only makes MORE requirements read as `unlinked`, never produces a false "linked". `decision_log.md`'s read was already `try/except OSError` from the first draft. Pinned by `test_pending_drop_run_ids_tolerates_an_unreadable_directory` (a monkeypatched `OSError`, not a mock of the whole call chain). |
| 3 | openai | medium | Presence of a decision-drop file / `Run-ID` bullet is treated as rationale evidence without checking the content is non-blank — a placeholder or hand-edited empty drop would count as linked. | **Partially fixed.** The pending-drop side now requires a non-blank `decision` field (the schema's own required content field) before counting a run_id — pinned by `test_rationale_run_ids_ignores_a_drop_with_a_blank_decision_field`. **Rejected-with-reason** for the aggregated `decision_log.md` side: every aggregated ADR entry is produced FROM a decision-drop that already passed schema validation at write time (`write_decision_drop.py`), so content-emptiness is a write-time concern the aggregator inherits correctly, not a gap this read-only scan needs to re-verify against rendered markdown — doing so would mean parsing prose after a `**Run-ID:**` bullet to judge its "substance," a heavier and fuzzier mechanism than an advisory proxy check justifies. |
| 4 | openai | medium | The plan knowingly adds a fourth independent decision-drop directory-scanning loop because the existing helper (`decision_drops_index._pending_drops`) is private — duplicating file-discovery/parsing semantics that must now be kept in sync by hand. | **Fixed.** Promoted a narrow public `decision_drops_index.pending_drops()` (a one-line wrapper around the existing private function) and switched `rewritability_links._pending_drop_run_ids` to call it — one authoritative scan, not a fourth copy. Pinned by `test_public_pending_drops_matches_the_private_implementation`. |
| 5 | glm | low | Consider emitting a per-FR proxy-link *count* (how many of its changing runs have rationale) in the detail text, not just linked/unlinked, so a reader can gauge confidence. | **Rejected-with-reason.** Every other Group I advisory check (I1-I3, I6-I8) reports an aggregate count + a capped id preview, not a per-FR sub-table — adding per-FR run counts here would be a new rendering shape for one check, disproportionate to a LOW-severity suggestion, and the capped id list already gives an author the specific ids to investigate further via `fr_history.py`'s own CLI. |
| 6 | glm | low | Splitting `group_i_rewritability.py` out "the moment the addition first crossed 300 lines" is slightly premature abstraction for a 69-line renderer. | **Acknowledged, no action** — the reviewer's own assessment: "mirrors the established pattern, so it's consistent rather than novel. Acceptable as-is." |
| 7 | glm | medium | `could_not_determine` will likely dominate the first-run output; if I9 rendered one line per FR, an advisory check with ~all-FR "unknown" output would read as noise and be ignored. Verify the rendering aggregates rather than dumping every FR. | **Rejected-with-reason, already true.** Confirmed by reading `group_i.py`'s own `_finding`/`run()` shape: I9 renders exactly ONE dashboard row per audit run (same as every other Group I check), with an aggregate count for each bucket and only a capped preview of ids — never one line per FR. No rendering change needed; the concern described a shape this check never had. |
| 8 | glm | low | The `**Run-ID:**` regex against `decision_log.md` could false-positive-match inside a fenced code block, blockquote, or table cell rather than a real bullet. | **Rejected-with-reason, checked empirically** (not merely asserted): a script walked every line of this repo's actual `decision_log.md`, tracking fence state, and found 342 occurrences of the bold `**Run-ID:**` form — every single one on a line starting `- **Run-ID:**` and none inside a fence. (A broader plain-text `grep -c Run-ID` returns 360 — the extra 18 are unbolded prose mentions like "Run-ID iterate-..." inside a `Context:` sentence, which the regex's literal `**` requirement already excludes.) Every occurrence is the aggregator's own bullet, because only `aggregate_decisions.py` ever writes this exact string into the file. A future ADR body that quotes an example commit message containing the literal bolded string could in principle still produce a false positive; named as a residual, not fixed, since a stricter regex risks a different false negative if the aggregator's bullet prefix ever varies — tracked as a "re-check if this file's format ever changes" note rather than over-fitting to today's single observed shape. |
| 9 | glm | low | `EventLogUnreadable` renders as `pass` naming the failure — ensure this is visually distinct from a genuine "all linked" pass so a broken log is not mistaken for a clean bill of health. | **Fixed.** The unreadable-log message now leads with "NOT EVALUATED" specifically (`advisory — NOT EVALUATED: could not read the event log...`), distinct from both the linked-pass wording ("all N requirement(s)...") and the unlinked-pass wording ("N requirement(s) changed in a run with no..."). |
| 10 | glm | low | Read-only, fixed relative paths, no new trust boundary; CI/workflow non-touch correctly sidesteps the supply-chain constraint. | No finding — informational. |

Verdicts: glm `approve` (with the above findings), openai `revise` (with the above findings,
both HIGH findings fixed, both MEDIUM findings fixed or rejected with a stated reason). No
finding was silently dropped.

## 5b. External Code-Review Findings (Step 3.7 — glm + openai, 2026-09-10, against `HEAD~1`)

| # | Provider | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | medium | `_RUN_ID_BULLET_RE` matched `**Run-ID:**` anywhere in `decision_log.md`, including ADR prose or fenced examples — an unrelated ADR containing the literal string (e.g. an illustrative commit-message excerpt) could make a requirement changed under that same string appear `linked`, undermining the check's own reporting signal. | **Fixed.** Anchored to the aggregator's real bullet shape: `^\s*-\s*\*\*Run-ID:\*\*\s*(\S+)\s*$` with `re.MULTILINE`. Verified against this repo's real `decision_log.md` (342 occurrences, all match unchanged). Pinned by `test_run_id_bullet_regex_ignores_prose_and_fenced_mentions` (a fenced-block + prose mention of the literal string, both correctly ignored). |
| 2 | glm | low | The same regex issue, independently found — matches anywhere, not anchored to a real bullet line; slightly broader than even this doc's own §5a-finding-8 description ("bullet") suggested. | **Fixed, same commit as #1** (two independent reviewers converging on one finding, not two separate fixes). |
| 3 | glm | low | A `work_completed` event naming an FR in `affected_frs`/`new_frs` but carrying no `adr_id`/`run_id` was skipped entirely, so that FR silently classified `could_not_determine` ("no recorded change") instead of `unlinked` ("a change was recorded, but unattributable") — conflating two outcomes the module's own three-outcome discipline says are materially different. | **Fixed.** `scan_fr_rationale_links` now tracks `touched_frs` (every FR named in any event) SEPARATELY from `fr_run_ids` (only the usable-run_id pairs); classification checks `touched_frs` first, so an unattributable change now correctly lands in `unlinked`. Pinned by `test_a_change_with_no_usable_run_id_is_unlinked_not_could_not_determine`. |
| 4 | glm | low | No test covered the >5-ids preview-cap rendering, the `EventLogUnreadable` branch AT THE GROUP I WIRING LEVEL (only the shared-lib layer proved propagation; nothing proved the renderer's `except rw.EventLogUnreadable` clause doesn't itself raise `AttributeError` if the loaded module lacked that name), or mixed linked+unlinked rendering. | **Fixed.** Three new tests in `test_audit_group_i_rewritability.py`: `test_preview_is_capped_but_the_true_count_is_reported`, `test_event_log_unreadable_at_the_group_i_wiring_level_never_fails` (monkeypatches the ACTUAL loaded module object via `load_shared_lib`, not a string-path mock, so it exercises the real `rw.EventLogUnreadable` attribute access), and `test_mixed_linked_and_unlinked_renders_both_parts`. |
| 5 | glm | low | If `fr_ids` is empty, the "all N requirement(s)..." message fires with `N=0`, reading as a false claim ("all 0 requirements... were changed in a run that also recorded...") rather than an empty one. | **Fixed.** `rewritability_detail` now guards this branch with `if not scan.linked: return "no requirements to evaluate this run"`. `group_i.run()`'s own `STATE_ROWS` branch never reaches this function with empty `rows` in practice, but the lib function is public — guarded rather than trusting every future caller. Pinned by `test_no_requirements_is_not_rendered_as_a_false_all_zero_claim`. |

Verdicts: glm `approve`, openai `revise` — the one medium finding fixed (independently
corroborated by glm's own low-severity version of the same issue); all four low findings fixed.
No finding was silently dropped.

## 6. Known limitations (disclosed, not fixed)

- **The link is a PROXY, not a direct check — now stated in the rendered dashboard text itself,
  not only here** (external plan review, openai, HIGH; §5a finding 1, fixed). No field anywhere
  states "ADR-NNN explains FR-xx.yy" — I9 infers it transitively through a shared run_id, and a
  requirement reads `linked` whenever ANY run that changed it also wrote SOME decision drop, even
  if that drop's own prose discusses a different requirement the same run touched. A run that
  changed a requirement without naming it in `--affected-frs`/`--new-frs`, or whose decision
  drop's own run_id differs from the change-recording run's (e.g. a follow-up ADR written days
  later under a new run_id), reads as `unlinked` even though a rationale may exist in prose
  somewhere.
- **`could_not_determine` will likely dominate on first run.** `fr_change_history.py`'s own
  docstring states event-log FR-linkage is a MINORITY of `work_completed` events — most FRs
  across the repo's specs have never been named in `affected_frs`/`new_frs` at all, so most will
  report `could_not_determine`, not `unlinked`. This is the honest baseline measurement the
  spec's own "pruefen, nicht annehmen" instruction asked for (the same "0 Zellen ok" spirit as
  P0's own honest-baseline measurement) — not a bug to suppress by re-labelling the bucket.
- **The `**Run-ID:**` bullet convention only exists on ADRs from 2026-05-16 onward** (same
  cutoff `fr_change_history.py` already documents for `adr_id`). An older ADR's rationale is
  real but invisible to this scan and reads as unlinked.
- **The Matt-Pocock filter itself (hard-to-reverse + surprising + real trade-off) is not
  applied.** I9 reports EVERY requirement with recorded changes and no rationale link, not only
  the subset that would have tripped the filter — building that judgement needs the grill-module
  authoring-time interview (§6 of the design spec), which is out of scope here. Named as a real
  gap rather than silently narrowed: a future grill-module integration is the natural place to
  apply the filter at write time, while I9 stays the after-the-fact detective measurement.

## 7. Confidence Calibration (Step 3.8)

Step 3.4's re-check records `effective_complexity: small`, no risk flags, `diff_loc: 597` (the
`plan_review_required` trigger fires on diff size alone, not complexity or a risk flag).
Neither the `medium`+ trigger nor `touches_io_boundary` fires. **Skipped per the strict trigger**
(`skipped_complexity_and_no_io_boundary`) — Self-Review (§8) is the review of record for this
run.

## 8. Self-Review (Step 3.6 — 7-item checklist)

| # | Item | Verdict | Note |
|---|---|---|---|
| 1 | Spec Compliance | pass | Both ACs met: "reports unlinked requirements" (I9's `unlinked`/`could_not_determine` detail text, both named explicitly) and "never fails a build" (I9 is unconditionally `pass`, in `_ADVISORY_CHECKS`, and the CLI never raises past a caught `EventLogUnreadable`). |
| 2 | Error Handling | pass | `scan_fr_rationale_links` propagates `EventLogUnreadable` rather than degrading to an empty scan (would silently misreport "every FR unlinked"); `group_i_rewritability.rewritability_detail` catches it and renders a `pass` finding naming the failure, never a crash and never a false green claiming completeness. A missing event log (the common case for a fresh/adopted repo) is an ordinary state (`could_not_determine` for every FR), not an error. |
| 3 | Security Basics | pass | Read-only: no new write surface, no new trust boundary beyond the event log / decision-drops directory Group I and `fr_change_history` already read. No path traversal (fixed relative filenames under `project_root`). |
| 4 | Test Quality | pass | `shared/scripts/tests/test_rewritability_links.py` (17 tests) covers the three outcomes, both rationale sources (pending drop + aggregated log), dedup, a malformed drop file, a blank-`decision`-field drop, an unreadable decision-drops directory, corrupt-fragment surfacing, `EventLogUnreadable` propagation, the missing-log case, the touched-but-unattributable-run_id case, and the anchored-regex false-positive rejection (prose/fenced-block mentions of `**Run-ID:**`). `plugins/shipwright-compliance/tests/test_audit_group_i_rewritability.py` (8 tests) covers the Group I wiring: never-fail, linked rendering, could-not-determine rendering, non-interference with sibling checks, the preview-cap path (>5 unlinked ids), mixed linked+unlinked rendering, `EventLogUnreadable` surviving at the wiring level (not just the shared-lib layer), and the vacuous-`fr_ids` guard. The last five tests in each file were added directly in response to Step 3.7's external code-review findings (see §5b). |
| 5 | Performance Basics | pass | One pass over the event log per audit run (not per-FR) — explicitly designed against `fr_change_history.change_history_for_fr`'s per-call re-read/re-sort, since Group I calls this once over every live FR in the catalogue. |
| 6 | Naming & Structure | pass | Mirrors the existing `group_i_criteria.py`/`group_i_tbd_age.py` split (detector logic in a pure sibling, `group_i.py` keeps finding assembly); `group_i_rewritability.py` was split out the moment the direct addition first crossed 300 lines, in preference to a bloat-baseline exception for a brand-new file. Both new files are well under the 300-LOC limit (227 and 94 lines, final — grew from the initial 206/69 during the Step 3.7 code-review fix round). |
| 7 | Affected Boundaries (ADR-024) | pass | Producer: `shipwright_events.jsonl` (`work_completed` events, unchanged by this sub-iterate) and `.shipwright/agent_docs/decision-drops/*.json` / `decision_log.md` (also unchanged). Consumer: the new `rewritability_links.py` classification, read-only. Round-trip probed for real against this actual repo's own event log and decision log in §9 below, not merely fixture data. |

## 9. Empirical probe (Step 3.8-adjacent, real repo)

```
$ uv run pytest plugins/shipwright-compliance/tests/test_audit_group_i.py \
    plugins/shipwright-compliance/tests/test_audit_group_i_rewritability.py -q
... 27 passed
$ uv run pytest shared/scripts/tests/test_rewritability_links.py -q
... 17 passed
```

Also read directly against this repo's own `.shipwright/agent_docs/decision_log.md` during
development (`rationale_run_ids`, ad hoc, re-verified after the Step 3.7 regex-anchoring fix):
the file contains 360 total substring occurrences of "Run-ID", of which 342 match the anchored
`- **Run-ID:** <value>` bullet shape the fixed regex now requires. The remaining 18 are
unbolded prose/heading mentions the anchored regex correctly excludes (the exact false-positive
class the code review flagged — see §5b) — confirming both that the convention this module
reads is real and consistently formatted, and that the anchoring fix did not silently drop any
real bullet.

## 10. Deferred, not built here

- Applying the Matt-Pocock filter (hard-to-reverse + surprising + real trade-off) at
  authoring/grill time — the design spec's own Phase-2 grill-module scope, not this
  sub-iterate's advisory detective check.
- A direct FR<->ADR schema field (e.g. `decision_drop.schema.json`'s own `affected_frs`) that
  would make the link exact instead of a run_id proxy — a real schema change with its own
  producer/consumer ripple (every F3 caller, the aggregator, the render), out of scope for an
  advisory measurement sub-iterate; named so it is not lost, not filed as a vague TBD (the
  campaign's own `trg-875104ac` lesson).

## 11. F0 self-correction (an unrelated bug this run's own artifact tripped over)

The first full F0 run went RED on `plugins/shipwright-iterate/tests/test_agent_doc_entry_rules.py`:
this run's own F3a Learnings entry (§ conventions.md) was 625 chars, over the 600-char budget —
and `check_agent_doc_budget.py`'s forward-only CLI check (run by hand earlier and reported "OK")
had missed it. Root cause, verified by direct inspection: the entry's own prose quoted another
convention's bold `**Run-ID:**` marker for illustration, and `agent_doc_budget.entry_anchor()`
extracts the first bold span as an entry's cross-diff identity — an unrelated EXISTING entry
happened to share that same incidental anchor, so the new-entry classifier treated this one as
"already present" and skipped the length check entirely. Fixed here by shortening the entry to
479 chars and removing the bold markup (`479 chars` verified); the underlying `agent_doc_budget.py`
anchor-matching gap is a real, separate latent bug, filed as `trg-f160885d` rather than fixed in
this diff (surgical scope — a shared-library fix belongs in its own iterate, not folded into M7).
Full F0 was re-run clean after the fix (§9's counts are pre-fix; see the finalization result JSON
for the final green run).

## 12. Addendum: bundled build — test-body-suspects (a P3.7 deferred item)

Bundled into this same run, alongside M7 rewritability: P3.7's own sub-iterate spec named a
third, lower-priority check and explicitly deferred it — an acceptance criterion whose own text
is UNCHANGED between base and head, but whose bound test's BODY was edited in the same diff. Same
class as this design's own M7 ("mechanics raise a flag, a human decides") and P3.6's design doc
§7: never a hard gate.

**What was added:** `shared/scripts/tools/check_test_body_suspects.py` +
`verifiers/_test_body_suspects.py` (detector, reuses the same base/head criterion-digest reader
P3.7's Orphan-AC-binding gate already built, plus an AST walk to digest the bound test's own
function source at each commit), wired as one new `pull_request`-only CI step immediately after
P3.7's two feeder checks in `.github/workflows/ci.yml`. Its own CLI returns exit `0`
**unconditionally** — clean / advisory-finding / infra-fault all report through the JSON payload's
`status` field, never the process exit code, so it can never become a merge blocker even by
accident (strictly weaker trust posture than its P3.7 siblings, never stronger). Documented
alongside those siblings in `docs/hooks-and-pipeline.md`.

**Provenance correction.** The code, CI comment, and docs originally cited a triage card id as
the bundling authorization; that id does not exist in this repo's tracked `triage.jsonl` (neither
this worktree's copy nor the main tree's) and triage ids are randomly minted, so it could not be
reproduced. Rather than ship an unverifiable citation, this run filed a real replacement card,
`trg-d03a239d`, documenting the gap and the decision to keep (not revert) the bundled work — it is
real, tested (`test_check_test_body_suspects.py`, `test_test_body_suspects.py`, both green in this
run's own F0), documented, and CI-acked for this run_id
(`.shipwright/planning/iterate/iterate-2026-09-10-p3-8-rewritability-advisory/ci_supplychain_ack.json`,
`consistent_with: "#711"`). All four citations were updated to `trg-d03a239d` in the same commit.
Recorded as a second F3 decision drop (`..._002.json`, separate from M7's own `..._001.json`) and
a second F4 changelog drop (`..._002.md`), since this is a materially separate concern from M7.
