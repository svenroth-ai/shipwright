# Empirical calibration suite (`-m empirical`)

Unit fixtures prove the code does what we coded; they cannot prove the **rubric
grades reality sensibly**. This suite points the grader at real, well-known OSS
repos pinned to a commit SHA and checks the grades match informed human
judgement — the framework's own "empirical probe over unfalsifiable confidence"
principle applied to the grader itself. The rendered reports double as the
launch-page example gallery.

## How it runs

```bash
# Offline (default): replay recorded fixtures, assert bands + ordering.
uv run tests/empirical/run_empirical.py --out gallery
pytest -m empirical                      # same assertions, pytest reporting

# Refresh (network + gh auth): re-record fixtures for the selected repos.
uv run tests/empirical/run_empirical.py --refresh --repos flask,express,request
```

- **Manifest:** `repos.yaml` — each entry pins `{name, url, pinned_sha,
  expected_band, tags}`. Calibration entries (tag `exemplary|average|poor`) assert
  a band + the cross-tier ordering; edge entries (`expected_band: null`) assert
  only robustness (graded, no crash, budget held).
- **Determinism = SHA-pin + record/replay:** the projected `GradeInputs` +
  report-extras for each pinned SHA are cached under `fixtures/`. Replay runs the
  engine (`compute_grade`) offline, so it still catches rubric regressions and
  does not rot when GitHub expires run logs (~90d). See `fixtures/README.md`.
- **CI:** `.github/workflows/grade-empirical.yml` (`workflow_dispatch`) is the
  opt-in launch gate — network + gh, records live, uploads the gallery, and its
  exit code blocks the public launch. `ci-only` (huge/expensive) targets are
  recorded there, not in the committed proof subset.

## The calibration loop (the one rule that matters)

We assert **bands + relative ordering** (`exemplary > average > poor`), never
exact scores — robust to intentional engine tweaks. When a real grade contradicts
human judgement, that is the signal to refine the **projection heuristics**
(`grade_inputs_projector` / the signal tiers, plan §4/§5) — **NEVER** the shared
`control_grade` scorer. The engine stays the single source of truth (a cold-repo
grade must equal the dashboard grade by construction); only the
cold-repo→`GradeInputs` mapping is tuned, and every tune re-runs the whole suite
(`--refresh`) to check for ordering regressions. A drift in an *exact* score shows
up as a fixture JSON diff — a review signal, not a red build.

## G6 calibration (2026-07-06 — gate GREEN)

G5's gate was **RED by design** (every real repo graded F, ordering inverted). G6
root-caused each miscalibration on **live data (5 repos)** and tuned the projection
heuristics ONLY. Full evidence: the iterate spec
`.shipwright/planning/iterate/2026-07-06-grade-g6-projector-calibration.md`.

### Why every cold repo graded F
The honesty gate (`_grade_gate._COLLAPSE_PILLARS`) caps the headline to F when a
measurable pillar < 0.5. `change_traceability` (= git-log PR/issue refs / commits)
is < 0.5 for EVERY cold OSS repo, because squash-merge strips PR refs from commit
subjects. That is the shared scorer (correct — unchanged); the projected **input**
was the problem.

