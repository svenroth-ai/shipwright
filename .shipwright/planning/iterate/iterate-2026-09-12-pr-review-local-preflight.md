---
run_id: iterate-2026-09-12-pr-review-local-preflight
status: implemented
type: change
complexity: medium
---

# Iterate: local PR-review preflight (`pr_review.py --base`/`--diff-file`)

## Origin

Operator-authored analysis, 2026-09-12: all three PRs blocked that day
(#725, #729, #742) were blocked by the required Tier-3 `PR Review` gate, not
by a test or lint. That gate reviews against a threat model ("what could
this do that nobody planned?"), a different question from the spec-
compliance cascade (`spec-reviewer`/`code-reviewer`/`doubt-reviewer`) that
already runs before every push — so a green cascade carries no information
about the CI verdict, and each finding cost a full push → CI → review round
to learn. The structural blocker: `pr_review.py` required `--pr-number`/
`--repo` and fetched the diff via `gh pr diff`, so it could not see a branch
that had not been pushed and opened as a PR.

## Spec Impact: NONE

No target-app FR in `shipwright_sync_config.json` names any file this diff
touches — this is shipwright's own delivery tooling (framework, not a
target app), so `change_type` is the no-FR branch. `affected_frs: []`.

## What changed

- **`plugins/shipwright-security/scripts/lib/pr_review_local.py`** (new) —
  the local-preflight diff source + no-side-effect verdict reporting:
  `build_local_diff` (private-temporary-index merge-base diff, the same
  technique F0's diff-coverage gate uses — includes untracked, excludes
  ignored, never touches the real index/HEAD), `read_diff_file`,
  `resolve_diff_mode` (CI vs. local argument validation), `post_local_result`
  (prints instead of posting).
- **`plugins/shipwright-security/scripts/tools/pr_review.py`** — `--pr-number`/
  `--repo` are now optional; new `--base <ref>` / `--diff-file <path>` /
  `--project-root` flags select local-preflight mode (mutually exclusive
  with CI mode). Local mode skips `read_reviewed_head`, `_post_verdict`, and
  `dismiss_own_stale_verdicts` entirely — same prompts/model/generated-file
  filter, same decision→exit mapping, zero side effects.
- **`plugins/shipwright-iterate/skills/iterate/references/F11.md`** — new
  step, run right before the branch is pushed: `pr_review.py --base
  <default>` against the still-unpushed branch. Exit 1 (BLOCK) STOPs the
  run; exit 2 (no key, transport failure) is advisory-only — logged,
  surfaced in F12, never blocking, because a preflight's own unavailability
  must never become a substitute gate's outage.
- **`docs/hooks-and-pipeline.md`**, **`docs/guide.md`** — documented the new
  step alongside the existing `verify_local.py` CI-gate-mirror pattern it
  follows.

## Confidence Calibration

- **Boundaries touched:** the `pr_review.py` CLI surface (new flags, same
  exit-code contract), the F11 finalization skill flow (new step, no schema
  change to `reviews.json`), Git plumbing (private temp index — read-only
  by construction).
- **Empirical probes run:**
  - Ran the new `--base origin/main` mode live against this very branch's
    diff, with a real `OPENROUTER_API_KEY` and `gh` available. It correctly
    built the merge-base diff, excluded a generated file, called
    `openai/gpt-5.6-luna` (the CI default model) with the same prompts, and
    returned `BLOCK` — flagging that the diff touches a sensitive skill file
    (`F11.md`) and asking for explicit maintainer confirmation before merge.
    Operator confirmed the design in-session (2026-09-12) — not recorded
    into `reviews.json` or any file `review_record_tier.decide()` reads,
    per the preflight-never-a-waiver contract.
  - Verified `build_local_diff` never mutates the real index/working tree
    (`git status --porcelain` identical before/after) and correctly (a)
    includes an untracked file, (b) excludes a commit that landed on the
    base ref AFTER the branch point — both via a real synthetic git repo,
    not mocks.
- **Test Completeness Ledger:**

  | Behavior | Status | Evidence |
  |---|---|---|
  | `resolve_diff_mode`: CI mode valid, local via `--base`/`--diff-file` valid, and the four invalid combinations | tested | `test_pr_review_local_diff.py::TestResolveDiffMode` (7 tests) |
  | `list_diff_paths`: extracts every header in order, empty diff -> empty list | tested | `...::TestListDiffPaths` (2 tests) |
  | `read_diff_file`: decodes valid UTF-8, replaces invalid bytes rather than raising | tested | `...::TestReadDiffFile` (2 tests) |
  | `build_local_diff`: includes branch commit + untracked, excludes unrelated base-only commit; never mutates real index/HEAD; disables ext-diff/textconv; unresolvable base returns an error, does not raise | tested | `...::TestBuildLocalDiff` (4 tests) |
  | `main()` local mode: approve → exit 0 / block → exit 1, no CI-only boundary called; prints banner+review, never posts; `--base` end-to-end; empty diff fails closed; truncated diff still prints (regression) | tested | `test_pr_review_local_preflight.py::TestLocalPreflightOrchestration` (7 tests) |
  | `resolve_diff_mode` usage errors exit `EXIT_USAGE` (3), never `EXIT_ERROR` (2) | tested | `...::test_pr_number_and_base_combined_exits_usage_not_error`, `...::test_no_mode_at_all_exits_usage` |
  | A genuine argparse-level failure (not `resolve_diff_mode`'s) also exits `EXIT_USAGE`, not the 2 argparse itself would otherwise raise | tested | `...::test_argparse_level_usage_error_also_exits_usage_not_2` (code review, 2026-09-12 — this was a real, previously-untested gap) |
  | `--help` still exits 0 through the new SystemExit remap | tested | `...::test_help_flag_still_exits_0` |
  | `post_local_result` strips control/escape chars from `body` before printing to a real terminal | tested | `...::test_local_result_strips_control_chars_from_printed_body` (code review, 2026-09-12) |
  | Empty/`.` `--diff-file` value is not a valid local source (`Path("")` is truthy) | tested | `test_pr_review_local_diff.py::test_empty_diff_file_path_is_not_a_valid_source` (external review, 2026-09-12) |
  | `--base` mode's `main()` call sends the actual merge-base diff content, not just "a" diff | tested | `...::test_base_mode_reviews_the_merge_base_diff` (strengthened — external review, 2026-09-12) |
  | Unresolvable `--base` / unreadable `--diff-file` exit `EXIT_USAGE`, never `EXIT_ERROR` | tested | `test_pr_review_local_preflight.py::test_unresolvable_base_exits_usage_not_error`, `...::test_unreadable_diff_file_exits_usage_not_error` (external review, 2026-09-12) |
  | CI mode regression (pre-existing suite, unmodified behavior) | tested | `plugins/shipwright-security/tests/test_pr_review_*.py` |
  | Live end-to-end against a real branch, real key, real `gh` | tested | manual probe above (Empirical probes run) |

  30/30 new tests across three files (16 `test_pr_review_local_diff.py` + 14
  `test_pr_review_local_preflight.py`, `_pr_review_local_fixtures.py` shared
  builders) — verified by `grep -c` against the actual files, not carried
  forward from an earlier draft (external review, 2026-09-12, caught the
  prior count as stale). 0 untestable rows; 0 testable-but-untested.
  `pr_review.py` split a second time (289 → 343 → 295 → 300 lines) by
  extracting `handle_empty_diff`/
  `handle_truncated_diff` into `pr_review_verdict.py`, which already exists
  for exactly this purpose (code review, 2026-09-12).
- **Confidence-pattern check:** asymptote — the real-repo live probe and the
  synthetic-git-repo tests each independently prove the merge-base/untracked/
  no-mutation claims that mocks alone would only assert, not demonstrate.
  Coverage — every new public function in `pr_review_local.py` and every new
  `main()` branch (empty-diff, truncated, normal decision, argparse
  validation) has a dedicated test. No `cross_component` file pattern is
  touched (F11.md/pr_review.py are not in `CROSS_COMPONENT_FILE_PATTERNS`),
  so Integration Coverage does not apply.

## Internal Plan Review (opus-plan-reviewer)

**Verdict: approve.** Two low-severity, non-blocking findings, both addressed:

- **Architecture (low):** `{security_plugin_root}` (F11.md) was a new
  template variable with only an inline gloss, unlike its sibling
  `{build_plugin_root}` which is defined once in `context-loading.md`. Fixed:
  added the same one-line definition there.
- **Security (low, already mitigated):** `build_local_diff`'s `git add -A`
  step runs clean/filter drivers (unlike the diff step, which disables
  `--no-ext-diff`/`--no-textconv`) — a malicious `.gitattributes` filter
  could run a local command during that add. No behavior change: this is
  the caller's own already-trusted working tree (F11 runs it after F6 has
  committed), so the actual attack surface is unchanged from an ordinary
  `git add`. Documented with a one-line docstring note.

Reviewer independently confirmed the 18/18 Test Completeness Ledger and the
`EXIT_USAGE`/`EXIT_ERROR` F11.md wiring against `pr_review_lib.py`'s exit-code
contract.

## Code Review (internal code-reviewer, Stage 2)

**Verdict: revise**, on a diff that already carried two external-review
rounds and one internal plan review. Three medium findings, all real and
fixed:

1. **`EXIT_USAGE` didn't cover argparse's own parse failures** — only
   `resolve_diff_mode`'s semantic validation returned it; a genuinely
   malformed invocation (bad `--timeout` value, unrecognized flag) still hit
   argparse's `error()`, which exits 2 directly — exactly the "reviewer
   infra unavailable, advisory-only" code F11 must never apply to a wiring
   bug. Fixed: `parser.parse_args` wrapped in `try/except SystemExit`,
   remapping any non-zero exit to `EXIT_USAGE` (exit 0 / `--help` untouched).
2. **`--diff-file` sends arbitrary local file content to the model with no
   warning** — flagged by the earlier external plan review too (see below)
   but never actually addressed; the spec's "Dismissed with reasoning" list
   answered a different point (diff-source scrutiny asymmetry). Fixed: a
   one-line warning in the `--diff-file` help text and the
   `pr_review_local` module docstring.
3. **`post_local_result`'s `print(body)` skips sanitization** — `summary` is
   the one field `render_comment` does not control-character-strip (inert in
   a Markdown PR comment; live in a real terminal, which local mode writes
   to). Fixed: `strip_display_unsafe` (already used elsewhere in this same
   module family) applied before the print.

Two low findings: a doc-only ledger mislabeling (fixed above) and a missing
inline comment on `meta_repo`/`meta_pr_number` (fixed). Fixing finding 1
grew `pr_review.py` back over the 300-LOC guideline; resolved by finishing
the split into `pr_review_verdict.py` (see Test Completeness Ledger) and
splitting the test file the same way `_pr_review_fixtures.py` already does
for the stale-verdict tests.

## External Code Review (`external_review.py --mode code`)

**Verdict: revise** (GLM + OpenAI agree). A first run against this diff came
back `reject` from both providers, reporting the diff contained only
`.shipwright/triage.jsonl` — every real file was missing. Root cause: the
diff had been built and read via bash-argument paths under bare `/tmp/...`,
which resolves to a different directory for a bash-native tool (its own
mount table) than for a Python/native-Windows process (drive-root-relative),
and MSYS's automatic path conversion applies only when such a path is its
own command-line argument, not when embedded inside a `python -c` script
string — so the diff-build script and the `external_review.py` invocation
silently disagreed about which file "the diff" was. Fixed for this run by
writing and passing the diff through the session's own unambiguous
scratchpad path; re-run against the correct diff, both providers converged
on real findings:

- **Local diff-acquisition failures read as advisory (medium, both
  providers independently found this)** — an unresolvable `--base` or an
  unreadable `--diff-file` returned `EXIT_ERROR`, not `EXIT_USAGE`; F11's
  exit-2-is-advisory rule would have silently skipped the preflight over a
  local configuration problem, the same failure class `EXIT_USAGE` was
  created for but hadn't yet covered at the diff-acquisition layer (only
  argument-shape and argparse-level failures were fixed by that point).
  Fixed: both paths now return `EXIT_USAGE`; CI's `fetch_pr_diff` failure
  stays `EXIT_ERROR`.
