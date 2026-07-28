# Iterate: IT-0 Hygiene-Sweep

- **Run ID:** `iterate-2026-07-28-hygiene-sweep`
- **Intent:** CHANGE
- **Complexity:** medium (`prior_source: history`, n=20)
- **Spec Impact:** **NONE** — no FR text changes. This run supplies enforcement
  and recording machinery that existing requirements already promise; the two
  FRs it unblocks (FR-01.17, FR-01.18) keep their text and their ACs verbatim.
- **Consolidates:** `trg-8f022f38` (+ its re-minted successor `trg-965c563e`),
  `trg-17f53a39`
- **Evidence source:** `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`

---

## 1. What this run is for

The consolidation brief made IT-0 the gate in front of IT-3 / IT-5 / IT-7,
on the theory that three anchors each had to write an entry into
`shipwright_bloat_baseline.json` — a file outside `CHURN_ALLOWLIST`
(`shared/scripts/lib/churn_merge.py:71`), so a conflict on it aborts
`resolve_churn_conflicts`.

**That premise was measured before building and is mostly false.** The
serialization is real for exactly one of the three. The rest of the sweep
(H1/H2/F6/D1/D3 + the mis-named deploy gate) stands on its own.

### 1.1 Corrections to the brief (measured 2026-07-28, at `6bb11960`)

| Brief claim | Measured | Verdict |
|---|---|---|
| `plugins/shipwright-iterate/tests/test_classify_complexity.py` (317) — baseline **missing** | entry present since `66ec453d` (Phase 0 inventory), `current=317` | **false** |
| `plugins/shipwright-iterate/agents/sub-iterate-runner.md` (479) — baseline **missing** | entry present since `c81e4b74`, `current=479` | **false** |
| `shared/scripts/tools/record_review_pass.py` (395) — baseline **missing** | no entry; `git log -S` on the baseline finds nothing | **true** |
| `shared/scripts/lib/worktree_isolation.py` = **371** vs recorded 370 | actual = **370**; matches the record exactly | **false** |
| `shared/scripts/tools/triage_gc.py` = 300, a borderline case | 300 is not `> 300`; `bloat_baseline.scan` skips it. No entry needed, and adding one would be noise | **true but not actionable** |
| H1 = **ten** files | **nine**. `gitleaks_config.py` was 307 in the snapshot, is **186** today | **stale** |
| `check_security_scan` "blocks every Bash git-commit; no commit is possible" | fires only when `_is_deploy_command(command)` is true (line 140). It is a **deploy** gate | **false** |

The brief already retracted the "no commit is possible" claim. The measurement
narrows it further: the gate never had anything to do with commits at all.

**Consequence for the dependency graph.** Only **IT-3** was blocked (its file
`record_review_pass.py` is genuinely un-baselined and the Stop hook blocks on
*touching* a non-baselined oversize file). IT-5 and IT-7b were never blocked.
They carry a different, real hazard, recorded here so they are not surprised
by it:

> `test_classify_complexity.py` (317/317) and `sub-iterate-runner.md` (479/479)
> both sit **exactly at their recorded ceiling**. Any line they add ratchets an
> existing entry, which the pre-commit anti-ratchet hook blocks. They must bump
> their own baseline entry in the same commit — and because the baseline is not
> churn-allowlisted, two of them doing that concurrently still conflict.
> Serialization between IT-5 and IT-7b remains advisable; it is just not IT-0's
> job to remove it, because IT-0 cannot.

---

## 2. Scope

Five independent hygiene items. (1)-(3) are data/doc; (4)-(5) are behaviour
changes with tests.

### AC-1 — H1: every oversize file on disk is in the baseline

Nine files exceed their limit with no baseline entry. Add one entry each,
`state: "grandfathered"`, `current` = measured newline count.

