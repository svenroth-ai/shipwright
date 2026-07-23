# Iterate Spec: a real per-run record of what every review pass found

- **Run ID:** iterate-2026-07-21-review-record
- **Type:** feature
- **Complexity:** medium (history-calibrated, n=20; `prior_source: history`)
- **Risk flags:** `touches_io_boundary` (declared — new serialized format with a
  cross-repo consumer), `cross_component` (if `campaign-mode.md` is touched)
- **Spec Impact:** MODIFY — extends **FR-01.11** (`/shipwright-iterate`) with two
  dated `(E)` acceptance lines. No new FR minted.
- **Origin:** handoff from webui campaign `2026-07-18-mission-artifacts`,
  sub-iterate S2; webui triage `trg-74ec44b8`.

---

## Problem

The Mission view's **Review** artifact answers "what did the reviews of this
change actually find?". Today it cannot, because the iterate lifecycle throws
that answer away.

Measured on this repo, per review type:

| Type | Source today | Run-scoped? | Findings? |
|---|---|---|---|
| `plan` (external plan/iterate review) | `external_review_state.json` | **No** — ONE shared file at `.shipwright/planning/iterate/`, every run overwrites it | prose payload only |
| `external_code` (external code cascade) | `external_code_review_state.json` | **No** — same | prose payload only |
| `code` (internal `code-reviewer` subagent) | iterate ADR prose | — | **none** |
| `doubt` (internal `doubt-reviewer` subagent) | iterate ADR prose | — | **none** |
| `self` (Self-Review, the ONLY review at trivial/small) | iterate ADR prose | — | **none** |

Two consequences:

1. **The internal passes leave no machine-readable trace at all.** They run,
   they find real defects, and the result exists only as prose in an ADR.
2. **Even the "clean contract" half is not run-scoped in this repo.** The webui
   consumer reads `.shipwright/planning/iterate/<run_id>/external_*review_state.json`
   — a per-run directory this repo never creates. So for a monorepo iterate,
   *all* review rows render as "no record", not just the two internal ones.
   `verifiers/iterate_compliance.py:96-102` already documents that shared file
   as "run-agnostic" and refuses to let it keep an audit live.

The waste is the sharpest part: **the internal reviewers already return
structured JSON.** `code-reviewer` returns
`{section, review:[{severity, category, file, line, finding, suggestion}]}`;
`doubt-reviewer` returns `{stage, gating, trigger, doubts:[…], summary}`. Nothing
persists it. This iterate does not ask the reviewers to change what they emit —
it stops discarding it.

## Non-goals

- Changing what any reviewer agent emits (`shipwright-build/agents/*` untouched).
- The webui consumer change (read `reviews.json`, render `self`) — cross-repo,
  filed as a follow-up.
- A 6th type for `spec-reviewer` (Stage 1). Out of scope; the pinned contract
  names four and this iterate adds only `self`.

## Decisions taken (Sven, 2026-07-21)

1. **Full findings list**, not just a count — each pass records its individual
   findings. The internal shapes map directly; the external prose is split
   best-effort against the format its own system prompt already mandates
   (`Category / Severity / File:line / Finding / Suggestion`).
2. **A missing record blocks finalization.** An empty Review row must always
   mean "genuinely not run", never "someone forgot to write it down".
3. **`self` is added as a fifth review type**, so a small/trivial change shows
   the review that actually happened instead of five empty rows.

## The record

One file per run, git-tracked, never evicted:

```
.shipwright/planning/iterate/<run_id>/reviews.json
```

That directory is also where the existing `external_*review_state.json` markers
move to (run-scoped at last), which is exactly where the webui consumer already
looks.

```json
{
  "schema_version": 1,
  "run_id": "iterate-2026-07-21-review-record",
  "reviews": {
    "self":          { "review_type": "self", "status": "completed",
                       "findings_count": 1, "findings": [ … ],
                       "provider": null, "completed_at": "2026-07-22T09:14:03Z",
                       "disposition": null, "recorded_by": "self-review" },
    "plan":          { … },
    "code":          { … },
    "doubt":         { … },
    "external_code": { … }
  }
}
```

