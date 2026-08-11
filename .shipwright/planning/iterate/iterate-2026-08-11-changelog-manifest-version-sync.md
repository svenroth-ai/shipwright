# Iterate Spec: changelog-manifest-version-sync

- **Run ID:** iterate-2026-08-11-changelog-manifest-version-sync
- **Type:** change
- **Complexity:** medium (escalated from classifier's `small` — see SKILL.md
  §F summary in the run transcript: new release-gating mechanism, new shared
  tool, SKILL.md contract change, tests across 4 scenarios)
- **Status:** implemented

## Goal

`/shipwright-changelog` tags and publishes a release without ever writing the
released version into any published package manifest, so a release can cut
`v0.24.0`, tag it, and still ship whatever version was last written into
`bootstrapper/package.json` (measured on shipwright-webui 2026-08-10:
CHANGELOG.md/tag said `0.24.0`, `bootstrapper/package.json` still said
`0.23.0` — the version npm would actually receive). Let the project declare
which manifests are published (config, not a hardcoded path), write the
released version into each declared manifest in the same release commit, and
verify after write — failing closed (stop before tagging) if any declared
manifest does not match. A project with none declared is a clean no-op.

## Acceptance Criteria

- [x] A project can declare zero or more published manifests via
  `shipwright_changelog_config.json` (`published_manifests: [{path, format}]`).
  No file / no entries → the sync step is a no-op, nothing written, nothing
  verified, release proceeds exactly as today.
- [x] For each declared manifest, a new Step 5.4 writes the released version
  into it (format `package_json` → `version` field) and **stages exactly
  those paths itself** (tool-owned `git add`, mirroring Step 5.5's
  `--stage`/`evidence_pathspec` contract) — never a hand-assembled pathspec
  in markdown prose, since that is a silent-omission footgun the review
  caught: an agent that forgets one path gets `status: ok` while the commit
  ships without the manifest.
- [x] After the release commit exists, a **verify-commit** pass re-reads
  every declared manifest from the **committed git blob** (`git show
  <sha>:<path>`), not the worktree, and confirms its version equals the
  released version. Any mismatch **stops the release before `git tag`** —
  chained with `&&` immediately before the tag command, mirroring
  `refresh_compliance_docs.py --verify-commit --release-audit && git tag`.
  Verifying the worktree alone is insufficient: nothing then stops the tag
  if the manifest write never made it into the commit. A manifest whose
  *committed* bytes are still at the previous version must fail the release
  — this is the regression case from the card, and it is only closed by
  checking the commit, not the working tree.
- [x] `--verify-commit` reads its manifest list from the **frozen result
  Step 5.4 wrote** (`--result-file`), never by re-reading
  `shipwright_changelog_config.json` again — the live config file is
  mutable worktree state; re-deriving scope from it after the commit would
  let an edited, removed, or never-committed config silently change (or
  empty) what gets verified (Branch A external review, openai finding #2 —
  the second high-severity gap, alongside symlink staging).
- [x] `--verify-commit` trusts the frozen `--result-file` only after
  confirming it actually recorded a successful, current-release sync: a
  file whose own recorded `status` isn't `"ok"` (a failed Step 5.4 run —
  the file is written unconditionally, including on failure) or whose
  recorded `version` doesn't match the release being verified (a leftover
  from a *different*, earlier release at the same fixed, non-run-scoped
  path) is refused, never read for its manifest list — otherwise a
  failed-then-resumed release or a stale file recreates the card's
  regression inside the gate's own state file (Stage 2 code-review,
  finding #1, high — found after all five prior review passes).
- [x] A **standing detective check**, `check_manifest_version_matches_tag`,
  is added to `changelog_checks.py` / `run_changelog_checks` (same home as
  the existing `check_changelog_version_matches_tag` /
  `check_git_tag_exists`) at **`WARNING`** severity (not `ERROR` —
  descoped in Architecture Review reconciliation: the pre-tag gate is
  what's release-blocking; this check's job is only to surface drift the
  gate never saw — a release cut before this iterate shipped, or a later
  commit editing a manifest by hand — without permanently foreclosing an
  intentional post-release manifest edit). No-op when no manifests are
  declared.
- [x] Declaring a manifest whose file does not exist on disk is a distinct,
  named failure (`manifest_missing`), never silently treated as "no
  manifests declared".