### The three projector fixes (heuristics only, scorer untouched)
1. **test-health reads matrix-named CI checks.** flask's test legs are named by
   matrix (`3.12`, `PyPy`, `Windows`) — no test-word — so the name-regex read 0/20.
   All are green `github-actions` checks. Now the tier keys on the CI-system **app
   slug** (OpenSSF Scorecard's actual CI-Tests signal), and a repo with a CI setup
   whose recent merged PRs show no passing CI test check scores LOW (decayed gate),
   not n/a. flask 0/20 → **20/20**.
2. **change-traceability from the network, not git-log.** git-log provenance
   *anti-correlates* with quality — flask (best) scored 0.14, *below* request
   (worst) at 0.20, because disciplined squash-merge leaves reference-free subjects.
   Now a network **PR-association** ratio (`associatedPullRequests`, SLSA
   code-review provenance) overrides the count when the network resolves; git-log
   stays the offline fallback. flask 0.04 → **0.51**.
3. **requirement-traceability ignores self-referential routes.** Route detection
   fired on flask's OWN library source (`@app.route` docstrings in `src/flask/*.py`),
   inflating a phantom requirement surface (frs=3, coverage 1/3) that dragged flask
   below express. A route whose framework name is a path segment of its source file
   is dropped → flask req **n/a** (no genuine app requirement surface).

### The uncomfortable truth (why the tiers were restructured)
On the MEASURABLE cold-repo signals, **control posture ≠ reputation**. express is
*more* traceable than flask (98% of changes via reviewed PRs vs flask's 51% squash +
direct releases), so "flask exemplary > express average" cannot hold without a
Goodhart fudge. The honest, defensible ordering is **well-run > deprecated**.

### Calibrated grades (live, at the pinned SHAs) — cold grades cap at B
| repo | tier | grade | why |
|---|---|---|---|
| `expressjs/express` | exemplary | **B** 89.0 | A on every measurable axis (green CI, 98% PR provenance) → capped to B |
| `addyosmani/agent-skills` | exemplary | **B** 89.0 | A on every measurable axis (green CI, tiny files) → capped to B |
| `obra/superpowers` | exemplary | **B** 87.5 | full PR provenance; no CI → test-health n/a (living repo → not F) |
| `pallets/flask` | exemplary | **C** 78.8 | green CI, but 51% PR provenance (squash + direct releases) |
| `request/request` | poor | **F** 43.8 | deprecated; CI config remains but 0 passing on recent merges |

Ordering: exemplary (min flask 78.8) **>** poor (max request 43.8). No inverted
ordering; each band defensible.

**Reputational guard (G5):** only `request/request` (officially deprecated /
self-EOL) grades F. A *living* repo without a CI gate scores test-health n/a → lands
in B/C, never a public F (see `obra/superpowers`).

### A is authoritative-only — a cold grade caps at B (2026-07-06 follow-up)
Change-reconciliation (are changed requirements re-verified?) is a load-bearing
control the Control Grade's own thesis rests on, and it is **structurally
unmeasurable for a cold external repo** — no RTM, no per-change behavior impact. So
the projector declares it the ONE `expected_dimensions` entry, and the honesty gate
(unchanged) caps every cold grade at **B** ("Controlled, minor gaps"): the headline
can't read "Under full control" over a control it cannot even see. The verdict says
so factually — *"verification incomplete — change reconciliation not measured"*; the
per-dimension table still shows the full A-level detail on the measurable axes.

This is **heuristic-only**: the authoritative path sets its own `expected_dimensions`
from real records, and reconciliation IS measured there (the dogfood monorepo scores
it **1.0**), so an adopted Shipwright repo can still reach A. The result is an honest
upgrade path — *free grader → at best B; adopt → A becomes reachable* — not a dark
pattern. A cold repo now spans **C..B**; **A is authoritative-only.**

### Change-traceability is n/a in local-only mode (2026-07-07 follow-up)
G6 fix #2 replaced the git-log count with the network PR-association ratio *when the
network resolves* but **kept the git-log count as the local offline fallback** — which
still scored (and could F-collapse) the dimension. That was the residual shitstorm: a
well-run repo with clean Conventional Commits but no `#N` refs (0/N git-log provenance)
graded **F "out of control"** in the default local-only mode. Because git-log
references *anti-correlate* with quality, the local fallback is worse than useless as a
graded signal. So change-traceability is now gated on `change_traceability_measurable`
(engine default True; the cold projector sets it False in local-only): with no
trustworthy provenance it renders **n/a** ("needs --allow-network"), exactly like
test-health/security — never scored off git-log, never an F-collapse. A local cold
grade of a well-run repo now lands **B** (reconciliation cap), never F.

**This does NOT touch the network empirical suite above:** with `--allow-network` the
PR-association tier still scores change-traceability, so every fixture here re-grades
identically (the recorded `GradeInputs` replay with the field defaulting True). The
**authoritative** path (real event-log provenance) sets the flag True, so the dogfood
grade is unchanged.

### Dogfood
The monorepo (+ WebUI) grade **authoritatively** (own `.shipwright/` records via the
unchanged engine), so the projection calibration does not touch them: the monorepo
re-grades **A 100** with the calibrated code, and `test_authoritative.py`'s dogfood
guard pins that the authoritative path never runs the projection.