Keyed by type (not a list) so uniqueness and "every type is represented" are
structural rather than a convention a writer can forget. Disk is snake_case per
this repo's convention; the webui consumer already maps snake_case markers onto
its camelCase `ReviewRow`, so the pinned
`{reviewType, status, findingsCount, findings[]}` descriptor is unchanged.

**Status vocabulary (closed):**

| Status | Meaning | Terminal? |
|---|---|---|
| `pending` | materialized so the type is explicitly represented; nothing recorded yet | no — overwritable |
| `completed` | the pass ran | **yes** |
| `not_run` | did not run, and `disposition` says why | **yes** |
| `not_applicable` | does not apply at this size/shape, `disposition` names the rule | **yes** |

**Immutability** is enforced on write: an upsert onto a terminal status is
rejected (exit 3) unless `--force`. A completed review cannot be quietly rewritten.

**Finding shape** — normalized across all four source shapes:

```json
{ "severity": "high|medium|low|null", "category": "…", "file": "…|null",
  "line": 42, "finding": "…", "suggestion": "…|null", "source": "code-reviewer" }
```

`severity` is nullable on purpose. Self-review reports pass/fail without a
severity, and inventing one would fabricate review data — the exact failure mode
this artifact exists to prevent.

## The gate

`check_review_record` (F11, small+; `n/a` at trivial):

> **No review type may still be `pending`.**

Uniform, and it does not re-encode the phase matrix inside a verifier where it
would drift. It forces an active declaration: a pass that did not run must be
recorded as `not_run` / `not_applicable` **with a reason**, rather than silently
omitted. Fails closed on a missing or corrupt file, and names the exact command
to close each outstanding type.

## Acceptance criteria

