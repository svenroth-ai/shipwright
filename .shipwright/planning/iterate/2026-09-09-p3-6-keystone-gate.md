# Iterate Spec: THE KEYSTONE GATE — a behaviour-changing PR names its changed ACs and their bound tests are green

- **run_id:** iterate-2026-09-09-p3-6-keystone-gate
- **Campaign:** req3-04c-ac-identity-wave2, sub-iterate p3.6 — **the north star** (campaign SPEC §1.4,
  §5 Track V: *"★ P3.6 ist der Nordstern, nicht ein Item unter vielen. Alles davor ist der Zubringer."*)
- **Status:** **APPROVED FOR BUILD** after four plan-review rounds (round 1: 3 blocking + 4 edits +
  6 rulings · round 2: 2 HIGH *introduced by round 1's own fixes* + 4 SHOULD + 3 minor · round 3
  verification: 2 HIGH *introduced by round 2's fixes* + 2 low → **GO**, with the two HIGHs to be
  re-verified by the build-time spec/code/doubt cascade rather than a fifth plan round). All folded
  in below. **Design is now the build contract.**
- **Affected FRs:** FR-01.11 (AC-identity / evidence-ledger area — same FR as P3.1–P3.5)
- **Source sub-iterate spec:**
  `.shipwright/planning/iterate/campaigns/req3-04c-ac-identity-wave2/sub-iterates/p3.6-keystone-gate.md`
