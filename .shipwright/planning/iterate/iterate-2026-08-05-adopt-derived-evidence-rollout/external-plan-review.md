# External plan review — iterate-2026-08-05-adopt-derived-evidence-rollout

Three rounds, `external_review.py --mode iterate`, provider `openrouter`,
`reviews_succeeded: 2`, `degraded: false` in all three.

| Round | Plan reviewed | openai | deepseek | Contradiction |
|---|---|---|---|---|
| R1 | initial mini-plan | `revise` | `revise` | none (agree) |
| R2 | revised mini-plan | `revise` | **`approve`** | none (agree within one step) |
| R3 | twice-revised mini-plan | `revise` | **`approve`** | none (agree within one step) |

R3 was requested by the operator as a confidence check before build. It was not a
formality: it returned **four findings, all new**, one of them a logical
inconsistency introduced by R2's own fix. The review record cites
`external-plan-review-r3.raw.json`.

Raw provider output for R2: `external-plan-review.raw.json` — that is the
artifact the review record cites, so the verdicts are provable rather than
transcribed. R1's raw JSON was not persisted (`external_review.py` prints to
stdout); R1 is summarised here from that output and is superseded by R2 anyway.

**Why R2 exists.** R1's findings were addressed in the plan, and the review record
refuses a completed `plan` marker recorded from prose — it demands
`--from external-review-json` so the verdicts are provable. Re-running on the
*revised* plan was the honest way to produce that artifact and validated the
revisions at the same time.

---

## Round 1 — both `revise`

| # | Finding | Severity | Disposition |
|---|---|---|---|
| R1-1 | `base=` derived from `HEAD` at Step H is an unstated timing invariant; `commit_at_adoption` is the authoritative record (raised independently by **both** reviewers) | high / medium | **ACCEPTED** — `--base` added, adopt passes the recorded value. Logged as a correction: the switch to the fifth mode silently changed the base source, and the two decisions were never coupled. *(The `HEAD`-when-absent fallback this first fix kept was itself removed at R3-1 — see below.)* |
| R1-2 | `release=None` must *remove* a stale `release=`, not merely omit it | medium | **ANSWERED BY PROBE** — `stamp_fixed_point` rewrites the whole banner line, so `release=v0.4.0` is removed (probed 2026-08-06). Regression test added as asked |
| R1-3 | Tests exercise the mode in isolation; the ordering guarantee is untested | medium | **ACCEPTED** — adoption-commit integration test |
| R1-4 | seven-vs-five discrepancy unresolved in the contract | medium | **ACCEPTED** — documented + set-agreement test |
| R1-5 | Group E text consumed by the WebUI; multi-command may break parsing | low | **ACCEPTED** — `_suggest` stays a single string |
| R1-6 | Unbounded amend retry could loop / overwrite | low | **ACCEPTED** — one attempt, path-limited |
| R1-7 | State the shared dependency on `stamp_fixed_point` / `write_back` | low | **ACCEPTED** — documented |

Agent-found from the same probes: `stamp_fixed_point` silently no-ops on a
banner-less document; and the function is `stamp_fixed_point`, not `stamp` (the
plan named it wrongly).

---

## Round 2 — openai `revise`, deepseek `approve`

All seven openai findings assessed as legitimate; none a false positive.

