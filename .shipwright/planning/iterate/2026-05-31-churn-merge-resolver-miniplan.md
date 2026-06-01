# Mini-Plan — churn-merge-resolver

## Chosen approach: `events=union` + allowlisted regenerate-on-conflict resolver

Two complementary mechanisms, because the churn artifacts fall into two kinds:

1. **`shipwright_events.jsonl` is the source log itself** (append-only, not derivable). → built-in git `union` driver via `.gitattributes`. Both sides' appended lines are kept automatically (also honored by GitHub server-side). Resolver normalizes duplicate lines by `evt` id.

2. **All other churn artifacts are fully derived snapshots** (8 MDs + `architecture.md`; `test_results.json` is a non-audited snapshot). → a post-merge resolver that, for each *conflicted, allowlisted* file, re-runs its canonical single-producer generator against the merged working tree and re-stages. `test_results.json` is the one "pick `--ours`" case.

### Control flow (resolver, `shared/scripts/tools/resolve_churn_conflicts.py`)
```
conflicted = git diff --name-only --diff-filter=U
non_allow  = conflicted - CHURN_ALLOWLIST
if non_allow:                      # HARD SAFETY GATE
    print(non_allow); exit 2       # never touch real source — human resolves
for f in conflicted:
    if f == events.jsonl:          # normally already unioned by .gitattributes
        union+dedup-by-evt-id; git add
    elif f == test_results.json:   git checkout --ours f; git add f
    else:                          # derived MD
        git checkout --theirs f    # clear marker (content irrelevant — we regenerate)
        run canonical generator(f) against merged tree
        git add f
# caller commits with a message carrying `Run-ID: <run_id>`
```

### Integration point (one place, documented)
A new "Integrate origin/main" procedure in the iterate SKILL (referenced from F11 + `references/mid-flight-escalation.md`):
```
git fetch origin
git merge origin/main            # events.jsonl auto-unions; MDs may conflict
uv run resolve_churn_conflicts.py --project-root . --run-id <run_id>
git commit --no-edit  (message already carries Run-ID trailer via the resolver's prepared MERGE_MSG, or amended in)
```

### Generator mapping (single-producer reuse — no new producers)
| Allowlisted artifact | Generator re-used |
|---|---|
| `agent_docs/build_dashboard.md` | `update_build_dashboard.py` |
| `agent_docs/session_handoff.md` | `generate_session_handoff.py` |
| `agent_docs/triage_inbox.md` | `aggregate_triage.py` (tracked-snapshot mode) |
| `compliance/{dashboard,sbom,test-evidence,traceability-matrix,change-history}.md` | `update_compliance.py` |
| `architecture.md` | (curated — resolver leaves conflicted + reports; NOT auto-regenerated, see Open Q1) |
| `shipwright_test_results.json` | `--ours` (snapshot, not regenerated) |
| `shipwright_events.jsonl` | union + dedup-by-id |

## Rejected alternatives
- **Untrack the derived artifacts** — reverses the externally-reviewed 2026-05-27 decision and breaks the `audit_staleness` snapshot-provenance audit (the 3 agent-doc MDs are in its `DOC_REGISTRY`). The artifacts are tracked snapshots *by design*.
- **Custom per-file git merge driver** (`merge=shipwright-regen` via `install-hooks`) — (a) needs per-clone `git config` (fragile on fresh clones); (b) GitHub won't run it server-side; (c) a driver only sees base/ours/theirs temp files, not whole-repo state, so it cannot re-run a generator that needs merged events/specs. `union` is the one built-in driver that fits (events.jsonl) and needs no config.
- **Post-merge regen on `main` (CI/hook)** — breaks snapshot-provenance: the MDs would no longer be in the PR's `Run-ID:`-trailer commit, so the audit baseline is wrong and false-staleness (E1–E5) returns.

## Open questions for external review
- **Q1 `architecture.md`:** it is semi-curated (not purely generated). Auto-regenerating it could lose hand-written prose. Plan = resolver treats it as **report-only** (leave conflicted, list it) rather than regenerate. Is "report-only for curated docs, regenerate for pure-derived" the right split, or should `architecture.md` be excluded from the allowlist entirely (so a non-allowlisted conflict on it forces human resolution)?
- **Q2 Run-ID trailer on a merge commit:** is putting `Run-ID:` on the *merge* commit sufficient for `audit_staleness`, or must the regenerated MDs land in a separate trailer-bearing follow-up commit?
- **Q3 dedup semantics:** is dedup-by-`evt`-id on `events.jsonl` safe, or could two legitimately-distinct events share an id (collision)? Fallback = dedup by full-line identity only.
- **Q4 scope/complexity:** is this safely a single medium iterate, or should `events=union` ship first as an independent hotfix and the resolver follow as its own iterate?

## Implementation steps (TDD)
1. `.gitattributes` + events round-trip test (AC-1/AC-2) — RED→GREEN first (smallest, highest-leverage).
2. `resolve_churn_conflicts.py` skeleton + `CHURN_ALLOWLIST` + hard safety gate test (AC-3).
3. Per-artifact resolution (regenerate MDs / ours / union) + idempotency test (AC-4/AC-5).
4. Run-ID-trailer-on-resolution-commit test (AC-6).
5. SKILL "Integrate origin/main" procedure + `hooks-and-pipeline.md` matrix + Test-Update-Klausel drift tests (AC-7/AC-8/AC-9).
6. Dogfood integration of this branch + worktree cleanup (AC-10).
