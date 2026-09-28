# Iterate Spec: hooks-uv-run-project-pin

- **Run ID:** iterate-2026-09-28-hooks-uv-run-project-pin
- **Type:** bug
- **Complexity:** medium (self-escalated from the Stage-1 `small` keyword
  estimate — the diff is known in advance to touch `hooks.json` across every
  plugin, which is the `cross_component` trigger path
  (`classify_complexity.CROSS_COMPONENT_FILE_PATTERNS` — "Claude-Code hooks +
  hook fan-out"). That flag forces a `medium` classification floor and a
  mandatory integration-coverage test once the diff exists, so escalating up
  front avoids restarting the run after Stage 2 would have caught it anyway.)
- **Status:** draft

## Goal

Every Shipwright plugin's `hooks.json` invokes its hook scripts as plain `uv
run "<script>"`, with no `--no-project`. `uv run` resolves which project to
sync by walking up from the session's **current working directory** — not
from the hook script's own path. When a Claude Code session's CWD is itself
an unrelated `uv`-managed Python project, every hook silently binds to and
attempts to sync/reinstall *that* project instead of running standalone —
at minimum wasted work (verifying dozens of unrelated packages on every
single hook firing), at worst a hard failure when the sync step needs to
write to that project's venv and a running process has a file open there
(confirmed live: Windows `os error 32`, "The process cannot access the file
because it is being used by another process", trying to reinstall an
editable console-script `.exe`).

Fix: pin every `hooks.json` `uv run` invocation with `--no-project`, so hook
execution never attempts to *discover, resolve or sync* whatever
uv-managed project happens to be the session's CWD — matching a pattern
already proven and shipped for 5 of the ~41 hook scripts in this repo
(`suggest_iterate.py`, `codex_activation_mint.py`,
`codex_pretooluse_gate.py`, `check_rtm_coverage.py`,
`check_security_scan.py`).

**Known residual (Internal Plan Review finding, disclosed not fixed):**
`--no-project` eliminates project discovery/sync — the actual cause of the
`os error 32` crash and of the wasted per-hook dependency verification —
but `uv` still honors an ambient `.venv` (or `VIRTUAL_ENV`) found in or
above the CWD, and a `.python-version`/`uv.toml` there. A CWD whose ambient
venv has a broken or pre-3.11 interpreter could still misbehave a hook,
just not via the sync-and-lock failure this iterate fixes. Pinning
`--python 3.11` everywhere to close that residual too was considered and
rejected — see Out of Scope.

## Acceptance Criteria

- [ ] Every `"command": "uv run ..."` entry in every plugin's `hooks.json`
      (both `plugins/shipwright-iterate/hooks/hooks.json` and its
      `hooks-codex/hooks.json` sibling) includes `--no-project` immediately
      after `uv run`.
- [ ] The two entries that also need a third-party package
      (`audit_compliance_on_stop.py`, which imports `yaml`) combine both:
      `uv run --no-project --with pyyaml "..."`.
- [ ] A meta-test statically parses every `hooks.json` in the repo and fails
      if any `"command"` field starting with `uv run` is missing
      `--no-project` — so a future hook added without the flag is caught by
      CI, not discovered live again.
- [ ] An integration test proves the *mechanism*, not just the syntax: it
      invokes a real representative hook script via `uv run --no-project
      "<script>"` from a temp CWD containing its own poisoned/impossible
      `pyproject.toml` (an unsatisfiable dependency), and asserts the call
      still succeeds — proving `--no-project` genuinely skips project
      discovery/resolution rather than merely "usually not hitting it". A
      paired negative case (same poisoned CWD, `uv run` WITHOUT
      `--no-project`) asserts that variant fails, so the test would have
      caught the original bug.
- [ ] `docs/hooks-and-pipeline.md` documents the `--no-project` convention
      for every hook's `uv run` invocation, per this repo's own rule that a
      `hooks.json` change must update that doc in the same diff.

## Spec Impact

- **Classification:** none
- **NONE justification:** this is an operational/invocation-mechanics fix to
  how hook scripts are launched (a `uv run` flag), not a change to any
  product-facing functional requirement — no FR describes *how* `uv run` is
  invoked, only that hooks fire and enforce their gates, which is unchanged.

## Out of Scope

- codextender's own repo (its `npm install --upgrade` path already degrades
  gracefully when the upgrade check fails and a prior install exists —
  verified by reading `npm/bin/codextender.mjs`, no fix needed there).
- **Correction (Internal Plan Review finding — the original claim here was
  wrong):** native `codex` CLI ("Codex Light") sessions are NOT immune.
  `codex_hooks_sync.py` (R1b) reads each plugin's bundled `hooks.json`
  commands verbatim — unchanged string, including whatever `uv run` flags
  it carries — and writes them into per-hook launcher scripts under the
  global, trust-independent `~/.codex/hooks.json`. A Codex session that has
  run that sync *is* driving the exact same `uv run` command string this
  iterate fixes. What's actually true, and what makes no separate code
  change necessary here: the fix reaches Codex sessions the same way it
  reaches Claude Code sessions — through the existing rebuild-and-resync
  step (`build_codex_plugin.py` + `codex_hooks_sync.py`), the Codex
  counterpart to `update-marketplace.sh` for the Claude-Code plugin cache.
  This machine's `~/.codex/hooks.json` currently holds no Shipwright
  wiring only because that sync hasn't been run here — not because the
  mechanism doesn't exist. Out of scope for *this* iterate is only
  performing that resync as part of this PR (it is a per-machine,
  per-operator step, not a repo change) — flagged in the F12 summary.
- Adding `--python <version>` pinning to every hook invocation. `--no-project`
  alone already eliminates the actual bug (project discovery/sync); adding a
  Python-version pin everywhere would be a second, independent change bundled
  into an unrelated fix — out of scope per the Surgical Changes principle.
  The 5 already-shipped `--no-project` hooks in this repo don't pin a Python
  version either, so this keeps the fix consistent with existing precedent.

## Design Notes

n/a — no UI, no design surface touched.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `plugins/*/hooks/hooks.json`, `plugins/shipwright-iterate/hooks-codex/hooks.json` (this repo, hand-edited) | Claude Code's own hook runner (parses each `"command"` string and executes it via the shell) | JSON hook-command strings |

`touches_io_boundary` fires because `hooks.json` is an explicit anchored
trigger path in the risk taxonomy. The "boundary" here is the hook-command
string itself (producer: this repo's `hooks.json` files; consumer: Claude
Code's hook runner, an external, unmodifiable component) — the Boundary
Probe for this iterate is the integration test above: it proves the
produced command string, run exactly as Claude Code's hook runner would run
it, behaves correctly against a real adversarial CWD.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** The fix is correct and the flag choice is sound (`--no-project`
  over `--isolated`/`--project`), but the spec overstated the isolation
  (a CWD `.venv`/`.python-version` is still honored) and wrongly scoped out
  Codex, whose sync mirrors these exact command strings and hard-fails the
  bundle merge on a prefix mismatch.
- **Findings:**
  1. (medium, architecture) `--no-project` doesn't fully decouple from CWD
     (ambient `.venv`/`.python-version` still honored) — **disclose**, spec's
     Goal section corrected to an accurate claim, residual documented.
  2. (medium, completeness) Codex out-of-scope claim was stale —
     `codex_hooks_sync.py` mirrors these exact commands into
     `~/.codex/hooks.json` — **fix**: spec's Out of Scope section rewritten
     with the correct mechanism and rebuild/resync path.
  3. (medium, architecture) `codex_hook_merge.py` hard-fails on a
     cross-plugin flag-prefix mismatch for the same script — **fix**:
     verified no mismatch exists post-fix (`audit_compliance_on_stop.py`'s
     `--with pyyaml` ordering is identical in both callers) and added
     `test_shared_uv_run_scripts_use_identical_flag_prefix_across_plugins`
     to `test_hooks_uv_run_pinned.py` to catch future drift mechanically.
  4. (medium, completeness) Regression scope too narrow (missed
     `shared/scripts/tools/tests` codex-hook suites + several plugin test
     roots that parse hook command strings) — **fix**: ran all named suites;
     found and fixed one real regression in
     `plugins/shipwright-build/tests/test_review_payload_hook_wiring_integration.py`
     (its command parser assumed no flags before the quoted script path).
  5. (medium, completeness) Integration test hygiene — env not scrubbed,
     network-dependent poison, no failure-reason assertion — **fix**:
     rewrote with `VIRTUAL_ENV`/`UV_*` stripped, an offline-deterministic
     `file://` poison, and a stderr content assertion on the negative case.
  6. (low, completeness) Spec/plan disagreed on "real representative" vs
     "trivial" script for the integration test — **fix**: test now derives
     its command from the actual shipped hooks.json entry rather than a
     hand-written approximation.
  7. (low, completeness) Meta-test could vacuously pass on an empty glob —
     **fix**: added a minimum-file-count assertion.
  8. (low, architecture) Mini-plan's rejected-alternative rationale claimed
     plugins have no `pyproject.toml` — factually wrong — **fix**: rationale
     corrected in the mini-plan.
  9. (low, completeness) Hook-authoring convention docs
     (`shared/prompts/writing-plugin.md`) don't mention `--no-project` —
     **fix**: updated alongside `docs/hooks-and-pipeline.md`.
- **Known limitations:** none beyond the disclosed `.venv`/`.python-version`
  residual (finding 1).
- **Status:** 8 fixed, 1 disclosed

## External LLM Review (plan)
- **glm:** approve. Low-severity refinements only: broaden the meta-test's
  `uv run` match to not assume a prefix position (already true — my regex is
  not anchored to string-start, so this finding's premise doesn't apply, no
  action needed); resolve `uv`/check its version explicitly in the
  integration test rather than assuming presence (**declined** — every other
  subprocess-integration test in this repo shells to `uv` unconditionally;
  adding a special-case guard here would diverge from repo convention, not
  blocking); add concrete per-machine resync commands to the docs
  (**fixed** — added to `docs/hooks-and-pipeline.md`); note the stderr
  assertion is already broad/stable, not an exact message (already true, no
  action needed); a one-line comment in `run_if_cache_ready.py` noting the
  isolation-chain dependency (**declined** — that file is templated and
  duplicated across 12 plugins + 1 template source; touching all 13 for a
  documentation-only nicety on a "verified non-issue" finding is scope creep
  outside the Surgical Changes principle).
- **openai:** revise. Findings: the mini-plan's own work-breakdown/test-
  strategy text had fallen behind what the spec's Confidence Calibration
  already described as built (offline-deterministic poison, command derived
  from a real hooks.json entry, the broader regression scope including the
  `shipwright-build` test fix) — **fixed**, mini-plan §2 rewritten to match
  the actual implementation; the static test's glob doesn't recursively
  discover hooks.json files outside the established `plugins/*/hooks*/`
  layout — **declined**: verified via a repo-wide `find` that no
  `hooks.json` exists outside that layout today, the `_MIN_EXPECTED_FILES`
  assertion already fails loudly if the glob stops matching real files, and
  a recursive repo-wide glob risks matching an unrelated test fixture
  someday named `hooks.json` under a `tests/` directory — the documented,
  CLAUDE.md-canonical plugin structure is the right scope boundary.
- **Verdicts:** glm=approve, openai=revise (no contradiction — within one
  step). No high-severity finding on either pass, so no STOP was required;
  all findings triaged above.

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-09-28-hooks-uv-run-project-pin/architecture_brief.md`
- **Verdicts:** glm=approve · openai=approve
- **Smallest thing that would do (per reviewers):** as proposed — a flag
  added to existing command strings plus the static meta-test; both
  reviewers explicitly endorsed deferring `--python` pinning rather than
  bundling it.
- **Findings:** none from either reviewer.
- **Reconciliation:** n/a — both reviewers confirmed the plan as-is; the
  mini-plan's rejected `--project`/`--isolated` alternatives were not
  revisited.

## Self-Review

```
Self-Review:
  1. Spec Compliance:    [pass] All 13 hooks.json files pinned with
     --no-project (AC-1/2), meta-test + integration test added (AC-3/4),
     docs updated (AC-5). No extra features added — --python pinning
     considered and explicitly declined as out of scope.
  2. Error Handling:     [n/a] No new system boundary — the change is a
     flag string in an existing command; nothing new to fail. The tests
     themselves handle subprocess failures via explicit exit-code/stderr
     assertions rather than letting them propagate uncaught.
  3. Security Basics:    [pass] No user input, no SQL, no HTML, no secrets
     touched. Hook commands remain quoted exactly as before.
  4. Test Quality:       [pass] Meta-test asserts the actual command-string
     outcome (not internal state); integration test has both a positive
     and a negative-control case (the negative case is the "always fails
     without the fix" proof — could not pass vacuously).
  5. Performance Basics: [n/a] No DB, no list endpoints; the fix REDUCES
     work per hook (skips a project sync it never needed).
  6. Naming & Structure: [pass] New test files follow existing
     shared/tests/test_hooks_*.py naming and style (mirrors
     test_hooks_json_quoting.py's structure). All files under 300 LOC.
  7. Affected Boundaries:[pass] Producer (hooks.json command strings) /
     consumer (Claude Code's + Codex's hook runners) identified in
     "Affected Boundaries" above. Round-trip probe: the integration test
     IS the round-trip test — it derives the real command from a shipped
     hooks.json entry and drives it through a real subprocess exactly as
     the consumer would, both for the fixed and unfixed shape.
     touches_io_boundary fired → round-trip test is present, not skipped.
  8. Test Hygiene Probe: [pass] `scan_test_hygiene.py --diff` → no findings.

Action: All clear, proceed to commit.
```

- **Boundaries touched:** the `hooks.json` `"command"` string → Claude
  Code's hook runner (see Affected Boundaries above).
- **Empirical probes run:**
  1. Live repro of the original failure reviewed directly (two screenshots
     from the operator's real session: SessionStart hook errors across
     every plugin, then Stop hook errors across every plugin citing
     `os error 32` on `codextender.exe`).
  2. `uv run -v` (verbose) from inside `C:\01_Development\codextender`
     (a real `uv`-managed project with its own `uv.lock`) confirmed `uv
     run <hook script>` resolves and verifies codextender's entire
     dependency tree (`litellm` + ~60 packages) on every invocation,
     including checking the editable `codextender==0.1.0` install itself —
     work that is completely unnecessary for a stdlib-only hook script.
  3. `uv run --no-project -v` from the same CWD confirmed project
     discovery is skipped entirely ("No project found; searching for
     Python interpreter" — no dependency resolution log lines at all).
  4. `uv run --isolated` (without `--no-project`) was tested and rejected
     as an alternative fix: it still discovers and resolves the host
     project's *own* dependencies (installed 50+ packages including
     `litellm`) into a throwaway venv — slow and still coupled to whatever
     host project happens to be CWD; `--no-project` is the correct flag,
     `--isolated` is not.
  5. AST-based audit (not regex — avoids docstring false positives) of
     every hook script's **top-level** imports, across all ~41 scripts
     referenced from every `hooks.json` in the repo, found exactly one
     genuine third-party (PyPI) dependency at that layer: `pyyaml`, in
     `audit_compliance_on_stop.py` — already handled via the existing
     `--with pyyaml` flag, confirmed compatible with `--no-project` by a
     direct live call (`uv run --no-project --with pyyaml
     audit_compliance_on_stop.py`, exit 0). **Corrected by Doubt Review
     (below): this probe only followed top-level imports and missed
     dependencies pulled in by lazy imports further down a
     `sys.executable`-propagated subprocess chain** — `jsonschema`
     (Group D manifest validation, reached from `audit_compliance_on_stop.py`
     itself) and `yaml` again (via `check_required_checks_hook.py` →
     `check_required_checks.py` → `lib.required_checks_drift`, reached from
     `run_if_cache_ready.py`'s SessionStart fan-out). Both are now supplied
     explicitly via `--with`, per the Doubt Review section below — the
     "no other hook script needs a third-party package" claim was false for
     the *child-process* dependency surface, though still true for each
     script's own top-level imports.
  6. `run_if_cache_ready.py`'s downstream fan-out (`subprocess.run([sys.executable,
     str(target)], ...)`) was read and confirmed to propagate whatever
     interpreter the top-level `uv run` resolved to each chained script —
     so the fix only needs to touch the top-level `hooks.json` command,
     never the forwarding logic itself.

- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | Every `hooks.json` `uv run` command includes `--no-project` | tested | `test_hooks_uv_run_pinned.py::test_every_uv_run_hook_command_has_no_project` PASSED |
  | 2 | The `--with pyyaml` hook command also carries `--no-project` | tested | same test, asserted per-command (not a separate row — one parametrized assertion covers both flags on the same command string) |
  | 3 | A representative hook script invoked via `uv run --no-project` from a CWD with an unsatisfiable host `pyproject.toml` still succeeds | tested | `test_hooks_uv_run_project_isolation.py::test_no_project_ignores_poisoned_cwd` PASSED |
  | 4 | The same invocation WITHOUT `--no-project` fails against that poisoned CWD (negative control proving the test would have caught the original bug) | tested | `test_hooks_uv_run_project_isolation.py::test_without_no_project_is_poisoned_by_cwd` PASSED |
  | 5 | The Windows file-lock race itself (a running process holding a console-script `.exe` open while `uv` attempts to resync a *different*, unrelated host project) | untestable | `requires-external-nondeterministic-service` — reproducing this specific OS-level timing race deterministically in CI would require spawning a real long-running subprocess and racing a real `uv` resync against it; the mechanism it depends on (`uv` resolving/syncing the *host CWD project* at all) is what tests #3/#4 prove is now structurally impossible, which is the actual fix — the race can no longer occur because there is no more sync attempt to race |
  | 6 | Existing repo tooling that parses/hardcodes the pre-fix `uv run "<script>"` command shape must still recognize the post-fix shape | tested | Found via `code-reviewer` (Stage 2): `shared/tests/test_ensure_shared_cache_vendored.py::_is_cache_guarded` assumed `tokens[:3] == [uv, run, guard]`, broke on the new `--no-project` token at index 2. Fixed (shifted to `tokens[:4]`, updated 2 synthetic-command tests, added a regression-guard negative case), plus the earlier-caught `plugins/shipwright-build/tests/test_review_payload_hook_wiring_integration.py` regression (row already implied by the mini-plan's work breakdown §6). Both files re-run green. |
  | 7 | The nested, hooks.json-invisible `uv run` in `cleanup-review-scratch-on-code-reviewer-failure.py` (spawned from `cwd=resolve_project_root()`) is also pinned | tested | Found via `doubt-reviewer` (Stage 3, reversibility lens). Fixed: added `--no-project`; `test_cleanup_review_scratch_on_code_reviewer_failure.py`'s `args[:2]==["uv","run"]` assertion widened to `args[:3]==["uv","run","--no-project"]`. 15/15 passed. |
  | 8 | `--with pyyaml`/`--with jsonschema` additions keep every `run_if_cache_ready.py`/`audit_compliance_on_stop.py` invocation's flag prefix identical across all plugins that share the target script (codex bundle-merge dedup requirement) | tested | `test_hooks_uv_run_pinned.py::test_shared_uv_run_scripts_use_identical_flag_prefix_across_plugins` PASSED post-fix; `shared/scripts/tools/tests` (codex_hook_merge/inventory/sync, 1171 tests) re-run green. |
  | 9 | `run_if_cache_ready.py`/`audit_compliance_on_stop.py` retain the *specific* `--with pyyaml`/`--with jsonschema` packages (not just *a* consistent prefix) | tested | Found via the required CI PR-review gate (Tier-3, `openai/gpt-6-luna`, run 36427748135): rows #6/#8 check prefix shape/consistency only, never flag content, so dropping `--with pyyaml --with jsonschema` from every plugin uniformly would pass both. Added `test_hooks_uv_run_pinned.py::test_dependency_carrying_scripts_retain_required_with_flags`. |

- **Confidence-pattern check:** asymptote — this is the first "are you
  confident?" pass on this change, no prior finding to chase. Coverage —
  every ledger row is `tested` or `untestable` with a valid reason_code; 0
  untested-testable. Integration composition (`cross_component`): test #3/#4
  above is the required `category:"integration"` behavior — it proves the
  `--no-project` flag on a real `hooks.json`-shaped command genuinely
  isolates hook execution from a real, adversarial host project, not just
  that the flag is present in the file.

## Doubt Review (doubt-reviewer, Stage 3)
- **Raw payload:** `.shipwright/planning/iterate/iterate-2026-09-28-hooks-uv-run-project-pin/doubt_review_reply.json`
- **Disposition detail:** `.shipwright/planning/iterate/iterate-2026-09-28-hooks-uv-run-project-pin/doubt_review_disposition.json`
- **Verdict:** all 4 doubts addressed (1 high, 2 medium, 1 low) — see `doubt_review_disposition.json`
- **High (hidden-coupling, confirmed real and live-reproduced):** `--no-project`
  removes the ambient CWD-project dependency resolution that `run_if_cache_ready.py`
  → `check_required_checks_hook.py` → `check_required_checks.py` (via
  `lib.required_checks_drift`'s module-level `import yaml`) used to receive for
  free whenever the session's CWD happened to have the Shipwright repo's own
  `.venv` synced. Live-confirmed: `uv run --no-project python -c "import yaml"`
  succeeds in this worktree (ambient `.venv` present) but fails with
  `ModuleNotFoundError` in a fresh directory with no ambient venv — which is the
  normal case for any *end-user* target project running the shipwright-iterate
  plugin, not just a corner case internal to this monorepo. The producer's own
  fail-open design (`check_required_checks_hook.py::run()` always returns 0)
  keeps this from crashing a session, but it silently stops the required-checks
  drift feature from ever recording success. **Fixed:** `--with pyyaml --with
  jsonschema` added to the `run_if_cache_ready.py` SessionStart prefix in all 12
  plugins' `hooks.json` (uniform, because `codex_hook_merge.py` dedups this
  shared script by its pre-rewrite relative path across plugins and hard-fails
  `BundleCollisionError` on a prefix mismatch — confirmed by reading
  `codex_hook_inventory.build_hook_inventory`'s `rel_key`/`prefix_shape` keying).
- **Medium (hidden-coupling):** the same ambient-resolution loss silently
  downgrades Group D traceability checks (`_group_d_manifest.py::_schema_valid`,
  fail-closed on a missing `jsonschema`) from evaluated to SKIP inside
  `audit_compliance_on_stop.py`, which already carried `--with pyyaml` pre-diff
  but never `--with jsonschema`. **Fixed:** `--with jsonschema` added alongside
  the existing `--with pyyaml` on both callers (`shipwright-changelog`,
  `shipwright-iterate`).
- **Medium (reversibility):** `plugins/shipwright-build/scripts/hooks/
  cleanup-review-scratch-on-code-reviewer-failure.py:232` spawns its own nested
  `uv run` (not read from any `hooks.json`, so invisible to the static
  meta-tests) with `cwd=resolve_project_root()` — the exact same bug class this
  whole iterate exists to fix, reproducing the original CWD-project-resync
  exposure inside a hook the meta-tests cannot see. **Fixed:** added
  `--no-project` (the target script, `review_scratch.py`, is confirmed
  first-party/stdlib-only); widened the existing test's argv-shape assertion.
- **Low (boundary-contract):** `test_hooks_uv_run_pinned.py`'s `_UV_RUN_PREFIX`
  regex only matches a `uv run` invocation immediately followed by a
  double-quoted argument, so an unquoted command would silently produce no
  offender. **Fixed:** widened `test_hooks_json_quoting.py`'s glob from
  `plugins/*/hooks/hooks.json` to `plugins/*/hooks*/hooks.json` (matching the
  pinned-test's own glob), so ADR-022's ${CLAUDE_PLUGIN_ROOT} quoting
  requirement now also covers `shipwright-iterate`'s `hooks-codex` sibling —
  the one file this repo actually has that the narrower glob missed — which
  closes the gap by construction rather than by a shlex-tokenizer rewrite.
- **Corrected claim:** Confidence Calibration probe #5 above originally
  concluded "exactly one third-party dependency... no other hook script needs
  a third-party package" from an AST audit of top-level imports only. That
  audit never followed the `sys.executable`-propagated subprocess chain, so
  the claim was false for the child-process dependency surface (see probe #5's
  inline correction above). The claim remains true for each script's own
  top-level imports.
- **Full re-verification post-fix:** `shared/tests` (11968+ tests) and
  `shared/scripts/tools/tests` (1171 tests, includes codex_hook_merge/
  inventory/sync) both green; targeted re-runs of
  `test_hooks_uv_run_pinned.py`, `test_hooks_json_quoting.py`,
  `test_hooks_uv_run_project_isolation.py`, and the `shipwright-build` plugin's
  `test_cleanup_review_scratch_on_code_reviewer_failure.py` /
  `test_review_payload_hook_wiring_integration.py` all green.
- **Second regression, self-caught on the full-suite re-run (not by a
  reviewer):** the `--with pyyaml --with jsonschema` tokens added to fix the
  High doubt (above) shifted `run_if_cache_ready.py`'s position in the
  `run_if_cache_ready` command string, which broke
  `test_ensure_shared_cache_vendored.py::_is_cache_guarded`'s **second** time
  (it was already fixed once, for `--no-project` alone, by `code-reviewer` —
  Test Completeness Ledger row 6). Fixed by making `_is_cache_guarded` locate
  the guard script by content (`tokens.index(_GUARD_PLACEHOLDER)`) rather than
  a fixed token offset, so it tolerates any number of leading `--with <pkg>`
  pairs between `--no-project` and the guard while still rejecting a
  malformed/odd `--with` prefix or a dropped `--no-project`. Added two new
  assertions covering both. 13/13 in that file + its reverse-direction
  sibling green; full `shared/tests` re-run green (13 tests were the sole
  failure on the first full re-run; this row records that finding + fix).

## Post-push CI findings (F11, two rounds)

- **Round 1 — required "Python (lint + test)" CI job failed, local suite had
  passed.** `test_hooks_uv_run_project_isolation.py::test_without_no_project_is_poisoned_by_cwd`
  (Test Completeness Ledger row 4) is a platform-dependent negative control:
  the "poisoned" CWD project declared an unresolvable `file:///this/path/...`
  dependency, which `uv` 0.11.9 fails to parse/resolve on Windows (confirmed
  locally: "Failed to parse metadata from built wheel... relative path
  without a working directory") but apparently resolves/parses without
  erroring on Linux CI (GitHub Actions run 36423886194: `uv run` without
  `--no-project` exited 0 against the same poisoned project) — so the
  negative control wasn't discriminating on every platform CI runs on.
  **Fixed:** switched the poison to `requires-python = "==99.99.99"` — no
  interpreter anywhere can ever satisfy an exact, absurd version pin, so the
  failure is deterministic offline and platform-independent by construction,
  not dependent on any OS's `file://` URI parsing. Verified locally:
  `--no-project` still bypasses it (exit 0), the unpinned invocation still
  fails (exit 2, "No interpreter found for Python 99.99.99...").
- **Round 2 — required "PR Review" Tier-3 gate (`openai/gpt-6-luna`) BLOCKed**
  (run 36427748135): "the new tests do not verify the explicit
  `pyyaml`/`jsonschema` dependencies added to preserve downstream hook
  behavior, so removing those dependencies everywhere could silently regress
  required-checks or Group D validation while the suite still passes" —
  ledger row 9 above. Fixing it surfaced a second, unrelated latent bug in
  the SAME test file: `test_shared_uv_run_scripts_use_identical_flag_prefix_across_plugins`'s
  helper `_target_script` had always returned `None` for every real command
  (the shared `_UV_RUN_PREFIX` regex consumed the opening `"` as part of its
  own match instead of stopping before it, so `_target_script`'s own
  `re.match(r'"...', rest)` never found a leading quote to anchor on) — so
  that "cross-plugin consistency" test had been vacuously green since it was
  authored: an always-empty per-script map can never disagree with itself.
  Only surfaced now because the new content-assertion test reuses the same
  helper and asserts the scripts are actually *seen*, not just that no
  offender was reported. **Fixed:** `_UV_RUN_PREFIX` changed to a lookahead
  for the closing quote (`(?=")`) instead of consuming it, so `match.end()`
  lands exactly on the quote `_target_script` expects. Re-verified: all 15
  tests in the file pass, including the cross-plugin consistency test now
  doing real (non-vacuous) comparisons.
