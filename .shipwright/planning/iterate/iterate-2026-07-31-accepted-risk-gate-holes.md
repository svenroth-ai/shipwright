# Iterate Spec: accepted-risk gate holes

- **Run ID:** iterate-2026-07-31-accepted-risk-gate-holes
- **Type:** bug
- **Complexity:** medium
- **Status:** draft

## Goal

Close two holes through which the accepted-risk drift gate reports success
while real security suppressions stay live and unrecorded: (1) `check` returns 0
whenever the register **file** is absent, before it looks at any suppression, so
deleting the file silences the gate; (2) the ignore-file reader counts an entry
whose own scanner-side expiry has already lapsed as an active suppression, so
renewing only the register's date makes the gate report "reconciled" while Trivy
has already stopped suppressing.

Filed from shipwright-webui, where this gate was first wired into CI
(webui PR #332), as SecFix-1 and SecFix-3 of a five-item family. Both findings
were cross-checked with Codex, which agreed they are real.

## Root cause

Not a regression — both are original design decisions that turn out to be
unsound in exactly one direction each.

1. **`cmd_check` guards on the wrong predicate.** It asks *"does a register file
   exist?"* when the question the gate exists to answer is *"is every live
   suppression recorded?"*. `load_register` already returns `[]` for an absent
   register (documented: *"absent is not malformed"*), so `reconcile()` handles
   the absent case correctly on its own — the early return in front of it is the
   whole bug. The rationale in the code ("a legacy/fresh repo is not an error")
   is true only for a repo with **no suppressions**, and that case still exits 0
   through the normal comparison. This repo carries a downstream backstop
   (`test_repo_register_is_loadable_and_non_empty`), but a change that deletes
   the register *and* that test passes today — which is why a backstop is a
   workaround, not a fix.

2. **`read_trivyignore_ids` reads the id and drops the expiry.** Trivy honours a
   per-entry due date in both ignore-file forms — `expired_at: YYYY-MM-DD` in
   the YAML form and an `exp:YYYY-MM-DD` field in the classic flat form — and
   stops suppressing once it passes (`pkg/result/ignore.go`:
   `!finding.ExpiredAt.IsZero() && finding.ExpiredAt.Before(clock.Now(ctx))`).
   The reader keeps every entry regardless, so a lapsed suppression still reads
   as "in effect" — contradicting the module's own docstring, *"the suppressions
   that are actually in effect"*. The flat form is doubly wrong: it never splits
   the `exp:` field off, so the whole line becomes the id.

## Acceptance Criteria

- [ ] **AC-1** `accepted_risks_cli.py check` on a repo with a live suppression
      (`SHIPWRIGHT_SEMGREP_EXCLUDE_RULES: some.live.rule`) and **no**
      `shipwright_accepted_risks.yaml` exits `1` and prints `UNRECORDED` naming
      `some.live.rule`. (Today: exits `0` and prints "nothing to reconcile".)
- [ ] **AC-2** `check` on a repo with **no** register and **no** suppressions
      still exits `0` — a genuinely fresh/legacy repo is not made red.
- [ ] **AC-3** `read_trivyignore_ids` on a `.trivyignore.yaml` holding
      `id: CVE-X` with `expired_at` = yesterday returns `set()`; the same entry
      with `expired_at: 2099-01-01` returns `{"CVE-X"}`.
- [ ] **AC-4** `check` with a register entry whose `rule` names a lapsed
      trivyignore id exits `1` and prints `STALE` for that id. (Today: exits `0`
      and prints "no drift".)
- [ ] **AC-5** `read_trivyignore_ids` on a classic flat `.trivyignore`
      containing `CVE-LAPSED exp:<yesterday>`, `CVE-LIVE exp:2099-01-01` and a
      bare `CVE-NOEXP` returns exactly `{"CVE-LIVE", "CVE-NOEXP"}`.
      (Today: returns all three lines verbatim, `exp:` suffix included.)
- [ ] **AC-6** `accepted_risk_rows(root, now=T)` derives discovery from `T`, not
      wall-clock: for a register entry backed by a trivyignore entry expiring
      `2026-12-22`, `now=2026-06-22` yields `source == "registered+active"` and
      `now=2027-01-01` yields `source == "registered"`.
- [ ] **AC-7** `check --project-root .` on **this** repo still exits `0` — the
      four live suppressions stay reconciled against the four register entries.
- [ ] **AC-8** Expiry-aware discovery must not blank the dashboard. With only a
      lapsed `.trivyignore` entry present, `accepted_risk_rows` still returns
      exactly one row for it, `expired=True`, `source="unregistered"` — the
      `EXPIRED — re-review` signal survives. *(Added after the Stage-1 spec
      review: this was implemented and documented as a contract while living
      only in a code comment. See "Dashboard visibility" below.)*
- [ ] **AC-9** The two flat-form parsers agree on the id. For
      `CVE-A exp:2099-01-01`, `accepted_risk_scan.read_trivyignore_ids` and
      `accepted_risk_view.parse_trivyignore` both yield `CVE-A`, so one
      suppression renders as exactly one dashboard row — and a lapsed flat entry
      renders with its date and `expired=True`.
- [ ] **AC-10** A `STALE` line caused by a *lapsed* ignore entry tells the
      operator to renew both dates and does **not** print "remove the register
      entry"; a `STALE` line caused by a genuinely removed suppression still
      does. *(Added after the Stage-2 review: this repo's own paired dates
      collide on 2026-12-22 and 2027-01-28, so the wrong advice would have been
      printed on a schedule.)*
- [ ] **AC-11** On a Trivy entry's `expired_at` date itself, an **unregistered**
      dashboard row reports `expired=True` — agreeing with the gate, which has
      already stopped counting the suppression that day.

> **Scope of AC-8 and AC-11: unregistered rows only.** A *registered*
> acceptance is rendered from the register alone (`expires`,
> `entry.is_expired(now)`), so the ignore file's `expired_at` never reaches that
> row; on the day its ignore entry lapses it flips to `source="registered"`
> ("recorded, suppression not active") but carries no EXPIRED flag. The Stage-3
> review found this and it is **disclosed, not fixed**: giving that row its own
> status is new dashboard vocabulary, which is the SecFix-5 conversation. It is
> also now unreachable in this repo, because the paired dates were offset (see
> below) so a recorded acceptance and its ignore entry lapse on the same day.

## Dashboard visibility (recorded after Stage-1 review)

The naive form of fix 2 — letting the dashboard's unrecorded rows come from
expiry-aware discovery — deletes a lapsed entry from the dashboard on the day it
starts to matter. That is the opposite of what the register was built for: the
`accepted_risks` module docstring names `.trivyignore.yaml`'s `expired_at` as the
one channel that ever carried a due date, "surfaced by the compliance dashboard
as `EXPIRED — re-review`".

So the two consumers deliberately get **different** answers from the same data,
and this is the decision, not an accident:

- the drift **gate** asks *"what is Trivy suppressing right now?"* → a lapsed
  entry is absent (that is finding 2);
- the **dashboard** asks *"what acceptances exist and what state are they in?"* →
  a lapsed entry is still listed, flagged `EXPIRED`. Discovery still decides
  `source` there, i.e. whether a *recorded* acceptance is actually wired up.

The Stage-1 reviewer was right that this exceeded the mini-plan's declared "one
line" and belonged in the spec rather than in a comment. Recording it also
exposed the real defect it had introduced — AC-9.

## Spec Impact

- **Classification:** none
- **ADD** (new FR appended): none
- **MODIFY** (existing FR changed): none
- **REMOVE** (FR retired): none
- **NONE justification:** **The behaviour this change alters is not covered by
  any FR.** No FR covers the accepted-risk register — its tests sit in
  `test-traceability.json` `untagged_tests` — so there is no requirement to link
  and none to amend.

  Stated that way deliberately. An earlier draft justified `none` as "no
  specified behaviour changes, only the implementation catching up to its
  documented contract", and the Stage-3 doubt review was right that this is
  false as written: AC-1 turns an input class that exited `0` into one that
  exits `1`, and the change moves the date on which this repo's own CI would go
  red. The classification is still correct — the FR-gate's bar is *"alters an
  FR's observable behaviour"* — but the reason on the record has to be the true
  one, because that sentence is what a later auditor reads.

## Out of Scope

- **SecFix-5** — that inline per-site suppressions (`# nosemgrep`) have no entry
  type in the register's `target` vocabulary. Filed separately and explicitly
  NOT autonomous: it is a schema decision with reach beyond this repo. Folding
  it in would put an unanswered question inside an unattended run.
- **SecFix-4** — re-vendoring these modules into shipwright-webui, which pins
  them by hash manifest and verifies nothing upstream. Tracked in the webui
  triage and must FOLLOW this item. **Two things it must carry, or it breaks:**
  (1) `accepted_risk_scan` now imports `coerce_date` from `accepted_risks`, a
  symbol that did not exist before — re-vendor **both files together** or the
  import fails; in the dashboard `_load_shared()` swallows that ImportError and
  silently falls back to the degraded branch, which labels every `.trivyignore`
  entry `registered+active` with no register cross-check at all. (2) webui
  should adopt the paired-date offset rule and
  `test_ignore_entries_outlive_their_register_entry` with it, or it inherits the
  same dated red.
- Reconciling the one-day boundary difference between the register's own
  `expires` (active *on* the due date) and Trivy's `expired_at` (lapsed *from*
  the due date). Real, pre-existing, and independent of these two holes.
