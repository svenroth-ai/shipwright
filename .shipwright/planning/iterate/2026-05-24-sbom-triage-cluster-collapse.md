# Iterate Spec: SBOM triage producer — collapse by common undeclared-dep signature

- **Run ID:** iterate-2026-05-24-sbom-triage-cluster-collapse
- **Type:** change
- **Complexity:** medium
- **Status:** draft

## Goal

Stop the SBOM producer (`emit_undeclared_triage`) from emitting N
separate triage items when N workspaces share the **same** set of
undeclared dep names. Collapse them into ONE action-unit per
common-undeclared-signature, with a launch payload that fans out
across all member workspaces. Mirrors the action-unit principle from
ADR-057 (Triage Inbox redesigned as a launch-surface).

## Acceptance Criteria

- [ ] **AC-1 (cluster detection).** Given N workspaces (N ≥ 2) whose
      sorted undeclared-dep name-tuple is byte-identical, the producer
      emits **one** action-unit instead of N. Single-workspace
      occurrences (N=1) keep the existing per-workspace shape.
- [ ] **AC-2 (dedup key shape).** Cluster items use
      `sbom:undeclared-cluster:<sha256-12>` where the hash input is
      `"|".join(signature) + "\n--members--\n" + "|".join(sorted(set(member_paths)))`
      — encodes BOTH signature AND membership so growing or shrinking
      the cluster yields a different key (external-review HIGH).
      Per-workspace items keep `sbom:undeclared:<manifest-rel-path>`.
      The two shapes are structurally distinct (different prefix) — no
      collision risk with audit_detector's source-based resolve.
- [ ] **AC-3 (idempotent across runs).** Same cluster signature + same
      workspace membership → re-running emits zero new items.
- [ ] **AC-4 (launch payload fan-out).** Cluster items carry a payload
      that loops over every workspace in the cluster. Format:
      `for d in W1 W2 ... ; do ( cd "$d" && <install_cmd> ) || exit 1
      ; done && <regen_cmd>`. Workspaces sorted alphabetically for
      diff-stable output. Single-quoted workspace paths (re-uses the
      `_shell_quote_workspace` hardening from iterate B.2).
- [ ] **AC-5 (auto-resolve scope).** When all member workspaces in a
      cluster have ZERO undeclared on the next emit, the cluster
      auto-dismisses (`reason="sbomResolved"`). When SOME members
      still have undeclared but with a different signature, the
      original cluster auto-dismisses and a fresh cluster (or
      per-workspace items) is emitted for the new state.
- [ ] **AC-6 (mixed-signature handling).** If workspace A has
      `{pytest, pytest-mock}` undeclared, B has `{requests}`, and C
      has `{pytest, pytest-mock}`: A+C form a cluster of 2 (one
      action-unit), B emits as per-workspace (N=1).
- [ ] **AC-7 (back-compat — legacy items untouched).** Pre-existing
      per-workspace items in `triage.jsonl` (status ∈ {triage,
      promoted, dismissed}) are NOT migrated. They remain
      individually addressable. The existing auto-resolve loop (which
      keys off `sbom:undeclared:` prefix) continues to clean them as
      they resolve. The new cluster-shape items live alongside.
- [ ] **AC-8 (manifest-type homogeneity).** A cluster MUST contain
      workspaces of the SAME `manifest_type` (`npm` xor `python`).
      Different manifest types use different install commands and
      cannot share a launch payload. Mixed signature + different type
      = separate clusters by (signature, type).
- [ ] **AC-9 (mixed cluster + per-workspace dedup correctness).** If
      cluster of {A, C} is open and a re-emission discovers the same
      signature only at A (C resolved), the cluster auto-dismisses
      (membership shrunk) and a new per-workspace item is emitted for
      A. Stable across multiple re-emissions.
- [ ] **AC-10 (telemetry).** `emit_undeclared_triage` return shape
      gains `"clusters": C` field (count of cluster items emitted
      this run). Backwards-compatible addition; existing callers
      reading `appended` / `dismissed` continue to work.
- [ ] **AC-11 (existing 13 TestEmitUndeclaredTriage cases pass).**
      Every pre-existing test (the N=1 case behavior) passes unchanged.

## Spec Impact

