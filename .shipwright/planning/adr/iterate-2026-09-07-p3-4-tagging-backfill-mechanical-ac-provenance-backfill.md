# Mechanical AC-provenance backfill, conservative by construction

Campaign `req3-04c-ac-identity-wave2`, sub-iterate p3.4 ("tagging-backfill"),
run `iterate-2026-09-07-p3-4-tagging-backfill`. Monorepo-only — the WebUI
repo's own backfill is a separate, already-tracked unit (`w4`, campaign
`req3-06-mechanics-webui`) in a different repository and is explicitly out of
scope here.

## Context

P3.1–P3.3 built AC (acceptance-criterion) identity (`[ACnn]` markers minted
into `spec.md`), an AC-scoped tag grammar (`covers("FR-xx.yy/ACnn")`), and the
manifest/gate machinery to read it — but the monorepo's own tests were still
0% mapped at the AC grain (only 3.46% mapped at the coarser FR grain). This
unit's job was to raise that, preferring mechanical derivation over
hand-mapping, with before/after reported and derived-vs-hand-mapped counts
stated separately (never blended) — full numbers in
`.shipwright/planning/iterate/iterate-2026-09-07-p3-4-tagging-backfill/coverage-report.md`.

## Decision

1. Mint AC ids into the real `spec.md` (`mint_ac_ids.py --write`) — verified
   safe against the P3.3 F11 binding-completeness gate (routes ADVISORY, not
   HARD, while every FR's `required_layers_source` is `inferred_legacy`) and
   idempotent (a second `--write` is a no-op).
2. New mechanical-derivation tool (`backfill_ac_provenance.py` +
   `lib/backfill_ac_provenance.py` + `_backfill_ac_provenance_apply.py`):
   joins a criterion's trailing provenance footnote (e.g.
   `(iterate-2026-07-27-no-silent-revert)`) against the commit carrying that
   exact `Run-ID:` line, and tags every test in a file that commit ADDED
   (git status `A`, never `M`) with the resolved `FR/AC` pair. Conservative by
   construction: a footnote slug is trusted only when it names exactly ONE
   `(fr_id, ac_id)` pair across the WHOLE document (not merely within its own
   FR — see "what changed mid-review" below), a slug must resolve to exactly
   one commit, and a file claimed by two different `(fr_id, ac_id)` pairs is
   dropped from both.
3. A small, explicitly bounded hand-mapped batch (4 files, 20 tags) where the
   already-bare-FR-tagged test's name/docstring/assertions matched one
   specific criterion closely enough to be a defensible judgment call, not a
   guess.
4. Regenerated `.shipwright/compliance/test-traceability.json` via the
   canonical `update_compliance.py --phase iterate` wiring (schema v4,
   already-additive `ac_id`/`acs` fields from P3.2 — no schema change here).

Result: any-tag coverage 475/13728 (3.46%) → 612/13767 (4.45%); AC-scoped
0/13728 (0.00%) → 142/13767 (1.03%) — 122 mechanically derived, 20
hand-mapped, exactly reconciling the manifest's own `with_ac` count (the
mechanical yield was 137 before a Stage-3 doubt-review finding forced a
15-tag revert — see "Stage-3 Doubt-Review Findings" below). Full breakdown,
exclusions, and denominator-delta reconciliation: `coverage-report.md` (same
directory as this file).

## What changed mid-review (the one real correctness bug this unit found in
itself)

