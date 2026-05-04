---
campaign: iterate-skill-hardening
branch_strategy: stacked
created: 2026-05-03T18:42:00.809326+00:00
---

# Campaign: iterate-skill-hardening

## Intent

Harden iterate skill with boundary-tests (A), confidence-calibration (B), multi-session-discipline (C), and boundary-coverage reporting (D). Triggered by latent producer-consumer bugs in iterate-2026-05-03-adopt-env-local-scaffold (BOM + inline-comment) that escaped unit tests + dual-LLM-review and were only caught by an empirical round-trip probe. Lerneffekt encoded into the skill itself.

## Sub-Iterates

| ID | Slug | Title | Status |
|---|---|---|---|
| A | boundary-tests-foundation | Boundary Tests Foundation | complete |
| B | confidence-calibration-phase | Confidence Calibration Phase | complete |
| C | multi-session-discipline | Multi-Session Discipline | complete |
| D | boundary-coverage-report | shipwright-test Boundary-Coverage-Report | complete |
| E | review-driven-hardening | Review-Driven Hardening (HIGH+critical-MEDIUM fixes from post-D code+external review) | pending |
| F | runner-contract-mandates-reviews | Runner Contract Mandates Reviews (closes the meta-loop) | pending |

## Review pass (between D and E)

After D shipped locally, we ran the reviews the runner contract should
have triggered automatically:
- 4× code-reviewer subagents (one per A/B/C/D)
- 4× `external_review.py --mode code` (OpenRouter dual-LLM Gemini+OpenAI)
- 1× holistic `external_review.py` over the campaign-level diff

Result: 6 HIGH findings (4 empirically verified by reading shipped code)
and ~12 MEDIUMs. Sub-Iterate E addresses these. Sub-Iterate F patches
the runner contract so future campaigns trigger reviews automatically.
