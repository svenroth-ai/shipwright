# Mini-Plan: main-self-heal

- **Run ID:** iterate-2026-07-28-main-self-heal
- **Type:** feature · **Complexity:** medium
- **Spec:** `.shipwright/planning/iterate/2026-07-28-main-self-heal.md`
- **Revision:** 2 — rewritten after external plan review round 1 (both reviewers
  `revise`). Dispositions in §7.

---

## 1. Files to create / modify

### Create

| Path | What |
|---|---|
| `shared/scripts/lib/main_health.py` | **Pure core.** Run selection, per-commit verdict, attribution, log reduction + redaction, claim matching, escalation. No `gh`, no `git`, no clock — every input is a payload, every "now" is a parameter. |
| `shared/scripts/tools/main_health.py` | **CLI + shell.** The `gh`/`git` calls, assembly of the one JSON, exit-code contract. |
| `shared/scripts/lib/assertion_weakening.py` | **Pure detector, AST-based.** Compares the *parsed* before/after of each changed test file — never the diff text. |
| `shared/scripts/tools/check_repair_safety.py` | **The AC-6 hard rule, in code**, wired as a gating CI step so it refuses rather than advises. |
| `plugins/shipwright-iterate/skills/iterate/references/main-repair.md` | **AC-5 procedure** — prose, because the intelligence is the agent's. |
| `shared/tests/test_main_health.py` | Run selection predicate, per-commit verdict, overall status. |
| `shared/tests/test_main_health_attribution.py` | Attribution: exact / uncertain / none, gaps, window exhaustion, candidate partners. |
| `shared/tests/test_main_health_claim.py` | Claim matching, fork rejection, staleness, failed-attempt counting, log reduction + redaction. |
| `shared/tests/test_assertion_weakening.py` | One case per weakening class, one per fence, fail-closed on unparseable. |
| `shared/tests/test_main_attribution_workflows.py` | AC-1/AC-2/AC-6-gate invariants pinned on the real workflow YAML. |
| `plugins/shipwright-iterate/tests/test_main_repair_hooks.py` | AC-4/AC-5 drift protection: both hooks present, reference linked. |

### Modify

| Path | Change |
|---|---|
| `.github/workflows/ci.yml` | per-commit concurrency group on `main` + `cancel-in-progress` off there; the repair-PR safety gate step |
| `.github/workflows/security.yml` | same concurrency fix — identical bug |
| `.github/workflows/bloat-check.yml` | `push: branches: [main]`; guarded base-ref resolution |
| `plugins/shipwright-iterate/skills/iterate/SKILL.md` | §B1a hook + Phase-Index link to `main-repair.md` |
| `plugins/shipwright-iterate/skills/iterate/references/F11.md` | pre-arm hook |
| `.shipwright/planning/01-adopted/spec.md` | MINT `FR-01.19` |
| `docs/hooks-and-pipeline.md` | context-loading matrix: what an iterate now reads at start |
| `docs/guide.md` | Ch. 8 quality gates — one paragraph |

---

## 2. The data model, stated before the code

### 2.1 Which runs count — the monitored-run predicate

A run contributes to `main` health **only** if all four hold:

1. its `workflowName` is one of the monitored workflows (table below);
2. `event == "push"`;
3. `headBranch == <default branch>`;
4. it is the newest attempt for its `(workflow, headSha)` pair (newest
   `createdAt`, ties broken by the larger `databaseId`).

Rules 2 and 3 are the load-bearing ones: the same commit SHA carries **both** a
PR run and a push-to-`main` run, and without the predicate a green PR run
silently masks a red `main` run — which would invalidate the entire "P green,
C red" guarantee this iterate exists to establish.

### 2.2 Monitored workflows — an explicit in-code policy, and only ONE decides health

| Workflow file | `workflowName` | Class | Decides health? | Meaning |
|---|---|---|---|---|
| `ci.yml` | `CI` | `overlap` | **yes** | lint + every test suite. A red here is what an agent is good at fixing. |
| `security.yml` | `Security Scan` | `finding` | no | a red is a **finding**, not an overlap → never an auto-fix |
| `codeql.yml` | `CodeQL` | `finding` | no | same |
| `bloat-check.yml` | `Bloat Check` | `finding` | no | a size crossing that only appears when two PRs combine is a design signal; "fixing" it by editing the baseline is the anti-pattern AC-6 forbids |

