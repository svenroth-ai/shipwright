# Iterate Spec: triage defer from the terminal + failing-check detail cap

- **Run ID:** iterate-2026-07-27-triage-defer-ci-cap
- **Type:** feature
- **Complexity:** medium
- **Status:** draft
- **Campaign card:** `trg-813d2305` (REQ-3 Phase 2 walk of FR-01.14 —
  `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`,
  criteria 2 and 13)

## Goal

Close the two decided gaps the FR-01.14 walk left open, both inside the files
this card owns. (1) The product promises three decisions on a triage finding —
take it into work, dismiss it, or deliberately defer it until later. The
Command Center can write all three; the terminal can write only two. Add
`defer` to the CLI, symmetric with `dismiss`, and make the terminal listing
show deferred entries as deferred rather than hiding them. (2) An action-unit
built from a failing check carries text the project does not control (workflow
name, branch, PR title). Its two siblings cap their detail line; the
failing-check entry does not, so one entry can grow without bound and crowd
the rest out of a capped view. Give it the same cap.

## Acceptance Criteria

- [ ] **AC-1** Given a triage item that is still open, when the operator runs
      `triage_cli.py defer <id> --reason <text>`, then the item's recorded
      decision becomes *deferred* (`snoozed`), the reason is stored with it,
      and the actor is recorded as `cli`.
- [ ] **AC-2** Given the operator omits `--reason`, or gives one that is empty
      or only whitespace, when `defer` is run, then the command refuses with
      exit 2 and writes nothing — a deferral without a stated reason is not a
      decision.
- [ ] **AC-3** Given an id that does not exist, or an item whose decision was
      already made (promoted / dismissed / deferred), when `defer` is run,
      then it refuses with exit 2 and the stored record is unchanged —
      identical guard to `dismiss`.
- [ ] **AC-4** Given both surfaces write a deferral, when the stored events are
      compared, then they carry the same status and reason fields — the CLI
      dispatches through the same shared helper (`triage_promote`) that the
      Command Center's contract is pinned against, not a private copy.
- [ ] **AC-5** Given deferred items exist, when the operator runs
      `triage_cli.py list`, then deferred entries are shown in their own
      labelled section, each carrying its reason, and are never mixed in with
      the open ones — open and deferred are distinguishable at a glance. The
      section header appears only when there is something in it, and the open
      block is unchanged whether or not deferred items exist.
- [ ] **AC-5b** Given a stored title or deferral reason contains terminal
      control characters — it may have been written by the Command Center, a
      producer, or an editor, none of which this CLI controls — when the
      deferred section is printed, then those characters do not reach the
      terminal, exactly as the open section already guarantees.
- [ ] **AC-6** Given deferred items exist, when `triage_cli.py list --json`
      runs, then the emitted array is unchanged — open items only, each with
      `pendingDelivery`. (Cross-repo contract: the Command Center compares this
      **field-by-field** against `triage-union-cli-list.json`, in its own
      repository, and only after a manual marketplace sync.
      **Corrected 2026-07-27** — this document and PR #444 both said
      "byte-for-byte"; the Stage-3 review disproved it. Nothing in THIS repo
      pins the bytes, so `indent=2 → indent=4` would pass every test in both
      repositories. The behaviour claim held; the guarantee named for it did
      not.)
- [ ] **AC-7** Given a failing-check action-unit whose workflow name, branch or
      run URL is pathologically long, when the entry is built, then its detail
      line is capped at the same 1024 characters as the security and
      proposed-change entries and ends with an ellipsis marking the cut.
- [ ] **AC-8** Given a failing-check or proposed-change action-unit of ordinary
      length, when the entry is built, then its detail is unchanged — the cap
      truncates only what *exceeds* it, so a detail of exactly the cap length
      is passed through untouched.
- [ ] **AC-9** The three documents that state what the terminal can do —
      `shared/glossary.md` (*Defer (Snooze)*), `docs/guide.md`,
      `docs/security-ci-setup.md` — no longer say the terminal cannot defer.

