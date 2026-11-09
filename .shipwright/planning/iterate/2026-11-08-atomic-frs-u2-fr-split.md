# Iterate: atomic-frs U2 — `fr_split`, the tool that cuts one requirement into several

Run: `iterate-2026-11-08-atomic-frs-u2-fr-split` · Type: feature · Complexity: medium (operator-classified high risk: spec, tests and traceability change together) · Branch: `iterate/atomic-frs-u2-fr-split`
Campaign: `.shipwright/planning/campaigns/2026-11-08-atomic-frs-BRIEF.md` (U2). This PR is the TOOL only; the first real cut (FR-01.11) is a second PR with the list of cuts for the operator to approve.

## Goal
`fr_split.py` takes an FR id and a grouping (which criteria go to which new requirement, with a plain name and description each), performs the cut in `spec.md`, the test tags and the coverage baseline, records every move, and runs a hard conservation check. Dry run first (diff, nothing written). Code finds the seams (U1), the AI proposes ONE grouping, the operator confirms, the tool performs it.

## Operator decisions (asked at the start of this run)
1. A moved criterion **keeps its number** (`FR-01.11/AC21` -> `FR-01.22/AC21`); only the FR part of the id changes.
2. Old ids stay resolvable through a machine-readable `## AC-Move-Map` table in `spec.md` (`Old id | New id`), append-only, like `## FR-Fold-Map`.
3. Two PRs: this tool PR, then the data PR for FR-01.11.
From the brief: no auto-merge; full review cascade with `model=opus` passed explicitly; parts need at least 3 criteria (stop rule); admin merge only if the operator grants it again in chat.

## Why FR-01.14 was not flagged by U1 (checked first, as asked)
`fr_cluster_report.py --fr FR-01.14`: 29 criteria, 28 bound to tests (enough evidence), verdict **no**: the evidenced criteria form ONE connected cluster plus loose singles. It is coherent, not under-evidenced. It stays whole; this run does not touch it.

## Design
| Piece | File | Notes |
|---|---|---|
| Move map | `shared/scripts/lib/ac_move_map.py` | parse / render / `resolve_ac`; header avoids `ID` so the FR-table readers ignore it |
| Spec cut | `shared/scripts/lib/fr_split_spec.py` | pure text-to-text. Moves bullet blocks verbatim, adds one table row + one anchored section per part, next free FR number counts live, removed, heading and map ids. Refuses unmarked criteria, prose between criteria, parts < 3, source keeping < 3, unknown / doubled criteria |
| Tag rewrite | `shared/scripts/lib/fr_split_tags.py` | only places that BIND (covers decorator / pytestmark strings, `#` `//` `/* */` comments), never other string literals, never a bare FR tag; keeps CRLF and non-ASCII columns |
| Conservation | `shared/scripts/lib/fr_split_check.py` | catalog (exactly once, text unchanged, count), bindings (same tests under new ids, none under old), manifest (layer + test + tag source per criterion), Group I1 name fence, shared-test coupling |
| Tool | `shared/scripts/tools/fr_split.py` | dry run default; `--apply` writes, regenerates the traceability manifest BEFORE and AFTER (the committed one may already lag), compares, restores every file on any failure; manifest restored to committed bytes unless `--keep-manifest`; `--allow-shared-tests` |

## Acceptance criteria (framework tool; no FR row changes — see Spec impact)
1. Dry run prints the cuts and a diff and writes nothing; exit 0 when the conservation check holds.
2. Every criterion of the source appears exactly once afterwards, wording byte-identical, number kept.
3. Tags that bind a moved criterion are re-pointed; fixture strings, bare FR tags and unrelated ids are untouched.
4. Every move is in the `## AC-Move-Map`; the section does not disturb the FR-table, catalog or fold-map readers.
5. A lost, doubled or reworded criterion, a changed test binding, a name with implementation detail, or a test naming criteria of two parts makes the run exit 1; on `--apply` the tree is restored.
6. A grouping that breaks the stop rule or a spec shape the tool cannot cut safely exits 2 with the reason.

## Spec impact
NONE (tooling): no FR row or criterion changes in this PR. `shared/fr-authoring.md` section 3c and `docs/guide.md` (I10 paragraph) gain a paragraph on performing a cut. Reason code: tooling.

## Verification done
- `shared/tests/test_fr_split.py`: 24 tests (spec cut, refusals, CRLF, tags, conservation negatives, tool dry run / apply / restore / coupling / exit codes, reader tolerance).
- Live probe on the real catalog (cut FR-01.11 AC21-25 -> FR-01.22): conservation ok, 3 test files re-pointed, before/after manifest regeneration compared, tree restored afterwards (not part of this PR).

