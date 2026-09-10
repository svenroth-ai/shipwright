# Iterate Spec: THE KEYSTONE GATE'S POST-MERGE DETECTIVE ARM (ruling Q5)

- **run_id:** iterate-2026-09-10-keystone-detective-arm
- **Status:** IMPLEMENTED — all fifteen acceptance criteria below (AC-D1..D15) are built and
  tested; see the Test Completeness Ledger (§3) for the AC → test-function mapping.
- **Campaign:** req3-04c-ac-identity-wave2 follow-up — the card ruling Q5 filed at merge
  (`trg-a05c4aba`, PR #702, `docs(triage)` commit 8f78b93be, #708)
- **Affected FRs:** FR-01.11 (AC-identity / evidence-ledger area — same FR as P3.1–P3.6)
- **Preceding art:** `.shipwright/planning/iterate/2026-09-09-p3-6-keystone-gate.md` (the
  preventive gate this composes with, never re-derives from), `shared/scripts/ci_provenance.py`
  (`resolve_ci_verification`), `shared/scripts/ci_execution_evidence.py`
  (`resolve_execution_evidence`).

## 1. Problem, exactly as the triage card scoped it

> The keystone AC gate is a preventive, in-run check: same CI job, same evidence, no commit
> boundary and no machine boundary to forge across. A complementary DETECTIVE control could
> instead ask, after the fact, whether a commit already on the default branch's tip genuinely
> satisfied the gate, using evidence bound to a real trunk CI run — composing with the existing
> cross-commit evidence resolver rather than reusing the preventive gate's own producer.

Two independent facts make this a genuine gap, not a duplicate of the preventive gate:

1. **The preventive gate never runs on a push.** `check_keystone_ac_gate.py`'s own `ci.yml` step
   is `if: github.event_name == 'pull_request'` (design §5.7) — a direct push to `main` bypasses
   it entirely, a limitation the design doc discloses (§7: *"a direct push to the default branch
   is ungated"*). Nothing recomputes the gate's verdict for a commit that landed that way.
2. **The preventive gate trusts its OWN run's local regeneration** (`_read_head_manifest` reads
   the worktree file the same job just rewrote). That is correct for a same-run question but is
   exactly the trust boundary `ci_provenance.py`'s own docstring names as Q2 — *"can I trust
   evidence I did not produce, for a commit that is not mine?"* — which the preventive gate
   explicitly does NOT answer (its own module docstring: *"Why this gate does NOT call
   resolve_execution_evidence"*).

## 2. Operating-context feasibility check (empirical, re-run for this iterate)

**Precondition status, checked against the real repo before writing a line of code:**

```
$ gh api repos/svenroth-ai/shipwright/actions/workflows/ci.yml/runs?branch=main&event=push&status=success&per_page=1
  head_sha=15929f80… (current origin/main tip)

$ gh api repos/svenroth-ai/shipwright/actions/runs/34496487215/jobs
  "Confirm traceability manifest verified (no drift)" -> conclusion: "skipped"
```

**`resolve_ci_verification` reports `not_verified` for `main`'s own tip today** — the pre-existing
structural manifest drift measured in the P3.6 design (§2.3) is still present. This is exactly
what the triage card warned: *"that resolver's precondition ... does not reliably hold yet
today, so this card is scoped, not urgent."* Two things follow:

- The detective control **cannot be validated end-to-end against a real confirmed run today**,
  because no commit has one yet. Its correctness must therefore rest on unit tests against
  fixtures/mocks of the two resolvers, exactly the discipline the preventive gate's own pure
  core (`_keystone_core.py`) already uses — that module has never had a live PR failure to test
  against either, and is unit-tested regardless.
- The control's honest, current-day steady-state output on every commit it is pointed at is
  `run_not_verified` (see §4) — a defined, non-alarming, correctly-reported "cannot judge yet",
  not a false green and not a false alarm. That IS the deliverable: the seven-way classification
  below, proven correct by its unit tests, waiting for the precondition (a real, drift-clean
  push run) to start actually resolving to `gate_confirmed_clean` / `gate_violated`.

**Scope decision this measurement drives:** ship the control **advisory-only, not wired into
`ci.yml` and not a CI gate** (ruling Q5's own text: *"it cannot block a merge"* — design §4). It
is a standalone, on-demand tool — the same posture `mint_ac_ids.py` ships in today (*"not wired
into any authoring flow ... deliberately"*). Wiring it into a scheduled/compliance-audit
consumer is a **separate, later decision**, named but not built here (§7).

## 3. What this iterate must NOT be

- **Not a CI gate.** No `ci.yml` step, no exit code that fails a job. §4/§7 of the P3.6 design
  are explicit that a detective control here "cannot block a merge" — it reports, it does not
  enforce.
- **Not a second unforgeability predicate.** `resolve_ci_verification` and
  `resolve_execution_evidence` are the ONLY places this system trusts evidence across a commit
  boundary. This iterate adds zero new trust logic — it reuses both verbatim, unedited.
- **Not a rebuild of `_keystone_core.py`'s decision logic.** `evaluate_keystone` already encodes
  every finding kind (`binding_removed`, `failed`, `skipped`, `not_selected`, `layer_gap`,
  `unminted_changed`, `new_frs_without_criteria`, `reader_divergence`) against two manifest dicts
  and a change set — it does not care where those dicts' bytes came from. This iterate's only new
  work is **which manifest dicts it hands that function**, sourced from CI-verified evidence
  instead of a local regeneration.
- **Not the orphan-test detector.** That is the OTHER card filed at the same merge
  (`trg-f68795d2`, p3.7(b)'s three named unbind shapes) — a different, harder gate, out of scope
  here.

## 3.5 Architecture Review (Branch A, external, 2026-09-10) — SCOPE REDUCED, not rejected outright

Both external reviewers (openai/codex, glm/openrouter) returned `reject` on the brief as
originally scoped (a standalone CLI + `ci.yml`-absence drift test + exit-code contract). Verdicts
agreed within one step (no contradiction). Findings, condensed:

- **Proportionality (openai medium, glm high).** The control's steady-state output on every real
  commit today is `run_not_verified` (§2's own measurement) — it cannot demonstrate a substantive
  outcome until the P3.6 §2.3 structural drift is fixed by unrelated, separately-carded work.
  Shipping a full CLI + exit-code contract + a standing "prove `ci.yml` never references this"
  drift test now buys a permanently-maintained interface for something currently inert.
- **Ownership (openai medium, glm medium).** Advisory-only, not wired into `ci.yml` or compliance
  audit, single-commit granularity — nobody is committed to running it. An unwired control nobody
  invokes is operationally indistinguishable from no control.

**Both reviewers independently named the same reduction** as the acceptable smaller commitment
(glm, verbatim): *"the smallest thing that would do ... the pure core module plus its unit tests
... with no CLI, no AC-D10/D11/D12 exit-code/ci.yml-absence machinery."*

**Reconciliation adopted.** Build the classification logic AND the resolver composition as a
plain, importable Python module — no standalone CLI script, no `argparse`, no exit-code contract,
no `ci.yml`-absence drift test (there is nothing to keep out of `ci.yml` if nothing exposes a
runnable entry point). This is not "TBD" — the seven-way classification, the CI-verified manifest
construction, and the composition with both resolvers are all real, tested code reachable by
calling `classify_commit(...)` directly (from a REPL, a future script, or a future compliance-
audit consumer) — it just does not commit to a specific CLI/wiring contract before a real
consumer exists to shape one, which is exactly what both reviewers objected to. §4 and the
acceptance criteria below are revised accordingly: the original CLI-shaped exit-code/`ci.yml`-
absence criteria are dropped entirely (nothing to test — there is no CLI and no wiring), and new
criteria (AC-D11, AC-D12, AC-D13) were added from the SECOND external review round (plan review,
§3.5.1 below) to cover edge cases that round found in the classification/composition logic itself.

### 3.5.1 Plan Review (external, `--mode iterate`, 2026-09-10) — `revise`, both reviewers

Run over the mini-plan + this spec, AFTER §3.5's scope reduction. Both reviewers (openai/codex,
glm/openrouter) returned `revise` (agreeing within one step). Findings and dispositions:

| Finding (condensed) | Severity | Disposition |
|---|---|---|
| Mini-plan still described the CLI dropped in §3.5 — spec/plan contradiction | high/medium | Fixed — mini-plan rewritten, CLI language removed entirely |
| "Six-way" mislabels a seven-row table | low/medium | Fixed — renamed throughout |
| Caller-supplied `parent` permits a mismatched/malicious commit pair; merge/root commits unhandled | medium/medium | Fixed — `classify_commit` takes no `parent`; resolves first-parent internally; root commit raises `ReadError` (§4.1, AC-D12) |
| Duplicate test `id`s within one requirement's verified evidence — no disposition | medium | Fixed — fails closed with `ReadError` (§4.1, AC-D11) |
| `build_verified_manifest`'s "shallow copy" could share mutable state with the input | low | Fixed — per-link fresh dicts, no shared nested state (§4.1) |
| PR-merged commits will dominate as `no_qualifying_run` once the drift is fixed — undocumented | medium | Fixed — named explicitly in §4.2, AC-D13 pins a fixture |
| No signal mechanism for when the precondition resolves and the control goes live | low | Accepted as a documented gap — §6 already names the drift-fix dependency; a watch/alert mechanism is itself a wiring decision deferred to §6 alongside the periodic-consumer item, not invented here for a module with no consumer yet |

All findings above `low`/informational are fixed in this revision; the one accepted-as-is finding
(no live-signal mechanism) is a scope call consistent with §3.5's own reduction — building a
notification mechanism for an unwired module would repeat the exact proportionality objection
§3.5 already resolved.

### 3.5.2 Plan Review — Round 2 (external, `--mode iterate`, re-run 2026-09-10 over the finalized
mini-plan + spec, after the round-1 fixes) — `glm: approve`, `openai: revise`

Re-run at review-cascade time (the round-1 raw payload was not persisted to disk before this
session was summarized, so re-running was the honest path rather than reconstructing round-1's
JSON from memory). Findings and dispositions:

| Finding (condensed) | Reviewer(s) | Severity | Disposition |
|---|---|---|---|
| §4.2's claim that ordinary PR-merged commits predominantly read `no_qualifying_run` is empirically wrong — `ci.yml` triggers `push: branches: [main]`, so a normal merge DOES get its own push-event run | both, independently | high/medium | Fixed — §4.2 corrected, `NO_QUALIFYING_RUN`'s docstring corrected, AC-D13's framing corrected from "dominant steady state" to "genuine edge case" |
| Orchestration order risk: evidence resolution might read the wrong commit's manifest | openai | medium | Verified NOT a real defect — the code already reads `committed_manifest` at `commit` before calling `resolve_execution_evidence`, in the correct order (`classify_commit`, lines ~239-241); the finding was based on the mini-plan's prose ambiguity, not the actual code. No code change; mini-plan prose left as-is since the spec's own §4.1 already states the correct order precisely |
| Neither resolver's status is validated against its own documented enum; an unexpected status silently falls through to the "next" branch | openai | medium | Fixed — both status checks now `raise ReadError` on any status outside the documented four-way/three-way contract (§4.1, AC-D15) |
| `commit` is used across multiple calls without being resolved to an immutable SHA once up front — a mutable ref could move between calls | openai | medium | Fixed — `classify_commit` now canonicalizes via `git rev-parse --verify` before any resolver call (§4.1, AC-D14) |
| Duplicate test ids in the COMMITTED manifest's own bindings (not just verified evidence) are not rejected | glm | low | Accepted as-is — the committed manifest's link identity flows through `ac_change_set`/`evaluate_keystone` unedited, the same trust posture the preventive gate already has for the committed file; `build_verified_manifest`'s own duplicate check is scoped to the untrusted verified-evidence side by design (§4.1) |
| A commit predating the traceability manifest might surface as an uncaught exception rather than a classified outcome | glm | low | Verified NOT a real defect — `read_base_manifest`'s absent-file branch returns `({}, warning)`, not `ReadError`, for a path genuinely absent at a valid commit; already covered by the existing frozen module's own contract, no new test needed |
| No smoke test calling the real (unmocked) resolvers to catch signature drift | glm | low | Accepted as scope-bounded — this module's only two dependencies each carry their own extensive test suites (`test_ci_provenance.py`, `test_ci_execution_evidence.py`); a signature-drift smoke test here would duplicate that coverage for a module with no live consumer yet (§3.5's proportionality argument extends to this) |
| No explicit ordering statement between the deferred consumer card and the P3.6 §2.3 drift-fix dependency | glm | low | Fixed — §6 now states the ordering constraint explicitly |

Two of eight findings were substantive code defects (both openai, both fixed: fail-closed status
validation, SHA canonicalization); one was a documentation/framing correction shared by both
reviewers independently (the single most important finding of this round); two were investigated
and found not to be real defects (verified against the actual code/frozen-module behavior, not
dismissed); three were accepted as scope-bounded, consistent with §3.5's own proportionality
argument. No third round was run — `glm` already returned `approve`, and every `openai` finding
above `low` was either fixed or verified non-applicable.

## 4. Design

### 4.1 The composition, precisely

```
shared/scripts/tools/verifiers/_keystone_detective_core.py
```

One module, no CLI (§3.5). Two layers inside it, kept separate on purpose:

- `build_verified_manifest(committed_manifest, evidence)` and the outcome-classification tree are
  PURE — no git, no filesystem, no subprocess, no `gh` — unit-testable against fixtures exactly
  like `_keystone_core.py` already is.
- `classify_commit(commit: str, *, project_root: Path)` is the thin orchestration entry point that
  actually calls the two resolvers and the existing keystone readers, then hands their outputs to
  the pure layer above. This is the one function a future consumer (a script, a compliance-audit
  producer, a REPL) calls; it is deliberately NOT wrapped in a CLI/argparse/exit-code contract
  (§3.5) until a real consumer exists to shape that contract.
  **Takes no `parent` argument** (revised, external plan review, both reviewers, medium — a
  caller-supplied parent permits an accidental or malicious mismatched pair). It resolves the
  commit's FIRST parent itself via `git rev-parse --verify "<commit>^1"` and raises `ReadError`
  naming the reason for a root commit (no parent to diff against) or any other unresolvable ref.
  A merge commit is judged against its first parent only — the ordinary "what would have been
  reviewed" lineage; the merge's OTHER parent's own changes are that parent commit's own concern,
  not this one's, and are not silently assumed away (documented, not smuggled in — plan review,
  glm, medium).

**What is reused, unedited, from three existing modules:**

| Reused as-is | From | Why safe to reuse |
|---|---|---|
| `resolve_ci_verification` | `shared/scripts/ci_provenance.py` | The one unforgeability predicate for "did a real trunk run confirm this commit's manifest structure" |
| `resolve_execution_evidence` | `shared/scripts/ci_execution_evidence.py` | The one predicate for "was this commit's per-requirement `tests`/`coverage` produced by that same verified run" |
| `read_base_manifest` (called at BOTH the target commit and its parent — the function's own docstring already documents the fail-closed three-way read as generic to "a commit", not specific to "base") | `shared/scripts/tools/verifiers/_keystone_base_manifest.py` | Structural manifest reads are not an execution claim (§5.3 of the preventive design already argues this for the base side; it applies identically to reading the *target* commit's own committed bytes structurally) |
| `ac_change_set(project_root, base_sha, head_sha, head_manifest, base_manifest)` | `shared/scripts/tools/verifiers/_keystone_ac_digest.py` | Fully generic over two git SHAs already — nothing here assumes "PR base" vs "PR head", only "earlier" vs "later" commit |
| `evaluate_keystone(change_set, head_manifest, base_manifest)` | `shared/scripts/tools/verifiers/_keystone_core.py` | Duck-typed, no I/O — decides purely from two manifest dicts and a change set |

**What is new:** for a target commit `C` with parent `P`, three inputs must be produced before
those five functions can run:

1. `base_manifest` = `read_base_manifest(project_root, P)` — `P`'s own committed manifest,
   structurally (same trust argument as the preventive gate's base side: `P` is an ancestor of
   the branch, already merged).
2. `committed_manifest` = `read_base_manifest(project_root, C)` — `C`'s own committed manifest,
   structurally. This gives the correct `acs[ac_id].tests[layer]` **link identities** (which
   tests are bound to which AC) — a structural claim, not an execution one.
3. **The part that needs the resolver:** `committed_manifest`'s link `executed`/`status` fields
   are the committed file's OWN claims, exactly the values an attacker (or a stale commit) could
   have hand-edited or never re-run — the same class of untrusted self-report `ci_provenance.py`
   exists to close. So this iterate builds `verified_manifest` = a shallow-per-link copy of
   `committed_manifest` where every link's `status`/`executed` is OVERWRITTEN from
   `resolve_execution_evidence(C, committed_manifest=committed_manifest, ...)`'s own
   per-requirement `tests[layer]` list, matched **by link `id` within the same requirement key**
   (never by a global id index — two requirements could theoretically share a test id in a
   hand-edited manifest, and this reader has no reason to assume otherwise). A link whose id is
   NOT found in the verified evidence's own list for that requirement is written as
   `executed: "not_run"` — fail-closed, the same posture `_layer_coverage_regen` already takes
   for "broken evidence staging" (P3.6 design §5.4). **Two links sharing the same `id` within one
   requirement's verified `tests[layer]` list is refused with `ReadError`** rather than resolved
   by silent last-write-wins (revised, external plan review, openai, medium) — an ambiguous shape
   this reader has no principled way to pick a winner from. `build_verified_manifest` builds fresh
   per-link dicts rather than mutating `committed_manifest`'s own nested structures, so the
   returned manifest shares no mutable state with the manifest that was read from git (revised,
   plan review, glm, low — "shallow copy" risk).
4. `evaluate_keystone(ac_change_set(project_root, P, C, committed_manifest, base_manifest),
   verified_manifest, base_manifest)` — the existing pure evaluator, unedited, fed the
   CI-verified manifest instead of a local regeneration.

**Why `committed_manifest` (not `verified_manifest`) drives change-set + binding-identity
resolution, and `verified_manifest` only drives greenness.** `ac_change_set` needs `spec_path`s
and `acs[ac_id]` link IDENTITIES (which tests exist, which AC they claim), which are structural
facts unaffected by whether they ran green — identical to how the preventive gate's own base
manifest is read purely structurally (§5.3 of that design). Only the per-link `executed`/`status`
— the part `ci_provenance`/`ci_execution_evidence` exist to authenticate — is substituted.

### 4.2 The seven-way classification (named up front, per the triage card's own instruction)

Exhaustive, mutually exclusive. A caller must never collapse any two of these into one "ok" or
one "not ok" bucket — the whole point of the card was that "detective arm TBD" hides exactly
this distinction.

| outcome | condition | meaning | must NOT be read as |
|---|---|---|---|
| `no_qualifying_run` | `resolve_ci_verification(C).status == "no_record"` | `C` never had a qualifying push-event CI run on the default branch at all — no evidence exists to judge it by | a violation, or a pass |
| `run_not_verified` | `.status == "not_verified"` | a qualifying trunk run for `C` exists, but that run's OWN structural drift check did not confirm a clean manifest — the run genuinely did not pass what this control needs (today's steady state, §2) | the same as `no_qualifying_run` — a run DID happen, it just didn't confirm |
| `verification_query_failed` | `.status == "error"` | the query to GitHub itself could not complete (timeout, `gh` missing, malformed response) | evidence of anything about `C` — `error` never means "could not determine" is a safe default to fall through from |
| `execution_evidence_unavailable` | verification is `verified` AND `resolve_execution_evidence(...).status == "unavailable"` | `C`'s manifest STRUCTURE was confirmed, but no per-test execution artifact exists (aged out of retention, or predates this mechanism) — greenness cannot be recomputed | a violation (structure was fine) or a pass (greenness is literally unknown) |
| `execution_evidence_query_failed` | `.status == "error"` | the artifact query/download/content-binding pipeline itself failed | the same "could not determine" discipline as `verification_query_failed` |
| `gate_violated` | evidence `confirmed` AND the recomputed `KeystoneVerdict.any_hard` is true | `C` reached `main` without a changed AC's bound test(s) being green, per CI-VERIFIED evidence — this is exactly what a direct push (or any other preventive-gate bypass) would look like after the fact | — (this is the one substantive finding) |
| `gate_confirmed_clean` | evidence `confirmed` AND no hard finding | `C` genuinely satisfied the gate, per real trunk CI evidence, not merely per its own committed self-report | — |

The example the triage card itself gave — *"a commit that never had a qualifying trunk run at
all versus one whose run genuinely failed"* — is `no_qualifying_run` vs. `run_not_verified`
above, named exactly as asked.

**Correction (2026-09-10, external plan review round 2, both reviewers, high/medium):** an
earlier draft of this section claimed `no_qualifying_run` was the dominant steady state for an
ordinary PR-merged commit, reasoning that "a PR-merge commit's only CI run is the
`pull_request`-event run before merge, not a `push` run of its own." **That is empirically wrong
for this repo.** `ci.yml` triggers `on: push: branches: [main]` — the merge commit GitHub creates
when a PR is merged (merge, squash, or rebase) lands on `main` via a real `push`, which fires its
own `push`-event CI run distinct from the pre-merge `pull_request`-event run. `main`'s own
concurrency-group comment in `ci.yml` states this directly: "On `main` the group is per-COMMIT
and cancelling is off, so EVERY merge is verified."

The corrected picture: `no_qualifying_run` is the **genuine edge case** — an Actions outage, a
workflow disabled at merge time, GitHub API lag before the run is queryable via the API, or a
commit predating this `ci.yml`'s push trigger. The dominant real-world outcome for an ordinary
PR-merged commit, once the P3.6 §2.3 drift is eventually fixed, is instead `verified` (a push run
exists, completed, and its structural step confirmed) — and TODAY, before that drift is fixed, it
is `run_not_verified` (a push run exists and completed, but the structural step did not confirm;
§2's live measurement). AC-D13 still pins the `no_qualifying_run` fixture (a commit whose only run
is a `pull_request`-event run) because the scenario is real and worth distinguishing from AC-D1 —
it is simply no longer framed as "what every ordinary merge looks like."

### 3.5.3 Code Review (Stage 2, internal, 2026-09-10) — `approve-with-nits`

Run over the finished build (after Plan Review Round 2's fixes). Findings and dispositions:

| Finding (condensed) | Severity | Disposition |
|---|---|---|
| `build_verified_manifest`'s "no shared mutable state" claim did not hold for pass-through nodes (a requirement with no/empty `acs`, or an AC node whose `tests` isn't a dict aliased the input directly) | medium | Fixed — pass-through paths now `copy.deepcopy`; mutation test extended to cover the FR-01.02 (empty `acs`) case that previously went unexercised |
| `EmptyLinkWalk` imported with `# noqa: E402,F401` but unused, inconsistent with the sibling module's own re-export convention; `ReadError` also missing from `__all__` | low | Fixed — both re-exported per `_keystone_ac_digest.py`'s convention, added to `__all__` |
| `_verification`/`_evidence`/`_repo_with_ac01_edit` copy-pasted verbatim across both new test files — the exact drift `_keystone_repo.py`'s own docstring says it exists to prevent | low | Fixed — moved into `_keystone_repo.py` as `make_verification`/`make_evidence`/`repo_with_ac01_edit`, imported (aliased) by both test files |
| Two GitHub API round-trips per `verified`-path commit (`resolve_execution_evidence` internally re-calls `resolve_ci_verification`) — inherited from the frozen module, undocumented here | low | Fixed — one-line note added to the module's own docstring; no code change (frozen-module behavior, out of scope to edit) |
| No `timeout` on the two new `_run_git` calls (SHA canonicalization, parent resolution), unlike other git-facing callers in the same `git_helpers.py` | informational | Fixed — both now pass `timeout=_GIT_TIMEOUT_SECONDS`, matching the module's own convention |

All five findings were fixed (four low/informational, one medium). The medium finding
(mutation-safety gap) is the more consequential one — the fix additionally required splitting
`build_verified_manifest` into its own module (`_keystone_detective_manifest.py`) once the fix
pushed the combined file past the 300-LOC guideline; see §4.3.

### 3.5.4 External Code-Review Cascade (medium+, `--mode code`, 2026-09-10) — `revise`, both
reviewers

Run over the full diff after §3.5.3's internal code-review fixes. Both reviewers (openai/codex,
glm/openrouter) returned `revise` (agreeing). Findings and dispositions:

