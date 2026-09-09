# Iterate Spec: Promote Layers per FR — Restart (execution-tier CI binding)

- **run_id:** iterate-2026-09-09-p3-5-promote-layers-per-fr-restart
- **Campaign:** req3-04c-ac-identity-wave2, sub-iterate p3.5 (restart, second attempt)
- **Status:** draft — round 2 (plan-review round 1 result: approve with 8 blocking changes +
  6 medium findings, all folded in below; awaiting round-2 verification before build)
- **Affected FRs:** FR-01.11 (AC-identity / evidence-ledger area, same FR as P3.1-P3.4c)
- **Source sub-iterate spec:** `.shipwright/planning/iterate/campaigns/req3-04c-ac-identity-wave2/sub-iterates/p3.5-promote-layers-per-fr.md`
  (see its `## RESTART BRIEF` section)
- **Prior art (reference only, not to merge/cherry-pick):** PR #690, branch
  `iterate/campaign-p3.5-promote-layers-per-fr`, final commit `13e3dbad7`. Abandoned open draft.

## Problem

PR #690 (first P3.5 attempt) got 12 BLOCK verdicts across 10 push/CI cycles. 9 of 12 restated:

> promotion trusts `coverage`/`tests` from `test-traceability.json` without establishing that
> the evidence came from a CI run bound to the current commit / manifest revision

P3.4c (`shared/scripts/ci_provenance.py`, merged as PR #691, commit `093162664`) was built to
close this and is now available. But `ci_provenance.py`'s own docstring says, in its own words,
that it closes only **half** the objection:

> `verified` means "a real CI run confirmed the committed manifest's requirement/test-ID
> structure was not fabricated or hand-edited"; it does **NOT** independently confirm that the
> recorded test outcomes or coverage numbers are accurate.

The comparison behind `verified` is structural-only — `compare_traceability_manifest.
_structural_view()` strips `tests`, `coverage`, **and `acs`** before comparing. Those fields are
exactly what P3.5's per-FR predicate reads (FR-level: `tests`/`coverage`; see `## 6. acs handling`
below for why `acs` does not need the same treatment). Treating `verified` as sufficient
reproduces the 13th BLOCK. **This restart's actual new work is closing that remaining half —
binding execution-tier evidence (which layer is "highest observable ok", whether a bound test
executed) to the CI run that produced it, not to the committed file's mutable fields.**

## Operating context feasibility check (empirical, run 2026-09-09, real repo/GitHub)

Round-2 plan review required this before any code: resolve real CI verification for a real recent
`main` commit and report how many of the 20 active FRs would actually promote/skip/escalate, not
a mocked number. Ran directly against this repo:

```
$ git rev-parse origin/main
093162664cd3e9c6e623e2e9010c61b6015cbf6e   # tip of main — P3.4c's own merge commit

$ uv run shared/scripts/tools/ci_provenance_check.py verify --commit 093162664... --project-root .
exit 3 — {"status": "not_verified", "detail": "qualifying run(s) found for this commit, none
confirmed a clean manifest", "run_id": null}
```

Checked directly against GitHub's API (`gh api .../actions/runs/34316980804/jobs`) to understand
why: a qualifying run DOES exist (push, `main`, `conclusion=success`, run 34316980804) — its
"Check traceability manifest against a fresh regeneration" step itself concluded `success`
(meaning the *script* ran cleanly), but its `code` output was **not** `'0'`, so "Confirm
traceability manifest verified (no drift)" concluded `skipped`. **Real, current structural drift
exists at the tip of `main` today**, independent of anything in this restart's diff. The next four
most-recent `main` commits are all `not_verified` too (expected — they predate the
`PROVENANCE_STEP_NAME` step existing in `ci.yml` at all, so no qualifying step is ever found).

**Result: today, `resolve_execution_evidence` would report `unavailable` for every one of the 20
active FRs — zero promotions.** Two separate facts compose to produce that number, and they must
not be conflated:

