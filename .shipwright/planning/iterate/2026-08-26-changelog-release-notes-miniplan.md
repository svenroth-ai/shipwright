# Mini-Plan: changelog-release-notes

- **Run ID:** iterate-2026-08-26-changelog-release-notes

**Revised after Internal Plan Review (opus-plan-reviewer, 17 findings, all
fixed).** See the iterate spec's `## Internal Plan Review` section for the
full triage. This version integrates every finding.

## 1. Files to create/modify

| File | Change |
|---|---|
| `shared/scripts/tools/extract_changelog_section.py` | new — reads `git show v{version}:CHANGELOG.md` (tagged blob, not worktree — Finding 5), slices the section via `changelog_sections.section_starts`/`section_end`, refuses (not "picks the first") when `len(starts) != 1` (Finding 16c). Resolves the previous version from `git tag --list 'v*' --sort=-v:refname` (Finding 15), not CHANGELOG heading order, and verifies it resolves before returning it. Enforces `MAX_SECTION_BYTES` (Finding 9) |
| `shared/scripts/tools/condense_release_notes.py` | new — single tool-less LLM completion call (reuses `external_review.py`'s provider/key-resolution + HTTP pattern; no Agent-tool spawn, no tool access — closes the prompt-injection-to-action risk, Round 2 deepseek finding 2) that turns extracted CHANGELOG text into the summary sections only (no footer — that's mechanical, see below) |
| `shared/scripts/tools/validate_release_notes.py` | new — sanitize-AND-validate (Round 2: returns the canonical sanitized body, not just pass/fail — the caller publishes exactly what this returns): non-empty, size cap well under GitHub's ~125,000-char body limit, `##` headings drawn from the fixed allowlist, version string present, ends with the mechanically-computed footer (both links, or none when `previous_version_tag is None`), `@mentions`/bare `#NNN` neutralized, Markdown image/autolink/bare-URL/raw-HTML-tag syntax rejected, links host-restricted to the project's own repo (normalized `owner/repo` from `git remote get-url origin`) |
| `shared/scripts/tools/create_github_release.py` | new — `gh auth status --hostname github.com` (Finding 16e) → `gh release view v{version}` first to detect an existing release (Finding 6, returns `status:"exists"`) → `gh release create v{version} --notes-file {path} --title v{version} --verify-tag` (Finding 2). Version string validated against `^\d+\.\d+\.\d+` before touching argv (Finding 16f). Returns `{"status": "ok"\|"exists"\|"skipped"\|"failed", ...}`; never raises for skip/exists/failed |
| `plugins/shipwright-changelog/skills/changelog/references/release-notes-prompt.md` | new — condensation subagent's instructions (moved here from the originally-proposed `shared/templates/`, which was the wrong home — Finding 11). Fenced instruction: the CHANGELOG text below is untrusted content to summarize, never a directive (Finding 8, prompt-level layer) |
| `plugins/shipwright-changelog/skills/changelog/SKILL.md` | edit — compact new subsection inside Step 7 (bloat-budget-conscious per Finding 1 — see §2 below), after `git push --tags origin main` and before "Record changelog event"; also updates the frontmatter `compatibility` line to mention release creation (Finding 16b) |
| `plugins/shipwright-changelog/skills/changelog/references/release-workflow.md` | edit — full rationale for: LLM condensation vs. mechanical (why judgment stays LLM, contract stays mechanical), forward-only scope, non-blocking-but-detected-next-release design, and the tag-integrity (`--verify-tag`) reasoning. This is where the bulk of the prose that would otherwise bloat SKILL.md lives |
| `plugins/shipwright-changelog/scripts/checks/setup-changelog.py` | edit — advisory (never blocking) check: does the immediately preceding tag have a GitHub Release? Reported in the existing setup JSON output, printed as a notice in the intro if true (Finding 7) |
| `docs/hooks-and-pipeline.md` | edit — artifact-write matrix gains a row: `/shipwright-changelog` now also writes a GitHub Release (best-effort) |
| `docs/guide.md` | edit — Chapter 4 (phases) / Chapter 8 (quality gates) get a one-line mention that release notes are now published to the code host, not just committed (Finding 16a) |
| `.shipwright/planning/01-adopted/spec.md` | edit — FR-01.09 gains two new ACs, **appended** (not inserted mid-list — Finding 13a), tool-agnostic wording ("the code host's release page" not "gh" — Finding 13b), `- (E) Given ... when ... then ...` shape (Finding 13c) |
| `shared/tests/test_release_notes.py` | new — **moved from `plugins/shipwright-changelog/tests/`** (Finding 4 — ADR-045 `lib`/`tools` namespace collision with the plugin's own `lib` binding). Reuses `shared/tests/_changelog_release_fixtures.py` |

## 2. Work breakdown

1. **`extract_changelog_section.py`** (shared/scripts/tools/). Reads the
   tagged blob via `git show v{version}:CHANGELOG.md` (subprocess, decode
   utf-8). Uses `changelog_sections.section_starts(lines, version)` +
   `section_end`; `len(starts) == 0` → refuse "version not found in tagged
   CHANGELOG.md"; `len(starts) > 1` → refuse "ambiguous — N headings for
   this version" (mirrors `aggregate_changelog.py`'s own `entry_version`
   multi-heading refusal). Enforces `MAX_SECTION_BYTES` (64 * 1024, matching
   the aggregator's own `MAX_DROP_FILE_BYTES` convention) — refuses rather
   than silently truncating into the condensation prompt. Previous version:
   `git tag --list 'v*' --sort=-v:refname`, take the first entry strictly
   below `{version}`; verify it via `git rev-parse --verify` before
   returning; omit (not fabricate) the compare link if none resolves.
   Output JSON: `{version, section_text, previous_version_tag | null}`.
   **Tests:** section present / absent / 0 headings / 2 headings / oversized
   section refusal / no previous tag (first-ever release) / previous tag
   present but unresolvable (deleted ref) → omitted, not error.
2. **`validate_release_notes.py`** (shared/scripts/tools/). Pure function
   `validate(body: str, version: str) -> ValidationResult` + thin CLI
   wrapper. Checks, in order (first failure wins, reason named):
   non-empty; `len(body.encode('utf-8')) <= MAX_RELEASE_BODY_BYTES` (set
   comfortably below GitHub's ~125,000-char cap, e.g. 60,000); every `##`
   heading is in `{Highlights, Features, Breaking Changes, Changed, Fixed,
   Security}`; `v{version}` (or `{version}`) appears in the body; both a
   CHANGELOG-anchor link and a compare link are present (when a previous
   version was resolved — skip that specific check when it was not, since
   the extractor already handled that case honestly). **Mechanical
   neutralization** (not just detection) applied to the body before these
   checks: `@name` → `` `@name` `` (code-span, kills the live mention),
   bare `#NNN` → `` `#NNN` `` (kills the live cross-reference), and outright
   rejection (validation failure, not neutralization) of Markdown image
   syntax `![...](...)`. Link-host check: every `[text](url)` must point at
   this repo's own `github.com/<org>/<repo>` host (read from `git remote get-url
   origin`) or a relative anchor — anything else fails validation.
   **Tests:** each rule independently (empty, oversized, bad heading,
   missing version string, missing links, `@mention` neutralized,
   `#123` neutralized, image rejected, external-host link rejected,
   a fully valid body passes clean).
3. **`create_github_release.py`** (shared/scripts/tools/). Preflight order:
   `gh --version` parsed → below the `--verify-tag` minimum (2.49) →
   `{"status":"skipped","reason":"unsupported_gh_version:<version>"}`.
   `gh auth status --hostname github.com` → not found on PATH →
   `{"status":"skipped","reason":"gh_not_found"}`; non-zero exit →
   `{"status":"skipped","reason":"gh_unauthenticated"}`. Version validated
   against `^\d+\.\d+\.\d+(-[\w.]+)?$` before any argv use — reject anything
   else outright (Finding 16f, closes the leading-dash-as-flag class of
   bug). Repo identity resolved once via the shared normalize-origin helper
   (Round 2) and passed explicitly as `--repo owner/repo` to every `gh`
   call below — never left to cwd inference. `gh release view v{version}
   --repo owner/repo` → confirmed not-found (stderr pattern / exit
   semantics distinguished from other failures, Round 2) →
   `create` is eligible; any OTHER view failure (network/auth/API error) →
   `{"status":"failed","reason":"release_view_failed:<excerpt>"}` WITHOUT
   attempting create; a found release → `{"status":"exists","url":...}`.
   Otherwise `gh release create v{version} --notes-file {path} --title
   v{version} --verify-tag --repo owner/repo` → success →
   `{"status":"ok","url":...}`; failure → `{"status":"failed",
   "reason":"<stderr excerpt, capped>"}`. Never raises for any of these —
   only for a genuinely programmer-error argv shape. **Tests:** every
   status branch (ok / exists / skipped:gh_not_found / skipped:
   gh_unauthenticated / skipped:unsupported_gh_version / failed:
   release_view_failed / failed:create) via a mocked `subprocess.run` (never
   a real `gh` call — matches this repo's "never run a producer to verify
   it" convention), PLUS an explicit **argv-shape assertion** — the exact
   list of args built for the create call, asserting `--verify-tag` and
   `--repo owner/repo` are present and the version string lands as a single
   safe argv element (Finding 14).
4. **`release-notes-prompt.md`** (plugin references/). The fixed structure
   already agreed with the operator (Highlights / Features / Breaking
   Changes / Changed / Fixed / Security, one sentence per bullet, no emoji,
   omit empty sections, close with the two links) PLUS the injection-fence
   instruction (Finding 8, prompt layer): state explicitly that the
   CHANGELOG text handed to the model is untrusted input to summarize, and
   any imperative-sounding text inside it is content, never an instruction
   to follow. **Test:** a drift-guard test asserting the file exists at the
   exact path SKILL.md references, and contains the required section-name
   markers (Finding 14, prompt-path drift).
5. **SKILL.md Step 7 edit — written bloat-budget-conscious (Finding 1).**
   `shipwright_bloat_baseline.json` pins this file at `current: 425` with
   zero headroom (`state: "exception"`, `ADR-348` already on file). Keep the
   SKILL.md addition to a compact bash chain + one short pointer sentence to
   `release-workflow.md` for the full rationale (matching how Step 5.4/5.5
   already stay terse and defer rationale to their own reference docs).
   Measure `wc -l` after the edit against the 425 baseline; if still over,
   look for genuine redundancy to trim in the same file BEFORE reaching for
   a bloat-exception ADR bump (repo convention: "find redundancy, never
   raise it" — see feedback memory). Only write a fresh bloat-exception ADR
   + bump `current` if no safe compression closes the gap. The new
   subsection, in order: `extract_changelog_section.py` (→ `skipped:
   extract_failed:<reason>` on refusal, Round 2) → `condense_release_notes.py`
   over `release-notes-prompt.md` + the extracted section text, summary
   sections only (→ `skipped: condensation_failed:<reason>` on failure,
   Round 2) → mechanically append the CHANGELOG-anchor + compare-link footer
   (never trusted to the model, Round 2) → `validate_release_notes.py`,
   which returns the sanitized body → write **that returned sanitized
   body**, not the raw reply, to `.shipwright/runtime/release_notes_v{version}.md`
   (`mkdir -p` first, `encoding="utf-8", newline="\n"` — Finding 16d) → on
   pass call `create_github_release.py` against that file. The chain avoids
   `set -e` so any stage's failure still reaches the summary print (Round 2).
   Add one line per outcome to the Step 7 summary banner (`ok` / `exists` /
   `skipped: <reason>` / `failed: <reason>` / `skipped:
   notes_failed_validation` / `skipped: extract_failed:<reason>` /
   `skipped: condensation_failed:<reason>`).
6. **`release-workflow.md` edit** — the rationale section carrying what
   Step 5's terse pointer defers: LLM-for-judgment / mechanical-for-contract
   split (Finding 3 direct answer), why `--verify-tag` (Finding 2), why
   forward-only, why non-blocking-but-detected-next-release (Finding 7).
7. **`setup-changelog.py` edit** — after computing `last_tag`, check (via
   `gh release view {last_tag}` or `gh api`, best-effort — a failure here
   is itself advisory, never blocking setup) whether it has a release; add
   `previous_tag_has_release: bool | null` to the JSON output; the skill's
   intro-banner step prints a one-line advisory notice when `false`.
8. **`docs/hooks-and-pipeline.md` + `docs/guide.md` edits** — per this
   repo's own CLAUDE.md rule (a changed plugin write-surface / phase
   behavior must be reflected here in the same diff).
9. **`spec.md` FR-01.09 edit** — append two `- (E) Given ... when ... then
   ...` lines after the existing last AC (line ~614), tool-agnostic wording.
   Re-run the FR-criteria/coverage checks afterward (Finding 13, since two
   new ACs on an existing FR can move Group D coverage).
10. **Tests** — `shared/tests/test_release_notes.py`, reusing
    `shared/tests/_changelog_release_fixtures.py` where it already builds
    realistic CHANGELOG.md fixtures. Covers items 1-3 directly, PLUS the
    **aggregator→extractor round-trip probe** (Finding 17): render a
    section via `aggregate_changelog._render_versioned_section`, write it
    into a fixture CHANGELOG.md the same way the real aggregator does,
    extract it back via `extract_changelog_section`, assert byte-equality.
    The SKILL.md prose change itself stays covered by the code-review
    cascade (not independently unit-testable), same as every other
    prose-only SKILL.md step in this plugin — no contradiction with item 4's
    drift-guard test, which covers the prompt *file*, not the SKILL.md
    prose.
11. **Post-push: `bash scripts/update-marketplace.sh` +
    `uv run scripts/check_plugin_cache_sync.py --strict`** (Finding 12) —
    procedural step run by the operator/agent after this iterate's PR
    merges, per CLAUDE.md's plugin-cache-sync rule. Not code — a checklist
    item for finalization, noted here so it isn't silently dropped like it
    was for iterates 7-11.

## 3. Component hierarchy
n/a — no UI.

## 4. Data model changes
None.

## 5. Test strategy
- Unit tests: `extract_changelog_section.py` (section slicing + refusal
  cases + previous-version resolution), `validate_release_notes.py` (every
  rule independently), `create_github_release.py` (all five status
  branches + argv-shape assertion, subprocess mocked throughout).
- Integration: the aggregator→extractor byte-equality round-trip.
- Drift guard: the prompt file exists at the path SKILL.md references and
  contains the required section markers.
- No E2E needed (CLI surface). `gh release create` itself is never invoked
  for real in tests — matches "never run a producer to verify it".
- Full plugin test suite run at F0. New tests live in `shared/tests/`
  (Finding 4 — avoids the ADR-045 `lib`/`tools` collision the plugin's own
  test root has with `shared/scripts/tools`-style imports); no new pytest
  root is created.

## 7. Round 2 revisions (External LLM Review — deepseek + openai, both verdict `revise`, both integrated as fixes)

Both reviewers converged on the same critical gap plus several overlapping
edge cases. No finding declined — all fixed, folded into the design above:

- **Sanitized body must be what's actually published (both reviewers, high).**
  `validate_release_notes.py` becomes a sanitize-**and**-validate function:
  `validate(body, version, previous_version_tag) -> (ok, sanitized_body,
  reason)`. It returns the canonical sanitized text (mentions/refs already
  code-spanned) and the SKILL.md step writes **that returned text**, not the
  raw subagent reply, to the notes file `gh` reads. A test asserts the exact
  bytes passed to the mocked `gh release create --notes-file` have
  `@mentions`/`#NNN` already neutralized.
- **Condensation subagent tool-access risk (deepseek, high).** A prompt-
  injected CHANGELOG bullet could steer a tool-enabled agent into taking
  action (filesystem/shell/network) before the mechanical validator ever
  runs — a prose fence in the prompt doesn't stop that. Fix: condensation is
  **not** an Agent-tool subagent spawn. It is a single tool-less LLM
  completion call, reusing `external_review.py`'s own provider/key-
  resolution and HTTP-call pattern (a new small
  `shared/scripts/tools/condense_release_notes.py`, same shape as
  `external_review.py` but one prompt in, one text reply out — no tools, no
  side effects possible).
- **Trailing links delegated to the LLM (openai, medium).** Fix: the LLM
  prompt asks only for the summary sections (Highlights through Security);
  the CHANGELOG-anchor and compare links are computed mechanically from the
  validated version + resolved previous tag and appended by
  `create_github_release.py`'s caller after condensation, never trusted to
  model output. The validator checks the body **ends with** this exact
  computed footer.
- **Previous-tag remote verification (openai, high).** `git rev-parse
  --verify` only proves a LOCAL ref exists. Fix: after picking the semver-
  highest local tag below `{version}` (see next point), verify it exists on
  `origin` too — `git ls-remote --exit-code --tags origin refs/tags/{tag}`
  — before using it for the compare link; on absence, try the next
  candidate, else omit the link (never emit a 404).
- **Semver-aware previous-version ordering (deepseek, medium).** String
  comparison on `git tag --list 'v*'` output mis-orders `v0.10.0` vs
  `v0.9.0`. Fix: parse each candidate tag against a strict `v\d+\.\d+\.\d+`
  grammar (reject anything else — closes openai's "arbitrary `v*` match"
  edge case too) and compare numerically.
- **Repo-identity normalization + explicit `--repo` (openai, medium).** Fix:
  one small shared helper normalizes `git remote get-url origin` (SSH,
  HTTPS, with/without `.git`) to `owner/repo`; reused by the validator's
  link-host allowlist AND passed explicitly as `--repo owner/repo` to every
  `gh release view`/`gh release create` call — never left to `gh`'s cwd
  inference.
- **`gh release view` non-zero conflates "not found" with real failures
  (openai, medium).** Fix: only a confirmed not-found (checked via stderr
  content / `gh release view --json` exit semantics) is treated as
  `exists:false`; any other failure (network, auth, API error) short-
  circuits straight to `{"status":"failed", ...}` — it does NOT fall through
  to attempting `create`.
- **Broader link/image surface than `[text](url)` (both reviewers, medium).**
  Fix: the validator also scans for and rejects Markdown autolinks
  (`<https://...>`), bare `http(s)://` URLs, and raw HTML `<a>`/`<img>` tags
  — not just the inline `[text](url)`/`![...]()` forms. Conservative-reject
  philosophy (openai's suggestion): anything URL-bearing that isn't the one
  expected, mechanically-appended footer form fails validation rather than
  being partially parsed.
- **`validate()` needs to know whether a compare link is required (deepseek,
  medium).** Fixed by the signature change above (`previous_version_tag`
  param) — first-ever release passes with no compare link; every other
  release fails without one.
- **Explicit banner statuses for extraction/condensation failure (deepseek,
  medium).** The "never silently swallowed" ACs apply to every stage, not
  just `create_github_release.py`. Fix: `skipped: extract_failed:<reason>`
  and `skipped: condensation_failed:<reason>` join the enumerated Step 7
  banner outcomes; the bash chain avoids `set -e` so a mid-chain failure
  still reaches the summary print instead of aborting silently.
- **`gh` minimum version for `--verify-tag` (deepseek, low).** Fix:
  `create_github_release.py` parses `gh --version` before relying on the
  flag; below the minimum (`--verify-tag` shipped in `gh` 2.49+), report
  `skipped: unsupported_gh_version:<version>` rather than letting `gh` fail
  on an unrecognized flag.
- **Setup-script advisory tri-state (deepseek, low).** Fix:
  `previous_tag_has_release: bool | None` — `None` (gh unavailable/
  unauthenticated during the check itself) prints "cannot verify" rather
  than being silently treated as `false` ("missing").

## 6. Alternative approach (rejected)

**Alternative: mechanical truncation instead of an LLM condensation pass**
— e.g. take the first N bullets per category, or hard-truncate each bullet
to its first sentence via a period-split regex.

**Rejected because:** the actual CHANGELOG bullets are not one-clause
sentences — many run 3-6 sentences with the "why" embedded mid-paragraph
(see the v0.32.0 section reviewed with the operator: e.g. the Traceability
Manifest bullet or the fold-map bullet). A naive first-sentence truncation
frequently keeps the least informative clause and drops the actual capability
being described, and a regex cannot distinguish "this changed behavior" from
"this is a breaking change requiring migration" — that classification is
exactly the judgment call the operator flagged as needing a human-quality
pass when reviewing the draft release body together in this conversation.
The LLM pass costs one subagent call per release (infrequent — releases
happen at most a few times a week), so the cost is negligible against the
quality gap. **Internal Plan Review reinforced rather than reversed this
call** (Finding 3's direct answer: keep judgment with the LLM, add a
mechanical contract in front of it rather than replacing the LLM pass).
