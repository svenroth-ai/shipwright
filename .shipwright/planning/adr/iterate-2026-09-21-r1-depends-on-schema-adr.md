# R1 — `depends_on` schema, `campaign_graph.py`, resume-safe readiness

Campaign `campaign-dag-scheduler`, sub-iterate R1
(`iterate-2026-09-21-r1-depends-on-schema`). Full design authority:
`.shipwright/planning/iterate/2026-09-20-campaign-dag-scheduler-plan.md`
§ "R1 — `depends_on` schema, `campaign_graph.py`, campaign-design
conversation, resume-safe readiness".

## Context

Bootstraps a dependency-aware parallel campaign scheduler by adding the
`depends_on` schema (campaign.md column + `status.json`/`loop_state.json`
carry-through), the structural/charset validators, a resume-safe status
projector (`safe_project_campaign_status`), and a narrow readiness guard on
`autonomous_loop.py::cmd_next` — without disturbing today's serial engine's
existing interface at all (`kind == "section"` completely untouched).

## Decision

Implemented exactly per the sub-iterate spec's "Files to create/modify" and
"Work breakdown" sections: new `lib/campaign_graph.py` (`id_charset_ok`,
`validate_dependency_graph`, `check_frozen_contracts`,
`safe_project_campaign_status`), new `lib/loop_state.py` (`_load_units_from`
moved with the three stated fixes, `is_unit_ready`, `describe_blocker`),
`campaign_status.py`'s header-indexed `parse_campaign_skeleton` rewrite +
`project_campaign_status` carry-through, `campaign_init.py`'s write-time
hard-reject validation + `stacked` deprecation warning, and `cmd_next`'s
one `kind == "sub_iterate"`-gated guard clause.

## External-Plan-Review-Findings

Reviewed via `external_review.py --mode iterate` against the master plan
document + this sub-iterate's spec (both external reviewers, GLM and
OpenAI, independently returned `SHIPWRIGHT_VERDICT: revise`; no
contradiction between them — both converged on several of the same points).