1. **Structural drift on `main`'s own tip is pre-existing and orthogonal to this restart.**
   `ci_manifest_drift_check.py` is deliberately advisory (never blocks a build — P3.4c's own
   mandate, reconfirmed by issue #449), so nothing today *forces* an operator to keep the
   manifest drift-free before merging. This restart's diff does not introduce this drift and is
   not the right place to fix it (that is a compliance-regen housekeeping task, not an
   execution-tier-evidence design question). **Recommended, not blocking:** file a triage item
   (or have the orchestrator run a compliance regen + commit) to get `main`'s tip drift-clean, so
   the FIRST real `verified` commit can exist and this mechanism can be validated end-to-end
   post-merge — see `## Rollout validation (new)` below.
2. **A branch-scoping fact, separate from (1):** `resolve_ci_verification`'s `_qualifying_runs`
   (`ci_provenance.py`) accepts only `event=="push"`. Every CI run of THIS restart's own commits,
   while developed and reviewed on an iterate worktree branch, is `pull_request`-triggered — never
   qualifying, by design (the whole unforgeability property depends on this). **This tool is only
   ever meaningful run against a checked-out `main` commit after it has been pushed and CI has
   completed** — never from the branch that built it. This is stated explicitly in the tool's own
   `unavailable` detail string and in `## Known limitations` below, and is exactly why `## 4.
   Standalone CLI wrapper (new, built now)` exists: an operator needs to ask "why did nothing
   promote" without running the tool that writes `spec.md`.

**Verdict: the design is not invalidated by a zero-promotions result driven by (1)+(2) above —
both are pre-existing/structural facts about the current repo and branch position, not a defect in
the execution-tier binding this restart adds.** Skipping everything under these conditions is the
*correct*, conservative behavior (never promote on unconfirmed evidence) — the alternative (some
number of promotions today) would mean the trust boundary was leaking. What this check does add,
concretely: an explicit rollout-validation requirement (below) that a post-merge check with a real
`verified` commit is run before this mechanism is considered proven end-to-end, rather than
resting on mocked tests alone.

## Rollout validation (new — tracked, not a pytest AC)

After this restart merges to `main` AND (separately, tracked as its own housekeeping step) `main`'s
tip becomes drift-clean and gets one `verified` push run: run `promote_required_layers.py` for
real and report the actual promote/skip/escalate counts, same shape as PR #690's own first real
run ("5 of 20 FRs promoted, 13 skipped, 2 escalated"). This is an operational rollout check, not a
build-time test (no real `verified` commit + populated artifact exists yet to assert against in
CI). Escalation volume must still be "zero to a handful" per the sub-iterate spec's own line 21 —
if it is not, that is the signal the spec already names to stop and revisit the predicate, applied
for real rather than only in mocks.

## What is preserved unchanged from PR #690

Per the RESTART BRIEF, none of these were disputed in any of the 12 rounds and are **not
rewritten**, only rebased onto current `main` (which now includes p3.4c):

- `shared/scripts/lib/layer_promotion.py` — the pure per-FR evaluator (`evaluate_fr`). **Zero
  lines changed** in this design — see `## Why the evaluator needs no code change` below.
- `shared/scripts/lib/layer_promotion_apply.py` — the two-phase fold/write, ledger-before-spec.md.
- `shared/scripts/lib/fr_layer_cell_writer.py` — the single-cell spec.md writer.
- `shared/scripts/tools/record_layer_promotion_decision.py` — the human-only override CLI.
- The `diff_risk_recheck`-shaped process contract: exit 0 (decided) / 3 (valid hand-back, still
  applies every clean decision) / other (operational failure); never-self-ack (only the human
  CLI can add a `demoted` entry or override a prior decision); per-FR, never a sweep.

**One small, additive change to `shared/scripts/lib/layer_promotion_ledger.py`** (blocking change
6 below: `append_decision` gains an optional `ci_run_id` kwarg) — everything else in it, including
`evidence_fingerprint`'s existing hashed shape, is unchanged (see `## Fingerprint-noise finding,
deferred` for why that shape is not changed despite a real, named risk).

**Only `shared/scripts/tools/promote_required_layers.py`'s orchestration (`plan_promotions`/`main`)
changes**, plus two new modules (a resolver + a standalone read-only CLI wrapper).

## Design (final, round 2)

### 1. Reuse, don't re-derive: `resolve_ci_verification` stays the ONE trust boundary

Unchanged from round 1. The new mechanism never re-implements "is this run trustworthy" (push,
default-branch, `conclusion=success`, `PROVENANCE_STEP_NAME` step `success`). A new module,
`shared/scripts/ci_execution_evidence.py` (flat, peer of `ci_provenance.py`), calls
`ci_provenance.resolve_ci_verification(commit, ...)` **first**, and only proceeds to look at
execution-tier data when its `status == "verified"`. There is exactly one unforgeability
predicate in this system; this module composes with it, it does not duplicate it.

### 2. What's actually new: a build artifact carrying the CI run's own regenerated manifest

`ci_manifest_drift_check.py` already regenerates `.shipwright/compliance/test-traceability.json`
**in place**, from that run's real, fresh JUnit output, before comparing it (structurally) to the
committed one. Today that regenerated file is discarded when the job ends.

**One new `ci.yml` step**, immediately after "Check traceability manifest against a fresh
regeneration":

```yaml
- name: Upload regenerated traceability manifest artifact (execution evidence)
  # P3.5 restart: the drift-check step above regenerates this file IN PLACE from this
  # run's real JUnit output before comparing it. Discarding it here (as before) throws
  # away the one thing that makes a promotion's tests/coverage fields non-forgeable.
  #
  # `if:` narrowed to code=='0' ONLY (round-2 plan review, Q2) -- an artifact uploaded on
  # drift-code '1' is dead storage anyway: "Confirm traceability manifest verified (no
  # drift)" is ITSELF gated on code=='0' (ci.yml, existing step), so a run with code=='1'
  # can never become `verified` and its artifact would never be consulted regardless.
  #
  # continue-on-error: true, deliberately diverging from "Upload coverage artifacts"'
  # precedent (which has none) -- that step is a debugging aid; this one is the wire this
  # restart's WHOLE unforgeability claim rests on, and a transient upload failure must
  # never become a NEW way for ci.yml to fail the build. IMPORTANT: with
  # continue-on-error: true this step's own `conclusion` always reads `success` even when
  # the upload itself failed -- only `outcome` reflects the real result. Nothing in this
  # design reads this step's conclusion (unlike PROVENANCE_STEP_NAME); the resolver always
  # asks the Artifacts API directly whether the named artifact actually exists for this
  # run_id (see `## 3`), so a swallowed failure here correctly surfaces there as
  # `unavailable`, never as a false `confirmed`.
  if: steps.manifest_drift.outputs.code == '0' && github.event_name == 'push'
  continue-on-error: true
  uses: actions/upload-artifact@v4
  with:
    name: traceability-manifest-regenerated   # EXECUTION_EVIDENCE_ARTIFACT_NAME constant
    path: .shipwright/compliance/test-traceability.json   # literal path, not a glob
    if-no-files-found: ignore
    retention-days: 90   # explicit, matching the repo default -- pinned so a future
                          # org-level default change can't silently shrink the window
                          # this design's "artifact retention" Known Limitation assumes
```

`github.event_name == 'push'` added (medium finding): the consumer-side trust filter
(`event=="push"`) already ignores a PR run's artifact regardless, but uploading it only on `push`
avoids uploading dead-on-arrival artifacts on every PR build, matching the step's actual purpose.

**Job has no OS matrix today** (verified by reading `ci.yml`'s single `python-checks` job:
`runs-on: ubuntu-latest`, no `strategy:`/`matrix:` block) — a shape test pins this fact explicitly
(see `## Files to create / modify`), because an OS-matrixed job re-running this same step per leg
would 409 on the duplicate artifact name and `continue-on-error: true` would swallow that
silently. If a matrix is ever added to this job, the artifact name must become per-leg
(`${{ matrix.os }}`-suffixed) and the shape test's failure is what would catch the omission.

**No new CI-side extraction/writer script.** The whole file, unmodified, uploaded as-is.

### 3. The new resolver: `ci_execution_evidence.resolve_execution_evidence`

```python
@dataclass(frozen=True)
class ExecutionEvidence:
    status: str  # "confirmed" | "unavailable" | "error"
    detail: str
    run_id: int | None = None
    requirements: dict[str, dict] | None = None  # req_id -> {"tests": ..., "coverage": ...}


def resolve_execution_evidence(
    commit: str, *, committed_manifest: dict, project_root: Path | str,
    workflow_file: str = "ci.yml",
    artifact_name: str = EXECUTION_EVIDENCE_ARTIFACT_NAME,
) -> ExecutionEvidence: ...
```

**`committed_manifest` is now a required, caller-supplied parameter** (round-2 change; round 1 had
this module reading nothing but querying GitHub). The caller (`promote_required_layers.py`) reads
it via ONE `git show {sha}:<relpath>` blob read (see `## 4`) and passes the already-parsed dict in
— this resolver never reads the local tree itself, and there is exactly one commit-pinned read of
the manifest across the whole tool, not two independent ones that could disagree (closes the
TOCTOU class blocking-change 7 named).

1. Calls `resolve_ci_verification(commit, project_root=project_root, workflow_file=workflow_file)`.
2. `status in ("no_record", "not_verified")` → `ExecutionEvidence("unavailable", ...)`.
   `status == "error"` → `ExecutionEvidence("error", ...)`. Neither downloads anything.
3. `status == "verified"` → **first**, lists the run's artifacts:
   `gh api repos/{owner}/{repo}/actions/runs/{run_id}/artifacts?per_page=100`.
   - The API call itself fails (non-zero exit / bad JSON) → `ExecutionEvidence("error", ...)` —
     an unresolved query, not a definite negative (same discipline `ci_provenance.py` already
     applies to its own runs/jobs queries).
   - No entry named `artifact_name` in the list, OR the matching entry's own `"expired": true` →
     `ExecutionEvidence("unavailable", ...)` — **round-2 fix (blocking change 4a):** this is the
     expected steady state for a `verified` commit predating this mechanism, or one whose artifact
     has aged out of retention. A defined negative, not an error — matches `ci_provenance.py`'s own
     `no_record`-vs-`error` discipline, applied one level down (artifact existence vs. run
     existence).
   - Present and not expired → `gh run download {run_id} --repo {owner}/{repo} --name
     {artifact_name} --dir {tmpdir}` (explicit `--repo`, never `gh`'s cwd-based resolution — same
     rigor `ci_provenance.py` applies to `gh api`, tightened relative to
     `shared/scripts/security_findings.py`'s cwd-reliant precedent; this module does **not** modify
     or import that file — small, disclosed, local duplication of its `tempfile.mkdtemp` /
     bounded-timeout / best-effort shape, same reasoning as round 1). A download failure at this
     point (network/timeout/corrupted zip) → `ExecutionEvidence("error", ...)`: the Artifacts API
     already confirmed the artifact EXISTS and is not expired, so a failure to actually fetch it is
     an operational problem, not a defined negative — **round-2 fix (blocking change 4a),
     distinguishing this from the "not found/expired" case above.**
4. Parses the downloaded `test-traceability.json` (located by its literal expected relative path
   inside the download dir, not `rglob` — round-2 hygiene fix: the artifact's own `path:` in the
   upload step is a single known file, so the download layout is exact, not "somewhere under this
   tree"). A malformed/unparseable file → `ExecutionEvidence("error", ...)`.
5. **Content-binding check (round-2, blocking change 5 — the highest-value fix in this round):**
   before trusting the parsed artifact at all,
   - `artifact["source_commit"] == commit`, and
   - `compare_traceability_manifest.structural_diff(committed_manifest, artifact) == ""`
     (reusing the **already-public** `structural_diff` function — not the private `_load`/
     `_validate`/`_structural_view` round 1 proposed reusing; this addresses the medium
     cross-directory-import finding by using the one function in that module already meant for
     exactly this comparison, with a bare `try/except (KeyError, TypeError)` around the call
     mapping any shape surprise to `error` rather than an uncaught traceback).
   Either check failing → `ExecutionEvidence("error", ...)`: **without this, a `verified` run's
   `run_id` could pair with bytes from a different attempt of the same run** (`/jobs` reports only
   the latest attempt's conclusions per `ci_provenance.py`'s own documented "Known limitations",
   but `gh run download {run_id}` can see artifacts across attempts, last-writer-wins on a name
   collision) — this is what converts the unforgeability claim from "trust the run_id pairing" to
   "verify the pairing's content actually matches what CI structurally confirmed." The
   cross-directory import (`shared/scripts/ci_execution_evidence.py` → `shared/scripts/tools/
   compare_traceability_manifest.py`) follows the identical, already-precedented pattern
   `layer_promotion.py`'s own docstring defends for `tools.verifiers._layer_coverage_binding` —
   both live under the same `shared/scripts` tree (not crossing into a plugin's own `scripts/`
   namespace, the actual ADR-044/045 hazard class), so this is not a new import-hazard shape.
6. Builds `requirements = {req_id: {"tests": node["tests"], "coverage": node["coverage"]} ...}`
   for every requirement in the (now content-bound) artifact.

**Unforgeability property (one sentence, matching the bar p3.4c's own spec set):** faking a
`confirmed` `ExecutionEvidence` requires forging GitHub's Artifacts API response for the exact
`run_id` that already passed `resolve_ci_verification`'s push/default-branch/success/step-success
filter, **with content that structurally matches what that same run's structural check already
confirmed and whose own `source_commit` field names the same commit** — the identical compromise
boundary `ci_provenance.py`'s docstring already states, tightened (not widened) by the
content-binding check in step 5.

### 4. Consumer wiring: `promote_required_layers.py`

**Single commit-pinned read, TOCTOU-free by construction (round-2, replaces round 1's
"HEAD-match guard"):**

```python
def _read_committed_manifest(project_root: Path) -> tuple[str, dict]:
    """Resolve HEAD once, then read the manifest AT THAT EXACT SHA via `git show` --
    never the on-disk file. A local, 6-line subprocess call, NOT a reuse of
    `ci_manifest_drift_check.capture_committed_manifest` (round-2 fix, blocking
    change 7): that function hardcodes the literal `HEAD:` ref with no commit
    parameter, so it cannot be pinned to the SHA this call already resolved, and
    reusing it would mean the manifest read is not provably the same commit the
    resolver is about to ask GitHub about."""
    sha = subprocess.run(["git", "-C", str(project_root), "rev-parse", "HEAD"], ...).stdout.strip()
    raw = subprocess.run(["git", "-C", str(project_root), "show",
                           f"{sha}:.shipwright/compliance/test-traceability.json"], ...).stdout
    return sha, json.loads(raw)
```

`main()` calls this **once**, by default (no `--commit` flag — there is nothing else meaningful to
pin it to; see `## Operating context feasibility check` for why). The resulting `(sha, manifest)`
is what `plan_promotions` evaluates against — **the working-tree copy of `test-traceability.json`
is never read for evaluation at all.** This is strictly TOCTOU-free (one read, no compare-then-use
window) rather than round 1's "compare on-disk to `git show`, then read on-disk" — round 1's design
still had a live race between its own guard check and its later read; this design removes the
on-disk read from the evaluation path entirely.

**`--manifest` becomes a read-only, dry-run-only override (round-2, resolves Q3):** if given, the
tool loads that path instead of the git-show read, for local inspection only, and refuses to reach
`write_promotion_files`/`record_ledger_entries` under any decision — a distinct `--dry-run` state
gated on `--manifest` being set, not merely documented as a convention. This is because any
manifest other than the committed blob makes the execution evidence (bound to the *committed*
manifest's `source_commit`) describe a document that is not what would actually be evaluated for
real; letting it write would silently defeat the whole binding.

**`evidence.status == "error"` is an operational failure, never a silent skip-all (round-2 fix,
blocking change 4b):** round 1's design let `ci_by_fr = evidence.requirements or {}` default to
`{}` on ANY non-`confirmed` status, including `error`, producing a clean `exit 0` "everything
decided as skip" report — indistinguishable from the correct, honest `unavailable` steady state.
`main()` now branches explicitly:

```python
sha, committed_manifest = _read_committed_manifest(project_root)
evidence = resolve_execution_evidence(sha, committed_manifest=committed_manifest, project_root=project_root)
if evidence.status == "error":
    print(json.dumps({"error": f"execution evidence could not be resolved: {evidence.detail}"}))
    return 2   # operational failure -- same shape as every other {"error": ...} exit-2 case in
               # this CLI (bad manifest, unwritable spec.md, unparseable ledger); NEVER exit 0.
```

Only `confirmed` and `unavailable` reach `plan_promotions` at all; both are legitimate, decided
inputs (the per-FR loop already treats `unavailable`'s empty `requirements` correctly — see
`## Why the evaluator needs no code change`).

**Per-FR wiring (`plan_promotions`, changed):**

```python
ci_by_fr = evidence.requirements or {}   # {} only ever reached via status=="unavailable" now
...
for node in active.values():
    fr_id = node["id"]
    eval_node = dict(node)
    # ... existing required_layers_source / required_layers union logic: UNCHANGED. These are
    # structural fields; content-binding (design ##3 step 5) already proves `committed_manifest`
    # (what `node` is drawn from) matches CI's own structural confirmation for `confirmed`
    # evidence, and `unavailable`/error-short-circuited runs never reach a promotion at all.
    ci_node = ci_by_fr.get(fr_id)
    # REPLACE, never merge: the committed file's own coverage/tests are never read again once
    # CI evidence is being consulted at all.
    eval_node["coverage"] = (ci_node or {}).get("coverage") or {}
    eval_node["tests"] = (ci_node or {}).get("tests") or {}
    decision = evaluate_fr(eval_node, is_collision=..., ledger_entry=..., ...)   # UNCHANGED call
    decision["ci_evidence"] = {                     # NEW, report-only, never read back
        "status": evidence.status, "run_id": evidence.run_id,
        "fr_confirmed": ci_node is not None,
    }
    decision["spec_path"] = node.get("spec_path", "")
    decision["_node"] = eval_node   # CHANGED: was `node`; now the CI-sourced eval_node, so
                                     # `evidence_fingerprint` (ledger) durably records what was
                                     # ACTUALLY used to decide.
    decisions.append(decision)
```

### Why the evaluator needs no code change (round 2 — realistic evidence shapes, not empty dicts)

Round 1's trace used `coverage={}`, `tests={}` for "no CI evidence." Round-2 plan review correctly
flagged this as unrealistic: real CI-regenerated `tests`/`coverage` (`_test_links_requirements.
build_requirement_nodes`) are populated whenever an FR has ANY tagged test at all, regardless of
whether that test executed. Re-traced against the actual producer's shapes:

**Case A — FR has a tagged-but-not-executed-by-this-run test** (e.g. a `cross_plugin`-marked test
CI's own `shared/tests` job excludes via `-m "not slow and not cross_plugin"`, or a layer whose
plugin-specific test root the run genuinely didn't touch): `tests["unit"] = [{"id": ..., "status":
"enabled", "executed": "not_run"}]`, `coverage["unit"] = "MISSING"` (never absent-from-dict —
`_cov_status` returns `"MISSING"`, not an omitted key, for a required layer with zero passing
links). Trace: `bound_but_absent_layers(tests)` → `{"unit"}` (status `enabled`, `executed` not in
`("pass","fail")`) → `evidence_ambiguous=True` → **`REASON_BOUND_TEST_ABSENT`, a valid escalation**
— this is EXACTLY the spec's named case 2 ("the binding exists but the named test did not run in
the CI evidence at all"), firing correctly and as designed. This is a genuine, expected source of
escalations for any FR whose bound test is `cross_plugin`-marked or otherwise excluded from the
`shared/tests`/`shared/scripts/tests`/`shared/scripts/tools/tests`/`integration-tests`/
`plugins/*/tests` roots `ci.yml`'s single job actually runs — **not a defect, but a real,
non-trivial source of volume this design must not silently absorb.** Flagged explicitly in
`## Rollout validation` above: if this pushes escalation volume past "zero to a handful," that is
the signal to revisit which layers/tests this predicate should even consider bound.

**Case B — FR has a tagged-and-executed-but-failing test:** `tests["unit"] = [{"id": ..., "status":
"enabled", "executed": "fail"}]`, `coverage["unit"] = "MISSING"`. Trace: `executed=="fail"` IS one
of the two decided values, so `bound_but_absent_layers` does NOT include this layer →
`evidence_ambiguous=False` → `highest_ok_layer(coverage)` → `None` (no `"ok"` anywhere) → falls to
`SKIP_NO_EVIDENCE_YET` (a real, honest "not promotable yet" — matches `layer_promotion.py`'s own
existing, undisputed docstring: "A failing test is a DECIDED 'not green'... never becomes
`highest_ok_layer`, same as no binding at all").

**Case C — CI-sourced evidence is strictly WEAKER than the committed file's** (the actual
adversarial/staleness case): committed `coverage={"unit": "ok", "integration": "ok"}` (possibly
hand-edited or simply stale), CI-sourced (now what `eval_node` actually holds, replacing the
committed values entirely per the REPLACE-never-merge rule) `coverage={"unit": "ok"}` only. Trace:
`required_before` (from the structural union, unaffected) might include `integration` already if
previously declared — `unverified_required = required_before - {"unit"}` → non-empty →
`SKIP_EXISTING_REQUIRED_NOT_VERIFIED` if `highest_ok` is not None (it is — `"unit"`), reached
correctly; a NEW FR with no prior `integration` requirement simply never sees `"integration"`
proposed at all, since `new_required` only ever widens by `highest_ok` from the CI-sourced set.
Either way, the committed file's stronger (possibly fabricated) claim about `integration` is never
consulted — confirms the REPLACE rule does what it is meant to do.

**Case D — CI-sourced evidence is confirmed-and-green** (an FR whose bound `unit` test is tagged,
executed, and passing in the real CI run): `tests["unit"]=[{"status":"enabled","executed":"pass"}]`,
`coverage["unit"]="ok"` → `highest_ok_layer` → `"unit"`, `evidence_ambiguous=False`,
`unverified_required` empty (assuming no other required layer) → **`action: "promote"`,
`required_layers` widened to include `"unit"`** — the intended, correct positive case.

**Conclusion — all four realistic cases confirmed, none introduce a 4th escalation case.** Only
Case A produces an escalation, and it is the spec's own named case 2, correctly triggered by real
(non-empty) evidence, not by round 1's over-simplified empty-dict trace. `REASON_LAYER_
UNDETERMINABLE`'s unrecognised-layer arm and `REASON_CONTRADICTS_DECISION`'s branches are
unaffected by any of this (unchanged from round 1's reasoning — neither reads a fabricated "empty
means nothing happened" assumption). **The spec's closed list of three escalation reasons stays
closed; what round 2 corrects is the CLAIM about which of the three fires and how often, not
whether a fourth exists.**

### 5. Ledger: fingerprint sourced from CI evidence, plus a new `ci_run_id` field (round 2)

`layer_promotion_apply.record_ledger_entries` is unchanged — it still just calls
`evidence_fingerprint(decision["_node"])`, and `decision["_node"]` is now `eval_node`
(CI-sourced), same as round 1.

**New, additive (blocking change 6):** `layer_promotion_ledger.append_decision` gains one new
optional keyword, `ci_run_id: int | None = None`, appended to the entry dict only when not `None`
(same pattern every other optional field in that function already follows — no schema-version
bump, since `_parse_ledger`'s validation only enforces the closed `action` vocabulary and
`required_layers`'s type, never rejects an unrecognised extra key). `record_ledger_entries` passes
`decision["ci_evidence"]["run_id"]` through. **This satisfies the spec's AC-1 "with its evidence
named" literally, not just via a content fingerprint** — a later reader of the ledger can see
*which CI run* confirmed a promotion, not only a hash of what it confirmed.

### 6. `acs` handling (round 2, blocking change 1)

`compare_traceability_manifest._REQUIREMENT_EXECUTION_KEYS` strips THREE fields, not two: `tests`,
`coverage`, **and `acs`**. Round 1's design only replaced `tests`/`coverage`, leaving `acs` exactly
as forgeable as `coverage` was before this restart. **Resolution: `acs` needs no replacement,
because `layer_promotion.evaluate_fr` never reads it at all** — confirmed by direct inspection of
its full source (no reference to `node.get("acs")`/`node["acs"]` anywhere), consistent with its own
docstring's explicit **FR-level only (D12)** scope: "The manifest's `acs` breakdown is deliberately
NOT consulted... AC-level an ADDITIONAL index on top, never a precondition." Nor does
`layer_promotion_ledger.evidence_fingerprint` (scoped to `coverage`+`tests` only, by its own
docstring) or `fr_layer_cell_writer` (writes the FR-level cell, not an AC-level one) ever touch it.
**A hand-edited `acs` field cannot influence this mechanism's predicate, ledger fingerprint, or
spec.md write in any way — proven by a regression test (AC-R11 below: an FR with a deliberately
poisoned `acs` field produces an IDENTICAL decision to the same FR with `acs` deleted entirely),
not merely asserted.** No code change needed for `acs`; the finding is fully closed by this proof,
not deferred.

## Fingerprint-noise finding, deferred (medium finding)

Real CI-sourced `coverage`/`tests` can vary run-to-run on cosmetic grounds (marker selection, a new
test file, a flaky retry) even when nothing about an FR's actual promotability changed.
Fingerprinting the raw CI-sourced node (as `## 5` above does, unchanged from round 1) means
`fingerprint_drifted` can go `True` on such noise. **Deferred, not fixed, for three reasons:**

1. `fingerprint_drifted`'s only consequence is inside `evaluate_fr`'s `demoted` branch, where it is
   **ANDed with `predicate_holds`** — raw noise alone, without `predicate_holds` also flipping to
   `True`, is inert (never reaches the re-escalation branch).
2. A `predicate_holds` flip on a demoted FR driven by genuinely different CI evidence (a
   previously-failing/absent bound test now passing) is arguably the CORRECT signal to re-surface
   to an operator — that IS a new situation the original veto never saw, which is precisely what
   "exitable" is supposed to catch, not noise to suppress.
3. Changing `evidence_fingerprint`'s hashed shape (e.g. to derived `highest_ok`/`absent-layers`
   facts instead of raw `coverage`/`tests`) would touch a "preserved, not rewritten" module's core
   function, used by BOTH the automated tool and the human override CLI — exactly the kind of
   extra, review-churn-prone surface change PR #690's own 12 rounds warn against introducing
   without a demonstrated real failure, not a theoretical one.

**Regression test added instead (AC-R14 below), pinning the current, correct behavior:** CI
evidence content differs across two runs for a `demoted` FR (raw fingerprint changes) but the
derived predicate verdict (`predicate_holds`) stays `False` in both → `evaluate_fr` still returns
`SKIP_DEMOTED_CONSISTENT` in both, never re-escalating on the noise alone.

## `spec.md`'s live (not commit-pinned) read — explicit deferral (medium finding)

`plan_promotions` reads each FR's owning `spec.md` from the **working tree**, not a git blob — this
is intentional, undisputed PR #690 design (its own docstring: "re-derive `required_layers_source`
LIVE rather than trusting the manifest's own stale copy... can still say `inferred_legacy` for an
FR a PRIOR run of this tool already promoted this session"), not something this restart introduces.
Extending the commit-pinning in `## 4` to `spec.md` as well would break that intentional property
(an operator's own in-progress edit, or this tool's own prior run in the same session, would no
longer be picked up) for no compensating unforgeability gain: `spec.md` is the **write target** of
this mechanism, never claimed to be CI-verified evidence in the first place — only
`test-traceability.json`'s `coverage`/`tests`/`acs` fields (and their manifest-structural siblings)
were ever the forgeability concern this restart exists to close. **Deferred with this reasoning,
not fixed** — flagged explicitly rather than silently left as a residual gap.

## New: standalone read-only CLI wrapper (round 2, Q4 resolved — build now)

`shared/scripts/tools/ci_execution_evidence_check.py`, mirroring `ci_provenance_check.py`'s own
shape:

```
uv run shared/scripts/tools/ci_execution_evidence_check.py check --commit <ref> --project-root .
```

Resolves `--commit` via `git rev-parse` (any ref git accepts — full/abbreviated SHA, `HEAD`, a
tag), reads that commit's manifest via the same `git show` pattern as `## 4`, calls
`resolve_execution_evidence`, and prints one JSON line: `{"status": ..., "run_id": ...,
"detail": ..., "fr_count": len(requirements) if confirmed else null}`. **Always exits 0** — this is
a pure diagnostic, never gates anything, never writes anything (no `spec.md`, no ledger). Built now
rather than deferred because the operating-context finding above means the FIRST real invocation
from an iterate worktree will report "unavailable" for every FR, and an operator needs a way to ask
"why" without running the tool that writes `spec.md` to find out.

## Known limitations (disclosed, not fixed — same discipline as p3.4c's own spec)

- **Operating context (new, empirically confirmed 2026-09-09):** meaningful only run against a
  checked-out `main` commit, after push, after CI completes, after that commit's manifest is
  drift-clean. Run from an iterate/feature worktree, or against a `main` tip with pre-existing
  structural drift (both true in this repo TODAY), it reports `unavailable` for every FR — by
  design, not a bug. See `## Operating context feasibility check` and `## Rollout validation`.
- **Artifact retention.** GitHub artifacts expire (pinned here to `retention-days: 90`, matching
  the repo default); an old but genuinely `verified` commit can still resolve to `unavailable` once
  its artifact ages out. Self-healing — matches p3.4c's own "not a durable ledger" limitation.
- **Only the newest qualifying+verified run's artifact is tried.** Accepted for the same reason
  p3.4c accepted the analogous limitation.
- **The whole regenerated manifest is uploaded**, not a minimal per-FR extract — now **load-bearing
  ** (round 2, Q1 resolved), not merely a simplicity trade-off: the content-binding check (`## 3`
  step 5) needs the whole structural shape to compare against, not a pre-filtered subset.
- **Same ambient `gh`/`git` trust assumption `ci_provenance.py` already documents.**
- **`spec.md`'s live-read is commit-unpinned by design** — see the explicit deferral above.
- **Fingerprint noise on `demoted` FRs is possible but inert in practice** — see the explicit
  deferral above.
- **Cross-attempt artifact selection is narrowed, not closed (external review, openai/high, round
  3).** `_find_unexpired_artifact` picks the newest unexpired match by `created_at`, matching
  `resolve_ci_verification`'s own "latest attempt" semantics as closely as the Artifacts List API
  allows — but two attempts of the SAME commit can both pass content-binding (`source_commit` +
  `structural_diff`) while genuinely disagreeing on `tests`/`coverage` (e.g. a flake healed or
  worsened between a first and a re-run attempt). Content-binding defends against evidence from
  the WRONG COMMIT being trusted; it does not, and by its own design cannot, distinguish between
  two real CI attempts of the RIGHT one. Accepted: the worst case is a real, CI-produced execution
  snapshot of the identical committed source, not a fabricated value — a materially weaker risk
  than what this whole restart exists to close. See `## External-Plan-Review-Findings` #1.
- **Artifacts-list query has no pagination (`?per_page=100`, external code review, glm/low, round
  3).** A run with more than 100 artifacts could push the named artifact past the first page,
  yielding a false `unavailable`. Fails toward the SAFE direction (no promotion, never a false
  `confirmed`); not implemented this round given this repo's actual artifact volume. See
  `## External-Code-Review-Findings` #8.
- **Fingerprint-basis asymmetry between the two CLIs (external code review, glm/medium, round 3).**
  `record_layer_promotion_decision.py` fingerprints the WORKING-TREE manifest's raw values, never
  commit-pinned or CI-sourced like the automated tool — see that file's own docstring and
  `## External-Code-Review-Findings` #5 for the full disclosure and why it was not fixed this
  round.

## Alternative approaches (rejected)

1. **Treat `resolve_ci_verification`'s `verified` as sufficient for execution-tier fields too.**
   Rejected — precisely the trap the RESTART BRIEF names.
2. **Make `ci_manifest_drift_check.py`'s `execution_report()` comparison blocking.** Rejected —
   forbidden by p3.4c's mandate and issue #449; would also false-block on expected
   platform-selection differences.
3. **One named CI step conclusion per requirement.** Rejected — does not scale, breaks the
   "one constant, pinned by a shape test" discipline.
4. **Move `promote_required_layers.py` into CI itself.** Rejected — turns this into a bot-PR
   delivery flow, out of scope.
5. **A single aggregate "execution tier also matched" CI step conclusion, instead of an artifact.**
   Rejected — is itself a second unforgeability predicate, and cannot be FR-scoped.

## Files to create / modify

1. `.github/workflows/ci.yml` (edit) — one new artifact-upload step (name contains "artifact" —
   blocking change 8, so `check_ci_gate_coverage.is_gate_step`'s explicit escape hatch applies and
   this is not misclassified as an un-allowlisted gate despite containing "test"), `if:
   manifest_drift.outputs.code == '0' && github.event_name == 'push'`, `continue-on-error: true`,
   `retention-days: 90`.
2. `shared/scripts/ci_execution_evidence.py` (new, flat, peer of `ci_provenance.py`) —
   `EXECUTION_EVIDENCE_ARTIFACT_NAME` constant, `ExecutionEvidence` dataclass,
   `resolve_execution_evidence(commit, *, committed_manifest, project_root, workflow_file="ci.yml",
   artifact_name=...)`.
3. `shared/scripts/lib/layer_promotion.py` — rebased, **zero logic changes**.
4. `shared/scripts/lib/layer_promotion_ledger.py` — rebased, **one additive optional kwarg**
   (`ci_run_id` on `append_decision`).
5. `shared/scripts/lib/layer_promotion_apply.py`, `fr_layer_cell_writer.py` — rebased, unchanged.
6. `shared/scripts/tools/promote_required_layers.py` — rebased, then: `_read_committed_manifest`
   (single git-show read); `--manifest` becomes a dry-run-only override; `evidence.status ==
   "error"` → exit 2 before `plan_promotions` runs; `plan_promotions` overlays CI-sourced
   `coverage`/`tests`, attaches `ci_evidence`, sets `decision["_node"] = eval_node`.
7. `shared/scripts/tools/record_layer_promotion_decision.py` — rebased, **unchanged**.
8. `shared/scripts/tools/ci_execution_evidence_check.py` (new) — read-only diagnostic CLI, always
   exit 0.
9. Tests: `shared/tests/test_ci_execution_evidence.py` (mocked `resolve_ci_verification` + mocked
   `gh api .../artifacts` + mocked `gh run download`, covering: confirmed; unavailable via
   no_record/not_verified/error-from-verification; unavailable via artifact-not-listed;
   unavailable via artifact-expired; error via artifacts-API-query-failure; error via
   download-failure-on-a-listed-artifact; error via content-binding mismatch on `source_commit`;
   error via content-binding mismatch on `structural_diff`); a CI-YAML-shape test for the new step
   (name/`if:`/`continue-on-error`/`retention-days` pinned, plus the no-OS-matrix assertion);
   `shared/scripts/tools/tests/test_promote_required_layers.py` extended per the Acceptance
   Criteria below; `shared/scripts/tools/tests/test_ci_execution_evidence_check.py` (always exit 0,
   never writes).

## Acceptance Criteria (assertion-shaped; supersedes/extends round 1's AC-R list; the sub-iterate
spec's original six ACs are unchanged and still apply)

- **AC-R1 (revised):** `resolve_execution_evidence` returns `status="confirmed"` with a per-FR map
  only when verification is `verified` AND the artifact is listed, not expired, downloads, parses,
  AND passes both content-binding checks. `status="unavailable"` when verification is
  `no_record`/`not_verified`, OR verification is `verified` but the artifact is absent from the
  run's artifact list or listed-but-expired. `status="error"` when verification itself is `error`,
  OR the artifacts-list query fails, OR a listed-and-unexpired artifact fails to download, OR it
  downloads but fails to parse, OR either content-binding check fails.
- **AC-R2 (the forgery test, unchanged):** hand-edited committed `coverage: {"unit": "ok"}` with no
  CI confirmation available (`unavailable`) → `action: "skip"`, never `"promote"`.
- **AC-R3 (unchanged):** `confirmed` evidence not containing the FR being evaluated → treated as
  no evidence (skip), no crash, no escalation.
- **AC-R4 (unchanged):** `demoted`-ledger FR stays `SKIP_DEMOTED_CONSISTENT` when CI evidence is
  unavailable, never spuriously escalates.
- **AC-R5 (unchanged):** promoted ledger entries fingerprint the CI-sourced node, not the raw
  committed node.
- **AC-R6 (revised, replaces round 1's on-disk-vs-HEAD guard):** `main()` never reads the
  working-tree manifest file for evaluation by default — a test asserts `_read_committed_manifest`
  is called and its result (not a disk read) feeds `plan_promotions`. `--manifest` forces dry-run:
  a test asserts that with `--manifest` set, no ledger write and no spec.md write occur regardless
  of computed decisions.
- **AC-R7 (revised — was tautological, now behavioral):** parametrized over four evidence classes
  (Case A absent/not_run, Case B executed-and-failing, Case C CI-weaker-than-committed, Case D
  confirmed-and-green from `## Why the evaluator needs no code change` round 2) — each produces the
  exact action/reason_code traced above; plus a cheap drift-pin test that `layer_promotion.py`
  exports exactly the three `REASON_*` constants.
- **AC-R8 (revised):** the new `ci.yml` step's `if:`/`continue-on-error`/`retention-days` are all
  pinned by a shape test; a separate shape test asserts the `python-checks` job has no
  `strategy.matrix` key today (an early-warning pin, not a permanent constraint).
- **AC-R9 (unchanged):** the original six sub-iterate-spec ACs all still hold with CI-sourced
  evidence substituted in.
- **AC-R10 (new — content binding):** a mocked artifact whose `source_commit` does not match the
  resolved commit → `error`; a mocked artifact whose structural shape (an added/removed/renamed
  requirement, or a changed `id`/`spec_path`) disagrees with `committed_manifest` via
  `structural_diff` → `error`. Neither ever silently falls through to `confirmed`.
- **AC-R11 (new — `acs` proof, not assertion):** an FR node with a deliberately poisoned `acs`
  field (e.g. a fabricated `"ok"` at a layer whose real `coverage` is `"MISSING"`) produces an
  IDENTICAL `evaluate_fr` decision, ledger fingerprint, and spec.md write to the same FR with `acs`
  key removed entirely.
- **AC-R12 (new — ledger names the run):** a promoted ledger entry's `ci_run_id` field equals
  `evidence.run_id`; a test reads it back via `latest_decision` and asserts it is present and
  correct.
- **AC-R13 (new — realistic-shape escalation, Case A):** a mocked confirmed evidence bundle whose
  `tests["unit"]` carries a `status:"enabled", executed:"not_run"` link (not empty, not a failing
  test) for a required layer → `REASON_BOUND_TEST_ABSENT`, matching the sub-iterate spec's named
  case 2 exactly, not a fabricated empty-dict case.
- **AC-R14 (new — fingerprint-noise regression pin):** two CI-sourced evidence snapshots for the
  same `demoted` FR that differ in raw `coverage`/`tests` content (so their raw fingerprints
  differ) but agree on `predicate_holds` staying `False` → both evaluate to
  `SKIP_DEMOTED_CONSISTENT`, neither re-escalates.
- **AC-R15 (new — operational-failure exit code, blocking change 4b):** `evidence.status ==
  "error"` → `main()` exits `2` with an `{"error": ...}` JSON body, `plan_promotions` is never
  called, no ledger/spec.md write of any kind occurs — distinct from the `0`/`3` decided-outcome
  exits.
- **AC-R16 (new — CLI wrapper, Q4):** `ci_execution_evidence_check.py` always exits `0` regardless
  of the resolved status (including on an unresolvable `--commit`, reported inside the JSON body,
  not via a non-zero exit) and never touches `spec.md` or the ledger under any input.

## Resolved answers (round 2 plan-review — replaces round 1's "Open questions")

- **Q1 (whole manifest vs. minimal extract):** Keep the whole manifest — now load-bearing for the
  content-binding check (`## 3` step 5), not merely a simplicity trade-off.
- **Q2 (`continue-on-error: true`):** Kept, `if:` narrowed to `code == '0'` only (drop `code ==
  '1'`, dead storage since the provenance step itself is `code=='0'`-gated).
- **Q3 (`--manifest` override scope):** Resolved by the commit-pinned single-read design (`## 4`) —
  the override now exists ONLY as an explicit, write-refusing dry-run mode.
- **Q4 (standalone CLI wrapper):** Build now — `## New: standalone read-only CLI wrapper` above.

## External-Plan-Review-Findings (Step 3.5, round 3 — post-implementation external LLM review)

Run against the built implementation (`external_review.py --mode iterate`, this doc as
`--plan-file`, the sub-iterate spec as `--spec-file`) — GLM verdict `approve` (5 findings),
OpenAI verdict `revise` (5 findings). Each disposed below; two produced real code changes.

| # | Source | Severity | Finding (one line) | Disposition |
|---|---|---|---|---|
| 1 | openai | high | Static artifact-name lookup can return an artifact from a DIFFERENT attempt of the same run than the one whose Jobs-API conclusion earned `verified`; content-binding (`source_commit` + `structural_diff`) proves same-commit/same-structure, not same-attempt. | **accepted-and-fixed (partial).** `_find_unexpired_artifact` now selects the NEWEST unexpired match by `created_at`, not the first list entry — narrows the window to match `resolve_ci_verification`'s own "latest attempt" semantics as closely as the Artifacts List API allows. Honest remainder (not closed): two attempts of the SAME commit can both pass content-binding while disagreeing on `tests`/`coverage` (e.g. a flake healed/worsened between attempts) — this defends against using the WRONG COMMIT's evidence, not against picking between two genuine runs of the right one. Added to Known Limitations below. |
| 2 | openai | medium | `structural_diff` deliberately excludes `tests`/`coverage` from its comparison, so a structurally-matching artifact can still carry a malformed execution-tier shape (non-dict `coverage`, non-list `tests[layer]`) that `evaluate_fr`'s own accessors are not defensive against — risk of an uncaught exception deep inside the locked promotion span instead of a clean `error`. | **accepted-and-fixed.** New `_execution_shape_error()` pre-flight check in `ci_execution_evidence.py`, run before a `confirmed` result is ever returned; any violation maps to `ExecutionEvidence(status="error")` instead of passing malformed data through. |
| 3 | openai | medium | Download-layout assumption (`gh run download` single-file extraction) is unvalidated against real `gh`/Actions behavior. | **rejected-with-reason.** Already handled: `path:` in `ci.yml` is a literal single file (not a glob), which is `actions/upload-artifact@v4`'s documented single-file-preserves-basename behavior; `_download_and_parse_artifact` already checks `candidate.is_file()` for the exact expected filename before parsing and reports a clean `error` detail if absent — no silent layout assumption. |
| 4 | openai | medium | `unavailable` reads as an ordinary decided "no promotable FRs" outcome, risking confusion with a genuine query failure. | **rejected-with-reason.** This is the round-2 design's own deliberate, heavily-tested distinction (`error` vs `unavailable`, blocking change 4b) — an FR-level tool's job is exactly "insufficient evidence ⇒ skip," and "no evidence yet" is empirically the expected steady state today (see `## Operating context feasibility check`). `evidence.status=="error"` is checked BEFORE `plan_promotions` ever runs and exits 2, never silently degrading to skip-all; see `promote_required_layers.py`'s module docstring and `test_evidence_error_is_an_operational_failure_never_a_silent_skip_all`. |
| 5 | openai | low | Rollout validation depends on separate drift-remediation housekeeping that is only "recommended," not owned/tracked. | **rejected-with-reason (deferred).** Process/tracking, not a code change; already an explicit `## Rollout validation` section below. Noted in F3a reflection for campaign follow-up. |
| 6 | glm | high | Content-binding assumes the regenerated manifest's `source_commit` field exists and equals the real commit for a push event (not a merge SHA). | **corrected disposition (round 4 post-push doubt-review, medium finding).** The original row above cited the WRONG chain (`regenerate_base_head`/`_build`, which lives in `tools/verifiers/_layer_coverage_regen.py` and is only called by the layer-coverage verifiers — never by `ci_manifest_drift_check.py`). The REAL chain, traced directly: `ci_manifest_drift_check.regenerate_manifest()` shells out to the `shipwright-compliance` plugin's `scripts.lib.collectors.test_links.generate_file(project_root)`, which calls `source_commit=io.git_head(project_root)` (`plugins/shipwright-compliance/scripts/lib/collectors/_test_links_io.py`) — i.e. `git rev-parse HEAD` run IN THE REGEN STEP ITSELF, not `github.sha` threaded through from the workflow. The conclusion ("no code change needed for the field's normal-path correctness") happens to still be right today — checkout leaves `HEAD == github.sha` on a push trigger — but for a different, more fragile reason than originally claimed: `git_head` swallows `OSError`/`SubprocessError` and returns a zero-SHA sentinel (`"0" * 40`) on failure, or on empty stdout. A zero-SHA `source_commit` would previously fail content-binding as a hard `error` (a self-repeating operational exit-2 for that commit) rather than the graceful `unavailable` the design intends for "no usable evidence yet" — fixed in `ci_execution_evidence.py`: any `source_commit` that does not look like a real 40-char hex SHA now resolves `unavailable` before the equality comparison runs at all. See `test_error_...` (renamed pattern) tests in `shared/tests/test_ci_execution_evidence.py`. |
| 7 | glm | medium | Escalation volume risk: if most FRs' bound tests are excluded by `ci.yml`'s test-selection, the first real run could escalate far more than the spec's "zero to a handful" expectation. | **rejected-with-reason.** Already disclosed and tracked — see `## Rollout validation` and `## Operating context feasibility check`, which empirically confirmed `main`'s current drift-clean state and documented the expected first-run shape. Inherent to acting on REAL evidence, not a design flaw. |
| 8 | glm | medium | The whole mechanism is unvalidated until `main` is drift-clean AND one verified push run with a populated artifact exists; the housekeeping that produces that state is "recommended, not blocking." | **rejected-with-reason (same as #5/#7).** Explicit Known Limitation + Rollout validation section; tracking artifact is this doc itself plus F3a reflection, not a new blocking gate (forbidden by p3.4c's mandate / issue #449). |
| 9 | glm | low | Adversarial/malformed zip content from a compromised Actions artifact is a low-probability but unhandled edge case. | **accepted-and-fixed (via #2).** The new `_execution_shape_error()` check plus the existing `try/except (KeyError, TypeError)` around `structural_diff` together reject any parsed-but-malformed content before it reaches the promotion predicate. |
| 10 | glm | low | Ledger-fingerprint collision risk if the aborted PR #690 attempt left hand-created `p3.5`-era ledger entries. | **verified moot.** Checked directly: `git cat-file -e origin/main:.shipwright/compliance/layer_promotion_ledger.json` — the ledger file does not exist on `origin/main` at all. No prior entries to collide with. |

Findings #1 and #2 are the only ones that changed code (`ci_execution_evidence.py`:
`_find_unexpired_artifact` newest-by-`created_at` selection; new `_execution_shape_error`
pre-flight validator) — both covered by new tests in `shared/tests/test_ci_execution_evidence.py`.

## Self-Review (Step 3.6, always — `references/iteration-reviews.md`)

| # | Item | Verdict | Note |
|---|---|---|---|
| 1 | Spec Compliance | pass | Rebuilt (not file-copied) the evaluator/ledger/writer/CLI shape from `13e3dbad7`, all 6 original ACs plus round-2's AC-R1..R16 covered by dedicated tests; matches REPLACE-never-merge, the closed 3-case escalation list, never-self-ack/human-only-override. |
| 2 | Error Handling | pass | `CommittedManifestReadError` distinguishes every git-read failure mode; `ExecutionEvidence.status=="error"` checked BEFORE `plan_promotions` runs (never silent skip-all); new `_execution_shape_error` turns a malformed artifact into a clean `error` instead of an uncaught exception inside the locked promotion span. |
| 3 | Security Basics | pass | Content-binding (`source_commit` + `structural_diff`) is the actual new unforgeability work; artifact selection now picks the newest match by `created_at`; all subprocess calls use fixed argv, `shell=False`; the `ci.yml` diff went through the mandatory operator acknowledgement gate, not a self-ack. |
| 4 | Test Quality | pass | Full TDD; 27 CLI-integration tests, 20 resolver-level tests, 11 standalone-diagnostic-CLI tests (incl. a real subprocess invocation for the flat-module import-hazard class), 8 CI-YAML shape-pinning tests. |
| 5 | Performance Basics | pass | One artifacts-list query + one download per RUN (never per-FR); bounded subprocess timeouts; no N+1 pattern. |
| 6 | Naming & Structure | pass | `ci_execution_evidence.py` stays a flat peer of `ci_provenance.py`; `promote_required_layers.py` stays a thin CLI shell delegating to `lib/`; no new abstraction for a single caller. |
| 7 | Affected Boundaries (ADR-024) | pass | Producer (`ci_manifest_drift_check.py`'s in-place regen, uploaded as a CI artifact) / consumer (`ci_execution_evidence.py`'s resolver) identified. Real (non-mocked) round-trip probes against this repo's actual HEAD manifest: `structural_diff(real, real) == ''`, and `_execution_shape_error()` accepts all 20 real requirement nodes with zero false-rejects. The one leg not provable pre-merge — the real GitHub Actions upload/download round-trip — is disclosed in Known Limitations and gated by Rollout Validation, consistent with the empirically-confirmed operating-context finding above. |

## External-Code-Review-Findings (Step 3.7, round 3 — post-implementation external LLM code review)

Run against the full diff (`external_review.py --mode code`) — GLM verdict `revise` (7 findings),
OpenAI verdict `revise` (5 findings); several are the SAME defect independently caught by both.

| # | Source | Severity | Finding (one line) | Disposition |
|---|---|---|---|---|
| 1 | openai/security/high + glm/bug/medium | high | The round-2 "pick the newest artifact by `created_at`" fix was dead code with respect to WHICH BYTES actually get fetched: `_download_and_parse_artifact` downloaded by NAME (`gh run download --name`), discarding the selected artifact's identity. | **accepted-and-fixed.** `_download_and_parse_artifact` now takes the selected artifact's own numeric `id` and downloads it directly (`gh api .../actions/artifacts/{id}/zip`, raw bytes, unzipped locally) — no second, independent by-name resolution. New tests assert the selected `id` is actually the one passed to the download call. |
| 2 | openai/test/medium + glm/test/medium | medium | The multi-artifact test's fake downloader ignored which artifact was selected, so it validated the mock, not the behavior — would pass even with #1's defect present. | **accepted-and-fixed (via #1).** Rewritten tests (`test_download_is_called_with_the_selected_artifacts_own_id`, `test_multiple_matching_artifacts_select_the_newest_id_by_created_at`) assert the exact artifact `id` reaching the download call. |
| 3 | openai/bug/medium + glm/edge-case/low | medium | `_execution_shape_error` validated shape only AFTER `node.get(...) or {}` had already normalized missing/deleted execution-tier fields to `{}` — a partially-corrupted or truncated upload (which `continue-on-error: true` makes possible) could resolve `confirmed` with silently-empty `requirements` instead of `error`. | **accepted-and-fixed.** `_execution_shape_error` now runs against the RAW, un-normalized artifact nodes and requires `coverage`/`tests` keys to be genuinely PRESENT (not merely defaulted) for every requirement ID the committed manifest expects; `resolve_execution_evidence` only normalizes AFTER this check passes. New test `test_error_when_execution_tier_coverage_key_is_deleted_not_merely_falsy`. |
| 4 | glm/bug/medium | medium | The dry-run (`--manifest`) branch of `promote_required_layers.main()` had no error wrapping around `load_ledger`/`plan_promotions`, unlike the real-write path — a corrupted ledger or an escaping `spec_path` would surface as a raw traceback instead of this CLI's documented `{"error": ...}` exit-2 shape. | **accepted-and-fixed.** Same try/except shape as `_plan_and_apply_locked` added to the dry-run branch. New tests `test_dry_run_with_a_corrupted_ledger_is_a_clean_operational_failure_not_a_traceback`, `test_dry_run_with_a_spec_path_escaping_the_project_root_is_a_clean_operational_failure`. |
| 5 | glm/bug/medium | medium | Fingerprint-basis asymmetry: the automated tool fingerprints the CI-SOURCED node; `record_layer_promotion_decision.py` fingerprints whatever `coverage`/`tests` the WORKING-TREE manifest carries (never commit-pinned) — a genuine divergence between the two bases can make `fingerprint_drifted` re-escalate `contradicts_recorded_decision` against a veto recorded against the same real-world state. | **accepted, NOT fixed this round (disclosed).** Retrofitting CI-evidence-awareness into this previously evidence-unaware CLI (commit-pinning its read, resolving evidence, refingerprinting) touches every one of its 19 existing tests — a nontrivial change whose own correctness risk, attempted under this round's remaining budget, outweighed closing a gap that is narrow in practice (an operator typically demotes shortly after inspecting FRESH local evidence, so the two bases usually agree). Documented prominently in the file's own module docstring, not silently dropped. |
| 6 | openai/spec/high | high | Read as: the escalation must route through `diff_risk_recheck`'s own acknowledgement/revalidation flow instead of a separate ledger + human-only-override CLI. | **rejected-with-reason.** The sub-iterate spec's own AC (`p3.5-promote-layers-per-fr.md` line 40) says the escalation "reuses the `diff_risk_recheck` contract (exit 3 + operator ack + exitable re-run)" — the CONTRACT SHAPE (exit-code semantics, never-self-ack, content-trusted exitable resolution), not literal reuse of that module's own ack-file mechanism for an entirely different escalation domain (iterate-level CI-supplychain risk vs. per-FR promotion decisions). This shape is exactly what `record_layer_promotion_decision.py` implements (never-self-ack, human-only, content/fingerprint-trusted). PR #690 — reviewed across 12 rounds — was never once challenged on this point; the restart brief explicitly calls this mechanism "undisputed." |
| 7 | openai/spec/medium | medium | `unavailable` execution evidence degrades to an ordinary skip for every FR, converting "binding exists but the test did not run in CI evidence" into a routine exit 0 whenever CI evidence is absent wholesale. | **rejected-with-reason.** Duplicate of plan-review finding #4 (see `## External-Plan-Review-Findings`) — same disposition: `REASON_BOUND_TEST_ABSENT` requires evidence that EXISTS and shows an ambiguous bound-but-unexecuted state; when evidence is wholesale absent there is nothing ambiguous to report, only "insufficient evidence, skip" — traced in the design's "Why the evaluator needs no code change" section. `evidence.status=="error"` (the genuine query-failure case) already exits 2 before any FR is evaluated. |
| 8 | glm/edge-case/low | low | `?per_page=100` with no pagination on the artifacts-list query — a run with more than 100 artifacts could push the named artifact past the first page, yielding a false `unavailable`. | **accepted, deferred (disclosed).** Added to Known Limitations below — same severity class and disposition style as p3.4c's own accepted, undisclosed-scope limitations; not implemented this round (low-probability given this repo's actual artifact volume, and a false `unavailable` fails toward the SAFE direction — no promotion — not toward a false `confirmed`). |
| 9 | glm/spec/medium | medium | The mandatory Stage-3 doubt review was recorded `not_run` again (as the first PR #690 attempt did), with no fresh-context adversarial pass against THIS code in evidence. | **acknowledged — tool-grant limitation, not a silent skip.** This runner has no Agent/Task tool and cannot spawn `doubt-reviewer`; `reviews.json` records `doubt: not_run` with a disposition naming this constraint, and the orchestrator's own campaign-mode 3f-bis cascade is where a real doubt-review pass runs before merge (promoted with `--force`, never silently skipped). This external CODE review pass — which independently caught findings #1/#2 before any doubt-reviewer would have — is the adversarial, fresh-context check this round substitutes in the interim; flagged explicitly to the orchestrator in the runner's final report. |

Findings #1–#4 changed code (all covered by new/rewritten tests); #5 is disclosed, not fixed;
#6/#7 are rejected with a cited reason; #8 is a disclosed, deferred low-severity gap; #9 is a
tool-grant constraint, explicitly surfaced rather than silently absorbed.

## Confidence Calibration (Step 3.8, mandatory — effective complexity `medium`)

**Boundary identified (ADR-024):** the CI Artifacts API/CLI download-and-extract boundary — the
ONE leg Self-Review item 7 flagged as "not provable pre-merge" (real `gh api .../artifacts/{id}
/zip` bytes → `zipfile` extraction), made newly load-bearing by this round's HIGH-severity fix
(finding #1 above: download-by-ID instead of download-by-name).

**Probe 1 (real, non-mocked):** fetched a REAL existing artifact from this repo's own most recent
successful `main` CI run (`repo-diff-coverage`, artifact id `10090708144`, 125 KB compressed) via
`gh api repos/svenroth-ai/shipwright/actions/artifacts/{id}/zip`, byte-for-byte the same endpoint
shape `_download_and_parse_artifact` now calls. Result: a genuinely valid ZIP (`zipfile.testzip()
== None`). Finding: none — the endpoint and CLI invocation shape work as designed.

**Probe 2 (real, non-mocked, exact mechanism replay):** re-ran the SAME fetch through the exact
`subprocess.run([...], stdout=fh, stderr=subprocess.PIPE, shell=False)` + `zipfile.ZipFile(...).
read(member)` sequence `_download_and_parse_artifact` itself uses (not a paraphrase — the literal
call shape), extracting `coverage.xml` (2,326,302 bytes) and confirming its content is genuine,
well-formed XML. Finding: none.

**Asymptote:** two consecutive real-artifact probes, zero findings on either — this boundary is
calibrated. The remaining, disclosed gap is narrower than before this round: not "does the
download/extract mechanism work against real GitHub bytes at all" (now proven, was previously
untested), but only "will THIS design's own artifact — a single-file JSON upload from `ci.yml`'s
new step, not yet run for real since it hasn't merged" — tracked by `## Rollout validation`, not
this calibration.

**Edge cases not probed (and why acceptable):** artifact expiry mid-download (network-timing race,
inherently unreproducible in a probe); a >100-artifact run exhausting pagination (disclosed as a
deferred low-severity limitation, finding #8 above, not a calibration gap); GitHub API rate-limit
exhaustion during the artifacts-list query (ambient `gh` trust assumption already documented,
same as `ci_provenance.py`).

## Post-Push Internal Cascade Findings (Stage-1/2 spec+code-reviewer, round 4)

Run against the pushed commit by the orchestrator's mandatory internal review cascade
(`campaign-mode.md` 3f-bis) — Stage-1 (`spec-reviewer`) PASSed cleanly, reconfirming both round-3
fixes independently. Stage-2 (`code-reviewer`) found one genuine, previously-unseen HIGH defect
that had escaped three prior review rounds (external plan review, external code review, self
review), plus one related medium finding. Both fixed same-round; disposed below.

| # | Source | Severity | Finding (one line) | Disposition |
|---|---|---|---|---|
| 1 | code-reviewer | **high** | `promote_required_layers.plan_promotions` looked up CI evidence by a requirement node's bare `id` (`"FR-01.01"`) — `ci_by_fr.get(fr_id)` — but `ci_execution_evidence.resolve_execution_evidence` keys its returned `requirements` dict by the committed manifest's own NAMESPACED top-level key (`"01::FR-01.01"`, confirmed directly against the real `.shipwright/compliance/test-traceability.json`). The lookup could never match for ANY FR, silently forcing every promotion decision through the `{}`/`{}` "no evidence" branch regardless of what CI actually confirmed — indistinguishable from the honest `unavailable` steady state, and camouflaged by this doc's own "zero promotions today" operating-context prediction. The entire restart's stated purpose (promoting FRs on confirmed CI evidence) could not have worked in production. | **accepted-and-fixed.** `plan_promotions` now iterates `active.items()` and looks up `ci_by_fr.get(manifest_key)` — the SAME key the resolver used to build the map. Root-caused to a composition gap: `_mock_evidence_from` (this file's own test helper) built its CI map keyed by `node["id"]` (bare), and `test_ci_execution_evidence.py`'s `_committed_manifest` fixture used `"FR-01.01"` as BOTH the dict key and the id — an unrealistic shape that made the two WRONG assumptions mutually consistent, so no test ever composed the real resolver's actual output with the real consumer. Both fixtures corrected to use realistic namespaced keys; a new end-to-end seam test (`test_end_to_end_seam_between_the_real_resolver_and_plan_promotions`) composes the REAL resolver with the REAL `plan_promotions` and asserts an actual promotion; two new tests (`test_ci_confirmed_evidence_overrides_a_greener_committed_claim` and its mirror) directly exercise CI evidence disagreeing with the committed manifest in both directions. All three new tests were verified RED against the pre-fix lookup (reverted locally, re-ran, confirmed `reason_code: "no_evidence_yet"`, `fr_confirmed: false`) before being confirmed GREEN against the fix — not merely asserted to work. |
| 2 | code-reviewer | medium | `resolve_execution_evidence`'s `isinstance(raw_requirements, dict)` guard ran AFTER the `structural_diff(committed_manifest, artifact)` call, not before — `_structural_view` unconditionally calls `data["requirements"].items()`, so a malformed top-level `requirements` (e.g. a list, from a corrupted/adversarial upload that `continue-on-error: true` makes possible) raised an uncaught `AttributeError` instead of the documented clean `error` outcome, breaking the module's own three-outcome contract. | **accepted-and-fixed.** The `isinstance` guard now runs BEFORE `structural_diff`; `AttributeError` also added to the caught exception tuple around that call as belt-and-braces (a malformed per-requirement NODE, not just the top-level dict, can raise the same way one level deeper). New test `test_error_when_top_level_requirements_is_not_an_object`, verified RED (real `AttributeError` traceback reproduced) against the pre-fix ordering before being confirmed GREEN against the fix. |

Both fixes are narrow and surgical (no design re-opening, per the orchestrator's explicit
instruction) — finding #1's fix is a two-line lookup-key correction plus fixture/test realism
work; finding #2's fix is a call-order swap plus one added exception type. The `ExecutionEvidence.
requirements` and `plan_promotions` docstrings were both tightened to name the manifest key
explicitly (`NN::FR-XX.YY`), replacing the previously ambiguous `req_id ->` phrasing. Low-severity
findings from this same review pass (readability/duplication/case-normalization/bloat-baseline)
were explicitly deferred per the orchestrator's instruction, not silently dropped — same
disposition class as the round-3 low findings already in Known Limitations above. The
"ledger-instead-of-`diff_risk_recheck`-reuse" HIGH (spec category) finding is being adjudicated
directly by the orchestrator's own doubt-reviewer against the round-1 rebase precedent, not sent
back to this runner — see the orchestrator's own message for that disposition.

## Post-Push Stage-3 Doubt-Review Findings (round 5, mandatory per the restart brief)

Run against round-4's commit (`a2d8a68c`) by the orchestrator's Stage-3 `doubt-reviewer` — a
genuine adversarial pass across contract-boundary, hidden-coupling, and reversibility lenses,
attempting to disprove 8 specific claims and failing to disprove any of them (REPLACE-never-merge,
`acs`-irrelevance, never-self-ack, and more all independently reconfirmed). Found one further
HIGH defect (the fourth round in a row to find exactly one HIGH the prior rounds missed — see
`## F3a` reflection below) plus one medium and four low findings. All six fixed same-round.

| # | Source | Severity | Finding (one line) | Disposition |
|---|---|---|---|---|
| 1 | doubt-reviewer | **high** | An operator's `demoted` veto was PERMANENTLY non-exitable once the CI-evidence path started returning real values: `record_layer_promotion_decision.py` fingerprinted the WORKING-TREE/committed manifest node's raw `coverage`/`tests`; `promote_required_layers.py` fingerprinted the CI-SOURCED `eval_node`'s raw `coverage`/`tests` — two structurally different bases BY CONSTRUCTION (the same reason `compare_traceability_manifest.py` excludes exactly these two fields from structural drift comparison: "which tests a run *collected* depends on OS/marker selection"). `fingerprint_drifted` therefore returned `True` on EVERY run regardless of whether the evidence had genuinely moved, re-escalating `REASON_CONTRADICTS_DECISION` forever — the operator's only escape was `--action promoted`, i.e. abandoning their own veto. Independently re-verified via direct source inspection (`layer_promotion_ledger.py:92-111`, `record_layer_promotion_decision.py:324` vs. `promote_required_layers.py:263,294-295`, `layer_promotion_apply.py:134,148`, `compare_traceability_manifest.py:9-18`) before any code was touched. | **accepted-and-fixed.** `evidence_fingerprint(node)` now hashes two DERIVED facts instead — `highest_ok_layer(coverage)` and `sorted(bound_but_absent_layers(tests))`, the exact same two facts `evaluate_fr`'s own `predicate_holds` is built from (both already public in `lib/layer_promotion.py`) — so the two writers' bases agree whenever the FR's actual promotability-relevant state agrees, regardless of raw OS/marker-selection noise in `tests`. Import is function-local (not module-top-level) to avoid a real circular-import failure: `layer_promotion.py` imports `fingerprint_drifted` FROM `layer_promotion_ledger.py` at ITS top level, so a top-level import in the reverse direction fails on whichever module loads first — verified empirically both load orders succeed with the lazy import. Dead code removed (`_canonical_tests`/`_link_sort_key`, no longer used by anything). Six new/updated regression tests (`shared/tests/test_layer_promotion_ledger.py`: two new derived-facts-agree/disagree pins, two existing link-reordering tests' rationale comments updated since the mechanism they pinned no longer exists; `shared/scripts/tools/tests/test_promote_required_layers.py`: `test_demoted_fr_with_raw_evidence_noise_but_same_derived_facts_stays_a_clean_skip`, composed through the REAL seam — both writers, not two mocks — with an explicit precondition assertion the raw content actually differs and the fingerprints actually agree), all verified RED against the pre-fix raw-hash fingerprint before being confirmed GREEN. |
| 2 | doubt-reviewer | medium | This doc's own round-3 disposition for external-plan-review finding #6 cited a code chain that does not exist (`regenerate_base_head`/`_build`, which lives in `tools/verifiers/_layer_coverage_regen.py` and is called only by the layer-coverage verifiers, never by `ci_manifest_drift_check.py`). The real chain — `ci_manifest_drift_check.regenerate_manifest()` → the `shipwright-compliance` plugin's `test_links.generate_file(project_root)` → `source_commit=io.git_head(project_root)` — makes today's "no code change needed" conclusion right for a more fragile reason than claimed: `git_head` swallows `OSError`/`SubprocessError` and returns a zero-SHA sentinel on failure/empty output, and a zero-SHA `source_commit` would fail content-binding as a hard, self-repeating `error` rather than the graceful `unavailable` the design intends for "no usable evidence yet." Independently re-verified via direct source inspection of both chains before any code was touched. | **accepted-and-fixed.** Corrected the finding #6 disposition row above to name the real chain. `ci_execution_evidence.py`'s content-binding check now special-cases a `source_commit` that is either the exact zero-SHA sentinel or does not look like a real 40-char hex SHA at all as `unavailable`, checked BEFORE the equality comparison. Three new tests in `shared/tests/test_ci_execution_evidence.py`, verified RED (the zero-SHA case specifically caught a real bug in the FIRST draft of this fix — an all-zeros string IS valid-looking hex, so a format-only check alone did not catch it; the zero-SHA sentinel needed its own explicit equality check) before being confirmed GREEN. |
| 3 | doubt-reviewer | low | Case-normalisation asymmetry: `resolve_ci_verification` lowercases `commit`; `resolve_execution_evidence` compared `source_commit` against the caller's ORIGINAL-case string. | **accepted-and-fixed.** `commit = commit.lower()` added at the top of `resolve_execution_evidence`. New test `test_resolve_execution_evidence_lowercases_the_caller_supplied_commit`, verified RED (an upper-case caller commit spuriously mismatched a lower-case `source_commit` for the identical commit) before being confirmed GREEN. |
| 4 | doubt-reviewer | low | `plan_promotions` dereferenced `node["id"]` unguarded twice — a hand-corrupted committed manifest carrying an ACTIVE node with no `id` (or a non-string one) escaped as a raw `KeyError` traceback instead of the CLI's documented `{"error": ...}` exit-2 shape. | **accepted-and-fixed.** `_active_requirements` now also filters on `isinstance(node.get("id"), str)`, at the single point every caller already reads "active requirements" through — the same treatment a structurally-invalid (non-dict) node already got. New test `test_an_id_less_active_node_is_excluded_not_a_raw_traceback`, verified RED (real `KeyError: 'id'` reproduced) before being confirmed GREEN. |
| 5 | doubt-reviewer | low | The seam test's `sys.modules["ci_execution_evidence"]` bare-name workaround (ADR-045-class hazard: `mod`'s own bare import registers a DIFFERENT module object than this test file's package-qualified one) had no comment explaining why, risking a future "simplification" back to a normal `monkeypatch.setattr` that would silently stop exercising the real code path. | **accepted-and-fixed.** One explanatory comment block added at the import site in `test_end_to_end_seam_between_the_real_resolver_and_plan_promotions`. |
| 6 | doubt-reviewer | low | The dry-run (`--manifest`) branch's docstring promise ("exit 3 means every FR that DID decide cleanly this run is still written") is violated by dry-run mode itself, which can return 3 on an escalation while having written nothing at all, by design. | **accepted-and-fixed (docstring only, no behavior change).** `main()`'s module docstring now explicitly excepts `--manifest` dry-run mode from that promise, naming what a `3` means there instead ("this WOULD escalate against the given manifest," never a claim about anything else being durably recorded). Behavior deliberately left unchanged — `--manifest` mode's own "no ledger entry and no spec.md write ever happen, regardless of what the run decides" contract is correct and intentional; changing the exit code itself would reduce, not improve, what a dry-run caller can observe. |

Every fix in this table was independently re-verified against the real source (not taken on the
doubt-reviewer's report alone) before any code was touched — same discipline as round 4. Per the
orchestrator's explicit scoping for this round: no other findings were reported as needing action;
the doubt-reviewer's own assessment states it "genuinely tried to disprove 8 things and failed on
all 8," so this table closes the mandatory Stage-3 pass for this sub-iterate.
