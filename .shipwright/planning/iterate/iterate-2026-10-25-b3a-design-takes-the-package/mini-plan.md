# Mini-plan B3a: Design takes the Brief package

Change: new design-phase tool `apply-brief-package.py` (re-verifies the package hash via the merged
B2 module `brief_dir_intake.verify_run_config`, loaded by file path), copies each mockup byte-identical
to `uploads/` and to `screens/NN-<id>.html` with a `<!-- Requirements: FR-xx.yy -->` comment injected
(`inject_requirements` in `screen_registry.py`). Capability slugs from `screen-map.json` resolve to FR ids
minted in `spec.md` (Name -> slug via `grill_trace_fr_coverage.slugify`). All validation before any write;
a differing existing file is never overwritten. Also copies the package's design_system file to
visual-guidelines.md and regenerates design-manifest.md. Docs: upload-mode.md, SKILL.md pointer.
A1 fixture 1 gets Colours/Typography/Spacing headings (tokens gate) and its pinned hash is updated.
Tests: plugin tests (11) with own minimal packages, integration test on fixture 1 with all gates.
Deferred by decision: snapshot isolation (U3), answer-time hash verification (U1/U2).