| # | Finding | Severity | Disposition |
|---|---|---|---|
| R2-1 | **The Group E remedy is not executable in the state Group E reports.** `preflight_pr` requires a clean tree, and the finding *means* the on-disk docs differ from their snapshot — so naming `--refresh-pr` alone lands the operator in `"the working tree has uncommitted changes"` | high | **ACCEPTED** — the suggestion names the ordered path the compliance skill already documents in Step 2c: `--restore`, then `--refresh-pr`. Verified by running it against `preflight_pr` in an integration test, not by string-matching |
| R2-2 | "Report the shortfall" is undefined at the call site; a JSON status with exit 0 is ignorable, and Step H could commit a half-stamped set | high | **ACCEPTED** — `status: "partial"` **and non-zero exit**; Step H proceeds only on a complete stamp or explicit `no_base`, so a partial stamp yields no commit at all |
| R2-3 | Falling back to `HEAD` is correct only when `commit_at_adoption` is *absent* — not when present-but-malformed/non-resolving, where a fallback manufactures plausible-but-false provenance | medium | **ACCEPTED** — explicit three-way resolution; malformed / literal `HEAD` / non-resolving → `no_base`, never a fallback. Validated with `git rev-parse --verify <sha>^{commit}`, not lexically alone |
| R2-4 | Production code consumes `COMPLIANCE_MDS` while correctness is defined over `REFRESH_SET`; drift is caught only when the test next runs | medium | **ACCEPTED** — the payload is built from the `.md` members of `REFRESH_SET` with a runtime invariant; the drift test stays as refactor protection |
| R2-5 | The no-commit Step-H path (skip verification, still commit) is untested and most likely to regress | medium | **ACCEPTED** — empty-repo onboarding integration test |
| R2-6 | The amend needs a final blob verification and must not sweep unrelated staged changes | medium | **ACCEPTED** — amended SHA re-run through `--verify-commit`; amend path-limited to the five |
| R2-7 | `commit_at_adoption` is repository-sourced data newly reaching rendered evidence and a subprocess argument; lexical validation alone permits symbolic revisions | low | **ACCEPTED** — canonical commit OIDs only, argv vectors never shell text, all resolution failures → `no_base` |

deepseek (`approve`) raised one medium — that condensing two recovery actions into
one suggestion string risks ambiguity — which is the same subject as R2-1 and is
resolved by the same ordered wording.

**openai's closing assessment:** *"the core design is sound: stamping only at the
adoption delivery point preserves deterministic ordinary rendering, and reusing
the existing fixed-point helpers avoids needless duplication."* The remaining
`revise` is about failure semantics and remedy executability — both now in the
plan — not about the approach.

---

## Round 3 — openai `revise`, deepseek `approve`

Requested as a pre-build confidence check. Four findings, **all new** — none a
restatement of R1 or R2.

| # | Finding | Severity | Disposition |
|---|---|---|---|
| R3-1 | **An absent `commit_at_adoption` falling back to `HEAD` reintroduces the exact timing failure R1 removed.** The plan refused the fallback for a *malformed* value but allowed it for an *absent* one; both mean the authoritative value could not be established | high | **ACCEPTED** — the asymmetry was unjustified. `--stamp-adopted` now never resolves `HEAD`: absent, malformed, literal `HEAD` and non-resolving all yield `no_base`. The generic `HEAD` default stays with `--stage`/`--pr`, which describe *now*; this mode describes *when onboarding read the repo*, which only the caller knows |
| R3-2 | The partial-stamp path **wrote before validating** — `write_back` preceded the completeness comparison, so an aborted adoption still left the repository mutated | medium | **ACCEPTED** — sequence reordered to stamp-in-memory → validate → write. The failure is now non-mutating; the integration test asserts worktree *and* index are unchanged |
| R3-3 | The `--restore` → `--refresh-pr` remedy is executable only when the evidence files are the *sole* working-tree changes; unrelated uncommitted edits still fail preflight, and that is a normal operator state | medium | **ACCEPTED** — the wording says unrelated changes must be committed or stashed too. New test with an unrelated dirty file, so the text cannot imply a guarantee it does not make |
| R3-4 | "Canonical commit object" was required in prose, but the plan never said the *resolved* full ID reaches the banner; `safe_commit` accepts abbreviated SHAs | low | **ACCEPTED** — the resolver returns the full verified ID and that value is stamped. Test asserts an abbreviated `--base` emits the full hash |

deepseek (`approve`) raised no blocking finding.

**openai's closing assessment:** *"the design is appropriately narrow and reuses
the established fixed-point stamping and verification mechanisms well."*

### Why build starts on a standing `revise`

The two reviewers agree within one step in all three rounds, so no contradiction
requires resolution. Every finding across R1–R3 (7 + 7 + 4) is dispositioned in
the plan, and R3's remaining `revise` names no unaddressed item — its own summary
scopes the objection to the two things now fixed. Three rounds also show the
findings converging in severity and shrinking in count (7 → 7 → 4) while moving
from approach to failure semantics to detail, which is the shape of a plan
settling rather than one still moving.