| # | Reviewer | Severity | Finding (summary) | Disposition |
|---|---|---|---|---|
| 1 | GLM | high | `cmd_next`'s exit-2 fallthrough is indistinguishable from genuine completion when every remaining pending unit is blocked — the orchestrator would silently finalize an unfinished campaign. | **accepted-and-fixed** — added additive `blocked_pending_ids` + `blockers` fields to the exit-2 JSON body (no exit-code change, per the spec's explicit "no new exit code" constraint); the orchestrator's own consumption of these fields is R4/R5a's job, documented as such in `campaign-mode.md`. |
| 2 | GLM | medium | `is_unit_ready`'s ancestry verification has no stated fetch/retry policy or cwd/lock ordering. | **rejected-with-reason** — already correctly handled: any git failure (fetch, timeout, unresolvable default branch) yields `None` (unverified/blocking), never a crash or false-positive; this IS the reviewer's own suggested fail-safe direction. Retry-count formalization is explicitly R4's "lease-based reconcile" scope. Docstring strengthened to state this explicitly. |
| 3 | GLM | medium | Migrated-`complete` row ancestry: unspecified handling for fetch failure / rewritten history / unresolved default branch. | **accepted-and-fixed** (documentation) — same fail-safe design as #2 covers this; `describe_blocker` already reports "merged, but its commit failed ancestry verification" distinctly from "not yet merged". Strengthened docstring in `loop_state.py` and `campaign-mode.md` to make the degradation mode explicit. |
| 4 | GLM | low | Headerless-table heuristic ambiguity: a data row whose first cell happens to equal a known column name could misparse as a header. | **rejected-with-reason** — pre-existing behavior, not an R1 regression: the ORIGINAL `parse_campaign_skeleton` (pre-R1) already used the identical `cells[0].lower() == "id"` header marker; R1 only extended what happens once a header IS recognized. Out of scope to redesign here. |
| 5 | GLM | low | `check_frozen_contracts`'s revert is only a transient `warnings` entry — no persisted audit record. | **rejected-with-reason** — the revert IS surfaced in `summary["warnings"]`, the fixed-shape record `campaign_progress.py`'s callers already consume/display; persisting into `events_log` is new write-contract scope beyond R1's stated file list, deferred. |
| 6 | GLM | low | Confirm `campaign_init.py`'s `sys.path` bootstrap actually works at its real invocation context. | **accepted-and-verified** — exercised directly (`init_campaign(...)` with a `depends_on` graph, including a rejection path) during implementation; both the accept and reject paths work correctly from the real CLI entry point. |
| 7 | OpenAI | high | `validate_dependency_graph() -> list[str]` can't be both flat AND separately-typed without callers parsing text. | **accepted-and-already-implemented** — resolved via a documented `"structural: "` / `"charset: "` string-prefix convention (module docstring states this explicitly); meets the plan's literal `list[str]` signature while giving callers an exact partition mechanism (`msg.startswith("charset:")`). |
| 8 | OpenAI | high | `is_unit_ready` described as "pure" but readiness needs a live git ancestry assertion. | **accepted-and-already-implemented** — the actual implementation keeps `is_unit_ready` genuinely pure (only reads `status`/`merged_commit` fields already present on the unit dict); the git ancestry check runs separately, once, in `_load_units_from` at load time via `verify_merged_commit_ancestry` — exactly the reviewer's own suggested fix. Plan-text ambiguity, not an implementation gap. |
| 9 | OpenAI | high | Live `campaign.md` refresh inside `cmd_next` is underspecified (no `--campaign-dir`, no locking sequence). | **rejected-with-reason / scoped-out** — implemented `cmd_next`'s guard using ONLY the `depends_on` already loaded onto each unit at `cmd_init` time (correctly refreshed on a resume, per `_load_units_from`'s fixes); no live per-call refresh is attempted inside `cmd_next`, consistent with the spec's explicit "do NOT add `--campaign-dir` to `cmd_next`" instruction. True live refresh is R4's `cmd_next_batch`. |
| 10 | OpenAI | high | Mapping `complete -> merged` needs the actual POST-MERGE commit SHA; fetching `origin/<default>`'s tip alone can't reconstruct which commit was this unit's. Specifically: step 3g's `--squash` merge mints a brand-new SHA the pre-merge branch commit recorded at step 3h will never be an ancestor of. | **accepted — documented as a known limitation, fix deferred to R4/R5b.** This is real and important: `verify_merged_commit_ancestry` will correctly-but-uselessly return unverified for every real squash-merged unit until a later sub-iterate teaches step 3h to record the actual post-merge SHA (`gh pr view --json mergeCommit`) instead of the runner's pre-merge commit. The degradation direction is SAFE (stays blocked, never falsely unblocks) — documented prominently in `loop_state.py`'s docstring and `campaign-mode.md`'s "Dependency Graphs" section, flagged explicitly for R4/R5b's attention. |
| 11 | OpenAI | medium | `safe_project_campaign_status` has no production caller wired in R1. | **rejected-with-reason** — out of scope per R1's own "Files to create/modify" list (does not include `campaign_progress.py`/`campaign_status_io.py`); its first caller is R4's `cmd_next_batch`, per the plan's own "Ownership split" note. Thoroughly unit-tested standalone in the meantime. |
| 12 | OpenAI | medium | Possible import cycle: `campaign_status.py` importing FROM `campaign_graph.py` while `campaign_graph.py` wraps `campaign_status.py`'s own `parse_campaign_skeleton`. | **rejected — not applicable to the actual implementation.** `campaign_status.py` does NOT import `campaign_graph.py` in this diff (verified: `python -c "import lib.campaign_status; import lib.campaign_graph"` succeeds); the import is one-way (`campaign_graph` -> `campaign_status`) only. The master plan's "imported by campaign_status.py" line is a forward-looking statement about R4, not an R1 requirement — not wired here. |
| 13 | GLM + OpenAI | medium | Case-insensitive id uniqueness: Windows worktree paths case-fold, so `R0`/`r0` can collide despite each passing the charset check independently. | **accepted-and-fixed** — `validate_dependency_graph` now folds case for duplicate-id detection AND `depends_on` existence resolution (author-supplied casing preserved in every message); new tests cover the case-fold collision, the case-mismatched-reference-resolves case, and case-fold self-dependency. |
| 14 | OpenAI | medium | R1 documents exit code 4 before R4 implements it — a misleading intermediate contract. | **rejected-with-reason — already mitigated.** The exit-code table in `campaign-mode.md` explicitly marks codes 4/5/6 `(R4)` and states in prose that `cmd_next`'s own exit 2 does not yet mean "campaign actually finished" in the interim window; this was written defensively before the review ran, precisely to avoid the concern raised. |

