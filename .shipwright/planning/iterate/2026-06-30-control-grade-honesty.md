# Iterate Spec — Control-Grade honesty (Goodhart-resistant verdict)

- **Run ID:** `iterate-2026-06-30-control-grade-honesty`
- **Intent:** CHANGE (compliance scoring) · **Complexity:** medium
- **Spec Impact:** NONE (compliance-internal — no tracked FR; `change_type=compliance`,
  per the established convention for Control-Grade work, e.g. AR-10 #291 and the
  anchor-wording #290, both of which also changed grade output)
- **Trigger:** reviewer comments A/B/C/D on the Control-Grade dashboard (Goodhart
  risk, pass-rate≠coverage, safety-critical wording, missing native Scorecard).

## Problem

The dashboard can show **A / 100 — "under full control"** while the very signal
that *is* control over AI changes decays:

- **A (Goodhart).** The grade's traceability `tag_rate` uses the *broad*
  `count_traced` (credits classified no-FR work), so a freeze of genuine
  FR-tagging (3% vs 18% all-time) only surfaces as a WARN row in Quality
  Indicators — it never touches the headline. By design (`_traceability.py`
  "honesty counterweight"), but the headline still lies.
- **B (pass-rate ≠ coverage).** Answered, not built here: we do **not** measure
  diff/patch coverage. `test_health` is pure pass-rate; the Test Completeness
  Ledger is an author-*claimed* checklist, not instrumented execution. → split
  out as a **fast-follow** iterate (CI `--cov` + `diff-cover` + grade input).
- **C (wording).** Anchors cite `DO-178C / IEC 62304 / ISO 26262` (avionics /
  medical safety-certification standards). No literal over-claim exists, but the
  vocabulary is needlessly attackable. Pivot to software-engineering / NIST
  standards.
- **D (anchor).** The real `ossf/scorecard-action` is **not** wired — "OpenSSF
  Scorecard" is only a methodology citation. Stand up the native action so the
  recognized 0–10 anchor actually runs (native-score *display* = fast-follow).

## Decision (approved with the user)

The disease is structural: a single aggregate can average/exclude away **any**
dark or declining pillar — traceability today, security tomorrow. So:

1. **Traceability-decline penalty (the number moves).** A *self-relative* FR-tag
   decline (recent strict-tag rate below the repo's own all-time rate; full
   freeze = max) applies a **capped** reduction (≤35%) to the
   requirement-traceability dimension. Self-relative ⇒ a stably-low infra repo is
   *not* punished; only erosion of the repo's own discipline is.
2. **Weakest-link verdict gate (the headline can't lie).** The headline
   **score+letter move together** (no "B (95/100)" contradiction). The number
   stays the OpenSSF-style weighted average **unless** a *load-bearing* control
   pillar (`requirement_traceability`, `test_health`, `change_traceability`,
   `security`) is:
   - **(a) declining** (traceability trend) → can't read "A": ceiling 89 (top of B);
   - **(b) a dark *expected* control** — named in `expected_dimensions` but n/a
     (e.g. `security.yml` exists but no CI summary ingested) → ceiling 89 +
     "verification incomplete"; (this is the "100 while security tests don't run"
     guard — symmetric, not traceability-special);
   - **(c) outright broken** (F-band, score < 0.5) → weakest-link cap to F.
   Supporting dims (reconciliation, size, deps) shape the *number* via the
   average but never hard-cap the verdict.
3. **C wording.** One open standard per Anchor (de-crowd):
   `requirement_traceability → ISO/IEC/IEEE 29148`,
   `change_reconciliation → ISO/IEC/IEEE 12207`, `security → NIST SSDF`,
   `change_traceability → SLSA`, `dependency_hygiene → OWASP`,
   `test_health → OpenSSF Scorecard`, `maintainability → ISO/IEC 25010`.
   Update the guide's plain-language table + the `OPEN_STANDARDS` test allowlist.
4. **D.** Add `.github/workflows/scorecard.yml` (native action, SARIF upload;
   `publish_results` gated on public-repo) + adopt scaffold for adopted repos.

**Backward-compat invariant:** all new `GradeInputs` fields default to "no
signal" (`fr_tag_*_pct=None`, `expected_dimensions=()`), so the repo-agnostic
scorer and every synthetic-input test behave exactly as before. New behavior
lights only when the Shipwright adapter (`build_grade_inputs`) supplies the
signals — keeping the kernel repo-agnostic for the future generic grader.

**Intended, accepted consequence:** the monorepo dogfood grade drops from ~A100
to **B** ("Controlled, minor gaps — traceability declining"). That is the point.

## Affected Boundaries

- `control_grade.py` scoring kernel (new inputs, penalty, verdict gate, anchors).
- `_control_block.py` adapter (lights trend + `expected_dimensions`).
- `_traceability.py` (extract `fr_tag_trend` SSoT shared by the row + the grade).
- `docs/guide.md` dimension table (C).
- `.github/workflows/scorecard.yml` + adopt workflow scaffold (D).
- Regenerated `.shipwright/compliance/dashboard.md` (via finalize compliance regen).

## Out of scope (named fast-follows)

- **B** — diff/patch coverage (CI `--cov` + `diff-cover` + `test_health` input).
- **D2** — render the native Scorecard 0–10 next to the custom grade (needs the
  action to have produced output on `main` first).
- **WebUI propagation** — webui runs vendored compliance copies → separate webui
  iterate re-applies A+C, adds `scorecard.yml`, regenerates its dashboard.

## Acceptance Criteria

1. A self-relative FR-tag decline reduces the requirement-traceability dimension
   score (capped) and marks it a gap with a "declining" detail.
2. A traceability decline caps the headline below A (score ≤ 89, letter ≤ B) with
   a verdict reason naming the decline.
3. A dark *expected* control (e.g. `security` n/a while expected) caps below A and
   the verdict says "verification incomplete"; with no expectation, behaviour is
   unchanged (stays A).
4. A broken load-bearing pillar (F-band) caps the headline to F; a broken
   *supporting* dim does not hard-cap.
5. No anchor cites `DO-178C` / `IEC 62304` / `ISO 26262`; every anchor names
   exactly one allow-listed open standard; guide table matches.
6. `scorecard.yml` exists, lints/parses, models `security.yml` conventions, and
   does not become a blocking required check.
7. All pre-existing `test_control_grade.py` cases stay green (back-compat).

## Confidence Calibration

- **Boundaries touched:** `control_grade.py` (scoring kernel), new
  `_grade_gate.py` (honesty layer), new `_grade_types.py` (value model split out
  to stay <300 LOC), `_traceability.py` (`fr_tag_trend` SSoT), `_control_block.py`
  (adapter), `docs/guide.md` (dimension table), `.github/workflows/scorecard.yml`.

- **Empirical probes run:**
  - *Live grade recomputation* on the real repo (`collect_all` →
    `build_grade_inputs` → `compute_grade`): **A100 → B (89)**, verdict
    "traceability declining (FR-tag 7% vs 18% all-time, last 30)"; security stays
    measurable + green (not a false incompleteness cap). The intended honest drop.
  - *Adversarial opus code review*: found **1 blocker** — the decline penalty fed
    the broken-pillar F-collapse cap, so the future generic grader would false-`F`
    any repo with `req_pre ∈ [0.5, 0.71]` + a real decline. **Fixed:**
    `requirement_traceability` removed from the collapse set (erosion = decline,
    not collapse) + regression test `test_decline_penalty_never_triggers_the_F_collapse_cap`.
  - *Repo visibility* confirmed **PUBLIC** via `gh repo view` → `publish_results:
    true` is valid; job guarded to the canonical repo so forks don't fail.
  - *YAML parse* of all `.github/workflows/*.yml` OK; *ruff* clean repo-wide;
    *full compliance suite* 918 passed; *shared suite* passed.

- **Test Completeness Ledger** (testable ⇒ tested; 0 untested-testable):

  | Behavior | Status | Evidence |
  |---|---|---|
  | self-relative decline severity (freeze/relative/stable/improve) | tested | `TestDeclineSeverity` (5) |
  | capped (≤35%) traceability penalty, never zeroing | tested | `TestTraceabilityPenalty` (3) |
  | decline caps headline below A | tested | `TestVerdictGateDecline` |
  | non-binding decline ⇒ no false "Capped:" | tested | `test_nonbinding_decline_does_not_claim_capped` |
  | dark *expected* control caps + "incomplete" | tested | `TestVerdictGateDarkExpected` (2) |
  | broken collapse pillar → F | tested | `test_broken_load_bearing_pillar_caps_to_F` |
  | decline never triggers the F-collapse cap | tested | `test_decline_penalty_never_triggers_the_F_collapse_cap` |
  | supporting/excluded dim broken ≠ hard-cap | tested | `test_broken_supporting_dim_does_not_hard_cap` |
  | 1 open critical = gap, not cap | tested | `test_one_open_critical_is_a_gap_not_a_hard_cap` |
  | anchors off safety-critical + single standard | tested | `TestAnchorPivot` (3) + `test_every_anchor_names_an_open_standard` |
  | adapter lights fr_tag trend + security expectation | tested | `TestBuildGradeInputsHonestyGate` (4) |
  | `fr_tag_trend` SSoT keeps the row byte-identical | tested | `TestRenderTracedRow` (existing, unchanged) |
  | back-compat: no-signal ⇒ unchanged scorer | tested | pre-existing `test_control_grade.py` fixtures stay green |
  | `scorecard.yml` runs the native action | untestable | `requires-external-nondeterministic-service` (GitHub Actions); YAML parse + SHA-pin verified |

- **Confidence-pattern check:**
  - *Depth (asymptote):* the gate math was probed at the boundaries (0.0 freeze,
    relative drop, stable-low, improvement; the 0.5 collapse line from both
    sides) — not "I'm confident it's right".
  - *Breadth (coverage):* all three gate conditions (decline / dark-expected /
    collapse) + the supporting-dim exclusion + the anchor pivot + the adapter are
    each covered; the live probe closes the unit-test→real-data gap.
  - *Integration composition:* not `cross_component` (no merge/hook/phase
    machinery touched); the adapter↔gate↔scorer composition is covered by the
    live `collect_all` probe.

## Review-driven calibration decisions (deliberate, documented)

- **Security collapse → F (review #4).** A measurable `security` dimension below
  0.5 (≥2 open high/critical vulns) F-caps the headline. For a security-first
  control grade this is intentional: many unaddressed criticals are not "minor
  gaps". A *single* critical (0.66) stays a gap shaped by the average, not a cap.
- **Fresh-adopt "verification incomplete" (review #2).** A repo with a
  `security.yml` but no ingested CI summary is B-capped with "security not
  measured". This is **correct honesty**, not a false positive: a configured-but-
  unrun control is incomplete verification, not full control. The future generic
  grader (fast-follow) must ingest the target repo's actual security state rather
  than infer expectation from the template file.
