# Mini-Plan: changelog-manifest-version-sync

- **Run ID:** iterate-2026-08-11-changelog-manifest-version-sync

## Files to create/modify

**Revised after Internal Plan Review** (16 findings; see spec's `## Internal
Plan Review` for the full triage table) — the headline change is that the
tool now owns commit-blob verification and its own `git add` staging,
instead of Step 6 hand-assembling a pathspec from the tool's plain report.

| File | Change |
|---|---|
| `shared/scripts/tools/sync_release_manifests.py` | new — validate/write/stage/verify-commit tool |
| `shared/scripts/tools/tests/test_sync_release_manifests.py` | new — unit tests |
| `shared/scripts/tools/verifiers/changelog_checks.py` | edit — new `check_manifest_version_matches_tag`, wired into `run_changelog_checks` |
| `shared/tests/test_verifiers_test_changelog_deploy.py` | edit — cover the new check (existing home for `check_changelog_version_matches_tag` / `check_git_tag_exists` tests) |
| `plugins/shipwright-changelog/skills/changelog/SKILL.md` | edit — new **Step 5.4** (before Step 5.5), Step 6 gains the verify-commit `&&` chain before `git tag` and adds `manifest_pathspec` to its commit pathspec |
| new: `plugins/shipwright-changelog/skills/changelog/references/manifest-sync.md` | new reference doc — config shape, status vocabulary, failure table, package-lock.json exclusion, crash-window recovery (mirrors `rerunning-a-release.md`'s style) |
| `shared/schemas/` | no new schema file — matches `shipwright_sync_config.json`'s own precedent (no schema file for that config either) |
| `docs/hooks-and-pipeline.md` | edit — artifact-write matrix gains the manifest write + the config-data-flow table gains the new `shipwright_changelog_config.json` read |
| `docs/guide.md` | edit — Appendix B / Chapter 8 (quality gates) gains a one-line mention |
| `.shipwright/planning/01-adopted/spec.md` | edit — FR-01.09 gains one AC block |

This repo's own root does not get a `shipwright_changelog_config.json` —
"no manifests declared" must equal "file absent" (a checked-in empty
declaration would be inconsistent noise), and this repo does not itself
publish a package manifest. shipwright-webui wiring its own config to
declare `bootstrapper/package.json` is a follow-up in that repo, out of this
diff's reach (stated in the spec's Out of Scope).

## Work breakdown

1. **Config shape + no-op path.** `sync_release_manifests.py` reads
   `shipwright_changelog_config.json` (`{"published_manifests": [{"path": ..., "format": "package_json"}]}`).
   Missing file or empty/absent `published_manifests` → return
   `{"status": "ok", "synced": [], "note": "no published manifests declared"}`
   without touching disk, without a `git add`. Test: fixture project with no
   config file → no-op; fixture with `published_manifests: []` → no-op.
2. **`--version` validation.** Bare semver (`X.Y.Z`, optional
   prerelease/build metadata), no leading `v`, no whitespace/control chars —
   checked before any file is touched, any mode (write, verify-commit,
   dry-run). Test: `v1.2.3` / `1.2.3 ` / `1.2.3\n` all rejected with a named
   status (`invalid_version_argument`) before touching disk.
3. **Pre-flight validation pass (two-phase, part A).** Before any write:
   for every declared entry, resolve `path` against `--project-root`,
   `Path.resolve()` it (following symlinks), and require the result stays
   under the resolved project root — else `path_outside_project`. Then
   require the file exists (`manifest_missing`), `format` is a recognized
   value (`unsupported_format` — only `package_json` implemented), the file
   parses as JSON (`parse_error`, wrapped so stdout still carries
   well-formed JSON even on a parse failure), and (package_json) a
   top-level `version` key exists (`missing_version_field` — never inject
   one) and is a string (`invalid_version_type`). Any pre-flight failure on
   ANY entry aborts before phase B — disk is untouched. Test: 2-manifest
   fixture, first entry valid + second entry missing `version` key → zero
   writes on disk, `status` names the second entry specifically.
4. **Write pass (two-phase, part B) — package_json format, surgical
   substitution.** For each entry (all pre-flight-valid at this point):
   if the manifest's current `version` value already equals the target
   (idempotent re-run) → `changed: false`, no write. Otherwise locate the
   *unique* text span `"version"\s*:\s*"<current_value>"` in the raw file
   text; if exactly one match, replace only that span (preserves the
   file's own indentation/newline convention — a one-line diff in the
   common case) and `changed: true`. If the surgical match is ambiguous
   (0 or 2+ occurrences of that exact key+value pair, e.g. a nested
   `"version"` field with the same value), fall back to a full
   `json.load`/mutate/`json.dump(indent=2)` re-render and mark
   `reformatted: true` in that entry's result, so the SKILL/operator can
   see when a whole-file rewrite happened. Use the same
   `durable_atomic_write`-style tmp+replace the changelog aggregator uses.
   If any entry's write fails partway through phase B, restore every
   already-written entry in this pass to its original captured bytes
   before returning the failure — disk ends exactly as it started. Test:
   one manifest, surgical path → diff is exactly the version value; a
   crafted fixture with duplicate value spans → `reformatted: true`; a
   monkeypatched write failure on entry 2 of 2 → entry 1's bytes restored,
   asserted via before/after file hash.
5. **`--stage` — tool owns `git add`.** After a successful write pass (or a
   no-op resolve-to-idempotent pass), run `git add` on exactly the paths
   that were declared (whether `changed` or not — an already-current
   manifest still needs to be part of the pathspec Step 6 assembles from
   this tool's own output, for symmetry with `evidence_pathspec`), and
   return `manifest_pathspec` (empty list when nothing was declared — Step
   6 must guard against an empty pathspec argument, same rule
   `evidence_pathspec` already carries). Test: `git status --porcelain`
   before/after `--stage` on a fixture repo confirms exactly the declared
   paths are staged.
6. **`--verify-commit <sha>` mode.** Separate CLI mode, run by SKILL.md
   AFTER the release commit exists and BEFORE `git tag`. For each declared
   manifest, `git show <sha>:<path>` the committed blob (not the worktree),
   parse it, and confirm `version` equals `--version` exactly. Any mismatch
   → `status: "verify_mismatch"`, names the path and both versions, exit 1
   — the SKILL chains this with `&&` immediately before `git tag`, so a
   manifest whose *committed* bytes are still stale stops the release
   before it's tagged. This is what actually closes the regression case
   from the card — write+verify against the worktree alone does not, since
   nothing then re-checks that the write actually landed in the commit.
   Test: commit fixture with one manifest deliberately NOT included in the
   commit (staged-but-reverted before commit, simulating an omitted
   pathspec) → verify-commit catches it even though a worktree-only verify
   would not (regression test for finding #1).
7. **Idempotent re-run.** Test: manifest already at the released version
   (both a `--version`-mode write pass and a `--verify-commit` pass) →
   `changed: false`, no write, verify still passes, `status: "ok"` — same
   "success, not a retry" contract as `aggregate_changelog.py`'s
   `changelog_updated: false`.
8. **Several manifests.** Test: 2+ declared manifests, all package_json,
   mixed initial versions (one already current, one stale) → correct
   per-entry `changed` values, all verified, one JSON result listing every
   entry.
9. **Standing detective check.** `check_manifest_version_matches_tag` in
   `changelog_checks.py`: reads `shipwright_changelog_config.json`, and for
   each declared manifest compares its current committed `version` against
   the latest git tag (mirrors `check_changelog_version_matches_tag`'s own
   comparison pattern). No manifests declared → no-op / pass. Wired into
   `run_changelog_checks` at ERROR severity. Test: fixture repo with a
   manifest deliberately left stale relative to the latest tag → check
   fails; matching → passes; no config → passes (no-op).
10. **SKILL.md wiring.** New **Step 5.4** (before Step 5.5, so a
    worktree-modifying write never lands in the gap between Step 5.5's
    `--stage` and Step 6's commit — the ordering Internal Plan Review
    flagged): run the tool non-dry-run in write+stage mode; `status: "ok"`
    → proceed, folding `manifest_pathspec` into Step 6's commit pathspec
    list alongside `evidence_pathspec`; anything else → stop, do not tag
    (same wording/contract as Step 5.5's existing rule). Step 6 gains the
    `--verify-commit "$(git rev-parse HEAD)" && git tag` chain, run
    alongside (not replacing) the existing
    `refresh_compliance_docs.py --verify-commit --release-audit` call — both
    must pass before the tag. Step 7 (PR) unaffected.
11. **New reference doc** `manifest-sync.md`, linked from SKILL.md's
    Reference Documents list: config shape, full status vocabulary, the
    write-then-**commit**-verify (not worktree-verify) contract, the
    package-lock.json exclusion, and the crash-window recovery note
    (abort between Step 5.4 and Step 6's commit leaves a bumped,
    uncommitted manifest in the worktree — re-run the release or
    `git checkout -- <path>`; the standing check from item 9 catches it if
    it is ever committed by accident later).
12. **Docs sync** — `docs/hooks-and-pipeline.md` artifact-write matrix row
    AND config-data-flow row (new config file being read) for
    `/shipwright-changelog`, `docs/guide.md` Appendix B one-liner, FR-01.09
    AC block, per CLAUDE.md's "changed skill step → update docs in the same
    diff" rule.

## Test strategy

Unit tests only (`shared/scripts/tools/tests/test_sync_release_manifests.py`
+ an addition to `shared/tests/test_verifiers_test_changelog_deploy.py` for
the standing check, pytest, tmp_path + a throwaway `git init` fixture repo
for the `--stage`/`--verify-commit` modes — no real repo state, no network,
no npm). No E2E: this is a release-time CLI tool with no browser/web surface
(see Verification section of the iterate spec). Scenarios: none declared
(no-op) · one manifest (write+stage+verify-commit) · several manifests (all
synced) · missing-file declared (fails closed, disk untouched) ·
unsupported format (fails closed, disk untouched) · path escape — absolute
path and `..` and symlink-out (fails closed, disk untouched) · malformed
`--version` (fails closed before any file touched) · missing/non-string
`version` field (fails closed, disk untouched) · mid-sequence write failure
on entry N of M (disk restored to original bytes) · surgical-substitution
ambiguity fallback (`reformatted: true`) · idempotent re-run (`changed:
false`, still verifies ok) · **the regression case**: a manifest staged but
NOT actually present in the commit (omitted pathspec, simulating the exact
failure mode from the card) — worktree-only verification would pass this,
`--verify-commit` must catch it · standing check catches drift from a
release cut before this gate existed.

## Amendments from Branch A external review + Architecture Review

Full findings/triage/reconciliation live in the iterate spec's `##
External LLM Review (Branch A)` and `## Architecture Review` sections. This
is the implementation-facing summary layered onto the work breakdown above
— items 3/4/6/9/10 below amend, not replace, the corresponding numbered
steps above.

- **Item 3 (pre-flight) gains:** config shape validation before anything
  else (`invalid_config` on malformed JSON / non-array `published_manifests`
  / non-object entry / missing-or-non-string `path`); canonical-path
  dedup (`duplicate_manifest_path`); reject **any** symlink in the path,
  not just an escaping one (`path_is_symlink` — `git add` stages the
  symlink entry, not the resolved target's blob, so an in-root symlink
  would let write and staged content diverge); a per-path
  `git status --porcelain -- <path>` dirty check before this tool's own
  writes (`manifest_dirty_before_sync` — otherwise `--stage` can fold
  unrelated pre-existing edits into the release commit); and duplicate
  top-level `"version"` key detection via `object_pairs_hook`
  (`ambiguous_manifest_structure` — never guess which one to rewrite).
- **Item 4 (write pass) gains:** `re.escape(current_value)` in the
  surgical-substitution regex (an unescaped semver string's `.`/`-`/`+`
  are regex metacharacters and can produce a false "unique match").
- **Item 5 (`--stage`) gains:** rollback now also covers a `git add`
  failure after writes succeeded (index lock, FS error) — restore the
  already-written manifests' bytes either way, distinct status
  `stage_failed`.
- **Item 6 (`--verify-commit`) gains:** takes `--result-file <path>`
  pointing at Step 5.4's own JSON result and reads its manifest list from
  there — **never** re-reads `shipwright_changelog_config.json`, which is
  mutable worktree state after the commit exists (this is what actually
  makes the gate trustworthy: the set being verified is the set that was
  actually written and staged, not whatever the config happens to say
  now). Also resolves each path relative to the true git root via
  `git rev-parse --show-prefix`, not assumed equal to `--project-root`.
  All git subprocess calls use `--` path separators, no shell.
- **Item 9 (standing check) severity changed:** `WARNING`, not `ERROR` —
  descoped in Architecture Review reconciliation (both external reviewers
  independently raised proportionality concerns about a hard release-
  blocking invariant on ordinary post-release commits; the pre-tag gate is
  what's actually release-blocking, this check's remaining job is
  surfacing drift the gate never saw). Reads from `git show HEAD:<path>`
  and imports the parsing helper from `sync_release_manifests.py` rather
  than re-implementing manifest parsing a second time.
- **Item 10 (SKILL.md wiring) gains:** Step 5.4 writes its result JSON to
  `.shipwright/runtime/manifest_sync_result.json` — a disposable,
  gitignored release-scratch path (same tier as
  `events-context-index.json`), not run-id-scoped, since
  `/shipwright-changelog` establishes its own `SHIPWRIGHT_RUN_ID` only at
  Step 7, after this file is already needed — for Step 6's
  `--verify-commit --result-file` call to consume.

**Architecture Review outcome:** both reviewers proposed a smaller
alternative (a read-only pre-tag gate, no auto-write) instead of the
write/stage/verify mechanism. Reconciliation (full reasoning in the iterate
spec): the write mechanism is kept because the operator's own card
explicitly scopes it as a separate, required item ("write ... so tag and
manifest cannot diverge by construction") — a read-only gate would still
depend on the operator remembering to hand-bump the manifest correctly,
which is the same fallible step that caused the measured drift. The
reviewers' proportionality point is accepted where it applies most
cleanly: the standing check, descoped from `ERROR` to `WARNING`.

## Alternative approach (considered, rejected)

**Alternative: a generic "manifest sync" step inside
`refresh_compliance_docs.py`** (reuse Step 5.5's existing "status: ok /
stop" tool instead of adding a new one). **Rejected** because
`refresh_compliance_docs.py` is scoped to the seven *derived compliance*
documents (dashboard, SBOM, traceability, ...) recomputed from
`shipwright_events.jsonl` + git history + triage — its own reference doc
(`compliance-evidence.md`) is explicit that these documents "carry no
information of their own." A published-package manifest is the opposite:
externally-consumed, hand-authored content (name, dependencies, scripts)
that this tool must read-modify-write, not recompute from repo history.
Folding it into the compliance refresher would make that tool responsible
for a write pattern (partial-field mutation of a third-party-owned file
format) its own architecture doesn't otherwise have, and would force every
consumer of `refresh_compliance_docs.py --release-audit` (which also runs
standalone at adopt Step H) to reason about manifest-sync failure modes
that have nothing to do with compliance evidence. A dedicated tool mirrors
the existing precedent instead: `aggregate_changelog.py` and
`aggregate_decisions.py` are already separate, single-purpose release-time
tools invoked as their own SKILL.md steps, each owning one artifact
family.
