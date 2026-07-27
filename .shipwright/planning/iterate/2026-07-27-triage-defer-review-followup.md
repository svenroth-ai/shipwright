# Iterate Spec: post-merge review follow-up for the triage defer surface

- **Run ID:** iterate-2026-07-27-triage-defer-review-followup
- **Type:** change
- **Complexity:** small
- **Status:** draft
- **Follows:** `iterate-2026-07-27-triage-defer-ci-cap` (PR #444, merged
  `631e0805`) — the Stage-2 `code-reviewer` and Stage-3 `doubt-reviewer` passes
  were run **after** that merge, at the operator's instruction, and found
  defects and overclaims the three external rounds had missed.

## Goal

Fix what the two subagent reviewers found in already-merged code, and correct
the statements that run made about itself which turned out to be false. The
four larger findings are deliberately **not** here — they are two triage cards
(below) so one future iterate can take them together.

## Acceptance Criteria

- [ ] **AC-1** Given a parked entry whose reason is present but consists only
      of whitespace, when the listing renders it, then it reads
      `(no reason recorded)` — the same as a genuinely absent reason. Today the
      fallback is applied before sanitising, so such a reason renders as a
      blank line, and the one test that covers this picked the single falsy
      input that happens to work.
- [ ] **AC-2** Given any **entry row** of the listing (its first line;
      continuation lines are distinguished by indentation), when it is read by a
      person or a script, then whether it is an open entry or a parked one is
      visible **on the row itself** — by a token at a fixed position, not by a
      search, since `source` and `dedupKey` are attacker-influenceable and
      could otherwise forge it — and not only from a section header printed
      once. Before this change every line starting `- trg-` meant an open
      entry; the previous run made that silently false, and its own security
      test uses exactly that pattern as its definition of a row.
- [ ] **AC-3** Given a parked entry whose title or reason is very long, when it
      is rendered, then it is truncated — the same crowding guarantee the
      previous run added to the producer side, which its own new rendering
      surface did not honour.
- [ ] **AC-4** Given a stored `dedupKey` made only of characters that
      sanitising removes, when the entry is rendered, then whether the field is
      emitted is decided by the **stored** value, not the display-massaged one.
      (Same class as the `source` fix in the previous run; a second site two
      lines below the comment asserting the rule.)
- [ ] **AC-5** Given the guard that rejects a decision on an already-decided
      item, when a test claims to pin it, then the test fails if the guard is
      removed. Today, for an item already parked, `defer` would append a second
      parked event and the resolved status would still read parked — so the
      assertion cannot fail.
- [ ] **AC-6** Given an operator runs `triage_cli.py --help`, then the `list`
      description matches what `list` now prints (it also prints the deferred
      section).
- [ ] **AC-7** Given an item that exists only in the not-yet-delivered outbox,
      when it is deferred, then it is deferrable there exactly as it is
      dismissable and promotable — the branch `_require_store`'s own comment
      calls load-bearing, and the only place the write target differs.
- [ ] **AC-8** Given the documents describing what the terminal and the Command
      Center each guarantee, then no statement claims parity that does not
      exist. Three specific corrections, all of them written by the previous
      run: (a) the shared helpers are the CLI's entry point and the reference
      semantics the Command Center mirrors — **not** a shared code path, since
      that surface permits a reason-less park and this module does not; (b) the
      machine-readable listing is **not pinned by any CI job in either
      repository** — the Command Center deep-equals a committed snapshot only a
      human regenerates, so any drift is silent; "byte-for-byte" was wrong, and
      "a formatting-only change would slip through" was still too generous; (c) the rendered agent-facing
      document shows a parked entry as a bare count, so "deferred is not a
      disappearance" is true of the terminal only, today.
- [ ] **AC-9** Given the previous run's self-review claims its new tests "touch
      no repo state", then that claim is corrected — one of them reads three
      real repository files — and the assertions it makes are strengthened so
      they cannot pass for a document that says the command does not exist.
- [ ] **AC-10** Given an operator parks something by mistake, then the
      documentation names the supported way to correct it instead of stating
      that recovery is impossible. (An un-park command is card `trg-51f8e2a1`;
      until it lands, the honest statement is that no *subcommand* reverses a
      park, not that the decision is irreversible.)

