# Triage Inbox

> Auto-generated 2026-07-03T21:56:46.817090Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 258
- Triage: 5 | Promoted: 1 | Dismissed: 251 | Snoozed: 1

## Top 5 items (severity-sorted)

### Source: compliance (1 item)

<a id="trg-1255fabe"></a>
- **Compliance: 1 open finding(s)** `id=trg-1255fabe | severity=medium | kind=compliance → P2/compliance`
  - 1 open compliance finding(s): H/H2  - H/H2: Bloat ratchet-suggestion (baseline current > actual) — plugins/shipwright-c…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 1 open compliance finding(s): H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-1255fabe --task-ref EXT:<ref>`

### Source: diff-coverage-followup (1 item)

<a id="trg-8fdebda3"></a>
- **Measure patch/diff coverage (were the CHANGED lines tested?), not just pass-rate** `id=trg-8fdebda3 | severity=high | kind=improvement → P1/engineering`
  - Reviewer comment B: '3618/3618 green' is pass-rate, not coverage — it says nothing about whether AI-added code is even…
  - Promote: `triage_promote.py --id trg-8fdebda3 --task-ref EXT:<ref>`

### Source: github (1 item)

<a id="trg-544fa61e"></a>
- **GitHub security: 26 shipwright-security finding(s) (medium)** `id=trg-544fa61e | severity=medium | kind=improvement → P2/engineering`
  - Repo svenroth-ai/shipwright \| code-scanning: (unavailable) \| dependabot: (unavailable) \| shipwright-security: 12 med…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-security
    
    Context: the shipwright-security CI workflow reports 26 open finding(s) for svenroth-ai/shipwright (GHAS Code Scanning is not configured).
    Severity breakdown — shipwright-security: 12 medium, 14 low.
    Workflow run: https://github.com/svenroth-ai/shipwright/actions/runs/28666243321
    Re-scan locally: see docs/security-ci-setup.md
    Source: triage item gh-security:svenroth-ai/shipwright
    ```
  - Promote: `triage_promote.py --id trg-544fa61e --task-ref EXT:<ref>`

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