- **AC1** Each of the five types can be recorded from its native shape:
  `code-reviewer` JSON, `doubt-reviewer` JSON, a self-review result, and external
  reviewer prose — producing normalized `findings[]` with `findings_count`
  matching `len(findings)`. Input may be raw JSON **or** a Markdown file
  containing the payload in a ```` ```json ```` block, so the orchestrator can
  hand over an agent reply verbatim without hand-extraction.
- **AC2** All five types are always present in the record; unrecorded ones read
  `pending`. Every terminal non-`completed` status carries a `disposition` that
  names a rule — a blank or single-word disposition is rejected.
- **AC3** Re-recording a type that already holds a terminal status is rejected
  (exit 3) and leaves the file byte-identical; `--force` overrides.
- **AC4** Round-trip: producer → file on disk → reader returns an equal record,
  including a finding whose text contains newlines, quotes, non-ASCII, and a `null`
  severity.
- **AC5** External prose in **both** observed layouts (`- Category: bug` and
  `**Category:** bug`) splits into one finding per item. When **no** finding block
  parses, the result is `findings: []` with `parse_status: "unstructured"` and the
  raw text retained — a review that found nothing must never be rendered as one
  fabricated finding, and an unparseable review must never be rendered as a clean one.
- **AC6** F11 fails when any type is `pending`, when the file is missing at
  small+, and when the file is schema-invalid or corrupt — each with a distinct,
  actionable message naming the command that closes it; it passes when all five
  are terminal, and skips at trivial.
- **AC7** The `external_*review_state.json` markers are **dual-written**: the
  existing shared path is written exactly as today (no consumer anywhere can
  break) *and* a run-scoped copy lands in `<run_id>/`. `iterate_compliance` W2
  resolves either.
- **AC8** Integration: a real run of the CLI across all five types produces a
  record that the F11 gate then passes, in one temp-project scenario.
- **AC9** `init` is create-if-absent only: re-running it over a populated record
  leaves it unchanged, and over a corrupt one it fails rather than replacing it.
- **AC10** A record written before this change exists (no `reviews.json`) is
  closed by a single `close-missing` command rather than trapping the run.
- **AC11** Empty native payloads are `completed` with zero findings, not errors:
  `code-reviewer` `{"review": []}`, `doubt-reviewer` `{"doubts": []}`, and a
  self-review with every item passing.

## External plan review — findings and disposition

Two providers via OpenRouter (gemini + openai), 2026-07-22. The record this
change produces parses **17** findings from that payload (5 gemini + 12 openai);
an earlier draft of this table said 13, having been written by reading the
review rather than counting it. The four extra rows are at the end — for an
iterate whose thesis is "stop discarding what reviews found", an undercount in
its own accounting is the same failure one layer up, and it is now falsifiable
directly against `reviews.json`.

| # | Sev | Finding | Disposition |
|---|---|---|---|
| G1/O1 | high | No specified data path from the reviewer agent's reply to the CLI | **accepted** — the orchestrator writes the agent reply to a temp file and passes it; the tool accepts Markdown-with-```json``` (AC1). Prompt contract names the call site per pass. |
| O2 | high | "One call ⇒ the two artifacts cannot drift apart" is false — two files are not transactional | **accepted** — claim was wrong. Validate + immutability check BEFORE any write; record is authoritative and written first; marker write is idempotent and repairable; one per-run lock spans both. |
| O3 | high | Moving the marker writer can break unknown consumers | **accepted, and it improved the design** — switched from *move* to **dual-write** (AC7). The shared path keeps its exact current behaviour, so no consumer can break and there is no old-layout/new-layout negotiation. |
| O4 | high | A clean external review would be turned into one fabricated finding | **accepted — this was a real correctness bug.** Zero parsed blocks now yields `findings: []` + `parse_status: "unstructured"` + retained raw text (AC5). Neither fabricate nor silently claim clean. |
| O5 | med | No strict schema validation on read/write | **accepted** — `read_record()` validates (exactly five keys, key==`review_type`, closed statuses, `findings_count == len(findings)`, disposition required on terminal non-completed, `run_id` matches expected); the gate treats a violation as corrupt. |
| O6 | med | `init` could clobber a populated record; races underspecified | **accepted** (AC9) — create-if-absent, fail on corrupt, materialization and upsert under the same lock. |
| O7 | med | The gate is satisfiable by marking everything `not_run` | **partially accepted** — a prompt-driven system cannot structurally prove who decided to skip. Enforced what is enforceable: dispositions must name a rule (AC2), blank/generic rejected. Residual risk documented; the alternative (re-encoding the phase matrix in the verifier) was rejected as drift-prone. |
| O8 | med | Adapters need explicit empty / malformed handling | **accepted** (AC11). |
| G2 | med | In-flight runs trapped by the new hard gate | **accepted in a different form** — added `close-missing` (AC10), one command. Rejected the suggested timestamp grace period: "older than this commit" is not determinable at runtime and an unauditable silent pass is exactly what decision 2 rules out. |
| G3 | low | Fallback finding lacks required-field defaults | **accepted**, superseded by the AC5 redesign. |
| G4 | low | Merge `review_findings.py` into `review_record.py` | **rejected** — combined they exceed the 300-LOC file limit the constitution imposes. The split is required, not preference. |
| G5 | low | `makedirs` race on init | **accepted** — `exist_ok=True` before lock acquisition. |
| O9 | med | A git-tracked artifact carrying raw external-review prose and arbitrary agent-produced text: secrets exposure, and untrusted content rendered by a cross-repo consumer | **accepted, bounded** — `reviews.json` IS tracked by design (verified: `git check-ignore` clears it; the markers stay ignored via `.gitignore:220`), because an audit artifact nobody keeps is not an audit artifact. The exposure class is not new — `{run_id}-external-review.json` payloads have been tracked for months. Bounded by `MAX_TEXT_CHARS` / `MAX_RAW_EXCERPT`, and the record carries reviewer prose only, never environment or credentials. **Consumer contract:** finding text is UNTRUSTED agent output and must be rendered as escaped text, never as markup — recorded here because the consumer is in another repository. |
| O10 | med | Paths derived from `run_id`; payload-file paths | **accepted — found independently in self-review and FIXED.** `is_safe_run_id` forces a single path component (an absolute `run_id` silently replaced `project_root`); 10 hostile inputs covered. `--payload-file` is an operator-supplied CLI argument, not untrusted input, and is read-only. |
| O11 | low | "Git-tracked, never evicted" needs repository policy, not just a write | **accepted, verified empirically** rather than assumed: `git check-ignore` exits 1 for `reviews.json` and `git ls-files` finds it. Unlike `.shipwright/agent_docs/iterates/`, this path has no 50-entry retention, so "never evicted" holds. |
| O12 | low | Is the module split justified? | **acknowledged** — the splits are forced by the constitution's 300-line file limit, not chosen. Same answer as G4. |

## Code review — findings and disposition

Internal `code-reviewer` (11 findings) + external cascade, gemini + openai
(2026-07-22). All three converged on the marker/lock cluster, which turned out
to be the weakest part of the change. Every finding below is FIXED in this diff
unless the disposition says otherwise.

| Sev | Finding | Disposition |
|---|---|---|
| high | The marker was written AFTER `upsert_and_write` released the lock, contradicting the spec's own O2 disposition | **fixed** — `upsert_and_write` takes an `after_write` callback that runs while the lock is still held; the marker is written through it. |
| high | "Re-run this command to repair the marker" was FALSE — a re-run hits the immutability guard and exits 3 before reaching the marker | **fixed** — added `repair_companion` / `repair-markers`, which rewrites the marker from the already-recorded entry without touching it; re-running the original command now repairs instead of dead-ending. |
| high | Recording `plan` / `external_code` without `--marker-status` left marker consumers with no evidence while the new gate read green (AC7) | **fixed, narrowed** — required when recording those types as `completed`. NOT required for `not_run` / `not_applicable`: the marker vocabulary has no term for "not applicable at this complexity", so forcing one would make the caller misstate why the pass did not run. |
| med | `--marker-status` was unvalidated, losing a check `mark-review-state.py` enforces | **fixed** — validated against `ALLOWED_STATUSES`; a typo is now exit 2 and writes nothing. |
| med | W2 credited the run-scoped marker by EXISTENCE alone, making its status logic dead code — a garbage status would pass where the same content at the shared path fails | **fixed** — `_w2_status_finding` applies the same status check to both, and run-specific evidence decides alone (falling back to the shared file would launder a bad marker into a pass). |
| med | `_parse_blocks` opened a block only on `Category`, silently dropping every finding in a category-less layout while still reporting `structured` | **fixed** — a block opens on the first key of any kind. |
| med | Merged `parse_status` was `structured` if ANY provider leg parsed, hiding a leg whose review was lost; the raw excerpt was truncated across legs | **fixed** — added `partial`; each leg gets its own excerpt budget, and truncation is marked. |
| med | A missing native result array (`{}`, `{"section":"x"}`) read as a clean review | **fixed** — the key must be present and a list; only an explicit `[]` means "found nothing". |
| med | `MAX_FINDINGS` silently truncated, so `findings_count` could describe a partial review as complete | **fixed** — an oversized payload is now REJECTED rather than shortened; per-finding text truncation is marked with `[…truncated]`. |
| med | `_cmd_init` had no error handling and `LockTimeout` escaped every handler, breaking the JSON contract the orchestrator parses | **fixed** — both route through `_fail`. |
| med | The spec claimed 13 external plan-review findings; the record says 17 | **fixed** — reconciled above, with the four missing dispositions added. |
| low | `coerce_severity` scanned for substrings, so "not high" became `high` | **fixed** — anchored to the leading token. |
| low | The last block's value ran to end-of-text, gluing the reviewer's closing summary onto the final suggestion (visible in this run's own first artifact) | **fixed** — terminates at the next heading or horizontal rule. |
| low | `close-missing` reported a concurrent close as `invalid_entry` (exit 2) instead of the documented exit 3 | **fixed**. |
| low | Unused `provider` parameter on `from_external_prose` | **fixed** — removed. |

## Doubt review (Stage 3) — findings and disposition

Fresh-context disprove pass against five named claims, run on the post-fix diff.
7 doubts (3 high). It was the most productive pass of the three, and two of its
findings would have shipped a feature that did not work.

| Sev | Doubt | Disposition |
|---|---|---|
| high | **The record was never staged.** F6's explicit `git add` list has `.shipwright/planning/iterate/*.md`, which cannot match `<run_id>/reviews.json`, and `check_review_record` accepted `commit_hash` and never used it. So: F6 commits without the record → F11 passes on working-tree presence → PR merges → worktree removed → **the record is gone from the tree the Mission view reads.** The feature would have been a no-op in main. | **fixed — this was the ship-blocker.** Added the run dir to F6's staging list with the rationale, and `check_review_record` now asserts the record is in the commit when it is tracked (mirroring `check_events_has_commit`'s AC4 layer, which exists because events.jsonl had this exact bug). Skipped when untracked or when no commit is supplied. Verified with real git repos, not mocks. |
| high | **A rejected write was reported as success.** `_repair_or_reject` turned ANY immutability rejection into exit 0 `repaired: true` whenever `--marker-status` was present, rewriting the marker from the NEW arguments — so recording `plan` as `not_run`/`skipped_config_disabled` over a `completed`/17-finding entry returned success, left the record saying `completed`, and flipped both markers to "skipped". No `--force`. Disproves "cannot be quietly restated" AND "cannot disagree" in one command. | **fixed** — a repair now requires the requested status to EQUAL the recorded one; anything else is exit 3. Response carries `record_unchanged: true` so no caller reads a repair as "my record landed". Also: `--force` on a marker type now requires `--marker-status`, so a forced correction cannot leave the marker asserting the superseded result. |
| high | **AC5's protection stopped at the boundary it was written for.** `parse_status` exists in the record but not in the marker nor in the pinned cross-repo `ReviewRow`, so a completed-but-unitemizable review reached the consumer as `completed / 0` — which `review-state.ts` renders as "ran and found nothing". O4's fabrication, displaced one repo downstream. Separately, an errored provider leg (no `feedback` key) was filtered out BEFORE the denominator, so one good leg of two reported `structured`. | **fixed** — the caveat is carried into the marker's `reason`, the one field the consumer already surfaces (as `disposition`). Errored legs now count toward the denominator and their failure reason is kept in `raw_excerpt`. |
| med | **Element-level loss.** An item missing its `finding` text was silently skipped, so a reviewer writing `issue` instead of `finding` recorded as `completed / 0` — byte-identical to an honest clean review, and the likeliest malformation when the producer is an LLM. `_items` already refuses a *missing array* on exactly this reasoning. | **fixed** — `_no_element_loss` compares items-in to findings-out in all three native adapters and refuses the payload. One earlier test asserted the old dropping behaviour; it was rewritten, because that test pinned the defect. |
| med | **The mandated `File:line` label mis-parsed**, storing a path of ``line: `path` ``. Not exotic input — it is the layout `shared/prompts/code_reviewer/system` asks for, and it was present verbatim in this run's own first artifact. | **fixed** — the key form is recognised; the real gemini string is now a fixture, and the two affected entries were re-recorded with `--force` (the legitimate "genuinely wrong record" case). |
| med | **`close-missing` was blanket, one-way and non-atomic** — no type scope, so it permanently asserts "did not run" for the self-review, which always runs; and each type was written under its own lock acquisition, so a mid-loop failure left an irreversible half-state on the very command meant to unblock a stuck run. | **fixed** — added `--only`, and `close_pending` writes the whole batch under ONE lock in ONE record write (all-or-nothing). |
| low | **The error path guessed.** The `OSError` handler asserted "the record was written but the marker was not" for every failure, including ones from `mkdir` / the lock / the record write itself — and interpolated `--marker-status None` into a repair hint argparse rejects. | **fixed** — a flag set when the record write returns decides the message; the hint is suppressed when no marker was requested. |

## Affected Boundaries

New serialized format. **Producer:** `shared/scripts/lib/review_record.py` via
`shared/scripts/tools/record_review_pass.py`. **Consumers:** (1)
`verifiers/review_record_check.py` in this repo — same-diff, covered by AC8;
(2) `shipwright-webui` `server/src/core/mission-context/review-state.ts` —
cross-repo, the highest-risk consumer, covered by the follow-up and by pinning
the on-disk shape in a round-trip test here (AC4).

## Confidence Calibration

- **Boundaries touched:** one new serialized format, `reviews.json`. Producer
  `lib/review_record_core.py` via `tools/record_review_pass.py`. Consumers:
  `verifiers/review_record_check.py` (same repo) and — the risky one —
  `shipwright-webui` `server/src/core/mission-context/review-state.ts`, in a
  DIFFERENT repository, where a serialization defect surfaces as a wrong Mission
  view rather than a failing test. Also touched: the `external_*review_state.json`
  marker (dual-written, never moved) and the W2 gate that reads it.

  **The automated detector does NOT flag this change.** Recomputed from the
  actual diff: `touches_io_boundary: False`, `cross_component: False`,
  `touches_ci_supplychain: False`. `IO_BOUNDARY_FILE_PATTERNS` is path-based
  (`*_state.json` / `*_config.json` / `.env*`), and this artifact is named
  `reviews.json`. The flag was therefore declared by hand and the round-trip
  probe run anyway — a gate that does not fire is not evidence of a boundary
  that is not there.

- **Empirical probes run:**
  1. **Parser against 8 REAL payloads on disk**, not fixtures — every
     `*review*.json` in `.shipwright/planning/iterate/` plus this run's own plan
     review. 7 of 8 parsed structured (4–14 findings each, severities
     distributed as expected). The 8th is a truncated stream-of-consciousness
     from gemini with no finding blocks at all, and correctly came back
     `unstructured` with ZERO findings — confirming the parser separates "found
     nothing" from "could not be read" on real data, which is the property AC5
     exists for.
  2. **Path-traversal probe.** `record_path(project, "C:/Windows/Temp/x")`
     returned `C:\Windows\Temp\x\reviews.json` — the project root silently
     replaced. Found in self-review, fixed, and pinned with 10 hostile inputs.
  3. **Git-tracking probe.** `git check-ignore` exits 1 for `reviews.json` and
     `git ls-files` finds it; the markers ARE ignored (`.gitignore:220`). The
     "git-tracked, never evicted" claim is verified, not assumed — and the
     record/marker split (durable artifact vs. transient gate state) is what the
     ignore rules already encode.
  4. **Dogfooding.** This run recorded its own five passes through the tool:
     `self` (1 finding), `plan` (17), `code` (11), `external_code` (10), `doubt`.
     The 17 vs. the 13 this spec first claimed is what exposed the accounting
     error the code review then flagged — the artifact caught its own author.
  5. **Risk-flag recomputation** (above), which is how the detector gap was found.

- **Test Completeness Ledger:** 137 tests over the new surface, all green.
  Behaviors enumerated in `shipwright_test_results.json`
  → `iterate_latest.test_completeness`; **0 testable-but-untested**. The only
  `untestable` row is the prompt contract itself (whether an agent obeys the
  instruction to record a pass), whose structural half — links resolve, budgets
  hold, references exist — is `covered-by-existing-test` via the
  `shipwright-iterate` plugin suite (506 tests). Includes one
  `category: "integration"` behavior (AC8): the CLI driven across all five types
  from real reviewer payload shapes, then the F11 gate run against the result.

- **Confidence-pattern check:**
  - *Asymptote (depth).* Three independent review passes plus self-review found
    **18 distinct defects**, of which **2 were mine before any reviewer saw the
    code** (path traversal, and the trailing-prose bug visible in the artifact
    the run itself produced). The reviewers did not converge on nothing — they
    converged on one CLUSTER (marker/lock ordering, flagged by all three), which
    is the signal that the cluster was genuinely the weak part rather than that
    the depth was exhausted. Post-fix, the Stage-3 doubt pass attacked five
    named claims from a fresh context.
  - *Coverage (breadth).* All five review types, all four adapter shapes, both
    verifier gates (new F11 check + the modified W2), the CLI's five
    subcommands, and every documented exit code. Deliberately NOT covered: the
    webui consumer's own rendering — it lives in another repo and is the named
    follow-up.
  - *Integration composition.* `cross_component` does not fire, so no
    integration coverage is forced; AC8 provides one anyway, because the piece
    most likely to break is the seam between the CLI that writes and the gate
    that reads.
  - *Residual, stated plainly.* The gate can be satisfied by closing every type
    `not_run`. A prompt-driven lifecycle cannot structurally prove who decided
    to skip a pass; what is enforced is that the skip is written down and names
    a rule. Re-encoding the phase matrix inside the verifier was rejected as
    drift-prone — the matrix moves, and a second copy goes stale silently.
