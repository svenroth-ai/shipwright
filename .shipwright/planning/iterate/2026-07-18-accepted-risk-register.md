# Iterate — Scanner-agnostic accepted-risk register (record + enforcement)

- **Run ID:** `iterate-2026-07-18-accepted-risk-register`
- **Type:** CHANGE · **Complexity:** medium · **Spec Impact:** NONE
  (framework record + gate machinery; no product requirement changes behaviour —
  same classification as the sibling `iterate-2026-07-18-ci-supplychain-risk-flag`)
- **Triage:** `trg-15a8e267` (CI-Security 1/2 — item 4 of anchor `trg-9509c2e8`)
- **Follow-up filed:** `trg-13b8283b` (CI-Security 1b/2 — item 2, surface convergence)
- **Upstream decision (NOT re-opened):** webui ADR
  `iterate-2026-07-18-unpin-actions-no-dependabot` — GitHub-owned actions on mutable
  tags, third-party SHA-pinned, no hosted updater. Portability, not cost.

## Problem

Accepting a risk means doing one of three unrelated things, only one of which a
human ever sees again:

| Channel | Scope | Expiry? | Visible where? |
|---|---|---|---|
| `.trivyignore.yaml` (`vulnerabilities[]`) | SCA / CVE only | **yes** (`expired_at`) | dashboard row |
| `SHIPWRIGHT_SEMGREP_EXCLUDE_RULES` / `…_ACCEPT_GH_OWNED_ACTION_TAGS` in `security.yml` | SAST rules | **no** | a prose table in `docs/security-ci-setup.md` |
| Manual dismissal in the GitHub Security tab | any code-scanning alert | **no** | nowhere in the repo |

**GAP 4 — the only due date in the system is bolted to the wrong scanner.**
`parse_accepted_risks` (`ci_security.py:163-201`) reads *only* `.trivyignore.yaml`,
and only its `vulnerabilities` key. It is the sole producer of the dashboard's
`EXPIRED — re-review` row (`:246-258`). So webui had to register a **Semgrep /
CI-posture** decision inside a **Trivy** ignore file to obtain a due date at all — an
acknowledged semantic stretch. Nothing reads an ADR `Re-Review-Date`
(`shared/constitution.md:54` mandates the field; no parser consumes it).

## Scope of THIS iterate (Phase 1 of 2)

Make an acceptance a **recorded, validated, time-bounded, enforced** object.
Converging the code-scanning surface (GAP 2) is `trg-13b8283b`.

**Why the parent card's "MERGED ON PURPOSE" is not violated.** Its stated worry was
that item 2 would be built against a Trivy-shaped register and migrated days later.
This phase fixes the register shape first, so 1b/2 is built against the generalized
register from the start. Both external reviewers independently called the merged
scope too large. The letter of the card is broken; its rationale is preserved.

**Honest consequence:** after this iterate the repo can still show red for a
consciously accepted risk. That is 1b/2's job, and it is named as such rather than
implied to be covered.

## Empirical findings that shaped this spec

### P1 — the divergence is in the shipped product

`shared/templates/github-actions/security.yml.template:88` runs raw
`semgrep scan --config auto --sarif`; `:121-124` uploads that SARIF untouched.
Adopted repos have **no register at all**: acceptance is applied at ingest
(`security_findings._findings_from_sarif`, ADR-260), quieting triage while
code-scanning keeps the alert. The monorepo converges only because its SARIF is
generated `--input-from-cache findings.json` (`security.yml:139-143`), i.e. *after*
normalizer tailoring — an accident of ordering, not a designed property.

### P2 — dismissals persist across re-scans, and a recorded rationale is wrong

`decision_log.md:3319` / `:3332` rejected dismissing code-scanning alerts, stated
rationale *"reappear each scan"*. Contradicted by this repo's own data:

- 22 CodeQL alerts dismissed **2026-06-27**
- `most_recent_instance.commit_sha` = `7c303a8b`, merged **2026-07-18**
- still `state: dismissed`

