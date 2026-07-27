# Mini-Plan: iterate-2026-07-27-rollback-uses-target-ref

## Chosen approach — evidence, not assertion: every claim the rollback makes has to be earned

The four items share one shape: the code states an outcome it never established.
The fix is the same everywhere — carry the fact, check the fact, report only the
fact — so all four land in one diff against one file family.

**1. `shared/scripts/deploy_profile.py` (new, ~90 LOC) — one reader for the target's policy**

The three shipped profiles already declare `smoke_test.poll_interval_seconds`
and `smoke_test.max_wait_seconds`, and `rollback.data_rollback_strategy`. Nothing
reads them. This module is the single reader: `load_profile(path)`,
`smoke_policy(profile) -> SmokePolicy`, `data_rollback_strategy(profile)`.

Top-level in `shared/scripts/` with a unique name, imported **bare**
(`from deploy_profile import …`) — the ADR-044/045 house rule, because both a
shared module (`smoke_test.py`) and a plugin-local module (`rollback.py`) import
it and a `lib.` import would bind `sys.modules['lib']` for whichever caller runs
first. Two readers of one JSON is exactly the divergence the 2026-07-23 learning
warns about, so there is one function per question and no second parse anywhere.

**2. `shared/scripts/smoke_test.py` (~119 → ~200 LOC) — ask until it answers or the deadline passes**

`run_smoke_test` gains `poll_interval` + `max_wait` and loops on
`time.monotonic()`. The result grows `attempts`, `waited_ms`, `deadline_seconds`,
`deadline_source` — so "failed release" becomes an auditable verdict rather than
a bare boolean. `--profile` supplies the deadline; explicit flags win over it.

**Backward compatibility is the load-bearing default.** `max_wait=None` means
*one attempt*, exactly today's behaviour. `/shipwright-test` passes only
`--timeout 10`, and `plugins/shipwright-test/tests/test_smoke_test.py` drives
unreachable URLs — a polling default would turn those into 60-second tests. The
deadline is opt-in and comes from the target, which is what "the deadline belongs
to the target" means.

**3. `plugins/shipwright-deploy/scripts/lib/jelastic_client.py` (+~55 LOC) — the ref needs somewhere to live**

`get_vcs_project(env, context)` → `environment/vcs/rest/getprojects`, returning
the project object for that context (the endpoint returns a *list*; match on
context, do not assume one object). `set_vcs_ref(env, project, ref)` →
`environment/vcs/rest/editproject` with the **full project object**, `branch`
replaced.

Read-merge-write, not a sparse write: the external review flagged that
`editproject` may be PUT-shaped, in which case sending only
`{envName, context, branch}` would wipe the repository URL and credentials —
turning a rollback into an outage. So an unreadable current config **refuses**
rather than writing. Both endpoints are documented-not-live-verified (no
`JELASTIC_TOKEN` here) — recorded in the profile's `known_gaps` and in
`rollback-strategy.md`, not glossed over.

**4. `plugins/shipwright-deploy/scripts/lib/data_drift.py` (new, ~75 LOC) — did the data move on?**

Two git calls, both with argument arrays and `--` separators, never a shell:
`git diff --diff-filter=A --name-only <ref> -- <dir>` for tracked additions
since the target ref, and `git ls-files --others --exclude-standard -- <dir>`
for untracked ones (a migration file nobody committed yet is still a schema that
moved on). A ref git cannot resolve is `unknown`, and `unknown` refuses exactly
like `drifted`: being unable to answer "has the data moved on?" is not
permission to proceed.

The review argued this is over-production for one git call. Fair on the logic —
it is now two calls and ~75 lines — but the module stays, because `rollback.py`
lands at ~250 LOC against a hard 300-line bloat gate; inlining would breach it.

**5. `plugins/shipwright-deploy/scripts/lib/rollback.py` (~119 → ~250 LOC) — the orchestration, rewritten around evidence**

Order is the design:

