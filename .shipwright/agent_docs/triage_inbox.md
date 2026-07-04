# Triage Inbox

> Auto-generated 2026-07-04T13:09:10.541223Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 264
- Triage: 6 | Promoted: 1 | Dismissed: 256 | Snoozed: 1

## Top 6 items (severity-sorted)

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

### Source: drift (1 item)

<a id="trg-4c6dedc1"></a>
- **Drift: C:\01_Development\shipwright\CLAUDE.md: 'plugins/shipwright-grade/' exists on disk but not listed in Structure** `id=trg-4c6dedc1 | severity=medium | kind=maintenance → P2/engineering`
  - C:\01_Development\shipwright\CLAUDE.md: 'plugins/shipwright-grade/' exists on disk but not listed in Structure
  - Promote: `triage_promote.py --id trg-4c6dedc1 --task-ref EXT:<ref>`

### Source: github (1 item)

<a id="trg-b5a4e13e"></a>
- **GitHub prompt-injection: 3 finding(s) (high)** `id=trg-b5a4e13e | severity=high | kind=bug → P1/engineering`
  - Repo svenroth-ai/shipwright \| prompt-injection (prompt_risks.json): 3 high \| run: https://github.com/svenroth-ai/ship…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-security
    
    Context: the shipwright-security prompt-injection scan reports 3 open finding(s) for svenroth-ai/shipwright.
    Severity breakdown — prompt-injection: 3 high.
    Workflow run: https://github.com/svenroth-ai/shipwright/actions/runs/28686996368
    Re-scan locally: see docs/security-ci-setup.md
    Source: triage item gh-prompt:svenroth-ai/shipwright
    ```
  - Promote: `triage_promote.py --id trg-b5a4e13e --task-ref EXT:<ref>`

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

