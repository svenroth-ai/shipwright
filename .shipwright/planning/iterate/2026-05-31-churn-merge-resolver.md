# Iterate Spec — churn-merge-resolver

- **Run ID:** `iterate-2026-05-31-churn-merge-resolver`
- **Intent:** CHANGE (root-caused from a recurring BUG: "dirty merge conflicts" on iterate PRs)
- **Complexity:** medium (high end — `touches_shared_infra` enforces full review + full test suite)
- **Spec Impact:** MODIFY — extends the single-producer / snapshot model (PR #78, iterate-2026-05-23-compliance-md-single-producer, iterate-2026-05-27-tracked-artifacts-single-producer) with a *merge-time* reconciliation path. Adds the missing AC-6 sibling: 2026-05-27 codified `merge`-not-`rebase` for Run-ID branches but did NOT provide auto-resolution of the regenerable snapshots those merges collide on.
- **Risk flags:** `touches_io_boundary`, `touches_shared_infra`
- **Affected Boundaries:**
  - `.gitattributes` (new) → `git merge` low-level driver selection (`merge=union` for `shipwright_events.jsonl`)
  - `git merge origin/main` → branch integration → working-tree conflict set (`--diff-filter=U`)
  - Resolver → git index + filesystem re-stage surface (only an allowlisted churn set)
  - Single-producer generators (`update_build_dashboard.py`, `generate_session_handoff.py`, `aggregate_triage.py`, `update_compliance.py`) → producer→file→consumer round-trip after a merge
  - `shipwright_events.jsonl` → append-only JSONL round-trip after a `union` merge (every line must stay valid JSON; the iterate's own `work_completed` event must survive in HEAD)
  - `audit_staleness` snapshot lookup → the resolution commit must carry a `Run-ID:` trailer so the Group-E audit does not report false `snapshot_unavailable`

## Problem Statement

Verified against session `10dff198-6601-476f-b2ef-065fd6b16c36` (run `iterate-2026-05-31-canon-adr-slug-fix`, PR #121): when `origin/main` advances while an iterate PR is open, the PR becomes `CONFLICTING` / `DIRTY`. The conflicts are **never on real source code** — they are exclusively on generated/"churn" artifacts:

```
CONFLICT (content): Merge conflict in shipwright_events.jsonl       # append-only log
CONFLICT (content): Merge conflict in shipwright_test_results.json  # latest-run snapshot
# plus dirty-tree blockers (regenerated post-commit, blocking the merge):
  .shipwright/agent_docs/{session_handoff,build_dashboard,triage_inbox}.md
  .shipwright/compliance/{dashboard,sbom,test-evidence,traceability-matrix,change-history}.md
```

Each occurrence has been resolved **by hand** (≥3 times: `9e26a9c` manually fixed `architecture.md` markers; session `10dff198` hand-resolved events=union + test_results=ours). No systemic prevention was ever added: there is **no `.gitattributes`** and **no merge-time resolver**.

### Why these files are tracked ON PURPOSE (rejected alternative: untrack them)

`iterate-2026-05-27-tracked-artifacts-single-producer-and-finalize-sandbox` (externally reviewed, 14 findings) **deliberately** keeps the 3 agent-doc MDs + 5 compliance MDs tracked as committed *snapshots*:
- Stop-hook churn ("dirty after every session") was already solved there by redirecting Stop-hook writes to a gitignored `runtime/` and making `iterate-finalize` the single producer of the tracked variant.
- The Group-E `audit_staleness` audit was **extended** (its AC-5) to compare these tracked MDs against their committed snapshot (lookup keyed on the last `Run-ID:`-trailer commit touching `.shipwright/compliance/` OR `.shipwright/agent_docs/`).

Therefore **untracking is wrong**: it would reverse that decision and break the snapshot-provenance audit. The artifacts are tracked snapshots by design; the real gap is that two iterates regenerating them produce divergent content that git cannot reconcile.

### Root cause (one sentence)

Fully-derived snapshots are committed per-PR, and there is no canonical way to reconcile two divergent regenerations at merge time — so reconciliation falls to a human every time.

## Goal

Make `git merge origin/main` into an `iterate/<slug>` branch **auto-reconcile every regenerable churn artifact** (and the append-only event log) deterministically, touching **only** an explicit allowlist and **never** real source code — eliminating the recurring manual conflict surgery while keeping all artifacts tracked and the audit intact.

## Acceptance Criteria

### AC-1: `.gitattributes` unions the append-only event log
Repo-root `.gitattributes` contains `shipwright_events.jsonl merge=union`. Empirical probe: construct a base + two divergent appends, `git merge`, assert the result contains **both** sides' new lines, **zero** conflict markers, and **every** line parses as JSON.

### AC-2: events union is validated unconditionally + preserves the iterate's own event
After any merge that **touches** `shipwright_events.jsonl` (union resolves it silently — it will NOT appear in `--diff-filter=U`), the resolver runs an **unconditional** validation: (a) every non-blank line parses as JSON; (b) this run's `work_completed` event (matched by `run_id`) is present, so F11 `check_events_has_commit()` stays green. Dedup is by **exact full-line identity** (never drops a distinct event); a WARN (not a drop) is emitted if two distinct lines share an `evt` id. If validation fails (a historic line was edited/removed → union corrupted it), the resolver fails hard with remediation steps (G2/O4/O5/O6).

### AC-3: resolver is allowlist-gated with a pre-flight abort (refuses source conflicts)
New tool `shared/scripts/tools/resolve_churn_conflicts.py`:
- Reads the conflicted set via `git diff --name-only --diff-filter=U`.
- `CHURN_ALLOWLIST` = the **8 derived MDs** (5 `compliance/*.md` + 3 `agent_docs/*.md`) + `shipwright_test_results.json` + `shipwright_events.jsonl`. **`architecture.md` is NOT in the allowlist** (curated prose — a conflict on it must reach a human; folding G4/O1).
- **Pre-flight gate (runs FIRST, before any generator):** if `conflicted ⊄ CHURN_ALLOWLIST`, resolve nothing, stage nothing, exit 2, print the offending paths. **Hard safety invariant — the resolver must never clobber a code conflict, and never runs a generator on a tree with unresolved non-churn conflicts** (G4/O1/O3/O13).

### AC-4: derived MDs are regenerated transactionally from merged state, not picked
For each allowlisted derived MD, the resolver re-runs its **canonical single-producer generator** (the same one `finalize_iterate` uses) against the merged working tree. **Transactional (O2):** ALL targets are regenerated into temp files and verified to succeed FIRST; only then are they staged atomically. On any generator failure, the merge state is left untouched and remediation is printed — never a partial stage. **Write-set guard (O8):** a test asserts each resolution path mutates ONLY its targeted allowlisted file(s). Idempotency probe: running the resolver twice yields no second diff (output deterministic from merged events/specs; banner-timestamp derived from `max(event.ts)` per commit `8382ff9`, not wall-clock).

### AC-5: snapshot-only files resolved by side, not regenerated
`shipwright_test_results.json` (latest-run snapshot, **not** in `audit_staleness.DOC_REGISTRY`) is resolved as `--ours` (the PR's own run). Documented as the one "pick a side" case.

### AC-6: regenerated snapshots land in a separate non-merge follow-up commit with the Run-ID trailer
Because `audit_staleness.find_snapshot_commit()` uses `git log --diff-filter=AM -- <paths>` (which excludes merge commits — empirically confirmed, G1/O10), the regenerated MDs are committed in a **separate, non-merge follow-up commit** (after the merge commit) whose message carries `Run-ID: <run_id>`. Test: build a real `merge → follow-up` history and assert `find_snapshot_commit()` returns the follow-up SHA (not None, not the merge).

### AC-7: thin wrapper + single documented integration point
New `shared/scripts/tools/integrate_main.py` wraps the whole flow (fetch → `git merge origin/main` → events validate → resolver → follow-up commit with Run-ID trailer) so a dev never runs bare `git merge` and misses the resolver (O14). The iterate SKILL gains an explicit "Integrate origin/main" procedure pointing at the wrapper (referenced from F11 + `references/mid-flight-escalation.md` dirty-tree handling). Per the **Test-Update-Klausel**, SKILL reference text + `docs/hooks-and-pipeline.md` are updated in the same diff.

### AC-8: drift-protection meta-tests
- `CHURN_ALLOWLIST` in the resolver matches the churn set documented in `docs/hooks-and-pipeline.md` (forward + reverse drift protection).
- A synthetic non-allowlisted (source) conflict makes the resolver exit non-zero and resolve nothing.
- events `merge=union` round-trip + JSON-validity probe (AC-1) is encoded as a test.

### AC-9: docs updated
`docs/hooks-and-pipeline.md` artifact-write matrix gains a "merge reconciliation" column/section; `docs/guide.md` Appendix B updated only if a user-facing command/flag changes (else no-op, recorded as NONE).

### AC-10: dogfood + housekeeping
This iterate's own branch is integrated with `origin/main` via the new resolver (eat own dogfood; record the empirical result). Stale worktree/branch `canon-adr-slug-fix` (PR #121 closed, superseded by merged #122) is removed (`git worktree remove` + `git branch -D`).

## Confidence Calibration
- **Boundaries touched:** `.gitattributes` merge-driver selection; `git merge` conflict set; resolver git-index/filesystem re-stage (allowlisted); 4 single-producer generators (producer→file); `events.jsonl` JSONL round-trip after union; `audit_staleness` Run-ID-trailer snapshot lookup.
- **Empirical probes run** (all are encoded tests, all GREEN):
  1. **events `merge=union` round-trip** (`test_events_union_merge.py`): base + 2 divergent appends → real `git merge` → both events present, zero conflict markers, every line valid JSON. A **control** probe (same history, no attribute) confirms it conflicts WITHOUT `union`. **Finding: none** — union is correct and necessary.
  2. **events validate/dedup + run-event survival** (`test_resolve_churn_conflicts.py`): exact-line dedup collapses only byte-identical lines; an id-collision on two *distinct* lines keeps both + warns (never drops); a missing run-event → `events_invalid` (exit 4). **Finding: none.**
  3. **resolver refusal on a source conflict** (`test_preflight_aborts_on_source_conflict_touching_nothing`, `test_integrate_aborts_and_restores_on_source_conflict`): a real `app.py` conflict → status `blocked` (exit 2), nothing staged/resolved, `git merge --abort` restores a clean tree, regeneration never runs. **Finding: none** — the hard safety invariant holds.
  4. **MD regeneration via canonical producers** (`test_regenerate_invokes_canonical_producers_and_stages`): the resolver calls the SAME `finalize_iterate` helpers, so output is byte-identical to finalize **by construction** (zero drift) — idempotency is structural, not coincidental. Full-tree byte-idempotency additionally confirmed by the AC-10 dogfood.
  5. **Run-ID follow-up commit found by the REAL audit** (`test_integrate_resolves_and_audit_finds_followup`): builds a real `merge → follow-up` history, imports the actual `audit_staleness.find_snapshot_commit`, asserts it returns the **follow-up** SHA (non-merge, Run-ID trailer) — empirically confirms G1/O10 (merge commits ARE skipped by `--diff-filter=AM`). **Finding: none.**
- **Edge cases NOT probed + why acceptable:** GitHub *server-side* auto-merge of the derived MDs (GitHub cannot run a custom resolver; the iterate flow integrates locally then pushes, per session `10dff198` — `union` still helps GitHub for `events.jsonl`). Concurrent operators merging the same branch (per-clone, serialized). Non-iterate branches with Run-ID trailers (out of scope — resolver is invoked only from the iterate integration step).
- **Confidence-pattern check (asymptote heuristic):** Probe 4 (idempotency) is the central producer/consumer contract. If it shows no finding, run Probe 1 (events round-trip) as the empirical asymptote; matches ADR-024's producer→file→consumer rule. Primary risk class = boundary asymmetry (the resolver regenerates with a *different* run_id/timestamp than finalize did) — mitigated because both call the SAME generator and timestamps derive from `max(event.ts)`, not wall-clock.

## Spec Impact (mandatory at medium+)
- **Spec Impact:** MODIFY
- **Affected FRs:** none — internal framework plumbing, not a user-facing FR.
- **New FRs:** none.
- **Change type:** internal-correctness fix (closes the recurring per-PR merge-conflict class on derived artifacts).
- **None reason:** N/A (impact is MODIFY).

## External Review Findings — addressed in build

External review (OpenRouter: `gemini-3.1-pro` + `gpt-5.4`, 2026-05-31) returned 6 HIGH + 9 MED/LOW findings. Both models endorsed the direction ("sound", "right shape", "safe as a single iteration"). Folded in:

- **G1/O10 (high) — empirically confirmed:** `audit_staleness.find_snapshot_commit()` runs `git log --grep=Run-ID: --diff-filter=AM -- <compliance+agent_docs paths>`. `--diff-filter=AM` **excludes merge commits** (git computes no diff for merges by default → path filter never matches a merge). So a Run-ID trailer on the *merge* commit is invisible to the audit. → **AC-6 revised:** regenerated MDs land in a **separate non-merge follow-up commit** carrying the `Run-ID:` trailer. A test pins this against a real merge+follow-up.
- **G2/O6 (high) — empirically confirmed:** `record_event.generate_event_id()` = `evt-{uuid4().hex[:8]}` (32-bit, non-sequential). Dedup-by-id could drop a distinct event on collision. → **dedup by exact full-line identity** (never drops a distinct line); additionally WARN (never drop) if two distinct lines share an `evt` id.
- **G4/O1 (high) — both models:** `architecture.md` "report-only" breaks the hard-safety invariant (partial/middle state). → **removed from `CHURN_ALLOWLIST` entirely**; a conflict on it now trips the pre-flight abort like any source file (human resolves). AC-3 updated.
- **O2 (high) — transactionality:** a generator failing mid-run after earlier `git add`s leaves a mixed index. → resolution is **transactional**: regenerate ALL targets into temp files, verify all succeed, only then stage; on any failure leave the merge state untouched + print remediation. AC-4 updated.
- **O3/O13 (high/med) — pre-flight gate:** generators must not run on a tree with unresolved non-churn conflicts. → resolver validates `conflicted ⊆ CHURN_ALLOWLIST` and aborts (exit 2, nothing touched) **before** invoking any generator. AC-3 updated.
- **O4/G5/O5 (high/low) — events validation unconditional + robust:** `union` only safe for distinct appended whole lines; edits/removed lines/missing-trailing-newline/partial JSON can corrupt. → after any merge that touches `events.jsonl`, validate **every** line parses as JSON AND this run's event is present; fail hard with remediation. Runs **unconditionally** when `events.jsonl` changed (not only when still in `--diff-filter=U`, since `union` resolves it silently). AC-2 updated.
- **O7 (med) — git plumbing:** prefer `git restore --source=... --staged --worktree` / version-tested porcelain over `git checkout --ours/--theirs`; integration-test in a real merge conflict.
- **O8 (med) — generator write-set audit:** each generator's actual write-set + required flags audited before wiring; a test asserts each resolution path mutates ONLY its targeted allowlisted file(s).
- **O14 (med) — wrapper, not just docs:** add a thin `integrate_main.py` wrapper (fetch→merge→validate→resolve→follow-up-commit) so devs don't run bare `git merge` and miss the resolver. AC-7 updated.
- **O11 (med) — rollout:** doc note that long-lived branches must merge the `.gitattributes` commit before `union` applies. **O9 (high) — consistency model:** documented explicitly — derived MDs = "merged truth" (regenerated), `test_results.json` = "PR-owned snapshot" (`--ours`); dashboard consumer tolerates the latter (tolerant fallback verified in producer/consumer map).
- **O12 (low, security):** resolver runs repo-local generators at merge time → documented as trusted-iterate-branch only; no shell interpolation on paths/run-ids (argv lists, not strings).
- Deferred (LOW): none material.

## ADR Identity
ADR-NNN assigned at `/shipwright-changelog` release per the run-id-as-identity convention. Linked to ADR-088 (single-producer pattern), iterate-2026-05-23-compliance-md-single-producer, and iterate-2026-05-27-tracked-artifacts-single-producer (whose AC-6 `merge`-not-`rebase` convention this completes).
