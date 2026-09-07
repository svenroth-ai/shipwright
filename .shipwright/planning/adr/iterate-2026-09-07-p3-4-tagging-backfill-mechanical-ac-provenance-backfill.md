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
0/13728 (0.00%) → 157/13767 (1.14%) — 137 mechanically derived, 20
hand-mapped, exactly reconciling the manifest's own `with_ac` count. Full
breakdown, exclusions, and denominator-delta reconciliation:
`coverage-report.md` (same directory as this file).

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
| 5 | OpenAI | high | Untagged-test insertion tags every `test*` in the file — file-scope, not test-scope, attribution | accepted-with-mitigation — same disposition as plan-review #7 |
| 6 | GLM | medium | `--grep` substring match over-approximates (prefix-slug collision, prose mention) | accepted-and-fixed — every candidate commit now re-checked against an exact whole-line `Run-ID: <slug>` regex match (git's native trailer parser was tried first and rejected — this repo's real commits put `Run-ID:` and `Co-authored-by:` in separate paragraphs, so `%(trailers:...)` silently under-reports) |
| 7 | GLM+OpenAI | medium | No fixture/integration test exercises the git join at all | accepted-and-fixed — `test_backfill_ac_provenance_cli_git.py` added, against real throwaway git repos |
| 8 | GLM | low | `_enumerate_python_tests`/insertion path may mis-handle class-qualified or nested test ids | not-fixed, tracked — real edge case, no evidence it fired in this run (all mechanical candidates are module-level `test_*` functions); left as a known limitation of the insertion path, not blocking this backfill's own correctness |
| 9 | GLM | low | Orphan-tag write left on disk after a non-zero exit | accepted-and-fixed — `main()` now snapshots every candidate file before writing and restores all of them byte-for-byte on an orphan |
| 10 | GLM | low | `core.quotePath` could hide non-ASCII paths; `"/tests/" in rel` misses a top-level `tests/` layout | accepted-and-fixed — `-c core.quotePath=off` added; substring check replaced with a path-segment check (caught a REAL bug: the fix's own regression test failed against the pre-fix code) |
| 11 | GLM | medium | `_upgrade_bare_tags` uses `write_text` with no atomic-write/failure handling | not-fixed, tracked — real hardening opportunity (route through the same atomic writer as `apply_writes`); did not fire in this run (0 upgrades applied — see #4); left for a future pass if this tool is reused |
| 12 | GLM | medium | The now-fixed `derive()` status-accounting test didn't call `derive()` itself | accepted-and-fixed — see #7 above; the new git-fixture tests exercise `derive()`'s real git-join path end to end |

## Consequences

The monorepo's AC-scoped coverage is no longer zero, with an honest,
conservative, and now bug-fixed derivation trail; two real correctness bugs
(cross-FR slug reuse, whole-file regex over-substitution) were found and
fixed by this unit's own review cascade before shipping, plus a metadata bug
(epoch-zero timestamp) in this unit's own regen step. Two low/medium findings
(class-qualified test ids, non-atomic upgrade writes) are tracked but not
fixed — neither fired in this run's real data, and fixing them speculatively
would be scope creep against a one-shot backfill unit.

## Rejected alternatives

Full AC coverage via fuzzy/title-similarity matching was rejected as
dishonest — this codebase's own `backfill_signals.TITLE_CAP` precedent
requires a heuristic verdict to have deterministic corroboration or stay
advisory, never auto-written. The mechanical yield (137 tags) is what the
real signal supports; manufacturing a bigger number was explicitly out of
scope.
