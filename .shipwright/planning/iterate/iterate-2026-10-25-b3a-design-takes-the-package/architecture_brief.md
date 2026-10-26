# Architecture brief: placing a Brief package's mockups into the design phase

Problem: a Brief package ships approved HTML mockups plus screen-map.json (screen id, mockup file,
capability slugs). The design phase needs those mockups as `uploads/` (kept byte-identical) and as
numbered `screens/NN-name.html` linked to the FR ids Project minted later, so the registry, FR-coverage
and flow gates pass without a human mapping step.

Options:
1. New script in the design plugin that verifies the package, copies files, injects the FR comment, writes the manifest.
2. Prose only: extend upload-mode.md so the agent does the mapping and copies by hand.
3. Extend `screen_registry.py` / `design_gate_extras.py` with the placement logic and call it from the existing setup script.

Constraint: the package hash must be verified before use; no FR id may be hand-typed; shared libs load by file path.
Nothing permanent is added beyond one script and one helper function.
