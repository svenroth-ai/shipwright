# Iterate — Ship the action-pinning posture RULE to adopters

- **Run ID:** `iterate-2026-07-19-adopter-pinning-posture-rule`
- **Type:** CHANGE · **Complexity:** small · **Spec Impact:** NONE
- **Triage:** `trg-0ce59c05` (CI-Security 2/2 — item 1 of anchor `trg-9509c2e8`)
- **Upstream decision (NOT re-opened):** GitHub-owned actions on mutable tags,
  third-party SHA-pinned, no hosted updater. **Portability, not cost.**

## Problem

An adopted repo gets correct workflows but **nothing tells the next author why**.
The first well-meant "let's pin everything for supply-chain safety" silently
reverses the posture — which is exactly how webui #285 happened, in a repo that
had the state right and had never written the reason down.

## The card's premise was false — three findings

`trg-0ce59c05` states *"VERIFIED ALREADY CORRECT (do not redo)"* for
`shared/templates/`. Measured before building:

1. **`astral-sh/setup-uv@v3` was NOT pinned in the shipped template**, while the
   monorepo pins it to `caf0cab7…` for itself. The framework held itself to a
   stricter standard than it shipped — the exact inversion of a template's job.
2. **`AikidoSec/github-actions-wf@v1` does not exist.** `gh api` returns 404 for
   both the tag and the repository. `ci-supabase-nextjs.yml.template` shipped a
   `security:` job that could never run for anyone, and additionally demanded an
   `AIKIDO_SECRET_KEY` secret nobody holds.
3. `svenroth-ai/shipwright/…/diff-coverage-gate@main` is **deliberate** and
   already pinned by `test_ci_template_diff_coverage` / `test_diff_coverage_action`
   — adopters track the gate as the framework evolves it. No action.