1. **Validate the ref form**, then the **data-drift gate** — both before any
   hosting call, so a refusal leaves the target untouched. `--ack-data-drift` is
   the explicit override.
2. **Read the current project config**, remember `previous_ref`, **pin** the new
   ref, then **update**. The update is only issued if the pin returned
   `result == 0`; a failed pin means the update never runs, so the old
   "silently redeploy HEAD" path is structurally gone.
3. **Read back.** `confirmed` / `unconfirmed` / `mismatch`, with
   `verification_error` naming why when unconfirmed. `mismatch` is a failure.
   `unconfirmed` keeps `success: true` — the pin *was* accepted — but the
   message says so in those words rather than claiming a confirmation the target
   never gave. Only `JelasticError` / `URLError` downgrade; a parse bug must not
   masquerade as an unavailable endpoint.
4. **On failure, name the state at the right altitude.** Two classes, because
   conflating them is its own dishonesty:
   - *refused before any hosting call* → `mutated: false`, `halt: false`,
     exit `1`, "the target was not touched" — no claim about what is running;
   - *started and unfinished* → `mutated: true`, `halt: true`, exit `3`, plus
     `state`, `last_attempted`, `what_it_found`, `previous_ref`, and a plain-
     English paragraph saying this rollback did not verify which version is
     running and that the operator should stop here.

`rollback_clone` gains `restored: false`: it stops the broken environment, it
does not restore anything, and the payload should say which.

**6. Tests — the assertion the old file never made**

`test_rollback.py` currently asserts only that `--target-ref` is *required*.
It gains the assertion that it is *used*: a stubbed client records every
outbound call, and the test fails unless `editproject` carries the ref and
precedes `update`. `test_data_drift.py` drives real temporary git repos.
`test_smoke_test.py` gains polling + deadline-boundary coverage against a real
local HTTP server that starts answering late.

`test_rollback_e2e_cli.py` is the F0.5 runner and deliberately uses **no
mocking**: it starts a local stub that speaks the Jelastic REST shape, points
`JELASTIC_API_URL` at it, and runs `rollback.py` as a subprocess from an
unrelated working directory. Real CLI, real HTTP, real client code, real git
repo — and the stub records exactly which endpoints were called with which
parameters, which is the only way to prove across a process boundary that the
ref was sent. It also proves the bare `deploy_profile` import resolves from a
normal invocation, which an in-process unit test cannot.

## Alternative considered — refuse to roll back at all, and tell the operator to do it by hand

`rollback_git` returns `success: false` with the manual `vcs/editproject` +
`vcs/update` procedure, and the plugin stops pretending it can revert a Jelastic
DEV environment. It has one real merit: it needs no unverified endpoint, so
nothing in the diff rests on an API shape we could not test against a live
target.

**Rejected.** FR-01.08 promises "the previously working version is put back
without a person having to intervene — the way back is part of releasing, not a
separate procedure somebody has to know about". Trading a false success for a
guaranteed manual step retires the capability instead of fixing it, and the
worst moment to hand an operator a manual procedure is the middle of a bad
release. The unverified-endpoint risk it avoids is already contained: `_call`
raises on `result != 0`, so a wrong endpoint reports failure rather than
succeeding falsely — the same fail-closed direction the alternative buys, minus
the retreat.

## Risk

- **Endpoint shape unverified against a live target.** Contained as above,
  disclosed in `known_gaps`; the first real rollback either works or reports a
  precise API error, and neither outcome is a silent false success.
- **A polling default would slow every existing caller.** Contained by
  `max_wait=None` ⇒ one attempt; pinned by AC8 and by the untouched
  `/shipwright-test` call site.
- **`SKILL.md` is bloat-grandfathered at 451 lines (limit 400).** Any growth
  ratchets and blocks the commit — the new prose goes into
  `references/rollback-strategy.md` (43 lines, ample headroom) and the SKILL
  edits must come out net-zero or smaller.
