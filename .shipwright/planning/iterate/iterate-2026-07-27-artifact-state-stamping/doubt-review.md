# Doubt review (adversarial, fresh context) — iterate-2026-07-27-artifact-state-stamping

Reviewer: `shipwright-build:doubt-reviewer` (opus), briefed to DISPROVE the claim
"a produced artifact now names which project state it describes, honestly — and where it
cannot, it says so". 9 doubts: 1 high, 3 medium, 5 low. Advisory, must-address.

**The high one was a real CI-red, and it was mine.** The reviewer noticed that
`audit_staleness.py` on disk differed from the reviewed diff: an earlier code-review fix
had replaced the absolute path bootstrap with `from scripts.lib._provenance import
strip_banner`. That module is also loaded **by file path** from two other pytest sessions
where `scripts` resolves to a different plugin's namespace. Verified empirically before
fixing — `plugins/shipwright-security` `test_finalize_security_compliance` failed with
`ModuleNotFoundError: No module named 'scripts.lib._provenance'`. This is the ADR-045
lib-collision landmine verbatim: green from the compliance plugin (1374 tests), red in CI.

## Dispositions

| # | Sev | Doubt | Disposition |
|---|---|---|---|
| D1 | high | `from scripts.lib._provenance import strip_banner` breaks file-path loads from other plugins' sessions | **FIXED, verified** — reverted to the absolute `parents[4]` bootstrap. Security + shared loaders now pass (6 and 5 tests). A **static guard** was added in the compliance plugin so the constraint no longer depends on tests in other plugins |
| D2 | med | a *rejected* `--run-id` fell through to `run_config::run_id`, so `{run_id}` produced a plausible wrong id instead of `(unknown)` | **FIXED** — `_resolve_run_id` distinguishes absent from rejected; a supplied-but-unusable value stamps `null` and warns. Regression-tested |
| D3 | med | AC3 said the banner names the run the doc "was rendered from", but `chore(release)` and the security Step 7.5 finalizer regenerate outside an iterate, so it names the *previous* iterate | **FIXED (wording)** — the spec criterion and `run_id_of`'s docstring now say "the most recent completed change recorded at render time" and spell out the two non-iterate producers. Not fixable by adding HEAD: a per-commit field would re-open the permanently-dirty tracked-markdown defect |
| D4 | med | wrong-tree stamping succeeds silently (exit 0), and the only cross-check fired spuriously on every legitimate iterate F5 | **FIXED** — the check now compares against the record's own `iterate_latest.run_id`, which is code-resolvable and catches the wrong-tree case; the run-config comparison is demoted to a note that cannot fire when the record agrees |
| D5 | low | `set(line.split())` is hash-randomised and `next(...)` took the first yielded value even when `None`, so two `commit=` tokens parsed differently per process | **FIXED** — ordered scan, first *valid* token wins |
| D6 | low | git C-quotes non-ASCII porcelain paths, so an exclusion can miss; `to_block` validated `run_id`/`commit` but passed `dirty` through | **FIXED (the second)** — `dirty` is now validated like the others. The C-quoting gap is **accepted and disclosed**: it fails safe (over-reports modification, never under-reports) and is unreachable for the ASCII repo-root path both producers use |
| D7 | low | `sbom_generator` destructured `provenance_lines()` into two names, so the third line sibling card `trg-a1fd8125` plans would raise at render time | **FIXED** — sbom now splats via a `generated_suffix` parameter; the list length is documented as not part of the contract |
| D8 | low | `normalize()` strips the banner for all 8 registry docs though only 5 are stamped, widening Group E's blind spot for 3 | **ACCEPTED, disclosed** in the spec. The reviewer could not construct a realistic body line starting with the token in any of the 8, so this is a widened blind spot, not a demonstrated miss |
| D9 | low | four assertions could not fail on the property they advertised | **FIXED (three)** — the canonical-form test asserts on **bytes** (so CRLF can actually fail it), the garbage test asserts **values** not just "did not raise". The byte-stable render test is kept: it is cheap and guards the banner specifically, with real clock-drift coverage living in `test_data_collector_determinism` |

## What the reviewer attacked and could NOT break

Recorded because "no finding" is only meaningful when the attempt is stated: a third
banner-forgery vector (tried `run=x`, `x-run=…`, `clean`, `uncommitted-changes`,
`commit=…`, `(unknown)` as run ids — all round-trip or degrade correctly); a 7-hex English
word reaching `commit` (no path — the compliance banner carries no commit and the tool's
comes from `git rev-parse`); a later write clobbering `source_state` (`record_coverage_total`
preserves it; `durable_atomic_write` writes raw bytes so the two cannot fight over CRLF);
F5b naming the previous run (`finalize_iterate` records `work_completed` *before* the
regen, deliberately); Group E newly reporting stale (two anchored monotone removals can
only reduce difference, and the transition commit normalises equal on both sides);
`parents[4]` depth (correct for the layout, and matches three pre-existing files);
`ComplianceData.run_id` as a contract break (appended last with a default); and
idempotency/refusal (`load_record` raises before any write).
