# Plan: P5 tidy mixed ACs and command-named FR titles

Goal (WHAT): acceptance criteria state the promise only; the 13 command-named requirement titles (FR-01.01 to FR-01.13) name a capability, so a rebuild that reshapes the tools keeps a stable anchor.

Reason (WHY): baseline-package campaign, unit P5 (`.shipwright/planning/campaigns/2026-10-31-baseline-package-BRIEF.md`). Model, vendor, threshold and format detail inside an AC makes a promise look like it must change when only the mechanism changes.

## Detail moved out of the ACs (current realisation, not the promise)

| AC | Detail removed from the AC text |
|---|---|
| FR-01.03 AC02 | Two outside reviewers (GPT + GLM via the external-review path); the gate is a missing API access key. |
| FR-01.03 AC03 | The internal reviewer's Claude model is set per project (`ModelConfig` plan-review tier), default `inherit` = the session model. |
| FR-01.03 AC07 | Minimum of two implementation steps per section (tuning number in the section validator). |
| FR-01.04 AC13 | Brand source is the claude.ai Design System. |
| FR-01.11 AC11 | Review passes recorded today: self, plan, code, doubt, external code. |
| FR-01.11 AC30 | Drivers are Claude and Codex; reviewer pairs are chosen per driver. |
| FR-01.11 AC32 | `fable` joins `opus`/`sonnet`/`haiku` as an accepted tier value; AC34 keeps the "every written-out list agrees" promise. |
| FR-01.11 AC35 | Codex reviewer model precedence: per-call, then session environment variable, then project config. |
| FR-01.14 AC14 | Sources are the code host's code-scanning analysis and the artifact published by the security workflow. |
| FR-01.14 AC18 | Entry stores aggregated counts, stable links and a length cap on detail. |
| FR-01.20 AC01 | One exchange is several transcript lines sharing a request id; they are folded by that id. |
| FR-01.21 AC05 | `codex_hooks_sync.py` syncs hooks into Codex's global config-layer hooks file; verified under real `codex exec` without `--dangerously-bypass-hook-trust`; Codex ignores a plugin-bundled `hooks` key (openai/codex#16430, #39895). |

## Title renames (heading and Name column in the catalog table)

FR-01.01 End-to-end delivery pipeline; .02 Project decomposition into scoped units; .03 Implementation planning with independent review; .04 Mockups from requirements; .05 Test-driven build of planned sections; .06 Multi-level project testing; .07 Security scanning and remediation; .08 Deployment and rollback; .09 Release notes and changelog; .10 Audit-ready compliance evidence; .11 Ongoing change at the depth it deserves; .12 Local project preview; .13 Onboarding an existing codebase. IDs, order and ACs are unchanged, so no re-mint. FR-01.18 (`/shipwright-grade`) is not in the brief's 13 and is left as is.
