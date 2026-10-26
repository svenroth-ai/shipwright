# Architecture brief: checking that built screens look like the approved mockups

Problem: in a brief-driven unattended run the design is approved before the build, but nothing in the Test
phase proves the built app still shows those screens. The existing structural fidelity step only compares
source text and is non-blocking, so a blank or wrong page can ship.

Options:
1. New blocking Test-phase check: screenshot mockup and built route in Chromium, compare with a layout metric and a tolerance.
2. Make the existing structural fidelity step blocking for Brief-package projects.
3. Leave it to the end-to-end run / human review.

Constraint: projects without a Brief package keep today's behaviour; the plugin has no third-party Python dependency;
a Test gate must not approve, waive or edit designs.
New permanent things: one comparison module, one capture script, one check script.
