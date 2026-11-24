# Mini-plan: P7 conversion check, retirements, passing-vs-junit check

Goal: prove the changelog conversion is complete, retire the pilot scaffolding, close the freeze holes, write the reports (programme Tz).

Steps: (1) shared/config/plugin_conversion.json registry + shared/scripts/tools/check_plugin_conversion.py (A-items gone from prose, B-items exist, CLI called, Codex bundle resolves release.py and starts, optional verify_local) + junit_promises.py (passing status vs the run's JUnit report, freeze sentinel, seeded regressions, trace.json export). (2) In-process tests with one seeded fault per A/B-item. (3) Retire check_skill_inventory.py + tests + the three inventory data files, and golden coverage.py + test_coverage_checks.py; P8c, spec reader and the orphan-trace guard move to scenario_index.py (frozen). (4) golden_lock.py --repin, approved_deltas.json emptied, entries reviewed against the 26 earlier deltas. (5) baseline/trace.json export, saving report, FINDINGS and LEARNINGS closed, docs. (6) No orphan test removed (no per-test approval list; operator decision).

Risks: the re-pin folds 33 earlier deltas; not wired into CI (ci.yml edit would need a human ack); skill-check shape of trace.json unverified.

Alternative considered: a session-outcome hook in the frozen golden conftest instead of a junit reader (rejected: the conftest is frozen and the hook would sit inside the file it must guard).