- **Design of record (not to be re-invented):** `Spec/design/2026-07-22-req3-campaign-SPEC.md`
  §1.4 (the gate's one sentence), §1.4.1 (the non-circumvention clause), §1.5 (M4/M6/M8),
  §3.2 (D9, D10, D12), §5 Track V, §8 E2.
- **Immediately-preceding art:** p3.4c (`shared/scripts/ci_provenance.py`, PR #691) and p3.5
  (`shared/scripts/ci_execution_evidence.py`, PR #693, commit `0348b8871`), plus the halted
  first P3.5 attempt (PR #690 — 12 BLOCK rounds, ~8.5 h, 9 of 12 the same root cause).

**Round-2 changelog.** Core architecture (§4 / §5.0) verified correct against `ci_provenance.py`
and `ci_manifest_drift_check.py`; unchanged. Three HIGH closed: the **`@covers`-suffix dodge**
(§5.3, new `binding_removed`, base-side binding now read); a **falsified measurement** (§2.3
re-measured against a real CI run); an **exit-2 landmine** in AC-K9(d) (§5.1 — the two criteria
readers are *not* interchangeable). Six rulings folded in; `## 8` became *rulings adopted*, with
one new ask (Q1b).

**Round-3 changelog — two of the round-2 fixes introduced new HIGH defects; both are closed here.**
(1) `unbound` was written as "no node at base **or** head", which *is* `binding_removed`'s own
input — the outcome table contradicted itself and AC-K8 vs AC-K14 asserted opposite verdicts for
identical input, so a builder following AC-K8 would have **reinstated round 1's dodge**. Now
disjoint with explicit precedence (§5.3). (2) Downgrading AC-K9(d) to exit 1 fixed its remedy but
left it **unscoped to the PR's diff**, so one intro sentence anywhere in the repo would have redded
every later PR — including the docs-only one AC-K1 requires to pass. Now scoped to FRs whose
`criteria_digests` changed in *this* PR (§5.1). Four SHOULD-fixes: the `origin/main` precondition
now defers to `_merge_base`'s own verdict (§5.7); `_spec_paths` takes **both** manifests (§5.1);
§5.5 no longer claims to reuse `evaluate_binding_completeness`, which tests the inverse direction;
arm 1's pseudocode is corrected to `read_all(...).items()` and digests `(fr_id, text)` (§5.2). Plus
three minor: the plugin-`addopts` three-way split (§2.3), the asymptote tally (§11), and the
**two-PR unbind sequence** now named as an explicit input to p3.7(b)'s card (§7, §10 item 8).

**Round-4 changelog — again, both HIGHs were introduced by the previous round's fixes.**
(1) The base-manifest `git show` read ruled only the v3-predates case; "path absent at base" and
"blob present but malformed" were unruled, and **every neighbouring helper in this repo defaults a
failed `git show` to permissive/empty** — so a builder following the house pattern would have
disarmed `binding_removed` and collapsed `_spec_paths` to head-only. Now an explicit three-way
rule with a logged warning on the one permissive branch (§5.3, AC-K9(e)), and Probe B is extended
to probe it against real git. (2) Round 3's precedence paragraph stated `binding_removed`/`unbound`
in **node-presence** terms while the outcome table stated them in **link-count** terms; the two
disagree on "base has links, head has a node with empty `tests`", where the node reading falls
through to a ∀-over-empty-set that is **vacuously true → exit 0** — round 1's dodge once more.
Collapsed to **one vocabulary (link counts) everywhere**, plus an assert-and-route guard so the
∀ walk is never entered empty (§5.3, AC-K8, AC-K16). Two low findings folded in: the divergence
guard now explicitly precedes and suppresses §5.2 arm 2 for the same FR, uses `.get(fr)`, and
§5.7's leftover literal `origin/main` prose is reworded.

---

## 1. Problem

The gate, in the SPEC's own one sentence (§1.4):

> **Ein verhaltensänderndes PR darf nicht mergen, ohne (a) die geänderten ACs zu benennen und
> (b) die an diese ACs gebundenen Tests in CI erneut laufen zu lassen — grün.**

Today, at FR granularity, most of the machinery exists and is undisputed:

| Piece | Where it lives today | Granularity |
|---|---|---|
| behaviour-change signal from the spec diff | `_layer_coverage_core.behavior_changed_keys` + `_layer_coverage_ac.changed_criteria_ids` | **FR** (one pooled digest per FR's whole criteria block) |
| "covered + executed-passing at every required layer" | `_layer_coverage_core.evaluate_cross_layer` | **FR** |
| "the binding must name the highest observable layer" | `_layer_coverage_binding.evaluate_binding_completeness` (P3.3) | **FR** |
| per-test execution evidence from a real run | `test_links.generate_file()` → `link.executed ∈ {pass,fail,not_run}` | test |
| the same, regenerated in CI from that run's own JUnit | `ci_manifest_drift_check.py` (in place, every push/PR) | test |
| per-AC identity | `lib/ac_identity.py` `[ACnn]` markers (P3.1) | **AC** |
| per-AC binding | manifest v4 `requirements[k].acs[ACnn].tests` (P3.2/P3.3) | **AC** |

Three things are missing, and they are exactly p3.6:

1. **Nothing reads the AC-level identity.** `_layer_coverage_ac.criteria_digests` hashes an FR's
   *pooled* criteria text, so it can say "some criterion of FR-01.11 changed" and never "AC17
   changed". `_layer_coverage_binding.py`'s own docstring already names the successor:
   *"P3.6 is the eventual AC-level keystone; this is the FR-level binding it depends on."*
   The campaign's own settled answer to "does AC identity have a consumer?" is: **P3.6 is the
   consumer.** If p3.6 does not read `[ACnn]`, P3.1–P3.4 have no consumer at all.
2. **Naming is never required.** A behaviour-changing PR that lands on no identifiable criterion
   falls into `evaluate_cross_layer`'s `could_not_determine` → a WARN, forever (SPEC §1.5 M4:
   *"AC-Prosa-Edit fällt heute in `could_not_determine` → WARN für immer"*).
3. **Nothing blocks a merge.** Every gate in the table above is an **F11 iterate verifier** — it
   runs inside `/shipwright-iterate`'s own finalization, on the agent's own machine, before push.
   A PR authored any other way never meets it. §1.4's sentence is a *merge* condition (M8:
   *"Durchsetzung — Gates in CI"*), and today `ci.yml` enforces nothing about requirements at all.

---

## 2. Operating-context feasibility check (empirical — real repo, real git, real CI)

Same discipline p3.5's restart was forced into by its own round-2 plan review: measure before
designing, and report the number a real run would produce. Round 1 of this document got one of
these measurements **wrong**; §2.3 is the corrected version and the correction changed a
conclusion, which is exactly why the measurement is here rather than assumed.

### 2.1 How much AC-level binding actually exists

```
criteria under an FR heading in .shipwright/planning/01-adopted/spec.md : 268  (20 active FRs)
   carrying an [ACnn] marker                                            : 268
   carrying a binding in manifest v4 (acs[ACnn].tests non-empty)        :   9
bound (AC -> test) links total                                          : 142
```

**Honesty note on the "268 of 268" figure (round-2 finding 3).** Numerator and denominator both
come from `ac_identity.read_all`, so on its own that ratio is self-referential — it says "every
criterion *this reader sees* is minted", not "every criterion *in the document* is minted". It is
still a meaningful statement about **arm 1 of AC-1** (which is defined in terms of this same
reader, so the measurement and the gate share a definition by construction), but it is **not**
evidence about what the FR-level reader sees. §5.1's reader-divergence guard and its drift test
(AC-K15) are what actually cover that gap; the ratio is not.

**Reading:** naming is complete *in this reader's terms*; binding is nearly absent. A gate that
demanded "every changed AC has a green bound test" would therefore be either a blanket blocker (if
a missing binding blocks) or nearly inert (if it does not). The campaign already decided which:
**"AC without a test" is p3.7's anti-ratcheted feeder check (SPEC §8 E2), not p3.6's.** p3.6
blocks on a *binding that is not green* and on a *binding that was removed* (§5.3), never on the
absence of one that never existed.

### 2.2 How often the gate would fire at all

Over the last **60 commits on `origin/main`**, exactly **3** touched `spec.md`:

| commit | verdict under the proposed per-AC digest |
|---|---|
| `545a4f320` (P3.4 backfill) | 268 ACs read as `added` — an artefact of the mint itself: at base no criterion carried a marker. Additions do **not** block under arm 2 of AC-2 unless they already carry a binding (deviation 3, §7), but under §5.2's corrected `unminted_changed` rule they would have blocked *at base*, which is why "mint before gating" is a stated precondition (§7). |
| `43e8969b2` | spec.md touched, **no minted-AC text change** → gate silent |
| `8255aca2f` | spec.md touched, **no minted-AC text change** → gate silent |

**Reading:** the keystone gate is a **low-frequency, high-consequence** gate, not a daily tax.
That is the honest characterisation and it belongs in the PR body: its value is that it cannot be
bypassed on the day it matters, not that it fires often.

### 2.3 Would it red `main` today? — RE-MEASURED against a real CI run (round-2 finding 2)

**Round 1 of this document claimed CI deselects `@pytest.mark.slow` everywhere, and named
`FR-01.07/AC06` as a permanently-unfixable red. That claim was FALSE and is withdrawn.**

What was wrong: `ci.yml`'s per-plugin loop runs `(cd "$plugin" && … pytest tests/ …)` with **no
`-m` filter**, so the *plugin's own* `pyproject.toml` supplies `addopts`. Across the 14 plugins that
is a **three-way split**, not a uniform value: **12** carry `addopts = "-v --tb=short"` (no marker
selection), **`shipwright-grade`** carries `"-v --tb=short -m 'not empirical'"`, and
**`shipwright-iterate`** declares `[tool.pytest.ini_options]` with **no `addopts` key at all**.
None of the three selects against `slow`. The root `pyproject.toml`'s `-m 'not slow'` governs
`integration-tests`; the explicit `-m "not slow and not cross_plugin"` governs only the three
shared roots. **Marker exclusion does not reach plugin roots at all.** The committed manifest's
`status: "skipped"` on those links is the fingerprint of a *local* regeneration on a machine
without the gitleaks binary — not CI.

**The re-measurement, and what it had to use instead of the artifact.** The reviewer's suggested
source — the `traceability-manifest-regenerated` artifact p3.5's `ci.yml` step uploads — **does
not exist for any commit.** Checked directly:

```
$ gh api repos/svenroth-ai/shipwright/actions/runs/34397706000/artifacts   # main tip, 0348b8871
   -> repo-diff-coverage ONLY

$ gh api .../runs/34397706000/jobs   (step conclusions)
   Check traceability manifest against a fresh regeneration ... success
   Upload regenerated traceability manifest artifact (execution evidence) ... skipped
   Confirm traceability manifest verified (no drift) ................... skipped
```

Both later steps are gated on `manifest_drift.outputs.code == '0'`, so **`main`'s tip still
carries the pre-existing structural drift p3.5's own restart doc measured and flagged as
recommended-not-blocking housekeeping.** It is still unresolved, it is not p3.6's to fix, and it
does not affect p3.6 (§5.7 — regeneration happens *before* comparison, so the gate reads fresh
bytes whether the comparison reports drift or not).

Used instead: the **verbatim `-v` pytest output of that same real push run** (34397706000,
commit `0348b8871`, 17 443 outcome lines), cross-referenced against all 142 AC-bound links:

```
AC-bound links total .................................... 142
reached PASSED in the real CI run ....................... 142
non-PASSED (FAILED / ERROR / SKIPPED / XFAIL) ...........   0
ACs where no bound link reached PASSED ..................   0
```

The three `FR-01.07/AC06` gitleaks tests are in that log as `PASSED` — CI installs gitleaks
8.21.2, so their `skipif` does not fire there.

**Conclusion: the gate would be GREEN on `main` today for every one of the 9 bound ACs. There are
zero pre-existing violations.** This *strengthens* §5.4's case for `not_selected` being HARD —
the affected population is not one, it is zero — and it settles Q3's specific instance: **no edit
to `test_gitleaks_extend_smoke.py`.** That file's smoke tests are meant to hard-fail rather than
skip in CI and already do; touching them would be unnecessary churn to a security test on the
strength of a probe that modelled CI wrongly. §10's former item 6 is deleted.

**A design constraint this re-measurement produced (new, and it kills an obvious
implementation).** Reconciling the 142 links against the log initially showed 7 "absent from CI".
All 7 are artefacts of node-id **spaces**, not absences: 6 are class-nested
(`TestStepE5EnvScaffold::test_step_e5_heading_present` in pytest's console/node-id space vs
`…py::test_step_e5_heading_present` in the manifest's link-id space) and 1 was a long line my
harvester's regex missed. The collector normalises both its tag hits and its JUnit evidence into
the same reduced space, so the *manifest* is self-consistent — but **any implementation of
`not_selected` that works by checking whether a link's id appears in this run's JUnit reports
would false-red on every class-nested bound test.** `not_selected` must be read from the
manifest's own `executed` field and nothing else. Pinned by AC-K7.

### 2.4 What AC-2 literally says, and why the quantifier matters

> *"A named AC whose bound test did not run green blocks."*

`_test_links_requirements._cov_status` is `any(...)`: a layer reads `"ok"` if **one** link is
`enabled` + `pass`, even when a sibling link failed. D10 says the forced rerun is **`alle`
gebundenen Tests**. **The keystone gate therefore must NOT reuse `coverage[layer] == "ok"`.** It
must walk the links and require **∀**, not **∃**. Reusing the existing eligibility *definition*
(`status == "enabled" and executed == "pass"`) while replacing the *quantifier* is the correct
composition; silently reusing `_cov_status` would ship a gate that a single green sibling test
satisfies. This is the subtlest defect available in this design and it gets its own acceptance
criterion (AC-K6).

---

## 3. What p3.6 must NOT be — three boundaries, each already decided

**(a) Not Track R (D11).** `campaign.md`: *"TRACK R (D11) IS STRUCK from scope … Do not build it,
do not build a weaker advisory version, do not re-derive the decision."* Track R is *code → spec*:
every changed production file must name an FR/AC; the external review of 2026-08-23 rejected it as
HIGH ("couples every small refactor to requirement metadata"). **Consequence: "behaviour-changing"
is NEVER derived from which source files a diff touches.** It is derived from the **spec side**
only — the posture `evaluate_cross_layer` already documents and no reviewer has disputed: *"a pure
refactor produces an identical base/head spec → the gate does not fire."* Ratified as Q2.

**(b) Not p3.7.** "AC without a test" is **anti-ratcheted** (SPEC §8 E2 — §2.1 measures the
backlog at 259 of 268). "A test whose AC vanished" is **hard from day one**. Both are p3.7. p3.6
emits both as report-only facts in its JSON so p3.7 can consume them, and blocks on neither.
**Note the boundary is about a binding that never existed, not one this PR removed** — see §5.3's
`binding_removed`, which is squarely p3.6's.

**(c) Not a second unforgeability predicate.** See §4.

---

## 4. The trust boundary: why `resolve_execution_evidence` is NOT this gate's mechanism — and where it IS

*(Verified correct by plan-review round 1 against `ci_provenance.py` and
`ci_manifest_drift_check.py`; kept as-is.)*

**Two different questions; p3.4c/p3.5 answer only the second.**

| | Question | Producer/consumer relationship | Mechanism |
|---|---|---|---|
| Q1 | *Did test T run green in **this** run?* | same process tree, same run, seconds apart | `test_links.generate_file()` over the run's own staged JUnit → `link.executed` |
| Q2 | *Can I trust an evidence file **I did not produce**, for a commit that is **not mine**?* | across a commit **and** a machine boundary | `resolve_ci_verification` → `resolve_execution_evidence` |

P3.5 faced **Q2** and could not avoid it: `promote_required_layers.py` runs on an agent's machine,
reads a *committed* file, and writes a durable, one-way, audit-visible promotion. Producer and
consumer are separated by a commit and a machine.

**p3.6 faces Q1.** The gate runs *inside the same CI job that produced the evidence*, immediately
after `ci_manifest_drift_check.py` has **regenerated
`.shipwright/compliance/test-traceability.json` in place** from that run's own JUnit reports.
There is no commit boundary and no machine boundary to forge across.

**Reusing `resolve_execution_evidence` here would not harden the gate — it would disable it.**
`ci_provenance._qualifying_runs` accepts only runs with `event == "push"` on the **default
branch**. A PR head commit has no such run *by construction*. Wiring that resolver into a
**pre-merge** gate makes it resolve `unavailable` on 100 % of PRs — permanently inert, which is
strictly worse than no gate because it looks like one. (§2.3's artifact check is a live
demonstration: even on `main`'s own tip the resolver has nothing to resolve today.)

**What p3.6 reuses instead — what "one mechanism, not two" actually means here:**

- The **same producer**: `test_links.generate_file()`. No new JUnit reader, no second
  execution-evidence format, no parallel notion of "green".
- The **same eligibility contract**: `status == "enabled" and executed == "pass"` — the single
  definition `_cov_status`, `evaluate_cross_layer` and `_layer_coverage_binding._highest_ok_layer`
  already share, with the quantifier corrected per §2.4.
- The **same bytes** p3.5 trusts: the file p3.6 reads in CI is byte-identical to the one the
  *"Upload regenerated traceability manifest artifact"* step uploads on a clean push. One
  artifact, two points on its life-cycle, two different questions.

**Where Q2 genuinely applies — and why it is out of scope.** A *detective* control could ask,
post-merge, "did `main`'s tip actually satisfy the keystone gate, per evidence bound to a real
trunk CI run?" That reader **would** compose with `resolve_execution_evidence`. It is preventive
vs detective, it cannot block a merge, and building it here would double the blast radius of the
campaign's highest-stakes unit. **Own card, filed at merge** — ruling Q5, §8.

**p3.6's own trust posture**, to be repeated verbatim in the module docstring:

> The keystone gate is exactly as strong as `ci.yml` itself. An actor who can change `ci.yml` on a
> merged commit can disable it — the identical exposure `ruff`, the diff-coverage gate, Semgrep,
> Trivy and Gitleaks already carry here, and the one `ci_provenance.py`'s own docstring names
> (`touches_ci_supplychain` mandatory review is the control, an agent convention, not a GitHub
> technical control). p3.6 deliberately does **not** claim more than every other merge gate here.
> What it *does* guarantee: **the committed `test-traceability.json` is overwritten by a fresh
> regeneration before the gate reads it, so hand-editing it has literally no effect on the
> verdict** — and, per §5.3, **the binding it is judged against is read from the base commit as
> well, so deleting a binding in the same PR does not silently disarm the gate.**

Both properties are checkable; §6 makes them probes, not claims.

---

## 5. Design

### 5.0 One pure evaluator, one CI adapter

```
shared/scripts/tools/verifiers/_keystone_ac_digest.py   # per-AC digests + change set (git, both sides)
shared/scripts/tools/verifiers/_keystone_core.py        # PURE evaluator: change set + 2 manifests -> verdict
shared/scripts/tools/check_keystone_ac_gate.py          # CI CLI (blocking) -- exit 0/1/2
```

Following the family's own split (`_layer_coverage_core` / `_binding` / `_removal` are pure; the
`CheckResult` shaping lives in `layer_coverage.py`). The pure core takes already-computed inputs
and touches no git and no filesystem, so it is unit-testable without a repo — the property that
made `_layer_coverage_core` reviewable. **Per ruling Q4 the F11 advisory adapter is NOT built this
round**; `_keystone_core` keeps the seam (a plain verdict dataclass, no CLI assumptions) so a later
F11 arm is cheap.

### 5.1 Per-AC change detection — and the reader difference, stated rather than assumed

`_keystone_ac_digest.ac_criteria_digests(text) -> ({(fr_id, ac_id): sha256}, [unminted_digests])`

- Discovery is **`lib.ac_identity.read_all(content)`** — the one AC reader, never a second parse.
  It returns `{fr_id: [(ac_id | None, criterion_text), …]}`, whitespace-normalised and
  continuation-joined by `fr_criteria.block_criteria`, with the `[ACnn]` marker stripped from the
  digested text.
- Text at each side comes from **`_layer_coverage_ac.spec_text_at(project_root, sha, path)`** —
  the existing three-way reader (`str` / `""` when absent / `None` when unreadable), over
  **`_spec_paths(head_manifest, base_manifest)`** — the **union of both sides** (round-3 finding 4).
  That helper is variadic *precisely* for this (its own docstring: *"the union, so a spec that was
  renamed or added between base and head is still compared"*), and round 2 already made the base
  manifest available at zero extra cost. Head-only would mean a PR that **removes or renames a
  spec file** makes that file's base-side criteria invisible — including to §5.3's
  `binding_removed` check, i.e. the very subtractability axis ruling Q2 says must not be freely
  available. One argument, one hole closed.
- **The union has a converse hazard the round-3 fix did not itself introduce a guard against
  (Stage-3 doubt review, medium — found during this build):** iterating `_spec_paths`'s union and
  `dict.update()`-ing each path's minted digests into one map is last-write-wins across paths. A
  SECOND spec file added in the same PR that re-anchors an already-edited `(fr_id, ac_id)` (or a
  bare `fr_id` heading) with its OLD text would otherwise silently overwrite the genuine edit's
  digest at HEAD, reverting it to the base digest and erasing `changed` for a criterion this PR did
  change — the module's own docstring already names "no ACs changed" as the one failure worse than
  over-firing. `ac_change_set` therefore tracks which path first claimed each HEAD key and raises
  `ReadError` (exit 2) the moment a second path claims one already claimed — an AC id or FR heading
  must anchor to exactly one spec path, never reused across documents, same as the "never reused"
  premise the marker system rests on generally. HEAD-only, matching `ac_criteria_digests`'s own
  base/head asymmetry: a base commit is already merged and cannot be authored by this PR. This is
  distinct from §7's "one spec file, one namespace today" bullet, which is about two MANIFEST nodes
  sharing a display id (routed advisory by `collision_display_ids`) — this is two SPEC PATHS
  claiming the same id at the text-reading layer, and it fails closed rather than routing advisory.

**The two criteria readers are NOT interchangeable (round-2 finding 3), and this design must not
pretend otherwise:**

| | anchor shape | `strict` |
|---|---|---|
| `ac_identity.read_all` (p3.6's reader) | heading-anchored only (`_ac_blocks.iter_heading_anchored_blocks`) | **`True`** — only the **contiguous leading bullet run** under the heading counts |
| `_layer_coverage_ac.criteria_digests` (the FR-level gate's reader) | `fr_criteria.iter_anchored_blocks` — headings **plus** the legacy bold-anchor form | **`False`** — deliberately, so a note between an FR's heading and its bullets does not hide them |

So an FR whose criteria are preceded by one ordinary introductory sentence yields **zero**
criteria from `read_all` and **nonzero** from `criteria_digests`. Round 1's AC-K9(d) made that
shape an **exit 2** — i.e. adding a sentence under an FR heading would have redded every PR in the
repo with an "infra failure" that has no spec-authoring remedy. Latent today only because this
spec.md happens to use 20 heading anchors and 0 bold anchors. **Corrected treatment:**

- The guard fires on **divergence**, not on absolute zero: *`read_all` yields zero criteria for an
  active FR **and** `criteria_digests` yields a non-empty digest for the same FR*. That is the
  shape that is actually vacuous — the gate would see nothing while the FR-level gate sees
  something.
- **…AND the divergent FR must be in THIS PR's diff (round-3 finding 2 — the blast-radius fix).**
  Round 2 downgraded this finding from exit 2 to exit 1, which fixed the *remedy* but not the
  *scope*: as written it fired on **any** active FR in the whole repo, so the day anyone lands one
  ordinary introductory sentence under any FR heading, **every subsequent PR would red — including
  docs-only ones**, contradicting source AC-3 and this document's own AC-K1. It is latent today
  only because the repo currently has zero divergence, which is not a property to rely on. **The
  guard therefore fires only when `criteria_digests(base)[fr] != criteria_digests(head)[fr]`** —
  i.e. the FR-level reader says *this PR* changed that FR's criteria while the AC reader sees
  nothing there at all. Both digests are already computed for this guard, so the scoping is free.
  A pre-existing divergence in an FR the PR does not touch is invisible to the gate and is caught
  instead by the drift test below — which is the correct division: a *repo-wide* condition is a
  test's job, not a per-PR gate's. **Use `.get(fr)` on both sides**, never a bare subscript: an FR
  absent at base (a brand-new one) would otherwise raise `KeyError` inside the guard.
- **Precedence: the divergence guard is evaluated BEFORE §5.2's arm 2, and suppresses it for the
  same FR (round-4 low finding 3).** A brand-new FR whose bullets are preceded by an introductory
  sentence triggers *both* — arm 2 sees "new active FR, zero minted criteria" and the divergence
  guard sees "zero from `read_all`, non-empty from `criteria_digests`". Same symptom, two exit-1
  messages, and arm 2's ("state at least one acceptance criterion") is the **wrong** remedy: the
  criteria are there, they are merely unreachable by this reader. The divergence guard's message
  ("move the introductory note below the bullets, or mint the criteria") is the actionable one, so
  it wins and arm 2 stays silent for that FR.
- Verdict: **exit 1** with a named authoring remedy — *"FR-xx's criteria changed in this PR but are
  not a contiguous leading bullet run under its heading (`ac_identity` cannot see them); move the
  introductory note below the bullets, or mint the criteria."* **Not exit 2.** Exit 2 must stay
  reachable only from genuine infra faults, or the 1-vs-2 distinction is noise (ruling Q6's rider).
- A **drift test** (AC-K15) asserts the two readers agree on today's real `spec.md`, so a
  divergence anywhere in the repo is caught the day it appears — by a failing test naming the FR,
  never by redding an unrelated PR.

> **BUILD-TIME AMENDMENT (2026-09-09, found by AC-K9(d)(i)'s own test) — the scoping signal above
> is necessary but NOT sufficient.** The rule as written scopes the guard to
> `criteria_digests(base).get(fr) != criteria_digests(head).get(fr)` **alone**. Writing the test
> falsified it: **adding an introductory sentence changes no criterion TEXT**, so
> `criteria_digests` is byte-identical across the very PR that creates the divergence, and the
> guard never fires on the change that causes it. The consequence is not cosmetic — the AC then
> vanishes from `read_all`, so the NEXT PR to edit that criterion sees it as `added` rather than
> `changed`. Under the ratified design that meant it **never blocks on greenness**; under
> deviation 3 (§7) it blocks *iff* the AC still carries a binding at head, which narrows this hole
> without closing it — an AC unbound at head still slips through, and arm (a) below is what
> actually closes it by blocking PR1. That is the two-PR shape of the dodge the gate
> exists for, arriving through the reader seam. **Shipped rule: three scoping arms, ORed** —
> (a) the AC reader could see this FR at base and cannot at head (the intro-sentence case);
> (b) the FR is new at head; (c) its `criteria_digests` value changed. The blast-radius property
> round 3 demanded is preserved exactly: a pre-existing divergence in an FR the PR does not touch
> satisfies none of the three (base was already invisible, the FR is not new, the digests match),
> so a docs-only PR still passes — pinned by
> `test_a_pre_existing_divergence_the_pr_does_not_touch_is_invisible`.
>
> **Second amendment, same section, same cause.** `criteria_digests` hashes the JOINED criteria
> text, so an FR with **no** criteria gets `sha256("")` — a perfectly *non-empty string*. "…and
> `criteria_digests` yields a non-empty digest" therefore cannot be read as a truthiness test, or
> every criteria-less FR reads as divergent and arm 2's input is misrouted. The implementation
> compares against a named `_EMPTY_CRITERIA_DIGEST` constant.

**The change set:**

| class | condition | consequence |
|---|---|---|
| `changed` | minted id present at both sides, digest differs | **AC-2 arm fires** (§5.3) |
| `added` | minted id absent at base, present at head | `head_links == 0` → report-only (`unbound` → p3.7's baseline). `head_links >= 1` → **AC-2's greenness walk fires** — **DEVIATION 3**, §7. No layer-gap check either way. |
| `removed` | minted id present at base, absent at head | report-only → p3.7(b) |
| `unminted_changed` | see §5.2 — a head criterion with no `[ACnn]` whose normalised digest is absent from the base's unminted set | **AC-1 arm 1 fires — and this DOES cover the added case** |

**Two properties inherited for free, both strictly better than today's FR-pooled digest:**

- **Reordering is not a change.** `[ACnn]` travels with the line, so moving a criterion within its
  block changes no id and no text. The current pooled per-FR digest fires on any reordering. (AC-K3)
- **Reflow is not a change.** `block_criteria` joins continuation lines and normalises whitespace
  before the digest. (AC-K3)

**Silence is the one failure mode worse than over-firing** (`_layer_coverage_ac._criteria_region`
states this rule for its own reader; it binds here too):

- `read_all` raising `MalformedAcMarkerError` / `DuplicateAcIdError` **at head** → **exit 2**.
  (Bonus: the gate thereby enforces marker hygiene at the merge boundary, which nothing does today.)
- The same **at base** → treat base as "no ACs", so every head AC reads as `added`/`unminted`,
  plus a visible warning. Asymmetric on purpose: a base commit is already merged and cannot be
  authored by the PR, so this direction is not exploitable, and it lets a branch forked before the
  P3.4 mint pass cleanly.
- `spec_text_at` → `None` at either side → **exit 2** (git could not read a side), exactly as
  `changed_criteria_ids`' `ac_error` already does.
- `_spec_paths` returning empty (no requirement in either manifest names a `spec_path`) → proceed
  with a trivially-empty change set **and** a warning saying so (Stage-2 code review, medium),
  because a freshly regenerated head manifest naming zero spec paths is a wiring signal, not
  evidence of a clean PR.
- Every named `spec_path` resolving to no content at either commit (a stale or mistyped path,
  distinct from the case above — a path IS named, it just never reads as anything) → proceed with a
  trivially-empty change set **and its own warning** (Stage-1 spec review, round 18, hard), because
  the bullet above's warning is keyed on `not spec_paths` and does not fire here; without a warning
  of its own this branch would suppress silently, the same failure mode this whole list exists to
  close.

### 5.2 AC-1 — "a behaviour-changing PR without named ACs is blocked"

> **This is a deviation, not compliance** (round-2 edit 5). The sub-iterate spec's AC-1 says
> *"named"*, which reads as **author-declared**. This design replaces declaration with
> **spec-derived detection**, because a derived signal is unforgeable where a declaration is not —
> the same R3 reasoning that makes every gate in this family recompute rather than read a
> self-report (`evaluate_cross_layer`: *"never the self-reported event `fr_impact`"*). It is the
> right call and the plan-review gate agrees, but it is a second deviation alongside Q1's, and it
> is asked for ratification as **Q1b** and stated plainly in §11 item 1 and in the PR body.

Two arms. Both **HARD from day one, with no baseline** — the same argument SPEC §8 E2 uses to make
p3.7(b) hard: *a gate needs a baseline only when it has a legacy backlog to grandfather.*

**Arm 1 — `unminted_changed`: you changed (or added) a criterion the framework cannot name.**

*Matching rule (round-2 edit 6 — round 1 left this undecidable).* An unminted criterion has **no
identity**: `ac_identity.read` returns `(None, text)` for it, so "changed" and "added" cannot be
told apart. The rule is therefore a **set difference over normalised digests**:

```python
# read_all(content) -> dict[fr_id, list[(ac_id | None, criterion_text)]]  -- iterate .items(),
# NOT the bare dict (round-3 finding 6: iterating it yields FR-ID STRINGS, not pairs).
def unminted_digests(content):
    return {
        # Digest (fr_id, text), never bare text (round-3 finding 6): identical boilerplate
        # under two different FRs would otherwise collapse to ONE digest, and an unminted
        # criterion moved verbatim from FR-A to FR-B would cancel out and go undetected.
        sha256(f"{fr_id}\x00{text}".encode("utf-8")).hexdigest()
        for fr_id, items in read_all(content).items()
        for ac_id, text in items
        if ac_id is None
    }

arm1 fires for every digest in  unminted_digests(head) - unminted_digests(base)
```

**This deliberately covers both an edited unminted criterion and a newly added one.** An
unminted criterion that survives the PR byte-identical does not fire (it is pre-existing backlog,
which is p3.7's, not p3.6's). **This corrects the change-set table's `added` row**, which is
about *minted* ids only: an *added and unminted* criterion **does** block.

Remedy named in the failure message — the real command, verified to exist:

```
uv run shared/scripts/tools/mint_ac_ids.py \
  --spec-file <the spec.md the finding names> \
  --registry-file shipwright_ac_registry.json --write
```

…and commit both the rewritten spec and the updated registry in this same PR. **Stated honestly in
the message and in §7: the minter is not wired into any authoring flow.** Its own docstring says
so (*"Not wired into anything yet (deliberately — P3.1's own scope)"*), so this is a manual step
today. Wiring it into the producers is the *emit* half of P3.3 that `trg-875104ac` already tracks —
explicitly **not** p3.6's, and not to be smuggled in.

Non-dodgeable by construction: deleting an `[ACnn]` marker turns that criterion into an unminted
one whose digest is absent at base, which fires arm 1.

**Arm 2 — a NEW active FR at head with zero minted criteria.** Minting a requirement that states
no acceptance criterion is the purest instance of "behaviour-changing without named ACs". All 20
active FRs carry criteria today (min 6, max 29) — zero pre-existing violations.

**Second precedence rule (found during build, Stage-2 code review, medium):** arm 2 is ALSO
suppressed for any FR already reported by arm 1 (`unminted_changed`). A brand-new FR hand-authored
with bullets but no `[ACnn]` markers yet has zero MINTED criteria, but it is not silent — it states
criteria, just unminted ones, and arm 1 already reports exactly that. Without this exclusion, that
shape (the single most likely first real-world encounter with this gate: authoring an FR before
running the minter) fires both arms at once, and arm 2's message ("states no acceptance criterion")
is then false. Distinct from the divergence-guard precedence above: divergence fires when the FR-
level reader sees criteria the AC-level reader cannot; this fires when the AC-level reader sees
them too, just unminted. Pinned by
`test_a_new_fr_with_unminted_bullets_is_not_ALSO_reported_as_stating_none`.

**Third precedence rule (Stage-2 code review, medium):** arm 2 is ALSO suppressed for any FR whose
heading already exists in the BASE **spec text** (`fr_id in base_fr_digests`), independently of the
base *manifest*. The manifest is regenerated at head but read from the last COMMIT at base, and the
two are known to drift — the traceability drift step is advisory, not a hard gate — so a display id
absent from a stale base manifest is not evidence the FR is new; the spec is. Without this
exclusion, an untouched FR whose base-manifest entry never landed would HARD-block an unrelated PR.
Spec-derived, per ruling Q1b's own principle. Pinned by
`test_an_fr_present_at_base_SPEC_but_missing_from_the_base_MANIFEST_is_not_new`.

> **BUILD-TIME AMENDMENT (external plan review, glm low) — state the set operation, because
> stating it exposed a repo-wide false red.** "NEW active FR" was left undefined; it is
> `active_display_ids(head_manifest) - active_display_ids(base_manifest)`, where *active* means
> `status == "active"` and the id compared is the DISPLAY id (`node["id"]`), not the namespaced
> key. Writing that down surfaced the null case: under §5.3's case (i) `base_manifest_absent` the
> base side is **empty**, so *every* head FR trivially reads as new and arm 2 fires for every
> criteria-less FR in the repo at once — the same blast-radius mistake round 3 fixed for the
> divergence guard, in the one mode that is already degraded. **"New" is not answerable without a
> base to be new relative to, so it is not answered:** arm 2 is suppressed entirely when the base
> manifest names no active requirement, with a warning in the JSON so the suppression is logged
> rather than silently inferred. Pinned by
> `test_an_absent_base_manifest_suppresses_the_new_fr_arm_entirely`.

**Fourth precedence rule (Stage-2 code review, medium; found during build; broadened Stage-1 spec
review round 18, hard) — arm 2 is ALSO suppressed whenever no spec text was actually read: neither
manifest names a `spec_path` for any requirement, OR every named `spec_path` resolved to no content
at either commit.** This is a SECOND, independent null case beyond the empty-base-manifest amendment
above: `base_fr_digests` and `head_minted` are empty not because the base genuinely states no
criteria, but because no spec text was ever scanned — §5.1's own "neither manifest names a
`spec_path`" bullet covers the first half of this state, and its sibling bullet (every named path
resolving to no content) covers the second. Without this exclusion, a base manifest that DOES carry
active requirements makes every head-only active FR read as `new_frs_without_criteria` — "states no
acceptance criterion" asserted from a document nobody read, the same blast-radius mistake the
empty-base-manifest amendment already exists to prevent, one call away. A warning is emitted for
BOTH halves: §5.1's first bullet's warning covers the "no path named" half; the second half — which
does NOT trigger that warning, since a path WAS named — carries its own warning, added specifically
so this branch is not silent (round 18's rejection). Pinned by
`test_no_spec_path_read_suppresses_the_new_fr_arm_even_with_a_nonempty_base` (first half) and
`test_a_named_spec_path_absent_from_git_at_either_commit_also_suppresses_arm_2` (second half).

**Deliberately NOT an arm:**

- **A title-only FR row change does not block.** `behavior_changed_keys` counts a changed `title`
  as behaviour change at FR granularity; blocking a typo fix because "no AC was named" is a
  false-red on a change that alters no criterion. Stays a WARN.
- **`could_not_determine` stays a WARN.** A spec delta landing on no FR row and no criterion is an
  edit to an abstract, a quality requirement, or prose between sections. Promoting it would
  **break AC-3 directly**. What M4's hole actually was — *"eine AC-Prosa-Änderung unter
  unveränderter FR-Zeile"* — is fully closed by arm 1 + §5.3. **M4 is closed;
  `could_not_determine` is not the residue of M4.**

### 5.3 AC-2 — "a named AC whose bound test did not run green blocks"

**The gate reads TWO manifests (round-2 finding 1, HIGH).** Round 1 resolved bindings from the
HEAD manifest only, and treated "no `acs[ac_id]` node" as report-only. Because that node is
produced from `@pytest.mark.covers("FR-xx/ACnn")` tags, **deleting the `/ACnn` suffix from one tag
in the same PR converted a HARD block into a silent exit 0** — the assertion-weakening class
§5.4's own reasoning says must be closed, arriving through the binding side instead of the marker
side. Ruling Q2 (spec-side-only detection) makes the binding side the gate's *only* other input,
so it must not be freely subtractable.

- **Base manifest** — read via `git show <base_sha>:.shipwright/compliance/test-traceability.json`.
  **No regeneration.** A link count under `acs[ac_id].tests` is a *structural* claim, not an
  execution claim, and base is an ancestor of `origin/main`, so §5.1's already-merged-is-trustworthy
  argument covers it.

  **This read is THREE-WAY and fail-closed — it must NOT follow the house `git show` pattern
  (round-4 finding 1, HIGH).** Round 3 ruled only the "base predates manifest v4" case (no `acs`
  node → zero links → correct degradation) and left two others unruled. That matters because the
  surrounding repo defaults a failed `git show` to **permissive/empty** — `check_agent_doc_budget
  ._base_text` and `anti_ratchet.measure_staged` both do; only `_layer_coverage_ac.spec_text_at` is
  deliberately three-way. A builder copying the house pattern here would make base silently `{}` on
  *any* read failure, which **(a) disarms `binding_removed` for that PR** (zero base links → falls
  to `unbound` → exit 0, reopening the round-1 `@covers`-suffix dodge) **and (b) collapses
  `_spec_paths(head, base)` to head-only**, reopening round-3's spec-rename gap. Mirroring
  `spec_text_at`'s discipline instead:

  | case | how it is told apart | verdict |
  |---|---|---|
  | (i) the path is genuinely **absent** at base (a repo/PR predating the compliance file) | `git cat-file -e <base>:<path>` fails **while** `git rev-parse --verify <base>^{commit}` succeeds — the same two-step `spec_text_at` uses | **proceed** with `base_links == 0` for every AC, **and emit a `base_manifest_absent` warning key in the JSON**, so the degradation is *logged*, never silently inferred |
  | (ii) the blob **exists** but is unparseable JSON / not an object | `git show` succeeds, `json.loads` raises | **exit 2** — a corrupt *existing* manifest is a genuine infra fault, categorically unlike an honestly-absent one |
  | (iii) git itself fails for any other reason (bad ref, unreadable object DB, timeout) | `rev-parse --verify` on the commit fails, or `git show` fails on a path `cat-file -e` said exists | **exit 2**, same as AC-K9(c) |

  **The consequence of case (i), stated rather than left inferrable:** for that PR
  `binding_removed` cannot fire (nothing to have been removed *from*) and `_spec_paths` degrades to
  head-only. That is the honest reading when the base genuinely has no manifest — but it is exactly
  the state an attacker would want, so it is **warned about in the output** rather than silently
  taken. It is unreachable in this repo today (the manifest has existed since long before any live
  branch point) and is pinned by AC-K9(e).
- **Head manifest** — the **regenerated** file (§5.7), never the committed one.
- In-repo precedent for exactly this shape: `check_repair_safety.py` + `assertion_weakening.py`
  already reason about *"coverage that disappeared"* over the merge-base diff.

For each `changed` AC `(fr_id, ac_id)`:

| outcome | condition | verdict | remedy named in the message |
|---|---|---|---|
| `binding_removed` | base had ≥1 link for `(fr_id, ac_id)`, head has none, **or fewer than base** (Stage-3 doubt review, high — a partial reduction is the same dodge in miniature) | **HARD** | restore the `@covers("FR-xx/ACnn")` binding(s), or justify the removal/reduction in review |
| `failed` | head link with `executed == "fail"` | **HARD** | fix the code, or update the test as the TDD expression of the new AC (§1.4.1 case 1) |
| `skipped` | head link with `status != "enabled"` | **HARD** | *"a green-but-skipped test does not satisfy the gate"* — `evaluate_cross_layer`'s own wording |
| `not_selected` | head link `status == "enabled"` and `executed == "not_run"` | **HARD** (§5.4) | this AC's binding names a test this run did not execute; retag to one it does, or fix evidence staging |
| `unbound` | `base_links == 0 and head_links == 0` | **report-only, exit 0** | p3.7's anti-ratcheted feeder owns this (§3(b)); §2.1 measures 259 of 268 in this state |

**ONE vocabulary: LINK COUNTS, never node presence (round-4 finding 2, HIGH).** Define, for each
`changed` AC, exactly two numbers — and derive every outcome from them alone:

```python
base_links = len(flatten(base_manifest ... acs[ac_id]["tests"].values()))   # 0 if any level absent
head_links = len(flatten(head_manifest ... acs[ac_id]["tests"].values()))   # 0 if any level absent
```

| `base_links` | `head_links` | outcome |
|---|---|---|
| ≥ 1 | **0** | **`binding_removed`** (HARD) |
| ≥ 1 | **1 ≤ head_links < base_links** | **`binding_removed`** (HARD — added Stage-3 doubt review, high; see below) |
| 0 | 0 | `unbound` (report-only, exit 0) |
| 0 | ≥ 1 | newly bound → the ordinary greenness walk |
| ≥ 1 | `head_links >= base_links` | the ordinary greenness walk |

**The reduction row (Stage-3 doubt review, high, found during this build).** The table as
originally shipped tested `head_links` for *emptiness* only, via a bare `if not head_links`. A PR
that drops one of several `@covers` tags on a multiply-bound AC (base 2 links, head 1) is `≥1 / ≥1`
in that reading, so it fell through to the ordinary greenness walk over the surviving link — which
can be green — silently discharging the changed criterion's obligation with a test that was never
about it. `len(head_links) < len(base_links)` closes this the same way the zero case already does:
same reason code (`binding_removed`), same remedy (restore what was dropped), because reducing a
binding and removing it outright are the same dodge at different scales. Pinned by
`test_a_partial_binding_reduction_on_a_changed_ac_is_also_binding_removed`, written to fail against
the emptiness-only phrasing.

**Why this replaces round 3's node-presence phrasing.** Round 3 stated the precedence rule in
*node* terms ("base-yes/head-no" = presence of the `acs[ac_id]` node) while the outcome table
above stated it in *link* terms. The two vocabularies **disagree on exactly one input**: base has
a node with ≥1 link, head has a node whose `tests` is empty. In link terms that is
`binding_removed` (HARD — correct). In node terms head is "yes", so it is neither
`binding_removed` (needs head-no) nor `unbound` (needs base-no) and **falls through to the
greenness walk, whose ∀-over-an-empty-set is vacuously true → exit 0** — round 1's dodge again,
through a narrower door, and AC-K8 inherited the node vocabulary verbatim so a builder following
it literally would have reproduced the hole. Whether the `@covers`-driven generator can actually
emit a node with an empty `tests` map is unverified and may be unreachable in practice; the fix
costs one definition and removes the ambiguity regardless. **Node presence therefore appears
nowhere in the predicate — not in the table, not here, not in AC-K8.**

**Guard the ∀ walk against the empty set — assert and route, never pass vacuously.** The greenness
walk is only ever entered with `head_links >= 1`; entering it with zero links is a programming
error, not a pass. `_keystone_core` raises on that input rather than returning "all green", and a
test pins it (AC-K16). This is the same ∃/∀ trap §2.4 devotes a whole section to, arriving from
the other side: §2.4 guards against *one* green link satisfying a set that should need all;
this guards against *zero* links satisfying it trivially.

Every bound link at every layer must be `status == "enabled" and executed == "pass"` — **∀, not
∃** (§2.4, AC-K6). `not_selected` is read from the manifest's `executed` field **only**, never by
matching link ids against JUnit/console node ids (§2.3's node-id-space finding; AC-K7).

### 5.4 `not_selected` is HARD — ratified, and now on zero-population evidence

Ruling Q3 ratified the principle: no advisory softening, no forced rerun. Reasons, updated with
§2.3's corrected numbers:

1. **Any softer treatment makes the gate dodgeable by a one-line decorator** — the same
   assertion-weakening class §1.4.1 calls *"die wichtigste Nicht-Umgehbarkeits-Regel der
   Campaign"*.
2. **The pre-existing population is ZERO, not one.** All 142 bound links reached `PASSED` in the
   real CI run at `main`'s tip (§2.3). Round 1's claim of one landmine was measurement error.
3. **It fails in the safe direction on infrastructure trouble.** Broken evidence staging makes
   every link `not_run` → block, never a silent pass — the posture `_layer_coverage_regen` already
   takes (*"the head manifest is built with EMPTY evidence (fail-closed → every layer `not_run`)"*).

**Rejected alternative — the forced rerun (D10's literal wording).** Re-execute the changed ACs'
bound tests by node id with no marker filter. Attractive (dissolves `not_selected`; evidence
produced and consumed by the gate itself) but **rejected**: it needs one pytest invocation per
test root (ADR-044's hard one-root-per-process rule; bound tests span `shared/tests`,
`plugins/*/tests`, `integration-tests`), per-root environment provisioning, and its own JUnit
merge — a second execution surface inside the campaign's highest-stakes unit, for a population of
zero. The `not_selected` HARD outcome is **forward-compatible** with adding it later: a rerun only
ever converts a block into a pass.

### 5.5 "Highest layer mandatory" — reuse P3.3's *ranking and routing*; the predicate itself is NEW

**What is reused vs. what is new (round-3 finding 5 — round 2's heading overclaimed).**
`_layer_coverage_binding.evaluate_binding_completeness` tests the **inverse** direction of what
this gate needs: it fires when the run's observed evidence **outranks** the declared
`required_layers` (`_layer_coverage_binding.py`: `if _LAYER_RANK.get(highest_ok, -1) <=
max_required_rank: continue` — i.e. it flags an *under-declared binding*). AC-K10 needs the
opposite: an AC's binding covering **less** than its FR requires. **So `evaluate_binding_completeness`
is NOT called here** — a builder reaching for it would implement the wrong test. Reused are the two
genuinely shared pieces: **`_layer_coverage_binding._LAYER_RANK`** (the canonical layer ordering)
and **`_layer_coverage_core.route_gap_severity(ambiguous=…, source=…)`** (the shared severity rule
P3.3's own external plan review insisted on so two gates cannot drift). The comparison predicate is
new and lives in `_keystone_core`.

For each `changed` AC, compare the layers its binding covers against the owning FR's
`required_layers` using that ranking, and route severity through that rule:

- `required_layers_source == "explicit"` → **HARD**
- a known legacy source (`inferred_legacy` / `defaulted_legacy`) → **ADVISORY** (pre-rollout valve)
- a collision display id → **ADVISORY** regardless

**All 20 FRs are `inferred_legacy` today**, so this arm is advisory on day one and becomes hard
**exactly as P3.5 promotes each FR** — one FR at a time, never in a sweep (D5). The keystone gate's
sharpness is governed by P3.5's ledger, which is what "P3.5 is the Zubringer" means mechanically.

### 5.6 AC-3 — "a docs-only PR passes untouched" falls out with zero machinery

A docs-only PR changes no criterion text → empty change set → clean pass, having read nothing else.
No path allowlist, no production/docs classification, so no brush against Track R (§3(a)). Even a
PR editing `spec.md` *prose outside any criterion* passes. The only way a docs-only PR fires this
gate is by editing an acceptance criterion — at which point it is not docs-only. (AC-K1)

### 5.7 Where it runs

**One new `ci.yml` step, `pull_request` only.**

```yaml
- name: Keystone AC gate (gate)
  # P3.6. MUST come after "Check traceability manifest against a fresh regeneration":
  # that step regenerates .shipwright/compliance/test-traceability.json IN PLACE from
  # THIS run's real JUnit output, so the committed file's own claims are already
  # overwritten before this gate reads them. Regeneration happens BEFORE that step's
  # own comparison, so this holds even while `main` carries the structural drift
  # measured in the design's 2.3 -- drift-code 1 is advisory and the job continues;
  # drift-code 2 fails the step and this one never runs (fail-closed).
  # pull_request only: the keystone gate is a MERGE condition (SPEC 1.4). A push run
  # has no PR to block and no base to diff against.
  # Name ends in "(gate)": check_ci_gate_coverage.GATE_NAME_KEYWORDS enrols it, so a
  # future `continue-on-error` on it is caught as a loose, un-allowlisted gate.
  if: github.event_name == 'pull_request'
  run: uv run shared/scripts/tools/check_keystone_ac_gate.py --project-root . --head-sha "${{ github.sha }}"
```

- **No new Required Check.** The step lives inside the existing `python-checks` job, which is
  already a Required Check. Branch protection untouched.
- **Base resolution reuses `_layer_coverage_regen._merge_base(project_root, head_sha)`** — the
  existing, reviewed helper (`origin/HEAD` → `@{u}` → `origin/main`/`master` → local; `""` ⇒
  fail-closed). Never a bare `origin/main` diff, never `commit^` (the MUST-FIX 4 that helper
  carries). The **same** base SHA is used for the spec text and for the base manifest (§5.3), so
  the two sides cannot disagree about which commit they describe.
- **`origin/main` availability — round 1's concern investigated and WITHDRAWN (round-2 edit 4).**
  `actions/checkout@v4` with `fetch-depth: 0` (ci.yml line 40) populates `refs/remotes/origin/*`
  repo-wide, so `origin/main` is present. Round 1's proposed fix — ordering the keystone step after
  *"Diff coverage (gate)"* — was **wrong regardless**: that step is conditional
  (`if: hashFiles('coverage.xml') != ''`), so it would pin a hard precondition on a soft
  dependency, and removing diff-coverage later would silently break the keystone gate with a
  passing shape test. **The ordering clause is dropped from AC-K12.** Instead the step is made
  *self-sufficient* — but **the precondition is `_merge_base`'s own verdict, not a hardcoded ref
  name (round-3 finding 3).** Round 2 proposed `git rev-parse --verify origin/main`, which
  contradicted this same section's own resolver description one bullet earlier: `_merge_base`
  (`_layer_coverage_regen.py:112-133`) tries `origin/HEAD` → `@{u}` → `origin/main` →
  `origin/master` → local `main` → local `master`, so a repo whose default branch is `master`, or
  one resolving through its tracking upstream, would have exited 2 as a false "infra fault" on a
  base `_merge_base` would have resolved fine. **Correct shape: call `_merge_base` first; exit 2
  with the `git fetch --no-tags origin <default-branch>` remedy ONLY when it returns `""`** — the
  one signal that genuinely means "no base could be resolved by any route". (The shared
  `diff-coverage-gate` action does its own `git fetch --no-tags origin "$base"` for a different
  reason: it is consumed by repos that may not use `fetch-depth: 0`.)
- On a `pull_request` event `github.sha` is the **merge commit** and is what the workspace has
  checked out, so `merge-base(<the ref _merge_base resolved>, github.sha)` — **not a literal
  `origin/main`; see the bullet above** — resolves to the base-branch tip and the
  diff is exactly the PR's own changes.
- **Exit codes 0/1/2** (ruling Q6) — and for the sharper reason the ruling gives: it matches
  `ci_manifest_drift_check`'s own 0/1/2 convention two steps earlier in the **same job**, so the
  job does not carry two exit-code dialects. `0` clean (incl. advisory-only) · `1` a HARD finding
  or the reader-divergence authoring finding · `2` genuine infra fault only. JSON verdict on
  stdout, always.

### 5.8 What is deliberately NOT built

- **No `ac_id → tests → last_verified_commit` baseline** (ruling Q1).
- **No forced rerun** (§5.4, ruling Q3).
- **No F11 advisory arm this round** (ruling Q4) — the seam is kept, the adapter is not shipped.
- **No post-merge detective arm** (ruling Q5) — own card, filed at merge.
- **No edit to `test_gitleaks_extend_smoke.py`** (§2.3, ruling Q3's specific instance).
- **No change to `test-traceability.json`'s schema.** v4 already carries everything this gate
  reads; the manifest is a frozen, churn-allowlisted contract.
- **No change to `_cov_status`, `evaluate_cross_layer`, `evaluate_binding_completeness`,
  `ci_manifest_drift_check.py`, or `mint_ac_ids.py`.** p3.6 is purely additive.

---

## 6. Rollout validation and probes

**Pre-merge, provable:** every acceptance criterion in `## 9` is a real test. Three **real,
non-mocked** probes must run and be reported before build is considered done:

- **Probe A — the hand-edit is inert.** Hand-edit the committed manifest to claim a changed AC's
  bound tests are green; run the gate against a regenerated manifest. Verdict unchanged. Turns §4's
  central claim into evidence. (AC-K13)
- **Probe B — real spec, real git; now also the base-manifest read.** Run `ac_criteria_digests`
  over the real `spec.md` at `545a4f320^` and `545a4f320` and confirm the change set matches
  §2.2's measured shape. **Extended (round-4 finding 1, near-zero cost since this probe already
  drives real git):** also perform the base-manifest read at a real commit **predating
  `.shipwright/compliance/test-traceability.json`'s existence**, and confirm it takes case (i) —
  `base_links == 0` plus a `base_manifest_absent` warning — rather than case (ii)/(iii). This is
  what turns §5.3's three-way rule from *reasoned* into *probed*, closing the one boundary §11
  item 7 has flagged as un-probed since round 2.
- **Probe C — the dodge is closed.** On a synthetic branch, delete the `/ACnn` suffix from a
  `@covers` tag bound to an AC whose criterion the same branch edits; assert `binding_removed`
  HARD, and assert the same scenario exits 0 under a head-manifest-only resolution (i.e. the test
  fails against round 1's design). (AC-K14)

> **RESULTS — all three ran at build time. Reported here rather than only claimed, because the
> paragraph above says "must run *and be reported*".** External code review (glm, medium) found
> Probe B present in the design and absent from the build; that was true, and it is what this
> block closes.
>
> - **Probe A — RAN.** `test_a_hand_edited_committed_manifest_cannot_flip_the_verdict`: a manifest
>   committed claiming `executed: pass` for the changed AC, with the regenerated bytes on disk
>   claiming `fail`. Verdict: exit 1, `failed` — the committed forgery is inert, and the test
>   re-reads `HEAD:` to confirm the forged bytes really were what was committed.
>   *Partially synthetic, and now disclosed as such:* the test writes the regenerated bytes itself
>   rather than driving `ci_manifest_drift_check`. External code review (openai, medium) is right
>   that this would survive the regeneration step ceasing to overwrite in place — so
>   `test_the_regeneration_step_overwrites_the_very_file_the_gate_reads` pins the two-way path
>   identity structurally, and a fuller regeneration-integration probe is deferred with a card.
> - **Probe B — RAN, against real repo history, and it matches §2.2 exactly.**
>   `ac_change_set` over the real `spec.md` at `680f46f0b9cb` → `545a4f32043b` (the P3.4 mint
>   commit): **268 added, 0 changed, 0 removed, 0 unminted, 0 reader-divergence, 0 warnings** —
>   the measured shape §2.2 predicted, arriving through the shipped code path rather than a
>   reconstruction of it. The base manifest at that commit read cleanly (20 requirements, no
>   warning).
> - **Probe B, extended arm — RAN, and case (i) is now PROBED, not reasoned.** The base-manifest
>   read at `e74d8090758e` (the commit immediately preceding `c8767470f`, which first added
>   `.shipwright/compliance/test-traceability.json`) returns `({}, warning)` — case (i) — with the
>   warning naming the degradation verbatim. A third measurement covers the v3-era shape the
>   design only reasoned about: at `c8767470f` the manifest exists with **15 requirements and zero
>   non-empty `acs` nodes**, so `base_links == 0` for every AC and `binding_removed` structurally
>   cannot fire — the reasoning in §11 item 7 (iii) confirmed by measurement.
> - **Probe C — RAN.** `test_dropping_the_ac_suffix_while_editing_the_criterion_is_binding_removed`
>   (exit 1, `binding_removed`) plus its companion, which re-evaluates the *identical* change set
>   under round 1's head-manifest-only resolution and shows it exits 0. The dodge is closed, and
>   the test demonstrably fails against the design it replaced.

**Post-merge, operational (tracked, not a pytest AC):** report the first real PR that fires the
gate — which arm, which ACs, what verdict. Non-firing across ten merged PRs is expected per §2.2
and is not evidence of a defect; the *false-red* count is the number that matters.

---

## 7. Known limitations (disclosed, not fixed)

> ### DEVIATION 3 — an `added` AC that ALREADY has a binding is greenness-walked
>
> **This reverses a rule ratified across all four plan-review rounds, so it is named here rather
> than left to be discovered in a diff.** Found by a Stage-1 spec review, which rejected the
> build for shipping the change while three passages of this document still asserted the opposite.
>
> **Attribution, plainly: no reviewer asked for this. It was found during build.** An earlier
> version of the code comment and its test credited "external code review (openai, high)" — that
> is wrong, and the correction matters because a fabricated mandate is worse than an undocumented
> one. The openai-high code-review finding is the Track R / Q2 scope objection, **rejected** in
> §12.1. The plan review's AC-id-rotation finding is dispositioned **"reported, not blocked"** and
> remains so.
>
> **The rule.** `added` ACs with `head_links == 0` stay report-only, exactly as designed.
> `head_links >= 1` now takes AC-2's greenness walk. Why, in four steps:
>
> 1. **Source AC-2 covers it literally** — "a **named** AC whose bound test did not run green
>    blocks". A newly added AC is a named AC, so exempting it is an *exception* to AC-2 and owes a
>    justification of its own.
> 2. **The design's justification is an assumption, not a property.** §5.1's parenthetical, "a new
>    criterion has no binding — p3.7's baseline", is the entire stated basis. When the criterion
>    *does* arrive carrying a `@covers` tag, the premise is false and nothing is left holding the
>    exemption up.
> 3. **The empirical basis does not discriminate between the two designs.** P3.4's mint added 268
>    ACs and every one of them has zero links, so the `head_links >= 1` gate keeps that PR silent
>    either way. The 268 measurement was never evidence for *this* choice — it is evidence for the
>    `head_links == 0` branch, which is unchanged.
> 4. **Remediability — the discriminator this document already uses — points the other way here.**
>    The `removed_with_bindings` arm stays report-only because "base had links" is *unfixable
>    inside the PR*: base is immutable. An added AC's red binding is entirely fixable in the same
>    PR (fix the test, fix the code, or drop the tag). Same test, opposite answer; applying it
>    consistently means this one blocks.
>
> **Scope — greenness ONLY, deliberately narrower than the `changed` arm.** `layer_gap` is *not*
> called on this arm. Greenness of a binding that exists is what AC-2 says; layer **breadth** for a
> brand-new criterion is *coverage*, which is p3.7's, and it is the arm that would start
> false-redding the moment p3.5 promotes an FR to `explicit` — add one criterion with a unit test
> to an FR requiring e2e and a symmetric implementation blocks the PR for work nothing asked for.
> A deviation should be exactly as wide as its justification. Pinned by
> `test_an_added_ac_is_NOT_layer_gap_checked_even_with_explicit_provenance`, which asserts the
> identical fixture HARD-blocks under `changed` and produces nothing under `added`.
>
> **What this does NOT do:** it does not close the id-rotation hole (a rotated id arrives with no
> binding), and it does not make p3.6 a coverage gate. Both remain p3.7(b)'s.

- **Exactly as strong as `ci.yml`** (§4). Deliberate; not hidden.
- **Mint before gating.** A repo adopting this gate *before* minting would see every criterion as
  `unminted_changed` on its first spec edit. True precondition; already satisfied here (P3.4
  merged). **And the minter is not wired into any authoring flow** — it is a manual
  `mint_ac_ids.py --write` today (its own docstring says so), so arm 1's remedy is a hand step.
  Wiring it is P3.3's *emit* half, tracked as `trg-875104ac`, explicitly not p3.6's.
- **`main`'s tip still carries pre-existing structural manifest drift** (§2.3) — so
  `resolve_ci_verification` reports `not_verified` and no execution-evidence artifact exists for
  any commit yet. Not p3.6's to fix and not a p3.6 dependency (§5.7), but it means p3.5's own
  mechanism is still unvalidated end-to-end, and the eventual detective arm (Q5) will need it
  resolved first.
- **Only `spec_path`s named by the base or head manifest are scanned** — the **union** of both
  (§5.1, round-3 finding 4), so a spec file added, renamed or **removed** across the PR is still
  compared from the side that has it. The residual limitation is narrower than round 2's: a
  criterion living in a spec file that **neither** manifest's requirements point at is invisible —
  the same scope `_layer_coverage_ac._spec_paths` has by design, since a spec no active requirement
  references is not part of the requirement graph this gate enforces over.
- **AC-level *coverage* is not gated, only AC-level *greenness* and *binding retention*.** 259 of
  268 ACs have no binding and the gate is silent on them by design. The honest description of
  p3.6's reach: *it protects the 9 ACs that are bound, it prevents a bound AC from being quietly
  unbound, and it grows automatically as binding does.* **This is the single most important
  sentence for the PR body** — overstating reach is how a keystone gate becomes theatre.
- **A test's body can be weakened without the gate noticing.** §1.4.1's answer stands: the
  test-body suspect check is p3.7 (advisory), the review layer is the doubt-reviewer. Mechanics
  raise the flag; a human decides. p3.6 does not and cannot close this.
- **`binding_removed` fires only for ACs in the `changed` set — and the SINGLE-PR shape is worse
  than the two-PR one below (external plan review, 2026-09-09: glm medium + openai high, found
  from opposite directions).** Deleting a minted criterion outright, or **rotating its id**
  (`[AC01] foo` → `[AC55] foo TWICE`), reads as `removed` + `added`. `removed` is report-only, and
  the `added` side blocks only if the NEW id already carries a binding (deviation 3 below) — which
  a freshly rotated id does not — so **one PR** can still discard an AC-to-test obligation without
  ever entering the `changed` set. **Disposition: reported, not blocked, and
  the reason is that no remediable predicate exists at this layer.** Blocking on "base had links"
  is *unfixable inside the PR* — base is immutable, so an author legitimately retiring a criterion
  *and* its test would fail forever with no action available. The predicate that IS remediable —
  *the criterion is gone but its `@covers` tag survives, now pointing at nothing* → remove or
  retarget the tag — is precisely **p3.7(b)'s orphan detector, hard from day one** (SPEC §8 E2);
  building a second copy here is how two gates drift, which this campaign has already paid for
  once. So p3.6 emits a dedicated **`removed_with_bindings`** key in its JSON on every PR, and
  (Stage-3 doubt review, low) also a `::warning::` workflow-command annotation to stderr when it is
  non-empty, since the JSON key alone is invisible in an otherwise-green exit-0 CI log unless a
  consumer already knows to look for it. p3.7(b) blocks
  it. Named explicitly on p3.7(b)'s card (§10 item 8b) alongside the two-PR sequence.
- **`pull_request`-only means a direct push to the default branch is ungated** (external plan
  review, glm). Consistent with "the gate is a merge condition", and every change here goes
  through a PR, but it is a *different* trust assumption than "exactly as strong as `ci.yml`":
  that claim is about the *content* of `ci.yml`, this is about *event routing*. An actor with
  direct push access bypasses the gate without touching `ci.yml` at all. A `merge_group` trigger
  would open the same hole silently, so AC-K12 carries a tripwire test asserting `ci.yml` has none.
- **`binding_removed`'s two-PR unbind sequence.** Unbinding an AC whose text this PR does not touch is invisible to
  p3.6. Concretely: **PR1** deletes the `/ACnn` suffix from a `@covers` tag and changes no AC text,
  so nothing is in the `changed` set and `binding_removed` cannot fire; **PR2**, later, edits that
  AC's text against a base where it is *already* unbound, so it reads `unbound` (exit 0) rather
  than `binding_removed`. Splitting the dodge across two PRs defeats the single-PR check. Closing
  it needs a signal that does not depend on the AC's text changing — which is exactly p3.7(b)'s
  "a test whose AC vanished" orphan detector, hard from day one. **This sequence is written into
  p3.7's follow-up card as a named input (§10 item 8), not left implicit**, because it is the one
  residual path through the hole finding 1 opened.
- **One spec file, one namespace today.** Collision handling is inherited from
  `collision_display_ids` / `route_gap_severity` (advisory), untested against a real
  multi-namespace repo because none exists here.
- **Invoked locally at a commit that IS its own merge-base, the gate exits 2 with a *fetch*
  remedy that does not apply** (found by the F0.5 surface run, not by any reviewer). `_merge_base`
  rejects a candidate whose merge-base equals the commit under test — deliberately, since that
  would be a zero-width diff — and returns `""`, which this gate maps to the fetch-depth message.
  **Structurally unreachable in CI:** on a `pull_request` event `github.sha` is the merge commit,
  which carries the PR's own commits and therefore never equals the merge-base; GitHub will not
  create a PR with no commits. Not fixed here because the alternative — exiting 0 on "I could not
  tell" — is precisely the fail-open this design refuses, and because `_merge_base` is shared with
  the P3.3/P3.5 gates and is not p3.6's to re-shape. Local reproduction takes an explicit
  `--base-sha`, which the flag exists for.
- **Retiring a requirement *while* editing its criterion reports `binding_removed`, whose remedy is
  then unactionable** (external code review, glm low). `_links_for` counts ACTIVE nodes only — a
  deliberate fail-closed fix in its own right — so flipping `status` to `retired` in the same PR
  that edits the criterion zeroes `head_links` and produces "restore the `@covers` tag", which
  still exists. The outcome **blocks**, so nothing is let through; only the message misroutes, and
  a reviewer reading the JSON sees the retirement in the same diff. Not fixed because the fix costs
  a fourth reason code and a fourth arm, for a flow this repo has never performed — a cost
  independent of `_keystone_core.py`'s current line count (239 after the Stage-2 code-review fix
  named the reduction's missing link ids, §12.1i finding 6; no longer at the 300-line limit that
  was the stated reason when this was first written). Recorded so that the first real occurrence
  is a two-line follow-up rather than a mystery.
- **The `failed` HARD arm is practically unreachable from `ci.yml` itself, only from the unit-test
  fixtures that exercise the pure evaluator directly** (Stage-3 doubt review, informational).
  `ci.yml`'s test steps run under `set -e`: a real test
  failure stops the job before this gate's step ever executes, so in normal CI operation `failed`
  can only be observed with a stale/hand-edited manifest claiming `executed: "pass"` for a test that
  did not actually run green this invocation — which the regeneration step (§4, AC-K13) already
  forecloses. The reason code is not dead code: it is the correct answer for that adversarial input,
  and `SKIPPED`/`NOT_SELECTED` remain reachable through ordinary `pytest.mark.skip`/deselection. Not
  a defect, recorded so a future reader does not "simplify" the arm away as unreachable.
- **The reduction check compares a REGENERATED head manifest against a STALE-BY-CONSTRUCTION base
  one** (Stage-2 code review, medium). `head_manifest` is regenerated from THIS run's own JUnit
  (§4, AC-K13), but `base_manifest` is read from the last COMMIT at base (§5.7) — the same "the
  two are known to drift" gap ruling Q1b already accepts for the new-FR-without-criteria arm. A
  base commit whose manifest under-counts links relative to what actually existed at base (stale
  regeneration, a hand-edit, an interrupted mint) can make `len(head_links) < len(base_links)`
  read as SMALLER than the true reduction, or manufacture a reduction that never happened. Not
  fixed: base is immutable by definition (§5.7's whole justification for reading it as a JSON
  artifact rather than regenerating it), so there is no "more current" base to compare against
  inside this PR — the same remediability argument deviation 3 already applies to `removed`.
- **A cardinality-only reduction check can be defeated by a constant-count retag** (Stage-2 code
  review, medium). `len(head_links) < len(base_links)` catches a link COUNT dropping, but two
  links whose ids both rotate to point at DIFFERENT tests of the same count leaves the count
  unchanged, so `binding_removed`'s reduction arm does not fire even though every original binding
  is gone. Not fixed: closing it needs per-link IDENTITY tracking (not just counts), which is the
  same "one vocabulary: LINK COUNTS" scope §5.3's tables already commit this gate to, and the
  identity-level question ("does this test still cover what it claims to") is p3.7(b)'s orphan
  detector's, not a count-based structural check's.

---

## 8. Rulings adopted — all eight, none open

**Deviation count: THREE, not two.** Q1 and Q1b were ratified at the plan gate. **Deviation 3**
(§7) was taken at build time and **ratified (2026-09-10, coordinator)** after Stage-1 round 2
passed fresh against it. Any passage of this document claiming "exactly two deviations" without
naming the third is stale — a Stage-1 spec review rejected the build for exactly that.

| # | Ruling | Where it lands |
|---|---|---|
| **D3** | **RATIFIED (2026-09-10, coordinator).** An `added` AC that already carries a binding takes AC-2's greenness walk (`head_links >= 1`); unbound `added` ACs stay report-only, and no layer-gap check applies to this arm at all. Taken during build because AC-2 names *any* named AC and the design's exemption rested on an assumption that fails when the criterion arrives tagged. **No reviewer requested it.** Full four-step reasoning and scope: §7's deviation-3 block. | §5.1 table, §7, AC-K4 |
| Q1 | **Drop D9's `last_verified_commit` baseline.** ci.yml re-runs every suite on every PR; nothing selective for a ledger to compensate for, and a stored baseline is a self-reported trust artifact — the class that cost PR #690 twelve rounds. **Condition:** record the deviation from the Scope line in **both the PR body and the module docstring**. | §5.8, §11 item 1 |
| Q2 | **Spec-side-only "behaviour-changing" is correct.** **Conditions:** (i) state verbatim in the PR body — *"a PR that changes behaviour in code and changes no acceptance criterion passes this gate untouched; it enforces spec-to-test consistency, not code-to-spec consistency"*; (ii) paired with finding 1 — spec-side-only means the binding side must not be silently subtractable. | §3(a), §5.3 |
| Q3 | **`not_selected` HARD; no advisory softening, no forced rerun.** Specific instance (retag `FR-01.07/AC06`?) → **no**, on re-measured evidence. | §5.4, §2.3 |
| Q4 | **CI-only this round; no F11 advisory arm.** Keep the adapter seam in `_keystone_core`. | §5.0, §5.8 |
| Q5 | **Detective arm = own triage card, filed at merge.** The card must name `resolve_execution_evidence` and the misclassification cases **explicitly**, not "detective arm TBD" — the `trg-875104ac` lesson. | §4, §10 item 8 |
| Q6 | **Exit 0/1/2**, matching `ci_manifest_drift_check`'s dialect in the same job. Rider: exit 2 only means something once finding 3 is fixed. | §5.7, §5.1 |
| Q1b | **RATIFIED (2026-09-09, coordinator).** §5.2 replaces the sub-iterate spec's author-*declared* "named ACs" with **spec-derived detection** — *"a derived signal is unforgeable where a declaration isn't"*, the same reasoning as Q2's ruling. Round 1's §11 wrongly reported this as compliance with only Q1 flagged as a deviation; there are **two**, and both are now ratified. **Condition, inherited from Q1:** stated in the PR body AND in `check_keystone_ac_gate.py`'s module docstring. | §5.2, §11 item 1 |

---

## 9. Acceptance criteria (assertion-shaped)

The sub-iterate spec's three ACs still apply; these are the testable form.

- **AC-K1 (docs-only, AC-3):** a PR touching only `docs/` + `README.md`, and a PR editing `spec.md`
  prose *outside* every criterion, both produce an empty change set, exit `0`, and read no
  manifest node.
- **AC-K2 (naming, AC-1 arm 1):** (a) a **minted** criterion whose marker is deleted → arm 1 fires,
  exit `1`; (b) **sibling case** — a criterion **added** with no `[ACnn]` → arm 1 fires, exit `1`;
  (c) an unminted criterion that survives the PR byte-identical → does **not** fire. The message
  names the real `mint_ac_ids.py --write` command and the registry file.
- **AC-K3 (precision):** reordering two minted criteria within one FR block, and re-wrapping one
  criterion's continuation lines, each produce an **empty** change set.
- **AC-K4 (added minted AC: report-only when UNBOUND, greenness-walked when bound — DEVIATION 3,
  §7):** a new `[ACnn]` present only at head with **no binding** → `added` + `unbound`, exit `0`
  (this is the 268-AC mint case, and it is what keeps that PR silent). The **same** new `[ACnn]`
  arriving **with** a `@covers` tag whose link is `fail` / `disabled` / `not_run` → exit `1` with
  that link's reason code; with every link `enabled` + `pass` → exit `0`. **No layer-gap check on
  this arm** in either case — the identical fixture that HARD-blocks under `changed` must produce
  nothing under `added`.
- **AC-K5 (greenness, AC-2):** a `changed` AC with a bound link `executed: "fail"` → exit `1`; the
  same AC with every bound link `enabled` + `pass` → exit `0`.
- **AC-K6 (∀ not ∃ — the §2.4 defect):** a `changed` AC with two bound links at one layer, one
  `pass` and one `fail` → exit `1`. Asserted *specifically against* the verdict `_cov_status` would
  give (`"ok"`), so a future "simplification" back to `coverage[layer] == "ok"` fails loudly.
- **AC-K7 (`skipped` / `not_selected`, and the node-id-space trap):** `status != "enabled"` → exit
  `1`, reason `skipped`; `enabled` + `not_run` → exit `1`, reason `not_selected`. Distinct reason
  strings, each naming its own remedy. **Plus:** a class-nested bound test whose manifest link id
  omits the class and whose `executed` is `"pass"` → exit `0` — pinning that the verdict comes from
  the manifest's `executed` field and never from node-id matching against JUnit output (§2.3).
- **AC-K8 (unbound is p3.7's — stated in LINK COUNTS, never node presence):** a `changed` AC with
  `base_links == 0 and head_links == 0` → exit `0`, and the AC appears in the JSON's `unbound`
  list for p3.7 to consume. **Four companion assertions pin the one vocabulary (§5.3):**
  (a) `base_links >= 1, head_links == 0` → `binding_removed`, exit `1` (AC-K14);
  (b) **`base_links >= 1` with a head node PRESENT but `tests` EMPTY → `binding_removed`, exit
  `1`** — the exact input on which the node vocabulary and the link vocabulary disagreed, written
  to fail against round 3's node-presence phrasing; (c) `base_links == 0, head_links >= 1` → the
  ordinary greenness walk, not `unbound`; (d) **`base_links >= 1, 1 <= head_links < base_links` →
  `binding_removed`, exit `1`** (Stage-3 doubt review, high, found during this build) — a partial
  reduction of a multiply-bound AC's binding, written to fail against emptiness-only phrasing where
  the surviving link(s) can be green and the reduction would otherwise pass the ordinary greenness
  walk silently.
- **AC-K9 (never silent):** (a) `MalformedAcMarkerError` / `DuplicateAcIdError` at **head** → exit
  `2`; (b) the same at **base** → exit `0`, every head AC `added`/`unminted`, warning in the JSON;
  (c) `spec_text_at` → `None` at either side → exit `2`; (d) **reader divergence, SCOPED TO THIS
  PR'S DIFF** — `read_all` yields zero criteria for an active FR, `criteria_digests` yields a
  non-empty digest for the same FR, **and that FR's `criteria_digests` value differs between base
  and head** → **exit `1`** with the authoring remedy of §5.1, **never exit 2 and never "no ACs
  changed"**. Two tests, and the second is the one that matters: (i) the divergent FR **is** in the
  PR's diff (an introductory sentence added between an FR heading and its bullets) → exit `1`, not
  `2`; (ii) **a pre-existing divergence in an FR the PR does NOT touch → exit `0`** — the
  blast-radius pin, written so it fails against round 2's unscoped guard, which would have redded
  every PR in the repo (including the docs-only one AC-K1 requires to pass).
  **(e) base-manifest read, three cases (§5.3, round-4 finding 1):** (i) the path is absent at a
  valid base commit → exit `0`/`1` on the merits with `base_links == 0` **and** a
  `base_manifest_absent` key present in the JSON output — asserted explicitly, so a silent
  degradation fails the test; (ii) the blob exists but is unparseable JSON → **exit `2`**;
  (iii) `git show` fails on a path `cat-file -e` reported as present → **exit `2`**. Case (i)'s
  test also asserts the gate did **not** report `binding_removed` for an AC whose head binding is
  gone — i.e. the disarming is real, which is precisely why it must be warned about.
- **AC-K10 (highest layer — ranking/routing reused, predicate new):** a `changed` AC bound only at
  `unit` whose FR requires `integration` → ADVISORY when `required_layers_source` is legacy (exit
  `0`), HARD when `explicit` (exit `1`). A drift test asserts the routing comes from
  `_layer_coverage_core.route_gap_severity` and the ordering from
  `_layer_coverage_binding._LAYER_RANK`, not local copies — **and that
  `evaluate_binding_completeness` is NOT called**, since it tests the inverse direction (§5.5).
- **AC-K11 (base resolution):** `_merge_base` returning `""` → exit `2` (fail-closed) naming the
  `git fetch --no-tags origin <default-branch>` remedy, never a green "nothing changed"; a test
  asserts `_merge_base` is the resolver used. **A companion assertion pins the round-3 finding-3
  fix: a repo whose default branch is `master` (no `origin/main` at all) but whose `_merge_base`
  resolves via `origin/master` exits `0`, not `2`** — i.e. no hardcoded `origin/main` precondition.
- **AC-K12 (CI shape):** a YAML-shape test pins the new step's `name` (ending `(gate)`), its
  `if: github.event_name == 'pull_request'`, the absence of `continue-on-error`, and — the one
  genuinely load-bearing ordering constraint — that it comes **after** the `manifest_drift` step.
  *No ordering assertion against `Diff coverage (gate)`* (§5.7).
- **AC-K13 (Probe A, real):** a hand-edited committed manifest claiming green does not change the
  verdict computed against the regenerated one.
- **AC-K14 (Probe C — the dodge, finding 1):** an AC whose criterion changed **and** whose
  `@covers` AC suffix was deleted in the same PR → `binding_removed`, exit `1`. A companion
  assertion proves the same input exits `0` under head-manifest-only resolution, so the test
  demonstrably fails against round 1's design rather than merely passing against round 2's.
  Deleting the suffix from every bound link is `head_links == 0`; deleting it from only SOME of
  several links is `1 <= head_links < base_links`, AC-K8(d)'s reduction case — same reason code,
  same remedy, a difference of degree rather than kind.
- **AC-K16 (the ∀-over-empty guard, round-4 finding 2):** calling `_keystone_core`'s greenness walk
  with an empty link set **raises** rather than returning "all green"; a test asserts the raise and
  asserts that no code path in `evaluate_keystone` can reach it (every caller is gated on
  `head_links >= 1`).
- **AC-K15 (reader-drift pin, finding 3):** a test asserts `ac_identity.read_all` and
  `_layer_coverage_ac.criteria_digests` agree on **today's real `spec.md`** (every FR non-empty in
  both), so the divergence of §5.1 is caught the day it appears.

**Test-shape constraint (round-2 edit 7 — performance).** This repo's diff-coverage gate is HARD
at 80 % with no `continue-on-error`, and **subprocess-only tests contribute 0 % to it** (a trap
this repo has hit before). So: drive `main(argv)` **in-process** for the bulk of cases,
monkeypatching collaborators **by module object**, not by import path; keep the subprocess form to
**one** end-to-end smoke case.

---

## 10. Files to create / modify

1. `shared/scripts/tools/verifiers/_keystone_ac_digest.py` (new) — `ac_criteria_digests` (minted +
   unminted), `ac_change_set(project_root, base_sha, head_sha, head_manifest, base_manifest)`.
   **1b. `_keystone_base_manifest.py` (new, added at build time)** — `read_base_manifest` + the
   shared `ReadError`. Split out because item 1 crossed the 300-LOC source limit and the two share
   nothing but the failure philosophy: one reads a JSON artifact out of git, the other reads
   criteria out of markdown. Baselining a brand-new file was the alternative and is worse.
2. `shared/scripts/tools/verifiers/_keystone_core.py` (new, pure) — `evaluate_keystone(change_set,
   head_manifest, base_manifest) -> KeystoneVerdict`; reuses `route_gap_severity` + `_LAYER_RANK`;
   defines the ∀ link predicate and the five reason codes (`binding_removed`, `failed`, `skipped`,
   `not_selected`, `unbound`).
3. `shared/scripts/tools/check_keystone_ac_gate.py` (new) — CI CLI, exit `0/1/2`, JSON stdout,
   `_merge_base`-verdict precondition (never a hardcoded `origin/main`, §5.7), base-manifest
   `git show` read.
4. `.github/workflows/ci.yml` (edit) — one step (§5.7).
5. Tests: `shared/scripts/tools/tests/test_check_keystone_ac_gate.py` (in-process `main(argv)` +
   **one** subprocess smoke), `shared/tests/test_keystone_core.py` (pure evaluator, fixtures), a
   `ci.yml` shape test (AC-K12), the reader-drift pin (AC-K15), and the three real probes (§6).
6. *(deleted — was "edit `test_gitleaks_extend_smoke.py`"; §2.3 withdrew its premise.)*
7. Docs: `docs/hooks-and-pipeline.md` (a new CI gate is a pipeline change — the CLAUDE.md rule
   binds), `docs/guide.md` ch. 8 (quality gates), `shared/glossary.md` if "keystone gate" becomes
   shared vocabulary.
8. **Two cards at merge.** (a) **Ruling Q5** — the post-merge detective arm, naming
   `resolve_execution_evidence`, the `main`-tip drift precondition (§7), and the specific
   misclassification cases it would catch. (b) **A named input to p3.7(b)'s orphan detector** —
   the **three unbind shapes** spelled out in §7, each named as a mechanism rather than "TBD" (the
   `trg-875104ac` lesson this campaign already learned): (i) the **two-PR unbind sequence** — PR1
   drops the `/ACnn` suffix with no AC-text change, PR2 later edits that AC against an
   already-unbound base; (ii) **outright deletion** of a minted criterion that had a binding;
   (iii) **id rotation** — `[AC01] foo` → `[AC55] foo TWICE`, which reads as `removed` + `added`
   and so never enters the `changed` set. p3.6 already hands the card its feeder: the
   `removed_with_bindings` key in the gate's JSON is exactly the population (ii) and (iii)
   produce, and the remediable predicate for all three is the same one — *a `@covers` tag whose
   AC no longer exists in the spec.*

---

## 11. Self-Review (Step 3.6 — 7-item checklist, re-run against the round-3 document)

| # | Item | Verdict | Note |
|---|---|---|---|
| 1 | Spec Compliance | **pass, with two named deviations** *(as of the plan gate — see the note below this table: the build added a third)* | All three sub-iterate ACs have a mechanism (§5.2, §5.3, §5.6) and tests (AC-K1/K2/K5/K14). D10's bug-intent gap is closed *by construction*: intent is never consulted anywhere, so `intent=bug` cannot exempt anything. D12 honoured — FR-level `Layers` untouched, AC-level is the index on top. **Two deviations, both explicit and both to be repeated in the PR body: (i) D9's baseline is dropped (ruling Q1); (ii) AC-1's "named" is spec-DERIVED, not author-declared (Q1b).** Round 1 reported only the first and called the rest compliance — corrected. |
| 2 | Error Handling | **fail (round 2) → fixed** | Round 1's worst error-handling defect was in this column: AC-K9(d) made an ordinary authoring choice an exit-2 infra failure. Round 2 fixed the *verdict* (exit 1 + authoring remedy) but **not the scope** — the guard still fired on any FR repo-wide, so one intro sentence anywhere would have redded every later PR including docs-only ones, contradicting AC-K1. Round 3 scopes it to FRs whose `criteria_digests` actually changed in this PR (§5.1), with AC-K9(d)(ii) written to fail against round 2's unscoped form. Lesson recorded: a downgraded severity is not a fixed blast radius. |
| 3 | Security Basics | **fail (round 2) → fixed, twice over** | Round 1 shipped a **trivially dodgeable gate** (deleting a `/ACnn` suffix turned a HARD block into exit 0). Round 2 added `binding_removed`, but wrote `unbound`'s condition as "no node at base **or** head" — which *is* `binding_removed`'s own input, so AC-K8 and AC-K14 asserted opposite verdicts for identical input and **a builder following AC-K8 would have reinstated the hole**. Round 3 makes the two conditions disjoint (base-yes/head-no vs base-no/head-no) with explicit precedence, and AC-K8 now carries a companion assertion pinning it. Residual, named rather than hidden: the **two-PR unbind sequence** (§7), routed to p3.7(b) as a real card. |
| 4 | Test Quality | **pass** | AC-K6 targets the `_cov_status` ∃/∀ trap; AC-K14, AC-K9(d)(ii) and AC-K11's `master` case are each written as regressions **against this document's own earlier rounds**, not merely as passes against the current one; AC-K8's companion assertion makes the round-3 precedence unimplementable-as-overlapping; AC-K15 pins reader drift; AC-K7 pins the node-id-space trap; AC-K10 now asserts `evaluate_binding_completeness` is *not* called. The diff-coverage/subprocess constraint is a stated build rule. |
| 5 | Performance Basics | **pass** | Per PR: two `read_all` parses per spec file, one extra `git show` for the base manifest (no regeneration), zero extra test executions, zero network calls. No measurable addition to an ~11-minute CI run. |
| 6 | Naming & Structure | **fail (round 2) → fixed** | Follows the family's pure-core / git-layer / adapter split; no new abstraction with one caller; no new severity vocabulary; no new evidence format; no manifest schema change; F11 seam kept but unshipped per Q4. **The round-2 defect was a naming one with teeth:** §5.5's heading claimed "reuse P3.3's rule", but `evaluate_binding_completeness` tests the *inverse* direction (evidence outranking the declared binding, not a binding covering less than required) — a builder reaching for it would have implemented the wrong predicate. §5.5 now states reused (`_LAYER_RANK`, `route_gap_severity`) vs. new (the comparison itself) explicitly. |
| 7 | Affected Boundaries (ADR-024) | **pass** | (i) **spec.md → `ac_identity.read_all` → digest** — probed against the REAL 268-criterion spec at two real commits; **and the round-2 work found the real hazard here was not the one round 1 named**: it is the divergence from the *other* criteria reader (§5.1), now guarded and drift-pinned. (ii) **JUnit → `test_links.generate_file` → `acs[ac_id]` → gate** — probed against a REAL CI run's 17 443 outcome lines across all 142 bound links, which both falsified §2.3 and surfaced the node-id-space constraint. (iii) **base manifest via `git show`** — new this round; the v3-base degradation is reasoned (no `acs` ⇒ zero links ⇒ outcome cannot fire) but **not yet probed**; Probe C covers the head side only. (iv) **gate → `ci.yml` step contract** — still not probeable pre-merge; pinned by AC-K12. Two boundaries probed against production data, one reasoned, one pinned-by-shape-test and disclosed. |

> **Superseded in part by the build (§7, §8 row D3).** Item 1's "two deviations" was true of the
> ratified DESIGN and is false of the SHIPPED CODE: the build took a third, greenness-walking an
> `added` AC that already carries a binding. The row is left standing rather than silently
> rewritten, because the gap between what a self-review asserted and what the build then did is
> the finding — a Stage-1 spec review had to catch it, and §12.3's asymptote note counts it.

**Asymptote note.** Counting the two tallies separately, which round 2 failed to do (minor (a)):

| round | found by **own** probing / self-review | found by the **reviewer** |
|---|---|---|
| 1 | **1** real defect (the `_cov_status` ∃/∀ trap). Two further "findings" were **not** defects: the `FR-01.07/AC06` hazard (a measurement error) and the `origin/main` fetch concern (withdrawn, edit 4). | — |
| 2 | **1** new constraint surfaced by re-probing (node-id spaces, §2.3) — named by no reviewer | **3 HIGH** (the `@covers` dodge, the falsified CI-selection model, the exit-2 landmine) |
| 3 | **0** | **2 HIGH + 4 SHOULD** (`unbound`/`binding_removed` contradiction, unscoped divergence guard; plus the `origin/main` inconsistency, head-only `_spec_paths`, the §5.5 overclaim, the arm-1 pseudocode) |

Round 2's note folded the withdrawn `origin/main` concern into round 1's *own-probing* tally while
counting round 2's reviewer findings separately — inconsistent, and it flattered round 1. Corrected
above.

**The asymptote is not reached and the trend still does not point at it.** The sharper reading is
the one this round supplies: **round 3 found zero defects by self-review and six by review**, and
**both HIGH findings were defects introduced by round 2's own fixes** — a contradiction created by
adding `binding_removed`, and a blast radius left behind by downgrading AC-K9(d). That is the
characteristic signature of fix-induced regression, not of convergence. Two of them landed in
columns round 2's self-review had marked `pass` (items 3 and 6), repeating round 2's own pattern.
The honest conclusion: **this document's self-review is not currently finding what its reviewers
find, so the review round is load-bearing and should not be shortened on the strength of the
diff looking small.** Probes A/B/C run against the build; the **base-manifest `git show`
boundary** (item 7 (iii)) remains un-probed and is still the first place to look — it is now
*more* load-bearing than in round 2, since `_spec_paths(head, base)` and `binding_removed` both
depend on it.

> **Closed at build time.** Item 7 (iii) is no longer un-probed: Probe B's extended arm measured
> all three base shapes against this repo's real history (§6 RESULTS) — absent file → case (i)
> with the warning; v3-era manifest → 15 requirements, zero `acs` nodes, so `binding_removed`
> cannot fire; current manifest → clean. The prediction the round-3 review flagged as the first
> place to look held, and it held *by measurement*.

---

## 12. Build record (Steps 3.5–3.8, this run)

### 12.1 External code review — findings and dispositions

Two rounds ran. The **first is discarded, and the reason is worth keeping**: the diff was built
with `git diff origin/main`, a tree-to-tree diff against a ref that had moved one commit ahead of
the fork point, so both reviewers correctly reported a HIGH "this PR reverts the entire merged
`s2-adopted-config-shape` iterate" — an artifact of the diff, not of the change. Rebuilt as
`git diff $(git merge-base origin/main HEAD)`; a `comm -12` over the two file lists confirmed the
only real overlap with the intervening commit is `docs/hooks-and-pipeline.md`. Verdicts on the
corrected diff: **glm approve, openai reject** — a real contradiction, resolved finding by finding.

| # | Reviewer / severity | Finding | Disposition |
|---|---|---|---|
| 1 | openai · high | The gate permits a PR that changes runtime behaviour without editing an acceptance criterion; it computes a spec-text change set only. | **rejected-with-reason — this is ruling Q2, ratified, and stated verbatim in the module docstring, §4 and the PR body.** *A PR that changes behaviour in code and changes no acceptance criterion passes this gate untouched; it enforces spec-to-test consistency, not code-to-spec consistency.* The reviewer's own alternative ("a trustworthy behaviour-change signal that covers code changes") **is Track R**, struck from scope in §3 on measured grounds. The finding is a correct reading of the *unscoped* sentence; the scope paragraph is the answer, and it is not hidden in a PR body — it is the fourth paragraph of the file. |
| 2 | openai · medium | The `ac_id → tests → last_verified_commit` baseline (D9) is deliberately not implemented. | **rejected-with-reason — ruling Q1, ratified at the plan-review gate.** `ci.yml` re-runs every suite on every PR, so there is nothing selective for a ledger to compensate for, and a stored baseline is a self-reported trust artifact — the class that cost PR #690 twelve review rounds. Recorded in the module docstring precisely so it survives the merge. |
| 3 | openai · medium | A valid-JSON but malformed manifest (`{"requirements": []}`) crashes the gate: `_read_head_manifest` checks only the top level while three readers call `.values()` on `requirements` → uncaught `AttributeError`, exit 1, no JSON. | **accepted-and-fixed.** `require_manifest_shape` validates once at each read boundary (head and base) and raises `ReadError` → exit 2 with a JSON verdict. Validating at the boundary rather than per call site is deliberate: every per-site fallback available is "treat as zero links", the silent zero the base-read module exists to refuse. Four new cases in `test_keystone_gate_infra.py`, asserted through `main` so the contract under test is "exit 2 **and** JSON", not "raises". Same failure shape as the self-review's `EmptyLinkWalk` finding — a gate defect reading as a hard finding. |
| 4 | openai · medium (test) | Probe A does not exercise real regeneration; it writes the manifest directly, so it would survive the regeneration step ceasing to overwrite the committed file. | **accepted-in-part.** The specific bypass is now pinned by `test_the_regeneration_step_overwrites_the_very_file_the_gate_reads`: `ci_manifest_drift_check.TRACKED_MANIFEST_REL` is identical to the path the gate reads, the regen script calls `generate_file(project_root)` (the tracked path, never a scratch one), and the *committed* bytes are the ones diverted to scratch. Inverting those two is the failure the finding names, and it now fails a test. The fuller integration probe (drive the real `uv run --project plugins/shipwright-compliance` regeneration from controlled JUnit) is **deferred with a card** — it needs a populated `.ci-junit/` tree and a compliance-plugin subprocess, which is a test-infrastructure iterate, not a line in this one. Disclosed in §6 RESULTS. |
| 5 | glm · medium (spec) | Probe B is entirely absent from the build: nothing drives `ac_criteria_digests` over the real `spec.md` at the pinned commits, and no test exercises the base-manifest read at a real pre-manifest commit. | **accepted-and-fixed by running it.** Probe B and its extended arm ran against real repo history; results in §6 RESULTS, and they match §2.2's measured shape exactly (268 added / 0 changed). Not encoded as a pytest case **on purpose**: a test pinned to `545a4f320` and `c8767470f` is green only on a full-depth clone and would skip silently on any shallow CI checkout — a test that always skips is weaker than a measurement that is reported. |
| 6 | glm · low | Retiring a requirement while editing its criterion yields `binding_removed`, whose remedy ("restore the `@covers` tag") is unactionable — the tag still exists; the retirement zeroed the count. | **rejected-with-reason, recorded as a limitation.** The outcome is fail-**closed** (the reviewer says so), so nothing is let through; only the message misroutes. The fix costs a fourth reason code and a fourth arm, to serve a flow — retire an FR and edit its criteria in one PR — that has occurred zero times in this repo's history. Reported here rather than fixed silently; if it fires once, it is a two-line follow-up. (At the time of this round, `_keystone_core.py` was also at its 300-line limit; the Stage-3 doubt-review extraction later bought back headroom — see §12.1g — so the flow-frequency reason above is now the only one still standing, not the size constraint.) |
| 7 | glm · low | `not_selected` is a catch-all for any `executed` value other than `pass`/`fail` (e.g. `"error"`). | **rejected-with-reason.** The message already interpolates the observed value (`executed={executed!r}`), so the operator sees the real cause rather than only the label, and the outcome blocks either way. Splitting `"error"` into the `failed` remedy would encode a value the manifest schema does not currently emit — a speculative branch with no producer. |
| 8 | glm · low (test) | The CLI harness (`_manifest_with_binding`, `_run`, `_edit_ac01`) is copy-pasted verbatim into the second test module rather than living in `_keystone_repo.py`. | **accepted-and-fixed.** Hoisted to `_keystone_repo.bound_manifest` / `run_gate` / `edit_ac01`, with the reason recorded in that module's docstring: two copies of "the manifest the gate is graded against" can diverge silently, and the module asserting the *weaker* shape would still be green. |

### 12.1a Tier-3 PR review (`ci.yml`'s own gate, first push of PR #702)

The sensitive-path PR-review gate fired on `.github/workflows/` and returned **BLOCK** with two
issues. Recorded here rather than only in the PR thread, because one of them is a defect in the
fix for finding 3 above — and the shape of that defect is the point.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| A | blocking | Adding a CI workflow gate is a supply-chain-sensitive change requiring manual maintainer approval before merge. | **Accepted, and not resolvable by this run.** The operator's CI supply-chain acknowledgement for this run id is already recorded and committed (`ci_supplychain_ack.json`, consistent-with `iterate-2026-09-09-p3-5-promote-layers-per-fr-restart`); the merge decision itself is the maintainer's. |
| B | blocking | `require_manifest_shape` validated only the TOP-LEVEL `requirements`, while `_links_for` also assumes `node["acs"]` and `ac_node["tests"]` are mappings — so `{"acs": []}` or `{"tests": []}` still raised an uncaught `AttributeError`, exit 1 with no JSON. The tests stopped at the same level and missed it. | **Accepted-and-fixed.** The walk now goes three levels deep. Six malformed shapes are asserted through `main()` at BOTH boundaries (exit 2 **and** JSON), plus a companion pinning the deliberate asymmetry: a non-mapping *node* or *AC node* is SKIPPED, not rejected, because every reader already guards those with `isinstance(..., dict)` — validating only what the readers do not guard is what keeps this function from becoming a second, drifting copy of the manifest schema. |

**What finding B is really evidence of, and it is not "one more edge case".** Finding 3 named the
crash class correctly and I fixed *the instance I had been shown* rather than the class — the same
error the build self-review made when it caught `EmptyLinkWalk` escaping `main()` and did not go
looking for the other boundary that produced a bare exit 1. Three reviewers in a row have now found
the same failure shape at a level I had not walked. The correct generalisation was available each
time: **when a fix is "validate at the boundary", enumerate every dereference the readers perform,
not the one in the report.**

**Contradiction resolution (glm approve vs openai reject).** The reject rests on findings 1 and 2,
which are the two ratified rulings — the reviewer is grading the implementation against the
sub-iterate spec's unscoped sentence, and the scope was narrowed on the record at the plan-review
gate, twice, with the narrowing repeated in the shipped source. Its third and fourth findings are
real and are fixed. So: the contradiction is not about the code, it is about which version of the
requirement is authoritative, and that question was already decided.

### 12.1b Stage-1 spec-compliance review — REJECT

| # | Severity | Finding | Disposition |
|---|---|---|---|
| A | reject (hard gate) | The build greenness-walks an `added` AC with a binding — reversing a rule ratified across all four plan rounds and still asserted in three passages of this document (§5.1's table, §7's bullet, AC-K4's title), while §11/§12.2 claimed "exactly two deviations". Compounded by two attribution errors: the code and its test credited "external code review (openai, high)", which is actually the Track R / Q2 finding that §12.1 **rejects**, and the plan review's AC-id-rotation finding is dispositioned "reported, **not** blocked". | **Accepted; decided rather than reverted, and narrowed.** Kept, because AC-2 names *any* named AC and the design's exemption rests on an assumption that fails when the criterion arrives tagged — full four-step reasoning in §7. **Narrowed** by removing the `layer_gap` call from the added arm: greenness is AC-2, layer breadth is coverage (p3.7's) and the arm most likely to false-red once p3.5 promotes an FR. Recorded as **deviation 3** in §5.1, §7, §8 row D3, AC-K4, §11 item 1 and §12.2 item 1, all in this diff. Attribution corrected in both the code comment and the test docstring to state plainly that **no reviewer asked for it — it was found during build**. |
| B | minor | The reader-divergence guard dropped the "**active** FR" qualifier the design states twice (§5.1, AC-K9(d)), while every sibling predicate in the diff filters to active nodes. | **Accepted-and-fixed.** `ac_change_set` now filters `head_fr_digests` through `_active_display_ids(head_manifest)`. Verified safe before applying: `build_requirement_index` parses requirements from the **spec text**, not from `@covers` tags (20/20 spec FR headings have active nodes today), so a genuinely new FR still gets a node from the regeneration step and the guard cannot be blinded to it. One existing test failed on the change — its fixture modelled a spec-FR with no manifest node, a state CI cannot emit; corrected, with a new test pinning that a **retired** FR is exempt while the identical spec diff still fires for an active one. |

### 12.1c Stage-1 round 2 (fresh, PASS) → Stage-2 code review → Stage-1 round 3 — REJECT

Stage-1 round 2, run fresh (not diff-based) against A/B's fixes, **PASSED**. The orchestrator then
personally ratified deviation 3. Stage-2 (code-reviewer) ran next and returned no blocking finding
but one **medium** correctness finding, plus two doc-precision notes it forwarded rather than
required. Fixed, then Stage-1 ran a third time, fresh, and **REJECTED again** — on the fix itself,
not on anything Stage-1 rounds 1-2 had already covered:

| # | Severity | Finding | Disposition |
|---|---|---|---|
| C | reject (hard gate) | Stage-2's fix added a second, undocumented suppressor of arm 2 — an FR already reported by arm 1 (`unminted_changed`) is now also skipped — while §5.1 names the divergence guard as **the** suppressor and §5.2 states arm 2's predicate without the exception. The fix is correct on the merits (the reasoning mirrors §5.1's own precedence rule for a sibling case) but no passage of the design doc was edited to say so, in the same commit that DID edit two peripheral passages (§2.2, the decision drop). | **Accepted-and-documented.** New precedence paragraph added directly after §5.2's arm-2 definition, naming the rule, the shape it prevents, and the pinning test explicitly, so a reader of §5.2 is no longer wrong about the shipped behaviour. |
| D | reject (hard gate) | Two fabricated attributions in `_keystone_core.py`, unrelated to the fix under review: `_walk_links`'s STATUS-FIRST precedence credited "external code review, glm medium", and `_links_for`'s ACTIVE-nodes-only credited "external code review, glm low" — neither matches any of the 8 recorded `external_code` findings (verified against `reviews.json` directly: the nearest real glm-low findings are the retire+edit misrouted-message finding, already recorded honestly at §7, and the `not_selected` catch-all — neither is either of these). Repeated in `test_keystone_core.py`'s docstring for the first. | **Accepted-and-fixed.** Both attributions corrected to "no reviewer asked for this — found during build" (the same honest form deviation 3 already uses), in the source comment, the module's ACTIVE-nodes-only paragraph (with a note distinguishing it from the real §7 finding it is adjacent to but not the same as), and the test docstring. |

### 12.1d Stage-1 round 4 (fresh) — REJECT

Round 3's fix itself contained the same two error classes it was fixing, undetected by round 3
because it checked "was the cited finding fixed", not "is the whole diff now consistent":

| # | Severity | Finding | Disposition |
|---|---|---|---|
| E | reject (hard gate) | Round 3's ACTIVE-nodes-only attribution fix landed in `_keystone_core.py`'s docstring but not in the test that pins the same behaviour — `test_a_retired_duplicate_requirement_contributes_no_links` in `shared/tests/test_keystone_core.py` still opened "External code review (glm, low)". Round 3's own §12.1c row D claimed the repeat was "for the first [attribution]" only, under-reporting its own diff. | **Accepted-and-fixed.** Corrected to the same honest form, with the same distinguishing note. |
| F | reject (hard gate) | A third, independent fabricated attribution, not raised by any prior round: `test_the_step_takes_no_conditional_dependency_on_another_step` in `test_ci_yml_keystone_step_shape.py` credited a tautology fix to "external code review (glm, low)" — no such finding exists among the 8 recorded `external_code` findings. | **Accepted-and-fixed.** Corrected to the honest build-time form. |
| G | reject (hard gate) | §8's heading, opening paragraph and row D3 all still stated deviation 3 was "NOT ratified — an open ask", and `check_keystone_ac_gate.py`'s module docstring repeated "is **not** ratified" — while this same round's §12.1c had already stated "The orchestrator then personally ratified deviation 3." Three-plus-one passages asserting the stale status, the identical pattern finding A (§12.1b) was rejected for. | **Accepted-and-fixed.** §8's heading, paragraph and row D3, and the CLI docstring, all now read "RATIFIED (2026-09-10, coordinator)" — the ratification is real (it happened after Stage-1 round 2 passed, before this round's diff was ever built), so the fix is to correct the stale passages, not to walk back the claim. |

**Pattern across all four Stage-1 rounds:** every REJECT has been a code/document disagreement or
an attribution error, never a wrong verdict from the evaluator itself — source AC-1/AC-2/AC-3 and
the link-count vocabulary have re-derived as compliant fresh, four times running. Rounds 3 and 4
narrow to the same root cause: a fix that corrects the *instance* a reviewer names, without a
repo-wide check (grep) for siblings of the same shape in the same diff.

**Why finding A is the most serious of the run.** Every other finding this iterate collected was a
defect in code. This one is a divergence between the code and the document that ships beside it —
and the document was still asserting the old rule *three times* while the build asserted the new
one. A reader trusting §5.1's table would have been wrong about the shipped gate's behaviour. It
also went the whole way through self-review, external plan review and external code review
undetected, because each of those looks at the change, not at the agreement between the change and
its spec. That is precisely the gap the Stage-1 hard gate exists to close, and it earned its place.

### 12.1e Stage-1 round 5 (fresh, PASS) → Stage-2 code review (fresh, no blocking finding)

Round 5 PASSED, confirming rounds 1-4's fixes had converged (all 24 review attributions in shipped
source/tests cross-checked against `reviews.json`; deviation 3's ratification status consistent
everywhere). Stage-2 then ran fresh against the new head and found nothing blocking, but one
**medium** correctness gap worth closing before merge:

| # | Severity | Finding | Disposition |
|---|---|---|---|
| H | medium (non-blocking, fixed anyway) | Arm 2's "new active FR" predicate compares the REGENERATED head manifest against the last-COMMITTED base manifest, and the two are known to drift (the traceability drift step is advisory, not a hard gate). An FR whose heading already existed in the base spec, but whose display id a stale base manifest never carried, would false-fire arm 2 for a PR that never touched it — the same blast-radius class the divergence guard was rescoped three times to avoid, but arm 2 had no equivalent "caused here" signal. | **Accepted-and-fixed.** Added the spec-derived exclusion `if fr_id in base_fr_digests: continue` (ruling Q1b's own principle: spec-derived, not manifest-declared) — one conjunct, changes no existing test's outcome. Pinned by `test_an_fr_present_at_base_SPEC_but_missing_from_the_base_MANIFEST_is_not_new`. |

Five smaller low-severity notes (a duplicate precedence check between producer and consumer, an
unreachable `_spec_paths() == []` corner, two attribution comments that were accurate but read
awkwardly out of context, an asymmetry between the manifest and spec git-read strategies, and one
untested pooling/collision interaction in `_keystone_layer_gap`) were left as the author's call —
none changes behaviour, and `_keystone_core.py` sat at exactly its 300-line limit at this round, so
cosmetic churn there was not free (later extracted to 230 lines by the Stage-3 doubt-review fix —
§12.1g — which is a separate round's headroom, not this one's).

### 12.1f Stage-1 round 6 (fresh) — REJECT

Round 5's Stage-2 fix (§12.1e finding H) itself had two of the same defect classes rounds 3-4 kept
finding, plus a new one specific to test quality:

| # | Severity | Finding | Disposition |
|---|---|---|---|
| I | reject (hard gate) | The pinning test named in §12.1e was VACUOUS: it used FR-01.02, which carries a MINTED criterion in `BASE_SPEC`, so arm 2's own final conjunct (`not any(k[0] == fr_id for k in head_minted)`) already suppressed it regardless of the new exclusion — the test passed identically with the fix reverted. | **Accepted-and-fixed.** Rewritten against a criteria-less FR (`### FR-01.03: Empties`), so only the `base_fr_digests` exclusion can save it. Verified by hand: reverting the exclusion makes the test fail (`['FR-01.03'] == []` assertion error), confirming it is now load-bearing. |
| J | reject (hard gate) | §5.2 was not updated with the third suppressor — the identical defect §12.1c finding C was rejected for two rounds earlier. | **Accepted-and-fixed.** A "Third precedence rule" paragraph added directly after the second, naming the exclusion, the drift condition, and the corrected pinning test. |
| K | reject (hard gate) | The new test's docstring opened "No reviewer asked for this — found during build, Stage-2 code review", asserting both "no reviewer asked" and "a reviewer (Stage-2) found it" in the same sentence — self-contradictory, and the wrong form: a reviewer DID ask, so the honest form is the one its sibling test already uses ("Stage-2 code review, medium"), not the build-time form reserved for un-requested findings. | **Accepted-and-fixed.** Docstring opens "Stage-2 code review, medium" to match. |

**Pattern across all six Stage-1 rounds, restated because it repeated a fifth time:** every REJECT
has been a code/document disagreement, an attribution error, or (new this round) a test that does
not test what it claims — never a wrong verdict from the evaluator itself. The evaluator has now
re-derived as AC-1/AC-2/AC-3-compliant fresh, six times running. **The recurring root cause is
narrower than "check everything again": a fix that satisfies the one assertion a reviewer wrote,
without checking that the assertion could FAIL against the code being replaced.** Finding I is the
clearest instance yet — the test read as thorough (real git, a docstring naming the exact hazard)
and was still vacuous, because the fixture's OTHER conjunct alone already produced the asserted
outcome.

### 12.1g Stage-1 round 7 (fresh, PASS) → Stage-2 round 3 (fresh, clean) → Stage-3 doubt review

Round 7 PASSED against the §12.1f fixes (all three findings re-verified fresh, not diffed against
the rejection). Stage-2 then ran a third time and found nothing blocking — the first clean Stage-2
pass of this PR. Per this campaign's pattern for the keystone gate specifically, Stage-3
doubt-review then ran once, adversarial, against the full merge-base diff. Six findings, triaged by
the reviewer's own stated severity rather than treated uniformly, each independently re-verified by
direct code reading before disposition:

| # | Severity | Finding | Disposition |
|---|---|---|---|
| Doubt 1 | high (must-address) | `binding_removed`'s `changed`-AC arm tested `head_links` for EMPTINESS only. Dropping ONE of several `@covers` tags on a fat AC (base 2 links, head 1) fell through to the ordinary greenness walk over the survivor, silently discharging the changed criterion's obligation with a test never written about it. | **Accepted-and-fixed.** Added a `len(head_links) < len(base_links)` HARD check in `_keystone_core.evaluate_keystone`, reusing the existing `BINDING_REMOVED` reason code (same remedy: restore the binding) rather than minting a new one. Pushed the file over 300 lines; resolved by extracting `_links_for`/`_walk_links` into a new sibling module `_keystone_links.py`, re-exported — the same pattern `_keystone_finding.py`/`_keystone_layer_gap.py` already set, not a one-off. Pinned by `test_a_partial_binding_reduction_on_a_changed_ac_is_also_binding_removed`, written to fail against the emptiness-only phrasing (the surviving link is green, so a walk-only evaluator reports the PR clean). |
| Doubt 2 | medium (must-address) | `ac_change_set`'s `for rel_path in _spec_paths(...)` loop calls `.update()` on `head_minted`/`head_fr_digests` per path — last-write-wins. A second spec file added in the SAME PR that re-anchors an already-edited `(fr_id, ac_id)` with its OLD text silently overwrites the genuine edit's digest, reverting it to the base digest and erasing `changed` for a criterion this PR did change — exactly the "no ACs changed" silence the module's own docstring names as the one failure worse than over-firing. | **Accepted-and-fixed.** Added collision detection: each spec path's claim on a `(fr_id, ac_id)` key or bare `fr_id` key is tracked (`head_minted_from`/`head_fr_digest_from`), and a second path claiming a key already claimed by a different path raises `ReadError` rather than silently overwriting. HEAD-only, matching `ac_criteria_digests`'s own base/head asymmetry (a base commit is already merged and cannot be authored by this PR). Pushed the file over 300 lines; resolved by extracting `_digest`/`ac_criteria_digests`/`_unminted_texts` into a new sibling module `_keystone_criteria.py`, re-exported — same extraction pattern as Doubt 1's fix. Pinned by `test_two_spec_files_minting_the_same_ac_id_at_head_raises_read_error`. |
| Doubt 3 | low (acceptable as follow-up) | The design's trust-posture paragraph (§4) claims the keystone gate's exposure to a `ci.yml` edit is "identical" to ruff/diff-coverage/Semgrep/Trivy/Gitleaks, but this gate's OWN verifier source under `shared/scripts/tools/verifiers/` is not itself named in `SENSITIVE_PATH_RE`/the CI-supply-chain patterns the way the others' enforcement points effectively are, so the parity claim slightly overstates. | **Deferred to a follow-up card**, per the reviewer's own explicit disposition ("acceptable as a follow-up card"). Adding these paths to `SENSITIVE_PATH_RE` is a CI-supply-chain-flag change in its own right and out of scope for this PR's diff. Not filed as a triage card by name in this document; tracked in the campaign's pending-tasks list for filing at merge, alongside the Q5/p3.7(b) follow-ups §10 item 8 already names. |
| Doubt 4 | informational (investigated, no fix needed) | Framed as "`spec_text_at` conflates absent-at-a-commit with a git read failure." | **No code change — the premise does not hold.** Direct read of `spec_text_at` (this file, ~line 150) confirms a genuine three-way return: `None` only when the sha itself does not resolve (a real infra fault), `""` only when the commit resolves but the path genuinely does not exist there, real text otherwise — already correctly disambiguated, and `ac_change_set`'s `if base_text is None or head_text is None: raise ReadError` guard already fails closed on the first case. Traced the deletion scenario by hand: a spec file deleted entirely at head reads `head_text == ""`, `ac_criteria_digests("")` returns no minted keys for that path, and every AC previously minted there falls out of `set(base_minted) - set(head_minted)` into `result.removed` — the existing, correct, non-silent path, not a new gap. No reproduction of "silent laundering" survived independent tracing. |
| Doubt 5 | low (cheap, optional) | `removed_with_bindings` is deliberately report-only (§7), but its only surface is a JSON array key — invisible in an otherwise green exit-0 CI log unless a consumer already knows to look for it. | **Accepted-and-fixed.** Added a `::warning::` GitHub Actions workflow-command annotation to **stderr** (never stdout — `_emit` prints the JSON payload as the whole of stdout, and every caller, including this CLI's own test harness, does `json.loads` on it) when `removed_with_bindings` is non-empty. Pinned by `test_removing_a_bound_ac_outright_is_reported_but_does_not_block`. |
| Doubt 6 | informational (cheap, optional) | The `FAILED` HARD reason code is practically unreachable from real `ci.yml` operation, since `set -e` stops the job before this gate's step runs on a genuine test failure. | **Documented, not fixed** — added a §7 bullet. Not dead code: it is the correct answer for the adversarial input it IS reachable from (a stale/hand-edited manifest claiming `pass` for a test that did not run this invocation), which the regeneration step already forecloses in the honest path. Recorded so a future reader does not "simplify" the arm away. |

No second Stage-3 pass was run after the Doubt 1/2 fixes — outside this cascade's established pattern (doubt review runs once, after Stage 1+2 pass), and the fixes are narrow, each independently traced by hand and pinned by a test written to fail against the prior phrasing, per this build's standing discipline. Stage 1 and Stage 2 both re-run fresh against the resulting diff before merge, which is where a fix that broke something else would surface.

### 12.1h Stage-1 rounds 8, 9, 10 and 11 (each fresh) — REJECT, REJECT, REJECT, REJECT

The §12.1g doubt-review fix (round 8's diff) has not yet re-PASSED Stage 1 as of round 11 — four
consecutive REJECTs, each for the same class this whole cascade keeps finding: a behavioural change
(or a build-record edit correcting one) landing without every passage that describes it being
updated to match, including — rounds 10 and 11 both show — passages the FIX ITSELF just added.

**Round 8 — REJECT (2 hard, 6 medium/low).**

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | hard | §5.3's two normative outcome tables still described `binding_removed`'s changed-AC arm as emptiness-only (`head_links == 0`), contradicting the shipped `len(head_links) < len(base_links)` reduction check. AC-K8 and AC-K14 likewise undocumented the reduction case. | **Accepted-and-fixed.** Both §5.3 tables amended with the reduction row; AC-K8 gained companion assertion (d); AC-K14 cross-references it. |
| 2 | hard | Four new attributions used the self-contradictory form "no reviewer asked for this ... Stage-3 doubt review" — the exact shape §12.1f finding K hard-rejected once already, on Doubt 2 and Doubt 5/6, all three of which the doubt reviewer DID raise. | **Accepted-and-fixed.** All four corrected to "Stage-3 doubt review, `<severity>`" (`check_keystone_ac_gate.py`, `test_check_keystone_ac_gate.py`, `test_keystone_ac_digest.py`, and two design-doc §7 bullets). |
| 3 | medium | §12.2 item 6 still said "five modules"; seven now ship. | **Fixed** — updated to name all seven and both extraction rounds. |
| 4 | medium | Two "not fixed because the module is at its 300-line limit" rationales (§7, §12.1 finding 6) rested on a premise the Doubt-1 extraction had already invalidated (`_keystone_core.py` freed to 228 lines at that point). | **Fixed with historical notes** — the live justifications in §7 no longer cite the size constraint; the past-round records in §12.1/§12.1e gained a parenthetical noting the later extraction, without rewriting what was true when each was written. |
| 5 | medium | The new cross-spec-path collision → `ReadError` had no normative statement in §5.1 (the section that specifies the `_spec_paths` loop it modifies), and its own error message cited "design §7" — the wrong section, describing a different, advisory collision. | **Fixed** — collision rule added to §5.1 directly after the union paragraph; citation retargeted to §5.1. |
| 6 | low | §12.3's tally ("Findings: 5") didn't count the Stage-3 doubt round's two real defects at all. | **Fixed** — round summary paragraph names both explicitly. |
| 7 | low | §12.1g's Doubt-3 row cited "§5's blockquote" for the Q5/p3.7(b) follow-up cards; they are named at §10 item 8. | **Fixed** — citation corrected. |
| 8 | low | A test docstring attributed the removed-outright gap to "Doubt 2's neighbour"; it was disclosed by the external plan review (glm medium + openai high), recorded at §7. | **Fixed** — docstring corrected to the real source. |

**Round 9 — REJECT (1 hard, 3 medium/low).** Round 8's fix corrected the design doc's own copy of
the outcome table but missed the identical table carried a second time, verbatim, in
`_keystone_core.py`'s own module docstring — the same document/code divergence, one level deeper.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | hard | `_keystone_core.py`'s "ONE vocabulary: LINK COUNTS" module-docstring table (lines 14-24) still listed only the four original rows, naming `>= 1 / >= 1` as "the greenness walk" with no reduction row — the module the design's §5.3 explicitly says is where this vocabulary lives, describing a rule the module's own code no longer implements. | **Accepted-and-fixed.** Table rewritten to five rows, matching §5.3 and the shipped `if len(head_links) < len(base_links)` branch exactly. |
| 2 | medium | The run's decision-drop record (`.shipwright/agent_docs/decision-drops/iterate-2026-09-09-p3-6-keystone-gate_001.json`) enumerated only the zero-link case in its `"decision"` field. | **Fixed** — updated to name the reduction too. |
| 3 | low | §12.3's "Findings: 5" didn't reconcile against its own probe table (3 rows marked found). | **Fixed** — made explicit: 3 from probes + 2 from the Stage-3 doubt review. |
| 4 | low | The F11 test-completeness ledger's evidence strings understated real test counts (16/8 vs. the actual 17/11) and had no behavior row for either Stage-3 fix. | **Fixed** — counts corrected, a new behavior row added, `counts.testable`/`tested` bumped 17→18. |

**After round 9's fix, a repo-wide sweep for the same emptiness-only phrasing** (every `binding_removed`/`BINDING_REMOVED`/`keystone` mention across the worktree) found no further survivors — the remaining "base >= 1, head 0" phrasings describe specific scenarios (the retired-duplicate case, base-side disarming) correctly, not the general rule.

**Round 10 — REJECT (3 medium/low, all documentation echoes of round 9's own fix).**

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | medium | `.shipwright/agent_docs/architecture.md`'s always-loaded Layer-1 entry still said "five `verifiers/_keystone_*` modules" — correct before the Doubt-1/2 extraction, stale after it. | **Fixed** — updated to seven. |
| 2 | medium | §7 and §12.1e each cited `_keystone_core.py`'s line count as 228 — correct after the Doubt-1/2 extraction, stale after round 9's own docstring-table fix added two more lines (230). | **Fixed** — both updated to 230. |
| 3 | low | §12.1 had no section for Stage-1 rounds 8 and 9, though every prior round has one (including round 9's own REJECT, whose four fixes ship in the same diff as this omission); §12.3's rejection tally undercounted accordingly ("six times, across rounds 1-8"). | **Fixed** — this section (§12.1h) added; §12.3 updated to reflect every round through this one. |

**Round 11 — REJECT (2 medium, both documentation echoes again — one a sibling-docstring
disagreement, one this section's own tally lagging the round it was written to close).**

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | medium | `test_keystone_ac_digest.py`'s sibling map routed AC-K9(e) and AC-K11 to `test_check_keystone_ac_gate.py`; both actually live in `test_keystone_gate_infra.py`, which its own docstring and `test_check_keystone_ac_gate.py`'s docstring both already stated correctly — three shipped docstrings, one of the three wrong. | **Fixed** — `test_keystone_ac_digest.py`'s sibling map corrected to route AC-K9(e)/AC-K11 to `test_keystone_gate_infra.py`, keeping AC-K13/K14 on `test_check_keystone_ac_gate.py`. |
| 2 | medium | This section still ended at round 10 while round 10's own three fixes (this diff) constitute a fourth round with no record, and §12.3's tally still read "seven times, across rounds 1-10" — the verbatim recurrence of round 10's own finding 3, one round later. | **Fixed** — this row and the heading/opening paragraph above extended to cover round 11; §12.3 updated to "eight times, across rounds 1-11". |

**A structural note for whoever reviews the next round, stated once here rather than re-discovered
each time: this record cannot document its own review round, by construction.** The commit that
fixes round N's findings is itself the diff round N+1 reviews — round N's own outcome (this record
extended, or not) is only knowable after round N+1 runs, which is necessarily after this commit
already exists. So the record legitimately lags the in-flight round by exactly one at every point
in this cascade; that one-round lag is not itself a defect (the round-11 reviewer made exactly this
call: *"a record that lags the in-flight round is unavoidable ... not the same thing"* as a false
claim). What IS a defect, every time: a record stale by MORE than one round, a count that
contradicts the rows actually present, or an affirmatively false claim (a stated PASS that did not
happen, a wrong section citation). Check the row count in §12.1h against §12.3's tally before
flagging either — if they already agree and the only gap is "the round that just ran isn't in here
yet", that gap is expected, not a finding.

### 12.1i Stage-1 round 12 (fresh, PASS) → Stage-2 code review (fresh, first pass on this code) — PASS-WITH-FINDINGS

**Round 12 PASSED** — the first PASS since round 7, ending the four-consecutive-REJECT streak
(rounds 8-11, §12.1h) and confirming the one-round-lag principle stated at the end of that section:
given the principle explicitly as a reviewing instruction, round 12's reviewer correctly
distinguished the (expected) one-round documentation lag from a genuine defect and passed clean.
Two non-blocking observations were raised and deliberately NOT acted on, to avoid re-triggering the
lag cycle over content the reviewer itself did not call a finding: this section's own
hooks-and-pipeline.md guard-count phrasing (see finding 13 below — since fixed, as part of THIS
round's work) and §10's file-creation list being incomplete.

**Stage-2 code review then ran for the first time against the Doubt-1/2 fixes** (the cross-spec-path
collision guard and the partial-binding-reduction check, §12.1g) — **PASS-WITH-FINDINGS, 14 findings
(5 medium, 9 low), none blocking.** Given P3.6's stakes, every medium and most lows were addressed
rather than left at "does not block merge":

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | medium | `main()` named only `ReadError`/`EmptyLinkWalk`; any other exception a reader raised (a malformed-but-differently-shaped manifest, an unanticipated git fault) escaped as a bare Python exit 1 with no JSON — indistinguishable in a CI log from a real hard finding. | **Fixed.** `main()`'s body extracted into `_run_gate`, wrapped in a catch-all that maps any exception to an `infra_fault` JSON payload, exit 2. Pinned by `test_an_unanticipated_exception_exits_two_not_one`. |
| 2 | medium | The reduction check compares a REGENERATED head manifest against a STALE-BY-CONSTRUCTION base one; base-side drift can under- or over-report a reduction. | **Disclosed, not fixed** (§7) — base is immutable by definition, so there is no more-current base to compare against inside this PR; same remediability argument as deviation 3. |
| 3 | medium | Neither manifest naming a `spec_path` for any requirement makes the per-AC change-set loop a silent no-op — indistinguishable from "nothing changed" when the real story is "there was nothing to compare". | **Fixed.** A warning is appended when `_spec_paths` returns empty. Pinned by `test_no_spec_path_in_either_manifest_warns_rather_than_reading_as_clean`. |
| 4 | medium | A cardinality-only reduction check (`len(head_links) < len(base_links)`) is defeated by a constant-count retag — two links rotating to different tests leaves the count, and the check, silent. | **Disclosed, not fixed** (§7), per the reviewer's own framing — per-link identity tracking is p3.7(b)'s orphan detector's question, not this count-based structural check's. |
| 5 | medium | The FR-heading collision branch (`head_fr_digest_from`, distinct from the AC-id collision branch above it) had no test of its own. | **Fixed.** `test_two_spec_files_heading_anchoring_the_same_fr_with_no_ac_markers_raises` added; the existing AC-id collision test also gained a `match=` pin. |
| 6 | low | The reduction's HARD-finding message named only link COUNTS, leaving an operator to diff two manifests by hand to find which `@covers` tag(s) vanished. | **Fixed.** A set-difference over base/head link ids names the missing id(s) directly. |
| 7 | low | `head_texts.get(digest, ("<unknown FR>", ""))` degrades a provably-unreachable miss into an unhelpful sentinel rather than surfacing the broken invariant. | **Fixed.** Bare subscript. |
| 8 | low | `UNBOUND` was defined and imported but never referenced; the JSON key it should have named was hardcoded as the literal string `"unbound"`. | **Fixed.** The gate's JSON payload now keys on `UNBOUND` directly. |
| 9 | low | `read_base_manifest` carried a dead `git rev-parse --verify` re-check — `read_committed_text`'s own `ls-tree` call already fails closed on an unresolvable commit before this branch is ever reached. | **Fixed.** Dead branch removed. |
| 10 | low | `_keystone_criteria.py` was the one verifiers module reaching into `lib` without its own ADR-045 sys.path bootstrap, relying on `verifiers/__init__.py`'s side effect. | **Fixed.** Bootstrap added, matching every sibling. |
| 11 | low | Redundant re-parsing across the per-spec-path loop (a performance micro-optimization). | **Deliberately deferred** — cosmetic, no correctness risk, and touching the loop again risks yet another documentation-drift round for no behavioral gain. |
| 12 | low | `test_keystone_core_arms.py` sits at exactly 300 lines, zero headroom. | **Deliberately deferred** — the limit has not been crossed; pre-emptive rebalancing is premature. |
| 13 | low | `docs/hooks-and-pipeline.md`'s "four tabulated... other three (deliberately unmirrored)" phrasing undercounts: one of the four tabulated guards is ALSO unmirrored, so the true unmirrored total is four (matching the section's own later sentence), not three. Independently flagged by both round 12's spec-reviewer (as a non-blocking observation) and this Stage-2 pass. | **Fixed.** Intro sentence reworded to state the split precisely: three of the four tabulated guards are mirrored, the fourth is not, plus three more described below. |
| 14 | low | Formatting nits: three consecutive blank lines before `@dataclass` in `_keystone_finding.py`; a trailing blank line at EOF in `test_check_keystone_ac_gate.py`; a doubled blank line between the module docstring and `from __future__` in `test_keystone_gate_infra.py`. | **Fixed**, all three. (The unconditional `::warning::` print gating suggestion in this same finding was cosmetic-only and needs no action.) |

**Two source files crossed the 300-line guideline as a direct consequence of these fixes, and both
were extracted rather than baselined, continuing this build's established pattern** (§12.2 item 6):
`test_keystone_ac_digest.py` (finding 5's new test) split into itself plus
`test_keystone_ac_digest_never_silent.py` (the AC-K9/never-silent and cross-spec-path-collision
tests); `_keystone_ac_digest.py` (finding 7's fix) split its reader-divergence and
new-FR-without-criteria arms into a new eighth verifier module, `_keystone_divergence.py`. Neither
extraction changed behavior — both are pinned by the unchanged test suite passing before and after.

### 12.1j Stage-1 round 13 (fresh) — REJECT (4 medium)

**Not one-round lag** — every finding was created BY the §12.1i fix commit itself and contradicted
that same commit's own new text, the exact shape §12.1h round-9/round-10 findings kept catching:
a fix's collateral effect (a line-count growth, a test moving files) left uncorrected in a passage
the fix commit did not think to touch.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | medium | `architecture.md`'s always-loaded Layer-1 entry still said "seven `verifiers/_keystone_*` modules" while this same commit's §12.1i and §12.2 item 6 both already said "eight" — the eighth module (`_keystone_divergence`) is created in this commit. Recurrence of round-10 finding 1. | **Fixed** — updated to eight. |
| 2 | medium | §7's retire-while-editing bullet cited `_keystone_core.py`'s "current line count (230…)"; finding 6's own fix (naming missing link ids via a set difference) grew the file to 239 in this same commit. Recurrence of round-10 finding 2. | **Fixed** — updated to 239, with an explicit reason (finding 6, not the Stage-3 doubt-review extraction this was last true of). |
| 3 | medium | The F11 ledger's evidence string claimed "`test_keystone_ac_digest.py` 17 tests PASSED"; this commit's own test-file split left it with 12, moving 7 to a file the ledger never names. | **Fixed** — evidence string updated to name both files with their real counts (12 + 7). |
| 4 | medium | The F11 ledger cited a node id, `test_keystone_ac_digest.py::test_two_spec_files_minting_the_same_ac_id_at_head_raises_read_error`, that the same split moved to `test_keystone_ac_digest_never_silent.py`. The test module's own docstring routed it correctly; the ledger did not. | **Fixed** — node id corrected to its new file. |

The reviewer additionally re-verified as clean and did not flag: the hooks-and-pipeline.md finding-13
rewording (matches `CI_ONLY_GATES` exactly), §12.1i's 14-row table against the actual diff, §12.2
item 6's "eight", and §12.3's addendum — plus one non-blocking observation (§12.2 item 4's "52 + 48
cases" understating the tools root by 3 after findings 1/3/5's new tests), fixed here as part of the
same pass since it was a real, checkable drift rather than a judgment call.

### 12.1k Stage-1 round 14 (fresh, PASS) → Stage-2 code review (fresh, second pass) — PASS-WITH-FINDINGS

**Round 14 PASSED** — independently re-verified all four round-13 corrections against the live tree
(module count, `_keystone_core.py`'s line count, both F11-ledger evidence strings) and found no new
drift from that commit's own edits.

**Stage-2's second pass then ran against the same diff — PASS-WITH-FINDINGS, 1 medium + 6 low + 2
nits, nothing blocking.** All prior-round fixes (findings 1, 3, 5-10, 13-14 of §12.1i) were
independently re-derived as genuinely correct, not just plausible — including that finding 5's new
test reaches the intended branch (an FR-heading-only collision with zero `[ACnn]` markers, so only
`head_fr_digest_from` can fire) and that both extractions are clean (no leftover imports, no broken
re-exports, no orphaned code).

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | medium | The empty-`spec_paths` degraded mode (finding 3, §12.1i) warns but did not suppress arm 2 (`new_frs_without_criteria`): with a NON-empty base manifest and no spec read at all, every head-only active FR HARD-blocked as "states no acceptance criterion" from a document nobody read — the same blast-radius mistake the existing `base_manifest_absent` suppression already exists to prevent, one call away. | **Fixed.** `resolve_new_frs_without_criteria` gained a `no_spec_was_read` parameter, short-circuiting the arm exactly like the empty-base-manifest case (no second warning — the existing top-level one already explains why). New regression test uses a base manifest with a real active requirement plus a head-only new one, both with no spec_path, to exercise the risky combination the finding-3 test never touched. |
| 2 | low | The `::warning::` line for `removed_with_bindings` contained `§` (design §7); `ensure_utf8_stdout()` pins stdout only, and Windows stderr on a codepage that cannot encode it would turn a legitimate clean exit 0 into a bogus `unexpected gate fault` exit 2 via this same round's own catch-all (finding 1, §12.1i). | **Fixed.** Reworded to "design doc section 7" — ASCII throughout, no codepage dependency. |
| 3 | low | `UNBOUND` is declared as a `Finding`-reason-code constant but never appears on a `Finding`; its only use is as a JSON payload key, alongside sibling literal keys. | **Not fixed** — `_keystone_finding.py`'s own docstring already documents this dual role ("a consumer... matches on these exact strings" against the JSON, not just `Finding.kind`), so the wiring is consistent with the module's stated purpose, not a new coupling. |
| 4 | low | The divergence→arm-2 precedence rule is implemented in both `_keystone_divergence.py` and (independently) `_keystone_core.py`. | **Not fixed**, per the reviewer's own explicit framing ("raise as advisory, not a required reduction") — both halves are already independently tested. |
| 5 | low | The extracted `resolve_*` functions mutate their caller's `AcChangeSet` in place with an unstated call-order dependency. | **Not fixed** — cosmetic, no correctness risk; deferred for the same reason as findings 11/12 of the prior round. |
| 6 | low | `test_the_step_name_ends_in_gate_so_the_ci_gate_guard_enrols_it` asserted a local constant against itself, never touching `check_ci_gate_coverage.is_gate_step` — deleting `"(gate)"` from `GATE_NAME_KEYWORDS` would leave it green while its own docstring's claim went false. | **Fixed.** Rewritten to build a real `Step` from the parsed `ci.yml` entry and assert `is_gate_step` classifies it true, plus that its `run` body alone matches no `GATE_COMMAND` — pinning that the `(gate)` suffix is genuinely load-bearing. |
| 7 | low | `hooks-and-pipeline.md`'s ordinal callouts ("**A fourth**... step follows it", "**A fifth** step closes the job") went stale when finding 13's fix (§12.1i) grew the intro from three tabulated guards to four, without shifting these two later ordinals by one. | **Fixed** — "fourth" → "fifth", "fifth" → "sixth". |
| 8 | nit | `Path(args.project_root).resolve()` re-wraps a value argparse's `type=Path` already produced. | **Not fixed** — cosmetic. |
| 9 | nit | `_read_head_manifest`'s `except ValueError` also silently catches `UnicodeDecodeError`, mislabeling a byte-corrupt manifest as "not valid JSON". Already fail-closed; only the message is imprecise. | **Not fixed** — cosmetic, no behavior change; the outcome (exit 2, `ReadError`) is correct either way. |

### 12.1l Stage-1 round 15 (fresh) — REJECT (2 hard)

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | hard | The `no_spec_was_read` suppressor (§12.1k finding 1) is a FOURTH arm-2 precedence rule shipping with no normative statement anywhere in §5.1/§5.2, which still enumerated only three suppressors. The identical class §12.1c finding C and §12.1f finding J were each hard-rejected for once already — a behavioural change landing without the design section it modifies being updated to match. | **Accepted-and-fixed.** A "Fourth precedence rule" paragraph added directly after §5.2's arm-2 definition (following the third precedence rule), stating the rule, its rationale, and its test. |
| 2 | hard | This same commit's own new test in `test_keystone_ac_digest_never_silent.py` made the F11 ledger's evidence string ("7 tests PASSED" for that file) false — it now holds 8. Verbatim recurrence of §12.1j finding 3, one commit later, not one-round lag: the count is contradicted by the tree the SAME commit produced. | **Fixed** — evidence string updated to 8. |

The reviewer independently re-traced the fix by hand with `no_spec_was_read` reverted and confirmed
the new test genuinely fails without it (a real regression test, not a vacuous one), and re-verified
every other count and citation in the document as still accurate — nothing else in this round's
commit had drifted.

### 12.1m Stage-1 round 16 (fresh) — REJECT (1 hard, two faces of one root cause)

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | hard | Round 15's own "Fourth precedence rule" paragraph (§12.1l finding 1's fix) cited "§5.1's own 'neither manifest names a `spec_path`' warning" twice — §5.1 states no such warning. The underlying warning itself (shipped since §12.1i finding 3, tested, now relied on by the Fourth rule) has no normative statement anywhere in §5.1's never-silent list. A wrong citation pointing at a genuine normative gap: fixing the gap makes the citation true. | **Fixed.** A fourth bullet added to §5.1's "Silence is the one failure mode worse than over-firing" list, stating the `_spec_paths`-empty warning directly; no change needed to the §5.2 citations themselves once the target exists. |

The reviewer independently traced the Fourth precedence rule's every clause against the shipped
`no_spec_was_read` code and confirmed it accurate, re-verified the corrected F11-ledger count (8),
and re-confirmed every other count and cross-reference in the document — this round's defect was
narrowly the missing §5.1 bullet, not a wider drift. Two non-blocking observations were raised and
addressed in the same pass since they were cheap and cost nothing to fix: §5.2's Fourth-rule
paragraph reworded from "a THIRD, independent null case ... distinct from ... the divergence guard's
own scoping" (loose — the divergence guard's scoping is a blast-radius rule, not a null case) to "a
SECOND, independent null case beyond the empty-base-manifest amendment"; §12.1l's own placement
description was left as-is, since the reviewer judged it harmless boilerplate.

### 12.1n Stage-1 round 17 (fresh, PASS) → Stage-2 code review (fresh, third pass) — PASS-WITH-FINDINGS

Round 17 confirmed round 16's §5.1 addition and the "SECOND, independent null case" rewording are
both accurate, and noted (non-blocking) that `_keystone_divergence.py`'s own docstring already said
"second" independently of the design doc — i.e. code and doc now agree, not one copying the other.

Stage-2's third pass reviewed the code changes since its second pass (`no_spec_was_read`, the stderr
`§` removal, the CI-shape test rewrite — the Stage-1 rounds in between were documentation-only) and
came back **PASS-WITH-FINDINGS, 0 blocking, 5 low**, after independently hand-verifying all four
changes correct, including a full hand-trace proving the new regression test fails without the fix.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | low | `no_spec_was_read = not spec_paths` tested whether a `spec_path` was NAMED, not whether text was actually READ — a path present in the manifest but resolving to `""` at BOTH commits (absent from git at either sha) would leave arm 2 unsuppressed with empty digests, still HARD-blocking incorrectly. Fails closed/loud, not silently — low likelihood in real CI, reachable in local reproduction. | **Fixed.** Renamed to `spec_text_was_read`, computed from whether any spec path actually yielded non-empty text at either commit during the read loop, not from `spec_paths` alone. New regression test: `test_a_named_spec_path_absent_from_git_at_either_commit_also_suppresses_arm_2`. |
| 2 | low | `no_spec_was_read: bool = False` was an unsafe-by-default parameter with exactly one caller; `head_minted` also lacked a type annotation. | **Fixed** in the same edit as finding 1: `spec_text_was_read` is now a required keyword-only argument with no default, positively named, and `head_minted: dict[tuple[str, str], str]` is annotated. |
| 3 | low | The CI-shape test rewritten at §12.1k finding 3 never mutated the step's `name` to prove the `(gate)` suffix specifically (not just the run body) is load-bearing. | **Fixed.** Added a `dataclasses.replace(step, name=...)` assertion stripping `" (gate)"` and confirming `is_gate_step` then returns `False`. |
| 4 | low | That same test's hand-built `Step(...)` duplicated, and already diverged from, `parse_workflows`'s own field coercion — a naive `bool("false")` reads a string `"false"` as truthy, while the real parser's string-aware check reads it as `False`. | **Fixed.** The test now selects the step from `parse_workflows(_REPO_ROOT)` directly instead of hand-constructing one, exercising the real code path. |
| 5 | low | The stderr-ASCII fix (§12.1k finding 4) had no regression test pinning it. | **Fixed.** Added `assert captured.err.isascii()` alongside the existing `::warning::` assertion, mirroring the repo's `test_operator_facing_strings_are_ascii_only` precedent in `test_suite_units.py`. |

All five findings were independently re-derived against the current source before being accepted —
`spec_text_at`'s three-way return contract was re-read to confirm finding 1's `""`-at-both-sides case
is genuinely reachable, and `ci_gate_scan.parse_workflows`'s `continue_on_error` coercion was re-read
to confirm finding 4's claimed divergence from the test's naive `bool()` coercion. All five were fixed
in one pass, none deferred: this is the first Stage-2 pass with nothing left to disclose-and-skip.

### 12.1o Stage-1 round 18 (fresh) — REJECT (1 hard) → fixed

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | hard | §12.1n's fix broadened arm 2's fourth suppressor from "no `spec_path` named" to "no spec text actually read" (also covering a named `spec_path` resolving to no content at either commit), but §5.2's Fourth precedence rule paragraph still stated only the narrower original trigger. Worse, its closing claim — "no second warning is emitted; §5.1's existing one already explains why" — became FALSE by this same broadening: in the newly-covered branch a `spec_path` IS named, so §5.1's `not spec_paths` warning never fires, and arm 2 was suppressed with an entirely empty `warnings` list. A silent suppression, contradicting §5.1's own governing rule the paragraph itself cites. Third recurrence of this exact class (§12.1l finding 1, §12.1m finding 1), now on the same paragraph a third time. | **Fixed two ways, matching each half of the defect.** (1) Code: `_keystone_ac_digest.py` now emits its own warning when `spec_paths` is non-empty but `spec_text_was_read` is False, closing the silence the reviewer found. (2) Doc: §5.1 gained a fifth never-silent bullet for this branch; §5.2's Fourth precedence rule paragraph restated to the actual two-disjunct trigger, with the "no second warning" claim corrected to describe which warning covers which half. The new test in `test_keystone_ac_digest_never_silent.py` now asserts the warning is present, rather than only asserting the arm is suppressed. |

The reviewer's own reasoning was adopted directly rather than re-derived from scratch: the finding
named both the exact defect (a false claim about warning coverage) and the exact remedy (emit a
second warning, which is what §5.1's "silence is worse than over-firing" principle already argues
for) in the same report, so the fix is the reviewer's own suggested alternative, not an independent
invention. A non-blocking observation from the same round — a stale test-count evidence string in
`iterate-2026-09-09-p3-6-keystone-gate.test-results.json` (pre-existing, not caused by this commit,
and explicitly flagged by the reviewer as outside this REJECT) — was deliberately left untouched:
that file is this run's frozen F5 evidence snapshot, not a live document, and revising it after the
fact to match later counts would misrepresent what F5 actually observed at the time it ran.

### 12.2 Self-Review (Step 3.6, against the BUILD)

| # | Item | Verdict | Note |
|---|---|---|---|
| 1 | Spec Compliance | **FAIL → fixed, and this row is the one that was wrong** | Claimed "two named deviations" (Q1, Q1b) while the build had already taken a **third** — greenness-walking a bound `added` AC — reversing a rule ratified across four plan rounds and still asserted in three passages of this document. A **Stage-1 spec review rejected the build for it**; self-review had marked this row `pass`. Now: three deviations, the third named in §7, §8 row D3, §5.1's table and AC-K4's title, with its misattribution corrected in code and test. Q1/Q1b remain in the shipped module docstring. |
| 2 | Error Handling | **fail → fixed twice, and the second time is the finding** | Found here first: `EmptyLinkWalk` escaping `main()` is a Python exit 1 — indistinguishable in a CI log from a real hard finding, so a gate defect would send an author to edit a spec that is fine. Now caught → exit 2 with JSON. External review then found the *same shape* at a different boundary (finding 3), and the Tier-3 PR review found it again two levels deeper (§12.1a finding B). The honest reading of this row: the class was identified early and then fixed **instance by instance** rather than enumerated. |
| 3 | Security Basics | **pass** | No new trust artifact, no new persisted state, no network. `github.sha` is interpolated as a SHA (no injection surface). The base read is fail-closed three ways and its one permissive branch is surfaced under its own JSON key. |
| 4 | Test Quality | **pass** | 57 + 48 cases (grew by five in the tools root over the three Stage-2 code-review passes — findings 1, 3 and 5 at §12.1i, finding 1 at §12.1k, finding 1 at §12.1n); the load-bearing ones fail against this document's *earlier rounds*, not merely pass against the current one. In-process `main(argv)` throughout with exactly one subprocess smoke, because subprocess-only tests contribute 0 % to the hard 80 % diff-coverage gate. |
| 5 | Performance Basics | **pass** | Two spec parses and one extra `git show` per PR; no regeneration, no extra test execution. |
| 6 | Naming & Structure | **pass** | Eight verifier modules plus the CLI, six extracted from the two the gate is built around (`_keystone_finding`, `_keystone_layer_gap`, `_keystone_base_manifest` from round 1-4; `_keystone_links`, `_keystone_criteria` added by the Stage-3 doubt-review fix, §12.1g; `_keystone_divergence` added by the Stage-2 code-review fix, §12.1i) — each under 300 lines by *extraction*, never by baselining. No new abstraction with one caller. |
| 7 | Affected Boundaries (ADR-024) | **pass** | See §12.3 — all four boundaries probed or pinned, and (iii) moved from *reasoned* to *measured* this round. |

### 12.3 Confidence Calibration (Step 3.8)

Probes run: **10**. Findings: **3 from probes (D, F, H below) + 2 from the Stage-3 doubt review
(§12.1g Doubt 1/2, which are not probes and have no row in the table below) = 5**. Asymptote:
**reached for the base-manifest boundary, NOT
reached for the gate as a whole** — and the second half is the honest answer, so it is stated
rather than rounded up. Probe H is the direct evidence for that second half: a probe written to
close a boundary found the same defect one level deeper, *after* the boundary had been declared
validated.

| Probe | Boundary | Finding |
|---|---|---|
| A | regenerated manifest → gate | none (verdict unchanged by a committed forgery) |
| B.1 | real `spec.md` → `ac_criteria_digests` → change set | none; 268 added / 0 changed, matching §2.2 |
| B.2 | base manifest absent at a real pre-manifest commit | none; case (i) with the warning |
| B.3 | v3-era base manifest (15 reqs, 0 `acs` nodes) | none; `binding_removed` structurally cannot fire, as reasoned |
| C | `@covers`-suffix dodge | none; blocks, and the companion shows round 1's design does not |
| D | malformed-but-valid-JSON manifest (post-review) | **found**: `AttributeError` → exit 1 without JSON. Fixed, then re-probed across three malformed shapes at both boundaries → no finding. |
| E (F0.5) | the SHIPPED CLI over a REAL merged PR (`0348b887` → `5d76efcd`, PR #700) | **no false red**: exit 0, `status: clean`, empty change set — the gate is silent on a PR that changed no criterion, which is AC-3's whole claim, measured rather than asserted. |
| F (F0.5) | the same CLI invoked with no `--base-sha` at a commit that is its own merge-base | **found**: exit 2 with a fetch-depth remedy that does not apply. Structurally unreachable in CI; disclosed in §7 rather than fixed, with the reason. |
| G (CI) | the shipped gate on the REAL PR that adds it (#702) — the first live firing | **no finding, and it closes the one boundary §11 item 7 (iv) called "not probeable pre-merge".** On run 34413699911 the step resolved `base_sha = 5d76efcd` through `_merge_base`'s own chain with no `--base-sha`, read `github.sha` (`c1d9f104`, the merge commit) as head, and returned exit 0 / `status: clean` with an empty change set. The `pull_request` trigger, the base resolution, the merge-commit head and the regenerated-manifest read are all now observed rather than pinned by shape. |
| H | malformed manifest at the NESTED levels (`acs`, `tests`), after the Tier-3 PR review found probe D's fix stopped one level short | **found**: `AttributeError` → exit 1 without JSON, at two more dereferences. Fixed, then re-probed across six malformed shapes at both boundaries plus the skip-vs-reject asymmetry → no finding. |

**Two consecutive no-finding probes on the base-manifest boundary** (B.2 then B.3) after B.2's
predecessor — the round-3 review's "first place to look" — is the asymptote condition for *that*
boundary, and it is met.

**It is not met for the gate as a whole, and the trend says so.** §11's tally recorded rounds
where self-review found 1, 1, 0 defects while review found 0, 3, 6. This round: self-review found
1 (the `EmptyLinkWalk` exit code), external review found 3 real ones and 2 correct scope
objections, the Tier-3 PR review found 1 more, the **Stage-1 spec review rejected the build
outright** for a code/document divergence none of the earlier passes looked for (eight times, across
rounds 1-11 of this same PR — §12.1b through §12.1h), and the **Stage-3 doubt review found two more
real defects in the shipped evaluator itself** — one **high** (a partial binding-count reduction
silently passing the gate, §12.1g Doubt 1) and one **medium** (a cross-spec-file digest collision
capable of erasing a genuine `changed` verdict, §12.1g Doubt 2) — after Stage 1 and Stage 2 had
BOTH already passed. That last fact is the sharpest data point yet: a spec-compliance pass and a
code-quality pass, run fresh and independently, both cleared code that an adversarial pass reading
for hidden coupling and boundary contracts did not.

**The streak broke at round 12** (§12.1i) — the first Stage-1 PASS since round 7, four rounds
after it started. Stage-2's first pass on the Doubt-1/2 fixes then found 14 more non-blocking
findings (5 medium, 9 low; §12.1i) — none of which round 12's spec-compliance pass was positioned
to catch, since none is a spec/document divergence. The two review stages keep finding disjoint
classes of defect, which is the argument for running both, not for either alone.

**Round 13 (§12.1j) rejected the Stage-2 fix commit itself — a ninth rejection, across rounds
1-13 now** — four medium findings, every one a collateral effect of that commit's own fixes
(a module-count growth, a line-count growth, a test-file split) left uncorrected in a passage the
fix commit did not think to touch. This is the class §12.1h named at rounds 9 and 10 recurring a
third time, one extraction round later: a fix's side effects on unrelated bookkeeping (architecture
snapshots, the F11 ledger) are as easy to miss as the fix's own direct documentation.

**Round 14 (§12.1k) passed**, confirming round 13's four corrections held. Stage-2's SECOND pass —
this time over code that had already survived one full spec/code/spec cycle — still found a genuine
medium correctness bug (arm 2 firing from a document nobody read, in the very degraded mode the
PRIOR Stage-2 pass's own finding 3 introduced the warning for) alongside six low findings and two
nits. The pattern holds across seven rounds of alternating review now: Stage 1 and Stage 2 keep
finding disjoint defect classes in the SAME code, including in fixes only one round old.

**Round 15 (§12.1l) rejected the fix for THAT medium bug — a tenth rejection, across rounds
1-15 now** — 2 hard findings, both created by the fix commit itself: the new `no_spec_was_read`
suppressor shipped as a fourth arm-2 precedence rule with no matching normative statement in §5.2
(the identical class §12.1c finding C and §12.1f finding J were each hard-rejected for already), and
the fix's own new test invalidated the F11 ledger's evidence count for the file it landed in
(the identical class §12.1j finding 3 was rejected for, one commit later). Both classes are now
recurring a THIRD time each across this cascade — a normative-lag miss and a collateral-count miss,
each independently confirmed to survive one full extra round after the pattern was first named.

**Round 16 (§12.1m) rejected round 15's own fix — an eleventh rejection, across rounds 1-16 now** —
1 hard defect, itself created by the fix that closed round 15's normative gap: the new §5.2
paragraph cited a §5.1 warning that §5.1 never actually states, because the warning it described had
never been given its own normative sentence. Fixed with one bullet added to §5.1's never-silent
list, closing the citation and the gap in the same edit — the cheapest possible remedy, once the
narrower diagnosis (a wrong citation pointing at a genuine hole, not two separate defects) was made.

**Round 17 (§12.1n) passed, and Stage-2's THIRD pass found nothing blocking for the first time** —
five low findings, all fixed in one pass rather than disclosed-and-deferred: a residual gap in the
SAME shape of bug Stage-2's second pass found (§12.1k finding 1) one layer deeper — "was a spec path
NAMED" is not "was spec text READ" — plus two test-quality strengthenings on the round-14 CI-shape
rewrite and a missing regression test for round-14's own stderr-ASCII fix. That a fresh adversarial
pass over already-twice-reviewed code still found a genuine (if low-likelihood) false-block gap is
this cascade's clearest evidence yet that "no blocking findings" is a property of a specific diff at
a specific round, never a property the code earns once and keeps.

**Round 18 (§12.1o) rejected the fix that closed round 17's own gap — a twelfth rejection, across
rounds 1-18 now** — 1 hard defect, the THIRD time this exact class (a behavioural broadening landing
without its §5.2 normative statement following) has hit the SAME paragraph (§12.1l finding 1,
§12.1m finding 1, now this). Fixed by adopting the reviewer's own diagnosis and suggested remedy
directly: the newly-broadened suppression branch was silent because it fell outside both existing
warnings, so it now carries its own, and §5.2's paragraph states the real two-disjunct trigger
instead of the narrower one that shipped in round 17. Three rejections on one paragraph is itself a
data point: a normative statement that keeps drifting behind its own implementation is a sign the
implementation is still moving faster than the design section can be trusted to track it by hand,
not evidence that any individual round's fix was careless.

**The two distinct failure patterns this run produced, both worth more than the individual fixes:**

1. **Fixing the instance instead of the class** — the same `AttributeError`-at-a-dereference shape
   was found three times, each a level deeper than the last fix (probes D and H, §12.1 finding 3,
   §12.1a finding B).
2. **Changing behaviour without changing the document that specifies it** (§12.1b finding A). Every
   review pass before Stage 1 examines *the change*; only a spec review examines *the agreement
   between the change and its spec*. A self-review row that reads `pass` while a shipped rule
   contradicts three passages of its own design doc is not a review, it is a restatement of intent
   — and that is the honest verdict on §12.2 item 1 as first written.

**Edge cases NOT probed, and why that is acceptable:** (i) *was* the `ci.yml` step's real behaviour
on a `pull_request` event — **no longer un-probed**: probe G observed it live on PR #702's own CI
run (base resolved through `_merge_base`, `github.sha` as the merge-commit head, exit 0 clean).
The eleven shape assertions remain, now as the regression net rather than as the only evidence;
(ii) the fuller regeneration-integration probe (finding
4) — deferred with a card, with the specific bypass pinned structurally; (iii) a merge-queue
`merge_group` event — this repo has none, and a tripwire test fails the moment one is enabled.