`unique_provenance_acs()`'s uniqueness check was originally scoped PER-FR: a
footnote slug naming exactly one AC *within its own FR* was trusted, even if
the same slug also appeared (correctly dropped as ambiguous) in a DIFFERENT
FR. Manual content-coherence verification (checking the OpenAI plan-review's
HIGH finding about file-level over-attribution) caught a real instance:
`iterate-2026-07-27-name-the-blocker` is unique within FR-01.03 (1 bullet,
AC19) but repeats 3× within FR-01.11 (AC16/AC19/AC20) — the underlying commit
delivered 4 distinct criteria across 2 FRs, and the FR-01.03 occurrence was
wrongly trusted. `test_layer_coverage_criteria.py` (tagged FR-01.03/AC19)
turned out to document "a FOLDED acceptance criterion" — matching FR-01.11's
AC20 far better than FR-01.03's AC19 (about external-review-step failure
recording). Fixed: uniqueness is now DOCUMENT-WIDE (a slug must name exactly
one `(fr_id, ac_id)` pair across the whole minted spec, not just within one
FR). The 7 files this produced (101 tags) were reverted to their
pre-backfill state and confirmed passing; the corrected tool no longer offers
that group as a candidate at all.

## External-Plan-Review-Findings (Step 3.5, GLM + OpenAI/codex, verdict revise
both)

| # | Source | Severity | Finding (short) | Disposition |
|---|---|---|---|---|
| 1 | GLM | medium | Arithmetic didn't reconcile (475→713 any-tag vs 258 AC-scoped; +38 denominator) | accepted-and-fixed — `coverage-report.md` states hand-mapped tags are upgrades (no net any-tag change) and reconciles the denominator delta exactly (+11 own tests, +28 pre-existing P3.3 regen gap) |
| 2 | GLM | medium | `mint_ac_ids.py --write` mutates real spec.md with no stated rollback/idempotence check | accepted-and-fixed — verified idempotent (2nd `--write` is a no-op); rollback is a plain `git checkout`/revert of `spec.md`, now documented |
| 3 | GLM | medium | No stated verification that every written AC id resolves | accepted-and-fixed — `validate_applied()` added, re-reads spec.md fresh after every write |
| 4 | GLM | low | Dropped/conflict counts not reported | accepted-and-fixed — `status_counts` added to `derive()`'s output |
| 5 | GLM | low | Schema v4 "unchanged shape" needs confirming no strict-key consumer | rejected-with-reason — `ac_id`/`acs` were already declared additive v4 fields by P3.2, not introduced here; confirmed no consumer does strict/unknown-key rejection (grep + full compliance suite green) |
| 6 | GLM | low | git-status-`A`-only rule: a later rename/split could leave a stale tag | rejected-with-reason — one-shot backfill tool, not a recurring job; every derived file was confirmed to exist and pass at HEAD in this run |
| 7 | OpenAI | high | File-level over-attribution: "added by commit X" ≠ "every test in it verifies this one criterion" | accepted-with-mitigation — manually verified content-coherence for every remaining candidate group against its criterion text; this is also exactly how the FR-01.03/AC19 bug above was caught and fixed (empirical proof the safeguard works) |
| 8 | OpenAI | high | Stale evidence: file may have been renamed/split/deleted since the qualifying commit | accepted-and-fixed — `apply_upgrades` already checks `abs_path.is_file()` before writing; post-write `validate_applied` and a full pytest run confirm current, non-stale content |
| 9 | OpenAI | medium | No stated behavior for shallow clones / rewritten history / merge commits | accepted-and-fixed (shallow) — `_is_shallow_clone()` refuses outright; rejected-with-reason (merge commits) — this repo squash-merges, and the tool fails safe (under-reports) if a trailer is ever lost |
| 10 | OpenAI | medium | Arithmetic reconciliation (duplicate of #1) | accepted-and-fixed — see #1 |
| 11 | OpenAI | medium | Bare-tag migration behaviour underspecified; idempotency untested | accepted-and-fixed — module docstring states the exact rule; `test_apply_upgrades_is_idempotent_on_rerun` added |
| 12 | OpenAI | medium | Needs fixture-based tests for filtering rules (ambiguous slugs, conflicts, no-op reruns) | accepted-and-fixed — 11 pure-logic + 18 CLI/git-correlation tests cover exactly these cases |
| 13 | OpenAI | low | Command-injection risk if slug/path values are shell-interpolated | rejected-with-reason — already safe by construction: git is invoked via subprocess arg arrays, `-F` fixed-string grep, no shell=True anywhere |

## External-Code-Review-Findings (Step 3.7 item 2, GLM + OpenAI/codex, verdict
revise both — run over the merge-base diff)