**Only the `overlap` class decides `green`/`red`.** This is a correction from
review round 2, and it is not a convenience: if a slow or long-red
finding-class workflow could define `main`'s health, then every iterate would
find `main` red for a reason it must not fix, and would file a card that
GitHub's own findings→triage producer already files. The finding-class
workflows are **reported** — their state rides in `findings[]`, which is
exactly the visibility AC-2 asks for — without turning a security finding into
a repair trigger.

A workflow named in the policy but absent from the repository's workflow files
is reported in `unknown[]` by name rather than silently dropped, and an
invariant test cross-checks the policy against the real YAML in **both**
directions (§5).

### 2.3 Per-commit verdict

Conclusions map: `success` / `skipped` / `neutral` → **pass**; `failure` /
`timed_out` / `startup_failure` / `action_required` → **fail**; `cancelled` →
**inconclusive** (exactly what AC-1 stops producing); still `queued` /
`in_progress` → **running**.

| Verdict | When (over the health-deciding workflows only) |
|---|---|
| `green` | every health-deciding workflow passed |
| `red` | any health-deciding workflow failed |
| `running` | none failed, at least one still running |
| `incomplete` | none failed or running, at least one has no conclusive run |

`status` (the headline) is the verdict of the `origin/main` tip, with
`incomplete` reported as `unknown` and a named reason. **`unknown` is never
`green`** — that is the one rule the whole tool is worthless without.

**The result is an observation, not a lock.** `origin/main` can advance between
the fetch and the answer. The JSON therefore carries `tip_sha` and `observed_at`,
and if the run list contains a push-to-`main` run for a SHA that is not in the
local commit series, that is itself proof the branch moved: `unknown[]` gains
`main_advanced_during_check` and the caller is told to re-run rather than act on
a stale green. This costs no extra API call.

### 2.4 Attribution and the retrieval window

Walk the first-parent commit series newest→oldest over a stated commit
`window` (default 25). The run retrieval limit is **derived, not guessed**:
`run_limit = window × (number of monitored workflows) × 2`, so it cannot fall
short of the window by construction — a fixed `100` against 25 commits × 4
workflows would have silently truncated and made ordinary commits look
`incomplete`. Both numbers, plus `runs_fetched` and `saturated`
(`runs_fetched == run_limit`), are echoed in the output; a walk that needs a
commit older than the oldest retrieved run reports
`history_window_exhausted` instead of attributing inside a partial set.

- `latest_red_commit` — the newest `red` commit.
- `last_green_commit` — the newest `green` commit older than it.
- `first_bad_commit` — the **oldest** `red` commit after that green anchor.
  ("Which commit broke `main`" is the first red after the last green; the
  newest red is a different fact, so both are reported.)
- `confidence`:
  - `exact` — a green anchor exists and every commit between it and
    `first_bad_commit` has a conclusive verdict;
  - `uncertain` — a green anchor exists but there are `incomplete` /
    `running` / cancelled commits in between; each is listed in `gaps`;
  - `none` — no green anchor inside the window →
    `reason_code: "no_green_anchor_in_window"`, and the window is reported so
    the caller can widen it rather than guess.

### 2.5 Candidate partners — the changes the bad commit was never tested against

1. Resolve the PR for `first_bad_commit` via the commit→PR association
   (`gh api repos/{owner}/{repo}/commits/{sha}/pulls`), preferring the PR whose
   `merge_commit_sha` equals the commit. Fall back to a `(#NNN)` in the commit
   subject only if the association returns nothing.
2. `base_sha` = that PR's `base.sha` — the base its checks actually ran against.
3. Partners = `git rev-list --first-parent <base_sha>..<first_bad_commit>^`.
4. Refuse to invent: no association → `null` +
   `reason_code: "pr_association_unavailable"`; a direct push → `"direct_push"`;
   `base_sha` not an ancestor of the commit's parent (rebase / force-push) →
   `"base_not_ancestor"`.

### 2.6 The claim (AC-7) — ONE declaration, used by both consumers

The repair PR **is** the claim, and a repair declares itself in exactly **one**
machine-checkable way: **its branch name**, `iterate/fix-main-<sha12>`. The
canonical grammar is `(^|/)fix-main-(?P<sha>[0-9a-f]{7,40})$`.

