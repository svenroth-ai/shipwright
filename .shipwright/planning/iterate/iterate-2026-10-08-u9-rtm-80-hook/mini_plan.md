# Mini-plan: U9 - commit-time 80% hook measures requirement coverage

## Problem
`check_rtm_coverage.py` gates `git commit` on the RTM line "Traceability coverage NN%", which is the share of build sections with a commit. Adopted projects have no build sections, so the line is absent and the hook allows every commit silently. The name and the whitepaper promise requirement coverage.

## Change
1. New pure module `plugins/shipwright-compliance/scripts/lib/rtm_manifest_coverage.py`: reads the committed `.shipwright/compliance/test-traceability.json`; FR metric (active requirements with >=1 test status=enabled and executed=pass) and a separate AC metric (same rule per AC); inactive requirements excluded; zero denominator is "unmeasurable", never 100%; staleness WARN by age (>14 d) or commits behind HEAD (>300, best effort git). No regeneration in the hook.
2. Hook: manifest first; legacy section line only when there is no usable manifest; every previous silent fail-open (corrupt manifest, no active requirements, compliance data but no figure, invalid threshold config) emits a visible WARN via additionalContext (exit 0). Soft-block + logged override unchanged; the block message prints the definition and the FR/AC counts.
3. Ratchet: optional `enforcement.rtm_coverage_baseline`; effective threshold = min(min-config, baseline), so a project far below 80% does not get a permanent soft-block.
4. Measurement (Step 1 of the unit): this repo (committed manifest 2026-09-28) = FR 21/21 (100%), AC 246/285 (86%) with the AC inventory taken from the spec (the manifest omits untagged ACs; an earlier 246/247 figure was wrong); no ratchet needed here.
Tests: pure-function tests + subprocess hook tests, tagged `pytest.mark.covers("FR-01.10")`.
