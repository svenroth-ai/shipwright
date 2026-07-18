# Iterate — Accepted-risk surface convergence (code-scanning + triage)

- **Run ID:** `iterate-2026-07-18-accepted-risk-alert-convergence`
- **Type:** CHANGE · **Complexity:** medium · **Spec Impact:** NONE
  (framework tooling; no product requirement changes behaviour — same
  classification as the Phase-1 sibling `iterate-2026-07-18-accepted-risk-register`)
- **Triage:** `trg-13b8283b` (CI-Security 1b/2 — item 2 of anchor `trg-9509c2e8`)
- **Predecessor:** `iterate-2026-07-18-accepted-risk-register` (PR #404) — the
  scanner-agnostic register itself.

## Problem — GAP 2

Phase 1 made an acceptance a recorded, validated, time-bounded object with a
both-directions drift gate and an expiry that fails a required test. It
deliberately did **not** quiet the code-scanning alerts, so the repo can still
show red for a consciously accepted risk. That is the root cause of webui #285:
the acceptance lives in one place and the red lives in another, so the red gets
cleared by hand, without a record, by whoever is annoyed by it first.

Phase 1's own gate says so out loud — `accepted_risks_cli.py:22-27` reports
`github-dismissal` entries as UNCHECKED and names this card. This iterate is
what makes that line removable.

## Empirical findings that shaped this spec

Full probe log: the six probes below were run against live GitHub state and the
real repo before any code was written.

### P1 — the token CAN PATCH a code-scanning alert (closes Gemini's Phase-1 high)

Phase 1 recorded this as scope-checked but deliberately unproven, "because the
only honest test overwrites a real alert comment". There is a third option — a
**non-destructive discrimination probe**:

```
gh api --method PATCH repos/{owner}/{repo}/code-scanning/alerts/1259 -f state=bogus_state_value
-> HTTP 422  "bogus_state_value is not a member of [\"open\", \"dismissed\"]"
```

422 is *body validation*. A token without write permission is rejected with 403
**before** the body is ever validated. Reaching the validator therefore proves
authn+authz passed, and the request was rejected so nothing was mutated. The
permission question is now answered by measurement, not by a scope table.

### P2 — rule-id-alone matching is provably unsafe, on this very repo

Distinct `most_recent_instance.location.path` per `(tool, rule)` across the 50
dismissed alerts:

| paths | tool / rule |
|---|---|
| **8** | CodeQL `py/unused-global-variable` |
| 7 | Scorecard `PinnedDependenciesID` |
| 3 | Scorecard `TokenPermissionsID` |
| 2 | CodeQL `py/uninitialized-local-variable` |
| 2 | CodeQL `py/overly-permissive-file` |

The eight `py/unused-global-variable` dismissals each carry a **different**
rationale (`_OWNED_PREFIXES is imported by resolve.py`,
`LEGACY_COMPLIANCE_DIRNAME is allowlisted`, `_COPYLEFT_LICENSES is deliberately
retained`, …). They are eight independent judgments that happen to share a rule
id.

Decisive: the single currently-**open** alert (#1259) *also* carries
`py/unused-global-variable`. A rule-wide entry would have silently swallowed a
brand-new, never-reviewed finding. Loose matching is not a theoretical risk
here — it is a live one, and it would have fired on the first run.

### P3 — pagination is already sound; verified, not assumed

`gh api --paginate` at `per_page=10` over the 50 dismissed alerts returns 5
pages as a **single** 290 166-byte payload that `json.loads` parses as one list
of length 50. So `_gh_api(..., paginate=True)` merges top-level arrays
correctly and no new pagination machinery is needed — only a `state` parameter,
because `_fetch_alert_list` (`github_api.py:102-108`) hardcodes `state=open`.

### P4 — surface (a) is NOT what the card assumed, and building it as worded would be destructive

The card asks the tool to "dismiss the matching open triage items". There is no
per-code-scanning-alert triage item to dismiss:

- `github_triage/producer.py:159-166` collapses **all** code-scanning +
  Dependabot alerts into ONE repo-level action-unit
  `gh-security:{owner}/{repo}`.
- A census of the entire `.shipwright/triage.jsonl` finds 3 `gh-security:`
  items and zero per-alert items.
- The legacy per-finding prefixes (`github:code-scanning:` et al.) were
  **deliberately retired** and one-shot migrated away
  (`github_triage/resolve.py:36-49`). Reviving that model is not a gap to
  fill; it is a decision to re-open.

Dismissing the aggregate because one alert was accepted would silence **every**
security finding in the repo. That is why it is not built.

**What surface (a) actually is.** `generate_security_report.py:482-495` files
one triage item per *local scanner* finding, keyed
`{tool}:{check_id}:{file}:{line}` — the same `(tool, rule, path)` shape the
alert side needs. Those are the items an acceptance can legitimately retract,
and one matcher serves both surfaces.

**Honest reachability.** Ingest-time suppression (`semgrep_tailoring`, Trivy
`--ignorefile`) means an accepted rule normally never *becomes* a triage item,
and CodeQL/Scorecard are not local scanners at all. So the live residue is
exactly the **pre-acceptance backlog**: items filed *before* the acceptance was
recorded, which ingest suppression cannot retract. There are currently **0**
`source="security"` items in this repo, so this surface is proven on fixtures,
not on live data. It is specified that way rather than implied to be exercised.

### P5 — all 50 existing dismissals are human-authored, no machine provenance

Every sampled `dismissed_comment` is hand-written prose. So "never reopen a
human-dismissed alert" has a real 50-alert regression fixture, and the
provenance marker is introduced *going forward*: **absence of marker == human
== never touch**.

### P6 — repo identity is not free

`gh api repos/{owner}/{repo}/…` substitutes the placeholders from the **current
working directory's** git remote. A mutation addressed through placeholders can
therefore target a different repository than the one whose register was read.
`github_api.owner_repo(project_root)` is a pure local `git remote get-url
origin` parse — it is the correct authority, and every API path must be built
from that resolved literal.

### P7 — the one open alert is a fix, not an acceptance

Alert #1259 is `_TRIVYIGNORE_NAMES` at `ci_security.py:50` — dead code left
behind by **Phase 1's own** extraction of the widened view into
`accepted_risk_scan.py` (which owns `TRIVYIGNORE_YAML_NAMES`). No reference
survives. CodeQL is correct. It is deleted in this diff rather than accepted:
an iterate that builds risk-acceptance machinery is exactly the wrong place to
demonstrate accepting a risk that should simply be fixed
(`shared/constitution.md`, ADR-239).

## External review (GPT-5.4 + Gemini 3.1 Pro, both succeeded)

GPT-5.4 returned **block** with 5 findings. Three were real defects, one was a
spec error, one was a false positive. Gemini's response arrived mid-reasoning and
carried no actionable finding.

- **GPT #2 (high) — deleting the register left alerts suppressed forever.**
  `cmd_converge` returned early when no register existed, so marked alerts were
  never reopened. The `mark not in known` branch covered a removed *entry* but
  not a removed *file* — and the file case is the more likely accident. → AC-12;
  an absent register is now an empty entry set, not an early exit.
- **GPT #4 (medium) — overlapping entries double-claimed an alert.** Two active
  entries matching one alert would PATCH it twice (the second comment
  overwriting the first entry's marker), and then a lapse in *either* would
  reopen an alert the other still covered. → AC-11; claims are resolved before
  anything acts, and an overlap is CONFLICTED with neither entry acting.
- **GPT #3 (medium) — an unreadable triage store rendered as "converged".**
  `_open_security_items` collapsed every failure into `[]`, so "I could not
  look" read as "there was nothing there" — the exact silent narrowing this
  tool refuses everywhere else, and a test had *blessed* it. → AC-8; absent
  (`FileNotFoundError`) and unreadable are now distinct, and unreadable blocks
  the converged claim.
- **GPT #1 (high, spec) — the CLI contract did not match AC-3.** Correct catch,
  but the **spec** was wrong, not the code: `--apply` on a dry-run-by-default
  command is the established repo convention (`triage_gc.py:19-27`). AC-3 was
  corrected; a second verb would have been a novel posture for the same
  guarantee.
- **GPT #5 (low) — docs not updated. FALSE POSITIVE.** Both
  `docs/hooks-and-pipeline.md` and `docs/security-ci-setup.md` are updated in
  this diff; the diff handed to the reviewer was scoped to `shared/`, `plugins/`
  and the register, so it could not see them. An artifact of my diff scoping,
  not of the change.

## Design

One domain module, one CLI, two surfaces, **one match key**.

| Layer | File | Role |
|---|---|---|
| Domain (pure) | `shared/scripts/alert_convergence.py` | match keys, scope validation, plan computation, provenance |
| gh shell (thin) | `shared/scripts/github_code_scanning.py` | list alerts by state (paginated), PATCH one alert |
| CLI | `shared/scripts/tools/accepted_risks_cli.py` | `converge` (read-only) · `apply` (mutating) |
| GC registry | `shared/scripts/tools/triage_gc.py` | new dismisser + reason tokens |
| Enforcement | `shared/tests/test_accepted_risk_convergence.py` | plan validity + negative controls |

**Why a new leaf module and not `github_api.py`.** `github_api.py` measures 321
LOC against a baselined `current` of 321 (`shipwright_bloat_baseline.json:509`).
The anti-ratchet rule blocks at `measured > current`, so **one added line is a
hard pre-commit and CI failure**. The file already solves this exact problem the
same way (`github_api.py:29-32` re-exports from `security_findings` with
`# noqa: F401 - impl split for anti-ratchet`).

**Pure core / thin shell** (the `watch_pr_delivery.py` split). All matching and
planning takes plain dicts, so it is exhaustively testable offline and in-process
— which is also what the 80% diff-coverage hard gate requires, since a
subprocess-invoked CLI contributes no coverage.

### Canonical match key

```
(tool, rule, path)
```

Line number is **excluded**: it drifts on every edit above the finding, so
including it would create permanent false drift — the failure mode the review
finding named. Path is the discriminator that makes `rule` safe.

A `github-dismissal` entry declares its breadth **explicitly**:

```yaml
- id: ar-2026-07-18-example
  target: github-dismissal
  rule: py/unused-global-variable
  scope:
    tool: CodeQL                 # REQUIRED — rule ids are not unique across tools
    paths:                       # EITHER an explicit path allowlist …
      - path/to/one/file.py
    # match: rule-wide           # … OR an explicit rule-wide opt-in
  expires: 2027-01-18
  rationale_ref: ADR-NNN
  statement: >-
    …
```

Neither `paths` nor `match: rule-wide` present → the entry is **AMBIGUOUS**. It
is refused, reported, and matches nothing. There is deliberately **no implicit
singleton rule** ("if it happens to match exactly one alert, take it"): that
would silently widen the day a second alert appears, which is P2's failure mode
with extra steps. Reject ambiguous mappings rather than guessing.

### Provenance and the reopen rule

Every machine dismissal comment ends with a marker:

```
<statement, trimmed> [shipwright-accepted-risk: <entry-id>]
```

- **Reopen touches only marked alerts.** An alert whose comment carries no
  marker was dismissed by a human and is never reopened and never overwritten.
- On expiry (or on the entry's removal), the marked alerts appear in the plan's
  `to_reopen` set, so visibility is restored by the same mechanism that removed
  it. This closes GPT #4 from Phase 1, which was deferred, not rejected.

### Mutation posture

`converge` is read-only and is the default way to look at the surface. `apply`
is a separate, deliberate command that is itself **dry-run by default** and
requires `--apply` to write — the repo-wide convention (`triage_gc.py:19-27`).

No workflow is edited and no scheduled job is added: **no automated sweeper may
hold the authority to mass-dismiss security alerts.** A consequence worth
stating: this diff therefore does not touch `.github/workflows/**`, so
`touches_ci_supplychain` does not fire and no supply-chain ack is pulled into a
change that is not about the CI trust boundary.

### Alternative considered — generate dismissals from CI

Rejected. It is the shape that produces #285: a job that reconciles the security
tab on every push turns "accepted once, by a person, with a due date" into
"whatever the register said at 3am". The register is authored by a human and
applied by a human running a command; CI's job is to *fail* when the two
disagree, which Phase 1 already does.

## Acceptance Criteria

- **AC-1** — Canonical match key is `(tool, rule, path)`; line is excluded. A
  `github-dismissal` entry without `scope.tool`, and without either
  `scope.paths` or `scope.match: rule-wide`, is AMBIGUOUS: refused, reported,
  and matched against nothing.
- **AC-2** — `converge` is read-only and reports every disposition separately:
  to-dismiss, to-reopen, ambiguous, stale (entry matching no alert), and
  human-dismissed-untouched. It never collapses "not actionable" into "clean".
- **AC-3** — Mutation happens only under an explicit `converge --apply`. Read-only
  is the default; no workflow and no scheduled job gains dismissal authority.
  (An earlier draft of this AC specified a separate `apply` subcommand; the
  external review flagged the mismatch with the built CLI. The AC was corrected
  rather than the code, because `--apply` on a dry-run-by-default command is the
  established repo convention — `triage_gc.py:19-27`, and the same shape used by
  `aggregate_changelog`, `aggregate_decisions`, `backfill_test_links`. A second
  verb would have been a novel posture for the same guarantee.)
- **AC-4** — An alert is never dismissed without a backing, non-expired register
  entry. Enforced by construction (the plan is built by iterating entries) and
  pinned by a negative control.
- **AC-5** — Every machine dismissal carries `[shipwright-accepted-risk: <id>]`.
  Reopen selects **only** marked alerts; an unmarked (human) dismissal is never
  reopened and never overwritten.
- **AC-6** — An expired entry moves its marked alerts into `to_reopen`, so
  expiry restores visibility rather than merely failing a test.
- **AC-7** — Repository identity is resolved locally from the checked-out repo's
  `origin` remote and every API path is built from that literal; a mismatch or an
  unresolvable remote aborts **before** any mutation.
- **AC-8** — The alert listing is paginated across the states the plan needs, and
  a failed fetch returns `None` and can never read as "converged" (ADR-052).
  Likewise a triage store that exists but cannot be READ is reported as unread
  and blocks the converged claim — "I could not look" must never render as
  "there was nothing there".
- **AC-11** — Two active entries claiming the same alert are CONFLICTED and
  neither acts. Merging them would PATCH the alert twice (the second comment
  overwriting the first entry's marker) and would then let a lapse in either
  entry reopen an alert the other still legitimately covers.
- **AC-12** — Deleting the register entirely restores visibility exactly as
  expiry does. An absent register is not an early exit from `converge`; it is an
  empty entry set, so previously-marked alerts are still reopened rather than
  left suppressed with nothing in the repo left to explain why.
- **AC-9** — Open `source="security"` triage items whose
  `{tool}:{check_id}:{file}:{line}` key matches an entry are dismissed with
  `by="acceptedRiskConverger"` / `reason="acceptedRiskResolved"`, and **both**
  tokens are registered in `triage_gc.MACHINE_DISMISSERS` /
  `MACHINE_REASONS` in this same diff, so the new reason cannot escape the
  dismissed-pile GC.
- **AC-10** — Phase 1's UNCHECKED message stops naming this card as pending
  work, and `docs/hooks-and-pipeline.md` + `docs/security-ci-setup.md` describe
  the converged surface.

## Deliberately out of scope

- **Adopter reach** (`shared/templates/`) — shipping the register and this
  convergence to adopted repos is a third step, worth doing only once this is
  proven here. Distinct from `trg-0ce59c05`, which ships the action-pinning
  posture rule, not the register.
- **Recording the 50 existing human dismissals as register entries** — each is a
  per-alert judgment. The tool makes them *visible* as unrecorded; converting
  them is a human's call, not this diff's.
- **Reviving per-alert GitHub triage items** — deliberately retired
  (`resolve.py:36-49`); reopening that model is a decision, not a gap.

## Confidence Calibration

- **Boundaries touched:**
  - **New foreign-format parse boundary** — GitHub code-scanning alert JSON →
    `Alert` (`alert_match.alert_from_api`). `touches_io_boundary` fires.
  - **New network WRITE boundary** — `PATCH …/code-scanning/alerts/{n}`. The
    only mutating GitHub call in the framework's Python.
  - **New string boundary, both directions** — the provenance marker is written
    into a dismissal comment and parsed back out of one. Round-trip tested;
    truncation is tested not to eat the marker, because an unmarked machine
    dismissal is indistinguishable from a human's and becomes irreversible.
  - **Existing key boundary, re-read** — the triage dedup key
    `{tool}:{check_id}:{file}:{line}` is parsed by a second consumer.
  - **Registry boundary** — `triage_gc.MACHINE_DISMISSERS` / `MACHINE_REASONS`.

- **Empirical probes run:** P1–P7 above, all against live state before the
  design was fixed. The two that changed the design rather than confirming it:
  **P2** (rule-alone matching would have swallowed the one open alert, which is
  why breadth is declared and never inferred) and **P4** (the card's surface (a)
  does not exist as written; building it literally would have dismissed a
  repo-wide aggregate). **P1** answered by measurement the permission question
  Phase 1 recorded as unanswerable without overwriting a real comment.
  **Live gate run:** `converge` against real GitHub — 0 register entries, 51
  alerts paginated across two states, 50 human dismissals correctly reported as
  untouched, exit 0.

- **Test Completeness Ledger:** 124 new tests over 16 behavior groups,
  **0 testable-but-untested.**

  | # | Behavior | Disposition |
  |---|---|---|
  | 1 | alert payload → match key; every missing component → `None`, never partial | tested (11) |
  | 2 | line number excluded from the key | tested (1) |
  | 3 | marker round-trip; unmarked/malformed comment reads as human | tested (7) |
  | 4 | dismissal comment carries statement+ref+expiry; truncation preserves marker | tested (2) |
  | 5 | scope validation: tool required, breadth declared, mutually-exclusive, path/reason shapes | tested (12) |
  | 6 | matching: tool/rule/path, rule-wide, cross-tool isolation, ambiguous matches nothing | tested (8) |
  | 7 | triage key parse incl. colon-bearing check_id; unparseable → no match | tested (11) |
  | 8 | plan dispositions: dismiss / satisfied / human / reopen-on-expiry / reopen-on-removal / stale / ambiguous / expiry boundary | tested (13) |
  | 9 | no backing entry ⇒ never dismissed; non-github targets never reach the surface | tested (2) |
  | 10 | triage surface: match, non-match, expired-no-op, GC tokens registered + `is_machine_churn` | tested (4) |
  | 11 | rendering: every disposition printed; untouched summarised; clean renders nothing | tested (3) |
  | 12 | gh shell: slug validation (10 negative), pagination, `None`≠`[]`, PATCH bodies, failure surfaced, UTF-8 decode | tested (20) |
  | 13 | CLI: build_plan, identity abort, failed-listing abort, read-only vs `--apply`, failed mutation, dispatch, exit 2 | tested (18) |
  | 14 | this repo's register: every `github-dismissal` entry resolvable + marked; `converge` absent from every workflow | tested (3) |
  | 15 | overlapping entries CONFLICT and neither acts; a lapse in one does not reopen what the other covers (review GPT #4) | tested (2) |
  | 16 | absent vs unreadable triage store are distinct; unreadable blocks the converged claim end-to-end (review GPT #3) | tested (4) |

  No `untestable` rows. The one claim that could not be asserted offline — that
  the token may PATCH — is closed by probe P1 against the live API rather than
  asserted in a test, because the only test-shaped version mutates a real alert.

- **Confidence-pattern check:**
  - **Asymptote (depth):** the two dangerous paths are probed to exhaustion —
    matching has a negative control per refusal branch, and the reopen rule is
    proven not to fire on a human dismissal in both the expired and the
    entry-removed case. Depth paid twice: the ledger's group-8 tests caught a
    real defect (an expired entry matching a human dismissal dropped the alert
    from the report entirely — silently, which is the exact failure the Plan
    docstring forbids), and the live run caught a second (cp1252 decoding, which
    made the tool permanently non-functional on Windows while failing closed).
    Depth did NOT reach the asymptote unaided: the external review found three
    more, all of the same family — a state that renders as converged when it is
    not. Two of them (whole-register deletion, overlapping claims) were outside
    the space my negative controls covered, and one had been actively blessed by
    a test I wrote. Recorded because it calibrates how much a self-authored
    negative-control suite is worth: it caught the defects inside its own model
    of the problem and none outside it.
  - **Coverage (breadth):** all five boundaries above carry tests, including
    both directions of the marker boundary and the registry coupling.
  - **Composition:** `cross_component` does **not** fire — no merge/churn
    resolver, hook, phase validator, or campaign machinery is touched. The one
    real cross-module seam (the `triage_gc` registry) is covered by the
    pre-existing bidirectional drift test, which passes *because* the reason
    token was added; it would have failed had only the emitter shipped.
  - **Not claimed:** the triage surface has **0** live instances in this repo
    today, so it is proven on fixtures, not on live data. Its live reachability
    is the pre-acceptance backlog only, and that is stated in P4 rather than
    implied by the passing tests.