- **F11.md's default-branch fallback silently produced `origin/` (medium,
  GLM)** — `git symbolic-ref ... | sed ... || echo main`: a pipe's exit
  status is the LAST command's, so a failed `symbolic-ref` (empty stdout)
  still has `sed` exit 0, and `|| echo main` never fires. Fixed: capture the
  ref into a variable first, default the *value* (`${default_branch:-main}`),
  not the pipe's exit status. Verified manually against both the normal and
  the simulated-failure case (old form produced literal `origin/`; new form
  correctly falls back to `origin/main`).
- Two low findings, both fixed: `--diff-file ""` was accepted as a valid
  local source (`Path("")` is truthy); `test_base_mode_reviews_the_merge_base_diff`
  only asserted exit 0, never that the sent diff actually contained the
  merge-base content.
- The ledger's own test count was stale (claimed 30, actual count at the
  time was 27) — GLM caught this too; fixed by counting from the files
  directly rather than carrying a number forward.

Dismissed with reasoning: OpenAI additionally flagged `post_local_result`'s
`summary_excerpt!r` stderr line as printing `summary` "directly" and unsafe.
Verified empirically — `repr()` already renders a control character as its
escaped textual form (`'\x1b[31m...'`, literal backslash-x-1-b, not a real
ESC byte), so no raw control byte reaches the terminal on that line; only
the `strip_display_unsafe(body)` line (already fixed, above) printed
anything unescaped. False positive, no change.

