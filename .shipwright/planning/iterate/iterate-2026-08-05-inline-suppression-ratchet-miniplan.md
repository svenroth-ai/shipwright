# Mini-Plan: inline-suppression-ratchet

- **Run ID:** iterate-2026-08-05-inline-suppression-ratchet
- **Complexity:** medium

## Chosen approach — per-rule counting ratchet, shared leaf + live guard

### Step 1 — `shared/scripts/inline_suppressions.py` (new shared LEAF)

Top-level `shared/scripts/`, **not** `shared/scripts/lib/`, so the compliance
dashboard can import it by bare module name. This is the established
ADR-044/045 pattern for exactly this need — `accepted_risk_scan.py` and
`gh_action_tag_owner.py` are the precedents, both consumed by a plugin and by
shared tooling without either importing the other's package.

Public surface:

| Name | Purpose |
|---|---|
| `BASELINE_NAME` | `shipwright_inline_suppressions.json` (repo-root, `shipwright_` config prefix) |
| `SCHEMA_VERSION` | `1` |
| `BaselineError` | raised on a present-but-invalid baseline — fail closed |
| `scan_sites(project_root)` | `{rule_id: [site, …]}` discovered from source |
| `load_baseline(project_root)` | `{rule_id: entry}`; absent → `{}` |
| `reconcile(project_root)` | `{ratchets, unrecorded, shrunk, ok}` |

Discovery regex matches the **explicit** form only, comment-marker anchored:
`nosemgrep:` followed by a comma-separated rule-id list. Rule ids are
normalised (stripped, empty dropped). A trailing rule list on a code line
(`shell=True,  # nosemgrep: …`) and a standalone comment line both match —
both forms are in use in this repo.

**REVISED after external review — the file set is derived from git, not from a
source-extension allowlist.** The plan originally limited the walk to allow-listed
source extensions; external review (GPT #2) flagged that as a bypass class — a
suppression in a file type nobody thought to list would be invisible. The
delivered design instead reads `git ls-files`, which is both broader and exactly
the property being measured ("source-controlled"). A non-git tree falls back to
a walk skipping `.git`, `.venv`, `node_modules`, `__pycache__`, `.worktrees`,
`site-packages` — and reports `mode: "walk"` so the narrower scope is never
presented as a clean result. Sibling worktrees must not be counted: this repo
keeps checkouts under `.worktrees/`, and counting them would make the
measurement depend on unrelated in-flight work.

**Prose formats are then excluded** (`.md`/`.rst`/`.txt`/…) — a *denylist of
prose*, never an allowlist of code, so a missed entry is a loud false positive
rather than a silent miss. This was not in the plan: the first real measurement
produced 7 phantom sites and 2 invented rule ids from a document explaining the
syntax. See the spec's probe log.

`rationale_ref` is validated with `accepted_risks.DECISION_REF_RE`,
**imported** rather than copied. The register already duplicates that regex
once (into `verifiers/ci_supplychain`) for a self-containment reason that does
not apply here: both modules are top-level shared leaves in the same
directory, so a bare import is exactly the ADR-045-safe shape.

### Step 2 — `shipwright_inline_suppressions.json` (baseline, decided autonomously)

Per the operator's grant. Seeded from the measured truth of this repo —
**5 rules, 20 sites** as finally measured (the plan's pre-implementation
estimate of "4 rules, 18 sites" came from a shell `grep` whose comma-splitting
collapsed the two `python36-compatibility-Popen` rules into one) — with
`max_sites` set to the **exact current count**, not a headroom-padded number.
A ratchet whose baseline starts loose is a ratchet that permits the first
regression for free.

`rationale_ref` for all four seed entries is this run id
(`iterate-2026-08-05-inline-suppression-ratchet`) — a form `DECISION_REF_RE`
accepts. It cannot be `ADR-NNN`: ADR numbers are assigned at
`/shipwright-changelog` release, so a number written now would be a guess.

### Step 3 — `shared/tests/test_inline_suppressions.py`

Unit tests + synthetic negative controls on `tmp_path` fixtures: growth
blocks, unrecorded rule blocks, corrupt baseline fails closed, absent baseline
does not silence, shrink is advisory, prose mentions are not counted,
`.worktrees/` is not walked, round-trip probe over the baseline parse.

### Step 3b — `shared/scripts/tools/inline_suppressions_cli.py` (+ its tests)

Not in the original plan; added because the baseline `_readme` and the register
header both need a command to point an operator at, and because the register's
own `accepted_risks_cli.py` is the precedent. It is an operator front-end, NOT
the enforcement path — the guard in Step 4 calls `reconcile` directly. Its
exit-code contract (0 clean / 1 drift / 2 baseline-unreadable) is pinned in
`shared/tests/test_inline_suppressions_cli.py`.

### Step 4 — `shared/tests/test_inline_suppressions_repo_guard.py`

The live guard: runs `reconcile` against THIS repo and fails with the
actionable diagnostic. Separate file, mirroring the register's own
guards/controls split, and keeps both files under the 300-LOC cap.

### Step 5 — dashboard block in `ci_security.py`

After the accepted-risks table: a count block naming the rules and stating
that inline suppressions are deliberately **not** register-tracked, with the
ratchet named as the control that replaces it. Loaded through the same
degradation-tolerant shared-import path `accepted_risk_view._load_shared`
already uses, so an unavailable shared tree degrades to a note rather than an
exception.

### Step 6 — prose pointers + decision drop

Update the three prose statements of the position
(`accepted_risks.py` docstring, `accepted_risk_scan.py` docstring,
`shipwright_accepted_risks.yaml` header) to name the decision and the ratchet.
F3 writes the decision drop.

## Alternative considered — reuse `shipwright_bloat_baseline.json` + `anti_ratchet.py`

**Rejected.** The bloat machinery keys on `{path: LOC}` and measures a *file's*
size; this keys on `{rule: site-count}` measured across the *whole tree*.
Bending one into the other would mean either a fake `path` per rule or a second
entry shape inside a baseline whose every consumer assumes the first. The
honest cost of a separate module is ~1 file; the cost of the overload is a
permanently ambiguous baseline schema. The *pattern* is reused (baseline JSON,
block-on-exceed, advisory-on-shrink, fail-closed-on-corrupt); the storage is
not.

## Risk flags — re-checked against the real diff (Step 3.4), all four FALSE

Run through `risk_detectors` over `git diff --cached --name-only` (17 files at
the time of the check; 21 in the final staged diff once the CLI, its tests and
the review record were added — none of the four added paths matches any
detector pattern either, re-confirmed by the spec reviewer):
`cross_component` False · `touches_ci_supplychain` False · `touches_io_boundary`
False · `touches_build` False.

- `touches_io_boundary` — the plan **predicted this would fire and it does
  not**. `is_io_boundary_change` is path-only; the content-keyword half is
  deliberately deferred (documented in `risk_detectors.py`), and
  `shipwright_inline_suppressions.json` matches none of the five path patterns.
  The Boundary Probe was run anyway and is recorded as voluntary. See the spec's
  Affected Boundaries for the full correction.
- `touches_migrations` from Stage 1 is confirmed a **false positive** — a prose
  match on the word "schema" in the task description.
- `cross_component` — not fired, as predicted: no hook file, no
  merge/churn/event-log resolver, no phase validator, no campaign drain.
  Deliberately kept that way by declining the pre-commit hook (spec Out of
  Scope), so no integration-coverage row is owed.
- `touches_ci_supplychain` — not fired: no `.github/workflows/**` change.

Complexity stays **medium** on scope, not on a safety floor — there is none.