| Finding (condensed) | Reviewer(s) | Severity | Disposition |
|---|---|---|---|
| `build_verified_manifest`'s no-shared-mutable-state contract still did not hold: the top-level `{**committed_manifest, ...}` merge, and sibling keys inside substituted requirement/AC nodes, still aliased the input — the internal code review's fix only covered the two explicit pass-through branches | both, independently | medium | Fixed — rewritten to `copy.deepcopy(committed_manifest)` once up front, then mutate the copy in place; categorically closes every aliasing path at once rather than patching branches one at a time |
| The AC-D13 test is a hollow duplicate of AC-D1's — both mock `resolve_ci_verification` to `no_record` with only the `detail` string differing, and `classify_commit` never branches on that string | glm | medium | Fixed — removed; AC-D13 reframed to point at the resolver's own existing test (`test_ci_provenance.py::test_no_record_when_only_pull_request_runs_exist`) rather than re-testing it hollowly here |
| Duplicate-id refusal is scoped across layers, not per layer, which could reject a legitimate same-id-under-two-layers shape | glm | medium | Verified as correct-as-designed, not fixed — substitution itself matches by id alone with no layer parameter, so narrowing the duplicate check to per-layer would let substitution silently prefer whichever layer's dict is visited last on a genuine cross-layer collision, reintroducing the exact last-write-wins risk AC-D11 exists to close. Documented in the function's own docstring |
| A verified link with a missing/non-string `status`/`executed` writes a raw `None` into the manifest instead of failing closed to `not_run` | glm | low | Fixed — such a link is now treated as absent, falling through to the same `not_run` fallback an unmatched id gets |
| `git rev-parse --verify <ref>` resolves an annotated TAG to the tag object's own sha, not the commit it points at | glm | low | Fixed — canonicalization now uses the `^{commit}` peel suffix, guaranteeing a commit sha |
| AC-D14's test only proves the canonical sha reaches the short-circuit's `resolve_ci_verification` call, not the parent lookup, `resolve_execution_evidence`, or either manifest read | openai | low | Fixed — a second AC-D14 fixture drives the `verified` path and captures the commit argument at both `read_base_manifest` calls and `resolve_execution_evidence` |

