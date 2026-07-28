# Iterate Spec: security-scope-and-parity

- **Run ID:** iterate-2026-07-27-security-scope-and-parity
- **Type:** change
- **Complexity:** medium
- **Status:** complete

## Goal

Put the coverage manifest to work. Part 1 made a security scan record what it did
not check; this makes three decisions honour that record — the project's own
accepted findings, whether a finding may be called fixed, and how far to go
before changing anything.

## Ownership boundary

Owns the security plugin's scanner wiring, its report generator, and the
presentation of findings to the operator. Does **not** own workflow files:
labelling the verdict at the workflow step belongs to the card that owns the host
checks.

**Part 2 of 2.** Part 1 (`#455`, merged as `8154e1bc`) established the manifest.
The split existed because the four items together measured 288,963 reviewable
chars against a 200,000 cap — the PR-Review gate fails closed above it. Every
item here reads the coverage rows, which is why this is stacked rather than
parallel. This half measures 136,559 (0.68x).

## Acceptance Criteria

- [x] **AC-1 — One accepted-findings answer per repository.** When the scanned
      target root has a `.gitleaks.toml`, the local secret scan **extends** it
      (`[extend] path`) instead of substituting a generated configuration, so the
      local path reaches the same verdict as the host workflow, which already
      auto-loads that file. With no project file present, the previous generated
      config (`[extend] useDefault` plus the shipwright exclusions) is unchanged.
      **The wrap costs one extension level — and that is tested, not assumed.**
      A repo whose own config is already a chain (`.gitleaks.toml` →
      `base.toml` → defaults) is resolved by the host in two hops and by the
      local path in three. If gitleaks stops short of the third, the built-in
      rules never reach the local scan and it reads clean where the host reports
      a secret — precisely the false-clean this AC removes. The external review
      raised it as HIGH; it cannot be settled from documentation on a machine
      with no scanner installed, so it is settled by
      `test_a_project_config_that_is_already_a_chain_keeps_parity`, which runs
      the two scans against the real binary and compares them. The only
      difference it permits is the shipwright path exclusions.
      **If that test fails, the wiring changes, not the test:** for a chained
      project config the local scan passes that config directly and forgoes the
      shipwright exclusions, recording their absence on the `secrets` row —
      parity is the guarantee, exclusion is the convenience.
- [x] **AC-2 — `useDefault` and `path` are never both emitted.** Gitleaks aborts
      on a config setting both; the renderer emits exactly one. Proven against
      the real binary, not just the rendered TOML.
- [x] **AC-3 — An ineffective ruleset is a degradation, not a footnote.** Because
      the two `extend` keys are mutually exclusive, extending moves responsibility
      for the built-in ruleset to the project's file. A `.gitleaks.toml` bringing
      no rules therefore scans for almost nothing — that forces the `secrets`
      class to `degraded`, so `is_complete()` is false, the report banner names
      it, and the card cannot say "every class was checked". A degradation applies
      ONLY to a class that would otherwise be `covered`.
- [x] **AC-4 — Compare two runs only over shared ground.** `resolved` / `new` /
      `persisting` are computed only for classes both runs covered; every other
      class is listed under `not_comparable` with the reason. A sidecar with no
      manifest makes nothing comparable. No per-finding outcome is stored — the
      answer is derived from the two sidecars on demand.
- [x] **AC-5 — Severity split and scope question at the point of work.** One
      collapsed `security-scan:{repo}` action unit carries the count at every
      severity, the unchecked classes, and a launch payload instructing the
      executing agent to state those counts and ask how far to go. `SKILL.md`
      gains a mandatory Step 2.5 scope gate.

      **Split honestly between code and prompt.** What is *executable* and tested:
      the card's counts, the concrete scope tiers (`security_card.scope_options`
      is the SSoT for the wording), and the instruction to ask. What is
      *prompt-only*: the remediation loop in Steps 3-5 is driven by an agent
      reading `SKILL.md`, not by a Python engine — so "findings outside the scope
      become `deferred`" is an instruction to that agent, not code this card ships.
      The external review flagged the original wording for implying an executable
      scope filter; it does not exist and is not claimed. The `deferred` state and
      its `remediation.deferred` counter are pre-existing fields of
      `shipwright_security_config.json` that the loop already writes. Wiring a
      machine-enforced scope would need a remediation engine — a separate card.