CodeQL re-observed them three weeks after dismissal; they stayed dismissed.
`updated_at` does **not** advance on re-observation, so the naive probe
(`updated_at > dismissed_at`) reports zero and reads as "never seen again" — a false
negative that would have inverted the 1b/2 design.

**What those ADRs actually rejected** — dismissal *as a substitute for fixing* —
stays rejected. The correction is recorded because this iterate descends from a card
about changes that contradict recorded decisions; stepping over them quietly would
repeat #285 inside the fix for #285.

### P3 — expiry has no teeth

`parse_accepted_risks` computes `expired` and only prints it. No gate reads it;
`shared/tests/test_trivyignore_register.py:37-46` asserts `expired_at` is *present*,
never that it is in the future.

### P4 — two silent holes in the existing parser

- `_TRIVYIGNORE_NAMES` (`:50`) covers `.trivyignore.yaml|.yml`, but the scanner side
  `_resolve_trivy_ignorefile` (`oss_backend.py:277-294`) *also* honours classic
  `.trivyignore` — a repo using it gets real suppression with **zero** visibility.
- The parser drops `statement`, `paths`, `purls` (`:194-200`) — the justification and
  scope, exactly the audit-relevant fields, never reach a human surface.

## External review (GPT-5.4 + Gemini 3.1 Pro, both succeeded — 15 findings, 5 high)

Two findings would have shipped broken.

- **BOTH (high) — bootstrap self-contradiction.** The draft seeded only the Semgrep
  acceptances and left the Trivy CVE out of the register, while AC-4 demands every
  suppression have an entry. The drift gate would have failed on this very PR. → every
  existing source-controlled suppression is seeded (AC-6); `.trivyignore.yaml` remains
  Trivy's operational input.
- **GPT #1 (high) — nothing invokes the tools.** A producer and a gate wired to no
  mandatory path document risk without constraining it — *literally the defect
  diagnosed in P3*. → both run as tests under `shared/tests/`, the path CI already
  requires, alongside the existing `test_trivyignore_register.py` policy test. No
  workflow edit, so no `touches_ci_supplychain` ack is pulled into a change that is
  not about the CI trust boundary.
- **GPT #2 (high) — "both directions" undefined across scanner types.** A CodeQL or
  Scorecard acceptance has no source-controlled counterpart; it is a GitHub
  dismissal. → explicit **target types** (AC-4), and the static gate covers only
  source-controlled ones and **says so in its output** rather than skipping silently.
- **GPT #4 (high) — expiry does not restore visibility.** → in this phase an expired
  entry is a hard test failure (AC-3). Reopening alerts belongs to 1b/2 and is carried
  on that card.
- **Gemini (high) — `--apply` permissions.** Deferred with the rest of `--apply` to
  1b/2; scope-checked (public repo, `repo` scope, admin) but deliberately **not**
  proven by a test mutation, since the only honest test overwrites a real alert
  comment. Carried on `trg-13b8283b`.
- **Gemini (medium) — `safe_load` on `security.yml`.** `if: ${{ … }}` breaks strict
  YAML. → targeted text extraction of the `env:` values, never `safe_load` (AC-5).
- **Gemini (low) — classic `.trivyignore` is flat text, not YAML.** → separate branch
  (AC-2).
- **Gemini (low) — timezone.** → expiry evaluated against UTC (AC-1).
- **Gemini (low) + GPT #9 — script proliferation / duplicate dashboard rows.** → one
  CLI with subcommands; one logical row per acceptance correlating register metadata
  with its operational counterpart (AC-2).
- **GPT #6 (medium) — a malformed register must not read as "all entries removed"**
  and mass-dismiss. → reconciliation only after a fully successful parse (AC-1).
- **GPT #8 (medium) — absent vs malformed.** Absent register = empty legacy register
  for dashboard/grader reads (old repos, temp test roots); malformed = fail closed;
  enforcement commands require presence (AC-1).
- **GPT #5, #7 (medium) — match keys, pagination, repo identity.** All concern
  `--apply`; carried verbatim onto `trg-13b8283b`.