Both reviewers agreed the overall design direction (source of truth in
`campaign.md`, frozen-per-unit degradation, the `campaign_graph.py` split)
is sound; the accepted findings above are targeted fixes, not a redesign.

## Self-Review

```
Self-Review:
  1. Spec Compliance:    [pass] Every file in the plan's "Files to create/modify"
     list touched with the exact function set specified; no extra feature
     (cmd_next_batch/--campaign-dir/exit 4 all explicitly R4, untouched).
  2. Error Handling:     [pass] campaign_init.py's write-time ValueError caught
     at the CLI boundary; verify_merged_commit_ancestry fails safe to None on
     any git/subprocess error; _read_loop_state_units degrades to [] on
     missing/corrupt JSON.
  3. Security Basics:    [pass] No SQL/HTML/secrets involved; the untrusted
     input (depends_on cell) IS validated (charset allowlist + structural
     checks), hard-rejected at write time.
  4. Test Quality:       [pass] New tests assert on outcomes (which unit gets
     claimed, whether a projection degrades); happy-path + error/blocked-path
     pair for every new function.
  5. Performance Basics: [fail] Stage-2 code review (medium, campaign-dag-scheduler
     R1): `_load_units_from` calls `verify_merged_commit_ancestry` once per
     `complete` row, and each call runs its own `git fetch origin` (60s
     timeout) — an N-unit resume performs N sequential fetches against the
     same ref instead of one shared fetch + N cheap ancestry checks.
     Doubt review (medium) sharpened this: the fetch also has no explicit
     `cwd=`, inheriting the caller's ambient directory — safe under
     campaign-mode.md's own documented convention (every `cmd_next`/`cmd_init`
     call runs from inside the campaign worktree, matching `cmd_next`'s own
     pre-existing `git rev-parse HEAD` call a few lines up, which has the
     same no-`cwd=` shape) but NOT self-defending against a caller that
     violates that convention. Non-blocking (fail-safe direction unaffected
     either way — a wrong-repo fetch still only yields `None`/blocked, never
     a false unblock); fix (hoist fetch out of the loop, pin `cwd=`) deferred
     to R4/R5b alongside `cmd_mark_merged`. is_unit_ready itself does zero I/O.
  6. Naming & Structure: [fail] campaign_status.py (357), campaign_init.py
     (409), and campaign_graph.py (328) all cross 300 lines — real crossings, mitigated via three ADR-gated
     bloat-baseline exceptions (campaign_status.py, campaign_init.py,
     campaign_graph.py) with a documented Ousterhout/YAGNI justification
     (splitting further was evaluated and rejected).
  7. Affected Boundaries:[pass] Producer/consumer pairs identified (campaign_init.py
     -> parse_campaign_skeleton/project_campaign_status; campaign_progress.py's
     3h commit record -> _load_units_from's complete->merged mapping +
     verify_merged_commit_ancestry). test_campaign_dag_integration.py is a REAL
     round-trip: files written to tmp_path, state file deleted and reloaded
     from disk across a simulated resume — not a mock. Cell-grammar edge cases
     covered in test_campaign_status_depends_on.py.
  8. Test Hygiene Probe: [pass] scan_test_hygiene.py --diff: no findings
     against every new/changed test file.

Action: Naming & Structure failure is a known, documented, ADR-gated
exception (not a silent miss) — proceed to commit.
```

