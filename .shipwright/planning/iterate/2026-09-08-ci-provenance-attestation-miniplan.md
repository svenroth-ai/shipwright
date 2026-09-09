# Mini-Plan: CI Provenance Attestation

- **run_id:** iterate-2026-09-08-ci-provenance-attestation
- **Final design (post Architecture Review, Round 3)** — step-conclusion via
  the GitHub Actions Jobs API, no artifact/digest layer. See the iterate
  spec's `## Design history` for the full three-round trail.

## Files to create/modify
- `.github/workflows/ci.yml` (edit — step id + output line + one new step)
- `shared/scripts/ci_provenance.py` (new, **flat**, not under `lib/`)
- `shared/scripts/tools/ci_provenance_check.py` (new)
- `shared/tests/test_ci_provenance.py` (new)
- `shared/scripts/tools/tests/test_ci_provenance_check.py` (new)
- a CI-workflow-shape test asserting the new step's `if:`, output-line
  placement, and step-name match against `PROVENANCE_STEP_NAME`
- `.shipwright/agent_docs/decision_log.md` (new ADR entry, written as a
  run_id-keyed decision-drop at F3, not appended directly from the iterate)

## Work breakdown

1. **`ci.yml` wiring** — give the existing drift-check step `id:
   manifest_drift`; insert `echo "code=$code" >> "$GITHUB_OUTPUT"`
   immediately after the existing `code=$?` line and BEFORE the `set -e` /
   branching (so it runs on every exit path, including `exit "$code"`). New
   step, name matching `PROVENANCE_STEP_NAME` (import the Python constant's
   value into the YAML-shape test, don't hardcode it twice by hand — decide
   the exact string once, e.g. "Confirm traceability manifest verified (no
   drift)" — contains no `GATE_NAME_KEYWORDS` token, confirmed against
   `check_ci_gate_coverage.py`'s list): `if: steps.manifest_drift.outputs.
   code == '0'`, `run: echo "manifest verified clean at ${{ github.sha }}"`.
   No `continue-on-error` needed — a bare `echo` cannot fail. Test: parse
   the YAML, assert the `if:` string literally, assert the echo-output line
   precedes any `exit "$code"` in the drift-check step's script body, assert
   the new step's `name:` equals `ci_provenance.PROVENANCE_STEP_NAME`
   (import the Python module in the test, don't duplicate the literal).

2. **`ci_provenance.py` predicate** (flat, `shared/scripts/`) —
   `PROVENANCE_STEP_NAME = "Confirm traceability manifest verified (no
   drift)"` (or whatever step 1 settles on — single source of truth).
   `resolve_ci_verification(commit, *, project_root, workflow_file=
   "ci.yml") -> CIVerification(status, detail, run_id=None)`. Internals:
   a. Validate `commit` against `^[0-9a-f]{40}$` (exactly 40 — GitHub's
      `head_sha` filter is an exact match; Stage-3 doubt review) and
      `workflow_file` against a bare `*.yml`/`*.yaml` filename;
      `status="error"` if either fails.
   b. `owner, repo = github_api.owner_repo(project_root)`; `status="error"`
      (with detail) if `None`.
   c. Own small `_gh_api(path, *, cwd)` helper in THIS file (does not touch
      `github_api.py`/`security_findings.py`) — resolve the default branch
      via `gh api repos/{owner}/{repo}` (this module's OWN call, not
      `github_api.default_branch()`, which is cwd-dependent).
   d. `gh api repos/{owner}/{repo}/actions/workflows/{workflow_file}/runs?
      head_sha={commit}&status=success&per_page=100`.
   e. Filter to `event=="push"` AND `head_branch==<resolved default>` AND
      `conclusion=="success"`; sort by `run_started_at` (fallback
      `created_at`) descending.
   f. For EACH qualifying run (not just the newest): `gh api
      repos/{owner}/{repo}/actions/runs/{run_id}/jobs`, find the step named
      `PROVENANCE_STEP_NAME` in any job's `steps[]`, read its `conclusion`.
      First `"success"` found → `status="verified"`, `run_id` set. No
      qualifying run has it → if `len(qualifying) > 0`: `status=
      "not_verified"`; else `status="no_record"`.
   g. Any `gh` call failure (missing binary, timeout, bad JSON) at any step
      → `status="error"` with a detail string naming which call failed,
      never a crash, never silently folded into `no_record`.
   Test: monkeypatch the subprocess boundary (module-object level, ADR-045
   convention) with scripted `gh api` responses covering: verified (one
   qualifying run, step success), not_verified (qualifying run(s) exist,
   step never success), no_record (zero qualifying runs — including a case
   where runs exist for the head_sha but ALL are `pull_request`-triggered —
   AC8, the real forgery test), error (subprocess raises / bad JSON /
   invalid commit), and the multi-run case (AC9 — newest qualifying run's
   step `"skipped"`, an older qualifying run's step `"success"` →
   verified).

3. **`ci_provenance_check.py` CLI** — argparse `verify --commit
   [--project-root .]`. Calls the predicate directly (no local manifest
   read at all — the whole digest/manifest-reading step from Round 1/2 is
   gone), prints one JSON line `{status, detail, run_id}`, maps status →
   exit code (0 verified / 3 not_verified / 4 no_record / 2 error). Test:
   at least one real-subprocess CLI invocation (not just calling `main()`
   in-process) — Internal Review's warning that `shared/tests`'s conftest
   sys.path setup can mask the import-path bug class this flat-module
   placement is designed to avoid.

4. **ADR** — one paragraph: the unforgeability property (push to default
   branch + `conclusion=success`, verified against the API's own run
   object), and a one-line note on the Round-3 simplification (why no
   artifact was needed).

## Test strategy
- Predicate tests via the `gh`-subprocess seam, monkeypatched at the module
  object per ADR-045 convention — 5 branches (verified / not_verified /
  no_record-zero-qualifying / no_record-only-PR-runs (AC8) / error) plus the
  multi-run search case (AC9).
- CLI contract test: in-process for the JSON/exit-code mapping, PLUS one
  real-subprocess invocation.
- One CI-YAML-shape test pinning the `if:` gate, the output-line placement,
  and the step-name/`PROVENANCE_STEP_NAME` match literally.
- No E2E/web surface — `surface_verification.justification` in the spec
  covers this.

## Alternative approaches (considered, rejected)

See the iterate spec's `## Alternative approaches (rejected)` and
`## Design history` — GitHub native Artifact Attestations (Round 1) and this
iterate's own first-draft artifact/digest design (Round 1/2, superseded in
Round 3 by Architecture Review's step-conclusion simplification).