- **DEFERRED, not rejected — GPT #4's alert-reopening.** It is the right end state,
  but it needs the matching machinery 1b/2 builds; implementing it here would mean
  building the matcher twice.

## Design

The register is the single **human-authored record**. Scanner wiring stays where it
is; a both-directions drift gate ties them together.

**Rejected — generating `.trivyignore.yaml` and the `security.yml` env vars from the
register.** `.trivyignore.yaml` would become a generated tracked artifact needing
**four** churn-reconciliation sites wired
(`iterate-2026-07-18-churn-allowlist-test-traceability`) or iterate merges abort, and
the env vars cannot be generated without editing a live security workflow. Real cost,
live gate, no gain over enforcement.

| Layer | File | Role |
|---|---|---|
| Register (human-authored) | `shipwright_accepted_risks.yaml` (repo root) | scanner-agnostic acceptances |
| Reader + validation | `shared/scripts/accepted_risks.py` | parse, validate, expiry (UTC) |
| CLI | `shared/scripts/tools/accepted_risks_cli.py` | `check` · `expire` (`apply` → 1b/2) |
| Human surface | `plugins/shipwright-compliance/scripts/lib/ci_security.py` | correlated render, offline |
| Enforcement | `shared/tests/test_accepted_risks_register.py` | drift + expiry as required tests |

`accepted_risks.py` sits directly under `shared/scripts/` per the cross-cutting-helper
rule (`iterate-2026-05-11-test-hygiene-helper-and-self-review-wiring`).

### Register shape

```yaml
schema: 1
acceptances:
  - id: ar-2026-06-30-gh-owned-mutable-tags
    target: semgrep-policy-toggle     # see target types below
    rule: "…github-actions-mutable-action-tag…"
    scope:
      owner: [actions, github]
    expires: 2026-12-30               # REQUIRED, evaluated at UTC
    rationale_ref: "iterate-2026-07-18-unpin-actions-no-dependabot"   # REQUIRED
    statement: >-                     # REQUIRED
      GitHub-owned actions stay on mutable tags by framework decision …
```

`rationale_ref` reuses the recognizer settled in PR #401 (`ADR-NNN`,
`iterate-YYYY-MM-DD-*`, `#NNN`, `DO-NOT #NNN`), so an acceptance cannot cite prose no
recorded decision backs.

### Target types (GPT #2)

| `target` | Operational counterpart | In static drift gate? |
|---|---|---|
| `trivy-ignore` | entry in `.trivyignore{.yaml,.yml,}` | yes |
| `semgrep-rule-exclusion` | rule id in `SHIPWRIGHT_SEMGREP_EXCLUDE_RULES` | yes |
| `semgrep-policy-toggle` | `SHIPWRIGHT_SEMGREP_ACCEPT_GH_OWNED_ACTION_TAGS=1` | yes |
| `github-dismissal` | a GitHub code-scanning dismissal | **no** — needs live API (1b/2) |

An unknown `target` is a validation error, not an ignored row.

### Why `parse_accepted_risks` is extended, not replaced

Its only production caller is `render_ci_security` (`:246`), but
`plugins/shipwright-grade/scripts/lib/reuse_bridge.py:85-92` re-exports siblings for
the cold-repo grader. Returned dicts **gain** keys (`target`, `source`, `statement`,
`rationale_ref`) and keep `id`/`expired_at`/`expired` — additive, so existing tests
and the grade bridge are unaffected. `ci_security.py` stays **pure and offline** per
its docstring contract; no network call is added there.

## Acceptance Criteria

- **AC-1** — The register parses into validated entries. Missing `expires`,
  `rationale_ref`, `statement` or an unknown `target` is an **error**, not a skipped
  row. Duplicate ids and invalid dates are validation failures. Expiry is evaluated
  against **UTC**. **Absent** register = empty legacy register for dashboard/grader
  reads; **malformed** register fails **closed** and never reads as "no acceptances"
  or "all entries removed".