| lines | limit | path |
|---:|---:|---|
| 403 | 300 | `shared/tests/test_review_findings.py` |
| 395 | 300 | `shared/scripts/tools/record_review_pass.py` |
| 390 | 300 | `plugins/shipwright-test/tests/test_warning_followups.py` |
| 330 | 300 | `shared/scripts/tools/record_requirement_impact.py` |
| 322 | 300 | `shared/tests/test_audit_e2e_integration.py` |
| 319 | 300 | `shared/tests/test_silent_revert.py` |
| 314 | 300 | `shared/tests/test_section_file_attribution.py` |
| 307 | 300 | `shared/tests/test_review_state_gate.py` |
| 302 | 300 | `plugins/shipwright-changelog/scripts/lib/changelog.py` |

**Verified by:** Group H1 returns `pass`.

*Baselining, not splitting, is the right call here:* eight of the nine are test
modules or record-writers that are long-and-coherent, not bloated
(`shared/glossary.md`: length is not the defect, incoherence is). Splitting them
is a separate judgement per file, and doing nine of those inside a hygiene sweep
would be exactly the "band-aid disguised as architecture" move the constitution
warns about. The baseline is the honest record that they crossed.

### AC-2 — H2: recorded ceilings match what is on disk

Ten entries record a `current` above the file's actual length. Lower each to
the measured value, so the anti-ratchet ceiling is the real one.

| recorded | actual | path |
|---:|---:|---|
| 486 | 485 | `plugins/shipwright-build/agents/section-builder.md` |
| 360 | 359 | `plugins/shipwright-compliance/scripts/lib/compliance_report.py` |
| 451 | 446 | `plugins/shipwright-deploy/skills/deploy/SKILL.md` |
| 306 | 282 | `shared/scripts/hooks/generate_handoff_on_stop.py` |
| 430 | 414 | `shared/scripts/tools/external_review.py` |
| ~~769~~ | ~~767~~ | `shared/scripts/tools/record_event.py` — **reverted, see below** |
| 768 | 737 | `shared/scripts/tools/verifiers/common.py` |
| 315 | 295 | `shared/scripts/tools/verifiers/plan_checks.py` |
| 704 | 696 | `shared/scripts/triage.py` |
| 507 | 492 | `shared/tests/test_verifiers_common.py` |

**Verified by:** Group H2 returns `pass`.

**One tightening was reverted at F11, and it is the interesting result of this
AC.** `record_event.py` measured 767 at this branch's fork point against a
recorded 769, so H2 called it a stale ceiling and the sweep lowered it. While
this run was in flight, PR #490 landed on `main` and restored the file to **769**
— the size the *old* ceiling permitted and the new one forbade. `ensure_current`
then refused to merge `main`: `merge_commit_failed`, anti-ratchet, measured 769 >
baseline 767.

The gate was right and the tightening was wrong. A hygiene sweep must not
retroactively forbid a change that is already reviewed and merged. The entry is
restored to 769, which is both `main`'s real size and, post-merge, this branch's
— so H2 stays green without anyone weakening anything.

**Generalizable:** an H2 `current` is a *low-water mark observed at one instant*,
not a ceiling anybody chose. Tightening every one of them converts ordinary
concurrent work into merge-time anti-ratchet blocks, and the blocked party is the
merge, not the author who grew the file. A file this iterate does not otherwise
touch should be tightened only when the low-water mark is stable. Ten were; this
one was not.

### AC-3 — F6: `CLAUDE.md` is at or under the 200-line hygiene cap

213 lines today. The cap is a *hygiene* signal from `group_f`, separate from the
bloat gate (which files `CLAUDE.md` as a runtime-prompt with a 400 limit — so
the bloat gate is silent here and only F6 fires).

Reduce by moving detail out, not by deleting knowledge: the two longest blocks
are the plugin-cache-sync rationale and the pytest-root-composition rationale,
both of which already have a canonical home elsewhere
(`shared/prompts/writing-plugin.md`, and the linked iterate spec).

**Verified by:** F6 returns `pass`; every rule that was in `CLAUDE.md` is still
reachable from `CLAUDE.md` by one link.

### AC-4 — D1/D3: an iterate's test totals reach its event

**Root cause (measured, not assumed).** D1 counts an FR as covered only when a
`work_completed` event names it *and* carries `tests.total > 0`
(`group_d.py:139`). D3 is the mint-side inverse.

