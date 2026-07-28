# Handover — 2026-07-28

Two independent pieces of work, in this order. Each section below is a **paste-ready
prompt**; neither needs the originating session's transcript.

Written after a session that started on the derived-snapshots refresh, discovered the
operator's real blocker was elsewhere, and parked. Read "Shared context" first — both
prompts depend on it.

---

## Shared context (applies to both)

### Commits are currently blocked in this repo

A `PreToolUse` hook on Bash — `check_security_scan` (shipwright-compliance) — blocks
every `git commit` while the RTM's `| Unresolved findings | N |` exceeds
`enforcement.allowed_critical_findings` in `shipwright_compliance_config.json`. That key
is **unset**, so the threshold is 0, and the RTM reports **24**.

What those 24 are, established by measurement:

- `unresolved = sum(we.review_findings - we.review_fixed for we in data.work_events)`
  (`rtm_generator.py:621`), i.e. a sum over `work_completed` events in
  `shipwright_events.jsonl`.
- Only **4 of 389** events carry the nested `review: {findings, fixed}` block. Two are
  clean (12/12, 18/18). Two are not: `evt-b9b5ddf2` (16/4) and `evt-bb598e0d` (20/8) —
  both 2026-06-08, both from the triage-outbox-delivery campaign. 16−4 + 20−8 = 24.
- Their evidence was deleted (campaign dir absent everywhere, cited ADR-141 never minted,
  both event commit SHAs pre-squash and not ancestors of main), **but the remediation is
  demonstrably on main** — `b8fcf8ae` "harden D2 sweep/GC" carries the matching `Run-ID`
  and enumerates its fixes A–F. Detail:
  `.shipwright/planning/iterate/2026-07-28-triage-delivery-audit-FINDINGS.md`.
- **Root cause is structural:** `review.fixed` is written at F5b, *before* the remediation
  commit exists, on an append-only log that cannot be corrected. The metric under-reports
  by construction for any run that takes its reviews seriously.

**The operator declined both an override and a threshold change, and will make commits
personally** by typing `! git commit …` in the session — the hook gates the agent's tool
use, not the operator's keyboard. So: **prepare the commit, stage it, hand the operator
the exact command.** Do not override the hook. Do not edit the threshold.

