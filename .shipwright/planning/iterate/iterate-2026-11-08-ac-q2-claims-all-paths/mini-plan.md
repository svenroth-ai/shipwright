# Mini-plan: pass the AC claims on every review path

1. Campaign runner Step 3.7 and orchestrator 3f-bis: run `ac_claims.py build` before the Stage-1 spawn; pass the file only when it holds claims.
2. Codex driver: `review_via_codex.py --claims-file` (role spec only); `codex_spec_review_schema.json` gets a required-nullable `ac_verdicts` (OpenAI strict mode); dispatch doc shows the build and the flag.
3. `record_review_pass` already copies `ac_verdicts`; no change. Warning only; unchanged when a run has no AC items.
4. Tests first (hermetic), docs (hooks-and-pipeline, iteration-reviews), changelog, decision drop.
