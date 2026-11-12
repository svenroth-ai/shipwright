# U3 run spec - audit G2 scope handling (cards trg-13c59214 amended, trg-5acb749f)

Normative source: campaign brief 2026-11-11-leadwright-followups-BRIEF.md section 2 U3.

## Acceptance criteria
- [x] AC1 A commit scope joined by commas (`feat(daemon,lib):`) is split on commas, trimmed, empty parts dropped; every part must be known; known+known passes; known+unknown reports only the unknown part; the evidence lists each unknown part.
- [x] AC2 The audit source comment and the compliance skill text no longer promise an automatic skip of G2 for adopted projects; they point to `disabled_checks: ["G2"]` or the project's own `g2_alias_map` / `g2_stoplist`. Pinned by a test.
- [x] AC3 G2 behaviour for a single scope is unchanged.

## Spec Impact
- **Classification:** modify
- **MODIFY:** FR-01.10 (compliance audit): comma-joined scope judged per part.

## Out of Scope
Any automatic G2 skip (operator decision 3.4). Changing the stoplist defaults.

## Affected Boundaries
n/a - no serialized format changes; commit subject text is parsed in memory.

## Verification
- **Surface:** cli
- **Runner command:** `uv run python plugins/shipwright-compliance/scripts/audit/run_audit.py --project-root . --only G`
- **Evidence path:** .shipwright/runs/iterate-2026-11-12-u3-g2-scope-audit/surface_verification.json
