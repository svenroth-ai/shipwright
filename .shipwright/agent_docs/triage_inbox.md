# Triage Inbox

> Auto-generated 2026-07-05T19:40:34.721218Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 268
- Triage: 6 | Promoted: 1 | Dismissed: 260 | Snoozed: 1

## Top 6 items (severity-sorted)

### Source: compliance (1 item)

<a id="trg-c99d9547"></a>
- **Compliance: 1 open finding(s)** `id=trg-c99d9547 | severity=medium | kind=compliance → P2/compliance`
  - 1 open compliance finding(s): H/H2  - H/H2: Bloat ratchet-suggestion (baseline current > actual) — plugins/shipwright-c…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 1 open compliance finding(s): H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-c99d9547 --task-ref EXT:<ref>`

### Source: diff-coverage-followup (1 item)

<a id="trg-8fdebda3"></a>
- **Measure patch/diff coverage (were the CHANGED lines tested?), not just pass-rate** `id=trg-8fdebda3 | severity=high | kind=improvement → P1/engineering`
  - Reviewer comment B: '3618/3618 green' is pass-rate, not coverage — it says nothing about whether AI-added code is even…
  - Promote: `triage_promote.py --id trg-8fdebda3 --task-ref EXT:<ref>`

### Source: github (2 items)

<a id="trg-7dbad194"></a>
- **[pr-ci] PR #320 has 1 failing check(s) on iterate/grade-report-audience-copy** `id=trg-7dbad194 | severity=high | kind=bug → P1/engineering`
  - PR #320 "feat(grade): audience-facing plain-language report redesign" on iterate/grade-report-audience-copy \| failing…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate --type bug
    
    Context: open PR #320 (https://github.com/svenroth-ai/shipwright/pull/320) has 1 failing required check(s) on branch 'iterate/grade-report-audience-copy': Python (lint + test).
    This blocks auto-merge — the PR sits armed-but-waiting until fixed.
    Source: triage item gh-pr-ci:320
    ```
  - Promote: `triage_promote.py --id trg-7dbad194 --task-ref EXT:<ref>`

<a id="trg-ba2b3f98"></a>
- **GitHub prompt-injection: 2 finding(s) (medium)** `id=trg-ba2b3f98 | severity=medium | kind=improvement → P2/engineering`
  - Repo svenroth-ai/shipwright \| prompt-injection (prompt_risks.json): 2 medium \| run: https://github.com/svenroth-ai/sh…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-security
    
    Context: the shipwright-security prompt-injection scan reports 2 open finding(s) for svenroth-ai/shipwright.
    Severity breakdown — prompt-injection: 2 medium.
    Workflow run: https://github.com/svenroth-ai/shipwright/actions/runs/28719714629
    Re-scan locally: see docs/security-ci-setup.md
    Source: triage item gh-prompt:svenroth-ai/shipwright
    ```
  - Promote: `triage_promote.py --id trg-ba2b3f98 --task-ref EXT:<ref>`

### Source: grader-campaign (1 item)

<a id="trg-e68e9901"></a>
- **Build shipwright-grade: repo-agnostic Control Grade grader (lead magnet)** `id=trg-e68e9901 | severity=high | kind=improvement → P1/engineering`
  - New standalone read-only plugin that grades ANY git repo (incl. non-Shipwright) with the same Control Grade rubric by p…
  - Promote: `triage_promote.py --id trg-e68e9901 --task-ref EXT:<ref>`

### Source: manual (1 item)

<a id="trg-cced399c"></a>
- **Decompose FR-01.10 / FR-01.07 into sub-FRs for precise feature traceability** `id=trg-cced399c | severity=low | kind=improvement → P3/engineering`
  - Follow-up to iterate-2026-06-30-fr-retag-honesty. Introduce sub-FRs (e.g. FR-01.10.x for Control Grade / RTM / SBOM / d…
  - Promote: `triage_promote.py --id trg-cced399c --task-ref EXT:<ref>`

