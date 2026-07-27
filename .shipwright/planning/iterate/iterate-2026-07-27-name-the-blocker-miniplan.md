# Mini-Plan — iterate-2026-07-27-name-the-blocker

One theme: **a check that holds the cause must name the cause.** Four sites.

## 1. Delivery watcher names its blockers (AC A, B)

**New** `shared/scripts/lib/pr_blockers.py` — pure predicates + two thin `gh` shells:

| Function | Kind | Purpose |
|---|---|---|
| `unresolved_threads(nodes)` | pure | review threads with `isResolved == false` |
| `missing_required_checks(required, rollup)` | pure | required contexts absent from the rollup entirely |
| `summarize(merge_state, threads, required, rollup)` | pure | `{blocked_by:[…], detail:{…}}`, or `{unknown:true, reason}` |
| `fetch_review_threads(pr, repo)` | shell | `gh api graphql` (probe-confirmed on PR #439) |
| `fetch_required_contexts(repo, branch)` | shell | `GET /repos/…/rules/branches/<b>` (probe-confirmed, no admin needed) |

`watch_pr_delivery.watch()` keeps the last fetched payload and, **only when it is
about to return a `pending` verdict** (timeout or `--once`), attaches
`verdict["blockers"]`. Probing once at the end rather than per poll keeps a
30-minute watch at two extra API calls, not sixty. The probe is injected
(`probe=…`) so the classifier tests stay gh-free.

`mergeStateStatus` is already in `_GH_FIELDS` and currently unread — that is the
first blocker source, free of any new call.

**Contract held:** `classify_delivery` is untouched; `merged` / `closed` /
`checks_failed` and exit codes 0/2/3/4 are unchanged. A probe that raises is
caught and becomes `{"unknown": true, "reason": …}` — never a lost verdict.

**Alternative rejected:** a distinct terminal `blocked` status with its own exit
code. It is not terminal — a thread gets resolved and the PR merges — and F11
callers treat exit 4 as "keep watching". Report the cause, keep the verdict.

## 2. Handoff freshness keys on content (AC C)

**New** `shared/scripts/lib/canon_frontmatter.py` — `parse_canon_frontmatter()`
moved verbatim out of `hooks/generate_handoff_on_stop.py`, which then imports it.
One parser for one format; the hook shrinks (ratchet-safe direction).

**New** `shared/scripts/tools/verifiers/handoff_freshness.py` — the check moves
out of `iterate_checks.py` (at an ADR-093 bloat exception, 1062 lines) and gains
`run_id`. Pass when the canon frontmatter names the current run, or the body
does; fail (WARNING, as today) naming which run it *does* name; skip when no
`run_id` was supplied. **The mtime path is deleted, not weakened** — no
`st_mtime` remains in the check.

**Why this is not a new idea:** `hooks/generate_handoff_on_stop.py:82` already
decides staleness exactly this way. The verifier was the odd one out.

## 3. Cross-layer coverage sees a folded criterion (AC D, E)

**New** `shared/scripts/tools/verifiers/_layer_coverage_ac.py`:

- `criteria_digests(text)` — split a `spec.md` on `### FR-XX.YY` headings, digest
  each section's **criteria bullets only** (`- (E) …`, `- [ ] …`, `- [x] …`).
  Body prose and the heading are excluded deliberately: in a post-rollout repo a
  resolved change is a HARD gate, and a typo fix in surrounding prose must not
  demand executed-passing tests.
- `spec_texts_at(root, sha, paths)` — `git show <sha>:<path>`; a path absent at
  that side yields `""` (a new spec file is not an error).
- `commit_exists(root, sha)` — the honest infra distinguisher, so "git is broken"
  never masquerades as "nothing changed".

`evaluate_cross_layer(base, head, ac_changed_ids=None)` gains one optional pure
argument and **unions** AC-changed FRs into `changed_keys`. The union matters
twice: it fixes the reported could-not-determine case, and it fixes the quieter
half — today, if any *other* FR's row changed, an AC-only-changed FR is dropped
with no warning at all.

`could_not_determine` survives unchanged for the genuinely undecidable case
(spec hash moved, no row and no criteria changed) — AC E. It is **not** weakened
to a pass.

**Frozen contracts untouched:** no manifest field, no schema version, no churn in
the committed `test-traceability.json`. The gate reads the spec out of git using
`spec_path`, which every requirement node already carries.

## 4. A reply that is not a review is not a success (AC F)

`shared/scripts/lib/external_review_degraded.py` gains `classify_reply()` plus
two provider `finish_reason` readers. Two signals only, both **reported by the
provider itself** — empty/whitespace answer, and a provider-declared truncation
(`length` / `MAX_TOKENS`). No prose heuristics: guessing whether text "reads
like a review" would block real reviews.

`external_review.py` is at its bloat baseline (430), so the change is exactly
three swapped `return` lines and one widened import — net zero lines.
`count_succeeded()` already keys on `status == "success"`, so a `degraded` leg
stops counting with no change to the degraded-gate logic.

## Test plan

TDD, red first. Unit tests per site; plus **one integration test** — required
because touching `hooks/generate_handoff_on_stop.py` sets the `cross_component`
risk flag, which the F11 verifier recomputes from the diff:

> `test_handoff_freshness_composition.py` — the handoff that
> `generate_session_handoff` writes, that the stop hook decides to skip
> regenerating, is the same handoff the F11 verifier accepts. Three components,
> one canon-frontmatter format, proven end to end rather than each mocked.

## Order

1. `canon_frontmatter` extraction + hook rewire (smallest, unblocks 2)
2. handoff freshness verifier + integration test
3. `pr_blockers` + watcher wiring
4. `_layer_coverage_ac` + core union + gate wiring
5. external-review reply classifier
6. docs: `docs/hooks-and-pipeline.md` delivery-watch paragraph

---

## External plan review — dispositions (openrouter: Gemini + GPT, 17 findings)

Recorded in `.shipwright/planning/iterate/iterate-2026-07-27-name-the-blocker/reviews.json`
(`parse_status: structured`). Every finding is answered; none is left merely raised.

### Accepted — the plan changes

| # | Finding | Change |
|---|---|---|
| 1 | Multi-line criteria bullets would be missed (both reviewers, high) — **confirmed against `spec.md:60`, where `(E)` bullets do wrap** | Digest each criterion **including its continuation lines** (indented lines up to the next bullet / blank-then-unindented). Accept `-`, `*`, `+` and numbered markers. |
| 2 | `reviewThreads` needs pagination (both, high) | Query `first: 100` with `pageInfo.hasNextPage`. Unresolved threads found are reported; when the page is truncated the probe **never asserts "no unresolved threads"** — it reports `truncated`. |
| 3 | `commit_exists()` cannot separate "path absent" from "cannot read history" (GPT-9, high) | Existence is tested with `git cat-file -e <sha>:<path>`. Absent → `""`. Present but unreadable, or an unreadable base commit → **infra failure**, which at medium+ blocks. Never silently `""`. |
| 4 | Skipping on a missing `run_id` silently weakens the check (GPT-5) | No silent skip. A missing run id emits a visible "cannot evaluate: no run id" WARNING. |
| 5 | "the body names the run" is substring-loose (GPT-6) | One canonical body marker: the `- **Run ID**:` line **inside `## Current Iterate Progress`**, exact value, not substring. The handoff carries a second such line under `## Last Iterate` naming the PREVIOUS run — a loose search would have passed a handoff generated by the run before this one. **Partly declined:** the suggested "fail on a frontmatter/body mismatch" is not implemented. The two markers answer different questions (which run *generated* the file vs. which run the *branch* is on), so a disagreement is not evidence of staleness and failing on it would be a new false signal — the exact thing this iterate removes. Frontmatter decides when present; the body marker is the fallback when it is absent. |
| 6 | `finish_reason` shapes differ per provider (GPT-11) | Read `choices[0].finish_reason` (OpenAI/OpenRouter) and `candidates[0].finish_reason` (Gemini, enum or str). **Absent reason stays neutral** — never a degrade on missing metadata. |
| 7 | An unresolved thread is not universally blocking (GPT-3) | Report causes as *candidates*, and assert blocking only when corroborated by `mergeStateStatus == "BLOCKED"`. The observed merge state ships in the payload. |
| 8 | Rules endpoint: permissions + branch URL-encoding (GPT-2, Gemini-4) | Branch is URL-encoded. 401/403/404/unrecognised shape ⇒ that source is `unknown` — **never** read as "no required check is missing". |
| 9 | Spec paths must come from base ∪ head (GPT-10) | Union of both manifests' `spec_path` values, so a moved/renamed spec is still compared. |
| 10 | Subprocess + untrusted-string hygiene (GPT-12, Gemini-5) | All git calls go through the existing `_run_git` (argument list, `shell=False`); GraphQL values are passed as variables; blocker reasons are normalized and length-bounded, never echoed model content. |
| 11 | Hook import path after extraction (GPT-7) | The hook's existing `sys.path` bootstrap already puts `shared/scripts` first; verified by running the hook through its production entry point from an unrelated working directory. |

### Declined — with the reason

| # | Finding | Why not |
|---|---|---|
| 12 | Use a Markdown AST for criteria (Gemini-1, alt.) | Adds a parse dependency to a gate that must run in a bare finalization subprocess. Continuation-aware line parsing covers the two authoring forms the generators actually emit and is directly testable. |
| 13 | Support arbitrary heading levels / non-canonical FR ids (GPT-8, part) | The `### FR-XX.YY` anchor and the `^FR-\d{2}\.\d{2}$` id form are already pinned by the frozen manifest schema and by both generators. Widening the parser past the contract would invent a grammar no producer writes. |
| 14 | Re-fetch the PR at probe time for one consistency point (GPT-4) | The payload the probe uses **is** the final poll's fetch, taken immediately before the probe. The observed `mergeStateStatus` is included so the snapshot is self-describing; a second fetch would buy microseconds of freshness for an extra API call. |
| 15 | Paginate review threads to completion (GPT-1, part) | Bounded at one page of 100 with an explicit truncation flag. Unbounded pagination on a pathological PR is a worse failure mode than a flag that says "there may be more". |
