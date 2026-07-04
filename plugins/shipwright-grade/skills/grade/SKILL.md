---
name: grade
description: >
  Grade any git repository against the Control Grade rubric (A–F), read-only
  and deterministic. Projects a cold repo's git history + tests + configs into
  the same GradeInputs the compliance dashboard uses and reuses the shared
  scoring engine unchanged. Underivable dimensions render honest n/a and become
  the "what adopting Shipwright would light up" story.
  TRIGGER when: the user wants to grade a repository, score a repo's control
  posture, run /shipwright-grade, get a Control Grade for a local path, or
  evaluate how traceable/tested/controlled a codebase is.
  DO NOT TRIGGER for: writing code (/shipwright-build), fixing a bug
  (/shipwright-iterate), a full compliance audit of THIS project
  (/shipwright-compliance), or deployment (/shipwright-deploy).
---

# Shipwright Grade

**Read-only Control Grade for any git repository.** Point it at a local path;
it derives what it honestly can from the repo's git history, test inventory and
config files, maps those signals onto the shared `GradeInputs`, and reuses the
same `compute_grade` engine that powers the compliance dashboard and the
certification gate. Dimensions it cannot derive render **n/a** (excluded from the
score, never faked) and are surfaced as *controls Shipwright would light up*.

> **Honest ceiling.** A cold-repo grade is a *heuristic estimate from the
> outside* — it inspects history and structure, it does not verify behaviour.
> Every heuristic grade is labelled as such.

## Scope in this version (G1 — core projector)

- **Local path only.** `resolve_target()` is a seam so URL clone-and-grade slots
  in later; today it grades a local directory that is a git repository.
- **Local-only, no network.** Private repos never leave the machine. The
  network-only dimensions (CI JUnit pass-ratio, code-scanning SARIF) render
  `n/a`; `--allow-network` enrichment arrives in a later phase.
- **Scored today:** requirement traceability (heuristic) + change traceability.
  **Surfaced but unscored:** the static test inventory ("N tests across M
  frameworks — present, not executed"). **n/a today:** test-health score,
  security, dependency hygiene, size/maintainability, change reconciliation.

## Usage

```bash
# From the plugin directory (thin CLI wrapper over the core library):
uv run scripts/tools/grade.py <path-to-repo> [--format terminal|markdown|json]
```

- `--format terminal` (default) prints a compact A–F card with the top reasons.
- `--format markdown` emits the same view-model as Markdown.
- `--format json` emits the typed report view-model (stable schema) for tooling.

The grade is **deterministic** for a given repository snapshot: nothing outside
a footer depends on wall-clock time or randomness. For very large repos that
exceed the reused detectors' internal scan caps, feature inference is a
*labelled sample* (the requirement-traceability provenance is stamped
`sampled/truncated`) — so the sampling is surfaced, never hidden.

## What it does, step by step

1. **Resolve** the target to a local git repository (`resolve_target`).
2. **Snapshot** it once into a memoized `RepoContext` (file list, git metadata,
   detector outputs) under deterministic caps — no repeated filesystem/git
   traversal.
3. **Route** authoritative-vs-heuristic: a real `.shipwright/` event log/RTM
   would be an authoritative source (wired in a later phase); everything else is
   a labelled heuristic projection.
4. **Project** the git history into synthetic work-events and map them +
   detector outputs onto `GradeInputs`.
5. **Grade** with the shared engine, unchanged.
6. **Render** the typed report view-model to a terminal / markdown / json card.

## Safety

Read-only. All `git` calls go through one hardened runner: list-argument
(`shell=False`, never string-concatenated), with the target repo's fsmonitor,
pager and hooks disabled and `safe.directory=*` so grading another user's repo
can't fail on "dubious ownership". Every repo-derived string (commit subject,
author, filename) is treated as hostile: the terminal card strips ANSI/control
characters before printing. Deterministic caps bound the grader's own traversal
and git output (max commits, files, bytes-per-file, log bytes); the reused
detectors are bounded by their own internal scan caps.