Both `medium`-severity findings and both `low`-severity findings were fixed; one `medium` finding
was investigated and disposed as correct-as-designed after tracing the substitution logic's own
id-only matching, not overridden by review authority alone. No third round was run — every
finding above was either fixed or dispositioned with a traced justification, the same bar
Round 2's own plan review used.

### 3.5.5 Post-push Tier-3 PR Review (`openai/gpt-5.6-luna`, PR #716) — two consecutive `BLOCK`s, same defect class

Runs automatically as a Required Check once the PR is opened (sensitive-path PR, per B4.5) — after
F6/F11, not part of the pre-push review cascade above.

| Round | Finding (condensed) | Severity | Disposition |
|---|---|---|---|
| 1 | `build_verified_manifest`'s `node.get("tests")` / `.items()` assumed every `evidence.requirements` VALUE is a mapping and that its `tests` is itself a mapping; a malformed confirmed-evidence structure raised an uncaught `AttributeError` | blocking | Fixed — a non-mapping requirement node, or a non-mapping `tests` value, treated as no verified evidence for that requirement. Two regression tests added |
| 2 | The round-1 fix left `evidence.requirements` ITSELF unvalidated: `(evidence.requirements or {}).items()` still raises `AttributeError` on a truthy non-mapping (list/string/object) | blocking (`deliver_pr.py`'s non-converging guard classified this as the SAME recurring finding as round 1 — both are the identical "unvalidated nesting level" defect class, one level apart) | Fixed comprehensively — every level `build_verified_manifest` dereferences (`evidence.requirements`, each requirement node, each node's `tests`) is now validated as a mapping before iteration, closing the whole class in one pass rather than patching one more level. Third regression test added (`test_a_non_mapping_evidence_requirements_is_treated_as_no_verified_evidence`) |

