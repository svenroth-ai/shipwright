# Iterate: SBOM data quality / honesty (AR-04)

- **Run ID:** iterate-2026-06-28-sbom-honesty
- **Intent:** CHANGE (compliance renderer + collector)
- **Complexity:** medium (classifier said `small`/history; upgraded for scope: new
  lockfile parser, cross-cutting license/version resolution, generator output-contract
  change, a documented-behavior change, tracked-artifact regen)
- **Spec Impact:** MODIFY (changes how `sbom.md` is rendered; no new FR)
- **Source spec:** `Spec/course-launch-compliance-control-coverage.md` → **AR-04**
  (triage anchor `trg-268c0655`, lane B)

## Problem (verified empirically against the real repo)

`/.shipwright/compliance/sbom.md` (the committed artifact):
- lists **`openai` twice** — `2.30.0` (root `pyproject`) and `1.0.0` (plan `pyproject`)
- shows several licenses as **`-`** while the footer claims *"all resolved dependencies
  are permissively licensed"* — a weasel verdict that hides the `-` rows.

Root causes (confirmed by running the collector + reading the lockfiles):
1. **Version = pyproject specifier floor, not the installed version.** `openai>=2.30.0`
   and `openai>=1.0.0` render as two rows (`2.30.0`, `1.0.0`); `uv.lock` resolves **both
   to `2.30.0`**. Same for `google-genai` (floor `1.0.0` vs lock `1.68.0`) and `requests`
   (`2.31.0` vs `2.33.0`). The dedup key includes the floor version, so dups never merge.
2. **License resolution is fragile.** `detect_python_license` reads only the *manifest-
   local* `.venv`. When one plugin's venv is unsynced at regen time the row falls to
   `NOT_INSTALLED` → `-`. That is exactly how the committed artifact got `-` rows while
   other rows resolved.
3. **Dishonest verdict.** `NOT_INSTALLED` rows render `-` but are excluded from the
   verdict, so the report claims "all permissive" while `-` rows exist.

## Approach (chosen)

All in `plugins/shipwright-compliance` (renderer + collector; the triage producer is
**left untouched** — it has 30+ tests and a different surface):

1. **`collectors/_uv_lock.py` (NEW)** — `load_lock_versions(manifest_dir)` parses the
   sibling `uv.lock` (stdlib `tomllib`) → `{canonical_name: resolved_version}`.
2. **Version from lockfile + dedup by installed version** — in `collectors/sbom.py`,
   the SBOM-inventory path resolves each Python dep's version from the sibling lock
   (fallback = floor) and dedups by `(canonical_name, resolved_version, dep_type)`.
   `openai` collapses to one row. A merged-count + lock-used flag flow to `ComplianceData`.
3. **Robust license resolution** — resolve the Python license across **all** `.venv`s
   under the project (a package installed in any venv resolves everywhere). A real
   license anywhere wins; `UNKNOWN_LICENSE` only if installed-but-no-license everywhere;
   `NOT_INSTALLED` only if absent from every venv. The triage path keeps strict
   per-manifest resolution (unchanged).
