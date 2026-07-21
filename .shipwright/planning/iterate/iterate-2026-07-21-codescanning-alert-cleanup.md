# Iterate: Close the five open GitHub code-scanning alerts

- **Run-ID:** iterate-2026-07-21-codescanning-alert-cleanup
- **Type:** change
- **Complexity:** medium
- **Spec Impact:** NONE (behavior-preserving; no FR added, modified or removed)
- **Risk flags:** none

## Problem

`svenroth-ai/shipwright` carries five OPEN code-scanning alerts — three Semgrep
`medium` plus two CodeQL nits. They accumulated from the last week's merges
(#412 introduced the shared FR-table reader, #422 introduced the shallow-clone
meta-test, the corpus harness landed in #414/#415).

Open alerts are not free. Per the recorded posture, an unresolved
`github-advanced-security` review thread BLOCKS auto-merge on any PR that
inherits it even when every required check is green. Leaving five open is a
standing tax on every future iterate, and it trains the reader to skim the
Security tab — which is how a real finding eventually gets skimmed too.

| Alert | Rule | Site | Sev |
|---|---|---|---|
| 1260 | `semgrep …audit.non-literal-import` | `shared/scripts/lib/fr_table_reader.py:91` | medium |
| 1258 | `semgrep …dangerous-globals-use` | `integration-tests/requirements_corpus/_probe_runner.py:177` | medium |
| 1257 | `semgrep …audit.non-literal-import` | `integration-tests/requirements_corpus/_collect_realm.py:54` | medium |
| 1261 | `CodeQL py/implicit-string-concatenation-in-list` | `integration-tests/test_fr_table_shape_convergence.py:94` | warning |
| 1271 | `CodeQL py/catch-base-exception` | `integration-tests/test_fr_history_recovery_provenance.py:212` | note |

## Triage — all five are false positives

None is a reachable vulnerability. Every flagged "untrusted input" is a
first-party literal that never crosses a trust boundary. Evidence per alert:

**1260 / 1257 — non-literal import.** `fr_table_reader._sibling` is
module-private with exactly five call sites, all module-level literals
(`requirement_model`, `fr_fold_map`, `_fr_table_cells`, `_fr_table_row`,
`_fr_table_columns`) — verified by grep, no other caller exists.
`_collect_realm._load` imports `target["module"]`, and every `"module"` value is
a hardcoded literal in the in-repo `requirements_corpus/registry.py` target
table. Neither reads argv, env, network or file content for the module name.

**1258 — dangerous globals().** `globals()[f"probe_{args.probe}"]` is already
constrained by argparse `choices=sorted(PROBES)`: an attacker cannot reach an
arbitrary global because the parser rejects any name outside the catalog before
the lookup runs. Semgrep cannot see an argparse-level allowlist.

**1261 / 1271 — CodeQL nits.** No security dimension at all; both are
readability/precision flags on deliberate code.

## Decision — fix at the root where a root fix exists

Suppression is the last resort, not the first. Three of five have a genuine root
fix and get one; only the two where dynamic import IS the design get an inline
`# nosemgrep`.

The two suppressions need no `shipwright_accepted_risks.yaml` entry. That
register's drift gate reads `.trivyignore*` and the `SHIPWRIGHT_SEMGREP_*` env
vars in `security.yml` — not inline comments (confirmed: the pre-existing
suppression at `fr_table_reader.py:99` is unregistered and CI is green). An
inline marker on a proven-literal call is a false-positive annotation, not a
consciously accepted risk; conflating the two would dilute a register whose
value is that every row is a real accepted risk with an expiry.

No GitHub dismissals are used. All five close on their own at the next scan of
merged `main`, which leaves the repo's own history as the audit trail rather
than a click in a web UI.

## Acceptance criteria

- **AC1** — `_probe_runner.py` dispatches probes through an explicit
  name→function table; no `globals()` indexing remains. `--probe` still accepts
  exactly the same eight names.
- **AC2** — the probe table has BOTH directions of drift protection: every table
  entry resolves to the correspondingly-named function, and every module-level
  `probe_*` function has a table entry.
- **AC3** — `test_fr_table_shape_convergence.py` builds its `-c` program in a
  named constant; the `subprocess.run` argument list contains no implicitly
  concatenated strings. Behavior identical.
- **AC4** — `test_fr_history_recovery_provenance.py` catches `Skipped` by name
  instead of `BaseException`, still converting a reintroduced skip into a hard
  failure, and no longer swallowing `KeyboardInterrupt` / `SystemExit`.
- **AC5** — both `importlib.import_module` sites carry a `# nosemgrep:` bound by
  adjacency plus a rationale naming the closed source of module names, and the
  `fr_table_reader` claim is ENFORCED by `_ALLOWED_SIBLINGS` rather than only
  asserted in prose (added after external review).
- **AC6** — full suites stay green; `ruff` clean.
- **AC7** — the scanner itself confirms the fix BEFORE merge: a local Semgrep
  run with the two offending rules reports 0 findings repo-wide, down from 3
  (added after external review — verifying tests but never the scanner would
  have left a malformed directive or wrong rule ID undetected).

## Empirical probes

1. **Are the `_sibling` call sites really all literals?** `grep '_sibling('`
   across the repo → 6 hits: the definition plus five module-level literal
   calls. No dynamic caller. → FP confirmed, not assumed.
2. **Do the `PROBES` values do anything?** grep for `PROBES` → only
   `sorted(PROBES)` for argparse choices. The realm strings
   (`"t1": "shared_tools"`) are read by NOTHING; each probe hardcodes its own
   `_paths("…")`. → the dict was a name catalog with a decorative second column
   that could silently disagree with the real realm. Replacing it with the
   dispatch table deletes a latent lie rather than just moving a lookup.
3. **Is `t2` exercised?** grep `probe("…")` in the test modules → seven of eight
   names appear; `t2` is never called. So a mistyped `t2` row would be caught by
   NO existing test. → AC2's drift test is load-bearing, not ceremonial.
4. **Does CodeQL flag every `except BaseException`?** Two others exist
   (`atomic_write.py:56`, `shared_loader.py:70`) and are NOT flagged — both
   re-`raise`. → the rule targets *swallowing* handlers; the fix is to stop
   swallowing, and those two are correctly out of scope.
5. **Does hoisting the `-c` program actually clear 1261?**
   `test_requirements_corpus_registry.py:225` already builds a subprocess
   program by implicit concatenation into a *variable* and is NOT flagged — the
   rule is scoped to list/tuple literals. → precedent in-repo; the fix shape is
   proven, not guessed.
6. **Would a suppression trip the accepted-risk register?** Read
   `accepted_risks_cli.py`: it reconciles `.trivyignore*` and the
   `SHIPWRIGHT_SEMGREP_*` env vars. No `nosemgrep` scanning. The existing
   unregistered suppression at `fr_table_reader.py:99` is green in CI. → no
   register entry required.

## Mini-plan

1. `_probe_runner.py` — move the catalog below the probe functions and turn it
   into `PROBES: dict[str, Callable]` mapping each name to its function; replace
   `fn = globals()[f"probe_{args.probe}"]` with `fn = PROBES[args.probe]`.
   `choices=sorted(PROBES)` is unchanged. Drop the dead realm strings.
2. `test_requirements_corpus_registry.py` — add the bidirectional drift pair
   (AC2), mirroring the existing `TARGETS`/`REALMS` forward+reverse tests that
   already live in this module.
3. `test_fr_table_shape_convergence.py` — hoist the `-c` body into a
   module-level `_ADOPT_RENDER_PROG` constant; the arg list becomes four plain
   elements.
4. `test_fr_history_recovery_provenance.py` — `from _pytest.outcomes import
   Skipped`; `except (Skipped, Exception) as exc:`; drop the now-dead
   `# noqa: BLE001`; rewrite the two comment blocks so the prose describes what
   the code now does.
5. `fr_table_reader.py` + `_collect_realm.py` — add the adjacency-bound
   `# nosemgrep:` plus a one-line rationale.
6. Re-run the 80-test baseline + `ruff`.

### Alternative considered — dismiss all five on GitHub instead

Rejected. A dismissal is a click that lives in GitHub's database, not in the
repo: it does not survive a re-import, it is invisible in review, and it teaches
the next reader nothing about WHY the call is safe. Three of the five also have
a real root fix available, and the register's own header is explicit that it is
"NOT a place to silence a real, reachable finding. Prefer a root remediation
whenever one exists." Dismissing would additionally have left the `globals()`
dispatch and its decorative realm column in place — probe 2 showed that column
could silently disagree with the real realm, so the dismissal path would have
preserved a latent defect in order to save four lines of diff.

A narrower variant — root-fix the three, dismiss the two imports — was also
rejected: an inline comment at the call site is strictly more discoverable than
a GitHub dismissal, and `fr_table_reader.py:99` already establishes that pattern
one branch away from the alert.

### One adjacent fix, deliberately included

`test_fr_change_history_recovers_compacted_history.py` carried the SAME guard,
already narrowed to `Skipped` by PR #422 — but via `from _pytest.outcomes import
Skipped`, the private import both reviewers flagged. It is switched to
`pytest.skip.Exception` here too (3 lines).

Not scope creep by accident: this iterate adds a comment stating that reaching
into `_pytest` is wrong, and shipping that comment while leaving the sibling
file doing exactly that would be incoherent. The repo now has one form, and no
`_pytest` import anywhere. #422 also shows why alert 1271 existed at all — that
PR fixed this defect class in one of the two files and missed the other.

## Out of scope

- `atomic_write.py:56` / `shared_loader.py:70` `except BaseException` — they
  re-raise, CodeQL correctly does not flag them, changing them is churn.
- The `sweep-outbox invalid` warning emitted by `setup_iterate_worktree`
  (`trg-b1dda91d`, `trg-16d374e1` unplaceable). Pre-existing local-main drift,
  unrelated to this diff; fix is `git merge origin/main` in the main tree.
- Any change to `security.yml` scanner wiring or the accepted-risk register.

## Confidence Calibration

- **Boundaries touched:** none. No `.env*`, no `*_config.json`, no hook, no
  workflow. `fr_table_reader.py` receives comment lines only; the other three
  files are test-harness code. `touches_io_boundary` = false,
  `touches_ci_supplychain` = false, `cross_component` = false.
- **Empirical probes run:** six, listed above — each replaced an assumption with
  a grep or a read. Probes 2 and 3 changed the plan (they turned the dispatch
  rewrite from "cosmetic" into "deletes a decorative column" and proved the
  drift test is required, not optional).
- **Test Completeness Ledger:** below.
- **Confidence-pattern check:** *Asymptote (depth)* — the risky edit is the
  dispatch rewrite; its failure mode is a mistyped row silently dropping a
  probe, which probe 3 proved existing tests would NOT catch for `t2`. AC2's
  bidirectional test closes exactly that gap, so depth is at the gap rather
  than spread evenly. *Coverage (breadth)* — all five alert sites are edited and
  all five have either a behavioral test or a same-diff drift test.
  *Integration composition* — n/a, no `cross_component` machinery touched
  (recomputed from the diff, not asserted).

### Test Completeness Ledger

Revised after external review: rows 7 and 10 were originally filed `untestable`
and both claims were wrong. Row 7's `requires-interactive-tty` was a dodge (a
child process observes exit behavior without aborting the parent), and row 10's
`requires-external-nondeterministic-service` was false — the same Semgrep rules
run locally. Both are now tested.

| # | Behavior introduced / changed | Disposition | Evidence |
|---|---|---|---|
| 1 | Probe dispatch resolves each name to its function without `globals()` | `tested` | `test_requirements_corpus_false_verdicts` + `_found_defects` — 7 names driven end-to-end through the subprocess runner |
| 2 | Every dispatch row maps to the correspondingly-named function | `tested` | `test_every_probe_table_row_resolves_to_its_like_named_function` — **mutation-verified**: `"t1": probe_t2` makes it red |
| 3 | Every `probe_*` function is registered (incl. never-invoked `t2`) | `tested` | `test_every_probe_function_is_registered_in_the_table` |
| 4 | `--probe` accepts exactly the eight documented names | `tested` | `test_the_probe_cli_offers_exactly_the_documented_names` |
| 5 | Adopt-generator header assertion unchanged after hoisting `-c` | `tested` | `test_the_adopt_generator_emits_it` (pre-existing, green) |
| 6 | A reintroduced `pytest.skip` fails the shallow-clone meta-test hard | `tested` | **new** `test_fr_history_skip_guard` — runs the real meta-test in a child pytest with `pre_s6_sections` patched to skip, asserts `1 failed` and not `1 skipped`. The guard had never been exercised before this iterate |
| 7 | A non-`Skipped` exception now propagates instead of becoming `pytest.fail` | `untestable` | `covered-by-existing-test` — the AssertionError path is exercised by the meta-test itself and the `Skipped` path by row 6. What remains is the *absence* of a handler, i.e. Python's default propagation; there is no branch of mine left to exercise |
| 8 | `_ALLOWED_SIBLINGS` matches what is actually imported (no stale entry) | `tested` | `test_the_declared_sibling_allowlist_matches_what_is_actually_loaded`, all 4 load styles — **mutation-verified**: adding an unused `"os"` reddens all four |
| 9 | An undeclared sibling name is refused before reaching `import_module` | `tested` | `test_an_undeclared_sibling_name_is_refused_before_it_reaches_import`, all 4 load styles — **mutation-verified** |
| 10 | Semgrep reports none of 1257 / 1258 / 1260 | `tested` | `semgrep --config r/…non-literal-import --config r/…dangerous-globals-use` repo-wide: **3 findings before, 0 after**. Pre-merge and reproducible, not a post-merge observation |
| 11 | The `_sibling` guard breaks no consumer in any import realm | `tested` | shared 4728 · integration 416 · compliance 1295, all green |

0 testable-but-untested behaviors.

## External plan review (GPT-5.4 + Gemini 3.1 Pro, 2/2 succeeded, not degraded)

Five findings, all accepted:

1. **`_pytest.outcomes.Skipped` is a private API** (both reviewers) — switched to
   the supported `pytest.skip.Exception`. Verified equivalent
   (`pytest.skip.Exception is Skipped` → True). GPT further noted that the
   planned `(Skipped, Exception)` tuple would have changed handling of *other*
   pytest outcomes (`Failed`, `Exit` are also BaseException-derived), which was
   an unintended semantic shift. Catching `Skipped` alone avoids it entirely and
   matches the guard's actual purpose.
2. **Ledger row 7 was a false `untestable`** — now tested (row 6 above).
3. **The suppression sits on the implementation, not the call sites** — added
   `_ALLOWED_SIBLINGS`, so the safety claim is enforced rather than asserted in
   a comment, plus the bidirectional test that keeps the set from rotting.
   Verified the sibling claim's counterpart for `_collect_realm`: `TARGETS =
   DISCOVERY + PARSERS`, both static literal tuples, no disk/env/argv path.
4. **The ACs never verified the scanner** — added the local Semgrep run as the
   primary verification (row 10). This turned out to matter: it is what proves
   the `nosemgrep` rule IDs are correct rather than plausible.
5. **Reverse drift test must filter by `__module__`** — done, and the forward
   test asserts `__name__` rather than callability.

### Two defects the mutation check found in my own tests

Running the new guards against deliberately broken code (rather than trusting a
green run) exposed both:

- The allowlist tests initially imported `fr_table_reader` in-process, which
  only worked because a *different* test module had already inserted the lib
  path — and which violates `test_fr_table_reader_load_styles`'s stated
  per-subprocess discipline. Rewritten as subprocess probes across all four
  load styles.
- The allowlist probe called `_sibling("os")` *before* snapshotting `_SIBLINGS`.
  Since `_sibling` memoizes, a guard that wrongly ALLOWED the name would also
  insert it into the cache, so the allowlist-vs-loaded comparison agreed with
  itself and passed. Reading the cache first makes the two facts independent.
