# Iterate Spec: changelog-release-notes

- **Run ID:** iterate-2026-08-26-changelog-release-notes
- **Type:** feature
- **Complexity:** medium
- **Status:** draft

## Goal
`/shipwright-changelog` tags a release (`git tag -a v{version}`) and pushes it,
but never creates a GitHub Release — clicking the tag on GitHub shows only the
one-line tag-annotation commit message, never the CHANGELOG.md content. Add a
step that creates a GitHub Release for the tag, with a body condensed by an
LLM pass from the just-written CHANGELOG.md section into a short,
human-readable summary (Highlights / Features / Breaking Changes / Changed /
Fixed / Security), not a raw 400+-line dump of the CHANGELOG's dense
multi-sentence bullets.

## Acceptance Criteria
- [ ] After a release tag is pushed to origin, the released `CHANGELOG.md`
  section is read from the tagged git blob (`git show v{version}:CHANGELOG.md`)
  — not the worktree file — and a subagent condenses it into a release body
  (English, no emoji, structure: optional Highlights / Features / Breaking
  Changes / Changed / Fixed / Security, each present section omitted only
  when empty, ending with links to the released `CHANGELOG.md` — the tagged
  blob, not a computed in-page heading-anchor (a self-corrected design
  decision: GitHub's slug algorithm is easy to get subtly wrong and a wrong
  slug 404s silently, so the link goes to the whole file at that tag instead)
  — and the tag-compare view. The compare link's "previous version" is derived from git tags
  (`git tag --list 'v*' --sort=-v:refname`), never from CHANGELOG heading
  order, and is verified to resolve before being emitted.
- [ ] The condensation is produced by an LLM subagent call (judgment task —
  what is "breaking" vs "changed", compressing multi-sentence bullets to one
  sentence each) — not a mechanical/regex script.
- [ ] The condensed body is mechanically validated before publishing — non-
  empty, under a hard size cap comfortably below GitHub's ~125,000-char
  release-body limit, every `##` heading drawn from the fixed allowed
  vocabulary, the version string present, the two required trailing links
  present, `@mentions` and bare `#NNN` issue/PR references neutralized,
  Markdown image syntax rejected outright, and links restricted to this
  project's own repo host. A body that fails validation is NOT published —
  reported as `notes_failed_validation`, never silently swallowed.
- [ ] `gh release create v{version} --notes-file {path} --verify-tag` is used
  (never lets `gh` auto-create a tag at the branch tip if the push silently
  failed). Before creating, `gh release view v{version}` is checked first —
  an existing release is left alone and reported as `exists`, never treated
  as a failure.
- [ ] When the `gh` CLI is missing or unauthenticated (checked via
  `gh auth status --hostname github.com`), release creation is skipped
  without blocking `/shipwright-changelog`'s phase completion, and the skip
  is reported in the Step 7 summary banner (never silently swallowed).
- [ ] When `gh release create` itself fails (network error, etc.), the
  failure is reported in the same summary banner; the changelog phase still
  completes (the release page is best-effort, the tag is the source of
  truth).
- [ ] The NEXT release's setup script (`setup-changelog.py`) advisory-warns
  (never blocks) when the immediately preceding tag has no GitHub Release —
  so a silently-failed/skipped release-notes step surfaces once, at the next
  release, instead of rotting unnoticed for months.
- [ ] Existing tags (v0.1.0 .. v0.32.0) are explicitly out of scope — this
  applies going forward only, per operator decision (no backfill).

## Spec Impact
- **Classification:** modify
- **ADD** (new FR appended): none
- **MODIFY** (existing FR changed): FR-01.09 (`/shipwright-changelog`) —
  its first AC already promises "a release note a person can read ... is
  prepared, not merely described"; today that note is only ever committed to
  `CHANGELOG.md`, never surfaced where a person actually looks (the code
  host's release page). This iterate completes that existing promise rather
  than minting a new capability (MINT-vs-FOLD gate: FOLD).
- **REMOVE:** none
- **NONE justification:** n/a

## Out of Scope
- Backfilling GitHub Releases for the 40+ already-pushed tags (operator
  decision — forward-only).
- Any change to `CHANGELOG.md`'s own content, format, or the aggregation
  logic in `aggregate_changelog.py` — this iterate only reads the already-
  written section and republishes a condensed derivative of it to GitHub.
- Editing/backfilling release notes for a release that used `--from` replay
  or any non-standard changelog invocation shape.

## Design Notes
n/a — no UI surface. This is a CLI/skill-prose + shared-script change.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `aggregate_changelog.py` (Step 4, existing) | new `extract_changelog_section.py` (this iterate) | CHANGELOG.md Markdown section, keyed by `## [version]` heading, read from the tagged git blob |
| condensation subagent (this iterate) | `create_github_release.py` (this iterate) | Markdown release-notes file on disk (`--notes-file`), gated by the mechanical validator |
| `create_github_release.py` (this iterate) | GitHub Releases API (via `gh` CLI) | `gh release create --verify-tag` args/notes-file |

`touches_io_boundary` risk flag applies. Boundary Probe plan (per Internal
Plan Review finding 17): the aggregator→extractor pair gets a real
round-trip test (write a section via the aggregator's own renderer, extract
it back, assert byte-equality) using `shared/tests/_changelog_release_fixtures.py`.
The `create_github_release.py`→GitHub pair is unprobeable from CI by design
(never invoke a real `gh release create` from a test — see "Never run a
producer to verify it"); the standing substitute is an argv-shape assertion
(the exact command line built, incl. `--verify-tag` and safe version-string
handling) over a mocked subprocess call.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** high
- **Summary:** Concept and FOLD classification hold up, but the plan as drafted hard-stops on the SKILL.md bloat anti-ratchet (zero headroom), puts tests in a root with an ADR-045 import collision, and would publish unvalidated LLM output behind a `gh release create` that can silently create a divergent tag if the push failed.
- **Findings:** (1) SKILL.md bloat anti-ratchet zero headroom, high, fixed — write compactly + offset, or bump baseline with a fresh exception ADR if compaction is insufficient. (2) `gh release create` auto-creates a divergent tag if push failed, high, fixed — pass `--verify-tag` (confirmed real flag, `gh` 2.92.0). (3) No mechanical validation between LLM output and the public release page, high, fixed — add a validator (heading allowlist, size cap, required links, non-empty, neutralize mentions/refs, reject image markdown, link-host allowlist). (4) Tests planned into `plugins/shipwright-changelog/tests/` collide with ADR-045 (`lib`/`tools` namespace binding), high, fixed — move to `shared/tests/`, reuse `_changelog_release_fixtures.py`. (5) Read from worktree CHANGELOG.md is unlocked/not-necessarily-tagged content, medium, fixed — read `git show v{version}:CHANGELOG.md` instead. (6) Re-running a release maps to `{status:"failed"}` instead of a distinct `exists` state, medium, fixed — `gh release view` first. (7) Non-blocking failure surfaces only in a banner nobody re-reads, medium, fixed (lightly) — add an advisory note in the next release's setup script output when the previous tag has no release. (8) Prompt-injection / live-mention / image-beacon risk from untrusted CHANGELOG drop-file text, medium, fixed — prompt-level fencing + mechanical neutralization in the validator. (9) No size bound (GitHub ~125k char cap), medium, fixed — `MAX_SECTION_BYTES` + pre-publish size check. (10) Iterate spec's Verification runner command doesn't actually run pytest, medium, fixed — corrected to the real pytest invocation. (11) `shared/templates/` vs `shared/prompts/` contradiction for the prompt file's location, medium, fixed — moved to the skill's own `references/`. (12) Missing `update-marketplace.sh` + `check_plugin_cache_sync.py --strict` step, medium, fixed — added as an explicit post-push step. (13) FR-01.09 AC edit under-specified (append-only placement, tool-agnostic wording, AC shape), medium, fixed. (14) Test plan under-covers argv shape / aggregator↔extractor round-trip / exists-branch / validator / prompt-path drift, medium, fixed — added. (15) Compare-link previous-version derived from CHANGELOG heading order (insertion order, not semver) risks a 404, medium, fixed — derive from `git tag --list` instead. (16) Assorted low-severity gaps (guide.md, frontmatter line, `section_starts` len != 1, mkdir+UTF-8 write, `gh auth status --hostname`, version-argv-injection guard), fixed. (17) Boundary probe covered only 1 of 3 declared pairs, low, fixed — added the aggregator→extractor round-trip probe; documented the GitHub pair as unprobeable from CI with the argv-shape test as the standing substitute.
- **Known limitations:** none disclosed — every finding was integrated as a fix.
- **Status:** 17 fixed

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-08-26-changelog-release-notes/architecture_brief.md`
- **Verdicts:** deepseek=revise (severity: high) · openai=revise (severity: medium)
- **Smallest thing that would do (per reviewers):** Option B — publish the tagged `CHANGELOG.md` section verbatim as the release body (`git show v{version}:CHANGELOG.md` → extract section → `gh release create --notes-file --verify-tag`), dropping the LLM condensation, the prompt, the vocabulary allowlist, and the anti-injection validation surface entirely.
- **Findings:** Both reviewers independently argue the LLM condensation is a disproportionate, permanently-maintained "second editorial pipeline" solving a problem ("release page has no content") that a deterministic verbatim-republish already solves, and that most of the validator's surface (mention/reference neutralization, image rejection, link-host allowlist) exists only to guard against a risk the LLM step itself introduces.
- **Reconciliation:** Operator asked to STOP-and-decide (deepseek's finding was severity: high). Decision: **keep the plan** — the LLM condensation stays, Option B (verbatim republish) is declined. Two things settle it, both stated by the operator and both already true of the design: (1) the raw `CHANGELOG.md` section is never lost — every condensed body ends with a link straight to that version's full section, one click from the release page; (2) the reviewers' implicit concern (an LLM writing unchecked to a public page) is already the exact problem the plan's own Round-2 revision solved, independently of this architecture pass — `validate_release_notes.py` is a deterministic generate-then-gate validator (fixed heading vocabulary, size cap, required links, mention/reference neutralization, image/external-link rejection) in front of a tool-less, no-side-effect completion call, which is the standard pattern for any LLM output reaching a public surface (the same shape as a lint/test gate on generated code). The reviewers' own prior-art example (`release-please`/`semantic-release`, fully mechanical) was the alternative already discarded earlier in this conversation once the operator read the real 454-line raw section for v0.32.0 and judged it unreadable as a release page. Nothing in either reviewer's finding survives past that point undiscovered — the objection is answered by what the plan already contains, not by new work.

## Confidence Calibration

- **Boundaries touched:** the three pairs in `## Affected Boundaries` above —
  aggregator → extractor (CHANGELOG.md section), condensation → create-release
  (release-notes file on disk, gated by the mechanical validator), and
  create-release → GitHub Releases API (`gh` CLI).
- **Empirical probes run:**
  - `test_aggregator_extractor_round_trip` — writes a versioned section via
    the real `aggregate_changelog._render_versioned_section`, commits+tags it,
    extracts it back, asserts byte-equality. Not a re-read of the diff — a
    real producer/consumer round trip.
  - `test_call_carries_no_tool_definitions` — asserts the condensation
    completion call's kwargs carry no `tools`/`functions` key, i.e. the
    prompt-injection defense is structural, not merely documented.
  - `test_extract_previous_tag_not_on_remote_is_omitted` — a tag pushed
    locally but never to `origin` (a real failure mode: `git push` without
    `--tags`) must not produce a compare link that 404s; probed against a
    real local bare "origin", not a mock.
  - `test_success_argv_shape` (`create_github_release.py`) — the exact argv
    `gh release create` receives, asserting `--verify-tag` is present and no
    stray flag can slip in from an unsanitized version string.
  - `test_urls_never_guess_a_heading_anchor` — a self-caught design flaw
    (computing a GitHub heading-anchor slug is easy to get subtly wrong and
    fails silently); probes that the shipped code links the tagged blob
    instead, never a slug.
  - `test_rejects_invalid_version` — a version string starting with `-`
    cannot be smuggled into `gh`'s argv as a flag.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | Normalize supported GitHub origin URL forms (ssh/https, `.git` suffix, trailing slash) | tested | `test_normalize_github_origin` |
  | 2 | Reject a non-GitHub or malformed origin URL | tested | `test_normalize_github_origin` |
  | 3 | Resolve repo identity from a real git remote | tested | `test_resolve_repo_identity_reads_git_remote` |
  | 4 | No remote configured resolves to `None` | tested | `test_resolve_repo_identity_no_remote_returns_none` |
  | 5 | Extract the section for an existing tagged version | tested | `test_extract_section_present` |
  | 6 | Tag exists but its CHANGELOG carries no heading for it | tested | `test_extract_section_absent_raises` |
  | 7 | Ambiguous (duplicate) version heading refuses rather than guesses | tested | `test_extract_section_ambiguous_raises` |
  | 8 | Version tag itself doesn't exist / isn't pushed | tested | `test_extract_missing_tag_raises` |
  | 9 | Previous-version resolution is semver-aware, not string-sorted (`v0.10.0` > `v0.9.0`) | tested | `test_extract_previous_version_semver_ordering` |
  | 10 | A previous tag never pushed to origin is omitted from the compare link | tested | `test_extract_previous_tag_not_on_remote_is_omitted` |
  | 11 | Non-semver tag noise is ignored when picking the previous version | tested | `test_extract_ignores_non_semver_tag_noise` |
  | 12 | Oversized section is refused, never silently truncated | tested | `test_extract_oversized_section_refused` |
  | 13 | Round-trip byte-equality against the real aggregator's own rendering | tested | `test_aggregator_extractor_round_trip` |
  | 14 | No API key configured skips condensation without raising | tested | `test_no_api_key_skips` |
  | 15 | Successful completion returns condensed text | tested | `test_openrouter_success` |
  | 16 | Empty completion is reported as an error, never published | tested | `test_empty_completion_reports_error` |
  | 17 | A provider exception is caught and reported, never raised | tested | `test_provider_exception_reports_error_not_raise` |
  | 18 | The completion call carries no `tools`/`functions` definitions | tested | `test_call_carries_no_tool_definitions` |
  | 19 | The condensation prompt file exists and keeps its required section-heading markers | tested | `test_release_notes_prompt_file_exists_with_required_markers` |
  | 20 | A well-formed condensed body passes and its sanitized form carries the footer | tested | `test_happy_path` |
  | 21 | Empty body fails validation | tested | `test_empty_body_fails` |
  | 22 | Oversized body fails validation | tested | `test_oversized_body_fails` |
  | 23 | A heading outside the fixed vocabulary fails validation | tested | `test_bad_heading_fails` |
  | 24 | Footer missing the version string fails validation | tested | `test_missing_version_string_fails` |
  | 25 | First release (no previous tag) passes without a compare link | tested | `test_first_release_no_compare_link_passes` |
  | 26 | A normal release's sanitized body carries the compare link | tested | `test_normal_release_footer_carries_compare_link` |
  | 27 | Unsafe URL forms (image, autolink, raw `<img>`/`<a>`, bare URL) are rejected | tested | `test_rejects_unsafe_url_forms` (5 cases) |
  | 28 | A link to a host other than the repo's own is rejected | tested | `test_rejects_external_link_host` |
  | 29 | A link to the repo's own host is allowed | tested | `test_allows_own_repo_link` |
  | 30 | `@mentions` are neutralized (backtick-wrapped) in the sanitized output | tested | `test_neutralizes_mention` |
  | 31 | `#NNN` issue/PR references are neutralized in the sanitized output | tested | `test_neutralizes_issue_ref` |
  | 32 | `gh` not installed skips release creation | tested | `test_skips_when_gh_not_found` |
  | 33 | `gh` below the `--verify-tag` minimum version skips | tested | `test_skips_when_gh_version_too_old` |
  | 34 | Unauthenticated `gh` skips | tested | `test_skips_when_unauthenticated` |
  | 35 | A malformed version string is rejected before it reaches `gh`'s argv | tested | `test_rejects_invalid_version` |
  | 36 | Unresolved repo identity skips | tested | `test_skips_when_repo_identity_unresolved` |
  | 37 | An already-existing release reports `exists`, never attempts create | tested | `test_reports_exists_without_creating` |
  | 38 | An indeterminate `gh release view` failure reports `failed`, never falls through to create | tested | `test_view_failure_reports_failed_not_create` |
  | 39 | A successful create's exact argv shape (`--verify-tag`, `--repo`, no stray flags) | tested | `test_success_argv_shape` |
  | 40 | A `gh release create` failure is reported, never swallowed | tested | `test_create_failure_reported` |
  | 41 | Orchestrator: an extract failure stops the chain before condense is called | tested | `test_extract_failure_reported_and_stops` |
  | 42 | Orchestrator: a condensation failure stops the chain before repo-identity/create | tested | `test_condensation_failure_reported_and_stops` |
  | 43 | Orchestrator: unresolved repo identity is reported as a condensation-stage failure | tested | `test_unresolved_repo_identity_reported` |
  | 44 | Orchestrator: a validation failure stops the chain before create is called | tested | `test_validation_failure_reported_and_stops` |
  | 45 | Orchestrator: the full success path writes the sanitized body to disk and calls create with it | tested | `test_success_writes_sanitized_body_and_calls_create` |
  | 46 | Orchestrator: a first release (no previous tag) omits the compare link from the written body | tested | `test_first_release_has_no_compare_link` |
  | 47 | Orchestrator: the CHANGELOG link is always the tagged blob URL, never a computed heading-anchor slug | tested | `test_urls_never_guess_a_heading_anchor` |
  | 48 | Orchestrator's footer construction matches `validate_release_notes`'s own contract | tested | `test_validate_expected_footer_used_consistently` |
  | 49 | Advisory check: no previous tag is not applicable (`None`), never blocks | tested | `test_no_previous_tag_is_not_applicable` |
  | 50 | Advisory check: `gh` unavailable is indeterminate (`None`) | tested | `test_gh_missing_is_indeterminate` |
  | 51 | Advisory check: previous tag has a release (`True`) | tested | `test_release_found_is_true` |
  | 52 | Advisory check: previous tag confirmed to have no release (`False`) — the only state that prints a notice | tested | `test_release_not_found_is_false` |
  | 53 | Advisory check: an indeterminate `gh` failure is `None`, never misreported as `False` | tested | `test_indeterminate_gh_failure_is_none` |
  | 54 | Advisory check: unresolved repo identity is `None` | tested | `test_unresolved_repo_identity_is_none` |
  | 55 | `create_github_release.py`→GitHub Releases API pair (real network call) | untestable | `requires-external-nondeterministic-service` — never invoke a real producer to verify it; substituted by the argv-shape probe (row 39) per boundary-probe plan above |
  | 56 | Extraction succeeds even when the WHOLE tagged file exceeds the section-size cap (external code review found this as a live, release-blocking bug on this repo's own 450KB+ CHANGELOG.md) | tested | `test_extract_succeeds_when_whole_file_exceeds_the_section_cap` |
  | 57 | Link-host check rejects a repo whose name merely starts with ours (`widgets-archive` vs `widgets`) | tested | `test_rejects_link_to_a_repo_whose_name_merely_starts_with_ours` |
  | 58 | Mention/issue-ref neutralization does not break an existing inline code span open | tested | `test_neutralizes_mention_without_breaking_an_existing_code_span` |
  | 59 | Mention/issue-ref neutralization still fires for a mention next to (not inside) a code span | tested | `test_neutralizes_a_mention_that_sits_right_next_to_a_code_span` |
  | 60 | Body containing an emoji is rejected | tested | `test_rejects_emoji` |
  | 61 | A heading with no content before the next heading is rejected | tested | `test_rejects_a_heading_with_no_content` |
  | 62 | An empty LAST heading is rejected even once the footer is appended (the empty-section check must scope to the pre-footer body, not body+footer — a second-order bug in the row-61 fix, caught by code-reviewer) | tested | `test_rejects_an_empty_last_heading_even_with_the_footer_appended` |
  | 63 | Orchestrator reports a failed status (never crashes) when the prompt file is unreadable | tested | `test_prompt_read_failure_reported_and_stops` |
  | 64 | Orchestrator reports a failed status (never crashes) when writing the notes file fails (read-only FS, disk full) | tested | `test_notes_write_failure_reported_and_stops` |
  | 65 | `normalize_github_origin` recognizes the `ssh://git@github.com/owner/repo` URI form, not just SCP-style SSH | tested | `test_normalize_github_origin` |
  | 66 | A non-H2 ATX heading (`#`, `###`+) cannot smuggle unauthorized text past the vocabulary/empty-section gate — the narrow exact-`## ` scan missed every other legal heading level (doubt-reviewer HIGH finding, confirmed live by hand-tracing before the fix) | tested | `test_rejects_a_non_h2_atx_heading` (3 cases) |
  | 67 | A 1-3-space-indented `## ` heading outside the allowed vocabulary is still rejected (indentation alone was never the bypass — the unchecked heading level was) | tested | `test_rejects_an_indented_h2_heading_outside_the_vocabulary` |
  | 68 | A 1-3-space-indented `## ` heading using an allowed name still passes | tested | `test_allows_an_indented_h2_heading_inside_the_vocabulary` |
  | 69 | Orchestrator: `_PROMPT_PATH` resolves to a real file on disk, not just a mocked one (doubt-reviewer LOW finding — every other test mocks `Path.is_file`, so a future rename of `release-notes-prompt.md` would silently degrade condensation to `skipped` forever without ever failing a test) | tested | `test_prompt_path_resolves_to_a_real_file` |
  | 70 | `_detect_provider` prefers `openrouter` when both keys are set, falls back to `direct` when only `OPENAI_API_KEY` is set | tested | `test_detect_provider_prefers_openrouter_over_direct`, `test_detect_provider_falls_back_to_direct` |
  | 71 | The direct-OpenAI provider path (success / empty completion / provider exception) mirrors the openrouter path's behavior | tested | `test_direct_provider_success`, `test_direct_provider_empty_completion_reports_error`, `test_direct_provider_exception_reports_error_not_raise` |
  | 72 | A missing `openai` package is a reported provider error, not an uncaught `ImportError` | tested | `test_openrouter_reports_missing_package_as_error` |
  | 73 | `condense_release_notes.py`'s own CLI (`main`) reports a missing section/prompt file and prints the condense result on success | tested | `test_main_reports_missing_section_file`, `test_main_reports_missing_prompt_file`, `test_main_success_prints_condense_result` |
  | 74 | `_gh_version`/`_gh_authenticated` parse a real `gh` CLI reply, tolerate an unparseable version string, a nonzero exit, and the subprocess call itself raising | tested | `test_gh_version_parses_real_output`, `test_gh_version_none_when_output_unparseable`, `test_gh_version_none_on_nonzero_exit`, `test_gh_version_none_when_run_raises`, `test_gh_authenticated_true_and_false`, `test_gh_authenticated_false_when_run_raises` |
  | 75 | `_release_view` reports indeterminate when the `gh` call itself raises, and tolerates non-JSON stdout on a found release | tested | `test_release_view_indeterminate_when_run_raises`, `test_release_view_tolerates_non_json_stdout` |
  | 76 | A missing notes file, and the `gh release create` call itself raising, are both reported as `failed` | tested | `test_missing_notes_file_reports_failed`, `test_create_call_raises_reports_failed` |
  | 77 | `create_github_release.py`'s own CLI (`main`) prints the create-release result | tested | `test_main_prints_json_result` |
  | 78 | `_git`'s own OSError/TimeoutExpired branch, and `_remote_has_tag` treating a real (unmocked) failing `git ls-remote` — no `origin` remote configured — as `False` rather than raising | tested | `test_git_helper_raises_when_subprocess_itself_fails`, `test_remote_has_tag_false_when_git_command_itself_fails` |
  | 79 | `extract_changelog_section.py`'s own CLI (`main`) reports an extraction failure as exit 1 with a JSON error, and prints the extracted section on success | tested | `test_main_prints_error_json_and_exits_1_when_extraction_fails`, `test_main_prints_ok_json_on_success` |
  | 80 | A relative in-page anchor link (`[text](#section)`) is always allowed, never reaching the host allowlist | tested | `test_allows_a_relative_in_page_anchor_link` |
  | 81 | `validate_release_notes.py`'s own CLI (`main`) reports a missing body file, writes the sanitized body to `--out-file` only on success, and never writes it on a validation failure | tested | `test_main_reports_missing_body_file`, `test_main_writes_sanitized_body_on_success`, `test_main_does_not_write_out_file_on_failure` |
  | 82 | The orchestrator reports a missing (not just unreadable) prompt file, and `publish_release_notes.py`'s own CLI (`main`) prints the `publish()` result | tested | `test_prompt_missing_reported_and_stops`, `test_main_prints_publish_result` |
  | 83 | `resolve_repo_identity` returns `None` when the `git remote get-url` call itself raises (not just a nonzero exit) | tested | `test_resolve_repo_identity_none_when_git_itself_fails` |
  | 84 | Advisory check: `gh --version`'s own nonzero exit, and the `gh release view` call itself raising, are both indeterminate | tested | `test_gh_version_nonzero_exit_is_indeterminate`, `test_gh_release_view_raising_is_indeterminate` |

  0 untested-testable rows.
- **Confidence-pattern check:** no "are you confident?"-style question was
  asked and answered "yes" only to be contradicted afterward — this run never
  claimed confidence before the review cascade ran. The review cascade
  (external LLM code review + Stage 2 code-reviewer + Stage 3 doubt-reviewer)
  DID surface 11 real findings after the implementation pass reported itself
  done, ranging from a whole-file size check that would have broken every
  future release on this repo's own 450KB+ CHANGELOG.md, to a link-host
  prefix bypass, to a second-order bug in one of the fixes for a first-order
  finding (rows 56-65), to a heading-level validation bypass that let
  attacker-controlled text under a `#`/`###`+ heading reach the public
  release page untouched (rows 66-69). That is the review cascade doing its
  job, not a confidence claim falsified — the distinction this check exists
  to police is claiming "yes, confident" and then being wrong, not "not yet
  reviewed" and then a review finding something. All 11 findings are fixed,
  tested, and recorded in `reviews.json` (`code`, `external_code`, `doubt`).
  Coverage: every ledger row is `tested`/`untestable`, 0 untested-testable.

## Verification (medium+)
- **Surface:** cli
- **Runner command:** `uv run pytest shared/tests/test_repo_identity.py shared/tests/test_extract_changelog_section.py shared/tests/test_condense_release_notes.py shared/tests/test_validate_release_notes.py shared/tests/test_create_github_release.py shared/tests/test_publish_release_notes.py -v` (split from one file into six, one per stage — see the mini-plan's `## 2. Work breakdown` for why). The plugin-side advisory check (`plugins/shipwright-changelog/tests/test_setup_changelog_previous_release.py`) is a SEPARATE pytest root (repo's own one-root-per-process rule — combining it into this command collides on the `tests.conftest` module name, `ImportPathMismatchError`, self-caught while running F0.5) and is verified instead as its own unit by F0's suite runner (`shipwright-changelog` unit, PASS) — `surface_verification.py`'s `--runner` accepts one non-shell command (no `&&`/`;`), so it cannot itself span two pytest roots.
- **Evidence path:** JUnit output from that pytest invocation, staged for F0.5
- **Justification (only if surface=none):** n/a — CLI surface, no dev server needed. `gh release create` itself is mocked/faked in tests (never hits the real GitHub API from a test run — see "Never run a producer to verify it").