4. **Honest generator** (`sbom_render.py` NEW — extracted to keep `sbom_generator.py`
   under its grandfathered 580-line ceiling):
   - Summary gains **`| Licenses resolved | X / Y |`** (Y = all packages) + a
     `(deduplicated)` annotation on the runtime count when rows merged.
   - Pie title **`License Distribution (all N packages)`** + an `unknown` slice so it
     counts every package.
   - Header gains **`(dependency versions resolved from uv.lock)`** when a lock was used.
   - Verdict: **`No license concerns: all N packages resolved (0 unknown, 0 copyleft)`**
     when clean; otherwise **`K of N dependency licenses unresolved - verify`** and the
     report never claims "all permissive" while any unresolved row remains. Genuine
     no-declared-license rows keep their "declare no license" line + section.
   - **ASCII-only** (hard constraint — `test_doc_is_ascii_even_with_fall2_deps` calls
     `generate(...).encode("ascii")`; the example markdown's ✅/⚠️/· cannot be used).
5. **Regenerate** the real `sbom.md` (venvs synced) → 5 runtime (deduped) + 2 dev = 7,
   all resolved, 0 unknown, 0 copyleft.

### Alternatives considered (rejected)
- **Data-only fix** (just `uv sync` + regenerate by hand): rejected — leaves `openai`
  duplicated (version still = floor) and re-breaks on the next unsynced-venv regen. AR-04
  explicitly asks to fix the *generator* ("dedupe by installed version", "make the line
  honest"). Band-aid, not root cause.
- **Add npm-lockfile version resolution too** (fully generic): deferred — this repo has
  **no npm deps** (untestable here), and the webui's npm dedup is a separate **repo
  data-fix** in the webui repo per the spec's plugin-vs-data-fix table. Noted as follow-up.

## Affected boundaries
- **Reads (new input):** `uv.lock` (TOML) per Python manifest; `.venv/**/dist-info/METADATA`
  across all venvs.
- **Writes:** `.shipwright/compliance/sbom.md` (regenerated).
- **Contract change:** `sbom.md` summary/verdict shape; `ComplianceData` gains
  `dependencies_deduped`, `dependencies_lock_resolved`.
- **Behavior-doc change:** `NOT_INSTALLED` is no longer silent in the *doc verdict* (it is
  counted as unresolved); it stays silent in *triage*. Docstrings updated
  (`_license_const.py`, `sbom_generator.generate`, `test_sbom_not_installed` header).

## WebUI (just-checking, separate repo — NOT changed here)
`shipwright-webui` has the **dedup half** only: `@types/node` / `tsx` / `typescript`
declared at different ranges across `client/` + `server/` → 66 packages (should be 63).
Its licenses all resolve, so its "all permissive" line is already honest. Per the spec
this is a webui-repo data-fix (a separate iterate). Reported to the user; not touched.

## Confidence Calibration
- **Boundaries touched:** `uv.lock` TOML parse (new `_uv_lock.py`), all-venv `METADATA`
  scan (new `_venv_scan.py`), `sbom.md` render contract (`sbom_render.py` + generator),
  `ComplianceData` (+2 fields), `mermaid.license_pie` signature.
- **Empirical probes run:**
  - Ran the new generator against the **synced main tree** → clean artifact:
    `openai` once @ `2.30.0` (deduped from 2 declarations), `google-genai 1.68.0` /
    `requests 2.33.0` (lock versions, not floors), **7/7 licenses resolved**, honest
    verdict, `deduped=29`, `lock_resolved=True`.
  - Ran against the **worktree after syncing root+plan venvs** → byte-identical clean
    artifact (so F5b's regen reproduces it).
  - `generate(...).encode("ascii")` passes on both — confirmed the hard ASCII-only
    constraint (`test_doc_is_ascii_even_with_fall2_deps`); the example markdown's
    ✅/⚠️/· would have failed, so the real output uses ASCII (`-`, plain words).
  - Full compliance suite **793 passed**; ruff (0.15.15) clean; anti-ratchet clean
    (`sbom_generator.py` 580→522, baseline ratcheted down).
- **Test Completeness Ledger:** every behavior introduced is `tested`:
  | Behavior | Test |
  |---|---|
  | `uv.lock` version parse (canonical, missing, malformed) | `TestLoadLockVersions` (4) |
  | version-from-lock + dedup (openai collapse, floor fallback) | `TestDedupByInstalledVersion` (3) |
  | global all-venv license resolution (incl. sibling-venv, no-license, real-wins) | `TestGlobalLicenseResolution` (4) |
  | `parse_pyproject_dep_specs` triples | `TestParsePyprojectDepSpecs` |
  | `ComplianceData` dedup/lock flags + `collect_all` wiring | `TestCollectAllFlags` (2) |
  | summary `Licenses resolved X/Y`, `(deduplicated)`, header lock note | `TestHonestRender` (4) |
  | pie counts all packages + `unknown` slice | `test_pie_counts_all_packages` + `test_mermaid` |
  | honest verdict (clean / unresolved / declare-no-license) | `TestHonestRender` (3) + updated `test_sbom_not_installed` + `test_sbom_generator` |
  | ASCII-only output | `test_output_is_ascii` + `test_doc_is_ascii_even_with_fall2_deps` |
  | copyleft still warns | `test_copyleft_still_warns` |
  | `sbom_render` units | `TestSbomRenderUnits` (4) |
  | real-repo clean `sbom.md` end-to-end | empirical probe (main + worktree generate) |

  No `untestable` rows; no "could-test-but-didn't". Triage producer untouched →
  its 30+ tests stay green (verified in the 793).
- **Confidence-pattern check:**
  - *Asymptote (depth):* dug to the actual mechanism (lockfile resolves above the
    floor; per-manifest venv fragility = the root cause of the dishonest committed
    artifact) and verified by running the real generator on both trees.
  - *Coverage (breadth):* lock-parse + dedup + global-license + render + pie +
    verdict + ASCII + copyleft + flags all unit-tested; full suite + lint + anti-ratchet green.
  - *Integration composition:* **not `cross_component`** — change is confined to one
    plugin's collector/generator (no merge/hooks/phase-validator/campaign machinery),
    so no integration-coverage gate applies (F11 `check_integration_coverage` recomputes
    the flag from the diff and will agree).