## Spec Impact

- **Classification:** `none`
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** FR-01.14 in `.shipwright/planning/01-adopted/spec.md`
  already states both promises verbatim — "each one is taken into work,
  dismissed, or deliberately deferred until later" (three decisions) and
  "text the project does not control … is length-capped so one entry cannot
  crowd out the rest". The REQ-3 Phase 2 walk wrote those criteria; this
  iterate implements them. No requirement text changes.

**Where delivery is recorded** (external review, dependency #6 — the first
draft claimed the campaign ledger's `unimplemented` cells would flip, which
would have been a claim left undone or a file this card must not touch).
`2026-07-23-req3-ac-evidence-ledger-mono.md` is a **dated walk record** shared
by every card the walk spawned — editing it here would both rewrite history
and collide with the host-checks and stamping cards. Delivery is instead
recorded where this run owns the record: the card `trg-813d2305` is dismissed
with a reason naming this run (the established convention — see the
`"delivered by PR #436"` / `"Implemented PR #431"` flips), plus the iterate
ADR and the changelog drop.

## Out of Scope

- **Un-deferring.** Neither surface can move an item out of a decided state:
  the Command Center's `statusFlipRoute` and the CLI's `promote`/`dismiss`
  both accept only `status == "triage"`. `defer` matches that guard exactly.
  Adding a reopen path would be a new capability on both surfaces, not this
  card.