- [x] **AC-6 — Nothing untrusted reaches the operator as prose.** Manifest-derived
      labels and caller-supplied values are rendered as data in the
      instruction-bearing payload, and the comparison reader applies the same
      sanitizing boundary as the report generator.
- [x] **AC-7 — No file exceeds where this pair of cards started.** Part 2 spends
      some of Part 1's reduction; every touched baselined file stays at or below
      its pre-Part-1 value.

## Spec Impact

- **Classification:** modify
- **MODIFY:** FR-01.07 — two new (E) acceptance criteria: run-to-run comparison
  gated on equal coverage, and one accepted-findings answer per repository with an
  ineffective ruleset reported as untrustworthy rather than clean.
- **ADD / REMOVE:** none.

**MINT-vs-FOLD:** FOLD — new guarantees of an existing capability.

The severity-split-and-ask behaviour needs no new criterion: FR-01.07 already
states *"how many there are at each severity is stated and the choice of how far
to go is put to that person — the tool never silently decides that the less severe
ones do not matter."* This implements it.

## Out of Scope

- Turning incomplete coverage into a **CI verdict** — sibling host-checks card.
- Failing the local scan when a tool is absent.
- Replacing the per-finding triage mirrors with the collapsed card. The card is
  emitted *alongside* them; the enumeration's dedup contract is untouched.

## Design Notes

Three new library modules plus one CLI, each well under 300 LOC:

| Module | Responsibility |
|---|---|
| `gitleaks_config.py` | resolve + inspect the project `.gitleaks.toml`; render the temp config that extends it; report an ineffective ruleset as a class degradation |
| `scan_compare.py` | coverage-gated diff of two sidecars, plus its markdown rendering |
| `security_card.py` | severity split, concrete scope options, card title/detail/launch payload |
| `tools/compare_scans.py` | the operator entry point over `scan_compare` |

### Why the degradation is forced rather than annotated

The first version detected a rule-less project config and wrote the reason into
the `secrets` row's `detail` while leaving the status `covered`. `is_complete()`
then stayed true, the report showed no banner, and the card said "every class was
checked" beside a detail saying the scan looked for almost nothing. Detection that
changes no decision is not detection. The status is forced instead — but only for
a class that would otherwise be `covered`, because `degraded` outranks
`not_requested` and `not_available`, and overwriting either would put a false
statement in the manifest.

### Why no per-finding outcome is stored

An outcome written into a scan record ("fixed on Tuesday") is frozen at a moment
when the coverage question may not have been asked. Deriving it from two sidecars
means the gate is applied every time, so the comparison cannot go stale.
`compare_scans` never mutates its inputs.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `gitleaks_config.render_config` | the `gitleaks` CLI | generated TOML extending the project's |
| `run_scan_and_report.py` | `scan_compare` / `compare_scans.py` | `latest.json` + `history/scan-*.json` |
| `security_card.build_scan_action_unit` | `.shipwright/triage.jsonl`, Command Center | triage item + launch payload |
| `scan.py` (`class_degradations`) | `findings.json` `coverage[]` | the manifest's `degraded` rows |

`touches_io_boundary` fires — round-trip tests write with the real producer and
read with the real consumer.

## Confidence Calibration

- **Boundaries touched:** the four pairs above.