**Why this mattered before writing a line:** the requested guard ("third-party
actions must be SHA-pinned") would have failed on findings 1 and 2 **on its own
PR**. A gate that is red on the commit introducing it cannot ship — the same
bootstrap self-contradiction the external review caught in the Phase-1 register,
where the draft seeded only some entries while requiring all of them.

Scope was widened deliberately and with the user's approval: fix the state, then
ship the rule and the guard, so all three land consistent.

## Design

| Layer | File | Role |
|---|---|---|
| Rule (shipped) | `shared/templates/claude-md-template.md` | adopters inherit the *why*, not just the state |
| Guard | `shared/tests/test_action_pinning_posture.py` | both-directions drift gate over the shipped templates |
| State | `ci-python-plugin-monorepo.yml.template` | `setup-uv` SHA-pinned to the framework's own commit |
| State | `ci-supabase-nextjs.yml.template` | dead Aikido `security:` job removed |

**Why the Aikido job was removed rather than pinned.** A reference that 404s has
no SHA to pin, so "pin it" is not an available fix. Verified safe: adopt scaffolds
`.github/workflows/security.yml` (Trivy + Gitleaks + Semgrep) independently of the
CI template, so removing a job that never ran removes no coverage — it removes a
false claim of coverage.

**Templates are matched as text, not parsed YAML** — they carry `{PLACEHOLDER}`
tokens and `if: ${{ … }}` expressions that break a strict loader. Same reasoning
as the accepted-risk reconciler's targeted extraction from `security.yml`.

## External review (GPT-5.4 + Gemini 3.1 Pro, both succeeded)

Four findings, **all real, all fixed** — and every one of them was a way for the
guard to pass while the thing it guards was broken. That is the same failure
family the sibling iterate hit; a guard's own blind spots are where it lies.

- **GPT high + Gemini medium — quoted and dynamic `uses:` values evaded the
  scanner entirely.** `uses: "evil/action@v1"` and
  `uses: evil/action@${{ inputs.version }}` are valid workflow YAML, but the
  first-cut regex matched the action shape *inline*, so neither matched at all —
  they slipped past **both** direction checks while the non-vacuity count still
  passed. → the regex now captures the whole scalar and classification happens
  in Python; anything unresolvable **fails closed**. Four evasion forms are
  negative-controlled.
- **GPT medium — `glob` missed nested templates.** A template in a subdirectory
  is still shipped to adopters. → `rglob`.
- **GPT medium — the updater check only caught `dependabot.*`.** Renovate under
  any of its filenames would have passed, despite AC-1 forbidding "or
  equivalent" — and the framework's own `risk_detectors` already knows those
  names, so the guard was weaker than the predicate it mirrors. → explicit
  filename set covering both vendors.
- **GPT low — the rule-shipping test was vacuous.** It checked for a heading and
  three bare words, so it would still have passed if the rule had been *inverted*
  into "pin everything and add Dependabot". → it now asserts the five normative
  claims, and fails naming whichever one disappeared.

## Acceptance Criteria

- **AC-1** — The posture rule ships in `claude-md-template.md`, stating the
  asymmetry, naming **portability** (not cost) as the reason, and forbidding a
  dependency-updater config. An adopter inherits the reasoning with the state.
- **AC-2** — A guard fails in **both** directions over every shipped workflow
  template: a third-party action not pinned to a 40-char SHA, and a GitHub-owned
  action that *is* SHA-pinned. Both were watched going red on a deliberately
  mutated template; neither is assumed.
- **AC-3** — The guard is non-vacuous: it asserts it found templates and ≥10
  `uses:` entries, so an empty or moved directory fails loudly rather than
  passing silently.
- **AC-4** — No dependency-updater config is shipped to adopters, asserted rather
  than assumed.
- **AC-5** — Every shipped template satisfies the posture in this same diff, so
  the guard is green on the PR that introduces it.

## Deliberately out of scope

- **Extending `CI_SUPPLYCHAIN_FILE_PATTERNS` to `shared/templates/`.** Measured
  gap: the ack gate matches only this repo's `.github/**`, so an edit to a
  *shipped* CI template changes every future adopter's trust boundary while
  escaping the gate. Not closed here because the concrete failure mode — template
  drift in either direction — is now blocked by a hard test, which is the
  stronger control; the ack is the broader "make someone think" mechanism. Filed
  as its own card rather than folded into a small iterate.
- **Shipping the accepted-risk register + `converge` to adopters** — the third
  step named in `iterate-2026-07-18-accepted-risk-alert-convergence`, now
  unblocked ("proven here first") but distinct from this card. Filed separately.

## Test Completeness Ledger

28 tests over 7 behavior groups, **0 testable-but-untested.**

| # | Behavior | Disposition |
|---|---|---|
| 1 | third-party action not SHA-pinned → FAIL (per template) | tested — watched red on a mutated template |
| 2 | GitHub-owned action SHA-pinned → FAIL (per template) | tested — watched red on a mutated template |
| 3 | guard is non-vacuous (templates found, ≥10 `uses:`) | tested |
| 4 | no dependency-updater config shipped to adopters | tested |
| 5 | the posture rule reaches `claude-md-template.md` with all five normative claims intact | tested — would fail if the rule were inverted |
| 6 | quoted / dynamic / bare `uses:` forms are all extracted (6 shapes) | tested (review GPT high) |
| 7 | third-party evasions fail CLOSED; a quoted GitHub-owned SHA-pin is still caught | tested (5 negative controls) |

No `untestable` rows: every behavior is a text assertion over tracked files.

**Confidence-pattern check.** Both guard directions were driven red by mutating a
real template and restored from git, so the gate is proven on the bug it exists
to catch rather than asserted. Coverage breadth is every `*.template` under
`shared/templates/github-actions/`, parametrized per file so a failure names the
offending template. `cross_component` does not fire — no merge/churn resolver,
hook, phase validator, or campaign machinery is touched. **Not claimed:** this
does not close the ack-gate blind spot for shipped templates (see out of scope).