- **AC-2** — The dashboard renders **one logical row per acceptance**, correlating
  register metadata with its operational counterpart (`registered + active in
  .trivyignore.yaml`), carrying target, expiry, status, rationale ref and statement.
  Classic flat-text `.trivyignore` is parsed by a separate branch (closes P4).
  A suppression with no register entry renders distinctly as drift, not as accepted.
- **AC-3** — An expired acceptance **fails a required test**. Expiry is no longer
  render-only (closes P3).
- **AC-4** — The drift gate fails when a source-controlled suppression has no register
  entry **and** when a `trivy-ignore` / `semgrep-*` entry matches no real suppression.
  `github-dismissal` entries are **excluded and reported as excluded** — the gate
  prints what it does not cover rather than capping silently.
- **AC-5** — `security.yml` env values are extracted by targeted text parsing, never
  `safe_load`; the file is **read, never written**.
- **AC-6** — Every existing source-controlled suppression (the Trivy CVE and both
  Semgrep channels) is seeded into the register in this diff, so AC-4 passes on this
  PR (the bootstrap finding).

## Deliberately out of scope

- **Surface convergence / `--apply`** → `trg-13b8283b` (1b/2), carrying GPT #5, #7,
  Gemini's permission finding, and GPT #4's alert-reopening.
- **Recording the 22 live CodeQL dismissals as register entries** — each is a
  per-alert judgment, and matching them needs 1b/2's machinery. Named here so the gap
  is visible rather than implied closed.
- **Adopter reach** (`shared/templates/`) — proven here first. Distinct from
  `trg-0ce59c05`, which ships the action-pinning posture rule, not the register.
- **Item 5, audit-level contradiction detection** — stays unpromised.

## Confidence Calibration

- **Boundaries touched:**
  - **New parse boundary** — `shipwright_accepted_risks.yaml` (hand-written YAML →
    `Acceptance`). `touches_io_boundary` fires (`yaml.safe_load`).
  - **Existing parse boundary, widened** — `.trivyignore{.yaml,.yml,}`; the flat
    form is newly read.
  - **Foreign-format boundary** — `.github/workflows/security.yml`, read by
    targeted text extraction, never written.
  - **Render boundary** — the compliance dashboard's CI-Security section.
  - The boundary is **read-only in this diff**: nothing here writes the register,
    so a producer/consumer round-trip has no producer to drive. The probe is
    therefore file → parsed entry → rendered row, run against the **real** repo
    register rather than only synthetic fixtures.

- **Empirical probes run:**
  - **P1** adopter template uploads untailored SARIF → the divergence is in the
    shipped product, not just here (`security.yml.template:88,121-124`).
  - **P2** code-scanning dismissals **persist** across re-scans: 22 alerts
    dismissed 2026-06-27 carry `most_recent_instance.commit_sha 7c303a8b` (merged
    2026-07-18) and are still `dismissed`. The first probe using `updated_at`
    returned zero and read as "never re-observed" — a **false negative** that
    would have inverted the 1b/2 design. It also falsifies the rationale recorded
    at `decision_log.md:3319`/`:3332`.
  - **P3/P4** expiry was render-only; the parser ignored the classic
    `.trivyignore` the scanner honours, and dropped `statement`/`paths`/`purls`.
  - **Live gate run** — `accepted_risks_cli check` on this repo: 3 register
    entries reconciled against 3 real suppressions, no drift; `expire` clean.
    This is the bootstrap finding both reviewers raised, closed empirically.
  - **Pre-existing-failure baseline** — the full `shared/tests` suite was run on
    clean `origin/main` (`7c303a8b`) and on this branch. **Identical 5 failures**
    (`test_architecture_md_reflects_arch_impact` on another iterate's drop, 4×
    `test_setup_writes_canonical` ADR-044/045 cross-plugin pollution); 4388 → 4425
    passed, the delta being this iterate's new tests. The failures are inherited,
    not introduced — asserted against a measured baseline, not assumed.
  - **sys.path-pollution probe** — the first cut had the compliance view import
    the shared `tools` package, which is exactly the ADR-044 coupling. Reworked to
    two bare-name leaf modules and an `append` (not `insert(0)`) so shared
    `lib/`/`tools/` can never shadow a plugin's own; compliance suite 1200/1200.