- [x] A declared `path` is **contained to the project root** after resolving
  symlinks: an absolute path or a `..` escape is refused (`path_outside_project`).
  **Any symlink at all in the path — internal or escaping — is refused**
  (`path_is_symlink`), not just external ones: `git add` stages the symlink
  entry, not the resolved target's changed blob, so an in-root symlink would
  let the write and the staged/committed content silently diverge (Branch A
  external review, openai finding #1). `published_manifests` is
  project-authored config, but `/shipwright-adopt` runs against untrusted
  brownfield repos, so path containment is not optional.
- [x] `shipwright_changelog_config.json` itself gets shape validation before
  anything else runs: malformed JSON, a non-array `published_manifests`,
  a non-object entry, or a missing/non-string `path` is a named failure
  (`invalid_config`), and two declared entries that canonicalize to the same
  file (aliases like `a/package.json` vs `./a/package.json`) is
  `duplicate_manifest_path` — both fail closed before any manifest is
  touched (Branch A external review, openai finding #4).
- [x] Every declared manifest path is **checked for pre-existing dirty state**
  (`git status --porcelain -- <path>`) before this tool writes to it. A
  manifest that already has uncommitted changes when the sync starts fails
  closed (`manifest_dirty_before_sync`) rather than silently folding
  unrelated edits into the release commit via `--stage` (Branch A external
  review, openai finding #3).
- [x] A manifest whose top-level JSON has a **duplicate `"version"` key**
  is a named failure (`ambiguous_manifest_structure`), never a guessed
  surgical rewrite or a silent `json.dump` collapse to one of the two
  values (Branch A external review, openai finding #5).
- [x] The two-phase rollback (see below) also **covers a `git add` staging
  failure** after writes succeeded, not just a write failure — restoring
  already-written manifests' bytes either way, with its own status
  (`stage_failed`) (Branch A external review, openai finding #6).
- [x] The standing check reads each manifest's version from the **`HEAD`
  git blob**, never the worktree, and reuses the sync tool's own manifest
  parsing helper rather than a second, independently-maintained reader
  (Branch A external review, openai finding #7).
- [x] Git subprocess calls use `--` path separators and no shell, so a
  declared path beginning with `-` can't be misread as a flag (Branch A
  external review, openai finding #8, low-cost hardening).
- [x] The surgical-substitution regex **escapes the current version value**
  (`re.escape`) before building its match pattern — semver's `.`/`-`/`+`
  are regex metacharacters, and an unescaped pattern could report a false
  "unique match" (Branch A external review, deepseek finding #9 — treated
  as a correctness bug in the exactness the surgical path exists to
  provide, fixed regardless of the tool's own severity label).
- [x] `--verify-commit`'s `git show <sha>:<path>` resolves the path relative
  to the actual git root (via `git rev-parse --show-prefix`), not assumed
  equal to `--project-root` — correct even when a project's root is a
  subdirectory of its git repository (Branch A external review, deepseek
  finding #10).
- [x] `--version` is validated (bare semver, no leading `v`, no
  whitespace/control characters) **before any write** — the same string
  reaches the manifest, the verify-commit comparison, and (with `v`
  prepended) the git tag, so a malformed operator-typed version must be
  rejected up front rather than silently written into a manifest and then
  "verified" against itself.
- [x] `package_json` is the only format implemented (measured case). An
  unrecognized `format` value in config is a named failure
  (`unsupported_format`), not a silent skip.
- [x] Within `package_json`, three edge cases are named failures, not
  silent no-ops or crashes: no `version` key present (`missing_version_field`
  — never inject one, e.g. a `"private": true` workspace root), `version`
  present but not a string (`invalid_version_type`), and unparseable JSON
  (`parse_error` — the tool still emits well-formed JSON on stdout so the
  skill's `status`-field read never itself throws).
- [x] The **multi-manifest write is two-phase**: every declared entry is
  validated (containment, existence, parseable, correct format, `version`
  field present-and-a-string) before any manifest is touched; only then are
  all writes performed. If a write still fails mid-sequence, every manifest
  already written in this pass is restored to its original bytes — a
  half-synced worktree is strictly worse than one release-time failure that
  touched nothing.
- [x] Re-running an already-tagged release (manifest already at the released
  version) is a **success**, not indistinguishable from a first run: the
  tool reports `changed: false` per already-current manifest, performs no
  write, and verify-commit still passes — mirroring
  `aggregate_changelog.py`'s `changelog_updated: false` / `section_action:
  "unchanged"` convention.
- [x] The write is a **surgical single-value substitution** (locate and
  replace only the `"version": "<old>"` text span, falling back to a full
  `json.dump` re-render — flagged `reformatted: true` in the result — only
  when the surgical match can't be made unambiguously), not an unconditional
  whole-file `json.dump` re-render: reformatting an entire third-party
  manifest on every release turns it into a merge/diff-noise magnet on a
  file the project may format its own way.
- [x] `package-lock.json` / other lockfiles are **explicitly out of scope**
  and named as a known limitation in `manifest-sync.md` — not silently
  unhandled. Syncing them is real scope creep beyond "package.json, the
  measured case" and belongs to a follow-up if it is ever needed.
- [x] Publishing itself (whether/when/how the package reaches npm, the
  missing `npm publish` workflow / `NPM_TOKEN`) is explicitly out of scope —
  this card is only about the version being correct when a release ships.

## Spec Impact

- **Classification:** modify
- **MODIFY:** FR-01.09 — append one acceptance-criterion block: the release
  phase also keeps every project-declared published-package manifest's
  version in lock-step with the release it tags, and fails closed rather than
  tagging over a manifest left at the previous version. This completes the
  existing "tag the release" guarantee (a tag is currently allowed to
  describe a package that was not actually re-versioned) rather than adding
  a capability the phase did not already claim to provide.
- **ADD:** none
- **REMOVE:** none

## Out of Scope

- Actually publishing to npm (`npm publish`, `NPM_TOKEN`) — separate operator
  task, tracked by the operator per the card.
- A generic version-rewriting engine for manifest formats no project in this
  repo or shipwright-webui actually has (Cargo.toml, pyproject.toml, gemspec,
  …). Only `package_json` is built; an unsupported format fails closed and
  names itself rather than being silently ignored.
- Rewriting `bootstrapper/package.json` itself — that lives in the
  shipwright-webui repo, not here. This iterate ships the mechanism in
  `plugins/shipwright-changelog`; wiring shipwright-webui's own
  `shipwright_changelog_config.json` to declare that manifest is a follow-up
  in that repo, out of this diff's reach.

## Design Notes

n/a — no UI surface; this is a release-tooling change (Python script + a
SKILL.md step + config).

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| operator (hand-authors) | `sync_release_manifests.py` (new, `shared/scripts/tools/`) | `shipwright_changelog_config.json` (JSON) |
| `sync_release_manifests.py` | npm / any manifest reader | `<declared manifest path>` (JSON, `package_json` format: `version` field) |
| `/shipwright-changelog` SKILL.md Step 5.4 | Step 6 (commit pathspec assembly) | tool's own JSON stdout (`manifest_pathspec`, `status`) |
| Step 6's `git commit` | `sync_release_manifests.py --verify-commit` | committed git blob (`git show <sha>:<path>`) — NOT the worktree; this is the pair that actually closes the card's regression, per Internal Plan Review finding #1 |
| `sync_release_manifests.py --verify-commit` | Step 6 (tag gate, `&&`-chained) | tool's own JSON stdout (`status: "ok" \| "manifest_missing" \| "unsupported_format" \| "verify_mismatch" \| "path_outside_project" \| "invalid_version_argument" \| "missing_version_field" \| "invalid_version_type" \| "parse_error"`) |
| `changelog_checks.py::check_manifest_version_matches_tag` (standing check, Step 7) | `run_changelog_checks` / `_validate_changelog()` | latest git tag vs. each declared manifest's committed version |

`touches_io_boundary` risk flag fires (new JSON producer/consumer pair) →
Boundary Probe required in Build TDD.

## Internal Plan Review

- **Ran:** yes
- **Reviewer:** `shipwright-plan:opus-plan-reviewer` (model: opus), over the
  iterate spec + mini-plan.
- **Summary:** "The problem framing, the fail-closed posture, and the
  package_json-only scoping are all right, but as planned the gate cannot
  deliver its headline guarantee: it verifies the worktree while the tag is
  cut from a commit whose pathspec is assembled by hand in markdown prose,
  so the original drift can recur with a green 'ok' in front of it. Fix
  that (verify the committed blob before `git tag`, let the tool stage its
  own paths, add a standing verifier check) plus path containment and the
  missing/absent-version-field cases, and the rest of the plan is sound."
- **Findings triage** (16 total: 5 high, 8 medium, 3 low):

  | # | Finding (short) | Severity | Disposition |
  |---|---|---|---|
  | 1 | Verify worktree ≠ verify commit — original drift can recur | high | **fix** — verify-commit against `git show <sha>:<path>`, chained `&&` before `git tag` |
  | 2 | Hand-assembled Step 6 pathspec is a silent-omission footgun | high | **fix** — tool owns its own `git add`, returns `manifest_pathspec` |
  | 3 | No standing detective check for manifest drift | high | **fix** — `check_manifest_version_matches_tag` added to `changelog_checks.py` |
  | 4 | No path containment on declared `path` (traversal/symlink) | high | **fix** — resolve + `is_relative_to(project_root)` post-symlink, own status `path_outside_project` |
  | 5 | `--version` never validated; verify compares against itself | medium (reviewer's `severity` field said medium; listed under the `high` bucket in the reviewer's own count by mistake — treated as high given it lets a malformed version through the gate silently) | **fix** — semver validation before any write |
  | 6 | Multi-manifest write isn't atomic despite the plan's own stated intent | medium | **fix** — two-phase validate-then-write, restore-on-mid-failure |
  | 7 | package_json edge cases (`no version key` / non-string / parse error) unhandled | medium | **fix** — three new named statuses, never inject a version key |
  | 8 | No idempotency story for re-running an already-tagged release | medium | **fix** — `changed: true/false` per manifest |
  | 9 | `package-lock.json` unaddressed | medium | **disclose** — named out of scope in `manifest-sync.md`; real scope creep beyond the measured `package.json` case, not silently unhandled |
  | 10 | Whole-file `json.dump` reformat churns third-party files | medium | **fix** — surgical single-value substitution, fallback flagged `reformatted: true` |
  | 11 | Alternative section weighed the wrong second option (staging/check, not just refresh_compliance_docs fold) | medium | **fix** — addressed by fixes 2 and 3 directly; alternative section left as-is (the fold-into-compliance-docs rejection itself still stands on its own merits) |
  | 12 | Spec/mini-plan disagree on test file location (two pytest roots) | medium | **fix** — corrected to `shared/scripts/tools/tests/` |
  | 13 | Crash-window between write and commit leaves a bumped, uncommitted manifest | low | **disclose** — documented recovery in `manifest-sync.md` (re-run, or `git checkout --`); the standing check (fix 3) catches an accidental later commit |
  | 14 | Dry-run has no test coverage; a self-negating mini-plan row | low | **fix** — dry-run test added; contradictory row deleted |
  | 15 | New config file needs a config-data-flow docs row, not just artifact-write | low | **fix** — folded into Task 5 (docs update) |
  | 16 | Step ordering: run manifest sync before Step 5.5, not between 5.5 and 6 | low (grouped with the staging fix) | **fix** — new step renumbered to **Step 5.4**, runs before Step 5.5 |

  No `severity: high` finding was declined or disclosed, so the
  single-session gate-catalog auto-default for
  `plan.internal-review-high-severity-declined` does not apply — proceeding
  straight to Branch A/B/C external review with the plan as revised above.

## External LLM Review (Branch A)

- **Ran:** yes — `external_review.py --mode iterate`, providers deepseek +
  openai via openrouter.
- **Verdicts:** deepseek=approve · openai=revise (no contradiction —
  verdicts within one step of each other per the tool's own comparability
  check).
- **Findings triage** (13 total: 2 high, 6 medium, 5 low — all from openai's
  "revise" plus deepseek's approve-with-notes):

  | # | Source | Finding (short) | Sev | Disposition |
  |---|---|---|---|---|
  | 1 | openai | In-root symlinked manifest path: write targets the resolved file, `git add` stages the symlink entry — worktree and staged blob can diverge | high | **fix** — reject ANY symlink in the manifest path (not just escapes); new status `path_is_symlink`, folded into the containment check |
  | 2 | openai | `--verify-commit` re-derives its manifest list from the live (mutable) config file instead of the frozen set Step 5.4 validated | high | **fix** — Step 5.4 writes its result to a run-scoped file; `--verify-commit` takes `--result-file`, never re-reads config |
  | 3 | openai | `--stage` stages declared paths unconditionally, including pre-existing unrelated edits to that file | medium | **fix** — pre-flight dirty check (`git status --porcelain -- <path>`) per declared path; dirty-before-sync is a new fail-closed status `manifest_dirty_before_sync` |
  | 4 | openai | No config-shape validation (malformed JSON, non-array, non-object entries, missing/non-string `path`, duplicate/aliased paths) | medium | **fix** — `invalid_config` status; canonicalize + reject duplicate canonical targets (`duplicate_manifest_path`) |
  | 5 | openai | Duplicate top-level `version` keys: JSON silently keeps the last, surgical regex could touch the wrong one | medium | **fix** — detect via `object_pairs_hook` duplicate count; fail closed (`ambiguous_manifest_structure`), never attempt a rewrite |
  | 6 | openai | Rollback only covers write failures, not a `git add` failure (index lock, FS error) after writes succeeded | medium | **fix** — extend restore-on-failure to cover staging too; distinct status `stage_failed` |
  | 7 | openai | Standing check's "current version" is underspecified — must read `HEAD`, not worktree, and must reuse the sync tool's own parsing, not a second weaker reader | medium | **fix** — check reads `git show HEAD:<path>`, imports the parsing helper from `sync_release_manifests.py` |
  | 8 | openai | Git subprocess calls need `--` path separators, no shell, safe handling of `-`-prefixed filenames | low | **fix** — cheap, applied throughout |
  | 9 | deepseek | Surgical-substitution regex uses the raw current-version string unescaped — semver's `.`/`-`/`+` are regex metacharacters, so the "unique match" check can be fooled | medium (deepseek called it medium; treated as high-priority-fix given it undermines the exactness the surgical path exists for) | **fix** — `re.escape(current_value)` before building the pattern |
  | 10 | deepseek | `--verify-commit`'s `git show <sha>:<path>` assumes `--project-root` is the git root; a monorepo subdirectory layout would resolve the wrong path | low | **fix** — resolve the git-relative path via `git rev-parse --show-prefix`, cheap and removes a real failure mode rather than just documenting around it |
  | 11 | deepseek | If bytes-restoration itself fails after a mid-sequence write failure, the worktree is left partially modified with no further automated recovery | low | **disclose** — documented in `manifest-sync.md`'s recovery section: manual `git checkout --` if restoration itself errors |
  | 12 | deepseek | Standing-check no-op path (no config file) needs an explicit enumerated test, not just an implied one | low | **fix** — already planned in mini-plan item 9's test list; confirmed explicit here |
  | 13 | deepseek | Abort between Step 5.4 and the commit leaves a bumped manifest that an operator could accidentally commit later; recovery note should be prominent | low | **fix** — folded into the same `manifest-sync.md` recovery section as #11, made a named subsection rather than a buried line |

  No high-severity finding was declined or disclosed — all fixed. Proceeding
  to build with the design above (final revision).

## Architecture Review

- **Brief:** `.shipwright/planning/iterate/iterate-2026-08-11-changelog-manifest-version-sync/architecture_brief.md`
- **Verdicts:** deepseek=revise · openai=revise (no contradiction — both
  land on the same alternative independently)
- **Smallest thing that would do (per reviewers):** a **read-only** pre-tag
  gate — fail the release if a declared manifest's version doesn't already
  match, leaving the operator to bump it by hand — rather than the plan's
  write/stage/verify mechanism. Both reviewers also separately questioned
  the standing detective check's value once a pre-tag gate exists.
- **Findings:**
  - openai (medium, proportionality): the standing check duplicates the
    pre-tag gate for new releases and permanently imposes "every declared
    manifest == latest tag" on ordinary post-release commits, foreclosing
    legitimate post-release manifest edits without special-case handling.
  - deepseek (high, proportionality + existence): the write/stage/rollback
    machinery (two-phase writes, surgical substitution, idempotency) is a
    large permanent subsystem to automate what a pre-tag read-only check
    would reduce to a one-line manual edit; the standing check alone
    "cannot prevent the mismatch, only report it after the tag already
    exists" and should not be the sole barrier.
- **Reconciliation:**
  - **Write mechanism: kept, not descoped.** The card that opened this
    iterate is explicit and enumerates the write as its own numbered scope
    item, independent of verification: *"Write the released version into
    each declared manifest as part of the SAME release commit, so tag and
    manifest cannot diverge by construction."* A read-only gate does not
    deliver that guarantee — it converts a silent failure into a blocked
    release, but the operator must still remember to hand-edit the exact
    manifest correctly before re-running, which is the same fallible step
    that produced the original drift (shipwright-webui's 0.23.0-vs-0.24.0
    gap was exactly a forgotten manual bump). The reviewers were shown the
    brief deliberately without this framing, per the architecture-review
    method — their "smallest thing" is a legitimate alternative in the
    abstract, but the operator's own scoping already chose "by
    construction" over "caught at the gate," with the reasoning stated.
    This is not declining the finding without engagement — see below.
  - **Standing check: descoped from a release-blocking `ERROR` to an
    informational `WARNING`.** The reviewers' proportionality objection is
    accepted on its merits for this specific piece: once the pre-tag gate
    exists, the check's only remaining job is catching drift the gate
    never saw (a release cut before this iterate shipped, or a later
    unrelated commit editing a manifest by hand) — exactly the gap
    Internal Plan Review finding #3 raised. It does not need to be a hard
    invariant on every commit to do that job; `WARNING` reports it for
    operator attention without foreclosing an intentional post-release
    manifest edit. This directly addresses openai's finding while still
    closing the internal review's gap, rather than picking one review over
    the other.

## External-Code-Review-Findings

`external_review.py --mode code`, run over the full staged diff
(`git diff --staged HEAD`, ~2700 lines across 17 files) at Step 8, before
F6. deepseek `degraded` (empty reply from the provider — not a finding,
a transport failure), openai `revise` (5 findings). Only one reviewer
answered; `contradiction.requires_resolution: true` for that reason alone
(not a disagreement between two verdicts) — treated as a normal completed
Branch A pass per the tool's own `degraded: false` top-level status
(only deepseek's individual leg failed, not the whole call).

| # | Source | Sev | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | high | SKILL.md Step 6 still requires the agent to expand `<every path from manifest_pathspec>` into `git commit -- <paths>` by hand — a transcription omission recreates the silent-omission mechanism the card exists to close | **disclosed, not restructured** — this mirrors the pre-existing `evidence_pathspec` convention already used for Step 5.5 in the same command, and (unlike a hand-assembled `git add`, which AC2 does forbid and which the tool now owns) an omitted manifest here is mechanically caught: `--verify-commit` reads the *committed* blob and fails `verify_mismatch`, blocking the tag — the exact backstop AC3 exists to provide. Rearchitecting Step 6 so the tool itself owns the commit is a larger change than this iterate's scope (the card's numbered items describe write+verify, not "own the commit"). Added an inline SKILL.md comment making the backstop explicit at the point of risk instead. |
| 2 | openai | medium | `_canonicalize` was lexical-only; `a/../package.json` and `package.json` alias past `duplicate_manifest_path` | accepted-and-fixed — `_canonicalize` now runs `posixpath.normpath` before building the dedup key; `test_duplicate_canonical_path_with_dotdot_segment_rejected` added |
| 3 | openai | medium | The no-manifests-declared early return omitted `manifest_pathspec` even when `--stage` was passed, though the mini-plan promised an empty list | accepted-and-fixed — `sync()` now returns `manifest_pathspec: []` on that path when `stage=True`; `test_sync_no_config_with_stage_reports_empty_pathspec` added |
| 4 | openai | medium | `validate_version`'s regex accepted non-SemVer strings with leading zeroes (`01.2.3`, `1.2.3-01`) | accepted-and-fixed — replaced with the canonical semver.org SemVer 2.0.0 regex (rejects leading zeroes in numeric major/minor/patch and numeric prerelease identifiers); `test_validate_version_rejects` extended with 5 new cases, `test_validate_version_accepts` extended with 2 valid-leading-zero-adjacent cases (`1.2.3-0`, `1.2.3-alpha0`) |
| 5 | openai | low | `_is_dirty` treated a failed `git status` as "not dirty", failing open for the one guard meant to be fail-closed | accepted-and-fixed, narrower than the raw suggestion — a git-status failure now fails closed EXCEPT specifically "not a git repository" (this tool's own unit tests deliberately exercise plain, non-git `tmp_path` fixtures; failing closed there would have broken 8 pre-existing tests for a case that isn't actually a dirty-state question). A simulated index-lock/damaged-repo failure (any *other* git error) now correctly fails closed; `test_dirty_check_failure_fails_closed` added, proven against the failure mode the finding actually describes |

Two additional notes surfaced by the internal `spec-reviewer` (Stage 1) during
the same pass, judged not to warrant a code change: (a) `read_text(encoding="utf-8")`
applies universal-newline translation, so a CRLF-checked-out manifest could be
rewritten LF-only while `reformatted` still reports `false` — narrow blast
radius (package.json is conventionally LF; `core.autocrlf` is the only path
that would surface it), left for `code-reviewer` (Stage 2) to weigh; (b) `sync()`'s
docstring overclaimed "never raises" — narrowed to state the one actual gap
(an OSError/UnicodeDecodeError from the preflight read escapes as a traceback,
non-zero exit either way) rather than adding a new named status for a failure
mode that has never been observed.

Re-verified after all four code fixes: `shared/scripts/tools/tests` (551
passed, 16 skipped, 2 deselected), `shared/scripts/tests` (463 passed, 2
skipped), `shared/tests/test_changelog_checks_manifest_sync.py` +
`test_verifiers_test_changelog_deploy.py` (32 passed), `uvx ruff@0.15.15
check` all green.

## Code Review (Stage 2)

`shipwright-build:code-reviewer` (model: opus), spawned after Stage 1
(`spec-reviewer`) PASSED. **Verdict: REQUEST CHANGES** — 1 high, 2 medium,
6 low. All fixed except two explicitly-disclosed lows.

| # | Sev | Finding (short) | Disposition |
|---|---|---|---|
| 1 | high | `verify_commit` trusted any `--result-file` unconditionally — never checked the recorded `status`/`version` it wrote itself. `main()` writes the result file even on a FAILED sync (every failure branch records `manifests: []`), at a fixed non-run-scoped path that persists across releases. A failed-then-resumed release, or a leftover file from a prior release, would make the pre-tag gate report `ok` with the no-manifests note — the card's own regression, recreated inside the gate's state file | **fix** — `verify_commit` now fails closed on `recorded["status"] != "ok"` (`sync_incomplete`) and on `recorded["version"] != version` (`result_file_stale`), both before trusting the manifest list; `test_verify_commit_rejects_a_failed_syncs_own_result_file`, `test_verify_commit_rejects_a_stale_prior_releases_result_file` added |
| 2 | medium | `_is_dirty`'s fail-closed carve-out matched the English substring `"not a git repository"` in git's stderr — git's messages are localizable and `git()` pins no `LC_ALL`, so on a localized git the carve-out never matches and the 8 unit tests using plain non-git `tmp_path` fixtures would fail | **fix** — repo-ness decided structurally via `git rev-parse --git-dir`'s exit code (new `_is_git_repo` helper), never by matching stderr text; existing tests unaffected (verified green) |
| 3 | medium | `test_surgical_substitution_escapes_regex_metacharacters` was vacuous — its decoy field (`"description"`) can never match the `"version":`-prefix-anchored pattern with OR without `re.escape`, so the test passed identically with the fix reverted. The ledger cited this test as closing Branch A deepseek finding #9; that evidence row was not actually testing the fix | **fix** — rewritten with a decoy that only an UNESCAPED pattern would additionally match (a nested `"version": "1x2x3"` field, same length as `"1.2.3"` with dots landing on the wildcard positions) — genuinely fails if `re.escape` is reverted |
| 4 | low | Surgical write not byte-preserving for CRLF manifests: `Path.read_text()` applies universal-newline translation, silently rewriting a CRLF-committed manifest LF-only while `reformatted: false` and `render_manifest_write`'s docstring claimed "every other byte" preserved | **fix** (Stage 1 flagged this as advisory-disclosure; Stage 2 judged the docstring's overclaim serious enough for a one-line fix) — `resolved.read_bytes().decode("utf-8")` instead of `read_text()`; docstring corrected to state the caller's responsibility |
| 5 | low | Dead/backwards code: `manifest_pathspec` list comprehension filtered on `is_file()` for paths that had just passed preflight AND were just written — unreachable, and if it ever did fire would silently drop a path already `git add`ed | **fix** — `list(paths)`, folded into the dry-run/stage consistency fix below |
| 6 | low | `manifest_pathspec` key presence inconsistent under `--dry-run --stage`: present (`[]`) on the no-manifests path, absent on the manifests-declared path — reintroducing the "caller reads a documented field, gets a KeyError" hazard Branch A finding #3 existed to close | **fix** — unified rule: the key is always present when `--stage` was requested, `[]` under `--dry-run`; `test_sync_dry_run_with_stage_reports_empty_pathspec` added |
| 7 | low | `git_relative_path()` shells out `git rev-parse --show-prefix` once per manifest in both `verify_commit`'s loop and the standing check's loop, for a value constant across the whole run | **disclosed, not fixed** — trivial today at 1-2 manifests per project (reviewer's own words); `shared/scripts/lib/manifest_sync_core.py` sits at 299/300 lines (see finding 9), and hoisting requires a new helper signature this file has no headroom to absorb without either a further trim or an ADR-exception baseline entry, which is disproportionate for a low-severity perf nit |
| 8 | low | Test comment stated the opposite of the code's actual ordering (`"entry a was never touched because b failed preflight first"` — a's own preflight succeeds first; a is untouched because the WRITE phase never starts) | **fix** — reworded |
| 9 | low | `manifest_sync_core.py` sits at exactly its 300-line source cap with zero headroom; reducibility review found no contract-complete reduction available | **disclosed** — recorded here per the reviewer's own request; the next toucher should plan a split or exception up front. (Finding 4's fix briefly pushed this file to 304 before two docstrings were tightened back to 299 — the margin is genuinely zero, not "currently fine") |

Two Stage-1 (`spec-reviewer`) notes-for-Stage-2 were explicitly re-judged
independently rather than assumed settled: the CRLF concern (finding 4
above) was upgraded from "disclose" to "fix" — Stage 2's read was that the
docstring's overclaim made disclosure insufficient once identified; the
"never raises" docstring narrowing was confirmed sufficient as already
landed (`sync()`'s claim is now accurate; the adjacent overclaim was in
`render_manifest_write`, fixed alongside the CRLF read).

Re-verified after all Stage-2 fixes: `shared/scripts/tools/tests` (554
passed, 16 skipped, 2 deselected), `shared/scripts/tests` (463 passed, 2
skipped), `shared/tests/test_changelog_checks_manifest_sync.py` +
`test_verifiers_test_changelog_deploy.py` (32 passed), `uvx ruff@0.15.15
check .` (full repo) all green. `manifest_sync_core.py` re-measured at 299
lines, `sync_release_manifests.py` at 294 — both under their 300-line cap.

## Doubt Review (Stage 3)

`shipwright-build:doubt-reviewer` (model: opus), fresh-context, biased to
DISPROVE. 8 doubts (1 high, 4 medium, 3 low) plus an explicit "could not
disprove" list covering the areas Stage 1/2 already exercised. Reviewer's
own priority guidance: "if you fix only two things, make them D1 and D5."
All 8 addressed — 6 with a code/doc fix, D1 with a reasoned rebuttal plus a
documented operator precondition (full fix is out of this card's scope).

| # | Sev | Doubt (short) | Disposition |
|---|---|---|---|
| D1 | high | Every no-config path reports `ok`/green across all three mechanisms (sync, verify-commit, standing check) with no independent cross-check — indistinguishable from "the operator's config is silently gitignored in this checkout" from "genuinely nothing to declare." Traced whether existing framework tooling (`gitignore_check.py`) already covers this: it only checks paths a plugin's own outputs generate (`generate_adoption_artifacts.py`'s `rel_outputs`), never an arbitrary hand-authored file like `shipwright_changelog_config.json` | **rebutted + documented** — the no-op-on-absent-config behavior is the card's own required design (small-complexity no-op requirement, independently reviewed at Stage 1/2/Architecture Review); full verification that a project's own config is tracked is explicitly Out of Scope. Added an operator-precondition note to `manifest-sync.md` ("Declaring published manifests"): confirm the config isn't gitignored (`git ls-files` / `git check-ignore`) before trusting a clean run as proof nothing needed syncing |
| D2 | medium | `sync()`'s `stage_failed` branch restores worktree bytes via `_restore()` but never unstages the index (`git reset`/`git restore --staged`) on a partial `git add` — and the one test covering this (`test_stage_failure_restores_written_bytes`) fully mocks `git`, so it can't detect a genuine partial-staging scenario either way. Empirically confirmed `git add -- <existing> <nonexistent>` fails atomically (nothing staged) for the one failure mode preflight can't already rule out (paths are confirmed to exist first) | **fix** — added `git(project_root, "reset", "-q", "--", *paths)` on `stage_failed`, before `_restore`, as defense-in-depth against any other partial-add failure (disk, permissions) preflight doesn't cover; strengthened the existing test to assert the reset call happens with the right pathspec; documented in `manifest-sync.md`'s Recovery section |
| D3 | medium | `verify_commit` hardened the CONTENT check (status/version) but not the SHAPE: `recorded.get(...)` on a non-dict `recorded` (`json.loads` parsing `[]`/`null`/a bare string) raises `AttributeError` — a traceback on stdout, violating the tool's own contract that stdout is always parseable JSON. Same gap for a non-list `manifests` field and a manifest entry missing `path`/`format` | **fix** — `verify_commit` now checks `isinstance(recorded, dict)`, `isinstance(manifests, list)`, and each entry's `path`/`format` are strings, all returning `result_file_invalid` before any attribute access that could raise; 4 new tests (`test_verify_commit_rejects_non_dict_result_file`, `test_verify_commit_rejects_non_list_manifests_field`, `test_verify_commit_rejects_malformed_manifest_entry`, plus the D6 dry-run test below) |
| D4 | medium | `resolve_contained_path`'s symlink guard uses `Path.is_symlink()`, which CPython only sets for `IO_REPARSE_TAG_SYMLINK` — NOT `IO_REPARSE_TAG_MOUNT_POINT` (NTFS junctions, `mklink /J`). A junction needs no admin/Developer Mode, unlike a real symlink, making it the *easier* escape to construct — and both existing symlink tests self-skip on the primary Windows dev machine (`PermissionError`), so this path had zero real coverage there | **fix** — added `_is_reparse_point()` (checks `st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT` via `lstat()`, no-ops on non-Windows) and OR'd it into the component-walk check; new `test_windows_junction_in_path_rejected` creates a real junction with `mklink /J` (no admin required) and confirms rejection — **passed** on this machine, unlike the two symlink tests it sits beside, which still self-skip |
| D5 | medium | SKILL.md Step 6's `git commit -- <paths>` is a separate bash statement whose exit code is discarded — the `&&` chain begins only at the NEXT line (`refresh_compliance_docs.py`). A failed/no-op commit (bloat pre-commit hook, empty pathspec, "nothing to commit") lets the script continue, `$(git rev-parse HEAD)` silently re-resolves to the PREVIOUS commit, and the verify-commit gate could pass against a commit that never received this release's changes — `git tag` firing over the wrong commit | **fix** — extended the `&&` chain to start at `git commit` itself, so a failed/no-op commit now halts before any of the verify/tag steps run |
| D6 | low | `--result-file` in `main()` is resolved relative to the process CWD, not `--project-root` (the two coincide in SKILL.md's own usage, but nothing enforces that for another caller); and a `--dry-run` sync writes a full `status: "ok"` result file that `verify_commit` doesn't distinguish from a real one | **fix** — `main()` now resolves a relative `--result-file` against `--project-root`; `verify_commit` rejects `recorded.get("dry_run")` truthy as `sync_incomplete`; `test_main_relative_result_file_resolves_against_project_root`, `test_verify_commit_rejects_dry_run_result_file` added; documented in `manifest-sync.md` |
| D7 | low | `manifest_sync_core.git()` used `text=True, encoding="utf-8"` with strict decode errors and no `timeout=`, unlike a sibling pattern elsewhere in the codebase; `changelog_checks._latest_git_version_tag` (pre-existing, newly load-bearing for this card's new standing check) had no `encoding=` at all, defaulting to locale-dependent decoding | **fix** — `git()` now passes `errors="replace", timeout=10`; both `subprocess.run` calls in `changelog_checks.py` (`_verify_tag_exists`, `_latest_git_version_tag`) hardened with `encoding="utf-8", errors="replace"` for consistency |
| D8 | low | `_is_dirty`'s fail-open carve-out for a non-git `--project-root` (returns "not dirty" immediately) is a real scope boundary, previously stated only in a docstring | **fix** — added to `manifest-sync.md`'s "What's out of scope" list: the dirty-check guard doesn't apply outside a git repo; `/shipwright-changelog` itself always runs in one, so this only matters for a caller outside that flow |

`manifest_sync_core.py` grew to 311 lines adding the junction check and
hardened `git()` (D4 + D7) — trimmed back to **294** by tightening the
`ManifestSyncError` and `resolve_contained_path` docstrings (the SemVer
comment was already tightened once in Stage 2); no baseline exception
needed. `sync_release_manifests.py` grew to 327 across D2/D3/D6 (defensive
reset, result-file shape checks, dry-run rejection, project-root-relative
resolution) — trimmed back to **299** by tightening docstrings/comments
throughout and inlining the single-use `_is_git_repo` helper into its one
caller; no baseline exception needed for either file.

Re-verified after all Stage-3 fixes: `shared/scripts/tests` (464 passed, 2
skipped — the new junction test **passed**, not skipped), `shared/scripts/
tools/tests` (559 passed, 16 skipped, 2 deselected),
`shared/tests/test_changelog_checks_manifest_sync.py` (6 passed), `uvx
ruff@0.15.15 check .` (full repo) all green.

## Confidence Calibration

- **Boundaries touched:** operator (hand-authors) → `shipwright_changelog_config.json`
  → `sync_release_manifests.py` → declared manifest files (JSON,
  `package_json` format) → npm/any manifest reader; `/shipwright-changelog`
  Step 5.4 → Step 6 (`manifest_pathspec`, `status` over process stdout/JSON)
  → committed git blob (`--verify-commit`) → `git tag` (fail-closed gate);
  `changelog_checks.py::check_manifest_version_matches_tag` (standing
  check) reading the same committed-blob boundary. `touches_io_boundary`
  fires (config JSON in, manifest JSON out).
- **Empirical probes run:**
  - Config-mutability probe (closes a real gap the review cascade itself
    did not catch): the design claims `--verify-commit` never re-reads
    `shipwright_changelog_config.json`, only Step 5.4's frozen
    `--result-file`. That claim was true by code inspection (`verify_commit()`
    has no import path to `load_declared_manifests`) but had **no empirical
    proof** — every existing git-integration test constructs the frozen
    result in-memory and never exercises a config edited or deleted
    *between* `sync()` and `verify_commit()`. Wrote
    `test_verify_commit_ignores_config_mutated_after_sync` (mutates the
    config to a different manifest, then deletes it entirely, before
    calling `verify_commit`) — **passed on first run, no finding**. This is
    the "yes, confident" trap the calibration phase exists to catch: the
    structural argument was correct, but it had not actually been run.
  - CLI exit-code probe (closes a second real gap): `/shipwright-changelog`
    Step 6 chains `sync_release_manifests.py --verify-commit ... &&
    git tag ...` — the entire fail-closed guarantee depends on `main()`
    returning a non-zero exit code on failure. Every prior test called
    `sync()`/`verify_commit()` as plain Python functions, bypassing
    `main()`, `argparse`, and the exit-code mapping entirely — the actual
    executable contract the shell `&&` chain relies on was untested. Wrote
    `test_main_exits_zero_on_ok_and_writes_result_file`,
    `test_main_exits_nonzero_on_failure`, and
    `test_main_verify_commit_requires_result_file` (asserts `SystemExit`
    code 2 from `parser.error`) — all passed on first run, no finding.
  - Two probes in a row found nothing (asymptote reached for these two
    dimensions) after the regression-test and symlink probes already run
    during Build (`test_verify_commit_catches_omitted_manifest_regression`,
    `test_in_root_symlink_also_rejected`) each found a real bug during
    design/review, not during this phase — consistent with the doc's own
    worked example shape (probes-that-find-bugs happen earlier, the
    calibration-phase probes close out the tail).
- **Test Completeness Ledger:**

  | Behavior | Status | Evidence |
  |---|---|---|
  | No config / empty `published_manifests` / absent key → clean no-op | tested | `test_no_config_file_is_no_op`, `test_empty_published_manifests_is_no_op`, `test_absent_published_manifests_key_is_no_op`, `test_sync_no_config_is_ok_noop`, `test_no_config_passes_as_noop` |
  | Single declared manifest is written + reported `changed: true` | tested | `test_sync_one_manifest_write` |
  | Several manifests, mixed already-current/needs-write | tested | `test_sync_several_manifests_mixed_initial_versions` |
  | Step 5.4 stages exactly its own written paths (`git add`, `manifest_pathspec`) | tested | `test_stage_returns_pathspec` |
  | `--verify-commit` reads the **committed blob**, passes when write landed in the commit | tested | `test_verify_commit_passes_when_write_landed_in_commit` |
  | **The regression itself**: manifest bumped in the worktree but omitted from the release commit → `verify-commit` fails, tag never cut | tested | `test_verify_commit_catches_omitted_manifest_regression` — the card's exact failure mode, proven closed |
  | `--verify-commit` never re-reads the (mutable) config, even if edited or deleted after `sync()` | tested | `test_verify_commit_ignores_config_mutated_after_sync` (calibration-phase probe) |
  | `--verify-commit` resolves the git-relative path when `--project-root` is a subdirectory of the git repo | tested | `test_verify_commit_resolves_subdirectory_project_root` |
  | Process exit code is 0 on `ok`, non-zero on any failure status (the `&&`-chain contract) | tested | `test_main_exits_zero_on_ok_and_writes_result_file`, `test_main_exits_nonzero_on_failure` (calibration-phase probe) |
  | `--verify-commit` without `--result-file` is a hard CLI usage error | tested | `test_main_verify_commit_requires_result_file` (calibration-phase probe) |
  | Standing check: no config → no-op; no releases yet → pass; matching manifest → pass | tested | `test_no_config_passes_as_noop`, `test_no_releases_yet_passes`, `test_matching_manifest_passes` |
  | Standing check: drifted manifest → `WARNING`, never `ERROR` | tested | `test_drifted_manifest_warns_not_errors` |
  | Standing check: declared manifest missing at `HEAD` → `WARNING` | tested | `test_declared_manifest_missing_at_head_warns` |
  | Standing check: malformed config → `WARNING`, never a crash | tested | `test_malformed_config_warns_not_errors` |
  | Declared file missing on disk → `manifest_missing`, distinct from no-manifests-declared | tested | `test_sync_missing_file_fails_closed` |
  | Path containment: absolute path, Windows drive path, `..` escape all rejected | tested | `test_absolute_path_rejected`, `test_windows_drive_path_rejected`, `test_dotdot_escape_rejected` |
  | Path containment: symlink escaping project root rejected | tested | `test_symlink_in_path_rejected` |
  | Path containment: **in-root** symlink also rejected (not just escapes) | tested | `test_in_root_symlink_also_rejected` — closes Branch A openai finding #1 |
  | Malformed config shape (bad JSON, non-array, non-object entry, missing/non-string path) → `invalid_config` | tested | `test_malformed_json_is_invalid_config`, `test_malformed_shape_is_invalid_config` (parametrized) |
  | Two declared entries that canonicalize to the same file → `duplicate_manifest_path` | tested | `test_duplicate_canonical_path_rejected`, `test_duplicate_canonical_path_with_dotdot_segment_rejected` (Branch A openai finding #2) |
  | No manifests declared but `--stage` passed → `manifest_pathspec: []`, not omitted | tested | `test_sync_no_config_with_stage_reports_empty_pathspec` (Branch A openai finding #3) |
  | `--version` rejects non-SemVer leading-zero forms (`01.2.3`, `1.2.3-01`), not just malformed shape | tested | `test_validate_version_rejects` (extended, Branch A openai finding #4) |
  | A `git status` failure other than "not a git repository" fails closed (index lock, damaged repo) | tested | `test_dirty_check_failure_fails_closed` (Branch A openai finding #5) |
  | Pre-existing dirty manifest before sync starts → `manifest_dirty_before_sync`, never folded into the release commit | tested | `test_manifest_dirty_before_sync_fails_closed` |
  | Duplicate top-level `"version"` key → `ambiguous_manifest_structure`, never a guessed rewrite | tested | `test_read_version_duplicate_top_level_key_rejected` |
  | A **nested** object's own `"version"` key is not mistaken for a root-level duplicate | tested | `test_read_version_nested_version_key_is_not_a_false_positive` — closes a false-positive risk found during design, not by an external reviewer |
  | `git add` staging failure after writes succeeded restores already-written bytes (`stage_failed`) | tested | `test_stage_failure_restores_written_bytes` |
  | `--version` validated before any write (rejects leading `v`, whitespace, non-semver) | tested | `test_validate_version_rejects` / `test_validate_version_accepts` (parametrized), `test_sync_invalid_version_argument_touches_nothing` |
  | Unrecognized `format` value → `unsupported_format`, not a silent skip | tested | `test_sync_unsupported_format_fails_closed`, `test_read_version_unsupported_format` |
  | `package_json` edge cases: missing `version` key, non-string `version`, unparseable JSON | tested | `test_sync_missing_version_field_fails_closed_disk_untouched`, `test_read_version_missing_key`, `test_read_version_non_string`, `test_read_version_parse_error` |
  | Two-phase write: all entries validated before any is touched; a later-failing entry leaves an earlier-validated one untouched | tested | `test_sync_missing_version_field_fails_closed_disk_untouched` (entry `a` untouched when entry `b` fails preflight) |
  | Mid-sequence write failure restores already-written manifests' bytes | tested | `test_sync_mid_sequence_write_failure_restores_earlier_manifests` |
  | Re-running an already-released version is a success with `changed: false`, no write | tested | `test_sync_idempotent_rerun_no_write` |
  | Surgical single-value substitution produces a minimal diff | tested | `test_surgical_substitution_minimal_diff` |
  | Surgical substitution escapes regex metacharacters in the current version (semver `.`/`-`/`+`) | tested | `test_surgical_substitution_escapes_regex_metacharacters` — closes Branch A deepseek finding #9 |
  | Ambiguous surgical match falls back to full re-render, flagged `reformatted: true` | tested | `test_surgical_substitution_ambiguous_falls_back_to_full_render` |
  | `--dry-run` reports without writing to disk | tested | `test_sync_dry_run_reports_without_writing` |
  | `--dry-run --stage` together still reports `manifest_pathspec` (as `[]`), never a missing key | tested | `test_sync_dry_run_with_stage_reports_empty_pathspec` (Stage 2 code-review finding #6) |
  | `--verify-commit` rejects a `--result-file` recording a FAILED sync's own output (`status != "ok"`) | tested | `test_verify_commit_rejects_a_failed_syncs_own_result_file` (Stage 2 code-review finding #1, high) |
  | `--verify-commit` rejects a `--result-file` left over from a DIFFERENT prior release (`version` mismatch) | tested | `test_verify_commit_rejects_a_stale_prior_releases_result_file` (Stage 2 code-review finding #1, high) |
  | `stage_failed` unstages the declared paths (`git reset`) as well as restoring worktree bytes | tested | `test_stage_failure_restores_written_bytes` (Stage 3 doubt-review D2) |
  | `--verify-commit` fails closed with `result_file_invalid`, not a traceback, on a non-object/non-list-shaped `--result-file` | tested | `test_verify_commit_rejects_non_dict_result_file`, `test_verify_commit_rejects_non_list_manifests_field` (Stage 3 doubt-review D3) |
  | `--verify-commit` fails closed on a malformed `manifests` entry (missing `path`/`format`) | tested | `test_verify_commit_rejects_malformed_manifest_entry` (Stage 3 doubt-review D3) |
  | Path containment: a Windows NTFS junction (`mklink /J`, not just a real symlink) is rejected | tested | `test_windows_junction_in_path_rejected` — closes Stage 3 doubt-review D4; passes (not skipped) on the primary Windows dev machine, unlike the two symlink tests beside it |
  | A relative `--result-file` resolves against `--project-root`, not the process CWD | tested | `test_main_relative_result_file_resolves_against_project_root` (Stage 3 doubt-review D6) |
  | `--verify-commit` rejects a `--result-file` recording a `--dry-run` sync (nothing was actually staged) | tested | `test_verify_commit_rejects_dry_run_result_file` (Stage 3 doubt-review D6) |
  | A project declaring a lockfile (`package-lock.json`, out of scope per `manifest-sync.md`) is rejected, not silently accepted | tested | `test_sync_unsupported_format_fails_closed` — `format` validation rejects any value other than `package_json`, which is the actual mechanism guarding the out-of-scope boundary |
  | No regression across the three affected pytest roots | tested | `shared/scripts/tools/tests`: 559 passed, 16 skipped, 2 deselected (full root); `shared/scripts/tests`: 464 passed, 2 skipped (full root); `shared/tests`: **9176 passed, 32 skipped, 20 deselected, 0 failed** (full root, 12m22s) |

  0 untested-testable, 0 untestable — publishing itself (`npm publish`,
  `NPM_TOKEN`) is a non-goal with no code in this diff touching it and is
  therefore not a row here at all, not an `untestable` disposition; every
  row that IS a behavior of what this diff built is `tested`.
- **Confidence-pattern check:** Asymptote (depth) — two probes run
  specifically for this phase (config-mutability, CLI exit-code) both
  passed on first execution with no finding, satisfying the "last probe
  found nothing" stopping condition; the bugs that *did* exist in this
  design (worktree-vs-commit verification, symlink staging mismatch,
  regex-metacharacter injection, duplicate-key false-positive) were each
  found and fixed earlier, during Internal Plan Review / Branch A external
  review / self-caught design review — consistent with the reference
  worked example, where probes cluster bug-finds early and the calibration
  phase's job is confirming the tail is actually clean, not finding new
  bugs from scratch. Coverage (breadth) — every AC bullet in this spec maps
  to a named tested/untestable row above; the ledger surfaced two real
  gaps (config-mutability, CLI exit-code) that all three review passes
  (internal, Branch A external ×2, architecture ×2) had missed, because
  none of them was asked to execute code — only to reason about the design.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run "shared/scripts/tools/sync_release_manifests.py" --project-root . --version 0.0.0-test --dry-run` against fixture projects (one manifest / several / none / stale / missing-file / bad-format / path-escape / re-run-idempotent) exercised by the shared tools' own pytest suite — no dev server, no browser surface exists for a release-time CLI tool.
- **Evidence path:** `shared/scripts/tools/tests/test_sync_release_manifests.py` pytest output (F0/F5 test run) — corrected from an earlier draft that named `plugins/shipwright-changelog/tests/`, a different pytest root than where the tool actually lives (caught in Internal Plan Review).
- **Justification (surface=cli, not web):** this is a release-time CLI tool invoked from a skill's markdown steps, not a web-facing feature; F0.5's web runner does not apply (no `dev_url`, no UI).
