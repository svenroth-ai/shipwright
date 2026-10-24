# Architecture brief: A2 extraction

Problem: four modules sit at or over the 300-LOC cap (gate_policy 301, design_gate_extras 300, phase_validators 495, phase_task_lifecycle 725); upcoming units must add code to them and the bloat gate would block or force baseline ratchets.

Options:
1. Do nothing; let each later unit add a baseline exception or split ad hoc under time pressure.
2. Move cohesive, already-isolated chunks (renderer, late-phase validators, lookup/planning/recovery transitions, HTML/feedback gates) into sibling modules and re-export the old names from the original module; no behaviour change.
3. Rewrite the lifecycle as a package (phase_task_lifecycle/ with __init__), changing import paths.

Chosen scope is option 2. Smallest alternative: only the minimum moves to get under 300 (e.g. just the renderer and the late validators), leaving lifecycle over cap.