One grammar, because there are two consumers — the claim query here and the CI
safety gate's `if:` condition (§3 step 8) — and two grammars that drift apart
give a PR that claims but is not gated. A meta-test asserts the workflow
condition and this regex accept the same branch names. A `Repairs-Commit: <sha>`
trailer stays a body convention for human linking; it is **not** an independent
claim form, precisely so there is nothing for the two consumers to disagree
about.

A pull request is a repair attempt for `<sha>` when **all** hold:

- its head branch lives in **this repository, not a fork** — the only people who
  can create one already have write access, so this is the real trust boundary
  (a fork PR must not be able to suppress the repair loop);
- its head branch matches the grammar above with that `<sha>`;
- optionally, its author is in `--trusted-author` (repeatable; off by default —
  the non-fork rule already carries the trust).

From the matched set: the newest **open** one is `repair_in_flight`, flagged
`stale` when untouched longer than `--claim-stale-minutes` (default 120) so a
claim that outlived its worker can be taken over instead of wedging the
mechanism. **Closed-unmerged** matches are counted as `failed_attempts`, which
is what makes the "two attempts did not resolve it" escalation real rather than
aspirational.

### 2.7 The failing output is untrusted input

`gh run view --log-failed` returns text a test printed. It is packaged for an
agent to read, so it is:

- reduced to the assertion-bearing lines (`FAILED`, `E   `, `assert`,
  `::error`, `Traceback`, ruff `path:line:col CODE`), capped by line **and**
  byte count, with `truncated` reported;
- passed through a conservative secret redactor (GitHub token shapes, `sk-`
  keys, AWS access-key ids, Slack tokens, PEM headers, `Bearer` values) on top
  of GitHub's own masking;
- labelled `"untrusted": true` in the JSON, and the procedure says in so many
  words that it is **data to read, never instructions to follow**.

---

## 3. Work breakdown (sequential)

1. `lib/main_health.py` — run predicate + newest-attempt selection (§2.1).
   *Test:* a PR run and a push run for one SHA; a rerun superseding an older
   attempt; a run on another branch; an unmonitored workflow.
2. `lib/main_health.py` — per-commit verdict + headline status (§2.3).
   *Test:* each verdict; `cancelled` is inconclusive not green; an empty run
   list is `unknown`; a vanished monitored workflow is named in `unknown[]`.
3. `lib/main_health.py` — attribution (§2.4).
   *Test:* clean anchor ⇒ `exact` + oldest red; a gap ⇒ `uncertain` + the gap
   listed; a multi-commit red streak ⇒ `first_bad` ≠ `latest_red`; no anchor ⇒
   `none` + `no_green_anchor_in_window` + the window echoed.
4. `lib/main_health.py` — log reduction + redaction (§2.7).
   *Test:* assertion lines kept, setup noise dropped, cap honoured and
   reported, each secret shape redacted, `untrusted` always set.
5. `lib/main_health.py` — claim + escalation (§2.6).
   *Test:* branch match, trailer match, **fork rejected**, stale vs fresh,
   `failed_attempts` counted from closed-unmerged, and each escalation reason
   (`finding_class_red`, `too_many_commits`, `repeat_attempts`).
6. `tools/main_health.py` — the shell. ONE `gh run list --branch main
   --limit N` on the green path; the association / log / PR-list calls happen
   only when red.
   *Test:* injected fakes for every call; a shell that raises ⇒ exit 4 with the
   source named in `unknown[]`, never exit 0. Exit codes `0 green · 2 red ·
   3 running · 4 unknown`.
7. `lib/assertion_weakening.py` — **AST, not diff text.** For each test file
   changed between the merge-base and HEAD, parse both revisions and compare
   at three levels — **module** (`pytestmark`), **class** (`Test*` decorators),
   and **function/method** (each test addressed by its qualified name, so a
   method inside a class is a first-class subject).
   **Blocks:** a test's assertion count dropped · a test function, method, class
   or file removed · `skip` / `skipif` / `xfail` newly applied at any of the
   three levels · the *after* revision does not parse · a changed test file that
   is **not** Python, which this detector cannot read and therefore refuses
   rather than waving through (`unsupported_test_file`).
   **Reports without blocking:** an assertion's *expression* changed — because
   *updating a pinned count another PR legitimately changed* is the single most
   common honest repair, and a rule that blocked it would block the very thing
   this iterate exists for. The PR must say why the new value is the truth.
   **Fences:** files added in this diff are exempt (nothing to weaken);
   non-test files are never examined (a production `assert` is not a test
   assertion).
   **Stated limit, not hidden:** a relaxation that keeps the assertion count and
   shape (`== 5` → `== 4`) is *reported*, not blocked. The tool is a
   conservative floor on unambiguous coverage loss; the governing norm — never
   adjust a test until it is green — stays a rule the agent is held to, and the
   docstring says so instead of implying completeness.
   *Test:* one per blocking class (including module- and class-level marks and
   the non-Python refusal), one per report class, one per fence.