Non-blocking comment (round 1): the existing missing-field test covered `executed` but not `status`
specifically — added `test_a_verified_link_missing_status_specifically_is_treated_as_absent` as its
sibling case.

### 4.3 Where it runs, and where it deliberately does not (yet)

- **No CLI, no script entry point** (§3.5). `classify_commit(commit, *, project_root)` is called
  directly by whatever consumes it. It raises nothing it doesn't
  document: a genuine local infra fault before classification (unresolvable ref, unreadable
  manifest at either commit) surfaces as the same `ReadError`/`EmptyLinkWalk` exceptions
  `_keystone_ac_digest`/`_keystone_core` already define — no new exception type, no exit-code
  contract to invent.
- **Not added to `ci.yml`.** No step, no job, no Required Check, no argv surface for one to be
  added to.
- **Not wired into `shared/scripts/tools/compliance_audit` (or any Group check).** A future
  detective/compliance consumer calling this CLI periodically (e.g., over the last N commits on
  `main`) is a real, named next step — but it is a wiring decision with its own cadence/threshold
  questions (how far back, how to surface `gate_violated` to an operator) that deserve their own
  card rather than being smuggled into this one. Named explicitly in §6, not built here — the
  same discipline `mint_ac_ids.py`'s own docstring uses for its own "not wired in yet".