- **Empirical probes run:**
  - *Do the two leak guards both fire?* Before: only mine did — my `rmtree` erased
    the evidence before the other session's `sessionfinish` hook could see it, so
    theirs was dead code. Verified by reintroducing a leak. After removing the
    delete: both fire and the evidence survives.
  - *Does the other guard's path list cover everything?* No — probed a leak into
    `.shipwright/securityreports/`, which `run_scan_and_report.py` writes and this
    card's tests drive. Their three filenames miss it; mine catches it. That is
    why both stay.
  - *Does the re-apply actually work?* It did not, at first. After importing
    `gitleaks_config.write_config`, the old local `_write_gitleaks_allowlist` was
    still defined in `oss_backend.py` and shadowed it — 26 tests failed with
    `TypeError: takes 1 positional argument but 2 were given`. Removed; suite green.
  - *Does gitleaks accept the generated config?* Not verifiable here — no scanner
    binary on this machine, which is the very condition Part 1's manifest reports.
    Deferred to CI, where gitleaks 8.21.2 is installed and
    `test_gitleaks_extend_smoke.py` hard-fails if it is absent. It passed on
    Part 1's PR twice (run 30251298886 and again on #455), proving default rules
    still fire, the project allowlist applies, and the shipwright exclusions
    survive.
  - *Does gitleaks resolve a relative `extend.path` against the process's
    working directory?* The first CI run answered yes, by way of the chained
    smoke test tripping its own fixture guard: the host-equivalent leg, launched
    from the plugin directory, found NOTHING — the project's `gitleaks-base.toml`
    was simply unreachable. So `_run_gitleaks` now runs the subprocess at the
    scanned target, as the host workflow does. The generated config's own extend
    path was absolute and never the problem; the project's INTERNAL chain was.
    Pinned by `test_gitleaks_runs_at_the_repo_root.py`, verified by removal.
  - *Does the wrap survive a project config that is ALREADY a chain?* Open, and
    deliberately so. The second review round raised it as HIGH: wrapping spends
    an extension level, and a two-hop project chain becomes three. Asserting a
    depth limit read from documentation would be the unfalsifiable-confidence
    anti-pattern, so the question is put to the binary —
    `test_a_project_config_that_is_already_a_chain_keeps_parity` runs the host's
    scan and the local scan over the same repo and fails if they disagree beyond
    the shipwright exclusions. It executes in CI on this PR, hard-fails if
    gitleaks is missing, and its failure message names the fix. The wiring is
    therefore shipped with the claim under test rather than with the claim
    assumed.
  - *Will the review truncate again?* Measured with the gate's own
    `filter_generated_paths`: 136,559 chars against the 200,000 cap.

- **Test Completeness Ledger:** machine-readable in
  `shipwright_test_results.json.iterate_latest.test_completeness`; every behavior
  `tested` with evidence, 0 testable-but-untested.

- **Confidence-pattern check:**
  - *Asymptote (depth):* the two failures that motivate the card are each pinned
    by a test that fails if the gate is removed —
    `test_losing_a_tool_between_runs_reports_nothing_fixed` and
    `test_the_class_is_degraded_not_covered`. Six external review rounds against
    the unsplit diff found thirteen defects; all are carried here already fixed,
    and the final round returned no findings.
  - *Coverage (breadth):* 712 tests in the security plugin (7 skipped — the
    real-binary smoke legs, which execute in CI), 9 in `shared/tests` for the
    card's producer/consumer round trip. F0 green across all 18 units: 11,313
    passed of 11,340 collected, 422 integration, zero failures — summed from
    each unit's junit XML rather than carried over from an earlier run, which is
    how the previously recorded figure turned out to be ~1,400 low. ruff clean.
  - *Integration composition:* `cross_component` does not fire — no hooks, no
    merge/churn/event-log resolver, no phase validator, no campaign machinery.
    `touches_ci_supplychain` does not fire: no `.github/workflows/**`,
    `.github/actions/**` or `dependabot.yml` path is in the diff, which is this
    card's ownership boundary.