8. `tools/check_repair_safety.py` **and its CI wiring** — a gating step inside
   the existing required `CI` job, conditional on the one repair-branch grammar
   (§2.6), running against the **merge-base** diff. A tool an agent is merely
   told to run is prose with a shebang; this makes it refuse.
   **The gate runs from the BASE revision, never from the PR's own checkout.**
   The step materialises `check_repair_safety.py` and `lib/assertion_weakening.py`
   out of `github.event.pull_request.base.sha` into a temporary tree and runs
   *that* against the PR's working tree. Otherwise a repair PR that edits the
   checker is judged by the checker it just edited — which is not an enforcement
   boundary at all, and would fail exactly when it matters most (an agent
   "fixing" a red run by touching the thing that reported it).
   *Test:* a workflow-invariant test asserting the step exists, is conditional on
   the shared grammar, carries no `continue-on-error`, and sources its
   implementation from the base SHA rather than the checked-out tree.
9. Workflows (AC-1 concurrency, AC-2 trigger + guarded base) and their
   invariant test.
10. Skill prose (AC-4, AC-5) and the drift test.
11. Spec row (FR-01.19), `docs/hooks-and-pipeline.md`, `docs/guide.md`.

---

## 4. Component hierarchy / data model changes

n/a — no UI. No new persisted artifact: the claim is deliberately an existing
GitHub object rather than a file, because a file-based claim outlives its worker,
which is the exact failure AC-7 names.

---

## 5. Test strategy

- **Unit (the bulk):** every pure function, from fixtures shaped like real
  `gh`/`git` payloads.
- **Integration:** `tools/main_health.py` end-to-end with injected shells —
  the exit-code contract, and that any failing shell degrades to `unknown`.
- **Empirical probes (not unit tests):** drive the REAL `gh run list`,
  `gh run view --log-failed`, `gh api …/commits/{sha}/pulls`, `gh pr list` and
  `git rev-list` against this repository and confirm the field names and shapes
  the fixtures assume. A payload reader tested only against fixtures its own
  author invented proves nothing about the producer.
- **Workflow invariants:** parsed YAML, not string matching. Two directions,
  per the skill's registry-driven-SSoT rule: every workflow named in the
  monitored-workflow policy resolves to a real `.github/workflows/*.yml` whose
  `name:` matches and which triggers on `push` to `main` without a path filter;
  and every workflow that *does* trigger on push-to-`main` is either in the
  policy or explicitly listed as deliberately unmonitored. A policy that drifts
  from the YAML would make ordinary commits look permanently `incomplete`.
- **Grammar agreement:** one test feeds the same branch names to the Python
  claim regex and to the workflow's `if:` condition and asserts they accept the
  same set — the two consumers of §2.6 cannot drift apart silently.
- **F0.5 surface:** `cli` — the real tool against the real repo, stdout + exit
  code captured as evidence.

---

## 6. Alternative approach considered — and why rejected

**Alternative: a scheduled `main-health.yml` that runs the detector and opens
the repair PR itself.**

Rejected:

1. **It needs a credential that can push to protected `main`** — and it would be
   the *second* consumer of exactly the token whose reach is still unverified
   (the same open question that blocks PROMPT 2). Two dependencies on one
   unproven credential is how one assumption becomes two red workflows.
2. **The fixer is the agent, not the workflow.** A cron can detect and file; it
   cannot read two commits and reconcile a registry entry. It would file a card
   every time — the escalation path, not the design.
3. **The two hooks cost nothing and fire exactly when it matters.** An iterate
   starting off `origin/main` is *already* about to build on that base; F11 is
   *already* about to merge onto it. One API call, no new credential, no new
   workflow.

The scheduled run stays the honest gap — "nobody is iterating and `main` is
red". It is parked deliberately, and this plan keeps it a three-liner by putting
the whole decision inside `main_health.py` instead of the skill prose.

---