| # | Source | Severity | Finding (short) | Disposition |
|---|---|---|---|---|
| 1 | Both | high | Required before/after + derived-vs-hand-mapped report was not actually committed anywhere (only quoted inside `reviews.json`) | accepted-and-fixed — `coverage-report.md` written, this ADR |
| 2 | GLM | medium | `generated_at` regenerated as epoch-zero (`1970-01-01T00:00:00+00:00`) — false provenance metadata | accepted-and-fixed — root cause: this unit's earlier regen called the bare `collectors.test_links.generate_file` helper directly (no `data`); switched to the canonical `update_compliance.py --phase iterate` wiring, which supplies a real timestamp |
| 3 | GLM | medium | Schema v4 unversioned key addition, cross-repo (WebUI) consumer risk | rejected-with-reason — same as plan-review #5; P3.2-scope decision, WebUI repo explicitly out of scope for this unit |
| 4 | GLM+OpenAI | high | `_upgrade_bare_tags` was a whole-file regex substitution that could rewrite a same-looking string in a docstring/comment/assertion | accepted-and-fixed — scoped to lines that ARE a `@pytest.mark.covers(...)` decorator; regression test added (never actually fired in this run's real data — all mechanical candidates were git-status-`A` files with zero pre-existing tags) |
| 5 | OpenAI | high | Untagged-test insertion tags every `test*` in the file — file-scope, not test-scope, attribution | accepted-and-fixed at the Tier-3 CI-gate re-review — see T3 below; the "accepted-with-mitigation" disposition this row originally carried relied on this run's real data never having 2+ untagged tests in one candidate file, not a code-level guard, and the gate correctly rejected that as insufficient |
| 6 | GLM | medium | `--grep` substring match over-approximates (prefix-slug collision, prose mention) | accepted-and-fixed — every candidate commit now re-checked against an exact whole-line `Run-ID: <slug>` regex match (git's native trailer parser was tried first and rejected — this repo's real commits put `Run-ID:` and `Co-authored-by:` in separate paragraphs, so `%(trailers:...)` silently under-reports) |
| 7 | GLM+OpenAI | medium | No fixture/integration test exercises the git join at all | accepted-and-fixed — `test_backfill_ac_provenance_cli_git.py` added, against real throwaway git repos |
| 8 | GLM | low | `_enumerate_python_tests`/insertion path may mis-handle class-qualified or nested test ids | accepted-and-fixed at the Tier-3 CI-gate re-review — see below; AST-qualified (`Class.test_name`) rather than left tracked |
| 9 | GLM | low | Orphan-tag write left on disk after a non-zero exit | accepted-and-fixed — `main()` now snapshots every candidate file before writing and restores all of them byte-for-byte on an orphan |
| 10 | GLM | low | `core.quotePath` could hide non-ASCII paths; `"/tests/" in rel` misses a top-level `tests/` layout | accepted-and-fixed — `-c core.quotePath=off` added; substring check replaced with a path-segment check (caught a REAL bug: the fix's own regression test failed against the pre-fix code) |
| 11 | GLM | medium | `_upgrade_bare_tags` uses `write_text` with no atomic-write/failure handling | accepted-and-fixed at Stage-3 doubt-review — see D4 below; `write_text`'s `os.linesep` re-expansion was also a latent CRLF-corruption bug on Windows, not just a non-atomicity gap; both closed together by routing through the same raw-bytes/detected-newline discipline as `apply_writes` |
| 12 | GLM | medium | The now-fixed `derive()` status-accounting test didn't call `derive()` itself | accepted-and-fixed — see #7 above; the new git-fixture tests exercise `derive()`'s real git-join path end to end |

## Stage-3 Doubt-Review Findings (PR #689, internal cascade)

| # | Severity | Claim under doubt | Disposition |
|---|---|---|---|
| D1 | high | "Derived, not guessed" holds for every remaining mechanical group | accepted-and-fixed — disproved for FR-01.01/AC08: 15 of 76 tags (in `test_preserve_canon_marker.py` and `test_canon_marker_write_contract.py`) verify a preserve-canon-marker fix the same introducing commit also shipped, not AC08's stated currency-decision behavior. Downgraded to bare `FR-01.01`, manifest regenerated, `coverage-report.md` corrected (137→122 derived, 157→142 total). The other 3 mechanical groups were individually re-verified per-file after this finding and confirmed matching |
| D2 | medium | Minting `[ACnn]` into the live spec.md is safe for every reader | accepted-and-tracked — `lib.ac_identity`'s own module docstring already named this exact risk as deferred to "whoever wires minting into a real, gate-read document (P3.2/P3.3)"; this unit is that wiring. Verified NOT currently active: no placeholder (`TBD`/etc.) bullet exists in the minted spec.md today, so the placeholder-collapse risk is latent, not live. The digest-gate risk (criterion-text hashing sees `[ACnn] ` as new content) is real but currently harmless by data shape (every minted criterion starts with `Given`); not a correctness bug this unit can responsibly fix by touching `fr_criteria.py`'s 9 downstream consumers inside a tagging-backfill unit — tracked as `trg-ce51177e` |
| D3 | low | A file claimed by two candidates naming the SAME `(fr_id, ac_id)` pair (e.g. a removed-then-re-added file) is always deduped | accepted-and-fixed — `apply_upgrades` now dedupes by `test_id` before calling `apply_writes`; did not fire in this run's real data (added a case for it to be caught if it recurs) |
| D4 | low | "0 tool-driven upgrades fired this run" (why the newline bug was left as tracked-not-fixed) is evidence, not just arithmetic | accepted-and-fixed regardless of which — fixed `_upgrade_bare_tags`'s write path to use the same raw-bytes/detected-newline discipline as `backfill_write.apply_writes`, closing both the non-atomicity gap (#11 above) and the CRLF-corruption risk in the same change |
| D5 | low | The committed coverage-report matches the tree exactly | accepted-and-fixed — two rows corrected for the two post-tagging bloat-cap splits (`test_completion_writers.py`, `test_silent_revert.py`); see `coverage-report.md` |

## Tier-3 CI-Gate Findings (required "PR Review" check, openai/gpt-5.6-luna,
verdict block — nine re-review rounds of the merge-commit diff, the first
after the doubt-review fix commit fell behind `origin/main` and had to be
refreshed via `ensure_current.py`, T2/T3/T4/T6/T7/T8/T9/T10 each fixed and
re-pushed in turn, T5 disputed with a reproduction rather than fixed)

| # | Severity | Finding (short) | Disposition |
|---|---|---|---|
| T1 | high | `_enumerate_python_tests`'s unqualified `rel::name` id (same as finding #8 above) collides for two same-named methods in different classes, and this unit's own dedup-by-test_id (D3's fix) then silently drops one write | accepted-and-fixed — `_enumerate_python_tests` now returns an AST-qualified name (`ClassName.test_name`, nested classes dotted); this tool's own `test_id`/dedup keys use it, while the "already tagged" check against the frozen `fr_tag_grammar` reference parser's `existing` set still matches on the unqualified form (that parser's own id format is out of scope to change here). Regression test: two classes with an identically-named `test_it` method, both must receive their own tag |
| T2 | high | `_upgrade_bare_tags` widened every line in the file matching `@pytest.mark.covers("<fr_id>")`, regardless of which test the decorator belonged to — the general mechanism behind the D1 bug already found and fixed by hand, still live in the code itself | accepted-and-fixed — rewritten to map each bare-tagged line to its OWN AST-qualified test via `decorator_list`, upgrade only when exactly one test in the file owns that bare tag, and skip as `ambiguous_multiple_bare_tags_same_fr` (no line touched, no fallthrough to new-tag insertion) when two or more do. Regression test: two tests sharing one bare FR tag, neither touched |
| T3 | high | The untagged-test insertion path (finding #5 above) tags EVERY wholly-untagged test in a candidate file identically — file provenance ("this commit added this file") never established WHICH test the AC describes, the same file-level attribution T2 closed for the upgrade path | accepted-and-fixed — insertion now fires only when exactly one untagged test exists in the file; two or more is reported `ambiguous_multiple_untagged_tests_in_file` and neither is tagged. `_UNTAGGED`'s CLI fixture (previously 2 untagged functions, asserting both got tagged) encoded the now-rejected behavior and was reduced to 1 function; its 3 dependent tests updated accordingly. Regression test: two classes with a same-named untagged method, neither touched; a single-untagged-method file still auto-tags with its qualified id |
| T4 | high | The writer follows repository-controlled paths (`project_root / rel`) and can write through a symlink (or Windows reparse point) outside the project root when run with `--write` — `Path.is_file()` FOLLOWS the final symlink, so it alone never catches this | accepted-and-fixed — added `backfill_write.is_contained(project_root, abs_path)`: rejects a symlinked leaf (`is_symlink()`) AND checks the resolved path is still under the resolved project root (`resolve(strict=True)`, catching a symlinked ancestor DIRECTORY too, not just the leaf). Wired into both call sites that read/write a candidate file before this fix had any containment check at all — `backfill_write.apply_writes` (the shared engine `backfill_test_links.py` also calls, with no containment check of its own) and this tool's own `apply_upgrades` read/write loop. Regression test: a symlinked test file pointing outside the project root is skipped as `path_escapes_project_root` and the real external target is confirmed byte-unmodified, in both call sites |
| T5 | high (disputed — false positive) | `_upgrade_bare_tags` allegedly replaces only the OPENING quote of a single-quoted `covers('FR-01.01')` bare tag, leaving the original closing quote behind and emitting invalid Python (`covers("FR-01.01/AC01')`) | disputed-and-not-fixed — reproduced directly: `_covers_pattern`'s regex captures the opening quote AND backreferences it (`\1`) to require the SAME character as the closing delimiter, so the matched span always spans the ENTIRE quoted literal (both delimiters), not just the opening one; the hardcoded `covers("{fr_id}/{ac_id}"` replacement therefore replaces the whole literal in one span and always emits valid, consistently double-quoted syntax. Verified by directly invoking `_upgrade_bare_tags` on a single-quoted fixture and asserting `ast.parse` on the rewritten file does not raise — it does not. Added the requested regression test anyway (proves the gate wrong going forward); no production code changed, since none is warranted for a claim that does not reproduce |
| T6 | high | `apply_upgrades` writes each bare-tag upgrade immediately (`abs_path.write_bytes(...)`) while iterating candidates, uncaught — an I/O failure partway through a multi-file batch (disk full, permission error, a file made read-only mid-run) previously propagated straight out of `main()`, so the existing pre-write snapshot/restore (D3's own safety net, built for the ORPHAN-tag case) never ran and every file already written before the failure stayed modified with no recovery | accepted-and-fixed — `main()`'s call to `apply_upgrades` is now wrapped in `try/except OSError`, restoring every file in the same pre-write snapshot the orphan-rollback path already uses and returning `rc=1` with `{"write_error": ..., "rolled_back": True}`. Regression test: a two-file batch where the SECOND file's write raises `OSError` — the FIRST file (already written) is confirmed restored to its original content, not left half-applied. Advisory (non-blocking) follow-up from the same review round, tracked rather than fixed: multiline/commented `@pytest.mark.covers(...)` decorators are invisible to the current single-line-regex ownership check (`_DECORATOR_LINE_RE`) — a real but pre-existing conservatism (such a tag is silently treated as "no bare tag here" rather than mis-parsed), not a regression this fix introduces; reworking the ownership check to a full AST/decorator-span parse is scope creep against a one-shot backfill unit (`trg-ce51177e`'s sibling — same "next unit that touches this module" disposition as D2) |
| T7 | high | `apply_writes` can return a `write_failures` entry for an insertion candidate (e.g. a TOCTOU race — `apply_upgrades` already read the file successfully once itself before adding it to the insert batch, `apply_writes` re-reads it a second time at the end) AFTER a SIBLING candidate's bare-tag upgrade elsewhere in the same batch already succeeded and was written directly to disk; `main()` folded `write_failures` into the ordinary `skipped` list and still returned `rc=0` — a partial application reported as an unqualified success, with the sibling upgrade never rolled back | accepted-and-fixed, narrowly scoped — `apply_upgrades` now also returns `write_failures_occurred: bool`, kept DISTINCT from the pre-existing `skipped` reasons (`file_absent_at_head`, `ambiguous_*`, etc. — deliberate, by-design non-writes, never treated as failures; rolling those back too would regress the tool's own documented best-effort-per-file design). `main()` now rolls back on `orphans OR write_failures_occurred`, sharing the same pre-write snapshot both branches already used. Regression test: `main()` with a monkeypatched `apply_upgrades` that writes one real bare-tag upgrade to disk and then reports `write_failures_occurred=True` — the already-written file is confirmed restored to its original content. This round's edits crossed the repo's 300-LOC bloat-gate cap on three files; cleared by splitting `main()`'s three snapshot/restore tests (orphan, mid-batch OSError, silent write-failure) out of `test_backfill_ac_provenance_cli.py` into a new `test_backfill_ac_provenance_cli_rollback.py` sibling (same precedent as that file's own `_git.py`/`_apply_skips.py` splits) and tightening two in-code comments, rather than filing an exception |
| T8 | high | `main()`'s own snapshot-before-write / restore-on-failure pair (T6's and T7's safety net) bypassed the T4 containment guard entirely — the snapshot loop read every candidate via `abs_path.is_file()` with no `is_contained` check, and the restore loop's `abs_path.write_bytes(content)` FOLLOWS a symlink, so a committed symlink candidate could get its EXTERNAL target rewritten purely by an unrelated sibling's rollback (an orphan or a write-failure elsewhere in the same batch) — the exact vulnerability class T4 closed, reopened in a code path T4 never touched | accepted-and-fixed — every snapshot read and every restore write now goes through `is_contained(project_root, abs_path)` first, skipping a non-contained path in both directions. The fix also crossed the same 300-LOC bloat-gate cap again (this file keeps growing one Tier-3 finding at a time); cleared by extracting the whole snapshot/apply/rollback orchestration out of `main()` into a new `_backfill_ac_provenance_rollback.py` module (`apply_with_rollback`), leaving `main()` a thin CLI shell — same "split, not exception" precedent as T7. Regression test: a symlinked candidate alongside a sibling whose upgrade is rolled back — the symlink's real external target is confirmed byte-for-byte unchanged after the run |
| T9 | high | `apply_with_rollback`'s own two remaining seams were not failure-safe: `validate_applied(...)` ran OUTSIDE any `try`/`except`, so a transient spec-read failure AFTER writes already landed crashed `main()` uncaught with no rollback; and `_restore()`'s per-file `write_bytes` had no exception handling at all, so a restore failure on ONE file aborted the loop and left every LATER file un-restored | accepted-and-fixed — `validate_applied(...)` is now wrapped in `try/except OSError`, reporting `apply_result["validate_error"]` and triggering the same rollback path; `_restore()` is now best-effort per file (`try/except OSError` around each `write_bytes`), collecting failed paths into `restore_failures` instead of raising, with a `_rolled_back_result` helper setting `rolled_back = not restore_failures`. Regression tests: (1) a monkeypatched `validate_applied` raising `OSError` after a real successful write — the write is confirmed restored and `rc == 1`; (2) a monkeypatched `write_bytes` failing for one specific file during restore while a sibling restore succeeds — the sibling IS still restored despite the other's failure, proving `_restore()` is genuinely best-effort, not abort-on-first-failure |
| T10 | high | The T9 fix's `except OSError` around `validate_applied(...)` was itself incomplete: `validate_applied` reads spec.md via `spec_path.read_text(encoding="utf-8")`, which raises `UnicodeDecodeError` on malformed UTF-8 — a `ValueError` subclass, NOT an `OSError` — so that specific, plausible failure mode still crashed `main()` uncaught with writes left un-rolled-back, one round after the seam was supposedly closed | accepted-and-fixed — the clause now catches `(OSError, UnicodeDecodeError)`. Regression test: a genuinely malformed (non-UTF-8) spec.md file, exercising the REAL `validate_applied` (not monkeypatched) against a real successful write, confirming the write is restored and `rc == 1`. This round's addition crossed the 300-LOC bloat-gate cap on `test_backfill_ac_provenance_cli_rollback.py` a fourth time in this same file's lineage; cleared by the same "split, not exception" precedent — the failure-safety tests (T9's two + T10's + the T8 symlink test) moved into a new `test_backfill_ac_provenance_cli_rollback_failsafe.py` sibling, leaving the original file with only the pre-existing orphan-tag and mid-batch-write-failure tests |