See `reviews.self_review` in `reviews.json` for the recorded pass (same
8 items, `{"items":[{"name","verdict","note"}]}`).

## External-Code-Review-Findings

Ran 4 rounds (each round's diff included every prior round's fixes) via
`external_review.py --mode code` against the full diff. Rounds 1-3 each
surfaced real bugs that got fixed and confirmed gone in the next round
(GLM round 3 explicitly verified: "the `done`-token regression and
stale-fetch fail-closed paths are correctly handled and tested"). Round 4
is where the remaining disagreement crystallized into two genuinely
architectural gaps (not code bugs) plus a few more small, real fixes.

### Fixed across rounds 1-4

| Round | Reviewer | Severity | Finding | Fix |
|---|---|---|---|---|
| 1 | both | high | Case-insensitive id uniqueness/existence resolved, but readiness (`is_unit_ready`), cycle detection, and `check_frozen_contracts` all did exact-case lookups — a write-time-VALID case-mismatched edge would deadlock its dependent forever. | Case-fold lookups added to `is_unit_ready`, `describe_blocker`, `_find_cycle_members`'s adjacency, and `check_frozen_contracts`'s id match + list comparison; original casing preserved for display via a `lower_to_original` map. |
| 1 | openai | medium | A row with a missing/non-string id could reach a bare `sorted()`/`set()` on mixed types and raise `TypeError` before any finding was returned. | `validate_dependency_graph` now filters and reports missing/non-string ids as their own structural finding before any set/sort operation. |
| 2 | glm | medium | `_map_unit_status` dropped `"done"` support — the pre-R1 loader treated `"complete"`/`"done"` identically; this rewrite silently stopped recognizing `"done"`, which would re-claim and rebuild an already-finished unit from scratch. | `_map_unit_status` maps `"done"` the same as `"complete"` -> `"merged"`. |
| 2 | openai | high | `verify_merged_commit_ancestry` ignored `git fetch`'s return code — a failed fetch still fell through to `merge-base` against a possibly-STALE local ref, which could verify a commit whose remote history was rewritten while offline. | Fetch failure (`returncode != 0`) now returns `None` immediately, never reaching `merge-base`. |
| 2 | openai | medium | `_load_units_from` read only the legacy `commit` field, discarding a future `merged_commit` field — once R4/R5b's `cmd_mark_merged` writes the real post-merge SHA there, a resume would instead verify the stale pre-merge SHA forever. | `commit = s.get("merged_commit") or s.get("commit")` — a no-op today (nothing writes `merged_commit` to `status.json` yet), forward-compatible once R4/R5b lands. |
| 2 | glm | low | `campaign-mode.md`'s campaign-design-conversation prose never stated the actual COST of a `depends_on` edge (a full CI+review+merge cycle), the part that steers an operator away from over-connecting the DAG. | One sentence added. |
| 3 | glm | medium | `verify_merged_commit_ancestry`'s `commit` argument (operator-editable, from `status.json`) flowed unvalidated into `git merge-base` argv — a value starting with `-` would be parsed as a git option. Plan text itself mandates strict hex-SHA validation before this exact class of sink (`audit_compliance_lifecycle.py::_merge_sha`'s guard). | Added the same `_SHA_RE = re.compile(r"[0-9a-f]{40}")` full-match guard, rejecting non-hex-SHA `commit` values before any subprocess call. |
| 3 | openai | medium | `campaign_init.py`'s `depends_on` coercion (`list(si.get("depends_on") or [])`) silently re-splits a bare string into characters (`list("AB") == ["A","B"]`); a non-list/non-string value reaches `list(...)` and raises an uncaught `TypeError` past `main()`'s `except ValueError` boundary. | Explicit type/membership check ahead of the coercion, raising a clean `ValueError` naming the offending sub-iterate id. |
| 3 (from round 2) | glm | low | `test_charset_violation_rejected_at_write_time`'s `pytest.raises(ValueError, match="charset")` also matches the wrapper's own static boilerplate text, so it would still pass even if the finding were misclassified as structural. | Match tightened to the actual finding text (`"charset: invalid id"`). |
| 4 | openai | medium | `_read_loop_state_units` accepted schema-invalid-but-syntactically-valid JSON (`{"units":[null]}`, `{"units":{}}`) straight into `check_frozen_contracts`'s `.get()` calls, crashing the "resume-safe" projection. | Now validates `units` is a list and filters to dict elements only, degrading to `[]` on anything else. |
| 4 | glm | low | `blocked_pending_ids`'s computation (every remaining `pending` unit) is only correct "by construction" today, not derived from the guard's own skip set — fragile to a future change. | Left as-is (correct today, cheap to re-derive later) but the invariant it depends on is now spelled out in an explicit code comment naming exactly what would break it. |
| 4 (self-caught) | — | — | The `campaign_graph.py` bloat-exception ADR file itself was never `git add -N`'d, so round-3's reviewed diff excluded it — GLM's round-3 "missing ADR file" finding was a false negative from MY OWN diff-generation gap, not a real missing file. | `git add -N`'d; confirmed present in round-4's diff. |