## 7. External plan review round 1 — findings and dispositions

Both reviewers returned `revise`. Every finding and what was done:

| # | Reviewer / severity | Finding | Disposition |
|---|---|---|---|
| 1 | openai / high | A green PR run can mask a red push-to-`main` run for the same SHA — the central guarantee is unsound without a run predicate | **Accepted.** §2.1: `event == push` **and** `headBranch == main`, newest attempt only. Fixtures for the masking case. |
| 2 | openai / high | "Monitored" and "scanner-class" are policy inputs that live nowhere | **Accepted.** §2.2 is an explicit in-code table; a vanished workflow becomes a named `unknown`, not a silent omission. |
| 3 | openai / high | Candidate-partner algorithm underspecified (how the PR number is resolved, squash/rebase, fallbacks) | **Accepted.** §2.5: commit→PR association API first, `(#NNN)` only as fallback, and three named refusal codes instead of invented candidates. |
| 4 | openai / medium | AC-3 says "newest red", step 2 said "oldest red" — different commits | **Accepted.** §2.4 fixes the definition (first red after the last green) and reports `latest_red_commit` too. AC-3 reworded. |
| 5 | openai / high | The history window can be exhausted; attributing inside a partial window is worse than refusing | **Accepted.** Window is a parameter, echoed in the output, and exhaustion is `no_green_anchor_in_window`. |
| 6 | openai / high | `check_repair_safety.py` is not enforcement unless a required check runs it | **Accepted — the sharpest finding.** Step 8: a gating step inside the existing required `CI` job, conditional on the repair-branch convention, over the merge-base diff. Scope stated honestly: it governs PRs that declare themselves repairs. |
| 7 | openai / medium | The textual detector is too narrow to be called a hard rule | **Accepted, and the claim is narrowed.** AST comparison replaces text; blocking classes are the unambiguous coverage losses; a changed assertion *expression* is reported, not blocked, because updating a legitimately-changed pinned count is the commonest honest repair. The limits are written into the tool's own docstring. |
| 8 | openai / medium | `github.event.before` can be zero / unresolvable | **Accepted.** Guarded resolution: empty, all-zero or unresolvable ⇒ an explicit "baseline unavailable" notice + empty baseline, never a diff against an invalid rev. |
| 9 | openai+gemini / medium+low | Anyone can forge a claim with a branch name or a copied trailer | **Accepted.** §2.6: non-fork head branch is required — write access is the real trust boundary. Optional `--trusted-author` narrowing on top. |
| 10 | openai / medium | `repeat_attempts` has no data source | **Accepted.** §2.6 counts closed-unmerged matches from a `--state all` query. |
| 11 | openai / medium | Failed CI logs are untrusted content handed to an agent | **Accepted.** §2.7: redaction, caps, and an explicit `untrusted: true` in the schema and the procedure. |
| 12 | openai / medium | `running` / `none` / `unknown` per workflow need distinct semantics | **Accepted.** §2.3 defines the conclusion mapping and the four verdicts; green requires *all* monitored workflows conclusive-pass. |
| 13 | gemini / high | Parsing `==` → `>=` out of a unified diff is a tar pit | **Accepted.** Pivoted to `ast`. |
| 14 | gemini / medium | `gh run list` must be scoped to the branch or main runs fall off the window | **Accepted.** `--branch main --limit N`, with N echoed in the output. |
| 15 | gemini / medium | `cancel-in-progress: false` with a per-ref group **queues** main runs serially | **Accepted — and it would have hurt.** The group becomes per-**commit** on `main` (`github.sha`) and stays per-ref elsewhere, so every merge is verified *in parallel* rather than behind a queue. |
| 16 | gemini / medium | No green anchor in the window needs an explicit fallback | **Accepted** — same as #5. |
| 17 | gemini / low | Claim injection via a draft PR | **Accepted** — same as #9. |

## 8. External plan review round 2 — findings and dispositions

Round 2 on the revised plan. OpenAI returned `revise`; Gemini's reply was cut
off before its verdict token, so its leg is recorded `unavailable` — its
findings are still read and answered below, and its lead finding was identical
to OpenAI's.

