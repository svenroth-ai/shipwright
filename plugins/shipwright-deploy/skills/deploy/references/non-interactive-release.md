# Non-interactive Release Path (`release.py`)

Steps 2-5 of the main skill are the interactive flow `/shipwright-deploy`
drives — PROD stays ASK-FIRST regardless of everything else (constitution),
and that flow is unchanged by what follows. `scripts/lib/release.py` is a
separate, coded entry point for a caller that has no agent in the loop to ask
a question or read a smoke-test JSON — a CI job, a campaign runner, or any
future automated release path:

```bash
uv run "{plugin_root}/scripts/lib/release.py" \
  --env-name "{env_name}" --repo-url "{repo_url}" --branch "{branch}" \
  --target dev --project-root "$(pwd)" [--confirm-failing-tests] \
  [--smoke-url "https://{env_name}.jpc.infomaniak.com" \
   --profile "{shared_root}/profiles/deploy/jelastic.json"]
```

It composes the same building blocks Steps 3-5 call individually, behind
structural guarantees FR-01.08 needs mechanised, not just documented:

- **Criterion 1 (AC02):** reads the identical test-gate oracle
  `validate-deploy.py` uses (`scripts/lib/test_gate.py`) *before* contacting
  the host — a failing/missing gate without `--confirm-failing-tests` never
  calls `jelastic_client.deploy_from_git` at all. Exit `2`.
- **PROD stays ASK-FIRST here too.** `--target` is required with no default
  (same "no silent default" pattern `rollback.py`'s own `--invocation` uses)
  — `--target prod` without `--confirm-prod` refuses before contacting the
  host, exit `2`, exactly like an unconfirmed test gate. A caller with no
  agent in the loop cannot show an `AskUserQuestion`, so it structurally
  cannot reach PROD unless something upstream (a human-gated CI approval
  step, a campaign operator) explicitly passed `--confirm-prod` — this
  module does not, and cannot, decide that on its own.
- **Criterion 5 (AC05):** when `--smoke-url` is given, a failed post-deploy
  smoke check automatically calls `rollback.rollback_git` back to the ref
  that was live immediately before this deploy, recorded with
  `invocation="auto"` in the same `rollback-history.jsonl` trail — but only
  when a polling deadline (`--profile` or `--smoke-max-wait`) was actually
  configured. A single 10s attempt (the default with no deadline) is not a
  reliable enough signal to trigger a host mutation on its own (`smoke_test.py`'s
  own docstring: "a fifteen-second start-up gets reported as a failed release
  and triggers a rollback nobody needed") — the failure is still reported,
  auto-rollback is just not attempted, with `rollback_skipped_reason` naming
  why. After a successful auto-rollback, `--smoke-url` is re-checked against
  the restored ref and surfaced as `rollback_verified_healthy` — a
  `ref_verified: confirmed` pin does not by itself mean the restored code is
  actually serving traffic. Omitting `--smoke-url` skips smoke verification
  and auto-rollback entirely — this is additive, never required. Exit `1` if
  smoke failed (rollback attempted or not); exit `0` once released.

This does not replace Steps 2-5's own `append_phase_history` / canon-event /
decision-log bookkeeping — a caller driving `release.py` directly still owns
recording those the same way an agent following Steps 3-5 does.

## Known limitations (doubt review, iterate-2026-09-16-deploy-ac02-ac05-coded-gates)

Recorded here rather than silently fixed — each needs a materially bigger
design than this unit's scope:

- **Auto-rollback restores a branch NAME, not a commit.** `previous_ref` is
  the VCS project's pinned branch, read before this deploy.
  `jelastic_client.deploy_from_git` (pre-existing, unmodified by this unit)
  never re-pins that branch for an environment that already has a VCS
  project — it only sends `branch` on first-ever creation. So for the
  routine "push new commits to the same branch, CI redeploys" cycle,
  `previous_ref` already equals the branch being deployed, and auto-rollback
  correctly — not silently — reports "nothing to roll back to": it has no
  distinct ref to name at commit granularity. Auto-rollback only has
  something to restore when the *branch name itself* changes between
  deploys (a first deploy of a feature branch, an explicit promotion).
  Restoring a specific prior *commit* on a same-branch redeploy would need a
  versioning/tagging scheme this module does not implement — until then,
  operators who need commit-level rollback on a same-branch pipeline should
  tag each release and redeploy via a distinct ref per release, the same way
  `rollback.py --target-ref` already expects a tag, not implicit branch
  history.
- **No lock across the whole gate→deploy→smoke→rollback sequence.**
  Concurrent `release.py` invocations against the same `env_name` are not
  serialized against each other (matching `rollback.py`'s own pre-existing
  assumption — it has no such lock either). Callers are expected to
  serialize releases per environment upstream (CI/campaign convention), not
  to invoke this concurrently for one target.