- Tagging the accepted-risk tests with an FR (separate backfill brief).
- **Trivy's other ignore-file sections.** Both parsers read `vulnerabilities:`
  and nothing else; `.trivyignore.yaml` also accepts `misconfigurations:`,
  `secrets:` and `licenses:`. A consuming repo using one of those has a live,
  source-controlled suppression on the `trivy-ignore` channel that this gate
  does not see — the same "stays live and unrecorded" shape this iterate closes,
  in the same file. Not reachable here (this repo scans `--scanners vuln` only,
  `oss_backend.py`), pre-existing, and widening what the gate covers is its own
  change. **Named because the Stage-3 review found it unnamed**, which for a gap
  of exactly this shape is worse than leaving it open.
- **A registered acceptance whose ignore entry has lapsed renders without an
  EXPIRED flag** on the dashboard — see the note under AC-11.
- **The failure contract for an unreadable / structurally invalid ignore file**
  (external review, GPT #3). `read_trivyignore_ids` returns `set()` on both
  `OSError` and `YAMLError` today. That is a deliberate, documented and
  separately-tested decision — the block above
  `test_malformed_trivyignore_yaml_yields_nothing` states the reasoning: paired
  with a register entry it surfaces as `STALE` rather than as clean. This
  iterate neither relies on nor worsens it (the behaviour is byte-identical
  before and after), and changing it is a third finding, not part of either
  briefed one. Surfaced in the F12 summary so it can be filed on its own.

## Design Notes

n/a — no UI surface to mock up. The change is a CLI gate, three library modules
(`accepted_risks`, `accepted_risk_scan`, `accepted_risk_view`) and the
accepted-risk section the last of those renders into the compliance dashboard.
That rendered section is markdown produced by code, not a designed screen, and
its behaviour is pinned by AC-8/AC-9 rather than by a design check.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| operator hand-edit → `.trivyignore.yaml` / `.trivyignore` (also consumed by `oss_backend._run_trivy --ignorefile`) | `accepted_risk_scan.read_trivyignore_ids` | YAML / flat text |
| **the same two files** | **`accepted_risk_view.parse_trivyignore`** — a SECOND, independent parser (ADR-045: it must stay readable with no `shared/scripts` on `sys.path`) | YAML / flat text |
| operator hand-edit → `shipwright_accepted_risks.yaml` | `accepted_risks.load_register` | YAML |
| `.github/workflows/security.yml` `env:` block | `accepted_risk_scan.read_workflow_env` | GitHub-Actions YAML |

**One format, two consumers — the row this table was missing.** The Stage-1
reviewer caught that omission, and it was load-bearing: fixing only
`read_trivyignore_ids` made the two parsers disagree about what an id even *is*
for a flat entry carrying `exp:`, so one suppression rendered as two dashboard
rows and a lapsed flat entry rendered as not-expired. Both parsers are now
aligned and pinned equal by `test_both_parsers_agree_on_the_id` +
`test_the_two_differ_only_by_dropping_lapsed_entries`, the same way
`DECISION_REF_RE` is pinned against its `ci_supplychain` copy.

`touches_io_boundary` fires: this change alters how a hand-authored, third-party
file format is parsed. Boundary Probe sub-step is mandatory.

## Confidence Calibration

- **Boundaries touched:** the four rows above, which are **three** distinct
  formats — the two Trivy ignore-file forms (read by TWO independent parsers,
  hence two rows for one format), the register YAML (read), and the workflow
  env block (unchanged).

- **Empirical probes run:** *(pre-fix RED baseline, `scratchpad/probe_baseline.py`)*
  - **P0** — `check` on this repo today: `4 register entries, 4 suppressions
    reconciled. no drift.` exit 0. Baseline is green, so any red below is the
    probe and not pre-existing debt.
  - **P1** — register deleted, two live suppressions present: exit `0`,
    "nothing to reconcile", while `discovered_suppressions` in the same
    breath returns `{'trivy-ignore': ['CVE-2026-9999'], 'semgrep-rule-exclusion':
    ['some.live.rule']}`. **Hole 1 confirmed: the gate sees the suppressions and
    reports success anyway.**
  - **P2** — trivyignore `expired_at` = yesterday, register renewed to 2099:
    exit `0`, "1 register entry, 1 suppression reconciled. no drift." **Hole 2
    confirmed: reconciled against a suppression Trivy has stopped applying.**
  - **P3** — flat `.trivyignore` with Trivy's documented `exp:` field:
    `read_trivyignore_ids` returned `['CVE-LAPSED exp:2026-07-30', 'CVE-LIVE
    exp:2099-01-01', 'CVE-NOEXP']`. **Bonus finding: the flat reader neither
    honours nor strips `exp:`, so the id itself is wrong.** In scope — it is
    hole 2 in the other spelling of the same file.
  - **P4** — Trivy's own boundary semantics read from source, not memory
    (`pkg/result/ignore.go`, `getExpirationDate` parses `exp:` with layout
    `2006-01-02`; `Prune` skips on `ExpiredAt.Before(now)`). Because the date
    parses to midnight, an entry stops suppressing **from** its `expired_at`
    date, i.e. `expired_at <= today` in date terms. Mirrored exactly.
  - **P5** *(post-fix)* — round-trip over both real file formats plus the
    live repo: P1 → exit 1 naming both suppressions UNRECORDED, P2 → exit 1
    STALE, P3 → `['CVE-LIVE', 'CVE-NOEXP']`, and this repo's own gate still
    `no drift` / `none past due` (AC-7).
  - **P6** *(Stage-1 review follow-up)* — composed the fixed reader with the
    dashboard's own parser on a flat entry `CVE-X exp:2099-01-01`:
    `read_trivyignore_ids` → `['CVE-X']` but `parse_trivyignore` →
    `['CVE-X exp:2099-01-01']`, so `accepted_risk_rows` emitted **two rows for
    one suppression**; and a lapsed flat entry rendered
    `('CVE-Y exp:2020-01-01', '', False)` — no date, not expired. **The
    reviewer's blocking finding reproduced exactly, and was worse than
    reported.** Fixed under AC-9.

- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | Absent register + live suppression → exit 1, `UNRECORDED` | tested | `test_absent_register_does_not_silence_live_suppressions` |
  | 2 | Absent register + no suppression → exit 0 | tested | `test_absent_register_without_suppressions_is_still_clean` |
  | 3 | Absent register is named in the operator output | tested | `test_check_without_register_says_so_and_still_reconciles` |
  | 4 | Deleting register + backstop test still fails the gate | tested | `test_deleting_the_register_cannot_silence_this_repos_gate` |
  | 5 | YAML `expired_at` lapsed → id absent from discovery | tested | `test_lapsed_yaml_entry_is_not_an_active_suppression` |
  | 6 | YAML `expired_at` future/absent → id discovered | tested | `test_unexpired_and_undated_yaml_entries_stay_active` |
  | 7 | Lapse boundary matches Trivy (`<=` today) | tested | `test_expiry_boundary_matches_trivys_own_rule` |
  | 8 | Lapsed trivy entry + register entry → `STALE`, **and `cmd_check` exits 1** | tested | `test_renewing_only_the_register_is_reported_as_stale` (asserts both `reconcile()["stale"]` and `cmd_check() == 1`; the exit-code half was added after the Stage-1 review found the row over-claimed its evidence) |
  | 9 | Flat `exp:` lapsed dropped, live kept, bare kept | tested | `test_flat_trivyignore_honours_trivys_exp_field` |
  | 10 | Flat id is the first field, not the whole line | tested | `test_flat_trivyignore_id_excludes_the_exp_field` |
  | 11 | Unparseable expiry → entry stays active (fail-safe) | tested | `test_unparseable_expiry_keeps_the_entry_active` |
  | 12 | `discovered_suppressions` honours an injected `now` | tested | `test_discovery_honours_an_injected_now` |
  | 13 | Dashboard rows derive discovery from the passed `now` | tested | `test_discovery_is_computed_against_the_passed_now` |
  | 14 | This repo's own gate stays green | tested | `test_main_check_passes_on_this_repo` (existing) |
  | 15 | Flat form: blank / whitespace-only lines yield no id (no `IndexError`) | tested | `test_flat_trivyignore_skips_blank_and_comment_lines` |
  | 16 | Flat form: a comment-only line is never read as an id | tested | `test_flat_trivyignore_skips_blank_and_comment_lines` |
  | 17 | Expiry parses from both a PyYAML `date` and a flat-file `str` | tested | `test_expiry_is_read_from_both_a_yaml_date_and_a_string` |
  | 18 | Malformed / unreadable ignore file still yields `set()` (unchanged) | tested | existing `test_malformed_trivyignore_yaml_yields_nothing`, `test_unreadable_flat_trivyignore_yields_nothing` |
  | 19 | With no `now` passed, discovery defaults to today (wall-clock path) | tested | `test_discovery_defaults_to_today` |
  | 20 | Expiry never filters the semgrep channels (they have no due date) | tested | `test_expiry_does_not_reach_the_semgrep_channels` |
  | 21 | A lapsed entry is still SHOWN on the dashboard, flagged expired (AC-8) | tested | `test_a_lapsed_suppression_is_still_shown_not_dropped` |
  | 22 | Both flat-form parsers agree on the id; one entry → one row (AC-9) | tested | `test_both_parsers_agree_on_the_id`, `test_a_flat_entry_with_an_expiry_renders_exactly_one_row` |
  | 23 | A lapsed FLAT entry renders its date and `expired=True` (AC-9) | tested | `test_a_lapsed_flat_entry_is_flagged_expired` |
  | 24 | A lapsed entry's STALE advice says renew-both, never remove-the-record (AC-10) | tested | `test_a_lapsed_entry_is_told_to_renew_not_to_delete` |
  | 25 | A genuinely removed suppression keeps the original remove-the-record advice | tested | `test_a_genuinely_removed_suppression_still_says_remove` |
  | 26 | The dashboard flags a Trivy entry expired ON its date, agreeing with the gate (AC-11) | tested | `test_on_its_lapse_date_the_dashboard_agrees_with_the_gate` |
  | 27 | Both flat parsers agree on the id across 10 input shapes (tabs, empty `exp:`, double `exp:`, comment-only, blank) | tested | `test_both_parsers_agree_on_the_id` (parametrized) |
  | 28 | This parser reads id + expiry correctly for those same 10 shapes | tested | `test_flat_line_parses_to_its_id_and_expiry` (parametrized) |
  | 29 | The only permitted parser divergence is a dropped lapsed entry | tested | `test_the_two_differ_only_by_dropping_lapsed_entries` |

  | 30 | A paired ignore entry outlives its register entry (no dated red) | tested | `test_ignore_entries_outlive_their_register_entry` |
  | 31 | An unparseable ignore file never advises deleting register records | tested | `test_an_unparseable_ignore_file_does_not_advise_deleting_records` |
  | 32 | A missing ignore file is not reported as unreadable | tested | `test_a_missing_ignore_file_is_not_called_unreadable` |
  | 33 | Lapsed advice is scoped to the Trivy channel | tested | `test_lapsed_advice_is_scoped_to_the_trivy_channel` |
  | 34 | Both parsers agree on YAML-form ids (incl. skipping an id-less entry) | tested | `test_yaml_form_ids_agree_with_the_shared_reader` |
  | 35 | YAML expiries: only the lapsed id is dropped by the gate's filter | tested | `test_yaml_form_expiries_agree_with_the_shared_readers_filter` |
  | 36 | A duplicate id folds onto the LATEST expiry, not last-wins | tested | `test_a_duplicate_id_folds_onto_the_latest_expiry` |
  | 37 | An undated duplicate never lapses | tested | `test_an_undated_duplicate_never_lapses` |
  | 38 | The view's third `_coerce_date` copy matches the shared one | tested | `test_the_views_date_parser_matches_the_shared_one` |

  *(Rows 24-29 were added after the Stage-2 code review; 24-26 close its two
  medium findings, 27-29 replace a pin it showed was weaker than it looked.
  Rows 30-38 were added after the Stage-3 doubt review — 30-31 close its two
  high doubts, the rest close mediums 4-6.)*

  *(Rows 19-23 were added after the Stage-1 spec review: rows 19-20 existed as
  tests but were unledgered, and 21-23 cover behaviour that had been
  implemented without an AC behind it. The breadth claim below is counted from
  the table, not asserted independently of it.)*

- **Confidence-pattern check:**
  - *Asymptote (depth):* **this run hit the pattern twice, so it got two extra
    probes.** P3 surfaced a third defect after the two briefed ones, prompting
    P4 (reading Trivy's source rather than trusting recall). Then the Stage-1
    spec review rejected a spec I had already called complete, naming a defect
    the whole test suite was green over — so P6 was run rather than reasoning
    about the claim. It reproduced immediately (two rows for one entry; a
    lapsed flat entry rendering `expired=False`), which is the asymptote rule
    working as intended: a green suite is evidence about the assertions that
    exist, never about the ones nobody wrote.
  - *Coverage (breadth):* 38 rows, all `tested`, 0 untested-testable.
  - *Asymptote, four rounds:* every review stage found real defects over a
    fully green suite — Stage 1 a duplicate-row bug I had introduced, Stage 2
    two dated mediums, Stage 3 two highs including a CI break this diff plants
    on **2026-12-22** in this repo's own main. At no round was "the suite is
    green" evidence that the next reviewer would find nothing, and each round's
    finding was invisible to the previous one's lens. Recorded because the
    pattern is the finding: the last two defects were **date-triggered**, a
    class no amount of running the suite today can surface.
  - *Integration composition:* `cross_component` does not fire — no
    merge/churn/event-log resolver, no hook, no phase validator, no campaign
    drain is touched.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run pytest shared/tests/test_accepted_risks_register.py shared/tests/test_accepted_risks_repo_guards.py shared/tests/test_accepted_risk_scan.py shared/tests/test_accepted_risks_cli.py shared/tests/test_accepted_risks.py -v`
- **Evidence path:** `.shipwright/runs/iterate-2026-07-31-accepted-risk-gate-holes/surface_verification.json`
- **Justification (only if surface=none):** n/a — the gate IS a CLI, and its
  tests drive the real entry point in a subprocess (`_run`), so the runner
  exercises the shipped surface rather than a library shim.

### Why the runner names one root, and where the second one is gated

Both external reviewers flagged that this command omits
`plugins/shipwright-compliance/tests` (GPT #1 medium, Gemini #1 high), which is
where AC-6 — the `now`-threading — lands. The finding is correct and is resolved
here rather than waived:

- It **cannot** be folded into the runner. `--runner` is single-valued
  (`surface_verification.py` `add_argument("--runner")`, no `append`), it is
  executed without a shell (so no `&&`), and naming both roots in one pytest
  process is refused by the repo-root `conftest.py` with exit 4 (ADR-044).
  Any command that satisfied the reviewers literally would fail closed.
- So the compliance root is gated at **F0** instead, which is a STOP-on-failure
  full-suite gate that runs before commit, and its result is recorded in
  `shipwright_test_results.json`. That makes the plugin invocation an explicit
  blocking completion condition — the reviewers' actual ask — just at the phase
  that is allowed to hold more than one root.
- **AC-6 is additionally pinned inside the F0.5 root** at the seam this iterate
  owns: `test_discovery_honours_an_injected_now` proves
  `discovered_suppressions(root, now=T)` derives from `T`, in `shared/tests`.
  The compliance test then only has to prove the view passes `now` down.

Net: no assertion in this change is verified by fewer than one blocking gate,
and the split is disclosed rather than implied.

## Internal Code Review (Stage 2) — dispositions

`code-reviewer` returned 2 medium + 7 low, bloat/reducibility PASS. Both mediums
were **dated defects in this repo**, not hypotheticals, and both are fixed:

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | med | The STALE message's advice is wrong for the lapsed cause. This repo's register `expires` and `.trivyignore.yaml` `expired_at` are set to the SAME day (2026-12-22, 2027-01-28), and those lapse a day apart, so on each renewal day CI goes red telling the operator to *"remove the register entry"* — deleting an acceptance that is doing its job, the exact outcome `_is_lapsed`'s fail-safe exists to prevent | **Fixed.** `reconcile()` now returns `lapsed` (computed with `now=date.min` to disable the filter); `_format_check` emits cause-specific advice. Pinned by `test_a_lapsed_entry_is_told_to_renew_not_to_delete` **and** `test_a_genuinely_removed_suppression_still_says_remove` so the original advice cannot regress |
| 2 | med | The dashboard applied the REGISTER's boundary (`< now`) to a TRIVY date, so on the lapse day it reported `expired=False` about a suppression the gate had already dropped — a new inter-consumer disagreement, on the one day the flag matters most | **Fixed.** `<=` for Trivy-sourced dates at both sites (normal + degraded path), commented in place. Pinned by `test_on_its_lapse_date_the_dashboard_agrees_with_the_gate` |
| 3 | low | `assert theirs <= mine` is weaker than it looks (holds for empty `theirs`); the real pin rested on one 5-line fixture | **Fixed.** Replaced with a 10-case parametrized table run against BOTH parsers (`_FLAT_CASES`), covering tab separation, `exp:` with no date, two `exp:` fields, comment-only and blank lines; plus `test_the_two_differ_only_by_dropping_lapsed_entries` stating the one permitted divergence as `mine - theirs == {lapsed}` |
| 4 | low | `"trivy-ignore"` hardcoded where `TARGET_TRIVY_IGNORE` was in scope; a vocabulary rename would silently split the dashboard's rows into two buckets | **Fixed.** Uses the constant for both the `setdefault` key and the lookup |
| 5 | low | `test_deleting_the_register_cannot_silence_this_repos_gate` would fail with a message asserting a precondition that had become false | **Fixed.** The premise is now asserted first, with its own message |
| 6 | low | The "mirrors Trivy exactly" claim omits that Trivy uses local time and this uses UTC | **Fixed.** Caveat recorded in `_is_lapsed` |
| 7 | low | Unparseable `expired_at` is over-counted in the YAML form (Trivy rejects the whole file, suppressing nothing) | **Documented, not changed.** Sits inside the disclosed out-of-scope failure contract; pointer added at the source so the follow-up has an anchor |
| 8 | low | Two tests renamed and a new test file added; `test-traceability.json` lists tests by node id | **Handled at finalization** — the compliance regeneration at F5b rewrites it; verified below |
| 9 | low | Two consecutive doc paragraphs both open on the dashboard | **Fixed.** Folded into the existing paragraph |

**File-size consequence.** Fixes 3 and 5 pushed two test files over the 300-line
cap, so each was split along the same seam the shared side already uses — the
gate/correlation half stays put, the parsing half moves to a file named for the
module it exercises (`test_accepted_risk_view_parsing.py`; and the discovery
edge cases moved from `test_accepted_risks_register.py` into
`test_accepted_risk_scan.py`). Every touched file is back under the cap.

## Adversarial Doubt Review (Stage 3) — dispositions

`doubt-reviewer` raised 12 doubts (2 high, 3 medium, 7 low) and disproved two of
its own attack lines honestly (it could not break the flat-form parser agreement
across 10+ input shapes, and could not find a repo the absent-register change
surprises — no workflow or pipeline phase invokes this gate against a user
project). The rest stood.

| # | Sev | Doubt | Disposition |
|---|---|---|---|
| 1 | **high** | The one-day divergence is **created** by this diff, not pre-existing, and plants a dated CI break: this repo pairs `expires: 2026-12-22` with `expired_at: 2026-12-22`, so on 2026-12-22 `check` exits 1 with STALE while `expire` reports nothing due | **Confirmed by probe and fixed.** Reproduced exactly (`2026-12-22: STALE=['CVE-2026-54285'] expire-overdue=[]`). `.trivyignore.yaml` dates offset by one day (→ 2026-12-23 / 2027-01-29) with an in-file comment forbidding re-alignment, and pinned repo-wide by `test_ignore_entries_outlive_their_register_entry`. The Out-of-Scope bullet claiming it was pre-existing is corrected |
| 2 | **high** | STALE has a **third** cause: an unparseable ignore file yields `set()`, so every Trivy acceptance reads STALE and gets "remove the register entry" — destroying real records over a YAML typo | **Fixed.** `reconcile()` returns `ignore_unreadable` (file present but zero entries); `_format_check` prints a syntax-first message that explicitly says *do not remove register entries*. Pinned by `test_an_unparseable_ignore_file_does_not_advise_deleting_records` + `test_a_missing_ignore_file_is_not_called_unreadable` |
| 3 | med | AC-8/AC-11 hold only for UNRECORDED rows; a *registered* acceptance renders from the register alone, so on its lapse day it loses the EXPIRED flag while CI is red | **Narrowed and disclosed.** ACs now say "unregistered rows only", with a note stating what a recorded lapsed acceptance renders as and why fixing it is SecFix-5 vocabulary. Doubt 1's date offset makes it unreachable here |
| 4 | med | The parser pin is flat-only; the **YAML** branch is duplicated too and is the form this repo uses. `view._coerce_date` is a third unpinned copy, now load-bearing for the `<=` boundary | **Fixed.** Added `test_yaml_form_ids_agree_with_the_shared_reader`, `test_yaml_form_expiries_agree_with_the_shared_readers_filter`, and `test_the_views_date_parser_matches_the_shared_one` (8-value table) |
| 5 | med | `trivy_by_id` collapses duplicate ids last-wins; Trivy legitimately repeats an id per `paths`, so a lapsed narrow entry can render a still-suppressing id as EXPIRED | **Fixed.** Folds onto the LATEST expiry (an undated entry wins outright). Pinned by `test_a_duplicate_id_folds_onto_the_latest_expiry` + `test_an_undated_duplicate_never_lapses` |
| 6 | low | The `lapsed` lookup ignores `target`, so a semgrep rule colliding with a Trivy id would get Trivy-only advice; same shape in the view's `trivy_by_id` lookup | **Fixed** at both sites. Pinned by `test_lapsed_advice_is_scoped_to_the_trivy_channel` |
| 7 | low | The `date.min` comment is literally false (`date.min <= date.min`), and it is a second, racy read | **Comment corrected** to "predates every date a repo would realistically write". The second read is retained: it is two reads of a file in the same process milliseconds apart, and CI is the only caller |
| 8 | low | `misconfigurations:` / `secrets:` / `licenses:` sections are invisible to the gate | **Named in Out of Scope** with its reach and why it is unreachable here |
| 9 | low | New cross-module symbol `coerce_date` breaks a partial re-vendor; `_load_shared()` swallows it into the degraded branch | **Recorded on the SecFix-4 handoff** as a must-carry, with the degraded-branch consequence spelled out |
| 10 | low | Three references point at `test_flat_form_agrees_with_the_shared_reader`, which Stage 2 replaced — the anti-drift comment points a reader at nothing | **Fixed** in all three places |
| 11 | low | The Stage-2 premise assertion is repo-wide, so from 2026-12-22 the test silently stops exercising the Trivy leg | **Fixed** — asserted per channel |
| 12 | low | The `spec_impact=none` justification is defensible but states a false reason; and the degraded-path `<` → `<=` flip is unpinned | **Justification rewritten** to the true reason. The degraded-path flip is now covered by `test_the_views_date_parser_matches_the_shared_one` for the parser, and noted as intentionally unpinned for the branch itself (it fires only when `shared/scripts` is unreachable, where there is no gate to agree with) |

## External Review (Step 4 — medium auto)

Provider: openrouter. `openai` = **revise**; `gemini` truncated before its
verdict marker on both attempts (`unavailable`) but returned usable findings
that agree with GPT's. Dispositions:

| # | Reviewer | Sev | Finding | Disposition |
|---|---|---|---|---|
| 1 | GPT + Gemini | med/high | Runner omits the compliance pytest root | **Accepted** — resolved above; F0 gates it, and AC-6's core is additionally pinned in the F0.5 root |
| 2 | GPT + Gemini | med | Flat-file field split breaks on blank / comment-only / whitespace lines (`IndexError`, or `#` read as an id) | **Accepted** — strip the comment first, skip empties, then split; ledger rows 15-16 |
| 3 | GPT | med | No stated failure contract for an unreadable/invalid ignore file | **Out of scope, disclosed** — pre-existing, deliberate, separately tested; unchanged by this diff. See Out of Scope |
| 4 | GPT | low | Doc wording "an absent register no longer passes" contradicts AC-2 | **Accepted** — docs say *"no longer bypasses reconciliation; it passes only when no active suppression is found"* |
| 5 | GPT | low | Resolve `now` once per operation to avoid a midnight split | **Accepted** — `discovered_suppressions` normalises once and passes the same `date` down |
| 6 | Gemini | med | `coerce_date` must stay polymorphic: PyYAML yields `datetime.date`, the flat form yields `str` | **Accepted** — this is precisely why the existing helper is promoted rather than a third parser written; ledger row 17 pins both types |
