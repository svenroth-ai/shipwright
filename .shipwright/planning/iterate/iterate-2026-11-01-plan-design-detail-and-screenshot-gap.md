# Iterate: Plan carries design-defined detail; screenshot-check prose matches what it measures

Run: `iterate-2026-11-01-plan-design-detail-and-screenshot-gap` | type: change | complexity: small | triage: trg-845e55d9

Evidence: e2e run 14 (`autorune2e/e2e-report/2026-10-31T08-43-13-059Z-iIc31u/report.md`, check S08), the preserved run
`autorune2e/run-uRPOYL` (`project/`, `gates.jsonl`, Claude session `home/.claude/projects/*/bdb7639d-*.jsonl`), `autorune2e/learnings-run12.md`.

## Part A - where Plan loses design detail

Plan DOES read the approved screens: `agents/section-writer.md` adds a `## Design Reference` block and (since the run-12 fix)
a mandatory `Initial state:` line; `generate-batch-tasks.py` hands the screen list to every section task. What it does not
do is make the writer COPY the other values a screen defines. The run's section text was written from the spec/brief text and
from memory of the kit, and Build's spec-reviewer (`agents/spec-reviewer.md` item 5) correctly REJECTs a section-vs-mockup
contradiction for a person. In the harness the "person" is the first option, which S08 flags.

Proof, run-uRPOYL (per gate):

| Gate | What the section said | What the screen / brief said |
|---|---|---|
| list switch width | `05-board-shell.md` step 1: "master list -> picker at <= 768px as in the screen" (session log, agent a2a5740: `sed -i '70s/<= 768px/<= 900px/'`) | `designs/screens/01-board.html:1227` `@media (max-width: 900px)` governs `.master-pane`; the kit's 768px rule is the top bar. The writer quoted the wrong kit breakpoint and claimed "as in the screen". |
| posted thread | `04-reply-workflow-pane.md`: posted keeps the draft and Copy reply visible | `04-thread-posted.html`: only the note "Posted. Link to your comment saved." The section never said what the posted state does NOT show. |
| link field | section adds "Link to your comment (optional)" beside Mark as posted (FR-02.04 / brief: optional url) | `03-reply-draft.html` has no such field. A real requirement the screen lacks, written into the steps without saying it extends the screen. |

Runs 12/13 (default tab, Draft reply button, thread detail, full text FR-01.04) are the same class; the run-12 fix covered only
the default tab (`Initial state`).

Cause: the writer prompt names ONE class of design-defined value (initial state) and asks for a link for everything else, so
breakpoints, per-state content and requirement-driven additions are paraphrased. Nothing separates a declared extension from a
contradiction, so every extension also costs a human gate in Build.

Fix (prompt-level, no new machinery): `section-writer.md` + the per-section task prompt require (1) the literal `@media` width of
the governing control, (2) a `Per-state content:` line (shown and NOT shown), (3) `Design extension: <element> - <FR/AC id>, not in
<screen>` for requirement-driven additions, (4) `Design contradiction:` for a true spec-vs-screen conflict, taking NO side. Review
(opus doubt/code reviewers) showed that letting the plan agent resolve a contradiction ("screen wins") would bypass the person-decides
rule (FR-01.05 AC05, `requirement-writeback.md`). The PR Review (Haiku, sensitive path) then also blocked a reviewer/builder relaxation for
declared extensions as a human-gate change needing a maintainer. Decision: NO gate change at all. Build's spec-reviewer, build SKILL and
self-review checklist are untouched; `Design extension:` / `Design contradiction:` lines only make the question visible at plan time. The cost: a
true requirement-driven extra (the link field) still costs one person question in Build; that is the intended trade.

Not fixed: whether Build should ever ask a person for a plan-vs-screen difference is unchanged (it should; the plan now stops creating
false ones). The S08 harness answering "first option" is the harness's concern.

## Part B - the Test-phase override

Check that failed: **Step 3.7b Screenshot Check (blocking, Brief package)**, not a font/token check. `shipwright_test_results.json`
`screenshot_check`: metric `grid-luma-occupancy-diff-ratio`, tolerance 0.15, 3 of 5 pass; `02-thread` 0.1766, `03-reply-draft` 0.175;
`screenshot_check_history`: attempt 1 (system fonts, ADR-010) 0.1578 / 0.1625, attempt 2 (Inter + Geist Mono bundled, ADR-082)
0.1766 / 0.175. Passing screens: 0.1328, 0.0797, 0.1094. All other layers green (362 unit, 38 browser, 16/16 journeys).

Why: the compared pair is the approved screen (designer's short sample text) against the built page showing the recorded thread
text (the two failing screens click a long thread). The metric counts per-cell text occupancy and luminance, so length moves cells.
`step-3.7b-screenshot-check.md` claimed "It sees layout, not wording" - false for text length, and calibrated on one case
(0.02 right / 0.30 blank). Bundling fonts made it WORSE (wider glyphs wrap more), so the "Bundle the fonts" gate was a red herring
that cost a round; the Plan decision ADR-010 (no external fonts) was not the cause.

Is the override legitimate: yes, by design. The Test skill never waives (`SKILL.md` Step 3.7b, `test_screenshot_check_prose.py`);
the validator `_screenshot_check_issue` (`shipwright-run/scripts/lib/phase_validators_late.py`) blocks with severity `ask`; the run
skill (Step 5) allows completing over a gate rejection only via `single-session-apply --override-reason`, ASK FIRST, "only on the
person's explicit answer", logged in `shipwright_run_config.json` `validation_overrides` (present: step test, waived true, ADR-083).
The agent asked, the (simulated) person answered. The path worked; S08 rightly flags a harness auto-answering it.

Gap (documented, one doc fix): the reference told the agent the check ignores wording, hiding the real cause, so the agent chased
fonts first. Fixed by correcting the prose with the measured numbers and the allowed decisions (send the screen back to Design, or
override). NOT changed: tolerance, metric, fonts or the fixture. A tolerance change from one run (n=2 screens) would be guessing;
the open options for the operator are (a) make the `social-engagement-real` mockup sample text as long as the recorded threads,
(b) judge the metric on a second real-data run before touching 0.15. Both are fixture / calibration decisions.

## Acceptance criteria

1. The section-writer prompt and the batch task prompt require literal breakpoints, per-state content, declared extensions and
   recorded contradictions (tests: `plugins/shipwright-plan/tests/test_design_detail_prompts.py`).
2. The build gate (spec-reviewer, build SKILL, checklist) is unchanged: a declared line is no exemption.
3. The screenshot-check reference no longer claims wording-only blindness and records the run-14 numbers and the override path
   (test: `plugins/shipwright-test/tests/test_screenshot_check_prose.py`).

## Spec Impact

NONE (prompt/reference prose; FR-01.06 behaviour unchanged).
