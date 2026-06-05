---
campaign: 2026-06-05-track-triage-jsonl
branch_strategy: per-sub-iterate
created: 2026-06-05
expands_triage: trg-2fb7d3bc
closes_findings: []
---

# Campaign: 2026-06-05-track-triage-jsonl

## Intent

Git-track `.shipwright/triage.jsonl`, mirroring how `shipwright_events.jsonl` is
handled: **the jsonl is the SSoT; the `.md` snapshot becomes a pure derived
view** (like the RTM). Today the canonical backlog lives only in a gitignored,
machine-local file, and the one repo-persistent representation
(`agent_docs/triage_inbox.md`) is rendered per-worktree from an ephemeral
SBOM-only jsonl — so it **diverges completely** from the live backlog the WebUI
shows.

Full analysis, root-cause chain, the events.jsonl reference model, ACs, and
gotchas live in the evidence-path plan doc:
`.shipwright/planning/iterate/proposed-track-triage-jsonl.md`.

**Tracking model** (mirrors `2026-06-02-hook-consolidation` / `trg-721b1765`):
- **Anchor:** `expands_triage: trg-2fb7d3bc` — the stable, hand-authored
  `kind: improvement` / `source: architecture` triage item representing this
  engineering work. Not producer-owned → does not auto-dismiss.
- **Closed findings:** none yet — this is forward-looking infrastructure, not a
  fix for an existing producer symptom.

## Why A and B are prerequisites

Without A and B we would commit a **churning, bloated** log into permanent git
history: the SBOM cluster producer mints a fresh id every run under membership
drift (the 161-and-growing dismissed pile), and tracking that as-is bakes the
churn engine + the dismissed bloat into history forever. A stabilizes the id; B
compacts the pile **before** it enters tracked history; only then is C safe.

## Sub-iterates (A → E)

| ID | Title | Complexity | Status | Branch | Commit |
|----|-------|-----------|--------|--------|--------|
| A | B-churn: stabilize SBOM cluster identity (signature-only id) | small | in_review | iterate/sbom-cluster-stable-id | — |
| B | GC / compaction of the dismissed pile (one-off tool + run) | small | pending | — | — |
| C | Tracking flip (gitignore negation + scaffolder self-heal + churn allowlist/resolver + F6 add + finalize simplify) | medium | pending | — | — |
| D | adopt / project wiring | small | pending | — | — |
| E | docs + glossary + hooks-matrix + monorepo migration | small | pending | — | — |

> **Dependency order:** A, B → C → D → E. A and B are independent of each other
> and could bundle, but are kept separate for clean blast-radius isolation.

## Sub-iterate A — scope note (supersedes part of the cluster-collapse iterate)

A decouples cluster **identity** (now a stable signature + manifest_type hash)
from cluster **content** (the member list). This **reverses the
membership-encoding decision** made under external-review OpenAI #2/#3 in
`proposed-sbom-triage-cluster-collapse.md` (its AC-9 / the "membership grows →
old-dismiss + new-emit" behavior). Membership drift while ≥2 members keep the
signature now reuses the SAME id → no churn, the dismissed pile stops growing
(campaign AC-4).

**Body-fidelity deferral (documented limitation):** the triage store is
append-only (`append` + `status` events only; body fields are written once at
`append`). So while A makes the id stable, the open item's **body** (workspace
list / launch payload) reflects membership-at-first-emit until the signature
fully resolves and re-emerges. Faithful re-render needs a triage-store `amend`
primitive — a **separable shared-contract + WebUI change**, out of A's
producer-only scope ("Touches `sbom_generator.py` + `test_sbom_generator.py`").
Tracked as a follow-up triage item rather than ballooning A across two repos.
A's *role* — stop the id-churn so the tracked log (C) doesn't churn forever — is
fully delivered without it.

## Campaign-level acceptance criteria

- [ ] **AC-1.** `.shipwright/triage.jsonl` is git-tracked in the monorepo and in
      every newly adopted/created project (negation present; scaffolder no longer
      ignores it; already-adopted repos self-heal on re-run). *(C, D)*
- [ ] **AC-2.** A fresh iterate worktree inherits the canonical backlog; the
      committed `triage_inbox.md` matches the WebUI. No more SBOM-only
      overwrites on merge. *(C)*
- [ ] **AC-3.** Concurrent appends across worktrees reconcile without manual
      conflict resolution; `append`+`status` shared-id semantics produce no
      false dedup warning/drop. *(C)*
- [x] **AC-4.** SBOM cluster identity is stable across runs under membership
      drift (no fresh id when 8↔9↔10 workspaces); dismissed pile stops growing.
      *(A — landed)*
- [ ] **AC-5.** `.gitattributes merge=union` for triage in the monorepo; no
      `.gitattributes` written to target projects. *(C)*
- [ ] **AC-6.** Docs + glossary + hooks-and-pipeline matrices updated; monorepo
      snapshot migrated; 161-item dismissed pile compacted. *(B, E)*

## Notes / progress log

- **2026-06-05 (A):** signature-only `_cluster_dedup_key(signature,
  manifest_type)`; member list dropped from the hash, `manifest_type` folded in
  to keep npm/python clusters distinct (AC-8). Inverted
  `test_cluster_membership_grows_*` to assert stable id; added
  shrink-within-range + dedup-key-independent-of-membership tests. Full
  compliance suite green (617 passed). Body-amend fidelity filed as follow-up.
