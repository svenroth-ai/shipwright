# Mini-Plan: triage-launch-surface

- **Run ID:** iterate-2026-05-20-triage-launch-surface
- **Type:** feature | **Complexity:** medium
- **Spec:** `.shipwright/planning/iterate/2026-05-20-triage-launch-surface.md`
- **Branch / Worktree:** `iterate/triage-launch-surface` /
  `.worktrees/triage-launch-surface/`

## Files to create / modify

| File | Change | Notes |
|---|---|---|
| `shared/scripts/triage.py` | **modify** | Add `launch_payload: str \| None = None` kwarg to `append_triage_item` + `append_triage_item_idempotent`. Persist as wire-key `launchPayload`. `read_all_items` passes it through unchanged. No validation required (free-form string). |
| `shared/scripts/github_triage.py` | **modify** | Replace per-finding emit with action-unit emit. New helpers `_owner_repo()` (from `gh api repos/{owner}/{repo}` or git remote), `security_action_unit`, `secrets_action_unit`, `ci_action_unit`. New `_LEGACY_PREFIXES` constant + `_migrate_legacy_items` sweep. `_OWNED_PREFIXES` becomes the three new ones. Delete the four legacy mapper functions. |
| `shared/scripts/github_api.py` | **modify** | Add `owner_repo() -> str \| None` helper. Resolution algorithm: (1) parse `git remote get-url origin` from `project_root`; (2) accept HTTPS `https://github.example.com/{owner}/{repo}[.git]?` and SSH `git@github.example.com:{owner}/{repo}[.git]?` forms, including GitHub Enterprise hosts; (3) strip trailing `.git`; (4) return `"{owner}/{repo}"`. On missing remote, non-GitHub URL, or any parse failure: return `None` (logged once to stderr). NO `gh api repos/...` call — gh requires owner/repo to call repos/, so resolution must be local-first. Test matrix: 7 representative remote shapes per AC-10. Mini-plan supersedes the iterate spec's earlier "github_api.py no change" statement (review finding #5). |
| `shared/scripts/tools/aggregate_triage.py` | **modify** | After the title/severity line of each open item, if `launchPayload` is a non-empty string emit it inside ```` ```text … ``` ```` fence. Idempotent re-render (no extra blank lines, deterministic order). |
| **NEW** `shared/scripts/tools/triage_cli.py` | **create** | Argparse-driven CLI. Subcommands take **positional id**: `list`, `promote <id> --task-ref <ref>`, `dismiss <id> --reason <reason>` (matches the iterate spec wording — review finding #1). Both `promote` and `dismiss` delegate to a SINGLE shared helper `triage_promote.promote_item` / `triage_promote.dismiss_item` (extracted in the triage_promote modification below) — no semantic divergence (review finding #2). `list` prints human-readable inbox view; control characters in `launchPayload` are stripped before printing to avoid terminal injection (review finding #10). Exit 0 / 1 / 2 per spec AC-4..6. |
| `shared/scripts/tools/triage_promote.py` | **modify** | Extract two library-shaped helpers `promote_item(project_root, item_id, *, task_ref, by="triage_promote.py", reason=None)` and `dismiss_item(project_root, item_id, *, reason, by="triage_promote.py")`. The existing `main()` invokes them with `by="triage_promote.py"`; the new CLI invokes them with `by="cli"`. Zero behavioral change for existing callers; parity test (AC-11) verifies byte-identical status events except for the `by` field. |
| **NEW** `shared/tests/test_github_triage_action_units.py` | **create** | AC-1 + AC-7 tests: action-unit emission, legacy migration sweep, fail-soft-on-failed-fetch invariant preserved. |
| **NEW** `shared/tests/test_triage_launch_payload_roundtrip.py` | **create** | AC-2 + AC-8 + AC-9 tests: producer→file→consumer round-trip with payload + with `None`; parametrized across all 7 producer call-sites; second-call idempotency. |
| **NEW** `shared/tests/test_triage_cli.py` | **create** | AC-4 + AC-5 + AC-6: subprocess tests invoking the CLI against a fixture project_root with a seeded `triage.jsonl`. Use `tests/conftest.py` `tmp_path` pattern. |
| `shared/tests/test_aggregate_triage.py` | **modify** | Add a case: open action-unit item with non-empty `launchPayload` → markdown fence rendered immediately under the item header. Existing cases (no payload, legacy items) untouched. |
| `shared/tests/test_triage.py` | **modify** | Update existing tests where they assert the persisted wire dict shape (now must accept the new key); add a "field absent vs null" case if not already present. |
| `shared/tests/test_github_triage.py` | **modify** | Existing #39 tests: keep the throttle / fail-soft / dedup-key tests; delete the per-finding-mapping tests (they're superseded). The action-unit tests in the new file replace them. |
| `.shipwright/planning/01-adopted/spec.md` | **modify** | Append "Refined by `iterate-2026-05-20-triage-launch-surface`" block to FR-01.14 with 5 new E-form ACs (action-units, launchPayload, inbox render, CLI surface, legacy migration). Done at F1 drift-check, not at Step 6. |
| `docs/guide.md` | **modify** | Chapter 4: add Triage Inbox section under the iterate phase docs (action-units, 3 verbs, launchPayload + copy-paste flow, CLI verbs). |
| `docs/hooks-and-pipeline.md` | **modify** | Artifact-write matrix: github_triage.py now writes launchPayload; aggregate_triage.py reads it. Context-loading matrix: no change. |

## Work breakdown (sequential)

0. **Pre-step: extract shared helpers in `triage_promote.py`** (RED →
   GREEN, 1 step — review finding #2)
   - Test: existing `triage_promote.py::main` behavior unchanged after
     refactor (full regression of existing test_triage_promote.py).
   - Add new test: import `promote_item` / `dismiss_item` from
     `triage_promote` and call directly; assert same status event
     shape as `main()` (proving the helper IS the canonical path).
   - Refactor: extract two helpers; `main()` becomes thin
     args-parse + helper-invocation. NO behavior change for existing
     callers.

1. **Schema extension in `triage.py`** (RED → GREEN, 1 step)
   - Write test: `append_triage_item(..., launch_payload="X")` then
     `read_all_items` returns an item where `item["launchPayload"] == "X"`.
   - Write test: omitting the kwarg yields `item["launchPayload"] is None`.
   - Write test: same for `append_triage_item_idempotent`.
   - Implement: thread the kwarg through both functions, add to the wire dict.
   - Run `shared/tests/test_triage.py` — green.

2. **Aggregator render** (RED → GREEN, 1 step)
   - Test (positive path): seed a triage.jsonl with one action-unit item
     carrying a multi-line `launchPayload`; assert the rendered markdown
     contains a `` ```text … ``` `` fence with the payload verbatim under
     the item header.
   - Test (loud failure — review finding #13): seed an item with `kind`
     matching a `gh-*` source and `launchPayload=None`; assert the
     aggregator emits a **visible placeholder** (e.g. `> [no launch
     payload — producer bug; please report]`) instead of silently
     omitting the launch surface. Items from legacy producers (no
     `launchPayload`) render exactly as today — no placeholder.
   - Test (safe fence): payload containing 3+ consecutive backticks
     uses a fence opener that is N+1 backticks long (common markdown
     idiom) so the payload never breaks out.
   - Implement minimal rendering hook in `aggregate_triage.py`.
   - Run `shared/tests/test_aggregate_triage.py` — green.

3. **`owner_repo()` helper in `github_api.py`** (RED → GREEN, 1 step)
   - Test matrix (AC-10): HTTPS `https://github.com/acme/foo.git` →
     `"acme/foo"`; HTTPS `https://github.com/acme/foo` → `"acme/foo"`;
     SSH `git@github.com:acme/foo.git` → `"acme/foo"`; enterprise HTTPS
     `https://github.example.com/acme/foo` → `"acme/foo"`; enterprise SSH
     `git@github.example.com:acme/foo` → `"acme/foo"`; missing remote
     → `None`; non-GitHub URL `https://gitlab.com/acme/foo` → `None`.
   - Implement local-first resolver (no `gh api` call). Logs one stderr
     warning on `None`.

4. **Action-unit mappers + legacy migration in `github_triage.py`**
   (RED → GREEN, 6 sub-steps)
   - **4a.** Test: given a fixture with 12 code-scanning + 4 dependabot
     alerts for repo `acme/foo`, calling `security_action_unit({
     "code_scanning": [...], "dependabot": [...]}, "acme/foo")` returns
     ONE dict with `dedup_key="gh-security:acme/foo"`, severity = max
     severity across both feeds, `launch_payload` starts with
     `/shipwright-security` and contains the security-tab URL. Payload
     content is **deterministic**: re-shuffle alert order and assert
     byte-identical payload (review finding #6).
   - **4b.** Test: given 2 secret-scanning alerts, `secrets_action_unit`
     returns ONE dict with critical severity, `dedup_key="gh-secrets:
     acme/foo"`, `launch_payload` = static-checklist + secret-scanning
     tab URL only. **No alert content** in payload — assert payload
     does NOT contain the fixture's `secret_type_display_name`,
     `secret_type`, location URLs, `html_url`, or commit SHA (review
     finding #9 — hygiene boundary).
   - **4c.** Test: given a failed CI run, `ci_action_unit` returns ONE
     dict with `dedup_key="gh-ci:{workflow_id}"` (NO sha — review
     finding #7), `launch_payload` starts with
     `/shipwright-iterate --type bug` and contains the workflow's
     GitHub **page URL** (stable across runs — derived from
     `_workflow_identity`), NOT the run-specific URL.
   - **4d.** Test: multi-branch — feed `latest_failed_ci_runs` two
     failed runs of the same workflow on `main` and `dev`. Confirm
     only the default-branch failure emits an item (the helper already
     scopes to `fetch_workflow_runs(default_branch())` via #39, but
     test explicitly per review finding #8).
   - **4e.** Test: legacy migration — seed a triage.jsonl with one
     legacy item per legacy prefix; call `import_findings` against a
     fixture where ALL four new-prefix fetches return empty (success);
     assert each legacy item dismissed with `reason="schemaMigration"`
     and no new appends. Run TWICE and assert the second run does NOT
     re-emit the schemaMigration event (review finding #12).
   - **4f.** Test: fail-soft preservation (PER-SOURCE — review finding
     #3) — when `fetch_code_scanning_alerts()` returns `None` but
     other three fetches succeed: legacy `github:code-scanning:*` items
     stay UNCHANGED; legacy `github:dependabot:*`,
     `github:secret-scanning:*`, `github-ci:*` items get migrated.
     Repeat for each of the four sources.
   - **4g.** Implement the three action-unit mappers, the legacy sweep
     (per-source-gated, using `read_all_items` resolved view), rewire
     `import_findings` plan loop. Update `_OWNED_PREFIXES`. The
     `latest_failed_ci_runs` helper stays unchanged.
   - Run `shared/tests/test_github_triage*.py` +
     `test_github_triage_action_units.py` — green.

5. **CLI tool** (RED → GREEN, 5 sub-steps — positional id per review #1)
   - **5a.** Test: subprocess `triage_cli.py list` against a tmp project
     with seeded triage.jsonl prints each open item's header + fenced
     launchPayload + exits 0. Empty inbox prints one line + exits 0.
   - **5b.** Test: subprocess `triage_cli.py promote trg-XX
     --task-ref EXT:foo` flips status to `promoted` (positional id) and
     exits 0.
   - **5c.** Test: subprocess `triage_cli.py dismiss trg-XX
     --reason notRelevant` flips status to `dismissed` (positional id)
     and exits 0.
   - **5d.** Test: invalid id `triage_cli.py promote trg-DOESNOTEXIST`
     → exit 2 with stderr explaining "item id not found".
   - **5e.** Test (parity, AC-11): seed an identical fixture jsonl in
     two tmp dirs; invoke `triage_promote.py` against one and
     `triage_cli.py promote ...` against the other with the same args;
     diff the new status events excluding `ts` and `by` — must be
     byte-identical.
   - **5f.** Implement argparse + subcommand dispatch. `promote` and
     `dismiss` import `triage_promote.promote_item` /
     `triage_promote.dismiss_item` (extracted in step 0 below). Control
     chars in `launchPayload` stripped before stdout (review #10).

6. **Round-trip drift protection** (2 layers — review finding #11)
   - **5a. Schema-level parametrized test** — one parametrized test
     around `append_triage_item_idempotent`(_idempotent_), iterating over
     all 7 documented sources (`KNOWN_SOURCES`). Each case appends with
     `launch_payload="..."` and with the kwarg omitted; asserts
     `read_all_items` returns the persisted value or `None`. Tests the
     SCHEMA boundary, not artificial producer call-shapes.
   - **5b. Targeted producer tests** — two real-producer tests: the
     GitHub action-unit emit (full payload, AC-2) + one legacy
     finding-granular producer (`phaseQuality` chosen as
     representative) confirming omitted `launch_payload` persists as
     `null`. Avoids forcing the other 5 legacy producers through a
     synthetic uniform interface.

7. **Doc updates** (1 step — mandatory, NOT optional)
   - `docs/guide.md`: new section "Triage as Launch-Surface" under
     Chapter 4 (iterate phase), explaining action-units, 3-verb model,
     launchPayload + copy-paste flow, CLI verbs.
   - `docs/hooks-and-pipeline.md`: update artifact-write matrix
     (github_triage.py now writes launchPayload; aggregate_triage.py
     renders it) — append a new row under the existing triage section.
   - `CLAUDE.md`: no change (no new conventions).

8. **Spec.md modification** (at F1 — drift check)
   - Append "Refined by `iterate-2026-05-20-triage-launch-surface`"
     block to FR-01.14 with 5 new ACs (one per AC-1..5 from the iterate
     spec; AC-7 condensed into the action-unit AC).

## Test strategy

- **Unit + integration tests** at every layer (storage / mapper /
  aggregator / CLI). All under `shared/tests/`.
- **Boundary Probe (touches_io_boundary):** round-trip test from
  producer → on-disk JSONL → consumer for every changed surface.
  Parametrized across all 7 producers.
- **F0.5 cli surface:** the pytest invocation listed in the iterate
  spec's Verification block drives action-unit emission, launchPayload
  rendering, CLI subcommands, and legacy migration through their real
  modules.
- **E2E:** N/A (no web/browser surface — library + CLI).
- **Drift protection:** parametrized round-trip across all producer
  call-sites (AC-9); legacy-key migration test (AC-7).

## Alternative approach (rejected)

**Alternative:** store `launchPayload` outside `triage.jsonl` in a
sibling `.shipwright/triage_payloads.json` keyed by item id. Producer
writes both files; aggregator joins on render.

**Why rejected:** introduces a second source of truth for a 1:1 relationship
between item and payload; risks the two files diverging on partial-write
crashes (one updated, the other not); doubles the lock-discipline surface.
The append-only triage.jsonl already handles the same problem class
(history-events-resolve-by-file-order); piggybacking on it is simpler.
The rejected alternative would only be preferable if `launchPayload`
were >>1 KB per item, which it is not (~200 bytes typical).

## Risk + safety floor

- `touches_io_boundary` → Boundary Probe mandatory (step 5 above).
- `touches_shared_infra` → full unit test suite at F0, full code review.
- Reviewers should specifically check:
  - The legacy-migration sweep MUST respect `resolvable_prefixes` —
    fail-soft on a failed fetch means the corresponding legacy items
    stay untouched (preserves ADR-052 invariant).
  - The new dedup keys for `gh-security` and `gh-secrets` use
    `{owner}/{repo}`, not `{owner_repo}` (single repo per run today,
    but the producer must work if the project ever ships across
    multiple repos — out of scope to test now, but key shape supports
    it without breakage).
  - `launchPayload` is stored verbatim — no string escaping or
    transformation. The aggregator emits it inside a code fence so any
    backtick content in the payload would break the fence; mitigate by
    escaping the payload through `_safe_fence_content` (e.g. if the
    payload contains ``` ``` ```` ```` ``` ````, the fence opener gets
    one more backtick — common markdown idiom).
  - The CLI's `promote` must NOT re-implement `mark_status` semantics;
    it MUST delegate to the existing path so behavior stays identical
    with `triage_promote.py`.