| # | Reviewer / severity | Finding | Disposition |
|---|---|---|---|
| 18 | openai+gemini / high | The arithmetic does not close: 40 commits × 4 monitored workflows ≥ 160 runs, but the retrieval limit was 100 — ordinary commits would look `incomplete` and attribution could run on a partial set | **Accepted, twice over.** §2.4: the run limit is now *derived* from the window rather than fixed, and `runs_fetched` / `saturated` / `history_window_exhausted` are reported. §2.2 also shrinks the demand at the source: only the `overlap` class decides health, so a green anchor needs `CI` alone. |
| 19 | openai / high | The safety gate executes the checker **from the PR's own checkout** — a repair PR that edits the checker is judged by its own edit, so the enforcement boundary is not one | **Accepted — the sharpest finding of round 2.** §3 step 8: the step materialises the checker and its library from `pull_request.base.sha` and runs that against the PR tree, with a workflow-invariant test pinning the property. |
| 20 | openai / medium | If a monitored workflow does not actually run on `main` for every commit (path filters, disabled, renamed), every commit is permanently `incomplete` | **Accepted, and the design changed rather than being patched.** Only `CI` decides health (§2.2); the rest are reported. Plus a two-direction invariant test cross-checking the policy against the real YAML (§5). |
| 21 | openai / medium | The AST rule misses class-level and module-level `skip`/`xfail`, test methods inside classes, and says nothing about non-Python test files | **Accepted.** §3 step 7 now compares at module, class and function level, addresses methods by qualified name, and **refuses** a changed non-Python test file rather than waving it through. |
| 22 | openai / medium | The check is race-prone: `origin/main` can advance after the worktree is cut or after the one `gh` call, so a green answer may describe a stale tip | **Accepted.** §2.3: `tip_sha` + `observed_at` are in the payload; a push-to-`main` run for a SHA absent from the local series raises `main_advanced_during_check` at no extra API cost; and the output says in words that it is an observation, not a lock. |
| 23 | openai / medium | The claim grammar and the CI gate condition are two policy implementations that can drift | **Accepted.** §2.6 collapses to ONE declaration — the branch name — with the trailer demoted to a human-linking convention, plus a meta-test asserting both consumers accept the same set. |
| 24 | openai / low | Regex redaction must not be presented as complete secret control | **Accepted.** The docstring and the procedure both call it defense-in-depth on top of GitHub's masking, alongside the caps and the `untrusted` flag; the package is not published as a broadly-visible artifact. |

## 9. External plan review round 3 — findings and dispositions

Round 3 findings are implementation-level rather than design-level, which is
where a plan review stops paying. All six are accepted and built into the code;
the loop closes at the **code** review (Step 8 cascade + `external_review.py
--mode code` on the real diff), not with a fourth plan round. Gemini's leg
returned an unparseable fragment with no verdict and is recorded `unavailable`.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 25 | high | The failing **step** cannot be read reliably out of log text | **Accepted.** The red path fetches structured job data (`gh run view <id> --json jobs`) and takes the failed job/step names from there; the log is only the reduced untrusted excerpt. Logs unavailable ⇒ the steps are still named, with `excerpt: null` + a reason. |
| 26 | high | `window × workflows × 2` is not a *proof* of coverage — reruns on a recent commit can crowd older commits out of a saturated response | **Accepted.** Saturation is treated as incomplete evidence: if the response filled the limit **and** the walk needs a commit older than the oldest retrieved run, the answer is `run_history_truncated` with `confidence: none`, never an attribution inside a partial set. |
| 27 | high | A query-only claim is not atomic — two agents can both find no claim and both open a repair | **Accepted, and the claim operation changed.** The atomic claim is **pushing the branch** `iterate/fix-main-<sha12>` *before* the repair work: a second agent's push of the same new branch is rejected by the remote, which is the lock. `main_health` therefore looks for the **ref** as well as the PR, and requires the branch's short SHA to be a real prefix of the attributed commit rather than any matching prefix. Stale takeover is defined explicitly in the procedure. |
| 28 | medium | Saying finding-class reds are "reported, not escalated" contradicts AC-6 | **Accepted — the earlier wording overcorrected.** A finding-class red now sets `escalate.required` with reason `finding_class_red` and an `escalation_key` (`main-red:<workflow>:<sha12>`) that makes card-filing idempotent. The procedure hands security-scanner reds to the existing GitHub-findings→triage producer (linking, not double-filing) and files the card itself for the rest. |
| 29 | medium | The base-revision gate depends on unstated CI facts | **Accepted.** The step is specified end to end: `ci.yml` already checks out with `fetch-depth: 0`, the base SHA is read from the event payload, both base-revision source files are written into an isolated temp package, the tool is invoked by explicit path, and **any** failure to obtain or run the base implementation fails the step closed. |
| 30 | medium | Deleted and renamed test files are not covered by "each test file changed" | **Accepted.** Discovery is driven by `git diff --name-status --find-renames <merge-base>...HEAD`: deletions are read from the base tree, additions are exempt, and a rename **preserves identity** (before = the old path in base, after = the new path) so a rename is not mistaken for a deletion. |