T1/T2/T3 are mechanism-level fixes to code this unit itself introduced (not
the frozen shared `backfill_scan.py`/`fr_tag_grammar.py` engines, which have
the same unqualified-id shape by long-standing, out-of-scope design) — T2 and
T3 mean the D1 root cause (and its insertion-path twin) are now closed at the
mechanism, not only patched by hand for the one batch the doubt-review
happened to catch. T4 is a genuine security fix (path-traversal via a
committed symlink), landed in the SHARED `backfill_write.py` module rather
than duplicated per-caller — confirmed via its only two real callers before
editing it (neither is "frozen" the way `fr_tag_grammar.py` is).

## Consequences

The monorepo's AC-scoped coverage is no longer zero, with an honest,
conservative, and now bug-fixed derivation trail; eleven real correctness/security
bugs (cross-FR slug reuse, whole-file regex over-substitution, per-file
mis-attribution inside a group-level-verified mechanical batch, that same
over-substitution mechanism's general form in both the upgrade AND the
insertion write path, a symlink path-traversal write in the WRITER, an
uncaught mid-batch write failure, a SILENTLY-succeeding mid-batch write
failure, that SAME symlink path-traversal class reopened in `main()`'s
own snapshot/restore pair — a code path the first symlink fix never
touched — that same rollback wrapper's own validation/restore seams not
being failure-safe, and that SAME seam's exception clause itself being
narrower than the exception it needed to catch) were found and fixed —
two by this unit's own review cascade before shipping, one (D1) by the
orchestrator's Stage-3 doubt-review after merge-base review, eight (T2,
T3, T4, T6, T7, T8, T9, T10) by the required Tier-3 CI-gate re-review of
the merge commit across nine separate re-review rounds (one of the nine,
T5, was a disputed false positive verified NOT to reproduce and left
unfixed) — plus a metadata bug (epoch-zero timestamp) in
this unit's own regen step and a latent Windows newline-corruption bug (D4)
in an unexercised
code path. D2 remains an
acknowledged, currently-latent risk left tracked rather than fixed, in shared
`fr_criteria.py` infrastructure this unit does not own (`trg-ce51177e`; fixing
it means touching 9 downstream gate consumers, which is scope creep against a
one-shot backfill unit and belongs to whichever unit next touches that
module).

## Rejected alternatives

Full AC coverage via fuzzy/title-similarity matching was rejected as
dishonest — this codebase's own `backfill_signals.TITLE_CAP` precedent
requires a heuristic verdict to have deterministic corroboration or stay
advisory, never auto-written. The mechanical yield (137 tags) is what the
real signal supports; manufacturing a bigger number was explicitly out of
scope.
