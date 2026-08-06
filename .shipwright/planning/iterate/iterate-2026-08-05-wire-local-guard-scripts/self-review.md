# Self-Review — iterate-2026-08-05-wire-local-guard-scripts

Step 7, 7-point checklist. Written before the Step 8 cascade.

1. **Spec compliance.** AC-1…AC-6 implemented. AC-2's guard was moved *into* the
   executable snippet after the external plan review; AC-6 drives the shipped
   `hooks.json` chain rather than a hand-assembled one, so it cannot certify a
   composition nobody ships.

2. **Tests.** 19 new across three files. Track 1 was confirmed red before
   implementing (4 failed / 1 vacuous pass, and the vacuous one was then given a
   non-vacuity assert). Track 2's module did not exist, so collection failure was
   its red. Both F0 spellings were probed empirically in both directions
   (file present → gates run and pass; file absent → no-op).

3. **Error paths covered.** Producer timeout; producer unstartable; undocumented
   exit code; non-Shipwright tree; producer file missing from a partial cache.
   `KeyboardInterrupt` is deliberately *not* swallowed, with a test pinning it.

4. **No scope creep.** Nothing promoted to must-pass (the Non-Goal where the
   landmine actually lives); no pre-push hook; the live `Prepare review request`
   divergence is left for the producer to file and the operator to decide.

5. **Docs.** Hooks registry updated (mandatory when a hook changes). `guide.md`
   was first checked and found not to describe F0 — then updated anyway once the
   spec-reviewer showed §2.10 step 5 framed the producer as manual-only.

6. **Reversibility.** Each track reverts independently; neither checker's own
   behaviour changed, so reverting the wiring restores today's state exactly.

7. **Affected boundaries.** `hooks.json` (io boundary + cross-component), a new
   `shared/scripts/hooks/*.py`, two shipped runtime prompts (`SKILL.md`,
   `F0.md`), three docs, one docstring.

## What I got wrong, and what caught it

- **AC-5 was under-delivered and its own guard shared the blind spot.** The stale
  "nothing invokes it for you" claim lived in *three* files; I corrected two and
  wrote the honesty test over the same two. The spec-reviewer found the third
  (`docs/hooks-and-pipeline.md`) — the very file AC-5 enumerates. Fixed, and the
  test now covers all three. A repo-wide sweep confirmed there is no fourth.
- **The first F0 snippet was bash-only**, on a repo developed on Windows where
  `if [ -f ... ]` is a syntax error — a step that silently would not run on the
  primary platform, which is the exact failure the card is about. Caught by
  asking "would this actually execute here?" rather than by a test.
- **The PowerShell branch initially ended on `Pop-Location`**, so it could not
  carry a non-zero exit and the two spellings disagreed about whether the step
  can STOP the run. Raised by the spec-reviewer as a note for Stage 2; fixed
  immediately rather than deferred.

## Known limits, stated rather than hidden

- The F0 step is documented prose plus a command, like F0's leak-guard. Nothing
  *proves* it ran. The in-code alternative is bloat-blocked: `run_test_suite.py`
  measures 518 against a baseline `current` of 518, so any addition ratchets an
  allowlisted entry and the pre-commit hook rejects the commit.
- A push made outside an iterate never reaches F0. Stated in both the docstring
  and the hooks doc rather than papered over.
- The producer costs ~1.5 s and three `gh` API calls per session, in consumer
  projects too. Accepted: it is portable, and `import_github_findings.py` already
  makes network calls in this exact chain.
