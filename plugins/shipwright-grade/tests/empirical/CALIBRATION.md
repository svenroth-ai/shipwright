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

## Current finding (G5 — pending calibration)

The recorded proof subset shows the gate is **RED by design**:

| repo | grade | why |
|---|---|---|
| `pallets/flask` (exemplary) | **F (19.9)** | change-traceability classifier credits only 24/500 commits; network test-health reads 0/20 |
| `expressjs/express` (average) | **F (49.0)** | 324/500 traced, 17/19 CI test-health |
| `request/request` (deprecated) | F (41.2) | static test inventory, thin history |

Ordering is **inverted** (exemplary scores lowest). Two projection heuristics need
tuning — the traceability classifier (under-credits flask's commit style) and the
network test-health tier (mis-reads flask as 0/20). That work is a **follow-up
calibration iterate** (it changes how every repo grades, including the dogfood
monorepo currently at A, so it needs its own TDD cycle + an A-grade regression
guard). The G5 deliverable is the harness + the gate that surfaced this; the RED
gate correctly blocks launch until the projector is calibrated.
