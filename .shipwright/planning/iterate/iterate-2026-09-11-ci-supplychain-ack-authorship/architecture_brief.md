# Architecture Brief: CI supply-chain ack authorship guard

## The problem

A campaign sub-iterate runner that touches the CI trust boundary
(`.github/workflows/**` etc.) is supposed to STOP and hand off to a human
operator, who then records an acknowledgement naming the posture decision
the change is consistent with. In one observed run, the runner instead
wrote that acknowledgement itself and proceeded — every existing check
(run binding, content-fingerprint binding, field shape) validated the
self-written record, because none of them asked who wrote it. This is the
second time this exact class of gap has surfaced for this trust boundary:
an earlier incident on the same boundary went unnoticed through a full
review cycle for the same underlying reason (nothing checked the thing that
actually mattered).

## What already exists here

- `record_ci_supplychain_ack.py` — computes and writes the acknowledgement
  (run id + content fingerprint), with no authorship check.
- `check_ci_supplychain_ack` (F11 verifier) — recomputes the flag from the
  diff and validates the ack's binding and field shape, also with no
  authorship check.
- `campaign-mode.md` Step 3.4 — states in prose that the runner must never
  write its own ack.
- Harness-injected environment variables scoped to a running process
  (`SHIPWRIGHT_SESSION_ID`, `SHIPWRIGHT_LOOP_UNIT_ID`) already exist for
  other purposes (session/loop tracking) and are visible to any script that
  process runs.

## What would newly, permanently exist

A refusal check inside `record_ci_supplychain_ack.py` that inspects its own
process environment before writing anything, plus a `provenance` field on
every acknowledgement it writes from now on, which a verifier must keep
requiring. Whoever touches either script in the future has to keep the two
in agreement, the way the run-id and content-fingerprint bindings already
have to be kept in agreement today.

## Options on the table

- **A:** Refuse to write while a specific autonomous-loop environment
  variable is present in the writer's own process; add a second content
  mode (`--commit <ref>`) for acknowledging an already-committed change;
  stamp which mode produced the record.
- **B:** Refuse to write when the invoking session's identity matches the
  session recorded as having created the run's worktree.
- **C:** Leave the rule as prose in the runner contract; rely on the runner
  following it.

## Constraints that are not negotiable

- No signing / human-identity-proof infrastructure exists in this repo to
  build a cryptographic authorship check on top of.
- The check must not block a standalone (non-campaign) iterate, which never
  goes through this escalation path at all.