## 5. Known limitations (disclosed, not fixed)

- **Cannot be end-to-end validated against a real `gate_violated`/`gate_confirmed_clean` case
  today** (§2) — `main`'s pre-existing structural drift means every real commit currently reads
  `run_not_verified`. Unit-tested against mocked resolver outputs for all seven outcomes instead,
  the same posture the preventive gate's own pure core has always had for its zero-population
  findings.
- **Only as strong as the two resolvers it composes with.** It adds no new trust logic and
  therefore inherits both modules' own documented compromise boundaries verbatim (a `ci.yml`
  change reaching `main` via push, or `gh`/git-environment compromise). Restated, not repeated in
  full, per `ci_provenance.py`'s own docstring.
- **Does not itself decide what an operator should DO with a `gate_violated` verdict.** It is a
  detective signal, not a remediation. Exactly ruling Q5's own scope: *"It is preventive vs
  detective, it cannot block a merge"* (P3.6 design §4).
- **A test's body can still be weakened without this control noticing**, identically to the
  preventive gate's own disclosed limit (P3.6 design §7) — greenness of a binding is not the same
  claim as correctness of the test behind it.
- **Single-commit granularity.** This iterate builds the per-commit classifier only; scanning a
  RANGE of commits on `main` (e.g., "everything since the last known-clean tip") is the wiring
  decision named in §4.3, not built here.