- **Test Completeness Ledger:** 62 new tests over 17 behavior groups (the machine-
  readable ledger in `shipwright_test_results.json` carries the 17 rows),
  **0 testable-but-untested.**

  | # | Behavior | Disposition |
  |---|---|---|
  | 1-6 | absent → `[]`; malformed / empty / missing-key / unknown-schema → `RegisterError`; explicit `acceptances: []` valid | tested (`test_accepted_risks`, 6) |
  | 7-8 | valid register parses; ISO-string `expires` accepted | tested (2) |
  | 9-16 | per-field validation: missing `expires` / missing `rationale_ref` / unknown `target` / unparseable date / filler ref / prose ref / empty id / short statement | tested (parametrized, 8) |
  | 17-18 | duplicate ids rejected; all four `rationale_ref` forms accepted | tested (2) |
  | 19-21 | expiry boundary inclusive; `expired()` filters; `today_utc` is UTC | tested (3) |
  | 22 | decision-ref recognizer pinned == the PR #401 gate (drift, both ends) | tested (1) |
  | 23 | `github-dismissal` in `TARGETS` but not `STATIC_TARGETS` | tested (1) |
  | 24-27 | live repo: register ↔ suppressions agree; nothing past due; register loadable + non-empty; every seeded ref is a recorded decision | tested (4) — **these are the gate** |
  | 28-32 | drift negative controls: unrecorded / stale / matching-pair-clean / non-static not counted as drift / unchecked reported | tested (5) |
  | 33-39 | parsing edges: commented env lines inert; `${{ }}` workflow parsed; toggle truthiness ×5 | tested (7) |
  | 40-41 | classic flat `.trivyignore` read; YAML form wins over flat | tested (2) |
  | 42-47 | `main()`: check/expire pass on real repo; non-zero on drift; exit 2 fail-closed on malformed; no-op without register; expiry vs drift reported separately ×2 | tested (6) |
  | 48-52 | dashboard correlation: registered+active is ONE row; registered-only flagged; unregistered = drift; audit fields reach the row; expiry vs `now` | tested (5) |
  | 53-54 | degradation announced on malformed register; absent register is not a degradation | tested (2) |
  | 55-57 | trivyignore forms: flat read, YAML scope carried, missing file empty | tested (3) |
  | 58-61 | rendered section: unregistered not laundered into "accepted"; authority rendered; **expired AND unrecorded both reported** (composed status); degradation note rendered | tested (4) |
  | 62 | back-compat: `parse_accepted_risks` still returns `{id, expired_at, expired}` | tested (pre-existing `TestAcceptedRisks`, unmodified) |

  No `untestable` rows: every behavior in this diff is offline and deterministic.
  The one genuinely un-probeable claim — that a maintainer's token can PATCH a
  code-scanning alert — belongs to `--apply` and is carried on `trg-13b8283b`
  rather than asserted here.

- **Confidence-pattern check:**
  - **Asymptote (depth):** the two highest-risk paths are probed to the point of
    no new information — validation has a negative control per field, and the
    drift gate is proven to go red in *both* directions plus fail closed on a
    malformed register. The one bug this depth actually caught in-flight was the
    composed-status defect (an entry both unrecorded and expired reported only the
    first fact), found by a pre-existing test, not by a new one.
  - **Coverage (breadth):** all four boundaries above carry tests, including the
    two the old parser silently missed (flat `.trivyignore`, non-Trivy scanners).
  - **Composition:** `cross_component` does **not** fire — this diff touches no
    merge/churn resolver, hook, phase validator, or campaign machinery. The
    cross-module seam that does exist (compliance → shared leaf modules) is
    covered by running the full compliance suite (1200 passed) *and* the full
    shared suite against a measured `origin/main` baseline.
  - **Not claimed:** this iterate does not make the repo stop showing red for an
    accepted risk. That is GAP 2, and it is `trg-13b8283b`.