### Fixed at F0 (fresh-verification gate, post-review)

Not caught by any external-code-review round because the reviewed diff never
included a full-suite test run — `uv run pytest tests/ -q` in
`plugins/shipwright-iterate` surfaced two real, mechanical breaks caused by
the size and content of my own prose additions to
`references/campaign-mode.md`, both fixed by extracting a new topical
reference file (`references/campaign-dependency-graphs.md`, unlisted in the
fixed allowlist `EXPECTED_TOPICAL_REFERENCES` — same pattern already used by
`campaign-worktree.md` / `campaign-step-3-4-risk-recheck.md`, so it needs no
allowlist entry and is not subject to the 400-LOC budget test itself):

| Finding | Fix |
|---|---|
| `test_every_new_reference_under_loc_budget` (400-LOC runtime-prompt cap, no exception mechanism unlike source-file bloat) failed: my additions grew `campaign-mode.md` from 366 to 506 lines. | Moved the entire "Dependency Graphs" detail section and the new "Exit-code loop-action table" into `campaign-dependency-graphs.md`, leaving a short pointer; `campaign-mode.md` compacted to 399 lines; 3f-bis remediation added 1 net line, now exactly 400 (at the cap, zero headroom). |
| `test_merge_is_inside_the_loop_and_ci_green_gated` failed: the new "KNOWN LIMITATION" prose mentioned `` `gh pr merge --squash` `` inside the (then-early-positioned) Dependency Graphs section, so `text.find("gh pr merge")` matched THAT prose mention before the real step-3g occurrence deeper in the file, breaking the pinned `checks_pos < merge_pos < finalize_pos` ordering assertion. | Fixed as a side effect of the same extraction above — the prose mention moved out with the rest of the section, restoring exactly one occurrence each of `gh pr checks` / `gh pr merge` in the correct order. |

### Verified as false alarms (not fixed — investigated and confirmed inapplicable)

