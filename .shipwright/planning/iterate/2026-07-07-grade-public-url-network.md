# Iterate B — grade: public URL defaults to network-on (Part 3)

- **run_id:** `iterate-2026-07-07-grade-public-url-network`
- **Intent:** CHANGE · **Complexity:** small (privacy-sensitive default → medium review care)
- **Source plan:** `Spec/grade-local-honesty-fix-plan.md` Part 3 (user-approved 2026-07-07)

## Problem
After Iterate A, a local cold grade measures ~only size-discipline (thin —
change-traceability/test-health/security are n/a without network). For the
lead-magnet flow on a PUBLIC repo there is no privacy reason to stay local: the
repo is already public, and cloning it already sends its identity to GitHub.

## Change
- `open_target` tags a cloned remote with `input_kind="url"` (populate the field
  that was reserved for exactly this — `resolve_target.ResolvedTarget.input_kind`).
- `grade.py`: `allow_network = args.allow_network or target.input_kind == "url"`.
  A **URL / owner-repo** target defaults network-on; a **local path** stays
  local-only (privacy-first). `resolve_network_policy` (unchanged) still probes
  visibility → auto-disables on a private/unverifiable remote unless
  `--allow-network-private`, and falls back to a local grade when `gh` is
  unavailable — so a URL grade is never a false F.
- SKILL.md + guide.md document the URL-vs-local network default.

## Acceptance Criteria
- **AC1:** a public URL / `owner/repo` target defaults to network enrichment
  (no `--allow-network` needed).
- **AC2:** a local path stays local-only by default — even a local repo with a
  public GitHub remote (privacy-first intact).
- **AC3:** `--allow-network-private` stays opt-in; a private/unverifiable remote
  auto-disables enrichment.
- **AC4:** `gh` unavailable / no resolvable remote → local grade, never F.
- **AC5:** SKILL.md + guide.md reflect the new default; grade suite green.

## Confidence Calibration
- **Boundaries touched:** the grader's input seam (`open_target` → `input_kind`)
  and the CLI's network-policy wiring (`grade.py`). No engine/contract change; no
  new consumer branches on `input_kind` except the new grade.py line (grep-verified).
- **Empirical probes (real CLI, gh authed as svroch):**
  - Public URL `octocat/Hello-World` WITHOUT `--allow-network` →
    `network_enabled: True`, enrichment `PR-association (octocat/Hello-World)`
    (was False pre-change). The default flip works E2E.
  - Local path to this monorepo (public remote) → `network_enabled: False`
    (privacy-first intact; graded A authoritative).
  - URL with no resolvable remote (test clone of a remote-less fixture) →
    grade B, `network_enabled: False` (honest local fallback, not F).
- **Test Completeness Ledger:**
  | Behavior | Disposition | Evidence |
  |---|---|---|
  | Cloned remote → input_kind="url" | tested | `test_clone.py::TestOpenTarget::test_cloned_remote_carries_url_kind` |
  | Local path → input_kind="local_path" | tested | `test_local_path_carries_local_path_kind` |
  | github.com URL target defaults allow_network=True | tested | `test_grade_cli.py::TestPublicUrlDefaultsNetworkOn::test_public_github_url_defaults_allow_network_true` (policy spy) |
  | **GHE / non-github.com URL is NOT defaulted network-on** (privacy: slug must not leak to github.com) | tested | `test_github_enterprise_url_does_not_default_network_on` (spy) + `test_gh_bridge.py::test_is_github_com_remote_false_for_non_github_com` |
  | `is_github_com_remote` matches ONLY literal github.com (https/ssh/scp), rejects GHE/spoofed/empty | tested | `test_gh_bridge.py::test_is_github_com_remote_true_for_github_com` + `..._false_for_non_github_com` |
  | Local path defaults allow_network=False | tested | `test_local_path_stays_local_only_by_default` (policy spy) |
  | --allow-network-private stays opt-in (allow_private False by default) | tested | same spy asserts `allow_private is False` |
  | URL clone without github.com remote → local grade, not F (hermetic) | tested | `test_url_clone_without_github_remote_falls_back_to_local_not_f` |
  | Existing URL clone-and-grade unaffected + now hermetic (still B) | tested | `test_url_is_cloned_and_graded` (regression, green) |
  - 0 untested-testable behaviors. AC1-AC4 covered by tests + real-CLI probes; AC5 by the doc edits + green suite.
  - **Internal-review findings addressed:** (1) GHE-host privacy gap → the default now
    gates on `is_github_com_remote` (github.com only; GHE requires explicit
    `--allow-network`); (2) test hermeticity → the fallback tests now run with
    allow_network=False, short-circuiting before any gh call.
- **Confidence-pattern check:** asymptote — unit (spy) + real-CLI E2E on a live
  public repo AND a live local repo; breadth — input seam, CLI wiring, private/no-gh
  fallback, docs. No cross_component machinery; no `touches_io_boundary` config.