Open cards covering the surrounding state: `trg-7b6f13df` (the 29 audited findings, with
3 verified high), `trg-17f53a39` (the hook is named for security but counts review
findings, and its threshold blocks everything), `trg-2f89afcf` (adopt inherits #480
without a refresh producer — the operator's third step, already tracked, nothing to file).

### Git identity

Commit as `svroch <218151234+svroch@users.noreply.github.com>`.

### The admin bypass is CONFIRMED for the operator — still unproven for the token

Pushing this handover produced GitHub's own confirmation:

```
remote: Bypassed rule violations for refs/heads/main:
remote: - Changes must be made through a pull request.
remote: - 6 of 6 required status checks are expected.
```

This closes a question the parked refresh could not answer from inside the repo. Earlier
attempts: `GET /rules/branches/main` returned all five rules for the calling actor and is
**not** evidence either way; the design therefore reasoned from `origin/main`'s history
(direct `chore(triage)` and `docs(…)` commits, and merge commits that also cleared
`required_linear_history`). That inference is now directly corroborated.

**Do not over-read it.** It proves the bypass for the human identity `svroch`. It does
**not** prove it for `SHIPWRIGHT_REFRESH_TOKEN`: a fine-grained PAT can be narrower than
its owner, and the refresh's whole delivery path depends on the token bypassing. The
adversarial review raised exactly this (rework item M5: a permanent `protected branch hook
declined` is indistinguishable from a transient race, and files nothing). **Verify the
token's bypass before the refresh ships** — a single throwaway push with that credential
answers it, and it is far cheaper than discovering it from a workflow that goes red on
every push to main with nothing recorded.

### `main` moves fast — re-base before assuming anything

Ten PRs merged during the session that produced this handover (#472, #479, #482–#489),
leaving the parked refresh branch **11 commits behind** its base `e21a7b71`. This is the
`BEHIND` problem the merge queue exists to fix, demonstrated on itself.

Four of those commits land in areas the refresh rework must touch — read them before
reworking, because they may already have solved, moved, or invalidated part of the list:

| Commit | Why it matters here |
|---|---|
| `bcc7a590` (#489) | *"'cannot run' must not mean 'was never asked'"* — the same class as rework item H2 (a failed generator reporting success). May already supply the pattern, or the vocabulary, to reuse. |
| `ee07a3b5` (#485) | *"a grade snapshot names the tree it was measured in"* — touches the `grade_snapshot` event the refresh deliberately restores between convergence passes. The restore's rationale is written against the old behaviour; re-check it. |
| `00ff3949` (#482) | *"the reviewer cascade gets an owner"* — changes how review passes are owned/recorded, which the refresh's five recorded review types depend on. |
| `e4db5154` (#488) | *"the revert check stops accusing an edit and a deletion it did not make"* — the silent-revert verifier the refresh's F11 will run. |

### After any merge that touches `plugins/*` or `shared/*`

`bash scripts/update-marketplace.sh` then
`uv run scripts/check_plugin_cache_sync.py --strict`. Skipping this is how iterates 7–11
landed fixes that never reached the running plugins.

---

## PROMPT 1 — the merge queue (do this first)

```
/shipwright-iterate --type feature "Enable a GitHub merge queue on main so parallel
iterates stop serialising on the up-to-date requirement."
```

### Why, and why it is the priority

`main-protection` (ruleset id 17548444) has
`required_status_checks.strict_required_status_checks_policy: true` — every PR must be up
to date with `main` before merging. With N open PRs, each merge makes the rest
out-of-date, forcing a branch update plus a full re-check cycle, so merges serialise. The
operator runs many parallel iterates and this is their live pain.

**A correction to carry forward:** PR #480 is sometimes described as having unblocked
parallel iterates. It removed the **DIRTY** (conflict) half only — eleven regenerated
snapshots no longer collide. **BEHIND is a separate problem** and only a merge queue fixes
it. Do not repeat the earlier mistake of conflating them.

### The six required checks (exact configured contexts)

`Python (lint + test)` · `Analyze (python)` · `Analyze (javascript-typescript)` ·
`Shipwright Security Scan` · `Anti-ratchet + allowlist diff` · `PR Review`

Read them from the host, do not trust this list:
`gh api repos/svenroth-ai/shipwright/rulesets/17548444`.

### The hard part — solve this before enabling anything

A merge queue fires `merge_group:` events. A workflow with no `merge_group:` trigger
**reports nothing in the queue, so every queue entry blocks forever** — the `phantom`
direction of `lib/required_checks_drift.py`. Adding the trigger is mechanical for
`ci.yml`, `codeql.yml`, `security.yml` and `bloat-check.yml`.

**`PR Review` is not mechanical.** It is a two-stage pair: `pr-review.yml` runs on
`pull_request` (no write scope, handles fork PRs with attacker-influenced input) and
`pr-review-run.yml` runs on `workflow_run` and **posts a commit status** named `PR Review`.
There is no `pull_request` event in a merge group, and its whole design rests on reviewing
a *pull request's* diff. Decide deliberately, and write the decision down:

- teach it to run on `merge_group` (what does it review — the queue branch vs the base?),
- or drop `PR Review` from the required set **for merge groups only** if the host permits
  that granularity,
- or keep it required and accept that the queue cannot be used until it is reworked.

Whichever: the FR-01.17 fork-PR safety property (stage 1 holds no write scope, stage 2
never runs contributor code) must survive. `shared/tests/test_workflow_token_permissions.py`
pins it.

### Already decided — do not re-litigate

`ci.yml` and `codeql.yml` carry a `paths-ignore` on their **push** trigger only, listing
the eight generated compliance paths (added on the parked refresh branch, so it may not be
on `main` yet — check). That filter must **not** extend to `merge_group`: a queue entry
should be fully checked. `shared/tests/test_refresh_workflow_contract.py` pins the
push/pull_request asymmetry and keeps the list equal to
`lib.derived_refresh.refreshable()`.

### Order of operations — this order matters

1. Land the `merge_group:` triggers and the `PR Review` decision **first**.
2. Verify each check actually reports on a merge group before enabling the rule — the
   memory landmine here is that a gate must be verified *in its own environment*; a
   workflow that looks correct in YAML and reports nothing in a queue is the failure mode.
3. Only then add the `merge_queue` rule to the ruleset (a host config change — confirm with
   the operator before applying; it is outward-facing).
4. `uv run shared/scripts/tools/check_required_checks.py` afterwards to catch drift in both
   directions.

### Risk flag

Touching `.github/workflows/**` sets `touches_ci_supplychain`, so the F11 verifier
`check_ci_supplychain_ack` requires an ack naming the recorded posture decision, bound to
the run id **and** a fingerprint of this diff's CI paths. Write it with
`shared/scripts/tools/record_ci_supplychain_ack.py` after the final F5 write and before
the F6 commit.

---

## PROMPT 2 — finalize the derived-snapshots refresh (after the queue)

```
/shipwright-iterate "Resume the parked derived-snapshots refresh: rework it per the
rework list in its spec's STATUS section, then finalize."
```

### Where it is

- Branch `iterate/derived-snapshots-refresh`, worktree
  `.worktrees/derived-snapshots-refresh`, base `e21a7b71`.
- **Everything is staged but NOT committed** (the operator declined the override needed to
  commit). Nothing is lost, but the work is only on disk — treat it as fragile and commit
  it early via the operator's `!` route.
- Spec: `.shipwright/planning/iterate/2026-07-28-derived-snapshots-refresh.md`.
  Mini-plan: `…-refresh-miniplan.md`. Both are current.
- Reviews already recorded and terminal in
  `.shipwright/planning/iterate/iterate-2026-07-28-derived-snapshots-refresh/reviews.json`
  — all five types (`self`, `plan`, `code`, `doubt`, `external_code`), none pending.
  Verbatim reviewer text in `external-plan-review.md` and `external-code-review.md`.
- ~95 new tests, all green. F0 was made green (6062 passed) after fixing two failures.

### Do not skip this: it is NOT shippable as it stands

Three independent reviews returned `revise`. **Read the spec's `## STATUS — PARKED`
section before touching anything** — it carries the full rework list (6 high, 14 medium, 5
low) with each finding's mechanism and fix, so you do not need this handover for detail.

The four that decide whether it works at all:

1. **No git identity anywhere in the job** → `git commit` fails on a GitHub runner, and
   `commit_failed` is not routed through the failure path, so nothing is recorded. Three
   integration tests pass only by inheriting `.git/config` from the dev clone and would go
   **red in CI**.
2. **A failed regen is indistinguishable from "nothing drifted"** → green run, snapshots
   frozen forever, no card. `converge` discards the producer's outcome dict.
3. **The credential is not out of reach of repo code** — a step boundary is not a trust
   boundary inside one job, and the credentialed step validates nothing about what it
   pushes.
4. **AC-1b cannot hold in CI** — `ci-security.json` needs `gh auth status`, which the
   deliberately credential-free generation step cannot satisfy.

### Make this structural change first

M1, M2, M4 and half of H3 are one mistake: the design **polices** what the producer
touched instead of **deciding** what enters the commit. Replace police-the-tree with
take-the-eight: converge → read the eight files' bytes → restore the worktree to base
(`git checkout HEAD -- .` plus a scoped clean; never `git reset --hard`, per the
constitution) → write the eight back → `git add --` and `git commit --` with an explicit
pathspec. Then "nothing else can ride along" is a property of the construction rather than
a check that fails open.

### Keep these verbatim — they survived all three reviews

The explicit per-path `CLASSIFICATION` with a failing test on an unclassified artifact; the
exact-trailer loop guard (the adversarial pass could **not** break the no-loop claim, and
both reviewers confirmed a YAML `contains` was correctly rejected); the free-text-free
`failure_record` with its `inspect.signature` structural test; the additive `base=` token
with its forgery, round-trip and Group-E-normaliser tests; the `paths-ignore`
all-or-nothing semantics (attacked and not broken, and the porcelain parser survived every
misparse attack); the `if: github.ref == 'refs/heads/main'` job guard; and reasoning about
the admin bypass from `origin/main`'s history rather than from the ambiguous
`GET /rules/branches/main` probe, which returned all five rules for the calling actor and
is **not** evidence either way.

### After the rework

A rework this size is unreviewed code. Re-run F0 **and** both subagent reviewers
(`shipwright-build:code-reviewer`, `shipwright-build:doubt-reviewer`, model `opus` —
the silent default is Fable) plus `external_review.py --mode code`. The operator has
authorised subagents with no restriction. Then F0.5–F11.

### One lesson worth carrying, because it cost this session real credibility

An external reviewer's finding was dismissed as "mechanism claim FALSE — executed proof",
and the proof was `assert rel in digest` — an assertion that **cannot fail**, because the
digest hashes files that exist and the file existed at HEAD. The reviewer was right. When
you find yourself overriding a review, check that your counter-evidence can fail.
