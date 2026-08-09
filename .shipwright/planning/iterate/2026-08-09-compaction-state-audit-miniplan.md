# Mini-Plan: compaction-state-audit

- **Run ID:** iterate-2026-08-09-compaction-state-audit

Revised after Internal Plan Review (opus-plan-reviewer, severity: high,
11 findings), then again after Branch A external review + Architecture
Review (both converged on the same ask a second time) — see the iterate
spec's `## Internal Plan Review`, `## External Plan Review` and
`## Architecture Review` sections for the full disposition tables. Two
changes since the first draft: (1) B1's replay-check now reads
`reviews.json` **directly**, not via `session_handoff.md` — that handoff
copy is gitignored/runtime-only and a killed-mid-phase run never gets it
regenerated, so it cannot be the authoritative signal; (2) a `SubagentStop`
salvage hook now backs the immediate-write prose mandate with a code-level
fallback for the three internally-spawned reviewers. Revised a third time
after the Step 8 review cascade (spec-reviewer PASS, code-reviewer + the
external code-review cascade both found real, independently-verified gaps):
the salvage hook's file-write path is now wrapped fail-open, and the
"missing-record" notice work item 2d actually planned (silent when
complexity is unresolvable) — dropped from the first implementation pass —
is now built and tested. See the iterate spec's `## External Code Review`
section for the full disposition table, including one finding rejected with
reason (the dual-import-pattern suggestion — re-verified independently, not
applicable to this file's actual loading path).

## 1. Files to create/modify

- `plugins/shipwright-iterate/skills/iterate/references/iteration-planning.md` — Mini-Plan Protocol → Persistence: remove the `small`-tier "no file" exemption (applies to every tier that runs the protocol).
- `plugins/shipwright-iterate/skills/iterate/references/path-a-feature.md` — Step 3 header/body to match.
- `plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md` — "Recording each review pass": add the immediate-write ordering mandate paragraph.
- `plugins/shipwright-iterate/skills/iterate/SKILL.md` — §B1: add the direct `reviews.json`-read replay clause (primary fix, AC-3a); Step 8: add the one-clause immediate-write imperative + run_id-in-prompt requirement at the cascade spawn point.
- `plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md` — **3f-bis** (the actual autonomous-cascade spawn site — NOT `sub-iterate-runner.md` Step 3.7, which only delegates to the orchestrator and never calls the `Agent` tool itself): same one-clause imperative + run_id-in-prompt requirement, since both observed compactions were autonomous runs.
- New: `plugins/shipwright-build/scripts/hooks/write-review-payload-on-stop.py` — `SubagentStop` salvage hook for `spec-reviewer`/`code-reviewer`/`doubt-reviewer`; self-contained (no `shared/scripts/lib` import — would collide with `plugins/shipwright-build/scripts/lib`'s own `lib` package name in that plugin's pytest process, ADR-044).
- `plugins/shipwright-build/hooks/hooks.json` — wire the new hook under `SubagentStop`, one matcher per review agent.
- New: `plugins/shipwright-build/tests/test_review_payload_on_stop.py`.
- `shared/scripts/lib/handoff_iterate.py` — `render_iterate_progress()`: read `reviews.json` via `lib.review_record_core.read_record`/`pending_types` (not a hand-rolled reader); reword as descriptive state; explicit line on a missing record at small+ resolvable complexity; `run_id` fallback from a `*-miniplan.md` header when no spec file exists.
- `shared/scripts/tools/verifiers/spec_checks.py` — `check_s3_iterate_miniplan`: WARN at `small` when `_iterate_category(...) == "feature"` (reuses the existing helper), keep SKIP at `small` for change/bug.
- `docs/hooks-and-pipeline.md` — context-loading matrix: Stop hook now also reads `reviews.json`.
- `docs/guide.md` — check Chapter 4/8 for the small-tier "inline only" mini-plan wording being changed.
- New: `shared/tests/test_review_cascade_handoff.py` — the checked-first "near its size cap" case actually hit: `test_generate_session_handoff.py` carries a grandfathered bloat-baseline entry (`current: 511`, limit 300); appending the 6 new review-cascade cases there measured 668 lines, ratcheting the anti-ratchet gate (`shared/scripts/hooks/anti_ratchet_check.py`, confirmed by running it against staged content). Split into this new sibling file instead — the intended remedy per its own printed remediation list ("split the file"), not a baseline bump.
- New: `plugins/shipwright-iterate/tests/test_mini_plan_persistence_doc.py`.
- New: `plugins/shipwright-iterate/tests/test_review_record_immediate_write_rule.py` (asserts the mandate at all three prose sites: iteration-reviews.md, SKILL.md Step 8, campaign-mode.md 3f-bis).
- New: `plugins/shipwright-iterate/tests/test_skill_b1_reviews_json_check.py` (doc-presence: B1's prose names the direct `reviews.json` read).
- New: `shared/tests/test_spec_checks_s3_miniplan_gate.py` — same reason: `test_spec_checks.py` is also grandfathered (`current: 665`); the two new S3 cases went here instead of extending it. `spec_checks.py` itself (`current: 783`) stayed in-place — its net addition (`_miniplan_required` + the S3 body edit) fit under the ceiling once condensed to avoid a second split for a ~10-line change.

## 2. Work breakdown

1. Read `shared/tests/test_generate_session_handoff.py` in full first — note its existing assertion `'Mandatory replay on Resume' not in text` (line ~283 per Internal Plan Review finding #10) and its fixture shape (git_info dict, tmp project_root layout); the new tests must not break that assertion by accident, and must match its exact fixture conventions.
2. Patch `render_iterate_progress()` in `shared/scripts/lib/handoff_iterate.py`:
   a. Import `read_record`, `pending_types`, `ReviewRecordError` from `lib.review_record_core` using the same relative-then-absolute dual-import pattern as `review_record_schema.py` (so it works both as a package import and via the Stop hook's `sys.path` route).
   b. `run_id` fallback: when `spec_path` is `None` (no spec below medium), glob `iterate_dir.glob("*-miniplan.md")` filtered by `short in name`, take the newest by mtime, and parse the same `- **Run ID:**` header line the spec-path branch already parses (`complexity` stays unavailable from a mini-plan header if it doesn't carry one — check the actual mini-plan template; if it doesn't, leave `complexity` empty as today).
   c. After the existing external-review-marker block: if `run_id` is set, call `read_record(project_root, run_id)` inside a `try`/`except ReviewRecordError` (treat as absent on error — matches the existing degraded philosophy elsewhere in this function); if a record exists, compute `pending = pending_types(record)`; if non-empty, append ONE descriptive (not imperative) line, e.g. `"Review types still unanswered in reviews.json: {', '.join(pending)} (each needs a status or disposition before F11 — some may be not_applicable at this complexity)."` — placed as its own bullet near the External Review Marker line, NOT inside the "Mandatory replay on Resume" block (that block stays reserved for the two existing, genuinely-due-now instructions).
   d. If `run_id` is set, complexity is resolvable and in `("small","medium","large")`, and `read_record` returns `None` (no file): append an explicit line stating no review record exists yet for this run — informational, not alarming, and never raised for an unresolvable-complexity case (stay silent there, matching today's degraded behavior).
3. Write the new/extended tests per work item 1: pending-type-surfaced (descriptive wording), mixed-realistic-record-no-false-command, missing-record-explicit-at-small-plus, missing-record-silent-when-complexity-unresolvable, run_id-fallback-from-miniplan-header, and one importing `lib.handoff_iterate` via the hook's actual `sys.path` route (import-safety regression guard per finding #10c).
4. Edit `iteration-planning.md` Mini-Plan Protocol → Persistence: single rule — "Save as `.shipwright/planning/iterate/{date}-{desc}-miniplan.md` at every complexity tier that runs this protocol" — keep Content items 2 (work breakdown) and 6 (alternative approach) gated `(medium only)`; only persistence changes for `small`, not content depth.
5. Edit `path-a-feature.md` Step 3 heading/body to match.
6. Write `test_mini_plan_persistence_doc.py`: extract `## Mini-Plan Protocol` → `## Escape Hatch Protocol` body (same anchor-and-assert pattern as `test_skill_step_6_rules_present.py`); assert no `small`-only "no file"/"inline in session only" carve-out remains, and the persistence sentence applies unconditionally.
7. Edit `iteration-reviews.md` "Recording each review pass": add the ordering-mandate paragraph (rationale lives here).
8. Edit `SKILL.md` Step 8: add the one-clause imperative at the cascade-spawn instruction ("write the reviewer's raw reply to its payload file as your very next action after it returns, before any other reasoning or the next spawn").
9. Edit `SKILL.md` §B1: add the third replay clause — read `reviews.json` directly via `record_review_pass.py show`, gated on `self` being terminal before treating any other pending type as a real interrupted-cascade signal (not merely "not yet due"). Keep the existing two-marker sentence — it covers a different, still-real check (`plan_internal`/`self` via the ADR block).
10. Edit `campaign-mode.md`'s 3f-bis: same one-clause imperative + run_id-in-prompt requirement as SKILL.md Step 8 (the actual autonomous spawn site — corrected from the original `sub-iterate-runner.md` Step 3.7 target after re-reading it: that step *delegates* the cascade, it has no `Agent` tool and never spawns it itself).
10b. Write `plugins/shipwright-build/scripts/hooks/write-review-payload-on-stop.py` (self-contained — no `lib.xxx` import, see file-list note) + wire it into `plugins/shipwright-build/hooks/hooks.json` under `SubagentStop`, one matcher per review agent. Write `plugins/shipwright-build/tests/test_review_payload_on_stop.py`; run the FULL `plugins/shipwright-build` test root afterward (not just the new file) to confirm no `lib` name collision with `test_config.py`/`test_sections.py`.
11. Write `test_review_record_immediate_write_rule.py` asserting the mandate text at all three sites (iteration-reviews.md body, SKILL.md Step 8 body, campaign-mode.md 3f-bis body) using each file's own anchor-and-assert pattern.
12. Write `test_skill_b1_reviews_json_check.py` asserting the B1 section body names the direct `reviews.json` read.
13. Edit `spec_checks.py`'s `check_s3_iterate_miniplan`: change the gate from `_is_medium_or_larger(complexity)` to `_is_medium_or_larger(complexity) or (complexity == "small" and _iterate_category(project_root, run_id) == "feature")`; keep the SKIP message accurate for the change/bug+small case (still correctly "not required").
14. Extend `test_spec_checks.py` with the two new cases (WARN at small+feature, SKIP at small+change and small+bug).
15. Update `docs/hooks-and-pipeline.md`'s context-loading matrix for the Stop hook (now also reads `reviews.json`); check `docs/guide.md` Chapter 4/8 for the small-tier mini-plan wording.
16. Run, per this repo's one-test-root rule: `shared/tests`, `plugins/shipwright-iterate/tests`, and any other root touched (check `record_review_pass.py`'s own test location if the S3/handoff changes have neighbors there).
17. Acceptance test (AC-4): build a fixture `reviews.json` (`self`, `spec` completed; `code` pending; rest pending) under a temp run dir; (a) drive `generate_handoff_on_stop.py`'s real entrypoint end-to-end against it and confirm `code` is named in the file it actually writes; (b) separately confirm the B1 direct-read path (simulate via `record_review_pass.py show` + `pending_types`) also names it. State explicitly in Self-Review that a literal same-session kill-and-restart could not be performed from inside the session doing the fix, and that (a)+(b) are the closest deterministic substitute — driving the actual production code paths rather than an isolated unit-level fixture.
18. Run `uv run scripts/verify_local.py` before considering the change ready for F0.

## 3. Component hierarchy

n/a (no UI).

## 4. Data model changes

None — `reviews.json`'s schema (`review_record_schema.py`) is read-only here, not altered.

## 5. Test strategy

Unit tests (`shared/tests/`, alongside existing handoff/spec-check tests — not a new root) for the `render_iterate_progress` and `spec_checks.py` changes; meta-tests (`plugins/shipwright-iterate/tests/`) for the four prose changes (mini-plan persistence, immediate-write mandate ×3 sites, B1 direct-read), following the repo's existing anchor-and-assert convention exactly. No E2E — no web/cli/api surface (Verification section: `surface: none`).

## 6. Alternative approach (considered and rejected)

**Alternative:** give review subagents Write access so they self-persist findings the instant they finish, closing the review-findings gap at the source instead of via an orchestrator ordering mandate.

**Rejected because:** it changes the security/capability surface of four subagent definitions that are deliberately restricted to `Read, Grep, Glob` (a review agent should not be able to write to the codebase it's reviewing — that boundary is intentional, not an oversight). It is also a larger blast radius than this bug fix needs: an ordering mandate at each spawn site (the orchestrator already has Write/Bash) closes the same window without touching subagent capability grants. Internal Plan Review (finding #8) confirmed the mandate needs repeating at every spawn site to be reliable, but did not challenge the underlying "orchestrator writes, not subagent" design — if the ordering-mandate approach proves insufficient in practice (agents keep deferring the write despite explicit instruction), that would be grounds for revisiting this alternative in a follow-up iterate, not folded in here.
