# Fail fast on a non-canonical campaign sub-iterate run_id

**Run-ID:** `iterate-2026-08-25-campaign-run-id-lowercase-mint`

## Context

A prior campaign sub-iterate run (`R0`, campaign `req3-04-ac-identity-mono`)
minted its run_id as `iterate-2026-08-25-R0-spec-reader-shipped-shape` —
embedding the campaign's uppercase display id (`R0`) literally into the
run_id. This passed every check until F5c's `append_iterate_entry.py`, which
enforces `RUN_ID_STRICT = r"^iterate-\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*$"`
(lowercase-only) with no escape hatch for a new entry — discovered only
after F3 (decision drop), F4 (changelog drop), the risk-recheck record, and
the F5 test-completeness ledger had already been produced under the doomed
run_id. That run was rescued by manually renaming the run_id lowercase
end-to-end. Its own ADR's Reflection section
(`.shipwright/planning/adr/iterate-2026-08-25-r0-spec-reader-shipped-shape-fr-criteria-convergence.md`,
"Reflection — Run-ID casing") recorded that whoever mints campaign
sub-iterate run_ids should pre-lowercase the embedded id, and explicitly
decided the fix belongs at the *minting* side, not by weakening
`RUN_ID_STRICT` (judged correct policy).

## Decision

Fix at the minting side, per that Reflection's own recommendation, with a
code-level backstop so a documentation slip does not cost hours again:

1. `campaign-mode.md`'s autonomous-loop step 3b now explicitly instructs the
   orchestrator to mint `run_id` with the sub-iterate's display id
   LOWERCASED when embedded (`...-r0-...`, never `...-R0-...`), keeping the
   uppercase form only in `branch_name`, the PR title, and the `sub_iterate_id`
   metadata field.
2. `sub-iterate-runner.md`'s Input section and Step 3.4 state the same
   constraint from the runner's side.
3. `plugins/shipwright-iterate/scripts/lib/diff_risk_recheck.py` — Step 3.4,
   the FIRST script call in the runner contract that receives `run_id` —
   now copies `RUN_ID_STRICT` locally (same "plugin-lib never imports
   shared/ at runtime" pattern already established by
   `session_plan.RUN_ID_STRICT`) and rejects a malformed run_id immediately
   (exit 2, actionable error message), instead of only discovering it at
   F5c hours later, after Build/F3/F4/F5/F5b have already run on it.

`RUN_ID_STRICT` itself is unweakened, consistent with the prior ADR's
finding that the regex is correct policy.

## Consequences

A malformed campaign sub-iterate run_id is now rejected at Step 3.4 —
immediately after Build, before any of F3/F4/F5/F5b produce artifacts keyed
by the doomed run_id — with an error message that names the exact fix. Three
`RUN_ID_STRICT` copies now exist (`shared/scripts/lib/iterate_entry.py`,
`plugins/shipwright-iterate/scripts/lib/session_plan.py`,
`plugins/shipwright-iterate/scripts/lib/diff_risk_recheck.py`), each
pinned by a cross-module test
(`test_run_id_strict_pinned_to_shared_iterate_entry`) so none can drift
alone. Two doc files (`sub-iterate-runner.md`, `campaign-mode.md`) were
trimmed to stay within their pinned/hard LOC ceilings (497 and 400
respectively) while adding this instruction — no baseline was bumped.

## Rationale

`diff_risk_recheck.py`'s Step 3.4 is genuinely the earliest point in the
runner contract that receives `run_id` as a script argument: Step 2
(`classify_complexity.py`) never receives it, and Step 1 (branch setup) is
pure orchestrator prose with no script call to hang a check on. The
orchestrator's own minting happens even earlier (step 3b, before spawning
the runner), but that is prose constructing a string, not a script
invocation — so the documentation fix (1-2 above) is the only lever
available there, and the code-level fail-fast (3) is the earliest *code*
boundary, not the earliest conceptual point.

## Rejected alternatives

Weakening `RUN_ID_STRICT` to tolerate uppercase — rejected by the prior
ADR as the wrong fix (the regex is correct policy; the uppercase run_id was
the defect), and re-litigating that decision here would have been exactly
the kind of case-error the prior ADR's own Post-Review Remediation section
warns against. Adding a brand-new, dedicated validation script that runs
before Step 1 — rejected: no script boundary exists that early (Step 1 is
prose), so a new script would only exist to hold this one check, and Step
3.4 already exists and is reached minutes into Build, long before F5c.

## Self-Review (Step 7)

1. **Spec Compliance** — pass, per the task's five acceptance criteria (root
   cause at minting side / earliest fail-fast / documented instruction /
   no regressions / LOC budget) and the two-round Stage-1/Stage-2 review
   cascade (both PASS, see `reviews.json`).
2. **Error Handling** — pass. The new early-exit reuses the existing
   JSON-error-then-exit-2 shape used two lines later for the
   `RuntimeError`/`ValueError`/`OSError` branch; no new failure mode.
3. **Security Basics** — pass. No new external input channel, no secrets,
   no dynamic import; pure regex match against an already-trusted CLI
   argument.
4. **Test Quality** — pass. New rejection test is parametrized with the
   literal real incident id, plus mixed-case/unshaped/short-date variants;
   a new acceptance test proves the lowercased fix passes; a cross-module
   pinning test guards all three `RUN_ID_STRICT` copies.
5. **Performance Basics** — pass. One regex match added before existing
   work; no new I/O.
6. **Naming & Structure** — pass. Matches the existing
   `session_plan.RUN_ID_STRICT` "copied local + pinning test" precedent
   exactly.
7. **Affected Boundaries (ADR-024)** — pass. Boundary: the run_id token
   shape. Producer = whoever mints it (orchestrator prose). Consumer =
   F5c's `append_iterate_entry.py` (pre-existing) and now
   `diff_risk_recheck.py` (new, earlier). Round-trip probe: exercised the
   real CLI `main()` end-to-end with the literal incident run_id (rejected,
   exit 2) and its lowercased fix (accepted, exit 0, artifact written).

## Confidence Calibration

Boundary touched: the run_id token format, consumed by two independent
scripts (`diff_risk_recheck.py`, `append_iterate_entry.py`) and produced by
orchestrator prose. Empirical probes run: (1) invoked the real
`diff_risk_recheck.main()` CLI with the literal incident string
`iterate-2026-08-25-R0-spec-reader-shipped-shape` — rejected, exit 2,
actionable message; (2) invoked it with the lowercased fix — accepted, exit
0, `risk_recheck.json` written; (3) ran the full plugin suite (948 passed)
and `integration-tests/` (all green) to confirm no regression; (4) ran the
full F0 canonical suite runner (18 units GREEN, diff-coverage 100% on the
changed lines) and F0.5 (cli surface, 27 tests run). Test Completeness
Ledger: see `shipwright_test_results.json` (F5). Confidence-pattern check:
asymptote reached after the two-round review cascade found nothing further
to fix; coverage breadth spans the CLI entrypoint (not just the bare
regex), the doc instructions, and both the failing and fixed shapes.