## Alternative approach considered — rejected

Narrow the required CI gate to Tier-3/external-contributor PRs only, so
internal PRs skip straight to merge once the spec-compliance cascade passes.
Rejected: that gate is the component that is *working* — it found three real
defects in one day. The fix is to run the same gate sooner, not to run it
less often; CI stays the sole authority for the required check.

## External review (Branch A)

**Iterate-mode call (plan vs. spec):** both reviewers returned `revise`.
Addressed: `EXIT_USAGE` split from `EXIT_ERROR` (a misconfigured invocation
could otherwise read as the advisory "reviewer unavailable" case), `--no-
textconv` added alongside the existing `--no-ext-diff`, a stderr line now
names every file section sent to the model before the call, and a real bug
the live probe then caught — the truncated-diff branch skipped
`post_local_result` in local mode, printing no banner or review body — is
fixed with a regression test. Dismissed with reasoning: base-ref staleness
(this step runs immediately after `ensure_current.py`'s own fetch, so the
merge base cannot be stale at this call site); diff-source asymmetry vs.
`gh pr diff` (fails toward MORE scrutiny, not less, and is now disclosed via
the same path-list line); duplicating `suite_worktree_diff`'s technique
instead of importing it (avoids coupling shipwright-security to shipwright-
iterate's F0 internals; cross-referenced in both docstrings); the F12
"surfaced" wording (matches the pre-existing, no-new-mechanism pattern
`main_health.py`'s own advisory notes already use).

**Architecture-mode call (should this exist at all):** GLM `approve`, OpenAI
`revise` — no contradiction requiring resolution (agree within one step).
Both independently suggested dropping `--diff-file` from the CLI surface
since F11 only ever calls `--base`. Kept, with reasoning: the operator's own
originating request named both `--base <ref>` and `--diff-file <path>`
explicitly; `--diff-file` has independent value beyond F11 (reviewing an
arbitrary diff — e.g. from a bug report — and a git-free, fully
deterministic test seam); both reviewers rated the point low severity and
one called it "not worth a revise on its own."

## Dogfooding run (F0.5 CLI surface)

Ran the finished tool against its own branch — `pr_review.py --base
origin/main --project-root . --prompt-dir shared/prompts/pr_reviewer` — as
the F0.5 CLI surface evidence for this run (no web/API surface exists for a
scripts-only change). `openai/gpt-5.6-luna` returned `block`: F11.md's shell
snippet only branches on `preflight_rc` 1/2/3 and silently falls through
(continues the run) for any other nonzero code — e.g. 127 if `uv` is missing
from PATH — which is indistinguishable from a clean pass. Real finding, not
covered by the earlier code/external-code review rounds (those exercised
`pr_review.py`'s own exit codes, not F11.md's shell branching over them).
Fixed with an explicit `elif [ "$preflight_rc" -ne 0 ]` STOP branch in
`F11.md`, mirrored in `docs/hooks-and-pipeline.md`'s F11 bullet. No new test
possible for this one (it is prose inside a runtime-prompt shell snippet, not
executable code) — caught only by actually running the finished tool
end-to-end, which is the point of doing this at F0.5 rather than treating the
CLI surface requirement as satisfied by unit tests alone.

## Second dogfooding run (F11, real preflight against the pushed diff)

Re-ran `pr_review.py --base origin/main` for real at F11 (after
`ensure_current.py` integrated 5 commits main had gained meanwhile).
`openai/gpt-5.6-luna` returned `block`: `build_local_diff`'s `git add -A` in
the private temporary index can execute a clean/filter driver a
`.gitattributes` declares, using whatever `[filter "<name>"]` command the
operator's own git config (local or global) already defines -- a real git
property, not specific to this code, but one the module's existing "acceptable
here, own already-trusted working tree" dismissal understated: `--base` is a
general CLI, and a maintainer checking out an unfamiliar contributor's branch
to review it before merge is exactly the scenario where an unrelated,
legitimately-configured personal filter (e.g. git-lfs) and that branch's
`.gitattributes` could combine. Verified empirically that neither this repo
nor any Shipwright-scaffolded template configures any `[filter ...]` clean/
smudge/process driver anywhere (`git config --get-regexp '^filter\.'` empty,
local and global; no `filter=` attribute in any tracked `.gitattributes`), so
the precondition does not exist here today -- but the CLI outlives this repo.
No `git` flag disables filter drivers for `add` without also losing
untracked-file coverage (constraint 5, a hard requirement), so this is
addressed as a documented, not eliminated, risk: `--base`'s help text and
`pr_review_local`'s module docstring now both say, explicitly, never to point
`--base` at a ref not already trusted as much as the caller's own working
tree. `pr_review.py` briefly crossed 300 lines adding the help-text warning;
trimmed back to exactly 300 by moving the full explanation into the module
docstring and keeping the CLI help to one line.

## Third dogfooding round (real required CI gate BLOCK, then a regression it caused)

The pushed PR's own required Tier-3 "PR Review" check (not the local preflight)
independently surfaced the SAME git-filter-driver risk the local dogfooding run
had found, and explicitly REJECTED the first (documentation-only) mitigation:
"documenting this risk does not prevent code execution when reviewing an
unfamiliar branch." It demanded a real fix — stage the worktree with an
isolated config/environment that disables filter drivers while still covering
untracked files — plus a regression test proving a configured filter does not
run.

First fix attempt: nulled `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` to
`os.devnull` for the staging subprocess. This did stop the filter from
executing, but caused a severe regression verified directly: `build_local_diff`
against `origin/main` returned 4675 files / 102MB instead of the correct ~27.
Root cause: this machine's `core.autocrlf=true` is set at the git SYSTEM config
layer (not global), so nulling `GIT_CONFIG_SYSTEM` silently disabled CRLF
normalization on the fresh `git add -A`, while `base_sha`'s tree held
normalized blobs — every text file in the repo then read as changed.

Corrected fix: stopped nulling config files at the environment level entirely.
Instead, query the MERGED effective git config (`git config --get-regexp
'^filter\..*\.(clean|smudge|process)$'`, unscoped — reads local+global+system
together) for every active filter-driver key, then blank each one via a `-c
<key>=` override on the `git add -A` call itself. `-c` outranks every config
layer, so no configured filter can run, and no other config value (like
`core.autocrlf`) is touched. Verified directly: `build_local_diff` against
`origin/main` now returns exactly 27 files / 220762 bytes, matching the known-
correct file list, and the new regression test
(`test_configured_clean_filter_driver_does_not_execute`) plus the full existing
suite (31 tests in the two local-preflight files, 1067 passed/7 skipped across
`plugins/shipwright-security/tests/`) all pass. Re-running the local preflight
against the corrected code no longer surfaces the filter-driver finding at
all — the only remaining finding is the reviewer's own sensitive-skill-path
BLOCK, a structural self-approval limitation for a solo maintainer/author (see
`feedback_solo_maintainer_admin_override_pattern` in project memory), not a
code defect. Admin-override approval to merge past that check was requested
and granted by the user.
