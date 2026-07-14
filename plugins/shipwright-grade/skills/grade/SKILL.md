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

## ⚠️ Cross-repo contract — the Command Center renders this report

**This report has an external consumer.** The Command Center WebUI
([shipwright-webui](https://github.com/svenroth-ai/shipwright-webui)) renders the
`ReportModel` graph **field-for-field** on its *"Grade your repo"* screen —
deliberately, so that screen and the downloadable HTML report cannot tell different
stories. It consumes `grade.py --format json`, which is literally
`json.dumps(dataclasses.asdict(model))`, so **every field on `ReportModel` /
`DimensionView` / `DimensionProvenance` is on the wire**.

**A change to this shape requires a corresponding WebUI change.** A field renamed or
dropped here does *not* fail loudly over there — it renders a half-empty card, or worse,
a plausible-but-wrong one.

**Load-bearing fields** (`plugins/shipwright-grade/scripts/lib/report_model.py`):

| Field | Why the consumer cannot lose it |
|---|---|
| `dimensions[].status` (`ok`\|`gap`\|`n/a`) | Drives the **visual**. An `n/a` is drawn as *absent evidence* (a dashed track), **never** as a zero-score bar. No code path may synthesize a score for an underivable dimension. |
| `dimensions[].provenance` + `.detail` | The per-row *"how this was measured"* disclosure — the grade showing its work. |
| `network_enabled` / `network_note` / `network_enrichments` | **Exactly what left the machine.** This is the receipt for the product's *"read-only, no account"* promise and is shown verbatim. If it disappears, the WebUI loses its trust surface. |
| `honest_ceiling_note` | Rendered *above* the dimensions: it reframes a low grade as a finding about the **record**, not a verdict on the code. |
| `measurable_count`, `na_count`, `controls_shipwright_would_light[]` | The *"what adopting Shipwright would light up"* story. |
| `schema_version` | Lets the consumer detect a shape it does not understand and say so, instead of rendering nonsense. |

**Versioning (`report_model.SCHEMA_VERSION`, `major.minor`).**

- **MAJOR** — breaking: a field **removed, renamed or retyped**. The WebUI must **refuse
  to render** an unrecognised major ("report shape not recognised") rather than
  half-render it. Ship a matching WebUI change.
- **MINOR** — additive: a new field. The WebUI keeps rendering and ignores what it does
  not know, so an addition must **not** force a WebUI release — otherwise people would
  stop bumping at all.

**You are not asked to remember any of this.** `tests/test_report_model_contract.py`
diffs the emitted payload against the contract fixture **as published on `origin/main`**,
derives the bump that diff obliges, and fails until it has been performed. The published
fixture (`tests/contracts/grade-report-<version>.json`) is **frozen**: a breaking change
cannot be hidden by rewriting the pin, because the baseline is the one thing a pull
request cannot rewrite. To land a shape change: bump `SCHEMA_VERSION`, add a **new**
versioned fixture, and open the WebUI PR.

**The version is not a substitute for validation.** It is producer-controlled metadata; a
malformed payload can still claim `1.0`. The consumer validates the shape *and* checks
the version, and fails closed on an unknown major.

**Target resolution is part of the contract too.** `grade.py` accepts a local path **or a
remote** (shallow-cloned into a throwaway tempdir, purged after; `--no-clone` opts out).
The WebUI surfaces the clone step and its network cost explicitly — *"do not pretend a URL
is free"* — so keep that behaviour stable, or tell the WebUI. Pinned by
`tests/test_clone.py` and `tests/test_resolve_target.py`.

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
- **Local path → local-only by default; a public github.com URL → network-on by default.**
  A **local path** never leaves the machine without an explicit `--allow-network`
  (privacy-first — even a local repo with a public GitHub remote stays local-only).
  A **github.com URL / `owner/repo`** target is fetched from github.com anyway —
  its identity is already sent there to clone it — so GitHub enrichment (CI-JUnit
  pass-ratio, Scorecard check-runs, code-scanning SARIF, reviewed-PR provenance)
  defaults **on** for it. A **GitHub Enterprise / other host** is excluded from the
  default (enrichment queries github.com, a host that clone never contacted, so its
  slug must not leak) — pass `--allow-network` for it explicitly. A **private /
  unverifiable** remote still auto-disables enrichment unless you pass
  `--allow-network-private`, and when `gh` is unavailable/unauthed the grade falls
  back to the honest local projection — never a false `F`. Without enrichment the
  network-only dimensions render `n/a`.
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
- `--format json` emits the typed report view-model for tooling, carrying a
  `schema_version` (`major.minor`) so a consumer can detect a shape it does not
  understand. The stability of that shape is *enforced*, not merely asserted — see
  **Cross-repo contract** above.
- `--format html` emits a single **self-contained** report (inline CSS, zero
  external requests, restrictive meta CSP, theme-aware) to stdout — the
  lead-magnet artifact. Redirect it: `… --format html > report.html`. Every
  repo-derived string is HTML-escaped and control/bidi-stripped (it renders
  untrusted input), so the report is inert by construction.
- `--allow-network` opts into GitHub enrichment for the target's remote — already
  the **default for a URL / `owner/repo`** target, so the flag is only needed to
  force enrichment on for a **local path**. It **auto-disables on a private /
  unverifiable remote** unless you also pass `--allow-network-private`. The report
  stamps exactly which enrichments ran (what left the machine).

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
