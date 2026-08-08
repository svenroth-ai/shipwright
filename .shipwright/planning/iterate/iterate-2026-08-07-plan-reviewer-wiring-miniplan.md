# Mini-Plan: plan-reviewer-wiring

- **Run ID:** iterate-2026-08-07-plan-reviewer-wiring

## 1. Files to create/modify

| File | Change |
|---|---|
| `plugins/shipwright-plan/skills/plan/SKILL.md` | edit — Step 5 intro paragraph gains one line naming the new always-first internal pass; Branch B/C bullets shrink (net LOC target: <=300, currently exactly 300) |
| `plugins/shipwright-plan/skills/plan/references/step-5-external-review.md` | edit — new `## Step 5-int` section (spawn + triage + scope-ratchet guard + plan.md template + decision_log logging + no-marker note), Branch A finding-triage wording aligned to the same vocabulary, Branch B/C text points at Step 5-int instead of running Self-Review Fallback, Self-Review Fallback sub-block gets one line marking it fallback-of-last-resort (LOC target: <=400, currently 290) |
| `plugins/shipwright-plan/skills/plan/references/external-review.md` | edit — Purpose (l.10), Prerequisites (l.20) and Graceful Degradation (l.57-63) all currently say the missing-key/opt-out path "falls back to self-review"; each gets a clause naming the internal review as what now carries it |
| `plugins/shipwright-plan/skills/plan/references/step-9-completion.md` | edit — l.109 Session Report `Review:` enumeration adds "internal review (opus-plan-reviewer) + {external outcome}" so the printed summary does not still read as self-review-only on B/C |
| `plugins/shipwright-plan/skills/plan/references/first-actions.md` | edit (found by spec-reviewer REJECT #1, not the internal review's file scan) — the startup-banner Requirements block and the single_session auto-default gate-policy paraphrase both still described the old self-review fallback |
| `plugins/shipwright-plan/skills/plan/references/error-handling.md` | edit (found by spec-reviewer REJECT #1) — the missing-API-keys section's Option 2 description |
| `plugins/shipwright-plan/agents/opus-plan-reviewer.md` | edit — **`description:` frontmatter line only** ("fallback when external LLM review is unavailable" is now stale; the pass always runs first). No change to `tools`, `model`, or the prompt body |
| `shared/config/gate_catalog.json` | edit — `plan.external-review-missing-keys` entry's `default_answer` + `summary` updated to name the internal review instead of the self-review fallback (+ cost note per finding 6 disposition); **new entry** `plan.internal-review-high-severity-declined` (auto-default, per finding 3 disposition) |
| `shared/config/gate_catalog.md` | regenerate via `resolve_gate_policy.py --render-doc` (never hand-edited) |
| `docs/guide.md` | edit — the `/shipwright-plan`-specific passages describing Step 5's fallback: the 4.4 Purpose paragraph, the numbered-flow bullet, and the "Option C" provider-setup block (l.1489) |
| `.shipwright/planning/01-adopted/spec.md` | edit — FOLD one new acceptance criterion into FR-01.03 |
| `.shipwright/agent_docs/decision_log.md` | append — internal-plan-review finding entries (this run's own dogfood pass) + the wiring decision itself |

No `.py` file changes are planned — `check-plan-gates.py`, `review_marker.py`,
`mark-review-state.py` all stay untouched (verified: the internal pass writes
no marker of its own; on Branch B/C it reports through the marker's
*existing* `--findings-count`/`--reason` fields, per the Step 5a Architecture
Review precedent already in this same file — see finding 2's disposition).

## 2. Work breakdown

1. **Draft `## Step 5-int` in `step-5-external-review.md`.** Spawn
   `shipwright-plan:opus-plan-reviewer` (Read/Grep/Glob, `model: opus` from
   its own frontmatter — no override) over `{planning_dir}/plan.md` +
   `{spec_file}`. Parse its JSON (`reviewer/severity/findings[]/summary`).
   Triage each finding `fix` / `disclose` / `decline` (reason required for
   decline; scope-ratchet guard: decline anything that would add scope the
   spec calls unsupported). Append `## Internal Plan Review
   (opus-plan-reviewer)` to `plan.md`. Log each non-trivial finding via
   `write_decision_log.py --section "Internal Plan Review — {split_name}"`.
   Explicitly no marker written. Test expectation: `test_every_kern_link_resolves`
   / LOC-budget tests still green after the addition.
2. **Rewire Branch A/B/C text.** Branch A: unchanged mechanics, add one
   clause "runs after the internal pass" + align finding-triage wording to
   fix/disclose/decline. Branch B: Option 2 text stops saying "run the
   Self-Review Fallback sub-block", says the internal pass already carries
   the gate. Branch C: same substitution. Self-Review Fallback sub-block
   itself: keep the content, prepend one line scoping it to "Agent tool
   unavailable" as fallback-of-last-resort. Test expectation: existing
   `plugins/shipwright-plan/tests/` suite green, no assertion breaks.
3. **Edit `SKILL.md` Step 5** to match (name the always-first pass, keep
   the section at or under 300 LOC total file). Test expectation:
   `test_kern_skill_md_under_300_loc` PASSED.
4. **Edit `external-review.md`** two sentences for consistency (Purpose +
   Prerequisites bullet). No test — prose-only, covered by the same link
   test suite (no new links added here).
5. **Edit `gate_catalog.json`** entry `plan.external-review-missing-keys`,
   then regenerate `gate_catalog.md`. Test expectation:
   `test_doc_matches_generated_catalog` PASSED, `test_gate_catalog.py` full
   suite green (no schema change, just string edits).
6. **Fold FR-01.03** in `.shipwright/planning/01-adopted/spec.md` — one new
   `(E)` acceptance-criterion line, MODIFY not ADD.
7. **Update `docs/guide.md`** — the three passages identified in file scan.
8. **Dogfood this exact mini-plan** through the new Step 5-int protocol
   before writing it into the reference file: spawn `opus-plan-reviewer`
   over this mini-plan + the FR-01.03 spec section, fold its findings here
   and into the iterate ADR, *then* run this iterate's own external-review
   mirror (`iteration-planning.md`'s Branch A/B/C) per the WICHTIG
   instruction — internal review before the external pass, findings folded.
9. **Self-review + full code review cascade** (spec-reviewer → code-reviewer
   → doubt-reviewer, `model=opus` per explicit instruction — session model is
   Sonnet, subagent spawns are pinned deliberately for this run).
10. **F0-F12 finalization**, ADR entry, changelog drop, PR.

## 3. Component hierarchy
n/a — no UI.

## 4. Data model changes
None.

## 5. Test strategy

- `pytest plugins/shipwright-plan/tests/ -v` (from `plugins/shipwright-plan/`)
  — the plugin's own suite, including the SKILL.md/reference structural
  meta-tests (LOC caps, link resolution).
- `pytest shared/tests/test_gate_catalog.py shared/tests/test_gate_catalog_doc_sync.py -v`
  (from repo root) — catalog integrity + doc-sync drift guard.
- `uvx ruff@0.15.15 check .` — no `.py` files are expected to change, but run
  it anyway since it is a hard CI gate.
- No E2E — this change has no startable surface (see iterate spec
  "Verification (medium+)").
- Live dogfood: this iterate's own Step-5-equivalent pass (item 8 above) is
  the functional proof that the wiring actually works end-to-end, since
  there is no automated test that can spawn an LLM subagent and assert on
  its judgment.

## 6. Internal Plan Review (opus-plan-reviewer) — findings folded

Dogfooded per WBS item 8: `opus-plan-reviewer` (model=opus, spawned live this
run) reviewed this mini-plan + FR-01.03 before any file was edited. 14
findings; disposition below. Full findings text: this run's ADR /
`decision_log.md` entries under `Internal Plan Review — plan-reviewer-wiring`.

| # | Finding (short) | Sev | Disposition |
|---|---|---|---|
| 1 | `disclose` has no destination/enforcement | high | **fix** — `disclose` now writes a `**Known limitations:**` bullet in the `## Internal Plan Review` plan.md block AND a decision_log entry `--decision "disclosed: {why accepted as-is}"` |
| 2 | Branch B/C: nothing records the internal pass ran | high | **fix** — always append `## Internal Plan Review` (even `findings: []`, so an absent section = did not run); on B/C, Step 5b's *existing* `--findings-count`/`--reason` fields (no schema change) carry the internal pass's count + outcome |
| 3 | No escalation when a `severity: high` finding is declined | medium | **fix** — a declined high-severity finding STOPs and asks the user before Step 6 (mirrors Step 5a's reject prompt); new `gate_catalog.json` entry `plan.internal-review-high-severity-declined` for single_session auto-answer |
| 4 | Re-entry not idempotent (Branch B retry / resume re-spawns, duplicate section) | medium | **fix** — Step 5-int runs once; if `## Internal Plan Review` already exists in plan.md, skip re-spawn |
| 5 | Doc ripple undercounted: `step-9-completion.md`, `SKILL.md:5` frontmatter, `external-review.md` Graceful Degradation | medium | **fix** — all three added to the file table below |
| 6 | Unconditional Opus spawn on Branch C overrides the operator's `feedback_iterations: 0` opt-out with the *most* expensive reviewer, undocumented | medium | **decline** — the card names Branch C (`user_disabled`) explicitly as one of "the two branches where external review is unavailable" the internal pass must carry; skipping it there leaves the exact branch the card most wants covered at the old bar. **Partial fix accepted:** document the cost in `docs/guide.md` and the `gate_catalog.json` summary rather than silence it |
| 7 | Scope ratchet: WBS item 2 rewords Branch A's triage vocabulary, contradicting AC-4 (spec's binary "addressed or declined") | medium | **fix** — fix/disclose/decline vocabulary scoped to Step 5-int only; Branch A's existing wording is untouched |
| 8 | No defined behavior for malformed/absent subagent JSON | medium | **fix** — mirrors Branch A's degraded-review rule: unparseable/absent output → internal review did NOT run → record `internal_review: not_run`, fall through to Self-Review Fallback |
| 9 | LOC budget tight, no named payer | medium | **fix (guidance)** — payer is the demoted Self-Review Fallback sub-block (28 LOC), compressed to checklist + output template only |
| 10 | Raw JSON/fenced reviewer output pasted into plan.md risks corrupting SECTION_MANIFEST parsing | low | **fix** — bounded fixed template only (severity/summary/finding-lines/known-limitations/status); raw JSON and fenced blocks from the reviewer are never pasted through |
| 11 | `opus-plan-reviewer.md` description ("fallback when external review unavailable") now stale; domain rubric (SQLi/React) force-fits Shipwright's own infra plans | low | **fix** — narrow Out of Scope to permit editing only the `description:` frontmatter line (discovery metadata, not behavior); spawn prompt at the call site adds one context line telling the reviewer the plan is infrastructure/documentation-shaped |
| 12 | Two unweighed alternatives: internal-only-on-B/C, internal-after-external on Branch A | low | **decline, with reasoning added to Section 6** — the card's own language ("before the external pass", applies generally) and the asymmetry-closing goal both name Branch A explicitly; ordering after would risk anchoring the independent lens on the external findings, which is exactly what running independent-then-cascading (matching spec→code→doubt) avoids |
| 13 | FR-01.03 fold has no draft wording yet | low | **fix** — adopted (below, `## 7. FR-01.03 fold — draft wording`) |
| 14 | Pre-existing `\n` literal bug at `SKILL.md:182,252` (unrelated to this iterate) | low | **disclose** — out of scope, no acceptance criterion covers it, fixing costs LOC this file does not have; noted here and a triage item filed separately |

## 7. FR-01.03 fold — draft wording

Adopted near-verbatim from the internal review (matches FR-01.03's existing
implementation-free register — no filenames, agent names, or tools named):

> (E) Given the outside reviewers cannot be reached or have been switched
> off, when the plan's review step ends, then an independent reviewer has
> still checked the plan against the requirements and its findings are each
> folded in or recorded with a reason — the step is never satisfied by the
> plan's own author re-reading it.

## 8. Alternative approach (considered and rejected)

**Alternative: make the internal review a hard substitute for the external
pass on Branch A too (skip external review whenever the internal pass
already approved), rather than layering both.**

Rejected because it re-creates exactly the asymmetry this card exists to
close, just inverted: code review at medium+ keeps the internal cascade AND
the external pass on the happy path — neither one is allowed to excuse the
other. Making the internal Opus pass a substitute for external review (not
just for self-assessment) would mean a plan gated only by two same-shaped
reviewers (both "read the repo") instead of the two structurally different
lenses (repo-reading Opus + text-only external models) that the card's own
reasoning names as the reason neither is redundant. It would also cut
directly against FR-01.03's existing acceptance criterion that the outside
reviewers are consulted whenever they are available — this alternative would
make availability conditional on the internal pass's verdict, which the
spec does not authorize and this iterate has no mandate to change.

**Alternative: run the internal pass only on Branch B/C (where it is
load-bearing), skip it on Branch A.** Declined — the card's own scope
language ("Wire the plan-reviewer into `/shipwright-plan` Step 5 at medium+,
**before the external pass**") names Branch A's external call as something
the internal pass runs ahead of, not around; the asymmetry-closing goal
("code review... has an internal cascade... PLUS a mandatory external pass.
Plan review has external only") is stated as a general property of the
review step, not conditional on which branch follows. Real added cost on the
happy path, documented rather than avoided (see finding 6 disposition in
Section 6).

**Alternative: on Branch A, run the internal pass AFTER the external one**
(so the repo-reading reviewer also sees the text-only findings). Declined —
inverts the ordering the code-review cascade uses (spec-reviewer's
repo-grounded pass runs first, independent of what code-review/doubt-review
later add) specifically to avoid anchoring an independent reviewer on
findings it did not derive itself. The anchoring risk this alternative
raises is real but cuts the other way: an Opus pass that reads the external
findings first is no longer an independent check on them.