## 6. Deliberately deferred (named explicitly, not "TBD")

1. **A periodic/on-demand consumer** that walks recent `main` commits and surfaces
   `gate_violated`/`execution_evidence_unavailable` findings to an operator (candidate home:
   `/shipwright-compliance`'s detective-audit groups, or a dedicated triage producer). Needs its
   own scope call on cadence and noise (an unavailable-evidence commit should not paginate an
   operator's triage inbox once per run).
- **Resolving the P3.6 §2.3 structural drift itself** so `resolve_ci_verification` starts
  returning `verified` for real commits — not this card's to fix (P3.6 design §7 already says
  so), but it is this control's own precondition, so it is the one dependency worth naming
  explicitly rather than leaving implicit a second time. **Ordering constraint (Plan Review Round
  2, glm):** the drift-fix card should land BEFORE the periodic/on-demand consumer card above —
  building a consumer on top of a precondition that never holds would ship a permanently-inert
  operator-facing feature, the exact "TBD" shape the original triage card was filed to prevent.

## 7. Acceptance criteria

- **AC-D1.** `resolve_ci_verification(...).status == "no_record"` classifies as
  `no_qualifying_run`, never conflated with `run_not_verified`.
- **AC-D2.** `.status == "not_verified"` classifies as `run_not_verified`.
- **AC-D3.** `.status == "error"` classifies as `verification_query_failed`, and this path never
  proceeds to call `resolve_execution_evidence` at all (an unresolved verification cannot license
  even asking the execution-evidence question).
- **AC-D4.** Given `verified` structural verification, `resolve_execution_evidence(...).status ==
  "unavailable"` classifies as `execution_evidence_unavailable`.
- **AC-D5.** Given `verified` structural verification, `.status == "error"` classifies as
  `execution_evidence_query_failed`.
- **AC-D6.** Given `confirmed` execution evidence and a fixture where every changed AC's bound
  links are all `status == "enabled", executed == "pass"`, the classifier returns
  `gate_confirmed_clean`.
- **AC-D7.** Given `confirmed` execution evidence and a fixture where a changed AC's committed
  binding names a test link whose VERIFIED (not committed) `executed` is `"fail"`, the classifier
  returns `gate_violated` — proving the tool overrides the committed file's own self-reported
  status rather than trusting it.
- **AC-D8.** A link present in the committed manifest's AC binding but ABSENT from the verified
  execution evidence's own per-requirement test list is treated as `executed: "not_run"`
  (fail-closed), and a fixture exercising this reaches `gate_violated` (via the existing
  `not_selected`/`skipped` finding path in `evaluate_keystone`, unedited).
- **AC-D9.** The link-id match is scoped PER REQUIREMENT KEY, not globally: a fixture with the
  same test `id` string bound under two different requirement keys, verified-green under one and
  verified-failed under the other, resolves each AC's greenness independently.
- **AC-D10.** `classify_commit` never calls `resolve_execution_evidence` when
  `resolve_ci_verification` did not return `verified` (AC-D3 restated as a call-count assertion,
  not just an output assertion — an unresolved verification must not even ask the execution
  question).
- **AC-D11.** Two links sharing the same `id` within one requirement's VERIFIED `tests[layer]`
  list raise `ReadError` rather than being silently resolved by last-write-wins — a fixture
  exercises this and asserts the specific exception, not a generic failure. The check is scoped
  ACROSS layers within a requirement, not per layer, because substitution itself matches by id
  alone with no layer parameter (external code review round 2, glm — considered and kept
  as-designed, not a defect: see §3.5.4). A verified link whose own `status`/`executed` fields are
  missing or non-string is treated as ABSENT (falls through to the same fail-closed `not_run` an
  unmatched id gets), never written into the manifest as a raw `None` (external code review round
  2, glm, low — fixed).
- **AC-D12.** `classify_commit` resolves the target commit's first parent internally
  (`<sha>^1`); it accepts no `parent` argument. A root commit (no parent) raises `ReadError`
  naming the reason. A fixture repo with a genuine root commit exercises this without crashing
  with an unrelated git error.
- **AC-D13.** Not independently re-tested at this module's boundary (external code review round
  2, glm, medium — a hollow duplicate of AC-D1's test was removed): `classify_commit` does not
  branch on WHY `resolve_ci_verification` returned `no_record`, only THAT it did, so the
  "only-a-pull_request-run" scenario collapses into AC-D1's generic case with no distinct code
  path to exercise here. The scenario itself is already tested at the resolver boundary —
  `shared/tests/test_ci_provenance.py::test_no_record_when_only_pull_request_runs_exist`.
- **AC-D14.** `commit` is canonicalized to a full COMMIT sha via `git rev-parse --verify
  "<ref>^{commit}"` (the `^{commit}` peel suffix, not a bare `--verify <ref>` — an annotated tag
  would otherwise resolve to the tag object's own sha, external code review round 2, glm, low —
  fixed) BEFORE any resolver call, and that resolved value — not the caller's original ref — is
  what both resolvers, the parent lookup, and both manifest reads all receive; passing a mutable
  ref (e.g. `HEAD`) proves this via TWO capture fixtures, one for the short-circuit path
  (`resolve_ci_verification`) and one driving all the way to the `verified` path
  (`resolve_execution_evidence` + both `read_base_manifest` calls — external code review round 2,
  openai, low, the first fixture alone did not cover this). An unresolvable ref raises `ReadError`
  before any network call (external plan review round 2, openai, medium).
- **AC-D15.** Either resolver returning a status string outside its own documented contract
  (`resolve_ci_verification`: verified/not_verified/no_record/error;
  `resolve_execution_evidence`: confirmed/unavailable/error) raises `ReadError` rather than being
  silently treated as the "next" branch (`verified`/`confirmed`) — fail-closed against a future
  contract change in either frozen module (external plan review round 2, openai, medium).

## Confidence Calibration

- **Boundaries touched:** `resolve_ci_verification` / `resolve_execution_evidence` (consumed,
  read-only, unedited), `evaluate_keystone` / `ac_change_set` / `read_base_manifest` (consumed,
  unedited), one new pure/orchestration module. No CLI, no `ci.yml` edit (§3.5 — scope reduced
  after Architecture Review).
- **Empirical probes run:** §2's live `gh api` query against `origin/main`'s real tip (result:
  `not_verified`, matching the design's own prediction). No committed automated test repeats this
  live call (it would make the suite network-dependent); it is a documented, one-time design-time
  measurement, the same convention the P3.6 design's own §2.3 measurement used.
- **Test Completeness Ledger:**

  | AC | Test | File | Status |
  |---|---|---|---|
  | AC-D1 | `test_no_record_classifies_as_no_qualifying_run` | `test_keystone_detective_core.py` | tested |
  | AC-D2 | `test_not_verified_classifies_as_run_not_verified` | `test_keystone_detective_core.py` | tested |
  | AC-D3 | `test_verification_error_classifies_as_verification_query_failed` | `test_keystone_detective_core.py` | tested |
  | AC-D4 | `test_execution_evidence_unavailable` | `test_keystone_detective_core.py` | tested |
  | AC-D5 | `test_execution_evidence_query_failed` | `test_keystone_detective_core.py` | tested |
  | AC-D6 | `test_confirmed_evidence_all_green_is_gate_confirmed_clean` | `test_keystone_detective_greenness.py` | tested |
  | AC-D7 | `test_verified_evidence_overrides_the_committed_files_own_self_report` | `test_keystone_detective_greenness.py` | tested |
  | AC-D8 | `test_a_link_absent_from_verified_evidence_is_fail_closed_not_run` | `test_keystone_detective_greenness.py` | tested |
  | AC-D9 | `test_the_same_link_id_under_two_requirements_resolves_independently` | `test_keystone_detective_greenness.py` | tested |
  | AC-D10 | short-circuit assertions embedded in AC-D2/AC-D3 (`_boom` raises if `resolve_execution_evidence` is ever called) | `test_keystone_detective_core.py` | tested |
  | AC-D11 | `test_duplicate_verified_link_ids_within_one_requirement_fail_closed`, `test_a_verified_link_missing_status_or_executed_is_treated_as_absent` | `test_keystone_detective_greenness.py` | tested |
  | AC-D12 | `test_classify_commit_takes_no_parent_argument_and_resolves_it_internally`, `test_a_root_commit_raises_read_error` | `test_keystone_detective_core.py` | tested |
  | AC-D13 | not independently re-tested here (see AC-D13's own entry above) | `shared/tests/test_ci_provenance.py::test_no_record_when_only_pull_request_runs_exist` | tested at resolver boundary |
  | AC-D14 | `test_a_mutable_ref_is_canonicalized_to_a_full_sha_before_any_resolver_call`, `test_an_unresolvable_commit_raises_read_error`, `test_the_canonical_sha_reaches_execution_evidence_and_both_manifest_reads` | `test_keystone_detective_core.py` | tested |
  | AC-D15 | `test_an_unrecognized_verification_status_raises_read_error`, `test_an_unrecognized_evidence_status_raises_read_error` | `test_keystone_detective_core.py` | tested |
  | (mutation contract, `build_verified_manifest`) | `test_build_verified_manifest_does_not_mutate_or_share_state_with_the_input` | `test_keystone_detective_greenness.py` | tested |
  | (fail-closed malformed evidence, PR review Tier-3) | `test_a_non_mapping_requirement_node_is_treated_as_no_verified_evidence`, `test_a_non_mapping_tests_value_is_treated_as_no_verified_evidence`, `test_a_non_mapping_evidence_requirements_is_treated_as_no_verified_evidence`, `test_a_verified_link_missing_status_specifically_is_treated_as_absent` | `test_keystone_detective_greenness.py` | tested |

  None `untestable`. The two files split at build time (346 lines, crossing the 300-LOC
  guideline) along the natural seam: classification/short-circuit vs. greenness-recomputation —
  see the mini-plan's "Files touched". `build_verified_manifest` itself later moved to its own
  module (`_keystone_detective_manifest.py`, §3.5.3) once its fix pushed the combined orchestration
  module past the same guideline.
- **Confidence-pattern check:** asymptote — seven outcomes are exhaustive and mutually exclusive
  by construction (each is a distinct `(verification.status, evidence.status, verdict.any_hard)`
  branch with no overlap); coverage breadth — every branch of `resolve_ci_verification` (4
  statuses) and `resolve_execution_evidence` (3 statuses) that this module's control flow can
  reach is exercised by a fixture, plus the composition-specific findings that are genuinely new
  logic rather than inherited from either resolver (AC-D8 fail-closed substitution, AC-D9
  per-requirement scoping, AC-D11 duplicate-id refusal, AC-D12 first-parent resolution).