| Round(s) | Reviewer | Finding | Why rejected |
|---|---|---|---|
| 2, 3, 4 | glm | The silent `except ImportError: resolve_default_branch = None` fallback could permanently, silently disable ancestry verification if `branch_base` doesn't export the symbol, or if a future transitive import chain reaches `loop_state.py` without `autonomous_loop.py`'s own sys.path bootstrap having run first. | Verified twice: (1) `resolve_default_branch` genuinely exists in `branch_base.py` and imports successfully (confirmed by direct import in this session). (2) `grep`-confirmed `loop_state.py` has EXACTLY ONE importer in the entire diff (`autonomous_loop.py`, via `lib.loop_state`), which inserts `shared/scripts/lib` onto `sys.path` (for its OWN bare `branch_base`/`file_lock` imports) strictly before importing `lib.loop_state` — so the one real code path is always safe. `campaign_status.py`/`campaign_graph.py` do NOT import `loop_state.py` anywhere (grep-confirmed) — the stated risk pathway does not exist in this diff. |
| 3 | openai | `_find_shared_scripts` is called in `campaign_init.py` but "never shown to exist" in the diff. | It is defined at line 51 of the same file (pre-existing, reused by an existing call site too) — the reviewer's tool-truncated view of the file simply didn't include it. |
| 3, 4 | openai, glm | `shipwright_bloat_baseline.json`'s three (later four) `"adr": "ADR-NNN"` entries are "placeholder"/"dangling" references, and the ADRs are `Status: proposed` while the baseline "already records the exception as in force". | This is the repo's OWN documented, intentional convention (`_template-bloat-exception.md`): the literal string `"ADR-NNN"` is used until `/shipwright-changelog` release assigns the real sequential number; a bloat-exception ADR is legitimately `proposed` until a human reviews it at that same release step. Not a defect — it is how every prior bloat exception in this repo's history is recorded. |

### Accepted, NOT fixed — escalated as an architectural/scoping gap for the campaign owner

| Round(s) | Reviewer | Severity | Finding |
|---|---|---|---|
| 1, 2, 3, 4 (escalating); doubt review (3f-bis) sharpened further | both, every round, + doubt-reviewer | high | **`cmd_next`'s exit-2 fallthrough vs. a genuinely completed campaign.** Additive `blocked_pending_ids`/`blockers` fields (round 1's fix) make a blocked-but-unfinished campaign OBSERVABLE, but do not change the documented orchestrator action for exit 2 ("Finalize", `campaign-mode.md`'s own exit-code table, written BEFORE this review cascade even ran). Round 4's GLM sharpened this to its precise mechanism: within one CONTINUOUS campaign session, `cmd_record` writes a finished unit's `loop_state.json` status as `"complete"` (accurate — the real merge, step 3g, hasn't happened yet at record time); nothing promotes it to `"merged"` again until a fresh `cmd_init` (a session restart). GLM's own framing still assumed a fresh `cmd_init` WOULD promote `complete -> merged` with a usable `merged_commit`, calling the restart case a "safety net". The 3f-bis doubt-reviewer disproved that too, by grepping the whole non-test tree: no producer anywhere writes `status: "merged"` with a truthy `merged_commit` — the squash-merge SHA-mismatch limitation (bullet above) applies identically on a fresh-init resume, so `verify_merged_commit_ancestry` returns `None` there as well. **`is_unit_ready` is `False` for every `depends_on` edge, on every code path, permanently** — not "safety net only across a restart" but "no working gate on any path until R4/R5b's `cmd_mark_merged` lands." Still worse than pre-R1 for a real single-session campaign that uses `depends_on` (GLM's "live regression" framing stands), and now also worse than the ADR's own original "restart safety net" framing overclaimed. |
| 2, 3, 4 (escalating) | both | high/medium | **Spec-required live `campaign.md` refresh inside `cmd_next` is not implemented.** The plan's "Readiness reads the live campaign.md projection" paragraph names "`cmd_next`'s own narrow guard clause" as a refresh site; the plan's own Work Breakdown item 6 and "Ownership split" section separately state `cmd_next` gets "no new flag/exit code" and that `--campaign-dir` is exclusively R4's `cmd_next_batch`. These two passages are IN TENSION — implementing the refresh without a new flag has no way to locate `campaign.md` from `cmd_next`'s existing arguments (only `--state`, which resolves to `loop_state.json`'s path, not the campaign slug). Built per the more operationally specific text (Work Breakdown + Ownership split); the more general paragraph is, on this evidence, an earlier-draft leftover the plan's own later sections superseded but never deleted. |

