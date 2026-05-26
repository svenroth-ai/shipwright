# Path C: BUG (fix something broken)

## Step 1: Iterate Spec (medium+ only)

Same as `references/path-a-feature.md` Step 1.

## Step 2: Spec Update — classify the Spec Impact (BUG)

A bug fix usually restores intended behavior, so the spec impact is
typically NONE. Classify it anyway:

- **MODIFY** — the spec itself was wrong: correct the FR row / ACs.
- **REMOVE** — the spec described behavior the fix removed: move the FR
  into `### Removed Requirements` with `status: deprecated`.
- **NONE** (default) — the fix restores behavior the spec already
  describes correctly. No FR change.

BUG iterates are NOT gated by the F11 spec-impact verifier — a bug fix
need not touch the spec. Record the classification in the iterate ADR;
ADD does not apply to bug fixes.

## Step 3: Investigate & Reproduce

**Do NOT attempt fixes before completing investigation.**

1. **Reproduce** — trigger the bug reliably. Note exact steps, inputs,
   and environment.
2. **Localize** — identify which layer fails:
   - UI (render/interaction) → check browser console, DOM state
   - API (request/response) → check network calls, status codes, payloads
   - Data (DB/state) → check queries, migrations, state shape
   - External (third-party) → check service status, API changes
   - [If UI layer] Compare current state against
     `.shipwright/designs/screens/{relevant}.html` to determine intended
     behavior before fixing
3. **Root Cause** — trace from symptom to cause. Ask "why?" at each level.
   Do NOT fix the first thing that looks wrong — that's symptom-patching.
4. **Write a failing test** that proves the root cause (not just the
   symptom):
   - The test must fail for the *identified root cause*, not a side effect
   - If you can't write a targeted test, your root-cause analysis is
     incomplete — go back to step 3
5. Run the test to confirm it fails:
   ```bash
   npx vitest run --reporter=verbose {test_file}
   ```

**Circuit breaker:** If 3 fix attempts fail after implementing Step 5,
STOP. Re-evaluate: Is the root cause actually understood? Is the
architecture itself the problem? If yes → escalate (see
`references/mid-flight-escalation.md`).

## Step 4: Mini-Plan (medium+ only)

See `references/iteration-planning.md`.

## Step 5: Fix

1. The worktree and branch `iterate/<slug>` already exist — created
   unconditionally in B1a (for a bug the slug carries a `fix-` prefix).
   Do NOT run `git checkout -b`. Fix in `{project_root}` (the worktree).
2. **Fix the root cause** — targeted change, minimal scope. Do not fix
   symptoms.
3. Run reproducing test to verify it passes.
4. Run related tests to verify no regressions.
5. **Boundary Probe (when `touches_io_boundary` is set)** — same Path A
   Step 6a sub-step applies. When the bug touches a serialized format,
   the fix is incomplete without a producer→file→consumer round-trip
   test that fails before the fix and passes after.
6. **Confidence Calibration (Step 7.5 in Path A)** applies identically
   to BUG fixes — mandatory at medium+, also at small with
   `touches_io_boundary`. Populate the spec's Confidence Calibration
   section before F0.

## Step 6-14: Same as FEATURE

Follow the Phase Matrix to determine which steps run for the assessed
complexity.