## Spec Impact

- **Classification:** `none`
- **NONE justification:** every criterion here either fixes a defect in the
  implementation of FR-01.14's already-written promises or corrects a false
  statement about that implementation. No requirement text changes. Delivery of
  the FR's remaining behaviour is carried by `trg-51f8e2a1`.

## Operator decisions taken 2026-07-27 (recorded here, executed by `trg-51f8e2a1`)

Put as four plain-language questions after the review; all four answered. They
are recorded here because the card that will implement them must not have to
re-derive them, and because a decision that lives only in a chat is not a
decision anyone can audit later.

| # | Question | Decision |
|---|---|---|
| 1 | A parked finding's check runs again and still sees it — what happens? | **Parking takes a required revisit date.** The finding stays suppressed until that date, then returns to the open list by itself. Chosen over "stays until you un-park it" and over today's behaviour (it re-fires as a new open item every import, which makes parking close to a no-op for machine-raised findings). |
| 2 | A parked finding fixes itself — should the entry close on its own? | **Yes, automatically**, exactly as an open one does. The alternative (only a human closes it) was rejected because the parked list would then accumulate entries describing problems that no longer exist. |
| 3 | Where should parked items appear? | **Every surface, in its own section.** Accepted cost: the machine-readable output is a versioned cross-repo contract, so this needs a version bump here plus the matching consumer change in the Command Center repo. "Terminal only, and correct the docs" and "a count everywhere" were both rejected. |
| 4 | Should a mistaken park be reversible? | **Yes, add an un-park command.** The store already permits the transition; only the command is missing, so today a mis-park pushes an operator toward hand-editing the log — the exact untrusted-input path the renderer exists to defend against. |

**The operator's own question, answered before deciding #1** — *"if we do that,
how do we find it again? does it just sit in the triage?"* It sits in the
Triage Inbox either way and never leaves it; the date changes only whether the
item comes back to the operator or waits to be looked for. With decisions 2 and
4 also taken, the parked list cannot silt up with solved items and nothing is
stuck there — so the date's remaining job is narrow and specific: it stops a
park becoming permanent through inattention. The cost was stated and accepted:
an operator who does not know a date will pick an arbitrary one.

## Out of Scope — the four larger findings, deliberately carried as two cards

The operator asked for these to be bundled so one iterate can solve them, not
split four ways.

- **`trg-51f8e2a1`** (high) — *deferring does not yet defer*: re-import
  suppression + the required revisit date, self-close, visibility on every
  surface, the un-park command, and a cap on the parked section. One coherent
  piece of product work; the decisions above are its input.
- **`trg-93ceb2b0`** (medium) — *a decision can be silently lost*: the
  unlocked read-then-write shared by promote / dismiss / defer, and the success
  line printed when the write did not land. Pre-existing, store-level,
  independent of the product work above.

Also out of scope: the truncation rule duplicated across `mappers.py` and
`producer.py` (advisory, flagged as a follow-up by the Stage-2 reviewer, and
`producer.py` is a file the previous card did not own).

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `triage_render.format_item` / `format_deferred` | a terminal, and any operator or agent reading `triage_cli.py list` | text lines |

The machine-readable `list --json` path is **not** touched by this run; AC-8(b)
only corrects what is claimed about it.

## Confidence Calibration

- **Boundaries touched:** the one above.
- **Empirical probes run:** {filled at Step 7.5}
- **Test Completeness Ledger:** {filled at Step 7.5}
- **Confidence-pattern check:** {filled at Step 7.5}

## Verification (medium+ — recorded although this run is small)

- **Surface:** cli
- **Runner command:** `uv run pytest shared/tests/test_triage_render_rows.py shared/tests/test_triage_defer.py shared/tests/test_triage_docs_consistency.py shared/tests/test_triage_wp9_sanitize_outbox.py shared/tests/test_triage_cli.py shared/tests/test_triage_cli_json.py shared/tests/test_triage_promote.py -v`
  (the first draft omitted the two files carrying AC-7 and AC-9, which would have
  recorded them as verified without executing their tests — Stage-3 finding)
- **Evidence path:** `.shipwright/runs/iterate-2026-07-27-triage-defer-review-followup/surface_verification.json`