- **Whether the code host runs its checks at all** — the host-checks card.
- **The per-criterion test backfill** carried by the enforcement list
  (including FR-01.14's one genuinely unpinned central criterion).
- **`secrets_action_unit`'s detail** — it interpolates only `owner_repo` and a
  count, both project-controlled; the card names three siblings, and this is
  not one of them.
- **`producer.py`'s `_ARTIFACT_DETAIL_MAX_LEN`** — a file this card does not
  own. The two caps stay numerically equal but separately declared.
- **The rendered `triage_inbox.md` view** (`aggregate_triage.py`) — not an
  owned file. **Corrected 2026-07-27:** this said it "already counts `snoozed`
  separately in its summary line", which reads as *that surface handles it*.
  It does not: it renders only open items, so a deferred entry survives there
  as one integer with no id and no reason — while this run edited the glossary
  to promise the opposite. Carried by `trg-51f8e2a1`.
- **The campaign ledger** `2026-07-23-req3-ac-evidence-ledger-mono.md` — see
  "Where delivery is recorded" above.

## Design Notes

No UI. Terminal output only.

**Listing shape** — open items keep their current rendering byte-for-byte
(header line, title, fenced launch payload). Deferred items follow in a
separate labelled block, rendered compactly: id / severity / kind / source,
the reason, the title — and deliberately **no launch-payload fence**. The
payload is the "do this now" instruction; reprinting it for an item the
operator explicitly parked would re-create the crowding this iterate's second
half exists to prevent.

**Where the cap lives** — `mappers.py` already declares
`_PR_CI_DETAIL_MAX_LEN = 1024` and open-codes the truncation. With a second
call site arriving, the constant is renamed `_DETAIL_MAX_LEN` and the
truncation moves into one `_cap_detail()` used by both mappers in that file.
No importer references the old name (verified across the repo).

**Why the helpers are extracted rather than copied** — `defer` differs from
`dismiss` by one string, and `_cmd_defer` from `_cmd_dismiss` by two. Copying
both would add ~55 lines, push `triage_cli.py` past the 300-line budget, and
leave two guard clauses that must be kept in step by hand.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `triage.mark_status` (`newStatus: "snoozed"`) | `triage.read_all_items`, `triage_gc`, `aggregate_triage`, WebUI `readAllItems` | JSONL (`.shipwright/triage.jsonl`) |
| `triage_cli.py list --json` | WebUI `server/src/core/triage-enrich.ts` (+ fixture `triage-union-cli-list.json`) | JSON array |
| `mappers.ci_action_unit` / `pr_ci_action_unit` → `detail` | `aggregate_triage`, `triage_cli list`, WebUI Triage page | JSONL field |

No new format is introduced: `snoozed` is a pre-existing member of
`triage.STATUSES`, already written by the Command Center and already handled
by every reader. The second boundary is a **frozen** contract — this iterate's
job there is to leave it unchanged, which AC-6 pins.

## Confidence Calibration

- **Boundaries touched:** the three in "Affected Boundaries" above.

- **Empirical probes run:**
  - *Forged-row probe.* Planted `- trg-fake000 severity=critical …` behind a
    newline inside a stored title and a stored reason, ran the real CLI, read
    the rendered stdout. **Found the defect:** `strip_control_chars` keeps
    `\n` and `\t` on purpose (launch payloads are multi-line), so the scalar
    fields were re-emitting them and the forged row rendered as its own line.
    Fixed with `strip_control_chars_inline`; the probe is now a test.
  - *Detail-length probe.* Measured the composed detail from a one-character
    probe run instead of assuming its fixed prefix. **Found an error in my own
    padding helper:** the mapper substitutes `"workflow"` for a falsy name, so
    a zero-length probe was off by eight and the boundary cases were testing
    the wrong lengths.
  - *Cross-repo contract probe.* Read the WebUI's
    `triage-union-cli-list.json` fixture header and `triage-enrich.test.ts`
    to confirm `list --json` is pinned deep-equal over there, then asserted
    open-only **with a deferred item present** rather than trusting the filter.
  - *Reason-optionality probe.* Read the Command Center's
    `parseDismissSnoozeBody`: `reason` defaults to `null` there. A deferral it
    wrote therefore has no reason, which is why the listing prints
    `(no reason recorded)` instead of `None`.
  - *Risk-flag recomputation.* Ran `risk_detectors.is_io_boundary_change` /
    `is_cross_component_change` / `is_ci_supplychain_change` against the
    staged file list — all three False, so no Boundary Probe, no integration
    behavior and no CI-supply-chain acknowledgement are owed. Recomputed
    rather than inherited from the classifier's opening call.
  - *Budget probe.* Ran the bloat pre-commit hook on the staged diff (no
    ratchet) and measured every touched file: 249 / 298 / 92 / 220 / 292 /
    133, all inside the 300-line rule, glossary 523 of 540.

- **Test Completeness Ledger**

  | # | Testable behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | `defer()` records `snoozed`, the reason and the actor | tested | `test_defer_records_the_decision_and_its_reason` PASSED |
  | 2 | `defer()` refuses an empty / whitespace / tab reason and writes nothing | tested | `test_defer_refuses_a_reason_that_says_nothing[3 cases]` PASSED |
  | 3 | `defer()` refuses control characters in the reason | tested | `test_defer_refuses_control_characters_in_the_reason` PASSED |
  | 4 | `defer()` refuses an already-decided item (dismissed / snoozed / promoted) | tested | `test_defer_refuses_an_already_decided_item[3 cases]` PASSED |
  | 5 | `defer()` raises `KeyError` on an unknown id | tested | `test_defer_unknown_id_raises_key_error` PASSED |
  | 6 | `defer()` raises `FileNotFoundError` with no store | tested | `test_defer_without_a_store_raises_file_not_found` PASSED |
  | 7 | `dismiss()` is unchanged by the shared extraction | tested | `test_dismiss_is_unchanged_by_the_shared_extraction` PASSED |
  | 8 | `promote()` is unchanged by the `_require_store` extraction | untestable | covered-by-existing-test (`test_triage_promote.py`, 38 passed unmodified) |
  | 9 | CLI `defer` happy path records the actor as `cli` | tested | `test_cli_defer_records_the_operator_as_the_actor` PASSED |
  | 10 | CLI `defer` refuses without a real reason and writes nothing | tested | `test_cli_defer_refuses_and_writes_nothing_without_a_real_reason[2 cases]` PASSED |
  | 11 | CLI `defer` and `dismiss` both exit 2 on an unknown id and leave the store untouched | tested | `test_cli_leaves_the_store_untouched_when_it_refuses[2 cases]` PASSED |
  | 12 | CLI `defer` exits 2 on an already-decided item | tested | `test_cli_defer_refuses_an_already_decided_item` PASSED |
  | 13 | the listing shows deferred entries in their own section, with the reason, after the open ones | tested | `test_list_shows_deferred_in_its_own_section_with_the_reason` PASSED |
  | 14 | no deferred header when nothing is deferred | tested | `test_list_says_nothing_about_deferral_when_there_is_none` PASSED |
  | 15 | deferred-only still reports "No open triage items" | tested | `test_list_with_only_deferred_items_still_reports_no_open_work` PASSED |
  | 16 | a Command-Center deferral with no reason renders `(no reason recorded)`, never `None` | tested | `test_list_renders_a_deferral_the_command_center_left_reasonless` PASSED |
  | 17 | ESC / BEL in a deferred entry's fields never reach the terminal | tested | `test_list_keeps_control_characters_out_of_the_deferred_section` PASSED |
  | 18 | a stored newline cannot forge a listing row, open or deferred | tested | `test_a_stored_newline_cannot_forge_a_listing_row[2 cases]` PASSED |
  | 19 | `list --json` stays open-only, with `pendingDelivery`, while an item is deferred | tested | `test_list_json_stays_open_only_when_an_item_is_deferred` PASSED |
  | 20 | the failing-check detail is capped whichever untrusted field grows | tested | `test_failing_check_detail_is_capped_whatever_grows[3 cases]` PASSED |
  | 21 | it is capped at the *same* length as its proposed-change sibling | tested | `test_failing_check_cap_matches_the_proposed_change_cap` PASSED |
  | 22 | capping the detail leaves the existing 160-char title cap alone | tested | `test_capping_the_detail_leaves_the_title_cap_alone` PASSED |
  | 23 | failing-check boundary: 1023 and 1024 pass through, 1025 truncates | tested | `test_failing_check_detail_boundary[3 cases]` PASSED |
  | 24 | proposed-change boundary: same three lengths | tested | `test_proposed_change_detail_boundary[3 cases]` PASSED |
  | 25 | an ordinary failing-check detail is byte-unchanged | tested | `test_an_ordinary_failing_check_detail_is_untouched` PASSED |
  | 26 | an ordinary proposed-change detail is byte-unchanged | tested | `test_an_ordinary_proposed_change_detail_is_untouched` PASSED |
  | 27 | the three documents no longer say the terminal cannot defer | tested | `test_the_documents_no_longer_say_the_terminal_cannot_defer` PASSED |

  27 behaviors, 10 acceptance criteria. 26 `tested`, 1 `untestable` with a
  closed-vocabulary reason code, 0 testable-but-untested.

- **Confidence-pattern check:**
  - *Asymptote (depth):* **yes, and it fired.** The first implementation
    passed all 23 of its own tests and was still wrong — the newline
    injection. One more probe was therefore run after the fix (a second
    external code-review round on the corrected diff), and it produced two
    more real items: the missing proposed-change boundary cases and a
    display-sanitized `source` deciding a control-flow branch. Both fixed, and
    a third round would now be re-reading the same ground.
  - *Coverage (breadth):* every row above is `tested` or carries a valid
    reason code; nothing is deferred to "should still test".
  - *Integration composition:* `cross_component` recomputed **False** from the
    diff (no hooks, no merge/churn resolver, no phase validator, no campaign
    machinery), so no `category:"integration"` behavior is owed.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run pytest shared/tests/test_triage_cli.py shared/tests/test_triage_promote.py shared/tests/test_github_triage_action_units.py shared/tests/test_github_triage_pr_ci.py -v`
- **Evidence path:** `.shipwright/runs/iterate-2026-07-27-triage-defer-ci-cap/surface_verification.json`
- **Justification:** n/a (a real surface exists — the CLI tests drive
  `triage_cli.py` as a subprocess, i.e. the actual operator-facing binary)
