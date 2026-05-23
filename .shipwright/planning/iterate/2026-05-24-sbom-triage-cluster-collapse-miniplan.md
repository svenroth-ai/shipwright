# Mini-Plan: SBOM triage producer — cluster-collapse

- **Run ID:** iterate-2026-05-24-sbom-triage-cluster-collapse
- **Spec:** `.shipwright/planning/iterate/2026-05-24-sbom-triage-cluster-collapse.md`

## Approach (single-file producer change)

`plugins/shipwright-compliance/scripts/lib/sbom_generator.py`:

### New helpers

```python
import hashlib

_TRIAGE_CLUSTER_PREFIX = "sbom:undeclared-cluster:"
_CLUSTER_MIN_MEMBERS = 2  # below this -> per-workspace

def _cluster_signature(undeclared: list[dict]) -> tuple[str, ...]:
    return tuple(sorted(d["name"] for d in undeclared))

def _cluster_dedup_key(signature: tuple[str, ...]) -> str:
    sig_str = "\n".join(signature).encode("utf-8")
    return f"{_TRIAGE_CLUSTER_PREFIX}{hashlib.sha256(sig_str).hexdigest()[:12]}"

def _cluster_launch_payload(
    workspaces: list[str], manifest_type: str
) -> str:
    install_cmd = "npm install" if manifest_type == "npm" else "uv sync --extra dev"
    regen_cmd = (
        "uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py"
        " --project-root . --phase iterate"
    )
    sorted_ws = sorted(workspaces)
    quoted = " ".join(_shell_quote_workspace(w) for w in sorted_ws)
    return (
        f"for d in {quoted} ; do \\\n"
        f"  ( cd \"$d\" && {install_cmd} ) || exit 1 ;\\\n"
        f"done \\\n"
        f"  && {regen_cmd}"
    )

def _cluster_title(members: list[dict], signature: tuple[str, ...]) -> str:
    return (
        f"SBOM: {len(members)} workspaces missing common "
        f"licenses for {len(signature)} package(s)"
    )

def _cluster_detail(members: list[dict], signature: tuple[str, ...]) -> str:
    pkgs = ", ".join(signature[:_UNDECLARED_TOP_N])
    more_pkgs = (f" (+{len(signature) - _UNDECLARED_TOP_N} more)"
                 if len(signature) > _UNDECLARED_TOP_N else "")
    ws = sorted(m["manifest_rel_path"] for m in members)
    return (
        f"Common undeclared ({len(signature)}): {pkgs}{more_pkgs}\n"
        f"Workspaces ({len(members)}): {', '.join(ws)}"
    )
```

### Refactored `emit_undeclared_triage`

1. Collect `groups` (unchanged).
2. **Bucket by (signature, manifest_type)** — same signature + same
   manifest_type = same cluster (AC-8 homogeneity).
3. For each bucket:
   - If `len(members) < _CLUSTER_MIN_MEMBERS` → emit per-workspace
     (unchanged code path; `current_keys` adds `sbom:undeclared:<path>`).
   - Else → emit one cluster item (`current_keys` adds the cluster key).
4. `current_keys` is a single set containing BOTH per-workspace and
   cluster keys.
5. Auto-resolve loop iterates ALL open `source="sbom"` items, dismisses
   any whose dedupKey is NOT in `current_keys`. Works uniformly for
   per-workspace and cluster items (AC-5, AC-9).

### Return-shape extension

```python
result: dict = {
    "appended": appended,
    "dismissed": dismissed,
    "clusters": clusters_emitted,  # NEW (AC-10)
}
```

## Tests (new in `test_sbom_generator.py`, in `TestEmitUndeclaredTriageClusters`)

13 new tests covering ACs 1-11:
- `test_single_workspace_keeps_per_workspace_shape` (AC-1, AC-11)
- `test_two_workspaces_same_signature_collapse` (AC-1)
- `test_three_workspaces_same_signature_collapse` (AC-1)
- `test_two_signatures_emit_two_clusters` (AC-6)
- `test_mixed_n_one_and_n_many_signatures` (AC-6)
- `test_cluster_dedup_key_shape_is_sha256_12` (AC-2)
- `test_cluster_idempotent_across_runs` (AC-3)
- `test_cluster_launch_payload_lists_all_workspaces_sorted` (AC-4)
- `test_cluster_launch_payload_quotes_paths_with_spaces` (AC-4)
- `test_cluster_auto_resolves_when_all_members_clean` (AC-5)
- `test_cluster_dismisses_then_reemits_when_membership_shrinks` (AC-9)
- `test_npm_and_python_signatures_emit_separate_clusters` (AC-8)
- `test_telemetry_returns_clusters_count` (AC-10)
- `test_legacy_per_workspace_items_untouched_by_cluster_emit` (AC-7)

All 13 existing `TestEmitUndeclaredTriage` tests must pass unchanged
(AC-11).

## Files to change

- `plugins/shipwright-compliance/scripts/lib/sbom_generator.py`
  (~80 LOC: 5 new helpers + refactored `emit_undeclared_triage`)
- `plugins/shipwright-compliance/tests/test_sbom_generator.py`
  (~300 LOC: 14 new tests)

## Rejected alternatives

- **N≥3 threshold:** rejected — pain starts at N=2 already. "Ein
  Iterate für das gleiche" applies whenever one operator action
  resolves multiple items.
- **Hierarchical parent/child schema:** rejected — too complex; the
  existing triage store doesn't model promote-cascade. The flat
  cluster pattern delivers the same UX with less risk.
- **Migration of legacy items:** rejected per AC-7 — symmetric
  emit/resolve gate (memory entry from iterate-2026-05-20).
  Asymmetric migration would risk mass-dismissing legitimate open
  items.
- **Including version specifiers in signature:** rejected — operator
  doesn't care that pytest>=8 vs pytest>=9, they want
  `uv sync --extra dev` in both places.

## Risk

- **Low.** Single-file producer change; new code path is additive.
  Existing `TestEmitUndeclaredTriage` (13 tests, all N=1 cases) must
  pass unchanged. Cluster path is exercised by 14 new tests.
- audit_detector ADR-052 compatibility verified: cluster dedup-key
  prefix structurally distinct from per-workspace; scoped resolve
  doesn't cross-dismiss.
