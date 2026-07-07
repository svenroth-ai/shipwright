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

## Authoritative vs heuristic

- **Authoritative** — a target with a healthy, current `.shipwright/` (a root-level
  `shipwright_events.jsonl` **and** `.shipwright/compliance/traceability-matrix.md`)
  is graded from its **own** records: the same `collect_all` → `build_grade_inputs`
  → `compute_grade` path the compliance dashboard uses. A grader-grade of a
  Shipwright project therefore **equals its dashboard grade by construction**.
- **Heuristic** — every other repo (and any corrupt / partial / **stale** /
  degenerate `.shipwright/`) is graded by the cold-repo projection from git history
  + structure, and labelled *heuristic*. Staleness is detected when the newest
  recorded work commit is not the working-tree HEAD; a commit-less (worktree-model)
  log is never false-flagged. The fallback is **fail-safe**: any ingestion error
  falls back to heuristic rather than crashing.

## Scope in this version (G4 — authoritative wiring + URL + plugin surface)

- **Local path or URL.** `open_target()` (over the `resolve_target` seam) grades a
  local git directory, or **clones a remote** (`https://…`, `git@host:owner/repo`,
  or `owner/repo` GitHub shorthand) into a throwaway tempdir that is purged even on
  a crash — shallow, single-branch, no-submodule, time- and size-capped, list-arg
  (injection-safe). `--no-clone` forbids cloning.
- **Local by default; network is opt-in.** Private repos never leave the machine.
  Without `--allow-network` the network-only dimensions (CI-JUnit pass-ratio,
  Scorecard check-runs, code-scanning SARIF) render `n/a`. (Cloning a URL target is
  the one unavoidable network step — separate from `--allow-network` enrichment.)
- **Scored locally (no network):** requirement traceability (git history);
  **size / maintainability** (static oversize-file ratio); **dependency hygiene**
  (lockfile → resolved licenses, when installed metadata is present). **Surfaced
  but unscored:** the static test inventory.
- **Scored with `--allow-network`:** **change traceability** (GitHub PR-association
  — the share of recent commits introduced by a reviewed, merged PR; the local
  git-log `#N` fallback anti-correlates with quality, so it is kept as a raw
  provenance line but is **n/a**, not scored, without the network); **test health**
  (best-available: CI JUnit → Scorecard check-runs → static inventory floor); and
  **security** (GitHub code-scanning SARIF, suppression-aware). **Always n/a:**
  change reconciliation — the Shipwright-only dimension (the funnel hook).

## Usage

```bash
# From the plugin directory (thin CLI wrapper over the core library):
uv run scripts/tools/grade.py <path-or-url> [--format terminal|markdown|json|html]
                                            [--allow-network] [--allow-network-private]
                                            [--no-clone]
# Examples:
uv run scripts/tools/grade.py .                        # a local repo
uv run scripts/tools/grade.py https://github.com/o/r   # clone-and-grade a remote
uv run scripts/tools/grade.py octocat/Hello-World      # GitHub owner/repo shorthand
```

- `--format terminal` (default) prints a compact A–F card with the top reasons.
- `--format markdown` emits the same view-model as Markdown.
- `--format json` emits the typed report view-model (stable schema) for tooling.
- `--format html` emits a single **self-contained** report (inline CSS, zero
  external requests, restrictive meta CSP, theme-aware) to stdout — the
  lead-magnet artifact. Redirect it: `… --format html > report.html`. Every
  repo-derived string is HTML-escaped and control/bidi-stripped (it renders
  untrusted input), so the report is inert by construction.
- `--allow-network` opts into GitHub enrichment for the target's remote. It
  **auto-disables on a private / unverifiable remote** unless you also pass
  `--allow-network-private`. The report stamps exactly which enrichments ran
  (what left the machine).

The grade is **deterministic** for a given repository snapshot: nothing outside
a footer depends on wall-clock time or randomness. For very large repos that
exceed the reused detectors' internal scan caps, feature inference is a
*labelled sample* (the requirement-traceability provenance is stamped
`sampled/truncated`) — so the sampling is surfaced, never hidden.

## What it does, step by step

1. **Resolve** the target with `open_target` — a local git directory in place, or a
   remote shallow-cloned into a purged tempdir (`resolve_target` is the low-level
   local validator behind the seam).
2. **Snapshot** it once into a memoized `RepoContext` (file list, git metadata,
   detector outputs) under deterministic caps — no repeated filesystem/git
   traversal.
3. **Route** authoritative-vs-heuristic: a healthy, current `.shipwright/` event
   log + RTM is graded from the target's own records (authoritative); everything
   else — and any corrupt/partial/stale/degenerate case — falls back to a labelled
   heuristic projection.
4. **Project** the git history into synthetic work-events; compute the G2 signals
   (size, deps, and — with `--allow-network` — test-health tiers + security) and
   map them + detector outputs onto `GradeInputs`.
5. **Grade** with the shared engine, unchanged (the size proxy uses one additive
   optional field, byte-identical for every existing caller).
6. **Render** the typed report view-model to a terminal / markdown / json / html
   card — each renderer consumes the view-model directly (no markdown-as-IR) and
   escapes/strips every repo-derived string for its output context.

## Interactive vs standalone

- **Standalone** (`grade.py`, the `npx`/`uvx` seed): **never blocks**. It reads no
  stdin, asks nothing, and grades deterministically — the same repository snapshot
  always yields the same grade.
- **Interactive** (`/shipwright-grade` inside Claude Code): MAY ask **at most two**
  clarifying *enrichment* questions when an answer would materially sharpen the
  report (e.g. "a suite is present but no CI results were found — grade it
  present-but-unverified, or do you have a CI run to point at?"). Answers are
  **provenance-stamped** and are *enrichments only*: they **never change the base
  deterministic grade** unless the user explicitly selects a **documented override
  mode** (e.g. `--run-tests`, a future fast-follow). The base grade a reader sees
  is always reproducible from the repository state alone.

## Safety

Read-only. All `git` calls go through one hardened runner: list-argument
(`shell=False`, never string-concatenated), with the target repo's fsmonitor,
pager and hooks disabled and `safe.directory=*` so grading another user's repo
can't fail on "dubious ownership". Every `gh` call is likewise list-argument and
gated behind `--allow-network`. **Untrusted input is first-class:** repo-derived
strings are ANSI/control-stripped before printing, and untrusted **CI JUnit XML
is parsed with a hardened parser** (`defusedxml`, DTDs rejected → XXE /
billion-laughs safe). A `403`/rate-limit/auth-failure/absent-`gh` degrades
deterministically to the next tier or `n/a`, never a crash and never a false
clean. Deterministic caps bound the grader's own traversal and git output (max
commits, files, bytes-per-file, log bytes).

**Untrusted-clone hardening.** A URL target is cloned by the same list-argument
runner into a `tempfile.TemporaryDirectory` purged on exit (even on a crash). The
clone is **scheme-allowlisted** (only `https://`, `git@host:owner/repo`, or
`owner/repo`; `http://`/`git://`/`file://`/`ext::…` are rejected), **shallow +
single-branch + no-tags + no-submodule-recursion**, with the `ext` and `file` git
transports disabled — so a hostile `.gitmodules` or `ext::` remote can neither
execute a command nor read local files. Time- and size-caps bound a slow or huge
remote.