`shared/scripts/tools/finalize_iterate.py` — the F5b writer, and the only writer
in the worktree flow — **builds the event with no `tests` key at all**. Test
totals reach an event only through `record_event.py`'s `--tests-*` flags, which
is the legacy/out-of-band F7 path that the worktree flow deliberately skips.

The trend confirms it is a writer gap, not missing work:

| month | `work_completed` with `tests.total>0` | without |
|---|---:|---:|
| 2026-05 | 57 | 27 |
| 2026-06 | 93 | 60 |
| 2026-07 | **66** | **96** |

The inversion in July is when the worktree flow became the norm.

The two flagged FRs are the visible edge of it — all five events naming them
carry **no** `tests` block:

```
FR-01.17  4 events (1 new_frs, 3 affected_frs)  tests=None on all four
FR-01.18  1 event  (new_frs)                    tests=None
```

Both are delivered and tested (FR-01.17's criteria are pinned by `@FR-01.17`
tags across three test modules; PR #475 landed its (E)6 enforcement). D1/D3 are
reporting the *recorder's* silence as the *project's* gap.

**Change:** `finalize_iterate.py` reads `shipwright_test_results.json` — which
F5 writes immediately before F5b — and populates the event's `tests` block from
it, through the same `validate_tests_block` contract `record_event.py` uses. An
explicit `tests` in `--event-extras-json` still wins; a missing or unreadable
results file leaves the event exactly as it is today (no key, no crash).

**Not in scope:** back-filling the 183 historical events. That is a data
migration with its own evidence burden, and amending events is precisely the
surface `trg-c97faa35` (IT-2) is opening. Fixing the writer stops the bleeding;
IT-2 owns the history.

**Consequence:** D1/D3 will still name FR-01.17 / FR-01.18 after this run,
because no *new* covering event for them exists yet. The next iterate that
names either FR will close them automatically. This is recorded here so the
finding is not mistaken for a failed fix.

**Verified by:** a test proving the event carries the real totals; a test
proving the extras override wins; a test proving a missing results file leaves
the event unchanged.

### AC-5 — the deploy gate gates on security, and says so

`check_security_scan` (PreToolUse, shipwright-compliance) soft-blocks **deploy**
commands. It reads the RTM row `| Unresolved findings | N |`.

That row is `sum(review_findings - review_fixed)` over `work_completed` events
(`rtm_generator.py:622-623`) — **code-review** findings. It is unrelated to the
security scan, which the same compliance tree reports separately and which is
currently green:

```
ci-security.json: critical_gate=pass  open_high_critical=0  critical=0
```

Two defects, both confirmed by measurement:

1. **The name lies about the subject.** An operator hitting this block reads
   "security scan" and goes looking for a vulnerability that does not exist.
2. **The counter is not a repo-wide measure and under-reports by
   construction.** Exactly **4 of 399** `work_completed` events carry a `review`
   block. The whole "66 total / 24 unresolved" comes from those four, and 24 of
   it from two events on 2026-06-08. `review.fixed` is written at F5b, *before*
   the remediation commits exist, and the log is append-only, so the fixed count
   can never catch up.

**Change:**
- Re-hang the gate onto `.shipwright/compliance/ci-security.json` — the actual
  security-scan output, and what the hook's name has always promised.
- Gate on **open criticals only** (`by_severity.critical`), against the existing
  `enforcement.allowed_critical_findings` threshold. *Explicitly not*
  `open_high_critical` (critical + high): the config key is named
  `allowed_critical_findings`, and silently making it license *high* findings
  too would widen any operator's existing setting without their knowledge
  (external plan review, OpenAI #7). High counts ride along in the block details
  as information. If a high-severity gate is wanted later it needs its own key
  and its own decision.
- Fail **closed** on every broken state — unreadable, malformed, not a JSON
  object, not a regular file, `degraded: true`, or a `critical_gate: fail`
  whose count cannot be sized. Fail open **only** when the summary is genuinely
  absent (a repo that was never scanned). A scanner that fataled or an artifact
  that was truncated is not evidence of "clean"
  (`project_scanner_degraded_marker`).
- Retire the events-based review-findings rows from the RTM. Nothing else
  consumes them once the gate is re-hung (verified: only `rtm_generator`
  produces them, only this hook read them). The section-based rows
  (`rtm_generator.py:375-376`) are fed by real per-section `code_review_findings`
  with a genuine fixed-list and are left alone.

**Verified by:** integration test — a deploy command against a tree with open
criticals blocks; against a clean scan passes; against a degraded scan blocks;
and a tree whose RTM shows 24 unresolved review findings but a green scan no
longer blocks (the exact state of this repo today).

---

## 3. Affected Boundaries

| Boundary | Files | Why it counts |
|---|---|---|
| Claude-Code hook contract | `plugins/shipwright-compliance/scripts/hooks/check_security_scan.py` | PreToolUse JSON in / exit-code out; fail-open on internal error |
| Compliance artifact contract | `plugins/shipwright-compliance/scripts/lib/rtm_generator.py` | RTM is read by hooks + dashboard |
| Event-log schema | `shared/scripts/tools/finalize_iterate.py` | `tests` block shape is shared with `record_event.py` via `validate_tests_block` |
| JSON config file | `shipwright_bloat_baseline.json` | read by Stop gate, pre-commit anti-ratchet, Group H |
| Runtime prompt | `CLAUDE.md` | loaded into every session |

`cross_component` **will fire from the diff** — `risk_detectors.py:118`
(`(^|/)hooks/.+\.py$`) matches `scripts/hooks/check_security_scan.py`. Integration
coverage is therefore mandatory and non-dodgeable; `check_integration_coverage`
recomputes the flag at F11.

`touches_io_boundary` also applies (`*_config.json`, JSON producer/consumer) →
Boundary Probe + round-trip.

---

## 4. Confidence Calibration

- **Boundaries touched:** Claude-Code hook contract, compliance artifact
  contract, event-log schema, baseline JSON, runtime prompt (§3 table).

### Empirical probes run

| # | Probe | Finding |
|---|---|---|
| P1 | Ran the **real** `group_h.run()` against the worktree, before and after | before: H1 fail (9 drift), H2 fail (10 suggestions). after: **H0–H6 all pass**, 171 entries, 164 oversize files all listed |
| P2 | Ran the **real** `group_f.run()` | `F6 PASS — CLAUDE.md is 192 lines (≤ 200)`; F7 pass |
| P3 | Ran the **real** `run_audit.py` end-to-end | open findings **5 → 2**. F6/H1/H2 closed; D1/D3 remain, naming FR-01.17 + FR-01.18 |
| P4 | `derive_tests_block` against the repo's actual `shipwright_test_results.json` with **this** run_id | `None` + diagnostic — the staleness guard fires on genuine data, not just synthetic (the file holds the *previous* run) |
| P5 | Same file, with the run_id it actually holds | `{'passed': 6857, 'total': 6876, 'skipped': 19, 'e2e_run': False}` — real ledger, correctly summed across unit + integration |
| P6 | Can the 5 historical events' totals be recovered? Inspected `.shipwright/agent_docs/iterates/*.json` for all four run_ids | **No.** Each retains only `tests_passed: true`, a boolean. The totals are unrecoverable from any tracked artifact — back-filling would mean *fabricating* numbers. This is what moved history out of scope from "deferred to IT-2" to "impossible without inventing data" |
| P7 | Structured diff on the baseline rewrite (external review OpenAI #6) | 21 entries touched, 150 byte-identical, none dropped, no field but `current` changed, `version` preserved |
| P8 | Baseline growth refusal | 3 files had grown past their ceiling — **all three mine**. Two were fixed by splitting/tightening; one declared. The script exits non-zero on any undeclared growth |
| P9 | `uvx ruff@0.15.15 check .` (the gating CI ruleset) | clean |

### Test Completeness Ledger

Principle: **testable ⇒ tested.** 0 untested-testable.

| # | Behavior | Disposition | Evidence |
|---|---|---|---|
| B1 | Every oversize file on disk has a baseline entry | `tested` | P1 — real `group_h._check_h1` returns pass |
| B2 | No recorded ceiling exceeds on-disk LOC | `tested` | P1 — real `group_h._check_h2` returns pass |
| B3 | Baseline rewrite preserves unrelated entries | `tested` | P7 structured diff |
| B4 | `CLAUDE.md` ≤ 200 lines, nothing lost | `tested` | P2; both relocated blocks resolve by one link (`shared/prompts/writing-plugin.md`, the pytest-root spec — existence verified) |
| B5 | Test totals are summed across reporting layers | `tested` | `test_iterate_tests_block.py::TestDerive::test_unit_and_integration_totals_are_summed` |
| B6 | `not_run` layers contribute nothing | `tested` | `TestDerive::test_not_run_layers_contribute_nothing` |
| B7 | `e2e_run` reflects whether e2e actually ran | `tested` | `TestDerive::test_e2e_run_is_true_when_e2e_actually_ran` |
| B8 | A failing run reports its real numbers | `tested` | `TestDerive::test_a_failing_run_reports_its_real_numbers` |
| B9 | `total == 0` yields no block | `tested` | `TestDerive::test_zero_total_yields_no_block` |
| B10 | Absent `skipped` stays absent (reader predicate preserved) | `tested` | `TestDerive::test_skipped_omitted_when_no_layer_reported_one` |
| B11 | A foreign `run_id` is treated as absent | `tested` | `TestStalenessGuard` (2 cases) + **P4 on real data** |
| B12 | Absent/malformed/non-dict/non-int results never break finalize | `tested` | `TestFailOpen` (4 cases) |
| B13 | A derived block failing validation is dropped, not raised | `tested` | `TestFailOpen::test_a_derived_block_failing_validation_is_dropped_not_raised` |
| B14 | An explicit extras block wins | `tested` | `TestPrecedence::test_explicit_extras_tests_wins_over_derivation` |
| B15 | An invalid/non-dict explicit block raises | `tested` | `TestPrecedence` (2 cases) |
| B16 | The derived block round-trips through JSON and the shared validator | `tested` | `test_round_trip_derived_block_satisfies_the_shared_validator` (**round-trip probe**, `touches_io_boundary`) |
| B17 | A folded event satisfies D1's exact predicate | `tested` | `test_d1_sees_a_folded_event_as_covering` |
| B18 | Deploy blocks on open criticals; allows a clean scan | `tested` | `test_security_gate.py::TestScanVerdict` |
| B19 | Non-deploy commands and quoted deploy-words never gate | `tested` | `TestCommandScope` (2 cases) |
| B20 | A malformed / non-object summary blocks (fails **closed**) | `tested` | `TestBrokenOrAbsentArtifact` (2 cases) — external review OpenAI #1 / Gemini #1 |
| B21 | A degraded scan blocks | `tested` | `TestBrokenOrAbsentArtifact::test_blocks_on_degraded_scan` |
| B22 | A never-scanned repo still allows (only legitimate fail-open) | `tested` | `TestBrokenOrAbsentArtifact::test_allows_when_never_scanned` |
| B23 | A summary with no usable verdict blocks | `tested` | `TestBrokenOrAbsentArtifact::test_blocks_when_summary_carries_no_verdict` |
| B24 | Falls back to `critical_gate` when counts are absent | `tested` | `TestScanVerdict::test_falls_back_to_critical_gate_when_counts_absent` |
| B25 | `high` findings alone do NOT gate | `tested` | `TestScanVerdict::test_high_findings_alone_do_not_gate` — external review OpenAI #7 |
| B26 | Threshold boundary is inclusive | `tested` | `TestThreshold::test_threshold_boundary_is_inclusive` |
| B27 | The gate resolves a subdirectory project root | `tested` | `TestSubdirectoryProjectLayout::test_blocks_from_workspace_root` |
| B28 | The RTM review counter no longer gates | `tested` | `TestScanVerdict::test_review_findings_counter_no_longer_gates` |
| B29 | **INTEGRATION** — the two artifacts are read independently on a real project tree | `tested` (`category: integration`) | `integration-tests/test_security_gate_subject.py::TestTheTwoArtifactsAreIndependent` — 3 cases incl. the monorepo's exact 2026-07-28 state and the inverse false-green |
| B30 | **INTEGRATION** — degraded/broken/absent artifacts compose correctly through the hook + root resolver + config | `tested` (`category: integration`) | `integration-tests/test_security_gate_subject.py::TestDegradedAndBrokenArtifacts` + `TestOperatorThreshold` |
| B31 | Retiring the RTM rows breaks no existing consumer | `tested` | full compliance suite (1522) + integration (429) green; `test_rtm_generator.py::test_findings_in_summary` still passes — it covers the SECTION rows, which stay |
| B32 | A `critical_gate: fail` with no numeric count blocks at **every** threshold | `tested` | `TestScanVerdict::test_an_unsizeable_fail_blocks_at_every_threshold` — **self-review catch**, independently confirmed by external code review |
| B33 | An exact count is still sized against the threshold normally | `tested` | `TestScanVerdict::test_an_exact_count_is_still_sized_against_the_threshold` |
| B34 | A malformed/negative/bool threshold coerces to zero tolerance | `tested` | `TestThreshold::test_a_malformed_threshold_falls_back_to_zero_tolerance` (4 values) |
| B35 | A directory (or other non-regular artifact) at the summary path blocks | `tested` | `TestBrokenOrAbsentArtifact::test_blocks_when_the_path_is_a_directory` — external code review |
| B36 | A layer with a valid `total` but unusable `passed` is skipped, not zeroed | `tested` | `TestFailOpen::test_a_total_without_a_usable_passed_skips_that_layer` — external code review |
| B37 | If no layer survives that check, no block is written | `tested` | `TestFailOpen::test_no_layer_survives_means_no_block` |
| B38 | A valid, non-degraded, in-threshold summary allows **regardless of `scan_date`** | `tested` | `TestScanVerdict::test_an_old_but_valid_clean_scan_still_allows` — see below |
| B39 | A symlinked summary is **followed**, and a clean target allows | `tested` | `test_security_gate_symlinks.py::test_symlink_to_a_clean_summary_is_followed_and_allows` |
| B40 | A symlinked summary is followed, and a dirty target blocks | `tested` | `test_security_gate_symlinks.py::test_symlink_to_a_dirty_summary_is_followed_and_blocks` |
| B41 | A symlink pointing at a directory blocks | `tested` | `test_security_gate_symlinks.py::test_symlink_to_a_directory_blocks` |
| B42 | A **dangling** symlink blocks — present-and-broken is not "never scanned" | `tested` | `test_security_gate_symlinks.py::test_a_dangling_symlink_blocks_rather_than_reading_as_absent` |
| B43 | A gate that cannot be **loaded** blocks rather than assuming a clean scan | `tested` | `test_security_gate_hook_main.py::test_an_unloadable_gate_blocks_rather_than_assuming_clean` |
| B44 | A stat error (e.g. `PermissionError`) reads as *unusable*, never as *absent* | `tested` | `test_security_gate_unit.py::TestReadSecuritySummary::test_a_stat_error_is_unusable_not_absent` |

**B38 — the ledger has no `untestable` rows, and B38 is why.** It was first
written as `untestable` for the staleness gap external review raised (OpenAI
#2): the summary carries `scan_date` / `source` but no commit binding, so the
gate cannot tell fresh-green from stale-green. That framing was wrong twice
over. None of the six closed-vocabulary `reason_code`s actually fit, and forcing
one would have been exactly the dishonesty this ledger exists to prevent — but
the honest move was not to drop the row either. *Allowing regardless of
`scan_date`* **is** a behaviour of this code, and it is trivially testable. So
it is now pinned by a test that asserts the deliberate decision, with the
reasoning in the test's own docstring.

The limitation itself stands and is recorded in the hook's docstring: binding to
HEAD is not viable while the producer is a weekly cron plus a PR gate, and the
freshness decision belongs to the **producer**. What changed is that the
decision is now visible to the next reader as intent rather than oversight.

**B39–B42 came from the PR-Review gate, and one of its two findings was wrong.**
The reviewer reported a correctness defect in `read_security_summary`: "the
regular-file check after `os.stat` inspects the wrong `st_mode`". It did not —
the earlier form rebound `st = os.stat(path)` before testing, so the mode was
always the resolved target's. But a security branch that a careful reader
misreads is not clear enough. `read_security_summary` was restructured so a
single `os.stat` (which follows symlinks) produces the only mode in scope, with
`lstat` consulted *solely* to tell a genuinely absent path from a dangling
symlink — and the four behaviors above now pin it. Net: the finding was factually
wrong, the code is better, and the branch is covered for the first time.

**B43–B44 came from the diff-coverage gate, and the gate was right about
something the test count hid.** CI reported 50% patch coverage with
`security_gate.py` and `check_security_scan.py` at **0.0%** — because every test
drove the hook through `subprocess`, and coverage.py does not instrument a child
process. The code was thoroughly exercised and completely unmeasured.

The fix is not a coverage exercise: `decide()` is a pure function of the
filesystem, so testing it in-process is strictly better — faster, and able to
assert the returned reason and details rather than only an exit code. Two
branches that the subprocess suites could not reach at all are now covered (a
gate that fails to *load*, and a `PermissionError` from `stat`). Measured after:
`security_gate.py` **99%**, `check_security_scan.py` **82%** (the residue is
`_resolve_project_root`'s fallback and the `_run` wrapper, both outside this
diff).

The two levels answer different questions and both stay: *does the shipped
script behave?* (subprocess) versus *does each branch of the decision behave?*
(in-process).

Final ledger: **44 behaviors, 44 tested, 0 untestable, 0 untested-testable.**

### Confidence-pattern check

- **Asymptote (depth):** the two behaviour changes are each pinned at the unit
  level *and* verified by running the real audit/producer code against real repo
  data (P1–P5). The D1/D3 chain is closed end-to-end by B17 — the folded event
  is checked against D1's literal predicate, not a paraphrase of it.
- **Coverage (breadth):** all six test roots that could see these files were run
  green (1522 + 6182 + 429 + 345 + 298 + 506 = 9282 passed, 17 skipped).
- **Integration composition:** `cross_component` fires from the diff
  (`hooks/.+\.py$` → `check_security_scan.py`). B29/B30 are the required
  `category: integration` behaviors — a real project tree, the real hook
  subprocess, the real root resolver, and both compliance artifacts present at
  once, proving the two are now read independently.
- **What would falsify this work:** a consumer of the retired RTM rows outside
  this repo. Searched every occurrence of both labels here (only the generator,
  this hook, and their tests) **and in the WebUI repo** — its only hits are its
  own generated `traceability-matrix.md` (`0 / 0`), an *output* of the same
  generator, not a reader. No code anywhere parses those labels. Checked rather
  than assumed, because "no in-repo reader" was the reviewer's stated doubt
  (OpenAI #3).

---

## 5. Out of scope (named, so the omission is deliberate)

- Back-filling `tests` onto the 183 historical events (belongs to IT-2's
  amendment surface).
- Splitting any of the nine H1 files. Each is its own judgement.
- Raising the ceiling for `test_classify_complexity.py` /
  `sub-iterate-runner.md` on behalf of IT-5 / IT-7b. Pre-raising a ratchet for
  work that has not been written is exactly the bypass the anti-ratchet exists
  to prevent.
- `trg-965c563e` is not dismissed **by this run** (brief §Nachtrag 1: a manual
  dismiss only mints the next id). It closed on its own during the P3 audit
  probe — `by: "complianceBacklog"`, `reason: "complianceRefreshed"` — because
  the finding set genuinely changed from five to two, and the producer minted
  `trg-e7c8f5a0` for the residual D1/D3. That is the designed lifecycle, and
  both lines are committed as the honest record of it. The brief's point stands
  and was honoured: no operator dismiss was issued.
