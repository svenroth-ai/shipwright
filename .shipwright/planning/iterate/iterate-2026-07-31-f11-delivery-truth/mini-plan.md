# Mini-plan — iterate-2026-07-31-f11-delivery-truth

## Chosen shape

**Separate observing from acting, and keep the pure decisions out of both.**

| # | File | Change | Why here |
|---|---|---|---|
| 1a | `shared/scripts/lib/pr_readiness.py` | **new, pure** — the **promoted** `failing_checks`/`pending_checks`, and `readiness` → `failed` / `blocked` / `pending` / `refresh_needed` / `green` + checks-observed count | *What state is the PR in?* `failing_checks` MOVES here rather than being re-implemented — #503's lesson: one helper its callers share beats a second view of one payload. |
| 1b | `shared/scripts/lib/pr_delivery.py` | **new, pure** — `classify_arm_outcome` (definitive facts only), `identity_problem`, `self_merge_allowed(env)` (fails closed on an unparseable value), the exit-code contract | *What may we DO about that state?* No `gh`, no clock, no subprocess ⇒ every branch is unit-testable. Split from 1a when the combined file crossed 300 lines. |
| 1c | `shared/scripts/lib/pr_self_merge.py` | **new** — the wait → refresh → re-verify → pinned-merge → confirm cycle | The most intricate part, independently testable. Split out when `deliver_pr.py` crossed 300 lines under Stage-1 fixes. |
| 2 | `shared/scripts/tools/watch_pr_delivery.py` | **edit, additive** — imports `failing_checks` from (1), and `classify_delivery(pr, *, ready_is_terminal=False)` gains the `ready` verdict; `_GH_FIELDS` gains `headRefOid`/`headRefName` for the pin | Default `False` keeps every current caller byte-identical — asserted over a payload matrix, not argued from the default. |
| 3 | `shared/scripts/tools/deliver_pr.py` | **new** — the ladder driver: **validate identity FIRST** (the arm is itself mutating) → arm → classify → (armed/blocked: watch as today) / (unavailable: hand to 1c) | A watcher that can merge is no longer safe to run for diagnosis (`--once` exists so a human can ask "why is this stuck?"), and `watch_pr_delivery.py` is 247 lines — absorbing the ladder would cross the 300-line limit and fuse two responsibilities. |
| 4 | `shared/scripts/tools/verifiers/handoff_freshness.py` | **edit** — compare through the same normalizer that renders | Defect B. Makes the self-refuting sentence impossible by construction. |
| 5 | `plugins/shipwright-iterate/skills/iterate/references/F11.md` | **edit** — the arm + Delivery Watch prose becomes the ladder; new exit code documented | The prose IS the runtime contract for this phase. |
| 6 | `docs/guide.md` | **edit** — the delivery guarantee and the opt-out switch | User-facing behaviour change; Ch. 8 / Appendix B are the sections that go stale. |
| 7 | `shared/tests/` | `test_pr_delivery.py` (new), `test_deliver_pr.py` (new), `test_watch_pr_delivery.py` (+`ready`), `test_handoff_freshness.py` (+3), one integration test for the composition | `cross_component`-shaped even if the flag does not fire: delivery now composes with the churn resolver and the verifier. |

**Order.** Defect B first (item 4 + tests) — small, unarguable, and it lands even
if anything about A needs re-deciding. Then 1 → 2 → 3 → 5/6, TDD throughout.

**The switch.** `SHIPWRIGHT_ITERATE_SELF_MERGE` — unset or `1` ⇒ the ladder may
merge; `0` ⇒ never merge, report not-delivered immediately. It sits beside the
existing `SHIPWRIGHT_ITERATE_AUTOMERGE=0` (campaign defer), which keeps its
meaning: a campaign still defers to its orchestrator and never self-merges.

**New exit code.** `6` = *not delivered, and no merger can exist* (arming
structurally impossible, self-merge forbidden). Distinct from `4` (pending
timeout) precisely because re-running the watch is futile, where on `4` it is the
remedy.

## Alternatives considered and rejected

**Predict the capability up front instead of attempt-then-classify.** Read
`allow_auto_merge` and the base rules *first*, and only arm when both say yes.
Rejected: the rules endpoint reports **rulesets**, and a repo on classic branch
protection can answer `[]` while arming works perfectly. Prediction would silently
demote such repos to the self-merge path — losing GitHub-native auto-merge for a
whole class of repositories to save one API call. Attempting is definitive; the two
facts are then used only to explain a failure that already happened.

**Put the ladder inside `watch_pr_delivery.py`.** Fewer files, one entry point.
Rejected on both grounds above: it crosses the size limit, and it makes the
diagnostic tool a mutating one — `--once` exists so a human can ask "why is this
PR stuck?", and that must never risk merging anything.

**Make the arm hard-fail instead (STOP when arming is refused).** Rejected: it
converts a silent non-delivery into a loud non-delivery without delivering
anything, and it would break case C harder than today. The fail-soft arm was a
deliberate choice — a missing repo setting must not break F11 for every future
iterate.

**Wait for green, then tell the operator to merge.** Rejected by the decision in
§2 of the spec: it leaves case C permanently manual, which is the persona the card
identifies as worst-served.

## Risks

| Risk | Handling |
|---|---|
| Self-merge on a repo with **zero** host checks rests on the local suite alone | Never hidden: the count of checks observed is reported, and F12 names who merged. Opt-out available. |
| Merging a stale branch (the Group-E hazard `ensure_current` exists for) | Refresh immediately before merging, then re-verify; merge only from a current, verified tree. |
| A refresh during the wait merges a commit the verifier never saw | The invariant is restored explicitly: re-run `verify_iterate_finalization.py` on the new HEAD, refuse on red. |
| GitHub error wording changes | Wording is corroborating evidence only; the discriminator is two readable facts, and an unreadable picture stays on today's conservative path. |
| Collision with IT-7a in `lib/pr_blockers.py` | That file is read, never edited. |
