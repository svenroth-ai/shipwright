# Mini-Plan — `iterate-2026-07-28-ci-ack-per-run-home`

## Chosen approach: per-run ack file

`.shipwright/planning/iterate/<run_id>/ci_supplychain_ack.json` — the directory
`reviews.json` already owns.

1. **`shared/scripts/tools/verifiers/ci_supplychain.py`**
   - Add `ack_path(project_root, run_id)` → the per-run relpath (single source
     of truth for writer and reader).
   - Rework `_read_ack` into a two-source read:
     1. committed per-run file (`git show <commit>:<relpath>`),
     2. worktree per-run file (only when untracked at that commit),
     3. legacy `iterate_latest.ci_supplychain_ack` (committed, then disk).
     First source that yields an ack wins; a *corrupt* source is an error, not a
     silent fall-through to the next.
2. **`shared/scripts/tools/record_ci_supplychain_ack.py`**
   - Write the per-run file instead of mutating `shipwright_test_results.json`.
   - Keeps `build_ack` untouched, so the run/content binding is unchanged.
3. **Tests** — new cases in `shared/tests/test_check_ci_supplychain_ack.py` and
   `test_record_ci_supplychain_ack.py`, plus an integration test that runs
   *both* gates over one real workflow-touching commit.
4. **Docs** — `docs/hooks-and-pipeline.md`, `.shipwright/agent_docs/conventions.md`,
   iterate `SKILL.md` taxonomy row, `references/F5.md` + `references/F6.md`.

### Why the reader keeps a legacy leg

39 iterate branches are in flight. Several already recorded an ack the old way.
Dropping the legacy read would red-line them at F11 for a reason they cannot
act on without a rebase. The leg is safe because the legacy ack passes through
*identical* run-id, fingerprint and field validation — it is a different
location, not a weaker rule.

### Why a corrupt source must not fall through

If a malformed per-run ack silently fell through to the legacy location, an
author could park a valid old-style ack and then write garbage to the new one.
Corrupt = error, matching the existing `_read_ack` posture on an unreadable
results file.

## Alternative considered: working-tree fallback on run-id mismatch

Change `_read_ack` so a committed ack naming a *different* run falls back to the
working copy.

- **Cheaper** — one condition, no new file, no F6 staging change.
- **Rejected** because it produces no durable record. The ack would exist only
  on the author's disk: never in the PR, never reviewable, and erased by
  `restore_derived_to_head` before F11 even reads it. The gate's docstring
  already rules this out explicitly. It also does not survive the parked
  derived-snapshots refresh, which removes the committed copy entirely — the
  ack would become unreachable, which is the failure this iterate exists to
  prevent.

## External plan review — both verdicts `revise`, dispositions

GPT and Gemini (openrouter). Every finding is answered below; the four accepted
ones changed the plan before any code was written.

**ACCEPTED**

1. *(both, high) F6 must actually stage the new file — updating `F6.md` alone is
   not enough.* **Verified rather than assumed:** F6's add-list already contains
   `git add .shipwright/planning/iterate/<run_id>/` — a **directory-level** add
   carrying `reviews.json` today. The new file lands in that same directory and
   is therefore staged by the existing rule, with no F6 code change needed. F6 is
   agent-executed prose (`finalize_bundle.py` covers F1/F3/F4/F5c/F5b, not F6), so
   the honest pin is a drift test asserting `F6.md` keeps the directory-level add
   and names the ack — recorded as such in the ledger, not overclaimed as an
   execution test.
2. *(GPT, medium) `git show` failure ≠ file absent.* Correct, and the first draft
   conflated them: any non-zero rc would have routed to the working tree, turning
   an infrastructure error into a trust path. Now `git ls-tree` decides
   **presence** (rc≠0 → verifier error, empty output → genuinely absent) and only a
   genuinely-absent path may fall back.
3. *(GPT, medium) present-but-invalid must be terminal, not fall through.* The
   sharpest finding. A stale-run or wrong-fingerprint per-run ack must **fail**,
   never quietly hand off to a valid legacy ack — otherwise the new home is
   bypassable. Resolution is now: the first source that is *present* is
   authoritative and validation applies to it alone; only genuine absence
   advances to the next source.
4. *(GPT, medium) `run_id` becomes a path component → traversal.* Accepted;
   reusing the canonical `is_safe_run_id` from `lib.review_record_schema`, which
   exists for this exact hazard on this exact directory. Unsafe run id → fail
   closed, after the "no CI file touched" early exit so it cannot fire spuriously.
5. *(GPT, low) mkdir + atomic write.* Accepted — `mkdir(parents=True)` plus
   tmp-file + `os.replace`, so an interrupted write cannot leave a half-file that
   fails the gate for an unrelated reason.

**REJECTED**

6. *(Gemini, high) per-run directories cause "infinite repository bloat"; use a
   static path instead.* Rejected — this would reintroduce the exact defect the
   derived-snapshots work removed. A static path is rewritten by **every**
   iterate, so N parallel PRs collide N(N-1)/2 times; that is why
   `derived_snapshots.py` explicitly excludes "every per-run / per-campaign path"
   from the snapshot set and keeps them shipping. Gemini's premise — "parallel
   iterates exist on separate branches, so a static path is fully isolated" — is
   true on the branch and false at **merge**, which is where the collisions
   actually happen. On volume: `reviews.json` already writes one per-run file for
   *every* iterate; this one is written only by the far rarer CI-touching subset,
   so it is strictly less traffic than an accepted existing pattern.

**NOTED, no change**

7. *(Gemini, medium) `subprocess` with `check=True` would raise on a missing
   path.* Not applicable — `_run_git` never raises; it returns `(rc, out, err)`
   and maps every exception to `(1, "", "")`. Verified by reading the helper.
8. *(Gemini, low) is the legacy ack a standalone file or a JSON key?* A key —
   `iterate_latest.ci_supplychain_ack` inside `shipwright_test_results.json`.
   Spec wording tightened.

## Landing

One commit, `iterate/ci-ack-per-run-home`, PR against `main`.
This iterate touches **no** `.github/workflows/**` file, so it does not itself
trip `touches_ci_supplychain` — the fix is proven by tests, not by self-application.