## 10. External CODE review — two rounds on the real diff

The internal Step-8 cascade was started twice and lost twice to the session
process being terminated mid-run. On the operator's instruction it was replaced
by **two independent rounds** of `external_review.py --mode code` against the
257 KB source diff, so that a single sampling could not quietly miss something.
That was the right call: round 2 found three defects round 1 did not.

Eleven findings; **seven fixed in-diff**, four answered. The three that mattered
most were all cases of *the tests agreeing with the code because both were
wrong* — which is exactly what an independent reader is for.

| # | Round / severity | Finding | Disposition |
|---|---|---|---|
| 31 | r1+r2 / high | `main_advanced_during_check` was DETECTED, reported — and the status stayed `green`, so every caller keyed on the exit code acted on data already known to be stale | **Fixed.** `_LOAD_BEARING_UNKNOWNS` forces `status = "unknown"`. Reporting a problem is not the same as answering honestly. New test. |
| 32 | r1+r2 / high | A red finding-class workflow never escalated: CI green ⇒ exit 0 ⇒ both hooks continue ⇒ nobody ever reads `escalate.required`. AC-6 unmet. Plus an idempotency key `main-red:Security Scan:` with an EMPTY sha | **Fixed.** New status `escalate` + exit code 5, wired into both hooks and the procedure; the key falls back to `tip_sha`, since finding workflows are evaluated on the tip. Two new tests. |
| 33 | r1+r2 / high | **The claim was not a lock.** Both racers hold the same `HEAD` (the claim is made *before* any work), push the same object, and git answers the second "Everything up-to-date" with exit 0 | **Fixed.** The claim is now GitHub's create-ref call, which fails *422 Reference already exists* whatever the target sha. |
| 34 | r1 / high | **The atomicity test validated a sequence the procedure never produces** — it committed before pushing, so rejection came from divergent history | **Fixed, and inverted.** The test now *falsifies* the push mechanism (two same-SHA pushes, both succeed) so the reason for choosing create-ref cannot silently outlive itself. The host-side 422 is `untestable` (`requires-external-nondeterministic-service`) rather than faked with a mock that would only assert what it was told. |
| 35 | r1 / medium | A green tip with an older red still produced an attribution and entered the whole red path — a resolved failure presented as active, and the one-call green budget broken | **Fixed.** Attribution requires the *tip* to be red/incomplete/running. Two tests, including the counter-case (a red under a still-running tip IS attributed). |
| 36 | r2 / high | At the F11 hook `HEAD` is this iterate's own finished branch, so the "small repair PR" would have carried all the unrelated work — and merged it as part of the repair | **Fixed.** The claim is created from `origin/<default>` and the repair happens in its own worktree. Drift test added. |
| 37 | r2 / high | A branch-only claim could never go stale (`stale: False`, no timestamp available), and a branch left behind by a *closed* repair read as a live claim forever — wedging that commit | **Fixed.** Branch-only claims report `stale: None` (genuinely unknown) and `True` once their pull requests are closed; the procedure now deletes the ref, not just the PR. Two tests. |
| 38 | r2 / medium | Renaming `tests/test_x.py` to a non-test path bypassed the gate — `analyze_file` judged only the destination | **Fixed.** A rename out of test collection blocks (`test_removed_by_rename`). Test added. |
| 39 | r1 / — | Gemini's leg returned an unparseable reasoning fragment in both rounds | **Noted.** Recorded `unavailable`; OpenAI answered fully in both rounds and its findings are dispositioned above. |
| 40 | r2 / — | "Add a concurrent same-commit test" | **Done** — see #34. |
| 41 | r1 / — | "`actions/checkout` checks out the merge commit on `pull_request`" | **Answered, no change.** That is why the gate diffs against `merge-base` rather than against the checked-out `HEAD`; the base revision it *executes* comes from `pull_request.base.sha`, which is immutable. |