- **Classification:** none
- **NONE justification:** Internal producer-shape refinement; the
  SBOM compliance contract (workspaces with undeclared deps surface
  in operator's triage inbox with actionable resolution path) is
  unchanged. Action-unit shape is an implementation detail of how
  the same compliance signal is presented. ADR-056 documents the
  producer contract; this iterate refines the action-unit shape per
  ADR-057 (launch-surface principle).

## Out of Scope

- **Migration of pre-existing per-workspace items to cluster shape.**
  Historical inbox stays as-is; only new emissions cluster.
- **Cluster signature beyond sorted package names.** Pragmatic
  minimum. Versions / dep_type are NOT part of the signature.
  (Rationale: if workspace A has `pytest>=8` and B has `pytest>=9`,
  they share the same undeclared problem from the operator's
  perspective — install `pytest`. Splitting on version specifier
  would over-segment.)
- **Cross-producer cluster collapse** (compliance / github / ci /
  f0.5). Each producer has its own action-unit shape; out of scope.
- **Filtering dev-deps from triage.** Rejected by user — a client
  repo using Shipwright to build their own plugin legitimately wants
  dev-dep undeclared signals.

## Design Notes

n/a — no UI surface (data lives in `.shipwright/triage.jsonl`; webui
renders read-side and inherits the new shape automatically).

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `emit_undeclared_triage` writes new cluster-shape items | `webui` Triage-Inbox + `audit_detector.py` ADR-052 resolve scope + RTM `frId` cross-link consumers | `.shipwright/triage.jsonl` lines (JSONL) |

Boundary character: the cluster dedup-key shape is a **producer-defined
contract**. audit_detector's auto-resolve loop scopes by
`source="sbom"` + dedup-key prefix — both prefixes
(`sbom:undeclared:` and `sbom:undeclared-cluster:`) inherit the
existing source-based scope safely.

## Confidence Calibration

- **Boundaries touched:** `.shipwright/triage.jsonl` schema extension
  (new `sbom:undeclared-cluster:<hash>` dedup-key shape, additive
  alongside `sbom:undeclared:<path>`) + `emit_undeclared_triage`
  return-dict gained `clusters` field (additive). Single caller
  `update_compliance.py` updated to mirror the additive shape in its
  error-fallback dict.

- **Empirical probes run:**
  - Cluster formation N=1: per-workspace shape preserved
    (`test_single_workspace_keeps_per_workspace_shape`). PASSED.
  - Cluster formation N=2/3: collapse to single action-unit
    (`test_two_workspaces_same_signature_collapse`,
    `test_three_workspaces_same_signature_collapse`). PASSED.
  - Multi-signature partitioning: distinct signatures form distinct
    clusters (`test_two_signatures_emit_two_clusters`). PASSED.
  - Mixed N=1 + N>=2 in one run
    (`test_mixed_n_one_and_n_many_signatures`). PASSED.
  - Dedup-key shape: 12 hex chars after prefix, deterministic for
    same (signature, members) input
    (`test_cluster_dedup_key_shape_is_sha256_12`). PASSED.
  - Idempotency: same signature + same members → no new items
    (`test_cluster_idempotent_across_runs`). PASSED.
  - Launch payload fan-out: for-loop, alphabetical sort, all members
    listed, npm install + update_compliance commands
    (`test_cluster_launch_payload_lists_all_workspaces_sorted`).
    PASSED.
  - Launch payload shell-quote hardening for paths with spaces
    (`test_cluster_launch_payload_quotes_paths_with_spaces`). PASSED.
  - Auto-resolve cluster when ALL members clean
    (`test_cluster_auto_resolves_when_all_members_clean`). PASSED.
  - Membership shrink: cluster {A,B} → A only → cluster dismissed,
    per-workspace A emitted
    (`test_cluster_dismisses_then_reemits_when_membership_shrinks`).
    PASSED.
  - Membership grow: cluster {A,C} → {A,C,D} → old dismissed, new
    appended (HIGH from external review — dedup key encodes BOTH
    signature AND members)
    (`test_cluster_membership_grows_dismisses_old_emits_new`). PASSED.
  - Manifest-type homogeneity: npm + python with same name = 2
    separate clusters (different install commands)
    (`test_npm_and_python_signatures_emit_separate_clusters`). PASSED.
  - Telemetry: `clusters` field present in return dict
    (`test_telemetry_returns_clusters_count`). PASSED.
  - AC-7 back-compat: legacy item for workspace `a` shielded by
    shadow-key when `a` joins a cluster
    (`test_legacy_per_workspace_item_shielded_when_workspace_joins_cluster`).
    PASSED.
  - AC-7 back-compat for promoted legacy items: untouched by
    cluster emit
    (`test_legacy_per_workspace_items_untouched_by_cluster_emit`).
    PASSED.

- **Edge cases NOT probed + why acceptable:**
  - **Extreme cluster size (100+ members).** OpenAI L9: shell loop
    could become unwieldy. Practical cap: shipwright dev repo has
    13 plugins, real-world clusters max out around dozens of
    workspaces. Out of scope; observable degradation, not silent
    breakage.
  - **SHA-256 hash collision** (OpenAI L12). 12 hex = 48 bits of
    entropy; birthday-paradox collision threshold is ~16M items.
    Practical risk negligible. Full canonical signature stored in
    item `detail` field for debug-time disambiguation.
  - **Webui XSS injection via package/workspace names in
    title/detail** (OpenAI #8). Not introduced by this iterate
    (existing per-workspace path already aggregates untrusted
    package names). Belongs to a separate webui-side
    output-encoding hardening pass.
  - **Cross-producer cluster (audit/github/ci/f0.5)**. Each
    producer has its own action-unit shape; out of scope per spec.

- **Confidence-pattern check:** the external LLM review surfaced
  2 HIGH findings (auto-resolve dismissing legacy items, dedup-key
  not encoding membership) that I had NOT individually probed in
  the initial mini-plan. Both required design changes (shadow keys
  + member-list in hash), not just cosmetic tweaks. Per the
  asymptote heuristic, "are you confident?" attestation was
  uncorrelated with bug presence. **One additional probe before
  F0:** I traced the dismiss-loop logic with a hand-stepped
  scenario for AC-9 (cluster shrinks to N=1) and confirmed the
  shadow-key mechanism preserves the legacy `a` per-workspace key
  while dismissing the now-stale cluster key. The corresponding
  test `test_cluster_dismisses_then_reemits_when_membership_shrinks`
  verified this empirically. Stopping rule met.

## Verification (medium+)

- **Surface:** `cli`
- **Runner command:** `uv run --project plugins/shipwright-compliance pytest plugins/shipwright-compliance/tests/test_sbom_generator.py -v --color=no`
- **Evidence path:** `.shipwright/runs/iterate-2026-05-24-sbom-triage-cluster-collapse/f05.log`
- **Justification (only if surface=none):** n/a