**Why neither was fixed here, and why escalation (not silent rejection) is the right
response:** Both gaps are genuine — repeated, independent reviewer convergence
across 4 rounds, with a concrete mechanism traced in each case, is not a
noise. But: (1) the ONE mechanism the plan itself proposes to correctly close
the first gap is `loop_claim.py::cmd_mark_merged` (searched and found in the
plan text, § the corrected merge-time `merged_commit` write) — a NEW,
fencing-validated, hex-SHA-guarded command explicitly assigned to R4/R5b,
requiring exactly the kind of new command + write path R1's own Work
Breakdown says NOT to build here. (2) The "quick fix" GLM itself proposed in
round 4 ("map `complete -> merged` for readiness purposes … trusting
`cmd_record`'s own commit") was evaluated and REJECTED as UNSAFE: it would
let a dependent start building on a sub-iterate that merely finished its OWN
build/tests but has not yet passed PR review or actually merged — exactly
the "wrongly unblocked" failure mode `verify_merged_commit_ancestry`'s own
docstring says must never happen ("worst case is 'stays blocked', never
'wrongly unblocked'"), and directly contradicts this same sub-iterate's own
new campaign-mode.md sentence ("X cannot even START until Y has *merged* —
a full CI + review + merge cycle"). Implementing either gap's fix safely
means doing a meaningful slice of R4's work now, under review pressure,
without R4's own design care (locking semantics, batch processing,
`cmd_mark_merged`'s fencing token). **Campaign owner decision (this run,
3f-bis, corrected after the doubt-reviewer's sharper finding):** `depends_on`
gating is currently inert on EVERY path, not merely a cross-restart safety
net — there is no working benefit to trade away by deferring. This
campaign's own R2-R6 sub-iterates do not populate `depends_on` (this
bootstrap campaign runs on today's plain FIFO order per campaign.md's own
stated build order), so nothing in THIS run relies on the gate. Decision:
**accept the gap through R4/R5b** rather than pull `cmd_mark_merged` forward
into an R1.5 — R1 ships as schema + validators + a correctly fail-closed
(never wrongly-unblocks) predicate only; docs corrected in the same diff to
stop claiming a working resume benefit. Filed as `trg-b085c323` for R4/R5b
planning.

**Round 5 correction (post-merge-attempt, external Tier-3 PR review on the
live GitHub gate, `openai/gpt-5.6-luna`): the "accepted gap" framing above
was itself insufficient — BLOCK, not advisory.** The reviewer read this exact
row and rejected the premise that leaving the orchestrator's documented exit-2
action as unconditional Finalize was a deferrable scoping decision: it is a
live correctness bug for `cmd_next`'s OWN current callers (this very
autonomous campaign session, and any `depends_on` campaign run before R4/R5b
lands), not merely a future one. Fixed in this same commit, still without
pulling any R4 work forward: `campaign-mode.md` step 3a now checks the JSON's
`blocked_pending_ids` before Finalize and STOPs (reporting `blockers`)
instead when non-empty — closing the "silently finalizes UNBUILT work"
symptom without touching `cmd_next`'s exit code, `is_unit_ready`, or any of
R4's own work. This narrows, but does not remove, the accepted gap above:
`depends_on` gating is still inert on every path (a blocked dependent still
never gets BUILT within one session — it now correctly stops the loop
instead of silently finalizing over it). The row above is retained verbatim
as the historical record of what was found and why the ROOT CAUSE fix was
deferred; this note records that the externally-reviewed live-gate SYMPTOM
was not left as documentation alone.

See `reviews.external_code` in `reviews.json` for the recorded pass.

## Confidence Calibration

`touches_io_boundary` fired (risk_recheck.json) and effective complexity is
`medium`, so this step is mandatory (SKILL.md Step 7.5 / this contract's
Step 3.8). Per `references/confidence-anti-patterns.md`, this is empirical
probes, not a self-report.

**Boundaries touched:** (1) `campaign.md` — human-edited markdown table;
producer = `campaign_init.py` / an operator's hand-edit, consumer =
`parse_campaign_skeleton` / `project_campaign_status`. (2) `status.json` /
`loop_state.json` — JSON, also operator-editable (the frozen-contract
scenario exists specifically because an operator can hand-edit a pending
unit's `depends_on`). (3) the git subprocess boundary — `verify_merged_commit_ancestry`'s
`fetch`/`merge-base` calls.

**Probes run (boundary 1, `campaign.md` — human-edited-format category from
`references/boundary-probes.md`):**

| Probe | Result |
|---|---|
| UTF-8 BOM, frontmatter-less file (`## Sub-Iterates` as the literal first line) | **FINDING** — BOM broke `stripped.startswith("## ")` section detection entirely, raising a confusing "no table rows" error. |
| UTF-8 BOM, realistic file (frontmatter present) | Clean — BOM lands on a frontmatter line, which is skipped either way. |
| CRLF line endings throughout | Clean — `.strip()` on each cell already absorbs a stray `\r`. |
| Non-ASCII id + dependency (`Ā`, `Fïrst`) | Clean — round-trips byte-for-byte. |
| Whitespace-only `Depends On` cell | Clean — correctly yields `[]`, not `[""]`. |
| Markdown emphasis + irregular spacing (`**A**,  B`) | Clean (pre-existing coverage). |

**Asymptote applied:** first probe (frontmatter-less BOM) found a real bug
→ fixed (`parse_campaign_skeleton` now `lstrip("﻿")`s the whole text
up front) → reprobed ALL SIX cases again → all clean. Two consecutive
clean results (the immediate reprobe, plus every other category passing on
its first attempt) — exhausted for this boundary.

**Boundary 2 (JSON state files):** round-trip already covered by
`test_campaign_dag_integration.py` (real `tmp_path` files, state reloaded
from disk across a simulated resume) plus the new
`test_schema_invalid_loop_state_units_does_not_crash` /
`test_units_not_a_list_does_not_crash` probes (Step 3.7 finding) proving a
malformed `loop_state.json` degrades safely rather than crashing.

**Boundary 3 (git subprocess):** `resolve_default_branch`'s existence and
successful import verified empirically (direct `python -c` import in this
session, not just read) — this is what let a 4-round-repeated external
review finding be rejected with actual evidence rather than a repeated
assertion. `verify_merged_commit_ancestry`'s failure modes (no commit,
non-hex commit, failed fetch, ancestor-not-found, timeout, no
`resolve_default_branch`) are exercised via mocked subprocess in
`test_loop_state.py` — no real-git-repo probe was run for this boundary
(edge-cases-not-probed, below); the fail-safe direction (any uncertainty ->
`None` -> stays blocked, never falsely unblocks) is what makes this an
acceptable, bounded gap rather than a live risk.

**Edge cases not probed, and why acceptable:** a real local git repository
exercising `verify_merged_commit_ancestry`'s actual `fetch`/`merge-base`
subprocess calls (vs. mocked) — external code review (round 3/4, GLM) named
this too. Not probed here: constructing a reliable, cross-platform
(Windows CI) local-remote git fixture is nontrivial scope creep beyond this
already-large sub-iterate, and the function's fail-safe design means an
unprobed real-git edge case degrades to "stays blocked" (safe), never
"wrongly unblocked" (unsafe) — the asymmetry this whole mechanism is built
around. Flagged as a good candidate for R4/R5b's own test suite, which
will need real-git fixtures anyway for `cmd_mark_merged`'s fencing-token
logic.

Recorded in the final result JSON's `reviews.confidence_calibration`
(not `record_review_pass.py`'s `reviews.json` — that tool's `--review-type`
enum has no `confidence_calibration` slot; this section + the result JSON
are the durable record for this step).

## Rejected alternatives

Per the sub-iterate spec: storing `depends_on` only in `status.json` (skip
the `campaign.md` column) was rejected — `campaign.md` is what the operator
and the design conversation read/edit; the source of truth belongs there.
