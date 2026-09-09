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
| `545a4f320` (P3.4 backfill) | 268 ACs read as `added` — an artefact of the mint itself: at base no criterion carried a marker. Additions do **not** block under arm 2 of AC-2, but under §5.2's corrected `unminted_changed` rule they would have blocked *at base*, which is why "mint before gating" is a stated precondition (§7). |
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
> `changed` and **never blocks on greenness**. That is the two-PR shape of the dodge the gate
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
| `added` | minted id absent at base, present at head | never blocks on greenness (a new criterion has no binding — p3.7's baseline) |
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
| `binding_removed` | base had ≥1 link for `(fr_id, ac_id)`, head has none | **HARD** | restore the `@covers("FR-xx/ACnn")` binding, or justify its removal in review |
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
| 0 | 0 | `unbound` (report-only, exit 0) |
| 0 | ≥ 1 | newly bound → the ordinary greenness walk |
| ≥ 1 | ≥ 1 | the ordinary greenness walk |

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
  (`[AC01] foo` → `[AC55] foo TWICE`), reads as `removed` + `added`. `removed` is report-only and
  `added` deliberately never blocks on greenness, so **one PR** can discard an AC-to-test
  obligation without ever entering the `changed` set. **Disposition: reported, not blocked, and
  the reason is that no remediable predicate exists at this layer.** Blocking on "base had links"
  is *unfixable inside the PR* — base is immutable, so an author legitimately retiring a criterion
  *and* its test would fail forever with no action available. The predicate that IS remediable —
  *the criterion is gone but its `@covers` tag survives, now pointing at nothing* → remove or
  retarget the tag — is precisely **p3.7(b)'s orphan detector, hard from day one** (SPEC §8 E2);
  building a second copy here is how two gates drift, which this campaign has already paid for
  once. So p3.6 emits a dedicated **`removed_with_bindings`** key in its JSON on every PR, making
  the shape visible in the CI log rather than only in this document, and p3.7(b) blocks it. Named
  explicitly on p3.7(b)'s card (§10 item 8b) alongside the two-PR sequence.
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
  a fourth reason code and a fourth arm in a module already at the source-size limit, for a flow
  this repo has never performed. Recorded so that the first real occurrence is a two-line
  follow-up rather than a mystery.

---

## 8. Rulings adopted — all seven, none open

| # | Ruling | Where it lands |
|---|---|---|
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
- **AC-K4 (added minted AC never blocks on greenness):** a new `[ACnn]` present only at head with
  no binding → `added` + `unbound`, exit `0`.
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
  list for p3.7 to consume. **Three companion assertions pin the one vocabulary (§5.3):**
  (a) `base_links >= 1, head_links == 0` → `binding_removed`, exit `1` (AC-K14);
  (b) **`base_links >= 1` with a head node PRESENT but `tests` EMPTY → `binding_removed`, exit
  `1`** — the exact input on which the node vocabulary and the link vocabulary disagreed, written
  to fail against round 3's node-presence phrasing; (c) `base_links == 0, head_links >= 1` → the
  ordinary greenness walk, not `unbound`.
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
| 1 | Spec Compliance | **pass, with two named deviations** | All three sub-iterate ACs have a mechanism (§5.2, §5.3, §5.6) and tests (AC-K1/K2/K5/K14). D10's bug-intent gap is closed *by construction*: intent is never consulted anywhere, so `intent=bug` cannot exempt anything. D12 honoured — FR-level `Layers` untouched, AC-level is the index on top. **Two deviations, both explicit and both to be repeated in the PR body: (i) D9's baseline is dropped (ruling Q1); (ii) AC-1's "named" is spec-DERIVED, not author-declared (Q1b).** Round 1 reported only the first and called the rest compliance — corrected. |
| 2 | Error Handling | **fail (round 2) → fixed** | Round 1's worst error-handling defect was in this column: AC-K9(d) made an ordinary authoring choice an exit-2 infra failure. Round 2 fixed the *verdict* (exit 1 + authoring remedy) but **not the scope** — the guard still fired on any FR repo-wide, so one intro sentence anywhere would have redded every later PR including docs-only ones, contradicting AC-K1. Round 3 scopes it to FRs whose `criteria_digests` actually changed in this PR (§5.1), with AC-K9(d)(ii) written to fail against round 2's unscoped form. Lesson recorded: a downgraded severity is not a fixed blast radius. |
| 3 | Security Basics | **fail (round 2) → fixed, twice over** | Round 1 shipped a **trivially dodgeable gate** (deleting a `/ACnn` suffix turned a HARD block into exit 0). Round 2 added `binding_removed`, but wrote `unbound`'s condition as "no node at base **or** head" — which *is* `binding_removed`'s own input, so AC-K8 and AC-K14 asserted opposite verdicts for identical input and **a builder following AC-K8 would have reinstated the hole**. Round 3 makes the two conditions disjoint (base-yes/head-no vs base-no/head-no) with explicit precedence, and AC-K8 now carries a companion assertion pinning it. Residual, named rather than hidden: the **two-PR unbind sequence** (§7), routed to p3.7(b) as a real card. |
| 4 | Test Quality | **pass** | AC-K6 targets the `_cov_status` ∃/∀ trap; AC-K14, AC-K9(d)(ii) and AC-K11's `master` case are each written as regressions **against this document's own earlier rounds**, not merely as passes against the current one; AC-K8's companion assertion makes the round-3 precedence unimplementable-as-overlapping; AC-K15 pins reader drift; AC-K7 pins the node-id-space trap; AC-K10 now asserts `evaluate_binding_completeness` is *not* called. The diff-coverage/subprocess constraint is a stated build rule. |
| 5 | Performance Basics | **pass** | Per PR: two `read_all` parses per spec file, one extra `git show` for the base manifest (no regeneration), zero extra test executions, zero network calls. No measurable addition to an ~11-minute CI run. |
| 6 | Naming & Structure | **fail (round 2) → fixed** | Follows the family's pure-core / git-layer / adapter split; no new abstraction with one caller; no new severity vocabulary; no new evidence format; no manifest schema change; F11 seam kept but unshipped per Q4. **The round-2 defect was a naming one with teeth:** §5.5's heading claimed "reuse P3.3's rule", but `evaluate_binding_completeness` tests the *inverse* direction (evidence outranking the declared binding, not a binding covering less than required) — a builder reaching for it would have implemented the wrong predicate. §5.5 now states reused (`_LAYER_RANK`, `route_gap_severity`) vs. new (the comparison itself) explicitly. |
| 7 | Affected Boundaries (ADR-024) | **pass** | (i) **spec.md → `ac_identity.read_all` → digest** — probed against the REAL 268-criterion spec at two real commits; **and the round-2 work found the real hazard here was not the one round 1 named**: it is the divergence from the *other* criteria reader (§5.1), now guarded and drift-pinned. (ii) **JUnit → `test_links.generate_file` → `acs[ac_id]` → gate** — probed against a REAL CI run's 17 443 outcome lines across all 142 bound links, which both falsified §2.3 and surfaced the node-id-space constraint. (iii) **base manifest via `git show`** — new this round; the v3-base degradation is reasoned (no `acs` ⇒ zero links ⇒ outcome cannot fire) but **not yet probed**; Probe C covers the head side only. (iv) **gate → `ci.yml` step contract** — still not probeable pre-merge; pinned by AC-K12. Two boundaries probed against production data, one reasoned, one pinned-by-shape-test and disclosed. |

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
| 6 | glm · low | Retiring a requirement while editing its criterion yields `binding_removed`, whose remedy ("restore the `@covers` tag") is unactionable — the tag still exists; the retirement zeroed the count. | **rejected-with-reason, recorded as a limitation.** The outcome is fail-**closed** (the reviewer says so), so nothing is let through; only the message misroutes. The fix costs a fourth reason code and a fourth arm in a module already at the 300-line limit, to serve a flow — retire an FR and edit its criteria in one PR — that has occurred zero times in this repo's history. Reported here rather than fixed silently; if it fires once, it is a two-line follow-up. |
| 7 | glm · low | `not_selected` is a catch-all for any `executed` value other than `pass`/`fail` (e.g. `"error"`). | **rejected-with-reason.** The message already interpolates the observed value (`executed={executed!r}`), so the operator sees the real cause rather than only the label, and the outcome blocks either way. Splitting `"error"` into the `failed` remedy would encode a value the manifest schema does not currently emit — a speculative branch with no producer. |
| 8 | glm · low (test) | The CLI harness (`_manifest_with_binding`, `_run`, `_edit_ac01`) is copy-pasted verbatim into the second test module rather than living in `_keystone_repo.py`. | **accepted-and-fixed.** Hoisted to `_keystone_repo.bound_manifest` / `run_gate` / `edit_ac01`, with the reason recorded in that module's docstring: two copies of "the manifest the gate is graded against" can diverge silently, and the module asserting the *weaker* shape would still be green. |

**Contradiction resolution (glm approve vs openai reject).** The reject rests on findings 1 and 2,
which are the two ratified rulings — the reviewer is grading the implementation against the
sub-iterate spec's unscoped sentence, and the scope was narrowed on the record at the plan-review
gate, twice, with the narrowing repeated in the shipped source. Its third and fourth findings are
real and are fixed. So: the contradiction is not about the code, it is about which version of the
requirement is authoritative, and that question was already decided.

### 12.2 Self-Review (Step 3.6, against the BUILD)

| # | Item | Verdict | Note |
|---|---|---|---|
| 1 | Spec Compliance | **pass, two named deviations** | Q1 and Q1b, both ratified and both stated in the shipped module docstring so they survive the merge (§11 item 1). |
| 2 | Error Handling | **fail → fixed** | Found here first: `EmptyLinkWalk` escaping `main()` is a Python exit 1 — indistinguishable in a CI log from a real hard finding, so a gate defect would send an author to edit a spec that is fine. Now caught → exit 2 with JSON. External review then found the *same shape* at a different boundary (finding 3), which is the honest reading of this row: the class was identified, one instance of it was not. |
| 3 | Security Basics | **pass** | No new trust artifact, no new persisted state, no network. `github.sha` is interpolated as a SHA (no injection surface). The base read is fail-closed three ways and its one permissive branch is surfaced under its own JSON key. |
| 4 | Test Quality | **pass** | 46 + 43 cases; the load-bearing ones fail against this document's *earlier rounds*, not merely pass against the current one. In-process `main(argv)` throughout with exactly one subprocess smoke, because subprocess-only tests contribute 0 % to the hard 80 % diff-coverage gate. |
| 5 | Performance Basics | **pass** | Two spec parses and one extra `git show` per PR; no regeneration, no extra test execution. |
| 6 | Naming & Structure | **pass** | Five modules, each under 300 lines by *extraction* (`_keystone_finding`, `_keystone_layer_gap`, `_keystone_base_manifest`), never by baselining. No new abstraction with one caller. |
| 7 | Affected Boundaries (ADR-024) | **pass** | See §12.3 — all four boundaries probed or pinned, and (iii) moved from *reasoned* to *measured* this round. |

### 12.3 Confidence Calibration (Step 3.8)

Probes run: **8**. Findings: **4**. Asymptote: **reached for the base-manifest boundary, NOT
reached for the gate as a whole** — and the second half is the honest answer, so it is stated
rather than rounded up.

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

**Two consecutive no-finding probes on the base-manifest boundary** (B.2 then B.3) after B.2's
predecessor — the round-3 review's "first place to look" — is the asymptote condition for *that*
boundary, and it is met.

**It is not met for the gate as a whole, and the trend says so.** §11's tally recorded rounds
where self-review found 1, 1, 0 defects while review found 0, 3, 6. This round: self-review found
1 (the `EmptyLinkWalk` exit code), external review found 3 real ones and 2 correct scope
objections. That is an improvement in the ratio but not a convergence, and one of the three
external findings was *the same failure class* self-review had just named at a different boundary.

**Edge cases NOT probed, and why that is acceptable:** (i) the `ci.yml` step's real behaviour on a
`pull_request` event — not probeable before merge by construction, pinned by eleven shape
assertions and observable on this very PR; (ii) the fuller regeneration-integration probe (finding
4) — deferred with a card, with the specific bypass pinned structurally; (iii) a merge-queue
`merge_group` event — this repo has none, and a tripwire test fails the moment one is enabled.