## Known limits / follow-ups
- JS/TS tags: the comment scanner has no string state (inherited from U1); a `//` inside a string literal is scanned as a comment, in the check and the rewrite alike, so both stay consistent.
- `fr_history.py` and other consumers do not yet follow the move map; the table is the contract, wiring consumers is a follow-up (old ids keep working as text in history).
- Non-test files that quote an old id (ADRs, iterate specs, event log) are history and stay untouched.

## Review round 1 (spec: APPROVE; code review and doubt review: findings, status)
Fixed in this PR: cells read with `split_cells` and a cell-count refusal (M1); a sub-heading under the source is refused (M2); restore covers Ctrl-C, is per file and says honestly when it could not restore, files this run created are removed again (M3, doubt 3); duplicate part titles refused and part labels keyed by new FR id (M4); `\n`-only line offsets (L1); FR numbers above 99 refused (L2); document order kept (L3); non-UTF-8 test files that name the source are a problem, not a silent skip (L4); old ids still quoted outside a tag are listed as a note (L5); heading regex for spec selection (L6); unusable input of any type exits 2 (L9); the AC registry gets the source's pre-cut high-water mark and the new FRs' (doubt 1, L7); the push-time baseline-growth check reads the AC-Move-Map so a moved baseline entry is not "new" (doubt 2); targets are re-compared right before writing, uncommitted changes in a target refuse the write (`--allow-dirty`), originals are backed up to a temp dir (doubt 4); move-map ids sit in backticks so `| FR-` line filters do not count them (doubt 6); only real `covers(...)` calls are rewritten, a `parametrize` row that mentions the word is not (doubt 8).
Accepted, not fixed here: (doubt 5) the evidence walker skips some directories and files over 2 MB that the manifest collector reads, so a dry run can be green and `--apply` refuse (safe: it restores); (doubt 7) no consumer reads the move map yet except the baseline-growth check; (doubt 9) running from the plugin cache against another repo needs the compliance plugin next to `shared/` (to be probed before the webui run, U2b); (doubt 10) the gitignored evidence index is refreshed by the manifest regeneration.

## Review round 2 (external plan review, architecture review, plan-internal review) - decisions
Fixed in this PR: JS/TS comment scanner now tracks string and template-literal state, one shared `js_comment_spans` for the evidence scanner and the rewriter (a `//` inside a string is text); the free-FR-number search also counts every FR number in `shipwright_ac_registry.json`; `remaining` needs a title and a description and its title is whitespace-collapsed; the baseline-growth check imports the move map at module level and follows `resolve_ac`.
Kept on purpose: the backup/restore layer. Git alone cannot restore a half-written run when the tree holds the operator's other uncommitted work, and the layer is tested (Ctrl-C, partial failure). `--allow-dirty` stays opt-in.
Not changed here (listed so PR 2 starts from them):
1. **Consumers of the move map.** The keystone AC gate, the Q2 AC-claims check and the F11 spec-impact / FR gates compare old and new AC sets and will read every moved criterion as removed plus added. Before PR 2: run those gates on the probe tree and either resolve through `resolve_ac` in the change-set builder or write the expected noise into PR 2's plan. Also wire `resolve_ac` into `fr_history` / AC-catalog readers; decide how a move map composes with the FR-Fold-Map (fold-then-move).
2. **Racing iterates.** A parallel iterate may mint the same new FR number on another branch. PR 2 re-runs the dry run against freshly fetched `origin/main` right before apply and lists the chosen ids at the top of the report.
3. **AC numbers are stable handles with gaps.** After a cut a part's numbers are not contiguous; the registry high-water mark keeps them unreused. Documented in fr-authoring 3c; PR 2 adds a test that the next mint on the new FR is above its high-water.
4. **Copied row columns.** New table rows copy Priority/Basis/Layers from the source unless the grouping overrides them; the operator confirms them in PR 2's list of cuts, together with test files carrying FR-level tags on the source.
5. **Other repos (U2b).** Running from the plugin cache against another repo needs the compliance plugin beside `shared/` (doubt 9): probe before the webui run.
6. FR-01.14 (29 ACs, one connected cluster) stays whole; exception recorded in the Why section above.

## Review round 3 (external code review GPT + GLM: both "revise")
Fixed: a target edited during the baseline regeneration now goes through the common cleanup path, so the regenerated manifest is put back (was an early return that left it); the temp backup is deleted after a successful apply; a successful apply without `--keep-manifest` says the committed manifest was left as is and must be regenerated in the data PR; the baseline-growth check follows a full move chain (test with two moves); `dirty_targets` moved into `lib/fr_split_check.py` (keeps the tool under 300 lines).
Accepted, not changed: no committed manifest means no manifest binding to lose, the run prints a note and the catalog and tag checks still hold; a compact (non one-per-line) baseline is reported by note and renamed by hand, because rewriting it as JSON would reformat the file; an unparseable test file surfaces as a failed binding check (safe direction); the dirty check names raw porcelain paths (cosmetic).
